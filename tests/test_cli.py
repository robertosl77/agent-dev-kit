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


class _FakeRuntime:
    project_config = None
    workspace = None

    def __init__(self, provider="anthropic"):
        self.kit = type("Kit", (), {"conversation": lambda self: object()})()
        self.current_target = type("T", (), {"provider": provider})()


def test_session_survives_provider_errors_and_hints_model_change(monkeypatch, capsys, tmp_path):
    from agent_dev_kit import cli
    from agent_dev_kit.provider_errors import ProviderExecutionError

    monkeypatch.chdir(tmp_path)
    error = ProviderExecutionError(
        "Provider 'gemini' failed: 404 NOT_FOUND model is no longer available",
        provider="gemini",
    )
    monkeypatch.setattr(cli, "cmd_plan", lambda *a, **k: (_ for _ in ()).throw(error))
    answers = iter(["/plan T-1 algo", "/exit"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))

    assert cli.run_conversation(_FakeRuntime("gemini")) == 0
    out = capsys.readouterr().out
    assert "No se pudo completar /plan" in out
    assert "otro modelo" in out


def test_multiline_input_is_accumulated_as_one_block(monkeypatch, capsys, tmp_path):
    from agent_dev_kit import cli

    monkeypatch.chdir(tmp_path)
    seen = []
    real = cli.cmd_input

    def spy(session, argument, *, io):
        real(session, argument, io=io)
        seen.append(list(session.context))

    monkeypatch.setattr(cli, "cmd_input", spy)
    answers = iter(["/input", "primera línea", "segunda línea", "/end", "/exit"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))

    assert cli.run_conversation(_FakeRuntime()) == 0
    assert seen == [["primera línea\nsegunda línea"]]
    out = capsys.readouterr().out
    assert "Escribí o pegá el pedido." in out
    assert "Leído" in out


def test_removed_task_command_is_unknown_and_shows_help(monkeypatch, capsys, tmp_path):
    from agent_dev_kit import cli
    from agent_dev_kit.commands import COMMAND_NAMES

    monkeypatch.chdir(tmp_path)
    answers = iter(["/task algo", "/do", "/exit"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))

    assert cli.run_conversation(_FakeRuntime()) == 0
    out = capsys.readouterr().out
    assert "Comando desconocido: /task. No se ejecutó nada." in out
    for name in COMMAND_NAMES:
        assert name in out
    assert "No hay plan. Primero /plan y aprobalo." in out
