# app/utils/generator.py
import secrets
import string
import hashlib

def _raw_code(length: int = 16) -> str:
    """Raw secure random string (uppercase + digits)."""
    alphabet = string.ascii_uppercase + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))

def _checksum(data: str) -> str:
    """Return a short 2-char checksum derived from sha256."""
    digest = hashlib.sha256(data.encode("utf-8")).hexdigest()
    return digest[:2].upper()

def _format_blocks(raw: str, block_size: int = 4) -> str:
    """Split raw into evenly sized blocks (last block may be shorter)."""
    return "-".join(raw[i:i+block_size] for i in range(0, len(raw), block_size))

def generate_license_key(prefix: str = "SOL", length: int = 16, block_size: int = 4) -> str:
    """
    Generate a production-grade license key.

    Example: SOL-ABCD-EFGH-IJKL-4F
    - length: number of raw characters used to create blocks (default 16 => 4 blocks of 4)
    - block_size: characters per block used in formatted output
    """
    raw = _raw_code(length)
    blocks = _format_blocks(raw, block_size)
    chk = _checksum(raw)
    return f"{prefix}-{blocks}-{chk}"
