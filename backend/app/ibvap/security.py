"""
security.py — write-access control for the HTTP API.

The server listens on 0.0.0.0 so phones and LAN browsers can reach it, which
used to mean anyone on the network could POST /api/shutdown, rewrite camera
URLs, delete fences or swap the model. Mutating API calls now need either:

  * a loopback source address (the desktop command client and the web
    dashboard running on the same machine), or
  * the API token in the ``X-IBVAP-Token`` header.

The token lives in ``security.token_file`` (default ``data/api_token``) and is
generated on first start, so a fresh install is locked down with no manual
step. Read-only GETs, the MJPEG streams and the phone camera intake stay open —
those are needed for pairing and viewing.

Loopback trust is only sound because server.py trusts proxy headers from
127.0.0.1 alone; with ``forwarded_allow_ips="*"`` any LAN client could claim to
be localhost via ``X-Forwarded-For``.
"""
from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import logging
import secrets
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

logger = logging.getLogger("ibvap.security")

TOKEN_HEADER = "x-ibvap-token"
_MUTATING = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def load_or_create_token(path: str | Path) -> str:
    p = Path(path)
    try:
        if p.is_file():
            tok = p.read_text("utf-8").strip()
            if len(tok) >= 24:
                return tok
        p.parent.mkdir(parents=True, exist_ok=True)
        tok = secrets.token_urlsafe(32)
        p.write_text(tok + "\n", encoding="utf-8")
        logger.info("Generated API write token at %s", p)
        return tok
    except OSError as e:
        # No writable data dir: fall back to an in-memory token. Remote writes
        # are then impossible until the disk is fixed, which is the safe side.
        logger.error("Cannot persist API token (%s) — remote writes disabled", e)
        return secrets.token_urlsafe(32)


def is_loopback(host: str | None) -> bool:
    if not host:
        return False
    try:
        return ipaddress.ip_address(host.split("%")[0]).is_loopback
    except ValueError:
        return host == "localhost"


def needs_token(method: str, path: str) -> bool:
    return method.upper() in _MUTATING and path.startswith("/api/")


# ── listener exposure ────────────────────────────────────────────────────────
# IBVAP runs as one local product: the API, dashboard and streams listen on
# loopback only. The single deliberate exception is phone camera intake during
# testing/demos — network.lan_phone_intake opens the HTTPS listener to the LAN,
# and ListenerGuard then serves nothing on it except the phone page and its
# frame WebSocket.
PHONE_INTAKE_PREFIXES = ("/cam/", "/camera/", "/ws/camera/")


def lan_listener_allows(path: str) -> bool:
    return path.startswith(PHONE_INTAKE_PREFIXES)


class ListenerGuard:
    """ASGI middleware: requests arriving on ``lan_port`` may only reach the
    phone intake routes. A plain HTTP middleware would not see WebSockets."""

    def __init__(self, app, lan_port: int | None = None) -> None:
        self.app = app
        self.lan_port = lan_port

    async def __call__(self, scope, receive, send):
        if (self.lan_port is not None
                and scope.get("type") in ("http", "websocket")
                and (scope.get("server") or (None, None))[1] == self.lan_port
                and not lan_listener_allows(scope.get("path", ""))):
            if scope["type"] == "http":
                body = b'{"error":"not available on the camera intake listener"}'
                await send({"type": "http.response.start", "status": 404,
                            "headers": [(b"content-type", b"application/json"),
                                        (b"content-length", str(len(body)).encode())]})
                await send({"type": "http.response.body", "body": body})
            else:
                await send({"type": "websocket.close", "code": 1008})
            return
        await self.app(scope, receive, send)


# ── Scoped API Clients & Role-Based Access Control ─────────────────────────
VALID_SCOPES: Set[str] = {"read", "ack", "admin"}

_SCOPE_HIERARCHY = {
    "admin": {"admin", "ack", "read"},
    "ack": {"ack", "read"},
    "read": {"read"},
}


def _hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.strip().encode("utf-8")).hexdigest()


@dataclass
class ApiClient:
    client_id: str
    name: str
    token_hash: str
    scopes: List[str]
    created_at_utc: str
    revoked: bool = False

    def has_scope(self, required_scope: str) -> bool:
        if self.revoked:
            return False
        for s in self.scopes:
            if required_scope in _SCOPE_HIERARCHY.get(s, set()):
                return True
        return False

    def to_dict(self) -> Dict:
        return asdict(self)


class ClientRegistry:
    """
    Manages named, revocable API clients with granular scopes (read, ack, admin).
    Stored in data/api_clients.json.
    """

    def __init__(self, path: str | Path = "data/api_clients.json") -> None:
        self.path = Path(path)
        self.clients: Dict[str, ApiClient] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.is_file():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            for item in data.get("clients", []):
                client = ApiClient(**item)
                self.clients[client.client_id] = client
        except Exception as e:
            logger.warning("Failed to load api_clients.json (%s) — starting empty", e)

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"clients": [c.to_dict() for c in self.clients.values()]}
        self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def register_client(self, name: str, scopes: List[str]) -> Tuple[str, ApiClient]:
        """
        Register a new client. Returns (raw_token, ApiClient).
        The raw token is only returned once upon creation.
        """
        raw_token = "ibvap_" + secrets.token_urlsafe(28)
        token_hash = _hash_token(raw_token)
        cid = f"cli_{secrets.token_hex(6)}"
        clean_scopes = [s for s in scopes if s in VALID_SCOPES] or ["read"]
        ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        client = ApiClient(
            client_id=cid,
            name=name,
            token_hash=token_hash,
            scopes=clean_scopes,
            created_at_utc=ts,
            revoked=False,
        )
        self.clients[cid] = client
        self._save()
        logger.info("Registered API client %s (id: %s) with scopes %s", name, cid, clean_scopes)
        return raw_token, client

    def revoke_client(self, client_id: str) -> bool:
        if client_id in self.clients:
            self.clients[client_id].revoked = True
            self._save()
            logger.info("Revoked API client %s", client_id)
            return True
        return False

    def verify_token(
        self,
        raw_token: str | None,
        required_scope: str = "read",
        master_token: Optional[str] = None,
    ) -> Tuple[bool, Optional[ApiClient]]:
        """
        Verifies a token against master token or registered scoped clients.
        """
        if not raw_token or not raw_token.strip():
            return False, None

        tok = raw_token.strip()

        # Check master admin token first (backward compatibility)
        if master_token and hmac.compare_digest(tok, master_token.strip()):
            master_client = ApiClient(
                client_id="master_admin",
                name="Master Admin",
                token_hash=_hash_token(master_token),
                scopes=["admin"],
                created_at_utc="",
                revoked=False,
            )
            return True, master_client

        # Check registered clients by hashed token comparison
        candidate_hash = _hash_token(tok)
        for client in self.clients.values():
            if hmac.compare_digest(client.token_hash, candidate_hash):
                if not client.revoked and client.has_scope(required_scope):
                    return True, client
                return False, client

        return False, None


def is_authorized(method: str, path: str, client_host: str | None,
                  header_token: str | None, token: str,
                  allow_loopback: bool = True,
                  require_token: bool = True,
                  registry: Optional[ClientRegistry] = None) -> bool:
    if not require_token or not needs_token(method, path):
        return True
    if allow_loopback and is_loopback(client_host):
        return True
    if not header_token:
        return False

    # Required scope is 'ack' for /ack routes, 'admin' for other mutating routes
    req_scope = "ack" if path.endswith("/ack") else "admin"

    if registry is not None:
        ok, _ = registry.verify_token(header_token, required_scope=req_scope, master_token=token)
        return ok

    if not token:
        return False
    return hmac.compare_digest(header_token.strip(), token)
