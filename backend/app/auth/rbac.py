"""SQL Server-backed role and table-permission lookup for authenticated users."""

import logging
from typing import Set

from fastapi import Depends, HTTPException, status
from pydantic import BaseModel

from app.auth.auth0 import AuthenticatedUser, get_current_user
from app.db.connection import get_db_connection


logger = logging.getLogger(__name__)


class AuthorizationContext(BaseModel):
    """Trusted authorization data resolved from SQL Server for one Auth0 subject."""

    user_id: int
    auth_subject: str
    email: str
    role: str
    allowed_tables: Set[str]


def _forbidden() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="The authenticated user is not authorized for this application.",
    )


def load_authorization_context(auth_subject: str) -> AuthorizationContext:
    """Load an active application's role and table permissions by Auth0 subject."""
    connection = get_db_connection()
    cursor = connection.cursor()
    try:
        cursor.execute(
            """
            SELECT
                u.UserId,
                u.AuthSubject,
                u.Email,
                r.RoleName
            FROM rbac.AppUsers u
            JOIN rbac.UserRoles ur
                ON ur.UserId = u.UserId
            JOIN rbac.Roles r
                ON r.RoleId = ur.RoleId
            WHERE u.AuthSubject = ?
              AND u.IsActive = 1;
            """,
            (auth_subject,),
        )
        user_rows = cursor.fetchall()
        if not user_rows:
            raise _forbidden()

        user_row = user_rows[0]
        cursor.execute(
            """
            SELECT
                rtp.SchemaName,
                rtp.TableName
            FROM rbac.AppUsers u
            JOIN rbac.UserRoles ur
                ON ur.UserId = u.UserId
            JOIN rbac.RoleTablePermissions rtp
                ON rtp.RoleId = ur.RoleId
            WHERE u.AuthSubject = ?
              AND u.IsActive = 1
            ORDER BY
                rtp.SchemaName,
                rtp.TableName;
            """,
            (auth_subject,),
        )
        allowed_tables = {f"{row.SchemaName}.{row.TableName}" for row in cursor.fetchall()}
    finally:
        connection.close()

    context = AuthorizationContext(
        user_id=int(user_row.UserId),
        auth_subject=str(user_row.AuthSubject),
        email=str(user_row.Email),
        role=str(user_row.RoleName),
        allowed_tables=allowed_tables,
    )
    logger.info(
        "Authorization context loaded: user_id=%s role=%s allowed_table_count=%s",
        context.user_id,
        context.role,
        len(context.allowed_tables),
    )
    return context


def get_authorization_context(
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> AuthorizationContext:
    """FastAPI dependency that resolves SQL-backed authorization after JWT validation."""
    return load_authorization_context(current_user.sub)
