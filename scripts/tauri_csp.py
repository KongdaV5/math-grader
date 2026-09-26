"""Strict checks for the Tauri image policy used by the shipped desktop app."""

LOOPBACK_IMAGE_ORIGIN = "http://127.0.0.1:8765"
EXPECTED_IMAGE_SOURCES = {
    "'self'",
    "asset:",
    "http://asset.localhost",
    "data:",
    "blob:",
    LOOPBACK_IMAGE_ORIGIN,
}


def validate_tauri_csp(policy):
    directives = {}
    for raw_directive in policy.split(";"):
        parts = raw_directive.strip().split()
        if not parts:
            continue
        name, *sources = parts
        if name in directives:
            raise ValueError("Tauri CSP contains duplicate {} directives".format(name))
        directives[name] = sources

    image_sources = directives.get("img-src")
    if image_sources is None:
        raise ValueError("Tauri CSP is missing img-src")
    if set(image_sources) != EXPECTED_IMAGE_SOURCES or len(image_sources) != len(EXPECTED_IMAGE_SOURCES):
        raise ValueError("img-src must use only the existing asset sources and exact loopback image origin")
    if any("*" in source for sources in directives.values() for source in sources):
        raise ValueError("Tauri CSP must not contain wildcard sources")
    if any(source == "http:" for source in image_sources):
        raise ValueError("img-src must not allow the full http scheme")
    return directives


def verify_policy_embedded(policy, executable_bytes):
    validate_tauri_csp(policy)
    if policy.encode("utf-8") not in executable_bytes:
        raise ValueError("Built Tauri executable does not contain the configured production CSP")
