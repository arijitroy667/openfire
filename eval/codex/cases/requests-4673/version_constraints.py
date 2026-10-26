SETUP_MAX_URLLIB3 = (1, 23)
RUNTIME_MAX_URLLIB3 = (1, 22)


def runtime_accepts(version: tuple[int, ...]) -> bool:
    return (1, 9) <= version <= RUNTIME_MAX_URLLIB3
