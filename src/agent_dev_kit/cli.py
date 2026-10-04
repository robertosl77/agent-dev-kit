import argparse
import sys
from pathlib import Path

from agent_dev_kit.execution import ProviderRuntime
from agent_dev_kit.project_config import load_project_config
from agent_dev_kit.provider_errors import (
    ProviderError,
    ProviderRecoverableError,
)
from agent_dev_kit.provider_registry import build_default_registry
from agent_dev_kit.task_plan import DisabledAgentRequiredError


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
        runtime = ProviderRuntime(
            registry=build_default_registry(),
            project_config=config,
        )

        if args.command == "run":
            return run_conversation(runtime, once=args.once)

        if args.command == "task":
            return run_task(runtime, args.request)

        parser.error(f"Unsupported command: {args.command}")
        return 2
    except (ProviderError, ValueError, FileNotFoundError, RuntimeError) as exc:
        print(f"Agent Dev Kit error: {exc}", file=sys.stderr)
        return 1


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
        return 0

    print(
        f"Agent Dev Kit ready — provider: "
        f"{runtime.current_target.provider}"
    )
    print("Type /exit to finish or /task <request> for a DAG task.")

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
        if message.startswith("/task "):
            request = message[len("/task "):].strip()
            if request:
                run_task(runtime, request)
            continue

        conversation, result = _ask_with_fallback(
            runtime,
            conversation,
            message,
            history,
        )
        history.append(("user", message))
        history.append(("assistant", result.output))
        print(f"{result.active_agent.name}> {result.output}")


def run_task(runtime: ProviderRuntime, request: str) -> int:
    confirm = _interactive_fallback_confirmation

    plan = runtime.run_with_fallback_sync(
        lambda kit: kit.plan_task_sync(request),
        confirm_switch=confirm,
    )

    missing = plan.missing_agents(runtime.kit.agents.keys())
    if missing:
        raise DisabledAgentRequiredError(missing)

    result = runtime.run_with_fallback_sync(
        lambda kit: kit.execute_plan_sync(plan),
        confirm_switch=confirm,
    )

    for node in result.nodes:
        print(
            f"[{node.status}] {node.id} ({node.agent})\n"
            f"{node.output or ''}"
        )

    return 0


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
