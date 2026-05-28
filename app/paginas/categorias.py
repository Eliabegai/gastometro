"""Página Categorias — overview + edição de overrides + recategorizar.

Funcionalidades:
  - Filtro de período (Ano + Visão Ano inteiro/Mensal + Mês) idêntico
    ao do Dashboard. Todas as tabelas/listas dessa página respeitam
    o recorte selecionado.
  - Lista de categorias existentes com soma acumulada no período.
  - Top descrições em 'Outros Gastos' (não categorizadas).
  - Editor de overrides: para cada descrição, escolher categoria;
    salvar grava `OverrideCategoria` no banco.
  - Botão "Recategorizar histórico" — re-aplica overrides + dicionário
    em todos os lançamentos (essa ação ignora o filtro, é global).

Quem prefere o fluxo de Excel pode continuar editando a coluna
`Categoria` no XLSX e rodando `gastometro aprender`.
"""

from __future__ import annotations

import streamlit as st
from sqlmodel import select

from app.helpers import (
    carregar_lancamentos,
    filtrar_por_ano,
    invalidar_cache,
    ref_para_nome_br,
    selecionar_ano,
    selecionar_mes,
)
from db.engine import get_session
from db.models import Categoria
from db.repository import (
    listar_overrides_dict,
    recategorizar_todos,
    salvar_override,
)

MODO_ANUAL = "Ano inteiro"
MODO_MENSAL = "Mensal"


@st.cache_data(ttl=30, show_spinner=False)
def _categorias_disponiveis() -> list[str]:
    """Nomes de todas as categorias do banco (despesa + receita)."""
    with get_session() as session:
        nomes = session.exec(select(Categoria.nome)).all()
    return sorted(nomes)


def _aplicar_filtros(df):
    """Renderiza os controles de período no topo e devolve `(df_recorte,
    rotulo_periodo)`.

    Mesma UX do Dashboard: Ano (selectbox) + Visão (Ano inteiro × Mensal,
    radio) + Mês (selectbox, só no modo mensal).
    """
    col_ano, col_modo, col_mes = st.columns([1, 1, 1])
    with col_ano:
        ano = selecionar_ano(df, key="categorias_ano")

    df_recorte = filtrar_por_ano(df, ano)

    with col_modo:
        modo = st.radio(
            "Visão",
            [MODO_ANUAL, MODO_MENSAL],
            index=0,
            horizontal=True,
            key="categorias_modo",
        )

    ref_selecionada: str | None = None
    if modo == MODO_MENSAL:
        with col_mes:
            ref_selecionada = selecionar_mes(df_recorte, key="categorias_mes")

    rotulo = (
        f"em {ano}" if ano is not None else "no histórico inteiro"
    )
    if modo == MODO_MENSAL and ref_selecionada:
        df_recorte = df_recorte[df_recorte["referencia_mes"] == ref_selecionada]
        rotulo = f"em {ref_para_nome_br(ref_selecionada)}"

    return df_recorte, rotulo


def _resumo_categorias(df, rotulo_periodo: str) -> None:
    if df.empty:
        return
    agg = (
        df[df["tipo"] == "despesa"]
        .groupby("categoria")["valor"]
        .agg(soma="sum", qtde="count")
        .reset_index()
    )
    if agg.empty:
        st.info(f"Nenhuma despesa {rotulo_periodo}.")
        return
    agg["ticket_medio"] = agg["soma"] / agg["qtde"]
    agg = agg.sort_values("soma", ascending=False)
    agg = agg.rename(
        columns={
            "categoria": "Categoria",
            "soma": "Total (R$)",
            "qtde": "Lançamentos",
            "ticket_medio": "Ticket médio (R$)",
        }
    )
    st.subheader(f"Categorias por gasto {rotulo_periodo}")
    st.dataframe(
        agg,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Total (R$)": st.column_config.NumberColumn(format="R$ %.2f"),
            "Ticket médio (R$)": st.column_config.NumberColumn(
                format="R$ %.2f"
            ),
            "Lançamentos": st.column_config.NumberColumn(format="%d"),
        },
    )


def _top_outros_gastos(
    df, rotulo_periodo: str, top_n: int = 30
) -> None:
    """Top descrições caídas em `Outros Gastos`. Editor rápido pra categorizar."""
    sub = df[(df["categoria"] == "Outros Gastos") & (df["tipo"] == "despesa")]
    if sub.empty:
        st.info(
            f"Nenhuma descrição em 'Outros Gastos' {rotulo_periodo} "
            "(todas categorizadas ou nada no recorte)."
        )
        return

    agg = (
        sub.groupby("descricao")["valor"]
        .agg(soma="sum", qtde="count")
        .reset_index()
        .sort_values("soma", ascending=False)
        .head(top_n)
    )

    categorias = _categorias_disponiveis()
    st.subheader(
        f"Top {len(agg)} 'Outros Gastos' {rotulo_periodo} (categorize rápido)"
    )
    st.caption(
        "Escolha a categoria certa e clique em **Salvar overrides** abaixo. "
        "A re-categorização do histórico roda ao final."
    )

    edits = st.data_editor(
        agg.assign(nova_categoria=""),
        column_config={
            "descricao": st.column_config.TextColumn(
                "Descrição", disabled=True, width="large"
            ),
            "soma": st.column_config.NumberColumn(
                "Total (R$)", format="R$ %.2f", disabled=True
            ),
            "qtde": st.column_config.NumberColumn(
                "Qtde.", disabled=True, width="small"
            ),
            "nova_categoria": st.column_config.SelectboxColumn(
                "Categoria",
                options=[""] + categorias,
                required=False,
            ),
        },
        hide_index=True,
        use_container_width=True,
        key="editor_outros",
    )

    if st.button("💾 Salvar overrides", type="primary", key="btn_salvar"):
        salvos = 0
        for _, row in edits.iterrows():
            descricao = str(row["descricao"]).strip()
            nova = str(row["nova_categoria"]).strip()
            if not descricao or not nova:
                continue
            salvar_override(descricao, nova)
            salvos += 1
        if salvos == 0:
            st.warning("Nenhuma linha tinha nova categoria preenchida.")
        else:
            invalidar_cache()
            _categorias_disponiveis.clear()
            with st.spinner("Re-categorizando o histórico…"):
                res = recategorizar_todos()
            st.success(
                f"{salvos} override(s) salvos. "
                f"{res['mudados']} de {res['total']} lançamentos atualizados."
            )
            st.rerun()


def _overrides_existentes() -> None:
    overrides = listar_overrides_dict()
    if not overrides:
        st.info("Nenhum override manual registrado ainda.")
        return

    st.subheader(f"Overrides ativos ({len(overrides)})")
    st.caption(
        "Descrições normalizadas (sem acento, lowercase) e a categoria "
        "atribuída. Pra remover, sobrescreva no editor de cima."
    )
    import pandas as pd

    df = pd.DataFrame(
        [
            {"Descrição normalizada": d, "Categoria": c}
            for d, c in sorted(overrides.items())
        ]
    )
    st.dataframe(df, use_container_width=True, hide_index=True, height=300)


def _adicionar_manual() -> None:
    """Form pra inserir um override sem precisar da tabela de Outros Gastos."""
    st.subheader("Adicionar override manual")
    categorias = _categorias_disponiveis()
    with st.form("form_override_manual"):
        descricao = st.text_input(
            "Descrição (como aparece na fatura)",
            placeholder="ex: G B Tucurivi Comercio",
        )
        categoria = st.selectbox("Categoria", options=categorias, index=0)
        ok = st.form_submit_button("Adicionar override", type="primary")

    if ok and descricao.strip() and categoria:
        salvar_override(descricao.strip(), categoria)
        invalidar_cache()
        with st.spinner("Re-categorizando o histórico…"):
            res = recategorizar_todos()
        st.success(
            f"Override salvo. {res['mudados']} de {res['total']} "
            f"lançamentos atualizados."
        )
        st.rerun()


def _botao_recategorizar() -> None:
    st.subheader("Forçar re-categorização")
    st.caption(
        "Usar quando você editou regras em `categorias.py` (dicionário fixo) "
        "e quer propagar pro histórico inteiro."
    )
    if st.button("🔄 Re-categorizar todos os lançamentos"):
        invalidar_cache()
        with st.spinner("Re-aplicando regras…"):
            res = recategorizar_todos()
        st.success(
            f"{res['mudados']} de {res['total']} lançamentos atualizados."
        )
        st.rerun()


def render() -> None:
    st.title("Categorias")

    df = carregar_lancamentos()
    if df is None or df.empty:
        st.info(
            "Banco vazio. Rode `gastometro` ou "
            "`python -m imports.migrar_excel_legado`."
        )
        return

    df_recorte, rotulo_periodo = _aplicar_filtros(df)
    if df_recorte.empty:
        st.info(
            f"Nenhum lançamento {rotulo_periodo}. Ajuste o filtro pra ver "
            "as categorias."
        )
        st.divider()
        # Mesmo sem dados no recorte, mostramos overrides/recategorizar
        # — são ações globais, não dependem do período.
        tabs = st.tabs(["Overrides ativos", "Adicionar manual", "Re-categorizar"])
        with tabs[0]:
            _overrides_existentes()
        with tabs[1]:
            _adicionar_manual()
        with tabs[2]:
            _botao_recategorizar()
        return

    _resumo_categorias(df_recorte, rotulo_periodo)
    st.divider()

    tabs = st.tabs(
        ["Outros Gastos", "Overrides ativos", "Adicionar manual", "Re-categorizar"]
    )
    with tabs[0]:
        _top_outros_gastos(df_recorte, rotulo_periodo)
    with tabs[1]:
        _overrides_existentes()
    with tabs[2]:
        _adicionar_manual()
    with tabs[3]:
        _botao_recategorizar()


render()
