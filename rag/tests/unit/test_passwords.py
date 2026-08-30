"""A2, punto de control 2/3 — prefijo y compatibilidad de hashes.

``verify_password`` reconoce tres formatos de ``password_hash`` (ver el
docstring de ``rag.api.passwords``): el formato actual (marcado con el
prefijo ``v2:``), el heredado de pre-hash SHA-256 + bcrypt (sin prefijo,
formato que producía ``hash_password`` antes de introducir el prefijo), y el
heredado de bcrypt directo sobre la contraseña (sin prefijo, sin pre-hash —
lo que producían versiones anteriores del endpoint admin). Ninguna
contraseña ni hash de este archivo es real; son cadenas sintéticas.
"""

import hashlib

import bcrypt

from rag.api.passwords import hash_password, needs_rehash, verify_password
from rag.api.routes.auth import LoginRequest, RegisterRequest


def test_password_created_by_shared_service_can_log_in() -> None:
    password_hash = hash_password("Una contraseña segura y larga")
    assert verify_password("Una contraseña segura y larga", password_hash)
    assert not verify_password("otra contraseña", password_hash)


def test_malformed_hash_returns_false_instead_of_raising() -> None:
    assert not verify_password("contraseña", "hash-inválido")


def test_legacy_admin_bcrypt_hash_remains_usable() -> None:
    """Heredado, formato 3: bcrypt directo sobre la contraseña, sin prefijo."""
    password = "contraseña-legada"
    legacy_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    assert verify_password(password, legacy_hash)


def test_legacy_prehash_hash_without_prefix_remains_usable() -> None:
    """Heredado, formato 2: pre-hash SHA-256 + bcrypt, sin prefijo — lo que
    producía ``hash_password`` antes de existir ``_CURRENT_PREFIX``."""
    password = "contraseña-legada-prehash"
    digest = hashlib.sha256(password.encode("utf-8")).digest()
    legacy_prehash_hash = bcrypt.hashpw(digest, bcrypt.gensalt()).decode("utf-8")
    assert verify_password(password, legacy_prehash_hash)
    assert not verify_password("otra-contraseña", legacy_prehash_hash)


def test_hash_password_uses_the_current_prefix() -> None:
    password_hash = hash_password("contraseña-formato-actual")
    assert password_hash.startswith("v2:")


def test_current_format_hash_rejects_wrong_password() -> None:
    password_hash = hash_password("contraseña-correcta-actual")
    assert not verify_password("contraseña-incorrecta", password_hash)


def test_needs_rehash_is_false_for_current_format() -> None:
    password_hash = hash_password("cualquier-contraseña")
    assert needs_rehash(password_hash) is False


def test_needs_rehash_is_true_for_legacy_prehash_format() -> None:
    digest = hashlib.sha256(b"cualquier-contrasena").digest()
    legacy_prehash_hash = bcrypt.hashpw(digest, bcrypt.gensalt()).decode("utf-8")
    assert needs_rehash(legacy_prehash_hash) is True


def test_needs_rehash_is_true_for_legacy_direct_bcrypt_format() -> None:
    legacy_direct_hash = bcrypt.hashpw(b"cualquier-contrasena", bcrypt.gensalt()).decode("utf-8")
    assert needs_rehash(legacy_direct_hash) is True


def test_auth_models_normalize_email_without_modifying_password() -> None:
    login = LoginRequest(email="  USER@Example.com  ", password=" password with spaces ")
    register = RegisterRequest(
        email="  NEW@Example.com  ",
        password=" another password with spaces ",
    )
    assert login.email == "user@example.com"
    assert login.password == " password with spaces "
    assert register.email == "new@example.com"
    assert register.password == " another password with spaces "
