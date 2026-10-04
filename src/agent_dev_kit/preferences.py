from dataclasses import dataclass, field
from importlib.resources import files
from pathlib import Path
from typing import Any, Iterable

import yaml

from agent_dev_kit.agent_definition import AgentDefinition


@dataclass(frozen=True, slots=True)
class PreferenceRule:
    id: str
    rule: str
    agents: tuple[str, ...] = ()
    include_projects: tuple[str, ...] = ()
    exclude_projects: tuple[str, ...] = ()

    def applies_to(self, *, project_name: str, agent_key: str) -> bool:
        normalized_agent = normalize_key(agent_key)
        normalized_project = project_name.strip().lower()

        if self.agents and normalized_agent not in {
            normalize_key(value) for value in self.agents
        }:
            return False

        if self.include_projects and normalized_project not in {
            value.strip().lower() for value in self.include_projects
        }:
            return False

        if normalized_project in {
            value.strip().lower() for value in self.exclude_projects
        }:
            return False

        return True


@dataclass(frozen=True, slots=True)
class ProjectPreferenceConfig:
    disabled_global: tuple[str, ...] = ()
    preferences: tuple[PreferenceRule, ...] = ()


@dataclass(frozen=True, slots=True)
class PreferenceCandidate:
    id: str
    rule: str
    agents: tuple[str, ...] = ()
    observations: int = 1
    projects: tuple[str, ...] = ()

    def is_ready_for_confirmation(self, threshold: int = 3) -> bool:
        return self.observations >= threshold


@dataclass(slots=True)
class PreferenceProfile:
    name: str
    preferences: list[PreferenceRule] = field(default_factory=list)
    candidates: dict[str, PreferenceCandidate] = field(default_factory=dict)


def load_default_profile() -> PreferenceProfile:
    resource = files("agent_dev_kit").joinpath("profiles/default.yaml")
    with resource.open("r", encoding="utf-8") as stream:
        return _profile_from_mapping(yaml.safe_load(stream) or {})


def load_profile(path: str | Path) -> PreferenceProfile:
    with Path(path).open("r", encoding="utf-8") as stream:
        return _profile_from_mapping(yaml.safe_load(stream) or {})


def save_profile(profile: PreferenceProfile, path: str | Path) -> None:
    data = {
        "profile": {"name": profile.name},
        "preferences": [
            _preference_to_mapping(item) for item in profile.preferences
        ],
        "candidates": [
            {
                "id": item.id,
                "rule": item.rule,
                "agents": list(item.agents),
                "observations": item.observations,
                "projects": list(item.projects),
            }
            for item in profile.candidates.values()
        ],
    }
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        yaml.safe_dump(
            data,
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )


def load_project_preference_config(
    path: str | Path,
) -> ProjectPreferenceConfig:
    preference_path = Path(path)
    if not preference_path.is_file():
        return ProjectPreferenceConfig()

    with preference_path.open("r", encoding="utf-8") as stream:
        data = yaml.safe_load(stream) or {}

    if not isinstance(data, dict):
        raise ValueError(
            f"Preference configuration root must be a mapping: {path}"
        )

    disabled = data.get("disabled_global") or []
    if not isinstance(disabled, list):
        raise ValueError("'disabled_global' must be a list.")

    raw_preferences = data.get("preferences") or []
    if not isinstance(raw_preferences, list):
        raise ValueError("'preferences' must be a list.")

    return ProjectPreferenceConfig(
        disabled_global=tuple(
            str(item).strip()
            for item in disabled
            if str(item).strip()
        ),
        preferences=tuple(
            _preference_from_mapping(item)
            for item in raw_preferences
        ),
    )


def resolve_preferences(
    profile: PreferenceProfile,
    *,
    project_name: str,
    agent_key: str,
    project_config: ProjectPreferenceConfig | None = None,
) -> tuple[PreferenceRule, ...]:
    project_config = project_config or ProjectPreferenceConfig()
    disabled = {
        normalize_key(value)
        for value in project_config.disabled_global
    }

    global_rules = [
        rule
        for rule in profile.preferences
        if normalize_key(rule.id) not in disabled
        and rule.applies_to(
            project_name=project_name,
            agent_key=agent_key,
        )
    ]

    local_rules = [
        rule
        for rule in project_config.preferences
        if rule.applies_to(
            project_name=project_name,
            agent_key=agent_key,
        )
    ]

    return tuple(global_rules + local_rules)


def apply_preference_rules(
    definition: AgentDefinition,
    rules: Iterable[PreferenceRule],
) -> AgentDefinition:
    resolved = tuple(rules)
    if not resolved:
        return definition

    rendered = "\n".join(
        f"- [{rule.id}] {rule.rule}"
        for rule in resolved
    )
    instructions = (
        f"{definition.instructions.rstrip()}\n\n"
        "Confirmed user preferences applicable to this context:\n"
        f"{rendered}\n"
    )

    return AgentDefinition(
        name=definition.name,
        instructions=instructions,
        handoff_description=definition.handoff_description,
        model=definition.model,
    )


def record_preference_observation(
    profile: PreferenceProfile,
    *,
    pattern_id: str,
    rule: str,
    agents: Iterable[str] = (),
    project_name: str | None = None,
) -> PreferenceCandidate:
    """Accumulate a repeated preference signal without confirming it."""

    candidate_id = normalize_key(pattern_id)
    existing = profile.candidates.get(candidate_id)

    normalized_agents = tuple(
        dict.fromkeys(normalize_key(item) for item in agents)
    )
    projects = tuple(
        [project_name.strip()]
        if project_name and project_name.strip()
        else []
    )

    if existing is None:
        candidate = PreferenceCandidate(
            id=candidate_id,
            rule=rule.strip(),
            agents=normalized_agents,
            observations=1,
            projects=projects,
        )
    else:
        candidate = PreferenceCandidate(
            id=existing.id,
            rule=existing.rule,
            agents=tuple(
                dict.fromkeys(existing.agents + normalized_agents)
            ),
            observations=existing.observations + 1,
            projects=tuple(
                dict.fromkeys(existing.projects + projects)
            ),
        )

    profile.candidates[candidate_id] = candidate
    return candidate


def confirm_preference_candidate(
    profile: PreferenceProfile,
    candidate_id: str,
    *,
    exclude_projects: Iterable[str] = (),
) -> PreferenceRule:
    key = normalize_key(candidate_id)
    try:
        candidate = profile.candidates.pop(key)
    except KeyError as exc:
        raise KeyError(
            f"Unknown preference candidate '{candidate_id}'."
        ) from exc

    confirmed = PreferenceRule(
        id=candidate.id,
        rule=candidate.rule,
        agents=candidate.agents,
        exclude_projects=tuple(exclude_projects),
    )
    profile.preferences = [
        item
        for item in profile.preferences
        if normalize_key(item.id) != key
    ]
    profile.preferences.append(confirmed)
    return confirmed


def _profile_from_mapping(data: Any) -> PreferenceProfile:
    if not isinstance(data, dict):
        raise ValueError("Preference profile root must be a mapping.")

    profile_section = data.get("profile") or {}
    if not isinstance(profile_section, dict):
        raise ValueError("'profile' must be a mapping.")

    name = str(profile_section.get("name") or "default").strip()

    raw_preferences = data.get("preferences") or []
    if not isinstance(raw_preferences, list):
        raise ValueError("'preferences' must be a list.")

    raw_candidates = data.get("candidates") or []
    if not isinstance(raw_candidates, list):
        raise ValueError("'candidates' must be a list.")

    preferences = [
        _preference_from_mapping(item)
        for item in raw_preferences
    ]

    candidates: dict[str, PreferenceCandidate] = {}
    for item in raw_candidates:
        if not isinstance(item, dict):
            raise ValueError("Each preference candidate must be a mapping.")
        candidate = PreferenceCandidate(
            id=normalize_key(str(item.get("id") or "")),
            rule=str(item.get("rule") or "").strip(),
            agents=tuple(
                normalize_key(str(value))
                for value in (item.get("agents") or [])
            ),
            observations=int(item.get("observations") or 1),
            projects=tuple(
                str(value).strip()
                for value in (item.get("projects") or [])
            ),
        )
        if not candidate.id or not candidate.rule:
            raise ValueError(
                "Preference candidates require id and rule."
            )
        candidates[candidate.id] = candidate

    return PreferenceProfile(
        name=name,
        preferences=preferences,
        candidates=candidates,
    )


def _preference_from_mapping(data: Any) -> PreferenceRule:
    if not isinstance(data, dict):
        raise ValueError("Each preference must be a mapping.")

    preference_id = normalize_key(str(data.get("id") or ""))
    rule = str(data.get("rule") or "").strip()
    if not preference_id or not rule:
        raise ValueError("Preferences require id and rule.")

    return PreferenceRule(
        id=preference_id,
        rule=rule,
        agents=tuple(
            normalize_key(str(value))
            for value in (data.get("agents") or [])
        ),
        include_projects=tuple(
            str(value).strip()
            for value in (data.get("include_projects") or [])
        ),
        exclude_projects=tuple(
            str(value).strip()
            for value in (data.get("exclude_projects") or [])
        ),
    )


def _preference_to_mapping(rule: PreferenceRule) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": rule.id,
        "rule": rule.rule,
    }
    if rule.agents:
        data["agents"] = list(rule.agents)
    if rule.include_projects:
        data["include_projects"] = list(rule.include_projects)
    if rule.exclude_projects:
        data["exclude_projects"] = list(rule.exclude_projects)
    return data


def normalize_key(value: str) -> str:
    return value.strip().lower().replace("-", "_").replace(" ", "_")
