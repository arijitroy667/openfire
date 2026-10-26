MAX_CONNECTIONS = 1


def can_serve_workers(worker_count: int) -> bool:
    return worker_count <= MAX_CONNECTIONS
