"""Página Categorias — overview + edição de overrides + recategorizar.

Funcionalidades:
  - Lista de categorias existentes com soma acumulada (link mental
    pro Dashboard / Lançamentos).
  - Top descrições em 'Outros Gastos' (não categorizadas).
  - Editor de overrides: para cada descrição, escolher categoria;
    salvar grava `OverrideCategoria` no banco.
  - Botão "Recategorizar histórico" — re-aplica overrides + dicionário
    em todos os lançamentos.

Quem prefere o fluxo de Excel pode continuar editando a coluna
`Categoria` no XLSX e rodando `gastometro aprender`.
"""

from __future__ import annotations

import streamlit as st
from sqlmodel import select

from app.helpers import carregar_lancamentos, invalidar_cache
from db.engine import get_session
from db.models import Categoria
from db.repository import (
    listar_overrides_dict,
    recategorizar_todos,
    salvar_override,
)


@st.cache_data(ttl=30, show_spinner=False)
def _categorias_disponiveis() -> list[str]:
    """Nomes de todas as categorias do banco (despesa + receita)."""
    with get_session() as session:
        nomes = session.exec(select(Categoria.nome)).all()
    return sorted(nomes)


def _resumo_categorias(df) -> None:
    if df.empty:
        return
    agg = (
        df[df["valor"] > 0]
        .groupby("categoria")["valor"]
        .agg(["sum", "count"])
        .reset_index()
        .sort_values("sum", ascending=False)
    )
    agg = agg.rename(
        columns={
            "categoria": "Categoria",
            "sum": "Total acumulado (R$)",
            "count": "Qtde. lançamentos",
        }
    )
    st.subheader("Categorias por gasto acumulado")
    st.dataframe(
        agg,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Total acumulado (R$)": st.column_config.NumberColumn(
                format="R$ %.2f"
            ),
        },
    )


def _top_outros_gastos(df, top_n: int = 30) -> None:
    """Top descrições caídas em `Outros Gastos`. Editor rápido pra categorizar."""
    sub = df[(df["categoria"] == "Outros Gastos") & (df["valor"] > 0)]
    if sub.empty:
        st.info(
            "Nenhuma descrição em 'Outros Gastos' (todas estão categorizadas)."
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
    st.subheader(f"Top {len(agg)} 'Outros Gastos' (categorize rápido)")
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

    _resumo_categorias(df)
    st.divider()

    tabs = st.tabs(["Outros Gastos", "Overrides ativos", "Adicionar manual", "Re-categorizar"])
    with tabs[0]:
        _top_outros_gastos(df)
    with tabs[1]:
        _overrides_existentes()
    with tabs[2]:
        _adicionar_manual()
    with tabs[3]:
        _botao_recategorizar()


render()
