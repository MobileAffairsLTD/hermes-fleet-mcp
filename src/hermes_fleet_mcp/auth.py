"""Bearer-token generation and constant-time comparison."""

import secrets


def generate_key(nbytes: int = 32) -> str:
    """Generate a URL-safe bearer token (32 random bytes by default)."""
    return secrets.token_urlsafe(nbytes)


def token_matches(provided: str | None, expected: str) -> bool:
    """Constant-time check. Accepts 'Bearer <token>' or the bare token."""
    if not provided or not expected:
        return False
    value = provided.strip()
    if value.startswith("Bearer "):
        value = value[len("Bearer "):].strip()
    return secrets.compare_digest(value, expected)
