DEFAULT_BUSY_TIMEOUT_SECONDS = 0


def connection_options() -> dict[str, float]:
    return {"timeout": DEFAULT_BUSY_TIMEOUT_SECONDS}
