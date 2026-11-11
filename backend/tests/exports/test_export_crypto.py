"""Passphrase encryption of exported files (.fhx)."""
import struct

import pytest

from src.exports import crypto

PASS = "correct horse battery"


def test_round_trip_keeps_bytes_exactly():
    data = "﻿date;name;amount\r\n2026-03-05;Ремонт ванни;1234,50\r\n".encode("utf-8")
    blob = crypto.encrypt(data, PASS)
    assert crypto.is_encrypted(blob)
    assert data not in blob and "Ремонт".encode() not in blob
    assert crypto.decrypt(blob, PASS) == data


def test_same_input_encrypts_differently():
    assert crypto.encrypt(b"same", PASS) != crypto.encrypt(b"same", PASS)


def test_wrong_passphrase():
    blob = crypto.encrypt(b"secret", PASS)
    with pytest.raises(crypto.WrongPassphrase):
        crypto.decrypt(blob, PASS + "!")


@pytest.mark.parametrize("index", [9, 20, 33, -1])  # salt, salt, nonce, tag
def test_any_changed_byte_is_rejected(index):
    blob = bytearray(crypto.encrypt(b"secret data", PASS))
    blob[index] ^= 0x01
    with pytest.raises(crypto.WrongPassphrase):
        crypto.decrypt(bytes(blob), PASS)


def test_changed_kdf_parameters_are_rejected():
    blob = bytearray(crypto.encrypt(b"secret data", PASS))
    blob[6] = 9  # r: still within bounds → different key / failed tag
    with pytest.raises(crypto.WrongPassphrase):
        crypto.decrypt(bytes(blob), PASS)


def test_oversized_kdf_cost_is_refused_before_deriving():
    blob = bytearray(crypto.encrypt(b"x", PASS))
    struct.pack_into(">B", blob, 5, 30)  # N = 2**30 would need ~1 TB
    with pytest.raises(crypto.CorruptFile):
        crypto.decrypt(bytes(blob), PASS)


@pytest.mark.parametrize("blob", [b"", b"FHX1", b"date;name\r\n" * 10, b"FHX1\x02" + b"\x00" * 60])
def test_not_an_encrypted_file(blob):
    with pytest.raises(crypto.CorruptFile):
        crypto.decrypt(blob, PASS)


@pytest.mark.parametrize("value, ok", [("1234567", False), ("12345678", True), ("x" * 128, True), ("x" * 129, False)])
def test_passphrase_length(value, ok):
    if ok:
        assert crypto.validate_passphrase(value) == value
    else:
        with pytest.raises(ValueError):
            crypto.validate_passphrase(value)
