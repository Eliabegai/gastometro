"""Utilidades compartilhadas pelas páginas Streamlit.

- Formatação BR (moeda, datas, referência mes).
- Cache da consulta principal (lançamentos) usando `st.cache_data`
  com TTL curto (atualiza ao reimportar via CLI).
- Filtros canônicos aplicáveis a um DataFrame de lançamentos.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd
import streamlit as st

from db.repository import listar_faturas_df, listar_lancamentos_df
from parsers.base import MES_POR_NUMERO

MES_POR_NOME = {nome: num for num, nome in MES_POR_NUMERO.items()}


def formatar_brl(valor: float | int) -> str:
    """`1.234,56` sem locale; preserva sinal."""
    s = f"{abs(valor):,.2f}"
    s = s.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"-R$ {s}" if valor < 0 else f"R$ {s}"


def ref_para_nome_br(iso: str | None) -> str:
    """'2026-05' → 'Maio/2026'. Aceita já formatado."""
    if not iso:
        return ""
    if "/" in iso:
        return iso
    if "-" not in iso:
        return iso
    try:
        ano, mes = iso.split("-", 1)
        nome = MES_POR_NUMERO.get(int(mes), mes)
        return f"{nome}/{ano}"
    except (ValueError, KeyError):
        return iso


def chave_ord_ref_iso(iso: str) -> tuple[int, int]:
    """Pra ordenar lista de referências `YYYY-MM` cronologicamente."""
    if not iso or "-" not in iso:
        return (0, 0)
    try:
        ano, mes = iso.split("-", 1)
        return (int(ano), int(mes))
    except ValueError:
        return (0, 0)


@st.cache_data(ttl=30, show_spinner="Lendo lançamentos do banco…")
def carregar_lancamentos(sinal_estorno_negativo: bool = True) -> pd.DataFrame:
    """Wrapper cacheado em torno de `listar_lancamentos_df`.

    TTL curto (30s) pra recarregar quase imediatamente quando o usuário
    rodar `gastometro` numa outra janela. Em telas críticas use
    `st.cache_data.clear()` ou recarregue a página.
    """
    return listar_lancamentos_df(sinal_estorno_negativo=sinal_estorno_negativo)


@st.cache_data(ttl=30, show_spinner="Lendo faturas do banco…")
def carregar_faturas() -> pd.DataFrame:
    return listar_faturas_df()


def aplicar_filtros(
    df: pd.DataFrame,
    *,
    pessoas: list[str] | None = None,
    contas: list[str] | None = None,
    categorias: list[str] | None = None,
    tipos: list[str] | None = None,
    referencias: list[str] | None = None,
    data_inicio: date | None = None,
    data_fim: date | None = None,
    texto: str | None = None,
) -> pd.DataFrame:
    """Aplica filtros canônicos. Cada parâmetro é opcional/aditivo.

    `texto` é busca case-insensitive em `descricao` (substring).
    """
    if df is None or df.empty:
        return df
    sub = df
    if pessoas:
        sub = sub[sub["pessoa"].isin(pessoas)]
    if contas:
        sub = sub[sub["conta"].isin(contas)]
    if categorias:
        sub = sub[sub["categoria"].isin(categorias)]
    if tipos:
        sub = sub[sub["tipo"].isin(tipos)]
    if referencias:
        sub = sub[sub["referencia_mes"].isin(referencias)]
    if data_inicio is not None:
        sub = sub[sub["data"] >= data_inicio]
    if data_fim is not None:
        sub = sub[sub["data"] <= data_fim]
    if texto:
        sub = sub[
            sub["descricao"].astype(str).str.contains(texto, case=False, na=False)
        ]
    return sub


def referencias_disponiveis(df: pd.DataFrame) -> list[str]:
    """Lista única ordenada de `referencia_mes` (ISO `YYYY-MM`)."""
    if df is None or df.empty:
        return []
    refs = {str(r) for r in df["referencia_mes"].astype(str) if r and r != "nan"}
    return sorted(refs, key=chave_ord_ref_iso)


def sidebar_filtros_lancamentos(df: pd.DataFrame) -> dict[str, Any]:
    """Renderiza filtros padrão na sidebar e devolve dict pra `aplicar_filtros`.

    Inclui `key`s distintas por widget pra Streamlit preservar estado
    entre re-runs. Quando a tabela está vazia, ainda renderiza widgets
    desabilitados (UX consistente).
    """
    st.sidebar.subheader("Filtros")

    pessoas_opts = sorted({p for p in df.get("pessoa", []) if p})
    contas_opts = sorted({c for c in df.get("conta", []) if c})
    categorias_opts = sorted({c for c in df.get("categoria", []) if c})
    tipos_opts = sorted({t for t in df.get("tipo", []) if t})
    refs_opts = referencias_disponiveis(df)

    pessoas = st.sidebar.multiselect(
        "Pessoa", pessoas_opts, default=[], key="f_pessoas"
    )
    contas = st.sidebar.multiselect(
        "Conta / Cartão", contas_opts, default=[], key="f_contas"
    )
    categorias = st.sidebar.multiselect(
        "Categoria", categorias_opts, default=[], key="f_cats"
    )
    tipos = st.sidebar.multiselect(
        "Tipo", tipos_opts, default=[], key="f_tipos"
    )

    refs_label = [ref_para_nome_br(r) for r in refs_opts]
    refs_label_to_iso = dict(zip(refs_label, refs_opts, strict=False))
    refs_sel_label = st.sidebar.multiselect(
        "Referência (mês)", refs_label, default=[], key="f_refs"
    )
    refs = [refs_label_to_iso[r] for r in refs_sel_label]

    texto = st.sidebar.text_input(
        "Buscar descrição contém…", value="", key="f_texto"
    ).strip()

    data_inicio: date | None = None
    data_fim: date | None = None
    if not df.empty and "data" in df.columns:
        datas = pd.to_datetime(df["data"], errors="coerce").dropna()
        if not datas.empty:
            faixa = st.sidebar.date_input(
                "Período (data da transação)",
                value=(datas.min().date(), datas.max().date()),
                key="f_data",
            )
            if isinstance(faixa, tuple) and len(faixa) == 2:
                data_inicio, data_fim = faixa

    return {
        "pessoas": pessoas,
        "contas": contas,
        "categorias": categorias,
        "tipos": tipos,
        "referencias": refs,
        "data_inicio": data_inicio,
        "data_fim": data_fim,
        "texto": texto or None,
    }


def invalidar_cache() -> None:
    """Esvazia cache do `st.cache_data` — usar após mutações no banco."""
    carregar_lancamentos.clear()
    carregar_faturas.clear()
