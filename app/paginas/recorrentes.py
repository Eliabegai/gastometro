"""Página Recorrentes — assinaturas, contas fixas, compras e similares.

Classifica cada padrão detectado em um tipo legível (assinatura, conta
fixa, financiamento, compra recorrente, fatura de cartão…) para facilitar
a leitura — não basta olhar só a categoria.
"""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from analytics.recorrentes import (
    TIPOS_RECORRENTE,
    detectar_recorrentes,
    historico_mensal_padrao,
    listar_tipos_recorrente,
    rotulo_tipo_recorrente,
)
from app.helpers import (
    carregar_lancamentos,
    formatar_brl,
    ref_para_nome_br,
)

_CORES_TIPO = {
    "assinatura": "#7C3AED",
    "conta_fixa": "#059669",
    "financiamento": "#DC2626",
    "emprestimo": "#EA580C",
    "fatura_cartao": "#64748B",
    "educacao": "#2563EB",
    "doacao": "#9333EA",
    "compra_recorrente": "#D97706",
    "outro": "#6B7280",
}

_TIPOS_SEM_FATURA = [t["id"] for t in listar_tipos_recorrente() if t["id"] != "fatura_cartao"]


def _filtrar_por_tipo(padroes: pd.DataFrame, tipos: list[str]) -> pd.DataFrame:
    if padroes.empty or not tipos:
        return padroes
    return padroes[padroes["tipo_recorrente"].isin(tipos)].copy()


def _kpis_por_tipo(padroes: pd.DataFrame) -> None:
    if padroes.empty:
        return

    resumo = (
        padroes.groupby("tipo_recorrente", as_index=False)
        .agg(qtde=("chave", "count"), media=("media_mensal", "sum"))
        .sort_values("media", ascending=False)
    )

    cols = st.columns(min(len(resumo), 4))
    for col, (_, row) in zip(cols, resumo.head(4).iterrows(), strict=False):
        tipo_id = row["tipo_recorrente"]
        col.metric(
            rotulo_tipo_recorrente(tipo_id),
            formatar_brl(float(row["media"])),
            delta=f"{int(row['qtde'])} itens",
        )


def _kpis_gerais(padroes: pd.DataFrame) -> None:
    c1, c2, c3 = st.columns(3)
    c1.metric("Padrões no recorte", len(padroes))
    soma = float(padroes["media_mensal"].sum()) if not padroes.empty else 0.0
    c2.metric("Gasto mensal estimado", formatar_brl(soma))
    if not padroes.empty:
        top = padroes.sort_values("media_mensal", ascending=False).iloc[0]
        c3.metric(
            "Maior do recorte",
            formatar_brl(float(top["media_mensal"])),
            delta=rotulo_tipo_recorrente(top["tipo_recorrente"]),
        )
    else:
        c3.metric("Maior do recorte", "—")


def _grafico_top(padroes: pd.DataFrame) -> None:
    if padroes.empty:
        st.info("Nenhum padrão neste recorte.")
        return

    top = padroes.sort_values("media_mensal", ascending=False).head(12).copy()
    top["rotulo"] = top["descricao"].str.slice(0, 32)
    top["tipo"] = top["tipo_recorrente"].map(rotulo_tipo_recorrente)
    top["cor"] = top["tipo_recorrente"].map(_CORES_TIPO).fillna(_CORES_TIPO["outro"])

    fig = px.bar(
        top,
        x="media_mensal",
        y="rotulo",
        orientation="h",
        color="tipo",
        color_discrete_map={
            rotulo_tipo_recorrente(tid): _CORES_TIPO[tid] for tid in TIPOS_RECORRENTE
        },
        labels={"media_mensal": "Média mensal (R$)", "rotulo": "", "tipo": "Tipo"},
        title="Maiores recorrentes do recorte",
    )
    fig.update_layout(yaxis={"categoryorder": "total ascending"}, height=420, showlegend=False)
    st.plotly_chart(fig, use_container_width=True)


def _tabela_padroes(padroes: pd.DataFrame) -> None:
    if padroes.empty:
        st.info("Nenhum padrão neste recorte.")
        return

    visivel = padroes.copy()
    visivel["Tipo"] = visivel["tipo_recorrente"].map(rotulo_tipo_recorrente)
    visivel = visivel.rename(
        columns={
            "descricao": "Descrição",
            "categoria": "Categoria",
            "contas": "Conta(s)",
            "meses": "Meses ativos",
            "qtde": "Lançamentos",
            "total": "Total (R$)",
            "media_mensal": "Média mensal (R$)",
            "variacao_pct": "Variação de preço (%)",
        }
    )
    visivel = visivel.sort_values(["Tipo", "Média mensal (R$)"], ascending=[True, False])
    st.dataframe(
        visivel[
            [
                "Tipo",
                "Descrição",
                "Categoria",
                "Conta(s)",
                "Meses ativos",
                "Média mensal (R$)",
                "Total (R$)",
                "Variação de preço (%)",
            ]
        ],
        use_container_width=True,
        hide_index=True,
        height=420,
        column_config={
            "Média mensal (R$)": st.column_config.NumberColumn(format="R$ %.2f"),
            "Total (R$)": st.column_config.NumberColumn(format="R$ %.2f"),
            "Variação de preço (%)": st.column_config.NumberColumn(
                format="%.1f%%",
                help="Diferença entre o menor e o maior valor cobrado "
                "ao longo dos meses (reajuste de plano, promoção, etc.).",
            ),
        },
    )


def _detalhe_padrao(df: pd.DataFrame, padroes: pd.DataFrame) -> None:
    if padroes.empty:
        return

    opcoes = [
        f"{rotulo_tipo_recorrente(row.tipo_recorrente)} — {row.descricao}"
        for row in padroes.itertuples(index=False)
    ]
    escolha = st.selectbox("Ver histórico mensal de…", opcoes, key="rec_detalhe_sel")
    descricao = escolha.split(" — ", 1)[1]
    linha = padroes.loc[padroes["descricao"] == descricao].iloc[0]

    c1, c2, c3 = st.columns(3)
    c1.metric("Tipo", rotulo_tipo_recorrente(linha["tipo_recorrente"]))
    c2.metric("Média mensal", formatar_brl(float(linha["media_mensal"])))
    c3.metric("Meses ativos", int(linha["meses"]))

    serie = historico_mensal_padrao(df, linha["chave"])
    if serie.empty:
        return

    serie["mes"] = serie["referencia_mes"].map(ref_para_nome_br)
    fig = px.bar(
        serie,
        x="mes",
        y="valor",
        labels={"mes": "Mês", "valor": "Valor (R$)"},
        title=f"Evolução mensal — {descricao}",
        color_discrete_sequence=[_CORES_TIPO.get(linha["tipo_recorrente"], "#6B7280")],
    )
    fig.update_layout(height=320)
    st.plotly_chart(fig, use_container_width=True)


def render() -> None:
    st.title("Recorrentes")
    st.caption(
        "Gastos que se repetem mês a mês, classificados por natureza: "
        "assinaturas, contas fixas, financiamentos, compras habituais "
        "e faturas de cartão."
    )

    df = carregar_lancamentos()
    if df is None or df.empty:
        st.info(
            "Banco vazio. Rode `gastometro` ou importe faturas "
            "para detectar padrões."
        )
        return

    meses_min = st.sidebar.slider(
        "Mínimo de meses (padrão geral)",
        min_value=2,
        max_value=6,
        value=3,
        help="Quantos meses distintos o gasto precisa aparecer. "
        "Assinaturas aceitam 2 meses.",
    )
    ocultar_faturas = st.sidebar.checkbox(
        "Ocultar faturas de cartão",
        value=True,
        help="Faturas agregadas (ex.: 'Fatura Nubank mensal') costumam "
        "dominar o total — oculte para ver assinaturas e contas fixas.",
    )

    padroes = detectar_recorrentes(df, meses_min=meses_min)
    if padroes.empty:
        st.info("Nenhum padrão recorrente detectado com os critérios atuais.")
        return

    tipos_opts = listar_tipos_recorrente()
    tipos_label = {t["id"]: rotulo_tipo_recorrente(t["id"]) for t in tipos_opts}
    tipos_default = _TIPOS_SEM_FATURA if ocultar_faturas else [t["id"] for t in tipos_opts]
    tipos_sel = st.sidebar.multiselect(
        "Tipos visíveis",
        options=[t["id"] for t in tipos_opts],
        default=tipos_default,
        format_func=lambda tid: tipos_label[tid],
    )

    padroes_visiveis = _filtrar_por_tipo(padroes, tipos_sel)

    _kpis_gerais(padroes_visiveis)
    _kpis_por_tipo(padroes_visiveis)
    st.divider()

    abas = st.tabs(
        [
            rotulo_tipo_recorrente(t["id"])
            for t in tipos_opts
            if t["id"] in tipos_sel
        ]
        + ["📋 Todos do recorte"]
    )

    for aba, tipo_id in zip(abas[:-1], [t["id"] for t in tipos_opts if t["id"] in tipos_sel], strict=False):
        with aba:
            sub = padroes_visiveis[padroes_visiveis["tipo_recorrente"] == tipo_id]
            col_tab, col_graf = st.columns([3, 2])
            with col_tab:
                _tabela_padroes(sub)
            with col_graf:
                _grafico_top(sub)

    with abas[-1]:
        col_tab, col_graf = st.columns([3, 2])
        with col_tab:
            _tabela_padroes(padroes_visiveis)
        with col_graf:
            _grafico_top(padroes_visiveis)

    st.divider()
    st.subheader("Histórico por padrão")
    _detalhe_padrao(df, padroes_visiveis)


render()
