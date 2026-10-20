"""
Minimal software WebAuthn authenticator (P-256, "none" attestation) for tests:
produces the same JSON a browser sends after navigator.credentials.create()/get().
"""
import hashlib
import json
import os
import struct
from typing import Optional

import cbor2
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from webauthn.helpers import base64url_to_bytes, bytes_to_base64url

UP, UV, AT, BE, BS = 0x01, 0x04, 0x40, 0x08, 0x10


class SoftAuthenticator:
    def __init__(self, rp_id: str, origin: str, backed_up: bool = False):
        self.rp_id, self.origin = rp_id, origin
        self.key = ec.generate_private_key(ec.SECP256R1())
        self.credential_id = os.urandom(32)
        self.counter = 0
        self.user_handle: Optional[bytes] = None
        self.flags_extra = (BE | BS) if backed_up else 0

    def _client_data(self, kind: str, challenge_b64: str, origin: Optional[str] = None) -> bytes:
        return json.dumps({"type": kind, "challenge": challenge_b64, "origin": origin or self.origin,
                           "crossOrigin": False}).encode()

    def _cose_key(self) -> bytes:
        numbers = self.key.public_key().public_numbers()
        return cbor2.dumps({1: 2, 3: -7, -1: 1, -2: numbers.x.to_bytes(32, "big"), -3: numbers.y.to_bytes(32, "big")})

    def create(self, public_key: dict, origin: Optional[str] = None, user_verified: bool = True) -> dict:
        """Answer PublicKeyCredentialCreationOptions (JSON form) like navigator.credentials.create()."""
        self.user_handle = base64url_to_bytes(public_key["user"]["id"])
        client_data = self._client_data("webauthn.create", public_key["challenge"], origin)
        flags = UP | AT | (UV if user_verified else 0) | self.flags_extra
        attested = os.urandom(0) + b"\x00" * 16 + struct.pack(">H", len(self.credential_id)) + self.credential_id + self._cose_key()
        auth_data = hashlib.sha256(self.rp_id.encode()).digest() + bytes([flags]) + struct.pack(">I", self.counter) + attested
        attestation = cbor2.dumps({"fmt": "none", "attStmt": {}, "authData": auth_data})
        cred_id = bytes_to_base64url(self.credential_id)
        return {
            "id": cred_id, "rawId": cred_id, "type": "public-key",
            "response": {
                "clientDataJSON": bytes_to_base64url(client_data),
                "attestationObject": bytes_to_base64url(attestation),
                "transports": ["internal"],
            },
            "clientExtensionResults": {},
        }

    def get(self, public_key: dict, origin: Optional[str] = None, user_verified: bool = True,
            counter_step: int = 1) -> dict:
        """Answer PublicKeyCredentialRequestOptions like navigator.credentials.get()."""
        self.counter += counter_step
        client_data = self._client_data("webauthn.get", public_key["challenge"], origin)
        flags = UP | (UV if user_verified else 0) | self.flags_extra
        auth_data = hashlib.sha256(self.rp_id.encode()).digest() + bytes([flags]) + struct.pack(">I", self.counter)
        signature = self.key.sign(auth_data + hashlib.sha256(client_data).digest(), ec.ECDSA(hashes.SHA256()))
        cred_id = bytes_to_base64url(self.credential_id)
        return {
            "id": cred_id, "rawId": cred_id, "type": "public-key",
            "response": {
                "clientDataJSON": bytes_to_base64url(client_data),
                "authenticatorData": bytes_to_base64url(auth_data),
                "signature": bytes_to_base64url(signature),
                "userHandle": bytes_to_base64url(self.user_handle) if self.user_handle else None,
            },
            "clientExtensionResults": {},
        }
