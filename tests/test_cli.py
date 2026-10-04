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
