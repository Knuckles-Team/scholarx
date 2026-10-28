"""Bind paper search to the MCP server's verified caller identity."""

from __future__ import annotations

from typing import Any, Protocol


class _TenantScoped(Protocol):
    @property
    def tenant(self) -> str: ...


from fastmcp.server.dependencies import get_access_token


class VerifiedPaperAccess:
    """Require a host-selected verified tenant claim and scopes.

    The FastMCP authentication provider verifies tokens before dispatch. The
    host chooses the claim and scopes; this class does not mint an authority.
    """

    def __init__(self, *, tenant_claim: str, required_scopes: frozenset[str]) -> None:
        if not tenant_claim.strip() or tenant_claim != tenant_claim.strip():
            raise ValueError("a tenant claim is required")
        if not required_scopes or any(not scope or scope != scope.strip() for scope in required_scopes):
            raise ValueError("at least one nonblank scope is required")
        self._tenant_claim = tenant_claim
        self._required_scopes = required_scopes

    async def __call__(self, query: _TenantScoped, ctx: Any) -> bool:
        try:
            token = get_access_token()
            if token is None or not str(ctx.session_id or "").strip():
                return False
            claims = token.claims
            if not isinstance(claims, dict):
                return False
            if not str(claims.get("sub") or token.client_id or "").strip():
                return False
            if claims.get(self._tenant_claim) != query.tenant:
                return False
            scopes = {scope for scope in (token.scopes or ()) if isinstance(scope, str)}
            claimed = claims.get("scope")
            if isinstance(claimed, str):
                scopes.update(claimed.split())
            return self._required_scopes <= scopes
        except (AttributeError, RuntimeError, TypeError):
            return False
