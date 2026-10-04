from agent_dev_kit.preferences import (
    PreferenceProfile,
    PreferenceRule,
    ProjectPreferenceConfig,
    confirm_preference_candidate,
    load_default_profile,
    load_profile,
    record_preference_observation,
    resolve_preferences,
    save_profile,
)


def test_default_profile_contains_confirmed_global_preferences():
    profile = load_default_profile()
    ids = {item.id for item in profile.preferences}

    assert "modular_structure" in ids
    assert "single_responsibility_owner" in ids


def test_global_preference_respects_agent_scope():
    profile = load_default_profile()

    backend = resolve_preferences(
        profile,
        project_name="Example",
        agent_key="backend",
    )
    testing = resolve_preferences(
        profile,
        project_name="Example",
        agent_key="testing",
    )

    assert "modular_structure" in {item.id for item in backend}
    assert "modular_structure" not in {item.id for item in testing}


def test_project_can_disable_one_global_preference():
    profile = load_default_profile()
    project = ProjectPreferenceConfig(
        disabled_global=("modular_structure",),
    )

    resolved = resolve_preferences(
        profile,
        project_name="Example",
        agent_key="backend",
        project_config=project,
    )

    assert "modular_structure" not in {item.id for item in resolved}
    assert "single_responsibility_owner" in {
        item.id for item in resolved
    }


def test_project_specific_preference_is_added():
    profile = PreferenceProfile(name="empty")
    project = ProjectPreferenceConfig(
        preferences=(
            PreferenceRule(
                id="project_rule",
                rule="Use the project's explicit convention.",
                agents=("backend",),
            ),
        )
    )

    resolved = resolve_preferences(
        profile,
        project_name="Example",
        agent_key="backend",
        project_config=project,
    )

    assert [item.id for item in resolved] == ["project_rule"]


def test_global_preference_can_exclude_project():
    profile = PreferenceProfile(
        name="example",
        preferences=[
            PreferenceRule(
                id="global_rule",
                rule="Global rule.",
                agents=("backend",),
                exclude_projects=("LegacyProject",),
            )
        ],
    )

    excluded = resolve_preferences(
        profile,
        project_name="LegacyProject",
        agent_key="backend",
    )
    included = resolve_preferences(
        profile,
        project_name="NewProject",
        agent_key="backend",
    )

    assert excluded == ()
    assert [item.id for item in included] == ["global_rule"]


def test_observation_becomes_candidate_but_needs_confirmation(tmp_path):
    profile = PreferenceProfile(name="default")

    first = record_preference_observation(
        profile,
        pattern_id="modularize_more",
        rule="Prefer modularization.",
        agents=("architecture",),
        project_name="A",
    )
    assert not first.is_ready_for_confirmation()

    record_preference_observation(
        profile,
        pattern_id="modularize_more",
        rule="Prefer modularization.",
        agents=("backend",),
        project_name="B",
    )
    third = record_preference_observation(
        profile,
        pattern_id="modularize_more",
        rule="Prefer modularization.",
        agents=("backend",),
        project_name="C",
    )

    assert third.is_ready_for_confirmation()
    assert profile.preferences == []

    confirmed = confirm_preference_candidate(
        profile,
        "modularize_more",
        exclude_projects=("Prototype",),
    )

    assert confirmed.id == "modularize_more"
    assert "modularize_more" not in profile.candidates
    assert profile.preferences == [confirmed]

    path = tmp_path / "profile.yaml"
    save_profile(profile, path)
    reloaded = load_profile(path)

    assert reloaded.preferences[0].exclude_projects == ("Prototype",)
