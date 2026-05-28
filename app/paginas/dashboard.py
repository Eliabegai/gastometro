"""Dashboard — visão geral do gastômetro.

Mostra:
  - KPIs: total do último mês, vs mês anterior, total acumulado,
    quantidade de lançamentos.
  - Gráfico de barras: total por mês (cronológico).
  - Gráfico de pizza: distribuição por categoria (top N + outros).
  - Tabela: top 10 maiores gastos do período mais recente.

Quando o banco está vazio, mostra uma chamada pra rodar o CLI.
"""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from app.helpers import (
    carregar_lancamentos,
    chave_ord_ref_iso,
    formatar_brl,
    ref_para_nome_br,
)

TOP_CATEGORIAS_GRAFICO = 10


def _kpi_card(coluna, titulo: str, valor: str, delta: str | None = None) -> None:
    coluna.metric(titulo, valor, delta=delta)


def _calcular_kpis(df: pd.DataFrame) -> dict[str, str | None]:
    """Total último mês, variação vs mês anterior, total acumulado, qtde."""
    if df.empty:
        return {
            "total_ultimo": "R$ 0,00",
            "delta_anterior": None,
            "total_acumulado": "R$ 0,00",
            "qtde": "0",
            "label_ultimo": "—",
        }

    refs = sorted(
        {r for r in df["referencia_mes"].astype(str) if r and r != "nan"},
        key=chave_ord_ref_iso,
    )
    ultimo = refs[-1] if refs else ""
    anterior = refs[-2] if len(refs) >= 2 else ""

    sub_ult = df[df["referencia_mes"] == ultimo]
    sub_ant = df[df["referencia_mes"] == anterior] if anterior else pd.DataFrame()

    total_ult = float(sub_ult["valor"].sum()) if not sub_ult.empty else 0.0
    total_ant = float(sub_ant["valor"].sum()) if not sub_ant.empty else 0.0

    delta: str | None = None
    if anterior:
        diff = total_ult - total_ant
        sinal = "+" if diff >= 0 else "-"
        if total_ant:
            pct = (diff / total_ant) * 100.0
            delta = (
                f"{sinal}{formatar_brl(abs(diff))[3:]} "
                f"({pct:+.1f}% vs {ref_para_nome_br(anterior)})"
            )
        else:
            delta = f"{sinal}{formatar_brl(abs(diff))[3:]} (mês anterior = R$ 0,00)"

    return {
        "total_ultimo": formatar_brl(total_ult),
        "delta_anterior": delta,
        "total_acumulado": formatar_brl(float(df["valor"].sum())),
        "qtde": f"{len(df):,}".replace(",", "."),
        "label_ultimo": ref_para_nome_br(ultimo) or "—",
    }


def _grafico_barras_mensal(df: pd.DataFrame) -> None:
    """Bar chart de total por mês (refs em ordem cronológica)."""
    if df.empty:
        return

    soma_por_ref = (
        df.groupby("referencia_mes")["valor"].sum().reset_index()
    )
    soma_por_ref["referencia_mes"] = soma_por_ref["referencia_mes"].astype(str)
    soma_por_ref = soma_por_ref.sort_values(
        "referencia_mes", key=lambda s: s.map(chave_ord_ref_iso)
    )
    soma_por_ref["mes_label"] = soma_por_ref["referencia_mes"].map(
        ref_para_nome_br
    )

    fig = px.bar(
        soma_por_ref,
        x="mes_label",
        y="valor",
        title="Total por mês",
        labels={"mes_label": "Mês", "valor": "Total (R$)"},
        text="valor",
    )
    fig.update_traces(texttemplate="R$ %{text:,.0f}", textposition="outside")
    fig.update_layout(
        yaxis_tickprefix="R$ ", yaxis_tickformat=",.0f", showlegend=False
    )
    st.plotly_chart(fig, use_container_width=True)


def _grafico_pizza_categorias(df: pd.DataFrame, top_n: int = TOP_CATEGORIAS_GRAFICO) -> None:
    """Pizza: top N categorias + 'Outras' (agregado), só gastos (valor > 0)."""
    if df.empty:
        return
    gastos = df[df["valor"] > 0]
    if gastos.empty:
        st.info("Sem gastos no período filtrado (só estornos / receitas).")
        return

    soma_cat = (
        gastos.groupby("categoria")["valor"].sum().sort_values(ascending=False)
    )
    if len(soma_cat) > top_n:
        cabeca = soma_cat.head(top_n)
        cauda = soma_cat.iloc[top_n:].sum()
        agg = pd.concat([cabeca, pd.Series({"Outras": cauda})])
    else:
        agg = soma_cat

    fig = px.pie(
        names=agg.index,
        values=agg.values,
        title=f"Distribuição por categoria (top {top_n})",
        hole=0.35,
    )
    fig.update_traces(textposition="inside", textinfo="percent+label")
    st.plotly_chart(fig, use_container_width=True)


def _maiores_gastos_recentes(df: pd.DataFrame, top_n: int = 10) -> None:
    """Tabela: maiores gastos do último mês registrado."""
    if df.empty:
        return
    refs = sorted(
        {r for r in df["referencia_mes"].astype(str) if r and r != "nan"},
        key=chave_ord_ref_iso,
    )
    if not refs:
        return
    ultimo = refs[-1]
    sub = df[(df["referencia_mes"] == ultimo) & (df["valor"] > 0)].copy()
    if sub.empty:
        return
    sub = sub.sort_values("valor", ascending=False).head(top_n)
    cols = ["data", "descricao", "categoria", "conta", "valor"]
    sub = sub[cols].rename(
        columns={
            "data": "Data",
            "descricao": "Descrição",
            "categoria": "Categoria",
            "conta": "Cartão",
            "valor": "Valor (R$)",
        }
    )
    st.subheader(f"Top {top_n} gastos — {ref_para_nome_br(ultimo)}")
    st.dataframe(
        sub,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Valor (R$)": st.column_config.NumberColumn(
                format="R$ %.2f"
            ),
        },
    )


def render() -> None:
    st.title("💸 Gastômetro — Dashboard")

    df = carregar_lancamentos()

    if df is None or df.empty:
        st.warning(
            "Nenhum lançamento no banco ainda. Rode `gastometro` (com PDFs em "
            "`entrada/`) ou `python -m imports.migrar_excel_legado` pra "
            "popular o histórico."
        )
        return

    kpis = _calcular_kpis(df)

    c1, c2, c3, c4 = st.columns(4)
    _kpi_card(
        c1,
        f"Total de {kpis['label_ultimo']}",
        kpis["total_ultimo"] or "R$ 0,00",
        kpis["delta_anterior"],
    )
    _kpi_card(
        c2, "Acumulado (todo o histórico)", kpis["total_acumulado"] or "R$ 0,00"
    )
    _kpi_card(c3, "Lançamentos no banco", kpis["qtde"] or "0")
    _kpi_card(
        c4,
        "Cartões / contas distintos",
        f"{df['conta'].nunique()}",
    )

    st.divider()

    col_a, col_b = st.columns([3, 2])
    with col_a:
        _grafico_barras_mensal(df)
    with col_b:
        _grafico_pizza_categorias(df)

    st.divider()
    _maiores_gastos_recentes(df)


render()
