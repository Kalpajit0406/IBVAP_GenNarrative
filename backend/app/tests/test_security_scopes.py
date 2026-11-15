"""
test_security_scopes.py — Granular API scopes and revocable client registry tests.

    python tests/test_security_scopes.py
    pytest  tests/test_security_scopes.py
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ibvap.security import ClientRegistry, is_authorized  # noqa: E402

CASES = []


def case(name):
    def deco(fn):
        CASES.append((name, fn))
        return fn
    return deco


@case("client registration creates hashed token and saves record")
def _():
    tmp_path = Path(tempfile.mkdtemp()) / "api_clients.json"
    reg = ClientRegistry(tmp_path)
    raw_token, client = reg.register_client("C2 Command Server", ["admin"])

    assert raw_token.startswith("ibvap_")
    assert client.name == "C2 Command Server"
    assert client.scopes == ["admin"]
    assert not client.revoked
    assert tmp_path.is_file()

    # Reopening registry loads persisted client
    reg2 = ClientRegistry(tmp_path)
    assert client.client_id in reg2.clients


@case("master admin token satisfies all scopes")
def _():
    reg = ClientRegistry()
    master = "master_secret_key_1234567890"

    ok_admin, _ = reg.verify_token(master, required_scope="admin", master_token=master)
    ok_ack, _ = reg.verify_token(master, required_scope="ack", master_token=master)
    ok_read, _ = reg.verify_token(master, required_scope="read", master_token=master)

    assert ok_admin and ok_ack and ok_read


@case("scope hierarchy: ack client can ack and read but cannot admin")
def _():
    tmp_path = Path(tempfile.mkdtemp()) / "api_clients.json"
    reg = ClientRegistry(tmp_path)
    tok_ack, _ = reg.register_client("Field Dispatch Radio", ["ack"])
    tok_read, _ = reg.register_client("Monitoring Dashboard", ["read"])

    # ACK token
    ok_ack_to_ack, _ = reg.verify_token(tok_ack, "ack")
    ok_ack_to_read, _ = reg.verify_token(tok_ack, "read")
    ok_ack_to_admin, _ = reg.verify_token(tok_ack, "admin")

    assert ok_ack_to_ack
    assert ok_ack_to_read
    assert not ok_ack_to_admin

    # READ token
    ok_read_to_read, _ = reg.verify_token(tok_read, "read")
    ok_read_to_ack, _ = reg.verify_token(tok_read, "ack")
    assert ok_read_to_read
    assert not ok_read_to_ack


@case("revoking client immediately blocks authentication")
def _():
    tmp_path = Path(tempfile.mkdtemp()) / "api_clients.json"
    reg = ClientRegistry(tmp_path)
    tok, client = reg.register_client("Temporary Auditor", ["read"])

    ok_before, _ = reg.verify_token(tok, "read")
    assert ok_before

    assert reg.revoke_client(client.client_id)

    ok_after, client_revoked = reg.verify_token(tok, "read")
    assert not ok_after
    assert client_revoked.revoked


@case("is_authorized validates mutating route against client registry")
def _():
    tmp_path = Path(tempfile.mkdtemp()) / "api_clients.json"
    reg = ClientRegistry(tmp_path)
    tok_ack, _ = reg.register_client("Alert Acknowledger", ["ack"])

    # /api/events/{id}/ack requires 'ack' scope
    assert is_authorized("POST", "/api/events/e1/ack", "192.168.1.50", tok_ack, "master",
                         allow_loopback=False, registry=reg)

    # /api/shutdown requires 'admin' scope -> ack token refused
    assert not is_authorized("POST", "/api/shutdown", "192.168.1.50", tok_ack, "master",
                             allow_loopback=False, registry=reg)


def run():
    failed = 0
    for name, fn in CASES:
        try:
            fn()
            print(f"  PASS  {name}")
        except Exception as e:
            print(f"  FAIL  {name}: {e}")
            failed += 1
    print(f"\n{len(CASES) - failed}/{len(CASES)} passed")
    if failed:
        sys.exit(1)


def test_all():
    for _, fn in CASES:
        fn()


if __name__ == "__main__":
    run()
