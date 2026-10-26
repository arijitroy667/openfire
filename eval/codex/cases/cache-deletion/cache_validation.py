def is_not_modified(file_exists: bool, request_time: int, last_modified: int) -> bool:
    return request_time >= last_modified
