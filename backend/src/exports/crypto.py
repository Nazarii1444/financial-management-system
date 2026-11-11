"""
Passphrase encryption for exported files (`.fhx`) — pure, no DB.

Layout (all integers big-endian):

    b"FHX1" | version (1) | log2(N) (1) | r (1) | p (1) | salt (16) | nonce (12) | AES-256-GCM ciphertext + tag

The key is scrypt(passphrase, salt, N, r, p). Everything before the ciphertext
is authenticated as associated data, so a changed header fails like a wrong
passphrase. The KDF cost lives in the header: it can be raised later without
breaking old files, and is bounded on read so an uploaded file can't make the
server allocate gigabytes.
"""
import os
import struct

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

MAGIC = b"FHX1"
VERSION = 1
EXTENSION = ".fhx"

# scrypt cost: N = 2**15, r = 8 → ~32 MB and ~0.1 s per derivation
_LOG2_N, _R, _P = 15, 8, 1
_MAX_LOG2_N, _MAX_R, _MAX_P = 17, 16, 4   # ~256 MB worst case
_SALT_LEN, _NONCE_LEN = 16, 12
_HEADER = struct.Struct(">4sBBBB")
_PREFIX_LEN = _HEADER.size + _SALT_LEN + _NONCE_LEN
_TAG_LEN = 16

PASSPHRASE_MIN, PASSPHRASE_MAX = 8, 128


class ExportCryptoError(ValueError):
    pass


class WrongPassphrase(ExportCryptoError):
    pass


class CorruptFile(ExportCryptoError):
    pass


def validate_passphrase(passphrase: str) -> str:
    if not PASSPHRASE_MIN <= len(passphrase) <= PASSPHRASE_MAX:
        raise ValueError(f"Passphrase must be {PASSPHRASE_MIN}–{PASSPHRASE_MAX} characters long")
    return passphrase


def is_encrypted(blob: bytes) -> bool:
    return blob[:len(MAGIC)] == MAGIC


def _key(passphrase: str, salt: bytes, log2_n: int, r: int, p: int) -> bytes:
    return Scrypt(salt=salt, length=32, n=2 ** log2_n, r=r, p=p).derive(passphrase.encode("utf-8"))


def encrypt(data: bytes, passphrase: str) -> bytes:
    salt, nonce = os.urandom(_SALT_LEN), os.urandom(_NONCE_LEN)
    prefix = _HEADER.pack(MAGIC, VERSION, _LOG2_N, _R, _P) + salt + nonce
    key = _key(passphrase, salt, _LOG2_N, _R, _P)
    return prefix + AESGCM(key).encrypt(nonce, data, prefix)


def decrypt(blob: bytes, passphrase: str) -> bytes:
    if len(blob) < _PREFIX_LEN + _TAG_LEN or not is_encrypted(blob):
        raise CorruptFile("Not an encrypted FinanceHub file")
    _, version, log2_n, r, p = _HEADER.unpack_from(blob)
    if version != VERSION:
        raise CorruptFile(f"Unsupported file version {version}")
    if not (10 <= log2_n <= _MAX_LOG2_N and 1 <= r <= _MAX_R and 1 <= p <= _MAX_P):
        raise CorruptFile("Unsupported key-derivation parameters")
    salt = blob[_HEADER.size:_HEADER.size + _SALT_LEN]
    nonce = blob[_HEADER.size + _SALT_LEN:_PREFIX_LEN]
    key = _key(passphrase, salt, log2_n, r, p)
    try:
        return AESGCM(key).decrypt(nonce, blob[_PREFIX_LEN:], blob[:_PREFIX_LEN])
    except InvalidTag:
        # GCM can't tell a wrong passphrase from tampered bytes — the passphrase is the usual cause
        raise WrongPassphrase("Wrong passphrase or damaged file") from None
