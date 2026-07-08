"""Componentes visuais de orçamento — barras, cartões e tetos."""

from __future__ import annotations

from collections.abc import Callable

import pandas as pd
import streamlit as st

from app.helpers import formatar_brl, formatar_brl_md

_STATUS = {
    "ok": ("🟢", "Dentro do limite", "#22c55e"),
    "alerta": ("🟡", "Atenção — acima de 80%", "#eab308"),
    "estourado": ("🔴", "Estourou o teto", "#ef4444"),
}


def _info_status(status: str) -> tuple[str, str, str]:
    return _STATUS.get(status, _STATUS["ok"])


def _brl_html(valor: float) -> str:
    return formatar_brl(valor).replace("$", "&#36;")


def render_barra_limite(
    rotulo: str,
    gasto: float,
    limite: float,
    pct: float,
    status: str,
    *,
    subtitulo: str = "",
    key_excluir: str | None = None,
    ao_excluir: Callable[[], None] | None = None,
) -> None:
    """Cartão com barra de progresso e status colorido."""
    icone, legenda, _cor = _info_status(status)
    restante = max(limite - gasto, 0.0)
    pct_barra = min(pct / 100, 1.0)

    with st.container(border=True):
        cab, acao = st.columns(
            [1, 0.06], gap="small", vertical_alignment="top"
        )
        with cab:
            st.markdown(f"**{icone} {rotulo}**")
            if subtitulo:
                st.caption(subtitulo)
        with acao:
            if key_excluir and ao_excluir and st.button(
                "✕",
                key=key_excluir,
                help="Remover limite",
                use_container_width=True,
            ):
                ao_excluir()

        st.markdown(
            f'<p style="font-size:1.25rem;margin:0 0 0.5rem 0">'
            f"<strong>{_brl_html(gasto)}</strong> "
            f'<span style="opacity:0.65">de {_brl_html(limite)}</span></p>',
            unsafe_allow_html=True,
        )
        st.progress(pct_barra)
        cols = st.columns(3)
        cols[0].caption(f"**{pct:.0f}%** usado")
        if status == "estourado":
            cols[1].caption(f"Excesso: **{formatar_brl_md(gasto - limite)}**")
        else:
            cols[1].caption(f"Restam: **{formatar_brl_md(restante)}**")
        cols[2].caption(legenda)


def valor_meta_existente(
    metas: pd.DataFrame,
    *,
    escopo: str,
    pessoa: str = "",
    categoria: str = "",
) -> float:
    """Retorna o teto já salvo ou 0 se não houver meta."""
    if metas.empty:
        return 0.0
    mask = metas["escopo"] == escopo
    mask &= metas["pessoa"].fillna("").eq(pessoa.strip())
    mask &= metas["categoria"].fillna("").eq(categoria.strip())
    hit = metas[mask]
    if hit.empty:
        return 0.0
    return float(hit.iloc[0]["valor_limite"])
