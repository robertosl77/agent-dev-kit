import argparse
import getpass
import re
import sys
from pathlib import Path

from agent_dev_kit.console_modes import (
    ConsoleIO,
    run_act,
    run_plan_only,
    run_propose,
)
from agent_dev_kit.console_setup import ConsoleSetup
from agent_dev_kit.git_actions import GitActionError
from agent_dev_kit.git_policy import GitPolicyViolation
from agent_dev_kit.usage import format_usage_line
from agent_dev_kit.workspace_tools import Workspace
from agent_dev_kit.execution import ProviderRuntime
from agent_dev_kit.project_config import load_project_config
from agent_dev_kit.provider_errors import (
    ProviderError,
    ProviderRecoverableError,
)
from agent_dev_kit.provider_registry import build_default_registry
from agent_dev_kit.task_plan import TaskPlanError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agent-dev-kit",
        description="Run Agent Dev Kit from a consuming project.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    run = subparsers.add_parser(
        "run",
        help="Open an interactive conversation.",
    )
    run.add_argument(
        "project_root",
        nargs="?",
        default=".",
        help="Consuming project root (default: current directory).",
    )
    run.add_argument(
        "--once",
        help="Send one message and exit.",
    )
    _add_provider_arguments(run)

    task = subparsers.add_parser(
        "task",
        help="Plan and execute one multi-agent task.",
    )
    task.add_argument(
        "project_root",
        help="Consuming project root.",
    )
    task.add_argument(
        "request",
        help="Task request to plan and execute.",
    )
    task.add_argument(
        "--mode",
        choices=("plan", "propose", "act"),
        default="propose",
        help=(
            "plan: only the plan · propose: plan + proposals (default) · "
            "act: agents change files on a local task branch."
        ),
    )
    _add_provider_arguments(task)

    graphs = subparsers.add_parser(
        "graphs",
        help="List the agent graphs recorded for each use (M-068).",
    )
    graphs.add_argument("project_root", nargs="?", default=".")
    graphs.add_argument("--limit", type=int, default=20)

    candidates = subparsers.add_parser(
        "candidates",
        help="Analyze recorded graphs and show routing improvement candidates.",
    )
    candidates.add_argument("project_root", nargs="?", default=".")

    mcp = subparsers.add_parser(
        "mcp",
        help="Expose Agent Dev Kit as a standard MCP server.",
    )
    mcp.add_argument(
        "project_root",
        nargs="?",
        default=".",
        help="Consuming project root (default: current directory).",
    )
    mcp.add_argument(
        "--transport",
        choices=("stdio", "streamable-http"),
        default="stdio",
        help="MCP transport (default: stdio).",
    )
    mcp.add_argument(
        "--host",
        default="127.0.0.1",
        help="HTTP bind host. Non-loopback hosts are rejected.",
    )
    mcp.add_argument(
        "--port",
        type=int,
        default=8000,
        help="HTTP port for streamable-http (default: 8000).",
    )

    return parser


def _add_provider_arguments(command: argparse.ArgumentParser) -> None:
    command.add_argument(
        "--provider",
        help=(
            "Provider to use (anthropic, gemini, openai). "
            "Without it, a menu asks every time."
        ),
    )
    command.add_argument(
        "--model",
        help="Model to use. Without it, the provider's live model list is shown.",
    )


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "mcp":
            from agent_dev_kit.mcp_server import run_mcp_server

            run_mcp_server(
                Path(args.project_root),
                transport=args.transport,
                host=args.host,
                port=args.port,
            )
            return 0

        config = load_project_config(Path(args.project_root))
        if args.command in {"graphs", "candidates"}:
            return run_graph_report(config, args)

        selection = ConsoleSetup().run(
            config,
            provider=args.provider,
            model=args.model,
        )
        io = ConsoleIO()
        workspace = Workspace(
            root=Path(args.project_root),
            config=selection.config.workspace,
            approve_command=lambda command: io.confirm(
                f"¿Ejecutar el comando '{command}'?"
            ),
            ask_github_token=lambda reason: _ask_github_token(reason),
        )
        runtime = ProviderRuntime(
            registry=build_default_registry(selection.credentials),
            project_config=selection.config,
            workspace=workspace,
            mode="propose",
        )
        print(
            f"Proveedor: {selection.provider} · modelo: {selection.model}",
            file=sys.stderr,
        )

        if args.command == "run":
            return run_conversation(runtime, once=args.once)

        if args.command == "task":
            return run_task(runtime, args.request, mode=args.mode)

        parser.error(f"Unsupported command: {args.command}")
        return 2
    except KeyboardInterrupt:
        print(file=sys.stderr)
        return 130
    except (
        ProviderError,
        ValueError,
        FileNotFoundError,
        RuntimeError,
        GitActionError,
    ) as exc:
        print(f"Agent Dev Kit error: {exc}", file=sys.stderr)
        cause = _error_cause(exc)
        if cause:
            print(f"  causa: {cause}", file=sys.stderr)
        return 1


_SECRET_PATTERN = re.compile(
    r"(sk-[A-Za-z0-9_\-]{4})[A-Za-z0-9_\-]+|(AIza[A-Za-z0-9_\-]{2})[A-Za-z0-9_\-]+"
)


def _error_cause(exc: Exception) -> str | None:
    """Short, sanitized description of the provider's original error."""

    original = getattr(exc, "original", None)
    if original is None:
        return None
    text = " ".join(str(original).split())[:300]
    return _SECRET_PATTERN.sub(lambda m: (m.group(1) or m.group(2)) + "…", text)


def run_conversation(
    runtime: ProviderRuntime,
    *,
    once: str | None = None,
) -> int:
    conversation = runtime.kit.conversation()
    history: list[tuple[str, str]] = []

    if once is not None:
        _, result = _ask_with_fallback(
            runtime,
            conversation,
            once,
            history,
        )
        print(result.output)
        print(
            format_usage_line(
                [("respuesta", result.usage)],
                runtime.project_config.pricing,
            ),
            file=sys.stderr,
        )
        return 0

    print(
        f"Agent Dev Kit listo — proveedor: "
        f"{runtime.current_target.provider}"
    )
    print("Escribí /help para ver /plan, /task y /do. /exit para salir.")

    while True:
        try:
            message = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0

        if not message:
            continue
        if message in {"/exit", "/quit"}:
            return 0
        command, _, request = message.partition(" ")
        if command in COMMAND_MODES:
            request = request.strip()
            if not request:
                request = _read_multiline_request()
                if not request:
                    print(f"Pedido vacío para {command}.")
                    continue
            try:
                run_task(runtime, request, mode=COMMAND_MODES[command])
            except (GitActionError, GitPolicyViolation, TaskPlanError, ProviderError) as exc:
                _report_in_session(f"No se pudo completar {command}", exc)
            continue
        if message == "/help":
            print(HELP_TEXT)
            continue

        try:
            conversation, result = _ask_with_fallback(
                runtime,
                conversation,
                message,
                history,
            )
        except ProviderError as exc:
            _report_in_session("No se pudo responder", exc)
            continue
        history.append(("user", message))
        history.append(("assistant", result.output))
        print(f"{result.active_agent.name}> {result.output}")
        print(
            format_usage_line(
                [("respuesta", result.usage)],
                runtime.project_config.pricing,
            )
        )


COMMAND_MODES = {"/plan": "plan", "/task": "propose", "/do": "act"}

HELP_TEXT = """Comandos:
  /plan <pedido>   solo el plan (qué agentes y en qué orden); no ejecuta nada
  /task <pedido>   plan + propuesta de cada agente (leen el repo, no lo modifican)
  /do   <pedido>   plan → tu OK → rama local desde develop → cambian archivos y
                   corren tests → diff y consumo → tu OK → commit local (sin push)
  /plan, /task o /do sin <pedido> abren entrada multilínea; terminá con /end
  /help            esta ayuda
  /exit            salir
Cualquier otro texto es una conversación (los agentes pueden leer el repo)."""


def _read_multiline_request() -> str:
    print("Pegá el pedido. Terminá con una línea que contenga solo /end.")
    lines: list[str] = []
    while True:
        try:
            line = input("...> ")
        except EOFError:
            break
        except KeyboardInterrupt:
            print()
            return ""
        if line.strip() == "/end":
            break
        lines.append(line)
    return "\n".join(lines).strip()


def run_task(runtime: ProviderRuntime, request: str, *, mode: str = "propose") -> int:
    io = ConsoleIO()
    confirm = _interactive_fallback_confirmation
    if mode == "plan":
        run_plan_only(runtime, request, io=io, confirm_switch=confirm)
        return 0
    if mode == "act":
        outcome = run_act(runtime, request, io=io, confirm_switch=confirm)
        return 0 if outcome.status in {"committed", "not_committed", "plan_rejected", "no_changes"} else 1
    run_propose(runtime, request, io=io, confirm_switch=confirm)
    return 0


def _report_in_session(prefix: str, exc: Exception) -> None:
    """Show the error and keep the session open (the key stays in memory)."""

    print(f"{prefix}: {exc}")
    cause = _error_cause(exc)
    if cause:
        print(f"  causa: {cause}")
    text = f"{exc} {cause or ''}".lower()
    if "404" in text or "not_found" in text or "not found" in text:
        print(
            "  El modelo elegido no está disponible para tu cuenta. Salí con /exit "
            "y volvé a entrar eligiendo otro modelo de la lista."
        )


def run_graph_report(config, args) -> int:
    from agent_dev_kit.graph_analysis import (
        analysis_report,
        format_graph_rows,
        graph_rows,
    )
    from agent_dev_kit.orchestration import (
        OrchestrationTraceStore,
        resolve_project_trace_path,
    )

    path = resolve_project_trace_path(
        config.project_root,
        config.orchestration.trace_path,
    )
    traces = OrchestrationTraceStore(path).read()
    if args.command == "graphs":
        rows = graph_rows(traces)[-max(args.limit, 1):]
        for line in format_graph_rows(rows):
            print(line)
        return 0
    for line in analysis_report(
        traces,
        threshold=config.orchestration.improvement_candidate_threshold,
    ):
        print(line)
    return 0


def _ask_github_token(reason: str) -> str | None:
    print(reason, file=sys.stderr)
    from agent_dev_kit.console_setup import clean_key

    token, _ = clean_key(getpass.getpass(
        "Token de GitHub de solo lectura (no se muestra ni se guarda; Enter para omitir): "
    ))
    return token or None


def _ask_with_fallback(
    runtime: ProviderRuntime,
    conversation,
    message: str,
    history: list[tuple[str, str]],
):
    prompt = _conversation_prompt(history, message)

    while True:
        try:
            result = conversation.ask_sync(prompt)
            return conversation, result
        except ProviderRecoverableError as exc:
            active_key = _agent_key_for_name(
                runtime.kit,
                conversation.active_agent.name,
            )
            new_kit = runtime.switch_after_error(
                exc,
                confirm_switch=_interactive_fallback_confirmation,
            )
            conversation = new_kit.conversation(
                start_agent=active_key,
            )
            prompt = _conversation_prompt(history, message)


def _conversation_prompt(
    history: list[tuple[str, str]],
    message: str,
) -> str:
    if not history:
        return message

    transcript = "\n".join(
        f"{role}: {content}"
        for role, content in history
    )
    return (
        "Continue the same conversation using this provider-neutral "
        "transcript as context.\n\n"
        f"{transcript}\n"
        f"user: {message}\n"
        "Respond to the latest user message."
    )


def _agent_key_for_name(kit, name: str) -> str:
    for key, handle in kit.agents.items():
        if handle.name == name:
            return key
    raise ValueError(f"Active agent '{name}' is not enabled.")


def _interactive_fallback_confirmation(
    current,
    next_target,
    error,
) -> bool:
    print(
        f"Provider '{current.provider}' cannot continue: {error}",
        file=sys.stderr,
    )
    answer = input(
        f"Switch to '{next_target.provider}'? [y/N] "
    ).strip().lower()
    return answer in {"y", "yes", "s", "si", "sí"}


if __name__ == "__main__":
    raise SystemExit(main())
