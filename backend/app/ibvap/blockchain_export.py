"""
ibvap/blockchain_export.py — OpenTimestamps & EVM Testnet Blockchain Proof Exporter.

Supports SIH Theme: Blockchain & Cybersecurity (Roadmap Item C):
Exports local Merkle roots and SHA-256 evidence chain tips into:
  1. OpenTimestamps (Bitcoin calendar server) commitment payloads.
  2. EVM Smart Contract calldata (e.g. Sepolia / Polygon) for on-chain anchoring.
  3. Formal Court/Command Attestation proofs for chain-of-custody admissibility.
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional


# Standard EVM Anchor Function: anchorProof(bytes32,string)
# keccak256("anchorProof(bytes32,string)") -> 0x8a9bf4b2...
EVM_ANCHOR_SELECTOR = "0x8a9bf4b2"


@dataclass
class BlockchainAttestation:
    anchor_id: str
    merkle_root: str
    chain_tip_hash: str
    record_count: int
    created_at_utc: str
    ots_payload: Dict[str, Any]
    evm_calldata: str
    verification_guide: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def format_evm_calldata(merkle_root: str, anchor_id: str) -> str:
    """
    Format standard ABI calldata for an EVM anchor transaction:
    anchorProof(bytes32 root, string id)
    """
    clean_root = merkle_root.lower().replace("0x", "").zfill(64)
    id_bytes = anchor_id.encode("utf-8")
    id_len = len(id_bytes)
    id_hex = id_bytes.hex()
    padded_len = ((id_len + 31) // 32) * 32
    padded_id = id_hex.ljust(padded_len * 2, "0")

    # Offset to string parameter (2 words = 64 bytes = 0x40)
    offset_hex = hex(64)[2:].zfill(64)
    len_hex = hex(id_len)[2:].zfill(64)

    return f"{EVM_ANCHOR_SELECTOR}{clean_root}{offset_hex}{len_hex}{padded_id}"


def create_blockchain_attestation(
    anchor_id: str,
    merkle_root: str,
    chain_tip_hash: str,
    count: int,
    ts_utc: Optional[str] = None,
) -> BlockchainAttestation:
    """
    Generate complete multi-chain anchoring payload from a local Merkle anchor.
    """
    ts = ts_utc or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    ots_payload = {
        "version": 1,
        "hash_algorithm": "SHA256",
        "digest": merkle_root,
        "calendar_urls": [
            "https://a.pool.opentimestamps.org/digest",
            "https://b.pool.opentimestamps.org/digest",
        ],
        "request_timestamp": ts,
    }

    calldata = format_evm_calldata(merkle_root, anchor_id)

    guide = (
        f"VERIFICATION INSTRUCTIONS:\n"
        f"1. Compute SHA-256 hash of suspect incident JSON record.\n"
        f"2. Verify inclusion in local Merkle root '{merkle_root}' using 'ibvap/anchor.py'.\n"
        f"3. Query external ledger transaction referencing Merkle root '{merkle_root}'."
    )

    return BlockchainAttestation(
        anchor_id=anchor_id,
        merkle_root=merkle_root,
        chain_tip_hash=chain_tip_hash,
        record_count=count,
        created_at_utc=ts,
        ots_payload=ots_payload,
        evm_calldata=calldata,
        verification_guide=guide,
    )
