"""HMAC-SHA256 artifact signing and verification.

Signs generated artifacts (DAGs, Glue scripts, config files) in Phase 4
so Phase 5 can verify integrity before deployment. Prevents tampered
artifacts from being deployed.

Uses ARTIFACT_SIGNING_KEY env var for HMAC key.
Falls back to unsigned checksums if key not set (dev mode).

Usage:
    from shared.utils.artifact_signer import sign_artifact, verify_artifact

    # Phase 4: Sign after generation
    sig = sign_artifact("workloads/foo/dags/foo_dag.py", agent_name="dag-agent")

    # Phase 5: Verify before deployment
    ok, detail = verify_artifact("workloads/foo/dags/foo_dag.py", sig)
"""

import hashlib
import hmac
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


SIGNING_KEY_ENV = "ARTIFACT_SIGNING_KEY"


def _get_signing_key() -> Optional[bytes]:
    """Get HMAC signing key from environment."""
    key = os.environ.get(SIGNING_KEY_ENV)
    if key:
        return key.encode("utf-8")
    return None


def compute_file_checksum(filepath: str) -> str:
    """Compute SHA-256 of a file's contents."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def sign_artifact(
    filepath: str,
    agent_name: str = "unknown",
    timestamp: Optional[str] = None,
) -> dict:
    """Sign an artifact file and return signature metadata.

    Returns:
        dict with keys: filepath, checksum, signature (or None), signed_by, signed_at, signed
    """
    checksum = compute_file_checksum(filepath)
    signed_at = timestamp or datetime.now(timezone.utc).isoformat()

    key = _get_signing_key()
    if key:
        # HMAC-SHA256 over: checksum + agent_name + signed_at
        message = f"{checksum}:{agent_name}:{signed_at}".encode("utf-8")
        signature = hmac.new(key, message, hashlib.sha256).hexdigest()
        signed = True
    else:
        signature = None
        signed = False

    return {
        "filepath": filepath,
        "checksum": checksum,
        "signature": signature,
        "signed_by": agent_name,
        "signed_at": signed_at,
        "signed": signed,
    }


def verify_artifact(filepath: str, sig_metadata: dict) -> tuple[bool, str]:
    """Verify an artifact's integrity and signature.

    Returns:
        (passed, detail) tuple
    """
    if not Path(filepath).exists():
        return False, f"File not found: {filepath}"

    # Step 1: Verify checksum (always, regardless of signing)
    current_checksum = compute_file_checksum(filepath)
    expected_checksum = sig_metadata.get("checksum", "")
    if current_checksum != expected_checksum:
        return False, (
            f"Checksum mismatch: expected {expected_checksum[:16]}..., "
            f"got {current_checksum[:16]}... — file has been tampered with"
        )

    # Step 2: Verify HMAC signature (if signing key is available)
    key = _get_signing_key()
    if key and sig_metadata.get("signed"):
        agent_name = sig_metadata.get("signed_by", "unknown")
        signed_at = sig_metadata.get("signed_at", "")
        message = f"{expected_checksum}:{agent_name}:{signed_at}".encode("utf-8")
        expected_sig = hmac.new(key, message, hashlib.sha256).hexdigest()

        actual_sig = sig_metadata.get("signature", "")
        if not hmac.compare_digest(expected_sig, actual_sig):
            return False, "Signature mismatch — artifact was not signed by expected agent"

        return True, f"Verified: checksum + signature valid (signed by {agent_name})"

    if not sig_metadata.get("signed"):
        return True, "Checksum valid (unsigned — dev mode, no ARTIFACT_SIGNING_KEY set)"

    return True, "Checksum valid (signing key not available for verification)"


def sign_artifacts(
    filepaths: list[str],
    agent_name: str = "unknown",
    timestamp: Optional[str] = None,
) -> list[dict]:
    """Sign multiple artifacts at once."""
    ts = timestamp or datetime.now(timezone.utc).isoformat()
    return [sign_artifact(fp, agent_name, ts) for fp in filepaths]


def verify_artifacts(
    signatures: list[dict],
) -> tuple[bool, list[tuple[str, bool, str]]]:
    """Verify multiple artifacts. Returns (all_passed, individual_results)."""
    results = []
    all_passed = True
    for sig in signatures:
        fp = sig.get("filepath", "")
        passed, detail = verify_artifact(fp, sig)
        results.append((fp, passed, detail))
        if not passed:
            all_passed = False
    return all_passed, results
