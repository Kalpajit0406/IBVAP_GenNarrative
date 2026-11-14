"""
test_blockchain_export.py — OpenTimestamps and EVM testnet proof exporter tests.

    python tests/test_blockchain_export.py
    pytest  tests/test_blockchain_export.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ibvap.blockchain_export import (  # noqa: E402
    EVM_ANCHOR_SELECTOR,
    create_blockchain_attestation,
    format_evm_calldata,
)

CASES = []


def case(name):
    def deco(fn):
        CASES.append((name, fn))
        return fn
    return deco


@case("EVM calldata formats ABI correctly with selector and padding")
def _():
    root = "a" * 64
    anchor_id = "ANC-001"
    calldata = format_evm_calldata(root, anchor_id)

    assert calldata.startswith(EVM_ANCHOR_SELECTOR)
    assert root in calldata
    # Check that anchor ID is hex encoded in calldata
    assert anchor_id.encode("utf-8").hex() in calldata


@case("blockchain attestation contains complete multi-chain proofs")
def _():
    root = "b" * 64
    tip = "c" * 64
    att = create_blockchain_attestation("ANC-999", root, tip, 42)

    assert att.anchor_id == "ANC-999"
    assert att.merkle_root == root
    assert att.chain_tip_hash == tip
    assert att.record_count == 42
    assert att.ots_payload["digest"] == root
    assert "https://a.pool.opentimestamps.org/digest" in att.ots_payload["calendar_urls"]
    assert "VERIFICATION INSTRUCTIONS" in att.verification_guide


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
