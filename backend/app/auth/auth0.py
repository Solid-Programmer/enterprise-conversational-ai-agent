"""Auth0 RS256 access-token validation for FastAPI dependencies."""

import logging
from functools import lru_cache

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import InvalidTokenError, PyJWKClient, PyJWKClientError
from pydantic import BaseModel

from app.core.config import settings


logger = logging.getLogger(__name__)
_bearer_scheme = HTTPBearer(auto_error=False)


class AuthenticatedUser(BaseModel):
    """Authenticated identity exposed to endpoint handlers."""

    sub: str


@lru_cache(maxsize=1)
def _jwks_client() -> PyJWKClient:
    """Create one cached client that retrieves Auth0's public signing keys."""
    return PyJWKClient(
        f"https://{settings.AUTH0_DOMAIN}/.well-known/jwks.json",
        cache_keys=True,
    )


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing access token.",
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> AuthenticatedUser:
    """Validate an Auth0 RS256 access token and return its subject claim."""
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _unauthorized()

    token = credentials.credentials
    try:
        header = jwt.get_unverified_header(token)
        if header.get("alg") != "RS256":
            raise InvalidTokenError("Unexpected signing algorithm")
        signing_key = _jwks_client().get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=settings.AUTH0_AUDIENCE,
            issuer=f"https://{settings.AUTH0_DOMAIN}/",
        )
        subject = claims.get("sub")
        if not isinstance(subject, str) or not subject:
            raise InvalidTokenError("Token subject is missing")
    except (InvalidTokenError, PyJWKClientError, ValueError) as exc:
        logger.info("Auth0 access-token validation failed: %s", exc)
        raise _unauthorized() from exc

    logger.info("Authenticated Auth0 subject: %s", subject)
    return AuthenticatedUser(sub=subject)
