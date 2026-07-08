"""Página Orçamento — tetos máximos de gasto casal e pessoal."""

from __future__ import annotations

import re

import streamlit as st
from sqlmodel import select

from analytics.escopo import (
    ESCOPO_CASAL,
    ESCOPO_PESSOAL,
    marcar_escopo,
    referencia_mes_anterior,
    resumo_escopo_categoria,
)
from analytics.orcamento import calcular_progressos
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
    filtrar_por_ano,
    formatar_brl,
    invalidar_cache,
    ref_para_nome_br,
    selecionar_ano,
    selecionar_mes,
)
from app.ui_orcamento import render_barra_limite, valor_meta_existente
from db.engine import get_session
from db.models import Categoria, Pessoa
from db.repository import (
    copiar_orcamentos_de_mes,
    excluir_escopo_categoria,
    excluir_orcamento_meta,
    listar_escopos_categoria_dict,
    listar_orcamentos_df,
    salvar_escopo_categoria,
    salvar_orcamento_meta,
)


@st.cache_data(ttl=30, show_spinner=False)
def _pessoas() -> list[str]:
    with get_session() as session:
        nomes = session.exec(select(Pessoa.nome).where(Pessoa.ativo == True)).all()  # noqa: E712
    return sorted(nomes)


@st.cache_data(ttl=30, show_spinner=False)
def _categorias_despesa() -> list[str]:
    with get_session() as session:
        nomes = session.exec(
            select(Categoria.nome).where(Categoria.tipo == "despesa")
        ).all()
    return sorted(nomes)


def _pessoa_id(nome: str) -> int | None:
    if not nome:
        return None
    with get_session() as session:
        p = session.exec(select(Pessoa).where(Pessoa.nome == nome)).first()
        return p.id if p else None


def _categoria_id(nome: str) -> int | None:
    if not nome:
        return None
    with get_session() as session:
        c = session.exec(select(Categoria).where(Categoria.nome == nome)).first()
        return c.id if c else None


def _resumo_gastos(df_mes) -> tuple[float, float, float]:
    overrides = listar_escopos_categoria_dict()
    marcado = marcar_escopo(df_mes, overrides_categoria=overrides)
    despesas = marcado[marcado["tipo"] == "despesa"]
    if despesas.empty:
        return 0.0, 0.0, 0.0
    casal = float(despesas.loc[despesas["escopo"] == ESCOPO_CASAL, "valor"].sum())
    pessoal = float(despesas.loc[despesas["escopo"] == ESCOPO_PESSOAL, "valor"].sum())
    return casal, pessoal, casal + pessoal


def _secao_tetos_principais(referencia: str, pessoas: list[str]) -> None:
    """Formulário guiado: define os tetos máximos do mês."""
    metas = listar_orcamentos_df(referencia)

    st.subheader("1. Defina os tetos máximos")
    st.markdown(
        "Informe **quanto pode gastar no máximo** neste mês. "
        "O app compara com os gastos reais e avisa quando passar de **80%** "
        "ou **estourar** o limite."
    )

    with st.container(border=True):
        st.markdown("**🏠 Casal — gastos conjuntos**")
        st.caption("Contas da casa, financiamentos, faturas sem titular, etc.")
        teto_casal = st.number_input(
            "Teto máximo do casal (R$)",
            min_value=0.0,
            step=100.0,
            value=valor_meta_existente(metas, escopo=ESCOPO_CASAL),
            key="teto_casal",
            help="Soma de tudo classificado como gasto do casal.",
        )

        tetos_pessoais: dict[str, float] = {}
        if pessoas:
            st.divider()
            st.markdown("**👤 Pessoal — gastos individuais**")
            st.caption("Cada um controla o próprio teto de gastos pessoais.")
            for nome in pessoas:
                tetos_pessoais[nome] = st.number_input(
                    f"Teto máximo de {nome.split()[0]} (R$)",
                    min_value=0.0,
                    step=50.0,
                    value=valor_meta_existente(metas, escopo=ESCOPO_PESSOAL, pessoa=nome),
                    key=f"teto_pessoa_{nome}",
                )

        if st.button("Salvar tetos", type="primary", key="btn_salvar_tetos"):
            salvou = False
            if teto_casal > 0:
                salvar_orcamento_meta(
                    referencia_mes=referencia,
                    escopo=ESCOPO_CASAL,
                    valor_limite=teto_casal,
                )
                salvou = True
            for nome, valor in tetos_pessoais.items():
                if valor > 0:
                    salvar_orcamento_meta(
                        referencia_mes=referencia,
                        escopo=ESCOPO_PESSOAL,
                        valor_limite=valor,
                        pessoa_id=_pessoa_id(nome),
                    )
                    salvou = True
            if salvou:
                invalidar_cache()
                st.toast("Tetos salvos!")
                st.rerun()
            else:
                st.warning("Informe pelo menos um valor maior que zero.")


def _secao_progresso(df_mes, referencia: str) -> None:
    st.subheader("2. Acompanhe o progresso")
    st.caption(
        "Compara os **gastos reais** do mês (faturas e planilha importadas) "
        "com os **tetos** que você definiu no passo 1. "
        "Tetos **por categoria** somam todos os lançamentos daquela categoria "
        "(inclui cartões pessoais). Tetos gerais usam a divisão casal/pessoal. "
        "Amarelo acima de 80%, vermelho se estourar."
    )
    overrides = listar_escopos_categoria_dict()
    metas = listar_orcamentos_df(referencia)
    progressos = calcular_progressos(df_mes, metas, overrides_categoria=overrides)

    if progressos.empty:
        st.info(
            "Nenhum teto definido ainda. Preencha os valores acima e clique em "
            "**Salvar tetos** — ou copie do mês anterior."
        )
        return

    for row in progressos.itertuples(index=False):
        meta_id = int(row.id) if row.id else None

        def _excluir(mid: int = meta_id) -> None:
            if mid:
                excluir_orcamento_meta(mid)
                invalidar_cache()
                st.rerun()

        subtitulo = ""
        if "Cartão de Crédito" in row.rotulo:
            subtitulo = "Soma de todos os cartões do mês (compras + faturas)."

        render_barra_limite(
            row.rotulo,
            row.gasto,
            row.limite,
            row.pct,
            row.status,
            subtitulo=subtitulo,
            key_excluir=f"del_meta_{meta_id}" if meta_id else None,
            ao_excluir=_excluir if meta_id else None,
        )


def _secao_limite_categoria(referencia: str) -> None:
    with st.expander("Limite por categoria (opcional)", expanded=False):
        st.caption(
            "Soma **todos** os lançamentos da categoria no mês. "
            "**Cartão de Crédito** = todos os cartões somados (não só a célula agregada)."
        )
        escopo = st.radio(
            "Este limite é de",
            [ESCOPO_CASAL, ESCOPO_PESSOAL],
            format_func=lambda e: "Casal" if e == ESCOPO_CASAL else "Pessoal",
            horizontal=True,
            key="orc_cat_escopo",
        )
        pessoa_id = None
        if escopo == ESCOPO_PESSOAL:
            pessoa_sel = st.selectbox("De quem?", [""] + _pessoas(), key="orc_cat_pessoa")
            pessoa_id = _pessoa_id(pessoa_sel) if pessoa_sel else None

        cat_sel = st.selectbox("Categoria", _categorias_despesa(), key="orc_cat_nome")
        valor = st.number_input(
            "Teto máximo desta categoria (R$)",
            min_value=0.0,
            step=50.0,
            key="orc_cat_valor",
        )
        if st.button("Salvar limite da categoria", key="btn_salvar_cat"):
            if valor <= 0:
                st.warning("Informe um valor maior que zero.")
            else:
                salvar_orcamento_meta(
                    referencia_mes=referencia,
                    escopo=escopo,
                    valor_limite=valor,
                    pessoa_id=pessoa_id,
                    categoria_id=_categoria_id(cat_sel),
                )
                invalidar_cache()
                st.rerun()


def _slug_categoria(nome: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", nome.lower()).strip("_")[:48]


def _secao_escopo_categorias(df_mes, referencia: str) -> None:
    label_mes = ref_para_nome_br(referencia)
    with st.expander("Classificar categoria como casal ou pessoal", expanded=False):
        st.markdown(
            "Veja **como os lançamentos estão classificados hoje** e ajuste "
            "se quiser que uma categoria inteira conte sempre como casal ou pessoal."
        )
        overrides = listar_escopos_categoria_dict()
        cat = st.selectbox("Categoria", _categorias_despesa(), key="escopo_cat_sel")

        resumo = resumo_escopo_categoria(df_mes, cat, overrides_categoria=overrides)
        total_cat = float(resumo["casal"]) + float(resumo["pessoal"])
        if total_cat > 0:
            c1, c2, c3 = st.columns(3)
            c1.metric("Casal nesta categoria", formatar_brl(float(resumo["casal"])))
            c2.metric("Pessoal nesta categoria", formatar_brl(float(resumo["pessoal"])))
            c3.metric(
                "Lançamentos",
                f"{int(resumo['qtde_casal']) + int(resumo['qtde_pessoal'])}",
                delta=f"{int(resumo['qtde_casal'])} casal · {int(resumo['qtde_pessoal'])} pessoal",
                delta_color="off",
            )
        else:
            st.caption(f"Nenhuma despesa em **{cat}** em {label_mes}.")

        if cat in overrides:
            salvo = "Casal" if overrides[cat] == ESCOPO_CASAL else "Pessoal"
            st.success(f"Override ativo: todos os lançamentos de **{cat}** contam como **{salvo}**.")
            default_idx = 0 if overrides[cat] == ESCOPO_CASAL else 1
        else:
            st.info(
                "Sem override — cada lançamento segue a regra automática "
                "(titular do cartão → pessoal; luz/financiamento → casal). "
                "Prévia abaixo."
            )
            default_idx = (
                0 if float(resumo["casal"]) >= float(resumo["pessoal"]) else 1
            )

        sub = df_mes[(df_mes["tipo"] == "despesa") & (df_mes["categoria"] == cat)]
        if not sub.empty:
            prev = marcar_escopo(sub, overrides_categoria=overrides)[
                ["data", "descricao", "pessoa", "valor", "escopo"]
            ].copy()
            prev["escopo"] = prev["escopo"].map(
                {"casal": "Casal", "pessoal": "Pessoal"}
            )
            prev = prev.rename(
                columns={
                    "data": "Data",
                    "descricao": "Descrição",
                    "pessoa": "Pessoa",
                    "valor": "Valor (R$)",
                    "escopo": "Escopo",
                }
            )
            st.dataframe(
                prev.sort_values("Data", ascending=False).head(15),
                hide_index=True,
                use_container_width=True,
                column_config={
                    "Valor (R$)": st.column_config.NumberColumn(format="R$ %.2f"),
                },
            )
            st.caption("Veja todos em **Lançamentos** (coluna Escopo + filtro).")

        escopo = st.radio(
            "Forçar classificação como",
            [ESCOPO_CASAL, ESCOPO_PESSOAL],
            index=default_idx,
            format_func=lambda e: "Gasto do casal" if e == ESCOPO_CASAL else "Gasto pessoal",
            horizontal=True,
            key=f"escopo_radio_{_slug_categoria(cat)}",
        )
        col_salvar, col_remover = st.columns(2)
        with col_salvar:
            if st.button("Salvar classificação", key=f"btn_salvar_escopo_{_slug_categoria(cat)}"):
                salvar_escopo_categoria(cat, escopo)
                invalidar_cache()
                st.rerun()
        with col_remover:
            if cat in overrides and st.button(
                "Remover override",
                key=f"btn_remover_escopo_{_slug_categoria(cat)}",
            ):
                excluir_escopo_categoria(cat)
                invalidar_cache()
                st.rerun()


def render() -> None:
    st.title("Orçamento")
    st.markdown(
        "Defina **tetos máximos** de gasto e acompanhe quanto já foi usado no mês."
    )

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
            key="btn_limpar_orcamento",
        ):
            st.rerun()

    if not ref:
        st.info("Selecione um mês para definir e acompanhar os tetos.")
        persistir_globais()
        return

    label_mes = ref_para_nome_br(ref)
    df_mes = df_ano[df_ano["referencia_mes"] == ref] if not df_ano.empty else df_ano
    casal, pessoal, total = _resumo_gastos(df_mes)

    st.markdown(f"### Gastos em {label_mes}")
    c1, c2, c3 = st.columns(3)
    c1.metric("Já gasto — casal", formatar_brl(casal))
    c2.metric("Já gasto — pessoal", formatar_brl(pessoal))
    c3.metric("Total do mês", formatar_brl(total))

    ref_ant = referencia_mes_anterior(ref)
    if ref_ant:
        metas_atual = listar_orcamentos_df(ref)
        col_txt, col_btn = st.columns([3, 1])
        with col_txt:
            if metas_atual.empty:
                st.info(
                    f"Primeira vez em {label_mes}? Copie os tetos de "
                    f"**{ref_para_nome_br(ref_ant)}** com um clique."
                )
            else:
                st.caption(
                    f"Quer replicar tetos que faltam? Copie do mês anterior "
                    f"({ref_para_nome_br(ref_ant)})."
                )
        with col_btn:
            rotulo_btn = (
                "Copiar do mês anterior"
                if metas_atual.empty
                else "Copiar tetos faltantes"
            )
            if st.button(rotulo_btn, key="btn_copiar_metas"):
                n = copiar_orcamentos_de_mes(ref_ant, ref)
                invalidar_cache()
                if n:
                    st.success(f"{n} teto(s) copiado(s).")
                else:
                    st.warning("Nada novo para copiar.")
                st.rerun()

    st.divider()
    pessoas = _pessoas()
    _secao_tetos_principais(ref, pessoas)
    st.divider()
    _secao_progresso(df_mes, ref)
    st.divider()
    _secao_limite_categoria(ref)
    _secao_escopo_categorias(df_mes, ref)
    persistir_globais()


render()
