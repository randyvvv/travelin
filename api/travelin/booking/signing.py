"""ES256 keys, JWKs, and content hashes for AP2 mandates."""

import hashlib
import json
import logging
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from jwt.algorithms import ECAlgorithm
from pydantic import BaseModel

logger = logging.getLogger(__name__)


def load_or_create_key(pem: str, name: str) -> ec.EllipticCurvePrivateKey:
    """The configured key, or a throwaway one so local development works without secrets."""
    if pem.strip():
        key = serialization.load_pem_private_key(pem.encode(), password=None)
        if not isinstance(key, ec.EllipticCurvePrivateKey):
            raise ValueError(f"{name} must be an EC private key")
        return key
    logger.warning("%s is not set; using a temporary key for this process", name)
    return ec.generate_private_key(ec.SECP256R1())


def key_id(key: ec.EllipticCurvePrivateKey) -> str:
    der = key.public_key().public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    return hashlib.sha256(der).hexdigest()[:16]


def public_jwk(key: ec.EllipticCurvePrivateKey) -> dict[str, Any]:
    jwk = ECAlgorithm.to_jwk(key.public_key(), as_dict=True)
    return {**jwk, "kid": key_id(key), "alg": "ES256", "use": "sig"}


def digest(value: BaseModel | dict[str, Any]) -> str:
    """SHA-256 of canonical JSON, so both services hash a mandate the same way."""
    data = value.model_dump(mode="json") if isinstance(value, BaseModel) else value
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode()).hexdigest()
