"""Verifies Supabase access tokens against the project's public signing keys."""
from functools import lru_cache
from uuid import UUID

import jwt

ALLOWED_ALGORITHMS = ["ES256", "RS256"]  # asymmetric only, so "alg: none" and shared-secret tokens are refused
AUDIENCE = "authenticated"
REQUIRED_ROLE = "authenticated"
KEY_CACHE_SECONDS = 600  # Supabase asks apps not to keep signing keys for longer than this
KEY_FETCH_TIMEOUT_SECONDS = 5


class InvalidToken(Exception):
    """Deliberately carries no detail: callers only need to refuse the request."""


@lru_cache(maxsize=4)
def _key_client(supabase_url: str) -> jwt.PyJWKClient:
    return jwt.PyJWKClient(
        f"{supabase_url}/auth/v1/.well-known/jwks.json", lifespan=KEY_CACHE_SECONDS, timeout=KEY_FETCH_TIMEOUT_SECONDS
    )


def verify_token(token: str, supabase_url: str) -> str:
    """Return the user ID from a valid token, or raise InvalidToken."""
    try:
        key = _key_client(supabase_url).get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            key.key,
            algorithms=ALLOWED_ALGORITHMS,
            audience=AUDIENCE,
            issuer=f"{supabase_url}/auth/v1",
            options={"require": ["exp", "sub", "aud", "iss"]},
        )
        if claims.get("role") != REQUIRED_ROLE:
            raise InvalidToken
        return str(UUID(claims["sub"]))
    except (jwt.PyJWTError, ValueError, TypeError, KeyError, AttributeError) as e:
        raise InvalidToken from e
