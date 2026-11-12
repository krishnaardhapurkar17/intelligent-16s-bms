"""Deterministic authorization abstraction; it does not implement cryptography."""

from dataclasses import dataclass
from enum import Enum


class AuthorizationState(str, Enum):
    AUTHORIZED = "AUTHORIZED"
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class AuthorizationDecision:
    state: str
    reason: str
    command: str
    principal: str | None


class CommandAuthorizer:
    """Allow configured roles to request commands using a simulation credential."""

    def __init__(self, credentials: dict[str, str], command_roles: dict[str, set[str]]):
        if not credentials or any(not p or not role for p, role in credentials.items()):
            raise ValueError("credentials must map nonempty principals to roles")
        self._credentials = dict(credentials)
        self._command_roles = {name: set(roles) for name, roles in command_roles.items()}

    def authorize(self, command: str, principal: str | None, credential: str | None) -> AuthorizationDecision:
        role = self._credentials.get(principal) if principal is not None else None
        if role is None or credential is None or credential != role:
            return AuthorizationDecision(AuthorizationState.REJECTED.value, "INVALID_CREDENTIAL", command, principal)
        allowed = self._command_roles.get(command)
        if allowed is None:
            return AuthorizationDecision(AuthorizationState.REJECTED.value, "UNKNOWN_COMMAND", command, principal)
        if role not in allowed:
            return AuthorizationDecision(AuthorizationState.REJECTED.value, "ROLE_NOT_AUTHORIZED", command, principal)
        return AuthorizationDecision(AuthorizationState.AUTHORIZED.value, "AUTHORIZED", command, principal)
