"""Página Diagnóstico — auditoria de fluxo e vazamentos de dinheiro.

Regras determinísticas sobre lançamentos, recorrentes e tetos. Sem IA.
Dívidas com saldo e juros ficam na página Dívidas.
"""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from analytics.diagnostico import (
    MESES_MINIMOS,
    PAPEL_AUDITORIA,
    PAPEL_VAZAMENTO,
    Achado,
    diagnosticar,
    filtrar_papel,
    plano_simples,
    vazamento_anualizavel,
)
from analytics.orcamento import calcular_progressos
from app.estado import hidratar_globais, persistir_globais
from app.helpers import (
    carregar_lancamentos,
    filtrar_por_ano,
    formatar_brl,
    formatar_brl_md,
    ref_para_nome_br,
    referencias_disponiveis,
    selecionar_ano,
)
from db.repository import listar_escopos_categoria_dict, listar_orcamentos_df

OPCAO_TODAS_PESSOAS = "Todas"

_SEV_ROTULO = {
    "critico": "Crítico",
    "alerta": "Alerta",
    "info": "Info",
}
_SEV_ICONE = {
    "critico": "🔴",
    "alerta": "🟡",
    "info": "ℹ️",
}
_IMPACTO_ROTULO = {
    "baixo": "Baixo",
    "medio": "Médio",
    "alto": "Alto",
}


def _esc(texto: str) -> str:
    """Escapa `$` pra `st.markdown` / `st.caption` não tratar como LaTeX."""
    return texto.replace("$", r"\$")


def _progressos_ultimo_mes(df: pd.DataFrame) -> pd.DataFrame:
    refs = referencias_disponiveis(df)
    if not refs:
        return pd.DataFrame()
    ultimo = refs[-1]
    metas = listar_orcamentos_df(ultimo)
    if metas.empty:
        return pd.DataFrame()
    df_mes = df[df["referencia_mes"] == ultimo]
    overrides = listar_escopos_categoria_dict()
    return calcular_progressos(df_mes, metas, overrides_categoria=overrides)


def _kpis_auditoria(kpis) -> None:
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Receitas", formatar_brl(kpis.receitas))
    c2.metric("Despesas", formatar_brl(kpis.despesas), delta_color="inverse")
    saldo_delta = "Superávit" if kpis.saldo >= 0 else "Déficit"
    c3.metric(
        "Saldo",
        formatar_brl(kpis.saldo),
        delta=saldo_delta,
        delta_color="off",
    )
    if kpis.taxa_poupanca is None:
        c4.metric("Taxa de poupança", "—")
    else:
        c4.metric("Taxa de poupança", f"{kpis.taxa_poupanca * 100:.1f}%")


def _card_achado(achado: Achado) -> None:
    icone = _SEV_ICONE.get(achado.severidade, "")
    sev = _SEV_ROTULO.get(achado.severidade, achado.severidade)
    with st.container(border=True):
        st.markdown(f"**{icone} {achado.titulo}** · {sev}")
        st.caption(_esc(achado.detalhe))
        st.markdown(f"**Como tratar:** {_esc(achado.tratamento)}")
        cols = st.columns(3)
        cols[0].caption(f"Custo mensal {formatar_brl_md(achado.custo_mensal)}")
        cols[1].caption(f"Custo anual {formatar_brl_md(achado.custo_anual)}")
        if achado.economia_mensal_estimada > 0:
            cols[2].caption(
                f"Economia estimada {formatar_brl_md(achado.economia_mensal_estimada)}/mês"
            )
        if achado.evidencias:
            with st.expander("Evidências"):
                visivel = pd.DataFrame(
                    [
                        {
                            "Descrição": e.descricao,
                            "Mês": ref_para_nome_br(e.referencia_mes) or "—",
                            "Valor (R$)": e.valor,
                        }
                        for e in achado.evidencias
                    ]
                )
                st.dataframe(
                    visivel,
                    hide_index=True,
                    use_container_width=True,
                    column_config={
                        "Valor (R$)": st.column_config.NumberColumn(format="R$ %.2f"),
                    },
                )


def _lista_achados(achados: list[Achado], vazio: str) -> None:
    if not achados:
        st.info(vazio)
        return
    ordem = {"critico": 0, "alerta": 1, "info": 2}
    ordenados = sorted(
        achados,
        key=lambda a: (ordem.get(a.severidade, 9), -a.score),
    )
    for achado in ordenados:
        _card_achado(achado)


def _aba_auditoria(diag) -> None:
    _kpis_auditoria(diag.kpis)
    st.divider()
    erros = [
        a
        for a in filtrar_papel(diag.achados, PAPEL_AUDITORIA)
        if a.severidade in {"critico", "alerta"}
    ]
    infos = [a for a in filtrar_papel(diag.achados, PAPEL_AUDITORIA) if a.severidade == "info"]
    st.subheader("O que está errado")
    _lista_achados(erros, "Nenhum erro crítico ou alerta neste recorte.")
    if infos:
        with st.expander(f"Observações ({len(infos)})"):
            for achado in infos:
                _card_achado(achado)

    st.divider()
    plano = plano_simples(diag.achados, n=5)
    st.subheader("Plano mais simples")
    if not plano:
        st.info("Nenhuma ação com economia estimada neste recorte.")
        return
    total = sum(a.economia_mensal_estimada for a in plano)
    st.caption(
        "Cinco movimentos com melhor relação economia × impacto no estilo de vida. "
        f"Se seguir todos, a sobra sobe cerca de {formatar_brl_md(total)}/mês."
    )
    for i, achado in enumerate(plano, start=1):
        st.markdown(
            f"**{i}. {_esc(achado.titulo)}** — {_esc(achado.tratamento)} "
            f"(~{formatar_brl_md(achado.economia_mensal_estimada)}/mês, "
            f"impacto {_IMPACTO_ROTULO[achado.impacto_estilo].lower()})."
        )


def _aba_vazamentos(diag) -> None:
    vazamentos = filtrar_papel(diag.achados, PAPEL_VAZAMENTO)
    vazamentos = sorted(
        vazamentos,
        key=lambda a: (a.score, a.custo_anual, a.economia_mensal_estimada),
        reverse=True,
    )
    anual = vazamento_anualizavel(vazamentos)
    c1, c2 = st.columns(2)
    c1.metric("Vazamento anualizável", formatar_brl(anual))
    c2.metric("Achados", str(len(vazamentos)))

    if not vazamentos:
        st.info("Nenhum vazamento pontuado neste recorte.")
        return

    acionaveis = [a for a in vazamentos if a.economia_mensal_estimada > 0]
    if acionaveis:
        top = acionaveis[:12]
        graf = pd.DataFrame(
            {
                "rotulo": [a.titulo[:42] for a in top],
                "custo_anual": [a.custo_anual for a in top],
            }
        )
        fig = px.bar(
            graf,
            x="custo_anual",
            y="rotulo",
            orientation="h",
            labels={"custo_anual": "Custo anual (R$)", "rotulo": ""},
            title="Onde está o vazamento (anualizado)",
        )
        fig.update_layout(
            yaxis={"categoryorder": "total ascending"},
            height=max(280, 28 * len(top)),
            showlegend=False,
        )
        st.plotly_chart(fig, use_container_width=True)

    tabela = pd.DataFrame(
        [
            {
                "O quê": a.titulo,
                "Custo anual (R$)": a.custo_anual,
                "Impacto": _IMPACTO_ROTULO[a.impacto_estilo],
                "Tratamento": a.tratamento,
                "Economia/mês (R$)": a.economia_mensal_estimada,
                "Severidade": _SEV_ROTULO[a.severidade],
            }
            for a in vazamentos
        ]
    )
    st.dataframe(
        tabela,
        hide_index=True,
        use_container_width=True,
        height=min(480, 80 + 35 * len(tabela)),
        column_config={
            "Custo anual (R$)": st.column_config.NumberColumn(format="R$ %.2f"),
            "Economia/mês (R$)": st.column_config.NumberColumn(format="R$ %.2f"),
        },
    )

    st.subheader("Detalhe")
    rotulos = [f"{_SEV_ICONE.get(a.severidade, '')} {a.titulo}" for a in vazamentos]
    escolha = st.selectbox("Ver evidências de…", rotulos, key="diag_vaz_detalhe")
    achado = vazamentos[rotulos.index(escolha)]
    _card_achado(achado)


def render() -> None:
    st.title("Diagnóstico")
    st.caption(
        "Auditoria de fluxo de caixa e vazamentos de dinheiro, com regras "
        "do próprio app — o que cortar primeiro e como tratar."
    )
    st.info(
        "Análise de **fluxo** (o que entra e o que sai). "
        "Saldo, juros e plano de quitação ficam em **Dívidas**. "
        "Reserva e investimentos ainda não entram nesta versão."
    )

    hidratar_globais()
    df = carregar_lancamentos()
    if df is None or df.empty:
        st.info("Banco vazio. Importe faturas ou a planilha familiar para começar.")
        return

    pessoas = sorted({p for p in df.get("pessoa", pd.Series(dtype=str)) if p})
    col_ano, col_pessoa = st.columns([1, 1])
    with col_ano:
        ano = selecionar_ano(df)
    with col_pessoa:
        opcoes_pessoa = [OPCAO_TODAS_PESSOAS, *pessoas]
        pessoa = st.selectbox("Pessoa", opcoes_pessoa, key="diagnostico_pessoa")

    df = filtrar_por_ano(df, ano)
    if pessoa != OPCAO_TODAS_PESSOAS:
        df = df[df["pessoa"] == pessoa]

    if df.empty:
        rotulo = f"em **{ano}**" if ano is not None else "no recorte"
        extra = f" para **{pessoa}**" if pessoa != OPCAO_TODAS_PESSOAS else ""
        st.info(f"Nenhum lançamento {rotulo}{extra}.")
        persistir_globais()
        return

    progressos = _progressos_ultimo_mes(df)
    diag = diagnosticar(df, progressos=progressos)

    if diag.meses_com_despesa < MESES_MINIMOS:
        st.info(
            "Precisa de pelo menos **2 meses** de despesa no recorte para "
            "montar o diagnóstico. Importe mais faturas ou alargue o ano."
        )
        _kpis_auditoria(diag.kpis)
        persistir_globais()
        return

    aba_aud, aba_vaz = st.tabs(["Auditoria", "Vazamentos"])
    with aba_aud:
        _aba_auditoria(diag)
    with aba_vaz:
        _aba_vazamentos(diag)

    persistir_globais()


render()
