"""Testes de autenticação e allowlist (sem runtime OAuth)."""

from __future__ import annotations

import pytest

from app.auth import (
    auth_habilitada,
    email_na_allowlist,
    emails_permitidos,
    exigir_acesso,
)


def test_emails_permitidos_parseia_lista(monkeypatch) -> None:
    monkeypatch.setenv(
        "GASTOMETRO_ALLOWED_EMAILS",
        " Ana@Gmail.com , Outro@Example.com ",
    )
    assert emails_permitidos() == frozenset({"ana@gmail.com", "outro@example.com"})


def test_emails_permitidos_vazio_quando_env_ausente(monkeypatch) -> None:
    monkeypatch.delenv("GASTOMETRO_ALLOWED_EMAILS", raising=False)
    assert emails_permitidos() == frozenset()


def test_email_na_allowlist_case_insensitive(monkeypatch) -> None:
    monkeypatch.setenv("GASTOMETRO_ALLOWED_EMAILS", "voce@gmail.com")
    assert email_na_allowlist("Voce@Gmail.com") is True
    assert email_na_allowlist("outro@gmail.com") is False


def test_email_na_allowlist_rejeita_vazio(monkeypatch) -> None:
    monkeypatch.setenv("GASTOMETRO_ALLOWED_EMAILS", "voce@gmail.com")
    assert email_na_allowlist(None) is False
    assert email_na_allowlist("") is False


def test_email_na_allowlist_lista_vazia_nega_todos(monkeypatch) -> None:
    monkeypatch.setenv("GASTOMETRO_ALLOWED_EMAILS", "")
    assert email_na_allowlist("voce@gmail.com") is False


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [
        ("true", True),
        ("1", True),
        ("yes", True),
        ("on", True),
        ("false", False),
        ("0", False),
        ("", False),
    ],
)
def test_auth_habilitada(monkeypatch, valor: str, esperado: bool) -> None:
    monkeypatch.setenv("GASTOMETRO_AUTH_ENABLED", valor)
    assert auth_habilitada() is esperado


def test_exigir_acesso_noop_quando_auth_desligada(monkeypatch) -> None:
    """Com auth off, `exigir_acesso` não levanta nem chama st.stop."""
    monkeypatch.setenv("GASTOMETRO_AUTH_ENABLED", "false")
    exigir_acesso()
