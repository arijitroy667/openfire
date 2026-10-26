def resolve(name: str, process_env: dict[str, str], dotenv: dict[str, str], defaults: dict[str, str]):
    return process_env.get(name) or dotenv.get(name) or defaults.get(name)
