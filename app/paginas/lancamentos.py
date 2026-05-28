"""Página Lançamentos — exploração / filtragem da tabela completa.

Filtros na sidebar (via `sidebar_filtros_lancamentos`): pessoa, conta,
categoria, tipo, referência mês, data, busca por texto. Mostra
contagem + soma do recorte e tabela paginada com export pra CSV.
"""

from __future__ import annotations

import streamlit as st

from app.helpers import (
    aplicar_filtros,
    carregar_lancamentos,
    formatar_brl,
    ref_para_nome_br,
    sidebar_filtros_lancamentos,
)


def _resumo(df) -> None:
    """Cabeçalho com contagem + soma + soma por tipo (despesa / receita / estorno)."""
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Lançamentos filtrados", f"{len(df):,}".replace(",", "."))
    c2.metric("Soma (R$)", formatar_brl(float(df["valor"].sum())))

    por_tipo = df.groupby("tipo")["valor"].sum().to_dict()
    c3.metric("Despesas", formatar_brl(float(por_tipo.get("despesa", 0.0))))
    receitas = float(por_tipo.get("receita", 0.0))
    estornos = float(por_tipo.get("estorno", 0.0))
    c4.metric(
        "Receitas + estornos",
        formatar_brl(receitas + estornos),
        delta=(
            f"{formatar_brl(estornos)} em estornos"
            if estornos
            else None
        ),
    )


def _tabela(df) -> None:
    """Tabela editável-visualmente (não muta o banco) com formato BR."""
    if df.empty:
        st.info("Nenhum lançamento bate com os filtros aplicados.")
        return

    visivel = df.copy()
    visivel["referencia_mes"] = visivel["referencia_mes"].map(ref_para_nome_br)
    visivel = visivel.rename(
        columns={
            "data": "Data",
            "descricao": "Descrição",
            "categoria": "Categoria",
            "conta": "Cartão / Conta",
            "pessoa": "Pessoa",
            "referencia_mes": "Referência",
            "parcela": "Parcela",
            "cidade": "Cidade",
            "valor": "Valor (R$)",
            "tipo": "Tipo",
            "fonte": "Fonte",
            "arquivo": "Arquivo origem",
        }
    )
    colunas_ordem = [
        "Data",
        "Referência",
        "Descrição",
        "Categoria",
        "Cartão / Conta",
        "Pessoa",
        "Parcela",
        "Cidade",
        "Valor (R$)",
        "Tipo",
        "Fonte",
        "Arquivo origem",
    ]
    visivel = visivel[[c for c in colunas_ordem if c in visivel.columns]]

    st.dataframe(
        visivel,
        use_container_width=True,
        hide_index=True,
        height=560,
        column_config={
            "Valor (R$)": st.column_config.NumberColumn(format="R$ %.2f"),
            "Data": st.column_config.DateColumn(format="DD/MM/YYYY"),
        },
    )


def _exportar_csv(df) -> None:
    """Botão pra download CSV do recorte filtrado."""
    if df.empty:
        return
    csv = df.to_csv(index=False).encode("utf-8")
    st.download_button(
        "⬇️ Baixar recorte filtrado (CSV)",
        data=csv,
        file_name="gastometro_lancamentos.csv",
        mime="text/csv",
    )


def render() -> None:
    st.title("Lançamentos")

    df = carregar_lancamentos()
    if df is None or df.empty:
        st.info(
            "Banco vazio. Rode `gastometro` ou "
            "`python -m imports.migrar_excel_legado`."
        )
        return

    filtros = sidebar_filtros_lancamentos(df)
    sub = aplicar_filtros(df, **filtros)

    _resumo(sub)
    st.divider()
    _tabela(sub)
    _exportar_csv(sub)


render()
