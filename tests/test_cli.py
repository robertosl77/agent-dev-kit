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
