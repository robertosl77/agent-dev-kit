from agent_dev_kit.cli import build_parser


def test_cli_parses_interactive_run_command():
    args = build_parser().parse_args(["run", "."])

    assert args.command == "run"
    assert args.project_root == "."
    assert args.once is None


def test_cli_parses_single_message():
    args = build_parser().parse_args(
        ["run", "/tmp/project", "--once", "hello"]
    )

    assert args.once == "hello"


def test_cli_parses_task_command():
    args = build_parser().parse_args(
        ["task", "/tmp/project", "Fix report"]
    )

    assert args.command == "task"
    assert args.request == "Fix report"


def test_cli_parses_mcp_stdio_command():
    args = build_parser().parse_args(
        ["mcp", "/tmp/project"]
    )

    assert args.command == "mcp"
    assert args.project_root == "/tmp/project"
    assert args.transport == "stdio"


def test_cli_parses_mcp_streamable_http_command():
    args = build_parser().parse_args(
        [
            "mcp",
            ".",
            "--transport",
            "streamable-http",
            "--host",
            "127.0.0.1",
            "--port",
            "9000",
        ]
    )

    assert args.transport == "streamable-http"
    assert args.host == "127.0.0.1"
    assert args.port == 9000


def test_session_survives_provider_errors_and_hints_model_change(monkeypatch, capsys):
    from agent_dev_kit import cli
    from agent_dev_kit.provider_errors import ProviderExecutionError

    class FakeRuntime:
        project_config = None

        def __init__(self):
            self.kit = type("Kit", (), {"conversation": lambda self: object()})()
            self.current_target = type("T", (), {"provider": "gemini"})()

    error = ProviderExecutionError(
        "Provider 'gemini' failed: 404 NOT_FOUND model is no longer available",
        provider="gemini",
    )
    monkeypatch.setattr(cli, "run_task", lambda *a, **k: (_ for _ in ()).throw(error))
    answers = iter(["/do T-1 algo", "/exit"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))

    assert cli.run_conversation(FakeRuntime()) == 0
    out = capsys.readouterr().out
    assert "No se pudo completar /do" in out
    assert "elegí" not in out or "otro modelo" in out
    assert "otro modelo" in out
