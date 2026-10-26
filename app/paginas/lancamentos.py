"""Página Lançamentos — exploração / filtragem da tabela completa.

A tabela respeita 2 níveis de filtro:

1. **Período global** (ano + modo + mês) compartilhado com Dashboard,
   Categorias e Faturas. Se você selecionou "Maio/2024" no Dashboard,
   essa tela já abre filtrada por Maio/2024. Um banner no topo
   informa o recorte ativo.

2. **Filtros locais** na sidebar (pessoa, conta, categoria, tipo,
   referência extra, data, busca por texto) — aplicados em cima do
   recorte global.

Tudo é persistido na URL (`?ano=2024&mes=2024-05&lanc_pessoas=Eliabe|Ana&...`)
e sobrevive a F5 / abertura de novas abas — link compartilhável.
O botão "🧹 Limpar filtros" na sidebar zera os locais; pra limpar
o período global, use o botão equivalente no Dashboard/Categorias.
"""

from __future__ import annotations

import streamlit as st

from analytics.escopo import ESCOPO_CASAL, ESCOPO_PESSOAL, marcar_escopo
from analytics.fluxo import marcar_previsto, resumir_fluxo
from analytics.recorrentes import marcar_recorrentes, rotulo_tipo_recorrente
from app.estado import (
    CHAVES_GLOBAIS,
    CHAVES_LANCAMENTOS,
    MAPA_GLOBAIS,
    MAPA_LANCAMENTOS,
    botao_limpar_filtros,
    hidratar_globais,
    hidratar_lancamentos,
    persistir_globais,
    persistir_lancamentos,
)
from app.helpers import (
    aplicar_filtros,
    carregar_lancamentos,
    filtrar_por_periodo_global,
    formatar_brl,
    formatar_brl_md,
    periodo_global_ativo,
    ref_para_nome_br,
    rotulo_periodo_global,
    sidebar_filtros_lancamentos,
)
from app.visao import alternar_resumo, colunas
from db.repository import listar_escopos_categoria_dict


def _resumo(df, resumido: bool = False) -> None:
    """Contagem + despesas líquidas + renda + saldo (regras de `analytics.fluxo`).

    Não existe mais "Soma": somar despesa com receita não significa nada.
    """
    fluxo = resumir_fluxo(df)
    c1, c2, c3, c4 = colunas(4, resumido)
    c1.metric("Lançamentos filtrados", f"{len(df):,}".replace(",", "."))
    c2.metric("Despesas (líquidas)", formatar_brl(fluxo.despesas))
    c3.metric("Renda", formatar_brl(fluxo.renda))
    c4.metric(
        "Saldo (renda − despesas)",
        formatar_brl(fluxo.saldo),
        delta=("Superávit" if fluxo.saldo >= 0 else "Déficit"),
        delta_color="off",
    )
    notas: list[str] = []
    if fluxo.estornos > 0:
        notas.append(f"Estornos de {formatar_brl_md(fluxo.estornos)} abatidos das despesas.")
    if fluxo.entradas_credito > 0:
        notas.append(
            f"Empréstimos recebidos ({formatar_brl_md(fluxo.entradas_credito)}) "
            "não contam como renda."
        )
    if "previsto" in df.columns and bool(df["previsto"].any()):
        notas.append("Há meses previstos (planilha, sem fatura) neste recorte.")
    if notas:
        st.caption(" ".join(notas))


COLUNAS_TECNICAS = ("Fonte", "Arquivo origem", "Grupo recorrente")


COLUNAS_RESUMO = ("Data", "Descrição", "Categoria", "Valor (R$)")


def _tabela(df, *, mostrar_tecnicas: bool = False, resumido: bool = False) -> None:
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
            "eh_recorrente": "Recorrente",
            "grupo_recorrente": "Grupo recorrente",
            "tipo_recorrente": "Tipo recorrente",
            "escopo": "Escopo",
            "previsto": "Situação",
        }
    )
    if "Situação" in visivel.columns:
        visivel["Situação"] = visivel["Situação"].map({True: "Previsto", False: ""})
    if "Escopo" in visivel.columns:
        visivel["Escopo"] = visivel["Escopo"].map(
            {"casal": "Casal", "pessoal": "Pessoal"}
        ).fillna("")
    if "Recorrente" in visivel.columns:
        # 📌 compromisso fixo · 🔁 hábito que se repete
        if "eh_fixo" in visivel.columns:
            visivel["Recorrente"] = [
                ("📌" if fixo else "🔁") if rec else ""
                for rec, fixo in zip(visivel["Recorrente"], visivel["eh_fixo"], strict=True)
            ]
        else:
            visivel["Recorrente"] = visivel["Recorrente"].map(
                {True: "🔁", False: ""}
            )
    if "Tipo recorrente" in visivel.columns:
        visivel["Tipo recorrente"] = visivel["Tipo recorrente"].map(
            lambda t: rotulo_tipo_recorrente(t) if t else ""
        )
    colunas_ordem = [
        "Data",
        "Referência",
        "Situação",
        "Recorrente",
        "Tipo recorrente",
        "Descrição",
        "Grupo recorrente",
        "Categoria",
        "Escopo",
        "Cartão / Conta",
        "Pessoa",
        "Parcela",
        "Cidade",
        "Valor (R$)",
        "Tipo",
        "Fonte",
        "Arquivo origem",
    ]
    if resumido:
        colunas_ordem = [c for c in colunas_ordem if c in COLUNAS_RESUMO]
    elif not mostrar_tecnicas:
        colunas_ordem = [c for c in colunas_ordem if c not in COLUNAS_TECNICAS]
    visivel = visivel[[c for c in colunas_ordem if c in visivel.columns]]

    st.dataframe(
        visivel,
        width="stretch",
        hide_index=True,
        height=420 if resumido else 560,
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


def _banner_periodo_global() -> None:
    """Banner informativo no topo da página: mostra o recorte ativo do
    filtro global (ano/mês) com link pra apagar. No-op se não há
    período definido (todo o histórico)."""
    if not periodo_global_ativo():
        return
    rotulo = rotulo_periodo_global()
    col_msg, col_btn = st.columns([5, 1])
    with col_msg:
        st.info(
            f"📅 Mostrando **{rotulo}** — filtro definido no Dashboard. "
            "Os filtros da sidebar (pessoa, conta, busca…) atuam em "
            "cima desse recorte.",
            icon="🔎",
        )
    with col_btn:
        st.markdown("&nbsp;", unsafe_allow_html=True)
        if botao_limpar_filtros(
            CHAVES_GLOBAIS + ("filtro_global_mes__widget",),
            MAPA_GLOBAIS.values(),
            key="btn_limpar_periodo_lanc",
            label="🧹 Limpar período",
            rotulo_auxiliar="Volta a mostrar todo o histórico",
        ):
            st.rerun()


def render() -> None:
    st.title("Lançamentos")
    resumido = alternar_resumo()

    # Hidrata tanto globais (ano/mes/modo) quanto locais (filtros da
    # sidebar) — globais vêm primeiro porque afetam quais opções
    # aparecem na sidebar (depois do recorte global).
    hidratar_globais()
    hidratar_lancamentos()

    df = carregar_lancamentos()
    if df is None or df.empty:
        st.info(
            "Banco vazio. Rode `gastometro` ou "
            "`python -m imports.migrar_excel_legado`."
        )
        return

    _banner_periodo_global()

    # 1. Aplica o período global PRIMEIRO. Resultado vira o universo
    #    cuja sidebar mostra os filtros locais (opções vêm só dos
    #    lançamentos do recorte — não polui dropdown com pessoas /
    #    categorias que não aparecem no período).
    df_periodo = filtrar_por_periodo_global(df)

    filtros = sidebar_filtros_lancamentos(df_periodo)
    texto_busca = filtros.get("texto")
    sub = aplicar_filtros(df_periodo, **{**filtros, "texto": None})

    ocultar_previstos = st.sidebar.checkbox(
        "Ocultar meses previstos",
        value=False,
        key="f_ocultar_previstos",
        help="Previsto = mês futuro vindo da planilha, ainda sem fatura.",
    )
    so_recorrentes = st.sidebar.checkbox(
        "Só recorrentes",
        value=False,
        help="Mostra apenas lançamentos que fazem parte de um "
        "padrão detectado (assinatura, conta fixa, etc.).",
    )
    escopo_opts = ["Todos", "Casal", "Pessoal"]
    escopo_filtro = st.sidebar.selectbox(
        "Escopo (casal / pessoal)",
        escopo_opts,
        key="f_escopo",
        help="Casal = gastos conjuntos; Pessoal = gastos do titular do cartão.",
    )

    overrides_escopo = listar_escopos_categoria_dict()
    df_marcado = marcar_escopo(
        marcar_recorrentes(sub), overrides_categoria=overrides_escopo
    )
    if texto_busca:
        mask = df_marcado["descricao"].astype(str).str.contains(
            texto_busca, case=False, na=False
        )
        mask = mask | df_marcado["grupo_recorrente"].astype(str).str.contains(
            texto_busca, case=False, na=False
        )
        df_marcado = df_marcado[mask]
    if so_recorrentes:
        df_marcado = df_marcado[df_marcado["eh_recorrente"]]
    if escopo_filtro == "Casal":
        df_marcado = df_marcado[df_marcado["escopo"] == ESCOPO_CASAL]
    elif escopo_filtro == "Pessoal":
        df_marcado = df_marcado[df_marcado["escopo"] == ESCOPO_PESSOAL]
    df_marcado = marcar_previsto(df_marcado)
    if ocultar_previstos:
        df_marcado = df_marcado[~df_marcado["previsto"]]
    sub = df_marcado

    if filtros.get("data_inicio") and filtros.get("data_fim"):
        ini = filtros["data_inicio"]
        fim = filtros["data_fim"]
        st.caption(
            f"Período filtrado: **{ini.strftime('%d/%m/%Y')}** "
            f"a **{fim.strftime('%d/%m/%Y')}** — ajuste em **Filtros → "
            f"Período** na sidebar."
        )

    # Botão "Limpar filtros" no rodapé da sidebar — perto dos filtros
    # que ele reseta. Inclui a key auxiliar de refs (label↔iso).
    st.sidebar.divider()
    if botao_limpar_filtros(
        list(CHAVES_LANCAMENTOS) + ["f_refs__widget", "f_ocultar_previstos"],
        list(MAPA_LANCAMENTOS.values()),
        key="btn_limpar_lanc",
        rotulo_auxiliar="Zera pessoa, conta, categoria, tipo, busca e período",
        na_sidebar=True,
    ):
        st.rerun()

    _resumo(sub, resumido)
    st.divider()
    mostrar_tecnicas = False
    if not resumido:
        mostrar_tecnicas = st.toggle(
            "Mostrar colunas técnicas (fonte, arquivo, grupo)",
            value=False,
            key="lanc_colunas_tecnicas",
        )
    _tabela(sub, mostrar_tecnicas=mostrar_tecnicas, resumido=resumido)
    _exportar_csv(sub)

    persistir_lancamentos()
    persistir_globais()


render()
