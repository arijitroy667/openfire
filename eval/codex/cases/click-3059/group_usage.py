def group_usage(name: str, *, has_commands: bool, invoke_without_command: bool) -> str:
    command = "COMMAND" if has_commands else ""
    if command:
        return f"Usage: {name} [OPTIONS] {command} [ARGS]..."
    return f"Usage: {name} [OPTIONS]"
