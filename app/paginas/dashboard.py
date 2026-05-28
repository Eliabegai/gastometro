"""Dashboard — visão geral do gastômetro.

Mostra:
  - Seletor de ano (default = ano corrente; opção 'Todos os anos'
    disponível pra ver o histórico inteiro quando precisar).
  - KPIs: despesa e receita do mês mais recente (com delta vs anterior),
    despesa, receita e saldo do ano todo.
  - Gráfico de barras: despesas vs receitas por mês (agrupado).
  - Gráfico de pizza: distribuição de **despesas** por categoria
    (receitas ficam de fora porque misturam fluxo de entrada com saída).
  - Tabela: top 10 maiores despesas do mês mais recente do recorte.

Princípio: receita NUNCA é somada com despesa num mesmo KPI. KPIs
ficam sempre rotulados explicitamente.
"""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from app.helpers import (
    carregar_lancamentos,
    chave_ord_ref_iso,
    filtrar_por_ano,
    formatar_brl,
    ref_para_nome_br,
    selecionar_ano,
)

TOP_CATEGORIAS_GRAFICO = 10


def _kpi_card(
    coluna,
    titulo: str,
    valor: str,
    delta: str | None = None,
    *,
    delta_color: str = "normal",
) -> None:
    """`delta_color`: "normal" (verde +/vermelho -), "inverse" (oposto,
    pra despesas), "off" (sempre cinza, pra rótulos textuais como
    Superávit/Déficit)."""
    coluna.metric(titulo, valor, delta=delta, delta_color=delta_color)


def _soma_por_tipo(df: pd.DataFrame, tipo: str) -> float:
    """Soma absoluta do tipo (`despesa`, `receita`, `estorno`).

    Para `receita` inclui estornos (também são entradas reais — crédito
    devolvido pelo banco). Para `despesa` exclui estornos. Tudo em
    módulo (estornos vêm com sinal negativo do banco).
    """
    if df.empty:
        return 0.0
    if tipo == "receita":
        sub = df[df["tipo"].isin(["receita", "estorno"])]
    else:
        sub = df[df["tipo"] == tipo]
    if sub.empty:
        return 0.0
    return float(sub["valor"].abs().sum())


def _formatar_delta(atual: float, anterior: float, label_anterior: str) -> str | None:
    """Formata o delta entre dois valores agregados (mês atual vs anterior)."""
    if anterior == 0 and atual == 0:
        return None
    diff = atual - anterior
    sinal = "+" if diff >= 0 else "-"
    if anterior:
        pct = (diff / anterior) * 100.0
        return (
            f"{sinal}{formatar_brl(abs(diff))[3:]} "
            f"({pct:+.1f}% vs {label_anterior})"
        )
    return f"{sinal}{formatar_brl(abs(diff))[3:]} ({label_anterior} = R$ 0,00)"


def _refs_ordenadas(df: pd.DataFrame) -> list[str]:
    if df.empty:
        return []
    refs = {r for r in df["referencia_mes"].astype(str) if r and r != "nan"}
    return sorted(refs, key=chave_ord_ref_iso)


def _kpis_mes(df: pd.DataFrame, ref: str, ref_anterior: str) -> dict[str, float]:
    """Despesa e receita do mês `ref` (+ deltas vs `ref_anterior`)."""
    cur = df[df["referencia_mes"] == ref]
    prev = (
        df[df["referencia_mes"] == ref_anterior]
        if ref_anterior
        else pd.DataFrame(columns=df.columns)
    )
    return {
        "desp_atual": _soma_por_tipo(cur, "despesa"),
        "rec_atual": _soma_por_tipo(cur, "receita"),
        "desp_ant": _soma_por_tipo(prev, "despesa"),
        "rec_ant": _soma_por_tipo(prev, "receita"),
    }


def _grafico_barras_mensal(df: pd.DataFrame) -> None:
    """Barras mensais: 1 par por mês (Despesa vs Receita)."""
    if df.empty:
        return

    sub = df[df["tipo"].isin(["despesa", "receita", "estorno"])].copy()
    if sub.empty:
        return

    sub["valor_abs"] = sub["valor"].abs()
    # Trata estorno como receita pra agregação visual
    sub["categoria_fluxo"] = sub["tipo"].replace({"estorno": "Receita"}).replace(
        {"despesa": "Despesa", "receita": "Receita"}
    )
    agg = (
        sub.groupby(["referencia_mes", "categoria_fluxo"])["valor_abs"]
        .sum()
        .reset_index()
    )
    agg["referencia_mes"] = agg["referencia_mes"].astype(str)
    agg = agg.sort_values(
        "referencia_mes", key=lambda s: s.map(chave_ord_ref_iso)
    )
    agg["mes_label"] = agg["referencia_mes"].map(ref_para_nome_br)

    fig = px.bar(
        agg,
        x="mes_label",
        y="valor_abs",
        color="categoria_fluxo",
        barmode="group",
        title="Despesas × Receitas por mês",
        labels={
            "mes_label": "Mês",
            "valor_abs": "Total (R$)",
            "categoria_fluxo": "Fluxo",
        },
        color_discrete_map={"Despesa": "#EF553B", "Receita": "#00CC96"},
    )
    fig.update_layout(yaxis_tickprefix="R$ ", yaxis_tickformat=",.0f")
    st.plotly_chart(fig, use_container_width=True)


def _grafico_pizza_categorias(df: pd.DataFrame, top_n: int = TOP_CATEGORIAS_GRAFICO) -> None:
    """Pizza: top N categorias de **despesa** + 'Outras'.

    Receitas ficam fora — categorizar "Salário" e "Dízimo" no mesmo
    gráfico não tem leitura útil.
    """
    if df.empty:
        return
    gastos = df[(df["tipo"] == "despesa") & (df["valor"] > 0)]
    if gastos.empty:
        st.info("Sem despesas no período filtrado.")
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
        title=f"Despesas por categoria (top {top_n})",
        hole=0.35,
    )
    fig.update_traces(textposition="inside", textinfo="percent+label")
    st.plotly_chart(fig, use_container_width=True)


def _maiores_gastos_recentes(df: pd.DataFrame, top_n: int = 10) -> None:
    """Tabela: maiores **despesas** do último mês com dados."""
    if df.empty:
        return
    refs = _refs_ordenadas(df)
    if not refs:
        return
    ultimo = refs[-1]
    sub = df[
        (df["referencia_mes"] == ultimo) & (df["tipo"] == "despesa")
    ].copy()
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
    st.subheader(f"Top {top_n} despesas — {ref_para_nome_br(ultimo)}")
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

    col_ano, _ = st.columns([1, 5])
    with col_ano:
        ano = selecionar_ano(df, key="dashboard_ano")

    df_recorte = filtrar_por_ano(df, ano)
    if df_recorte.empty:
        st.info(
            f"Nenhum lançamento em {ano}. Tente outro ano ou 'Todos os anos'."
        )
        return

    refs = _refs_ordenadas(df_recorte)
    ultimo = refs[-1] if refs else ""
    anterior = refs[-2] if len(refs) >= 2 else ""
    kpis_mes = _kpis_mes(df_recorte, ultimo, anterior)

    desp_ano = _soma_por_tipo(df_recorte, "despesa")
    rec_ano = _soma_por_tipo(df_recorte, "receita")
    saldo_ano = rec_ano - desp_ano

    rotulo_ano = (
        f"no ano {ano}" if ano is not None else "(todo o histórico)"
    )

    # Linha 1: KPIs do mês mais recente
    c1, c2, c3, c4 = st.columns(4)
    label_mes = ref_para_nome_br(ultimo) or "—"
    label_ant = ref_para_nome_br(anterior) or "mês anterior"
    _kpi_card(
        c1,
        f"Despesas em {label_mes}",
        formatar_brl(kpis_mes["desp_atual"]),
        _formatar_delta(kpis_mes["desp_atual"], kpis_mes["desp_ant"], label_ant),
        delta_color="inverse",
    )
    _kpi_card(
        c2,
        f"Receitas em {label_mes}",
        formatar_brl(kpis_mes["rec_atual"]),
        _formatar_delta(kpis_mes["rec_atual"], kpis_mes["rec_ant"], label_ant),
    )
    saldo_mes = kpis_mes["rec_atual"] - kpis_mes["desp_atual"]
    _kpi_card(
        c3,
        f"Saldo de {label_mes}",
        formatar_brl(saldo_mes),
        delta=("Superávit" if saldo_mes >= 0 else "Déficit"),
        delta_color="off",
    )
    _kpi_card(
        c4,
        "Lançamentos no período",
        f"{len(df_recorte):,}".replace(",", "."),
    )

    # Linha 2: KPIs do ano todo
    c5, c6, c7, c8 = st.columns(4)
    _kpi_card(c5, f"Despesas {rotulo_ano}", formatar_brl(desp_ano))
    _kpi_card(c6, f"Receitas {rotulo_ano}", formatar_brl(rec_ano))
    _kpi_card(
        c7,
        f"Saldo {rotulo_ano}",
        formatar_brl(saldo_ano),
        delta=("Superávit" if saldo_ano >= 0 else "Déficit"),
        delta_color="off",
    )
    _kpi_card(
        c8,
        "Cartões / contas distintos",
        f"{df_recorte['conta'].nunique()}",
    )

    st.divider()

    col_a, col_b = st.columns([3, 2])
    with col_a:
        _grafico_barras_mensal(df_recorte)
    with col_b:
        _grafico_pizza_categorias(df_recorte)

    st.divider()
    _maiores_gastos_recentes(df_recorte)


render()
