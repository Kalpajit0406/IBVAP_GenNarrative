"""
test_anchor.py — Cryptographic Merkle tree and evidence anchoring tests.

    python tests/test_anchor.py
    pytest  tests/test_anchor.py
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ibvap.anchor import AnchorLedger, MerkleTree  # noqa: E402

CASES = []


def case(name):
    def deco(fn):
        CASES.append((name, fn))
        return fn
    return deco


@case("empty tree produces deterministic empty root")
def _():
    tree = MerkleTree([])
    assert isinstance(tree.root_hash(), str)
    assert len(tree.root_hash()) == 64


@case("single leaf generates valid root")
def _():
    h = "a" * 64
    tree = MerkleTree([h])
    assert len(tree.root_hash()) == 64
    proof = tree.audit_proof(0)
    assert MerkleTree.verify_proof(h, proof, tree.root_hash())


@case("multi-leaf tree verifies all inclusion proofs (even and odd count)")
def _():
    for count in (4, 5, 8, 11):
        hashes = [f"{i:02x}" * 32 for i in range(count)]
        tree = MerkleTree(hashes)
        root = tree.root_hash()

        for idx, h in enumerate(hashes):
            proof = tree.audit_proof(idx)
            assert MerkleTree.verify_proof(h, proof, root), f"Proof failed for index {idx} in size {count}"


@case("tampered leaf or wrong root fails verification")
def _():
    hashes = [f"{i:02x}" * 32 for i in range(4)]
    tree = MerkleTree(hashes)
    root = tree.root_hash()
    proof = tree.audit_proof(0)

    # Tampered leaf
    assert not MerkleTree.verify_proof("f" * 64, proof, root)

    # Wrong root
    assert not MerkleTree.verify_proof(hashes[0], proof, "0" * 64)


@case("anchor ledger appends and reads anchor records")
def _():
    tmp_path = str(Path(tempfile.mkdtemp()) / "anchors.jsonl")
    ledger = AnchorLedger(tmp_path)

    hashes = ["11" * 32, "22" * 32, "33" * 32]
    tip = "33" * 32
    rec = ledger.append_anchor(hashes, tip, anchored_to="local_testnet")

    assert rec.count == 3
    assert rec.chain_tip_hash == tip
    assert rec.merkle_root

    loaded = ledger.read_anchors()
    assert len(loaded) == 1
    assert loaded[0]["merkle_root"] == rec.merkle_root
    assert loaded[0]["count"] == 3


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
