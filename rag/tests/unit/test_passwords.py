"""Compatibilidad del servicio único de contraseñas."""

import bcrypt

from rag.api.passwords import hash_password, verify_password
from rag.api.routes.auth import LoginRequest, RegisterRequest


def test_password_created_by_shared_service_can_log_in() -> None:
    password_hash = hash_password("Una contraseña segura y larga")
    assert verify_password("Una contraseña segura y larga", password_hash)
    assert not verify_password("otra contraseña", password_hash)


def test_malformed_hash_returns_false_instead_of_raising() -> None:
    assert not verify_password("contraseña", "hash-inválido")


def test_legacy_admin_bcrypt_hash_remains_usable() -> None:
    password = "contraseña-legada"
    legacy_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    assert verify_password(password, legacy_hash)


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
