"""Autenticação e autorização do app Streamlit.

Usa OIDC nativo do Streamlit (`st.login` / `st.user`) com Google.
A allowlist de e-mails vem de `GASTOMETRO_ALLOWED_EMAILS`.

Desligue auth em dev/testes com `GASTOMETRO_AUTH_ENABLED=false`.
"""

from __future__ import annotations

import os

import streamlit as st

ENV_AUTH_ENABLED = "GASTOMETRO_AUTH_ENABLED"
ENV_ALLOWED_EMAILS = "GASTOMETRO_ALLOWED_EMAILS"


def auth_habilitada() -> bool:
    """Auth ativa quando `GASTOMETRO_AUTH_ENABLED` é truthy (default: off)."""
    return os.getenv(ENV_AUTH_ENABLED, "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def emails_permitidos() -> frozenset[str]:
    """E-mails da allowlist (lowercase, sem espaços extras)."""
    bruto = os.getenv(ENV_ALLOWED_EMAILS, "")
    if not bruto.strip():
        return frozenset()
    return frozenset(
        parte.strip().lower()
        for parte in bruto.split(",")
        if parte.strip()
    )


def email_na_allowlist(email: str | None) -> bool:
    """True se `email` está na allowlist (case-insensitive)."""
    if not email:
        return False
    permitidos = emails_permitidos()
    if not permitidos:
        return False
    return email.strip().lower() in permitidos


def usuario_autorizado() -> bool:
    """Logado no Google **e** e-mail permitido."""
    if not auth_habilitada():
        return True
    if not st.user.is_logged_in:
        return False
    return email_na_allowlist(getattr(st.user, "email", None))


def _tela_login() -> None:
    st.title("Gastômetro")
    st.subheader("Acesso restrito")
    st.caption(
        "Entre com sua conta Google para ver os dados financeiros. "
        "Só e-mails autorizados têm acesso."
    )
    st.button("Entrar com Google", type="primary", on_click=st.login)


def _tela_acesso_negado() -> None:
    email = getattr(st.user, "email", None) or "(desconhecido)"
    st.error(f"Acesso negado para **{email}**.")
    st.caption(
        "Este e-mail não está na lista de usuários autorizados. "
        "Peça ao administrador para incluir seu e-mail."
    )
    st.button("Sair", on_click=st.logout)


def exigir_acesso() -> None:
    """Bloqueia o app até login + allowlist. Chame antes de carregar dados."""
    if not auth_habilitada():
        return

    if not st.user.is_logged_in:
        _tela_login()
        st.stop()

    if not email_na_allowlist(getattr(st.user, "email", None)):
        _tela_acesso_negado()
        st.stop()


def renderizar_barra_usuario() -> None:
    """Mostra nome/e-mail e botão Sair na sidebar (só com auth ligada)."""
    if not auth_habilitada() or not st.user.is_logged_in:
        return

    nome = getattr(st.user, "name", None) or "Usuário"
    email = getattr(st.user, "email", None) or ""
    with st.sidebar:
        st.caption(f"👤 {nome}")
        if email:
            st.caption(email)
        st.button("Sair", on_click=st.logout, key="btn_logout_sidebar")
