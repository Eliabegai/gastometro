"""Página Casal — comparativo detalhado de gastos conjuntos vs pessoais."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from analytics.escopo import (
    ESCOPO_CASAL,
    ESCOPO_PESSOAL,
    comparativo_pessoas,
    historico_escopo_mensal,
    marcar_escopo,
    referencia_mes_anterior,
    resumo_escopo_despesas,
    resumo_por_categoria_escopo,
)
from app.estado import (
    CHAVE_MES,
    CHAVES_GLOBAIS,
    MAPA_GLOBAIS,
    botao_limpar_filtros,
    hidratar_globais,
    persistir_globais,
)
from app.helpers import (
    carregar_lancamentos,
    chave_ord_ref_iso,
    filtrar_por_ano,
    formatar_brl,
    ref_para_nome_br,
    selecionar_ano,
    selecionar_mes,
)
from db.repository import listar_escopos_categoria_dict


def _kpis_mes(
    df_mes: pd.DataFrame,
    overrides: dict[str, str],
    *,
    df_ano: pd.DataFrame | None = None,
    ref_ant: str | None = None,
) -> None:
    marcado = marcar_escopo(df_mes, overrides_categoria=overrides)
    resumo = resumo_escopo_despesas(marcado)
    total = resumo["total"] or 0.0
    pct_casal = (resumo["casal"] / total * 100.0) if total else 0.0

    ant_casal = ant_pessoal = 0.0
    if ref_ant and df_ano is not None:
        df_ant = df_ano[df_ano["referencia_mes"] == ref_ant]
        if not df_ant.empty:
            r_ant = resumo_escopo_despesas(
                marcar_escopo(df_ant, overrides_categoria=overrides)
            )
            ant_casal, ant_pessoal = r_ant["casal"], r_ant["pessoal"]

    def _delta(atual: float, anterior: float) -> str | None:
        if anterior == 0 and atual == 0:
            return None
        diff = atual - anterior
        sinal = "+" if diff >= 0 else "-"
        if anterior:
            pct = diff / anterior * 100.0
            return f"{sinal}{formatar_brl(abs(diff))[3:]} ({pct:+.1f}%)"
        return f"{sinal}{formatar_brl(abs(diff))[3:]}"

    c1, c2, c3, c4 = st.columns(4)
    c1.metric(
        "Gastos do casal",
        formatar_brl(resumo["casal"]),
        delta=_delta(resumo["casal"], ant_casal) if ref_ant else None,
        delta_color="inverse",
    )
    c2.metric(
        "Gastos pessoais",
        formatar_brl(resumo["pessoal"]),
        delta=_delta(resumo["pessoal"], ant_pessoal) if ref_ant else None,
        delta_color="inverse",
    )
    c3.metric("Total despesas", formatar_brl(total))
    c4.metric("Casal no total", f"{pct_casal:.0f}%", delta_color="off")


def _grafico_historico(df_ano: pd.DataFrame, overrides: dict[str, str]) -> None:
    hist = historico_escopo_mensal(df_ano, overrides_categoria=overrides)
    if hist.empty:
        st.info("Sem despesas no ano selecionado.")
        return

    hist = hist.copy()
    hist["mes"] = hist["referencia_mes"].map(ref_para_nome_br)
    long = hist.melt(
        id_vars=["mes", "referencia_mes"],
        value_vars=["casal", "pessoal"],
        var_name="escopo",
        value_name="valor",
    )
    long["escopo"] = long["escopo"].map({"casal": "Casal", "pessoal": "Pessoal"})

    fig = px.bar(
        long,
        x="mes",
        y="valor",
        color="escopo",
        barmode="stack",
        title="Despesas casal vs pessoal por mês",
        labels={"mes": "Mês", "valor": "Total (R$)", "escopo": "Escopo"},
        color_discrete_map={"Casal": "#2563EB", "Pessoal": "#F59E0B"},
    )
    fig.update_layout(yaxis_tickprefix="R$ ", yaxis_tickformat=",.0f")
    st.plotly_chart(fig, use_container_width=True)


def _grafico_pessoas(df_mes: pd.DataFrame, overrides: dict[str, str]) -> None:
    comp = comparativo_pessoas(df_mes, overrides_categoria=overrides)
    if comp.empty:
        st.info("Sem gastos pessoais neste mês.")
        return

    fig = px.bar(
        comp,
        x="pessoa",
        y="total",
        text=comp["participacao_pct"].map(lambda p: f"{p:.0f}%"),
        title="Gastos pessoais por titular",
        labels={"pessoa": "Pessoa", "total": "Total (R$)"},
        color_discrete_sequence=["#F59E0B"],
    )
    fig.update_traces(textposition="outside")
    fig.update_layout(yaxis_tickprefix="R$ ", yaxis_tickformat=",.0f")
    st.plotly_chart(fig, use_container_width=True)


def _tabelas_categorias(df_mes: pd.DataFrame, overrides: dict[str, str]) -> None:
    col_a, col_b = st.columns(2)
    with col_a:
        st.subheader("Top categorias — casal")
        casal = resumo_por_categoria_escopo(
            df_mes, ESCOPO_CASAL, overrides_categoria=overrides
        )
        if casal.empty:
            st.caption("Nenhuma despesa conjunta.")
        else:
            st.dataframe(
                casal.rename(columns={"total": "Total (R$)", "qtde": "Lançamentos"}),
                hide_index=True,
                use_container_width=True,
                column_config={
                    "Total (R$)": st.column_config.NumberColumn(format="R$ %.2f"),
                },
            )
    with col_b:
        st.subheader("Top categorias — pessoal")
        pessoal = resumo_por_categoria_escopo(
            df_mes, ESCOPO_PESSOAL, overrides_categoria=overrides
        )
        if pessoal.empty:
            st.caption("Nenhuma despesa pessoal.")
        else:
            st.dataframe(
                pessoal.rename(columns={"total": "Total (R$)", "qtde": "Lançamentos"}),
                hide_index=True,
                use_container_width=True,
                column_config={
                    "Total (R$)": st.column_config.NumberColumn(format="R$ %.2f"),
                },
            )


def render() -> None:
    st.title("Casal")
    st.caption("Comparativo de gastos conjuntos e pessoais de cada titular.")

    hidratar_globais()
    df = carregar_lancamentos()
    if df is None or df.empty:
        st.info("Banco vazio. Importe faturas para começar.")
        return

    col_ano, col_mes, col_limpar = st.columns([1, 1, 0.7])
    with col_ano:
        ano = selecionar_ano(df)
    df_ano = filtrar_por_ano(df, ano)
    with col_mes:
        ref = selecionar_mes(df_ano) or ""
    with col_limpar:
        st.markdown("&nbsp;", unsafe_allow_html=True)
        if botao_limpar_filtros(
            CHAVES_GLOBAIS + (f"{CHAVE_MES}__widget",),
            MAPA_GLOBAIS.values(),
            key="btn_limpar_casal",
        ):
            st.rerun()

    overrides = listar_escopos_categoria_dict()

    if ref:
        df_mes = df_ano[df_ano["referencia_mes"] == ref]
        ref_ant = referencia_mes_anterior(ref)
        st.subheader(ref_para_nome_br(ref))
        _kpis_mes(df_mes, overrides, df_ano=df_ano, ref_ant=ref_ant)
        st.divider()
        col_g1, col_g2 = st.columns(2)
        with col_g1:
            _grafico_pessoas(df_mes, overrides)
        with col_g2:
            comp = comparativo_pessoas(df_mes, overrides_categoria=overrides)
            if not comp.empty:
                st.subheader("Participação pessoal")
                for _, row in comp.iterrows():
                    st.write(
                        f"**{row['pessoa']}**: {formatar_brl(float(row['total']))} "
                        f"({row['participacao_pct']:.0f}% do pessoal)"
                    )
        st.divider()
        _tabelas_categorias(df_mes, overrides)
        st.divider()

    st.subheader("Evolução no ano")
    _grafico_historico(df_ano, overrides)

    if ref:
        refs = sorted(
            df_ano["referencia_mes"].dropna().unique().tolist(),
            key=chave_ord_ref_iso,
        )
        if ref in refs and refs.index(ref) > 0:
            st.caption(
                f"Deltas comparados com {ref_para_nome_br(refs[refs.index(ref) - 1])}."
            )

    persistir_globais()


render()
