INSTALLED_DISTRIBUTIONS = {"click-issue-test": "0.1.0"}


def detected_version(callback_module: str, package_name: str | None = None) -> str:
    candidate = package_name or callback_module.split(".", 1)[0]
    try:
        return INSTALLED_DISTRIBUTIONS[candidate]
    except KeyError as exc:
        raise LookupError(f"distribution {candidate!r} was not found") from exc
