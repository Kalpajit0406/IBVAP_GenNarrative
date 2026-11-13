"""
ibvap/anchor.py — Merkle Tree Root Computation & Audit Proofs for Evidence Anchoring.

Supports SIH Theme: Blockchain & Cybersecurity (P0 Roadmap Item C):
Provides cryptographic batching of the local SHA-256 hash-chained surveillance ledger
into compact Merkle roots suitable for external anchoring (e.g. OpenTimestamps / public EVM testnet)
without leaking full surveillance payloads or exposing local video feeds.
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def hash_leaf(record_hash: str) -> str:
    """Domain-separated leaf hashing (RFC 6962 / standard Merkle tree)."""
    return _sha256(b"\x00" + record_hash.encode("utf-8"))


def hash_node(left: str, right: str) -> str:
    """Domain-separated internal node hashing."""
    return _sha256(b"\x01" + bytes.fromhex(left) + bytes.fromhex(right))


class MerkleTree:
    """
    Binary Merkle Tree for batch evidence anchoring and cryptographic inclusion proofs.
    """

    def __init__(self, record_hashes: List[str]) -> None:
        self.leaves = [str(h).strip().lower() for h in record_hashes if str(h).strip()]
        self.levels: List[List[str]] = []
        self._build()

    def _build(self) -> None:
        if not self.leaves:
            self.root = _sha256(b"")
            self.levels = [[]]
            return

        current = [hash_leaf(h) for h in self.leaves]
        self.levels.append(current)

        while len(current) > 1:
            next_level = []
            for i in range(0, len(current), 2):
                left = current[i]
                right = current[i + 1] if i + 1 < len(current) else current[i]
                next_level.append(hash_node(left, right))
            current = next_level
            self.levels.append(current)

        self.root = self.levels[-1][0] if self.levels[-1] else _sha256(b"")

    def root_hash(self) -> str:
        return self.root

    def audit_proof(self, index: int) -> List[Tuple[str, str]]:
        """
        Produce a list of (sibling_hash, 'L'|'R') steps from leaf to root.
        """
        if index < 0 or index >= len(self.leaves):
            raise IndexError("Leaf index out of bounds")

        proof: List[Tuple[str, str]] = []
        idx = index
        for level in self.levels[:-1]:
            is_right = (idx % 2 == 1)
            sibling_idx = idx - 1 if is_right else idx + 1
            if sibling_idx >= len(level):
                sibling_hash = level[idx]   # duplicated odd leaf
            else:
                sibling_hash = level[sibling_idx]
            proof.append((sibling_hash, "L" if is_right else "R"))
            idx //= 2
        return proof

    @staticmethod
    def verify_proof(leaf_hash: str, proof: List[Tuple[str, str]], expected_root: str) -> bool:
        """Verify an inclusion audit proof against the expected root."""
        current = hash_leaf(str(leaf_hash).strip().lower())
        for sibling, direction in proof:
            if direction == "L":
                current = hash_node(sibling, current)
            else:
                current = hash_node(current, sibling)
        return current.lower() == expected_root.lower()


@dataclass
class AnchorRecord:
    """An anchored block batch summary."""
    anchor_id: str
    ts_utc: str
    count: int
    merkle_root: str
    chain_tip_hash: str
    anchored_to: str            # e.g. "local_audit_ledger" / "opentimestamps" / "evm_sepolia"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class AnchorLedger:
    """
    Manages anchor summaries persisted to disk in JSONL format.
    """

    def __init__(self, path: str = "data/anchors.jsonl") -> None:
        self.path = Path(path)

    def append_anchor(
        self,
        record_hashes: List[str],
        chain_tip_hash: str,
        anchored_to: str = "local_audit_ledger",
    ) -> AnchorRecord:
        """Create and write a Merkle anchor record for a slice of evidence hashes."""
        tree = MerkleTree(record_hashes)
        ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        anchor_id = f"ANC-{int(time.time() * 1000)}"

        rec = AnchorRecord(
            anchor_id=anchor_id,
            ts_utc=ts,
            count=len(record_hashes),
            merkle_root=tree.root_hash(),
            chain_tip_hash=chain_tip_hash,
            anchored_to=anchored_to,
        )

        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec.to_dict()) + "\n")

        return rec

    def read_anchors(self) -> List[Dict[str, Any]]:
        if not self.path.is_file():
            return []
        out = []
        with open(self.path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        out.append(json.loads(line))
                    except Exception:
                        pass
        return out
