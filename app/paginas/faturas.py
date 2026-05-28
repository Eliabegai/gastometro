"""Página Faturas — lista de PDFs processados, com drill-down.

Tabela principal com cabeçalhos das faturas (1 por arquivo PDF). Ao
selecionar uma linha, mostra os lançamentos daquela fatura na parte
de baixo.

A lista respeita o **período global** (ano + mês) compartilhado com
Dashboard, Lançamentos e Categorias. Se você selecionou Maio/2024 no
Dashboard, essa tela já abre mostrando só as faturas dessa referência.
Botão "🧹 Limpar período" no topo apaga o recorte.
"""

from __future__ import annotations

import streamlit as st

from app.estado import (
    CHAVES_GLOBAIS,
    MAPA_GLOBAIS,
    botao_limpar_filtros,
    hidratar_globais,
    persistir_globais,
)
from app.helpers import (
    ano_global_atual,
    carregar_faturas,
    carregar_lancamentos,
    chave_ord_ref_iso,
    formatar_brl,
    mes_global_atual,
    modo_global_atual,
    periodo_global_ativo,
    ref_para_nome_br,
    rotulo_periodo_global,
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


def _filtrar_faturas_por_periodo_global(df):
    """Aplica ano/mês globais ao DataFrame de faturas.

    Faturas têm `referencia_mes` (ISO `YYYY-MM`); pra filtrar por ano
    extraímos o prefixo. Idempotente — se nenhum global estiver setado,
    devolve `df` intocado.
    """
    if df is None or df.empty:
        return df

    ano = ano_global_atual()
    if ano is not None and "referencia_mes" in df.columns:
        df = df[df["referencia_mes"].astype(str).str.startswith(f"{ano}-")]

    from app.helpers import MODO_GLOBAL_MENSAL

    if modo_global_atual() == MODO_GLOBAL_MENSAL:
        mes = mes_global_atual()
        if mes and "referencia_mes" in df.columns:
            df = df[df["referencia_mes"] == mes]

    return df


def _banner_periodo_global() -> None:
    """Banner com o recorte ativo + botão pra apagar (mesma UX de Lançamentos)."""
    if not periodo_global_ativo():
        return
    rotulo = rotulo_periodo_global()
    col_msg, col_btn = st.columns([5, 1])
    with col_msg:
        st.info(
            f"📅 Mostrando faturas de **{rotulo}** — filtro definido no Dashboard.",
            icon="🔎",
        )
    with col_btn:
        st.markdown("&nbsp;", unsafe_allow_html=True)
        if botao_limpar_filtros(
            CHAVES_GLOBAIS + ("filtro_global_mes__widget",),
            MAPA_GLOBAIS.values(),
            key="btn_limpar_periodo_faturas",
            label="🧹 Limpar período",
            rotulo_auxiliar="Volta a mostrar todas as faturas",
        ):
            st.rerun()


def render() -> None:
    st.title("Faturas")

    hidratar_globais()

    with st.expander("📥 Importar nova fatura (PDF)", expanded=False):
        render_uploader(key_prefix="pagina_faturas")

    df_fat = carregar_faturas()
    if df_fat is None or df_fat.empty:
        st.info(
            "Nenhuma fatura no banco ainda. Use o uploader acima ou rode "
            "`gastometro` no terminal (PDFs em `entrada/`)."
        )
        return

    _banner_periodo_global()

    df_fat_periodo = _filtrar_faturas_por_periodo_global(df_fat)
    if df_fat_periodo.empty and periodo_global_ativo():
        st.warning(
            f"Nenhuma fatura em **{rotulo_periodo_global()}**. "
            "Use o botão acima pra ver todas."
        )
        persistir_globais()
        return

    c1, c2 = st.columns(2)
    c1.metric(
        "Faturas no recorte",
        f"{len(df_fat_periodo):,}".replace(",", "."),
    )
    total = float(df_fat_periodo["valor_total_declarado"].fillna(0).sum())
    c2.metric("Soma dos totais declarados", formatar_brl(total))

    st.divider()
    _tabela_faturas(df_fat_periodo)
    st.divider()
    _resumo_por_cartao(df_fat_periodo)
    st.divider()

    df_lanc = carregar_lancamentos()
    _drill_down(df_fat_periodo, df_lanc)

    persistir_globais()


render()
