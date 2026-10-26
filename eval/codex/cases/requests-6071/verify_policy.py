from __future__ import annotations


DEFAULT_CA_BUNDLE = "system-default"


def resolve_ca_bundle(environ: dict[str, str]) -> str | bool:
    """Return the CA bundle setting selected for an HTTPS request."""
    if "CURL_CA_BUNDLE" in environ:
        value = environ["CURL_CA_BUNDLE"]
        return value if value else False
    return DEFAULT_CA_BUNDLE
