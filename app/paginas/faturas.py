"""Página Faturas — lista de PDFs processados, com drill-down.

Tabela principal com cabeçalhos das faturas (1 por arquivo PDF). Ao
selecionar uma linha, mostra os lançamentos daquela fatura na parte
de baixo.
"""

from __future__ import annotations

import streamlit as st

from app.helpers import (
    carregar_faturas,
    carregar_lancamentos,
    chave_ord_ref_iso,
    formatar_brl,
    ref_para_nome_br,
)
from app.paginas._importar_pdfs import render_uploader


def _tabela_faturas(df) -> None:
    visivel = df.copy()
    visivel["referencia_mes"] = visivel["referencia_mes"].map(ref_para_nome_br)
    visivel = visivel.rename(
        columns={
            "arquivo": "Arquivo",
            "conta": "Cartão",
            "pessoa": "Pessoa",
            "referencia_mes": "Referência",
            "fechamento": "Fechamento",
            "vencimento": "Vencimento",
            "valor_total_declarado": "Valor total (R$)",
            "qtde_transacoes": "Qtde.",
        }
    )
    colunas = [
        "Arquivo",
        "Cartão",
        "Pessoa",
        "Referência",
        "Fechamento",
        "Vencimento",
        "Valor total (R$)",
        "Qtde.",
    ]
    visivel = visivel[[c for c in colunas if c in visivel.columns]]

    st.dataframe(
        visivel,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Valor total (R$)": st.column_config.NumberColumn(format="R$ %.2f"),
            "Fechamento": st.column_config.DateColumn(format="DD/MM/YYYY"),
            "Vencimento": st.column_config.DateColumn(format="DD/MM/YYYY"),
        },
    )


def _resumo_por_cartao(df) -> None:
    """KPIs agregados por cartão: nº faturas, soma do total, qtde transações."""
    if df.empty:
        return
    agg = (
        df.groupby("conta")
        .agg(
            faturas=("id", "count"),
            total=("valor_total_declarado", "sum"),
            transacoes=("qtde_transacoes", "sum"),
        )
        .reset_index()
        .sort_values("total", ascending=False)
    )
    st.subheader("Resumo por cartão")
    agg["total"] = agg["total"].fillna(0.0).map(formatar_brl)
    agg = agg.rename(
        columns={
            "conta": "Cartão",
            "faturas": "Qtde. Faturas",
            "total": "Valor total acumulado",
            "transacoes": "Qtde. Transações",
        }
    )
    st.dataframe(agg, use_container_width=True, hide_index=True)


def _drill_down(df_faturas, df_lanc) -> None:
    """Selectbox da fatura → tabela com seus lançamentos."""
    if df_faturas.empty:
        return

    df_faturas = df_faturas.copy()
    df_faturas["ref_label"] = df_faturas["referencia_mes"].map(ref_para_nome_br)
    df_faturas["rotulo"] = df_faturas.apply(
        lambda r: f"{r['arquivo']}  —  {r['conta']}  ({r['ref_label']})",
        axis=1,
    )

    opcoes_ordenadas = df_faturas.sort_values(
        "referencia_mes",
        key=lambda s: s.map(chave_ord_ref_iso),
        ascending=False,
    )

    st.subheader("Detalhe de uma fatura")
    rotulo = st.selectbox(
        "Escolha uma fatura:",
        options=opcoes_ordenadas["rotulo"].tolist(),
        index=0,
    )
    linha = opcoes_ordenadas[opcoes_ordenadas["rotulo"] == rotulo].iloc[0]
    arquivo = linha["arquivo"]

    sub = df_lanc[df_lanc["arquivo"] == arquivo].copy()
    if sub.empty:
        st.info("Nenhum lançamento para essa fatura no banco.")
        return

    c1, c2, c3 = st.columns(3)
    c1.metric("Lançamentos", f"{len(sub):,}".replace(",", "."))
    c2.metric("Soma (R$)", formatar_brl(float(sub["valor"].sum())))
    c3.metric(
        "Total declarado",
        formatar_brl(float(linha["valor_total_declarado"] or 0.0)),
    )

    sub_v = sub[
        ["data", "descricao", "categoria", "parcela", "cidade", "valor", "tipo"]
    ].rename(
        columns={
            "data": "Data",
            "descricao": "Descrição",
            "categoria": "Categoria",
            "parcela": "Parcela",
            "cidade": "Cidade",
            "valor": "Valor (R$)",
            "tipo": "Tipo",
        }
    )
    st.dataframe(
        sub_v,
        use_container_width=True,
        hide_index=True,
        height=400,
        column_config={
            "Valor (R$)": st.column_config.NumberColumn(format="R$ %.2f"),
            "Data": st.column_config.DateColumn(format="DD/MM/YYYY"),
        },
    )


def render() -> None:
    st.title("Faturas")

    with st.expander("📥 Importar nova fatura (PDF)", expanded=False):
        render_uploader(key_prefix="pagina_faturas")

    df_fat = carregar_faturas()
    if df_fat is None or df_fat.empty:
        st.info(
            "Nenhuma fatura no banco ainda. Use o uploader acima ou rode "
            "`gastometro` no terminal (PDFs em `entrada/`)."
        )
        return

    c1, c2 = st.columns(2)
    c1.metric("Faturas registradas", f"{len(df_fat):,}".replace(",", "."))
    total = float(df_fat["valor_total_declarado"].fillna(0).sum())
    c2.metric("Soma dos totais declarados", formatar_brl(total))

    st.divider()
    _tabela_faturas(df_fat)
    st.divider()
    _resumo_por_cartao(df_fat)
    st.divider()

    df_lanc = carregar_lancamentos()
    _drill_down(df_fat, df_lanc)


render()
