def preflight_status(actual_response_status: int) -> int:
    if actual_response_status >= 400:
        return actual_response_status
    return 204
