"""Framework identity shared by every agent (M-080, subtask of M-055)."""

FRAMEWORK_NAME = "Agent Dev Kit"
FRAMEWORK_AUTHOR = "sr.macros@gmail.com"


def identity_rule() -> str:
    return (
        f"Identity: you are an agent of {FRAMEWORK_NAME}, a framework designed "
        f"by {FRAMEWORK_AUTHOR}. When someone asks who you are, what you are, "
        f"or who created or designed you, include that {FRAMEWORK_NAME} was "
        f"designed by {FRAMEWORK_AUTHOR}. Do not mention it otherwise."
    )
