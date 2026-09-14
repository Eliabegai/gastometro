"""Página Dívidas — cadastro de estoque e destruidor (avalanche/snowball).

Tipos são extensíveis (imóvel, veículo, pessoal, consignado, cartão…).
Os lançamentos mensais continuam no fluxo; aqui mora saldo, juros e parcela.
"""

from __future__ import annotations

from datetime import date, datetime

import pandas as pd
import plotly.express as px
import streamlit as st
from sqlmodel import select

from analytics.dividas import (
    ESTRATEGIA_AVALANCHE,
    ESTRATEGIA_SNOWBALL,
    ROTULO_INDEXADOR,
    ROTULO_SISTEMA,
    ROTULO_STATUS,
    cenarios_extra,
    comparar_estrategias,
    cronograma_eventos,
    juros_mensal_atual,
    prazo_price_meses,
    resumo_estoque,
    rotulo_tipo_divida,
    sugerir_a_partir_de_recorrentes,
)
from app.helpers import (
    carregar_lancamentos,
    formatar_brl,
    formatar_brl_md,
    invalidar_cache,
)
from db.engine import get_session
from db.models import (
    INDEXADORES_DIVIDA,
    SISTEMAS_AMORTIZACAO,
    STATUS_DIVIDA,
    STATUS_DIVIDA_ATIVA,
    TIPO_DIVIDA_CARTAO,
    TIPO_DIVIDA_CHEQUE_ESPECIAL,
    TIPO_DIVIDA_CONSIGNADO,
    TIPO_DIVIDA_ESTUDANTIL,
    TIPO_DIVIDA_IMOVEL,
    TIPO_DIVIDA_OUTRO,
    TIPO_DIVIDA_PESSOAL,
    TIPO_DIVIDA_VEICULO,
    TIPOS_DIVIDA,
    Categoria,
    Pessoa,
)
from db.repository import (
    excluir_divida,
    listar_dividas_df,
    marcar_divida_quitada,
    salvar_divida,
)

_SEM_PESSOA = "(casal / não atribuir)"
_SEM_CATEGORIA = "(nenhuma)"
_NOVA = "+ Nova dívida"
_FONTE_FORM = "_divida_form_src"

ORDEM_TIPOS = [
    TIPO_DIVIDA_IMOVEL,
    TIPO_DIVIDA_VEICULO,
    TIPO_DIVIDA_PESSOAL,
    TIPO_DIVIDA_CONSIGNADO,
    TIPO_DIVIDA_ESTUDANTIL,
    TIPO_DIVIDA_CARTAO,
    TIPO_DIVIDA_CHEQUE_ESPECIAL,
    TIPO_DIVIDA_OUTRO,
]

EXTRAS_CENAARIO = [0.0, 200.0, 500.0, 1000.0, 2000.0]


def _int_ou_zero(valor) -> int:
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return 0
    try:
        return int(valor)
    except (TypeError, ValueError):
        return 0


def _float_ou_zero(valor) -> float:
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return 0.0
    try:
        return float(valor)
    except (TypeError, ValueError):
        return 0.0


def _as_date(valor, fallback: date) -> date:
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return fallback
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    try:
        return pd.Timestamp(valor).date()
    except (TypeError, ValueError):
        return fallback


def _tipos_ordenados() -> list[str]:
    vistos = [t for t in ORDEM_TIPOS if t in TIPOS_DIVIDA]
    extras = sorted(TIPOS_DIVIDA.difference(vistos))
    return vistos + extras


@st.cache_data(ttl=30, show_spinner=False)
def _pessoas() -> list[str]:
    with get_session() as session:
        nomes = session.exec(select(Pessoa.nome).where(Pessoa.ativo == True)).all()  # noqa: E712
    return sorted(nomes)


@st.cache_data(ttl=30, show_spinner=False)
def _categorias_despesa() -> list[str]:
    with get_session() as session:
        nomes = session.exec(select(Categoria.nome).where(Categoria.tipo == "despesa")).all()
    return sorted(nomes)


def _pessoa_id(nome: str) -> int | None:
    if not nome or nome == _SEM_PESSOA:
        return None
    with get_session() as session:
        p = session.exec(select(Pessoa).where(Pessoa.nome == nome)).first()
        return p.id if p else None


def _categoria_id(nome: str) -> int | None:
    if not nome or nome == _SEM_CATEGORIA:
        return None
    with get_session() as session:
        c = session.exec(select(Categoria).where(Categoria.nome == nome)).first()
        return c.id if c else None


def _meses_em_texto(meses: int | None) -> str:
    if meses is None or meses <= 0:
        return "—"
    anos, m = divmod(int(meses), 12)
    if anos and m:
        return f"{anos}a {m}m"
    if anos:
        return f"{anos} ano" if anos == 1 else f"{anos} anos"
    return f"{meses} mês" if meses == 1 else f"{meses} meses"


def _rotulo_editar(nome: str, divida_id: int) -> str:
    return f"{nome} (#{int(divida_id)})"


def _serie_brl(serie: pd.Series) -> pd.Series:
    return serie.map(lambda v: formatar_brl(float(v)) if pd.notna(v) else "—")


_COLUNA_BRL = st.column_config.TextColumn(alignment="right")


def _kpis(resumo: dict[str, float]) -> None:
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Dívidas ativas", str(int(resumo["qtde"])))
    c2.metric("Saldo total", formatar_brl(resumo["saldo"]))
    c3.metric("Parcelas no mês", formatar_brl(resumo["parcela"]))
    c4.metric("Juros médio (saldo)", f"{resumo['taxa_media']:.1f}% a.a.")


def _tabela_cadastro(df: pd.DataFrame) -> None:
    if df.empty:
        st.info("Nenhuma dívida cadastrada ainda.")
        return
    visivel = df.copy()
    visivel["Tipo"] = visivel["tipo"].map(rotulo_tipo_divida)
    visivel["Status"] = visivel["status"].map(lambda s: ROTULO_STATUS.get(s, s))
    prazos: list[str] = []
    juros_mes: list[float] = []
    for _, row in visivel.iterrows():
        n = prazo_price_meses(
            _float_ou_zero(row["saldo"]),
            _float_ou_zero(row["taxa_juros_aa"]),
            _float_ou_zero(row["parcela_mensal"]),
        )
        prazos.append(_meses_em_texto(n) if n is not None else "não quita")
        juros_mes.append(
            juros_mensal_atual(_float_ou_zero(row["saldo"]), _float_ou_zero(row["taxa_juros_aa"]))
        )
    visivel["Prazo est."] = prazos
    visivel["Juros/mês (R$)"] = juros_mes
    visivel = visivel.rename(
        columns={
            "nome": "Nome",
            "credor": "Credor",
            "saldo": "Saldo (R$)",
            "taxa_juros_aa": "Juros % a.a.",
            "parcela_mensal": "Parcela (R$)",
            "pessoa": "Pessoa",
        }
    )
    visivel["Saldo (R$)"] = _serie_brl(visivel["Saldo (R$)"])
    visivel["Parcela (R$)"] = _serie_brl(visivel["Parcela (R$)"])
    visivel["Juros/mês (R$)"] = _serie_brl(visivel["Juros/mês (R$)"])
    st.dataframe(
        visivel[
            [
                "Nome",
                "Tipo",
                "Credor",
                "Saldo (R$)",
                "Juros % a.a.",
                "Parcela (R$)",
                "Juros/mês (R$)",
                "Prazo est.",
                "Status",
                "Pessoa",
            ]
        ],
        hide_index=True,
        use_container_width=True,
        column_config={
            "Saldo (R$)": _COLUNA_BRL,
            "Parcela (R$)": _COLUNA_BRL,
            "Juros/mês (R$)": _COLUNA_BRL,
            "Juros % a.a.": st.column_config.NumberColumn(format="%.2f%%"),
        },
    )
    st.caption("Prazo estimado assume Price com a parcela de hoje. SAC/rotativo: revise o saldo.")


def _defaults_ficha() -> dict:
    return {
        "nome": "",
        "tipo": TIPO_DIVIDA_IMOVEL,
        "credor": "",
        "status": STATUS_DIVIDA_ATIVA,
        "saldo": 0.0,
        "taxa_juros_aa": 0.0,
        "parcela_mensal": 0.0,
        "indexador": "pre",
        "sistema_amortizacao": "price",
        "dia_vencimento": 0,
        "parcelas_totais": 0,
        "parcelas_pagas": 0,
        "pessoa": _SEM_PESSOA,
        "categoria": _SEM_CATEGORIA,
        "usar_contrato": False,
        "data_contratacao": date.today(),
        "usar_fim": False,
        "data_fim_prevista": date.today(),
        "observacao": "",
    }


def _row_para_ficha(row) -> dict:
    pessoa = str(row.get("pessoa") or "").strip() or _SEM_PESSOA
    categoria = str(row.get("categoria") or "").strip() or _SEM_CATEGORIA
    data_contrato = row.get("data_contratacao")
    data_fim = row.get("data_fim_prevista")
    return {
        "nome": str(row.get("nome") or ""),
        "tipo": str(row.get("tipo") or TIPO_DIVIDA_IMOVEL),
        "credor": str(row.get("credor") or ""),
        "status": str(row.get("status") or STATUS_DIVIDA_ATIVA),
        "saldo": _float_ou_zero(row.get("saldo")),
        "taxa_juros_aa": _float_ou_zero(row.get("taxa_juros_aa")),
        "parcela_mensal": _float_ou_zero(row.get("parcela_mensal")),
        "indexador": str(row.get("indexador") or "pre"),
        "sistema_amortizacao": str(row.get("sistema_amortizacao") or "price"),
        "dia_vencimento": _int_ou_zero(row.get("dia_vencimento")),
        "parcelas_totais": _int_ou_zero(row.get("parcelas_totais")),
        "parcelas_pagas": _int_ou_zero(row.get("parcelas_pagas")),
        "pessoa": pessoa,
        "categoria": categoria,
        "usar_contrato": bool(data_contrato),
        "data_contratacao": _as_date(data_contrato, date.today()),
        "usar_fim": bool(data_fim),
        "data_fim_prevista": _as_date(data_fim, date.today()),
        "observacao": str(row.get("observacao") or ""),
    }


def _idx(opcoes: list[str], valor: str, fallback: int = 0) -> int:
    return opcoes.index(valor) if valor in opcoes else fallback


def _carregar_ficha(dados: dict) -> None:
    """Novo `st.form` a cada carga — senão o Streamlit ignora `value=`."""
    st.session_state["divida_form_rev"] = int(st.session_state.get("divida_form_rev", 0)) + 1
    st.session_state["_divida_ficha"] = {**_defaults_ficha(), **dados}


def _form_divida(df: pd.DataFrame) -> None:
    ids_por_rotulo: dict[str, int | None] = {_NOVA: None}
    for _, row in df.iterrows():
        ids_por_rotulo[_rotulo_editar(str(row["nome"]), int(row["id"]))] = int(row["id"])

    if "divida_editar_next" in st.session_state:
        nxt = st.session_state.pop("divida_editar_next")
        if nxt in ids_por_rotulo:
            st.session_state["divida_editar"] = nxt
    escolha = st.selectbox("Editar", list(ids_por_rotulo.keys()), key="divida_editar")
    divida_id = ids_por_rotulo[escolha]
    atual = None
    if divida_id is not None and not df.empty:
        match = df[df["id"] == divida_id]
        if not match.empty:
            atual = match.iloc[0]

    prefill = st.session_state.pop("divida_prefill", None)
    if prefill:
        _carregar_ficha(prefill)
        st.session_state[_FONTE_FORM] = f"prefill:{prefill.get('nome')}"
        st.info(
            f"Ficha preenchida a partir de **{prefill.get('nome')}**. "
            "Falta informar o saldo restante e os juros % a.a."
        )
    else:
        fonte = f"id:{divida_id}" if divida_id is not None else "nova"
        if st.session_state.get(_FONTE_FORM) != fonte:
            _carregar_ficha(_row_para_ficha(atual) if atual is not None else _defaults_ficha())
            st.session_state[_FONTE_FORM] = fonte

    dados = st.session_state.get("_divida_ficha", _defaults_ficha())
    rev = int(st.session_state.get("divida_form_rev", 0))
    tipos = _tipos_ordenados()
    pessoas = [_SEM_PESSOA, *_pessoas()]
    categorias = [_SEM_CATEGORIA, *_categorias_despesa()]
    status_opts = sorted(STATUS_DIVIDA)
    index_opts = sorted(INDEXADORES_DIVIDA)
    sist_opts = sorted(SISTEMAS_AMORTIZACAO)

    st.caption(
        "Saldo restante e juros % a.a. são o que o Destruidor usa. "
        "A parcela sozinha não simula quitação."
    )
    with st.form(f"form_divida_{rev}"):
        nome = st.text_input(
            "Nome",
            value=str(dados["nome"]),
            placeholder="Financiamento da casa",
        )
        c1, c2, c3 = st.columns(3)
        with c1:
            tipo = st.selectbox(
                "Tipo",
                tipos,
                index=_idx(tipos, str(dados["tipo"])),
                format_func=rotulo_tipo_divida,
            )
            credor = st.text_input("Credor / banco", value=str(dados["credor"]))
            status = st.selectbox(
                "Status",
                status_opts,
                index=_idx(status_opts, str(dados["status"])),
                format_func=lambda s: ROTULO_STATUS.get(s, s),
            )
        with c2:
            saldo = st.number_input(
                "Saldo restante (R$)",
                min_value=0.0,
                step=100.0,
                value=float(dados["saldo"]),
                help="O que ainda deve hoje, não o valor original do contrato.",
            )
            taxa = st.number_input(
                "Juros % a.a. (CET ou taxa do contrato)",
                min_value=0.0,
                step=0.1,
                value=float(dados["taxa_juros_aa"]),
                help="A simulação usa juros nominais mensais = taxa anual / 12.",
            )
            parcela = st.number_input(
                "Parcela mensal (R$)",
                min_value=0.0,
                step=50.0,
                value=float(dados["parcela_mensal"]),
            )
        with c3:
            indexador = st.selectbox(
                "Indexador",
                index_opts,
                index=_idx(index_opts, str(dados["indexador"])),
                format_func=lambda s: ROTULO_INDEXADOR.get(s, s),
            )
            sistema = st.selectbox(
                "Amortização",
                sist_opts,
                index=_idx(sist_opts, str(dados["sistema_amortizacao"])),
                format_func=lambda s: ROTULO_SISTEMA.get(s, s),
            )
            dia = st.number_input(
                "Dia do vencimento",
                min_value=0,
                max_value=31,
                value=int(dados["dia_vencimento"]),
                help="0 = não informar.",
            )

        c4, c5, c6 = st.columns(3)
        with c4:
            tot = st.number_input(
                "Parcelas totais", min_value=0, value=int(dados["parcelas_totais"])
            )
            pagas = st.number_input(
                "Parcelas já pagas", min_value=0, value=int(dados["parcelas_pagas"])
            )
        with c5:
            pessoa = st.selectbox(
                "Titular", pessoas, index=_idx(pessoas, str(dados["pessoa"]))
            )
            categoria = st.selectbox(
                "Categoria de gasto",
                categorias,
                index=_idx(categorias, str(dados["categoria"])),
                help="Opcional: amarra a ficha à categoria dos lançamentos.",
            )
        with c6:
            usar_contrato = st.checkbox(
                "Informar contratação", value=bool(dados["usar_contrato"])
            )
            data_contrato = st.date_input(
                "Contratação", value=_as_date(dados["data_contratacao"], date.today())
            )
            usar_fim = st.checkbox(
                "Informar fim previsto", value=bool(dados["usar_fim"])
            )
            data_fim = st.date_input(
                "Fim previsto",
                value=_as_date(dados["data_fim_prevista"], date.today()),
            )
        observacao = st.text_area(
            "Observação", value=str(dados["observacao"]), height=80
        )
        salvar = st.form_submit_button("Salvar dívida", type="primary")

    if salvar:
        if not nome.strip():
            st.error("Informe um nome.")
            return
        if saldo > 0 and parcela <= 0:
            st.error("Informe a parcela mensal para dívidas com saldo.")
            return
        did = salvar_divida(
            divida_id=divida_id,
            nome=nome,
            tipo=tipo,
            credor=credor,
            status=status,
            saldo=saldo,
            taxa_juros_aa=taxa,
            indexador=indexador,
            sistema_amortizacao=sistema,
            parcela_mensal=parcela,
            parcelas_totais=int(tot) or None,
            parcelas_pagas=int(pagas) or None,
            dia_vencimento=int(dia) or None,
            data_contratacao=data_contrato if usar_contrato else None,
            data_fim_prevista=data_fim if usar_fim else None,
            pessoa_id=_pessoa_id(pessoa),
            categoria_id=_categoria_id(categoria),
            observacao=observacao,
        )
        invalidar_cache()
        if did is not None:
            st.session_state["divida_editar_next"] = _rotulo_editar(nome.strip(), did)
        st.session_state.pop(_FONTE_FORM, None)
        st.toast("Dívida salva.")
        st.rerun()

    if divida_id is not None:
        col_q, col_x = st.columns(2)
        with col_q:
            if st.button("Marcar como quitada", key=f"quit_{divida_id}"):
                marcar_divida_quitada(divida_id)
                invalidar_cache()
                st.session_state["divida_editar_next"] = _NOVA
                st.session_state.pop(_FONTE_FORM, None)
                st.rerun()
        with col_x:
            if st.button("Excluir cadastro", key=f"del_{divida_id}"):
                excluir_divida(divida_id)
                invalidar_cache()
                st.session_state["divida_editar_next"] = _NOVA
                st.session_state.pop(_FONTE_FORM, None)
                st.rerun()


def _botao_preencher(row, chave: str) -> None:
    if st.button("Preencher", key=chave):
        st.session_state["divida_prefill"] = {
            "nome": row["nome"],
            "tipo": row["tipo"],
            "credor": row.get("credor") or "",
            "status": STATUS_DIVIDA_ATIVA,
            "saldo": 0.0,
            "taxa_juros_aa": 0.0,
            "parcela_mensal": float(row["parcela_sugerida"]),
            "indexador": row.get("indexador") or "pre",
            "sistema_amortizacao": row.get("sistema_amortizacao") or "price",
            "pessoa": _SEM_PESSOA,
            "categoria": row["categoria"] or _SEM_CATEGORIA,
        }
        st.session_state["divida_editar_next"] = _NOVA
        st.rerun()


def _bloco_sugestao(row, prefixo: str, i: int) -> None:
    cols = st.columns([3, 2, 1])
    cols[0].markdown(
        f"**{row['nome']}** · {rotulo_tipo_divida(row['tipo'])} ({int(row['meses'])} meses)"
    )
    cols[1].caption(f"Parcela média {formatar_brl_md(float(row['parcela_sugerida']))}")
    with cols[2]:
        _botao_preencher(row, f"{prefixo}_{i}_{str(row['nome'])[:20]}")


def _sugestoes(lancamentos: pd.DataFrame, dividas: pd.DataFrame) -> None:
    sug = sugerir_a_partir_de_recorrentes(lancamentos, dividas)
    if sug.empty:
        return
    contratos = sug[sug["tipo_recorrente"] != "fatura_cartao"]
    faturas = sug[sug["tipo_recorrente"] == "fatura_cartao"]

    if not contratos.empty:
        st.subheader("Detectado nos lançamentos")
        st.caption(
            "Financiamentos e empréstimos ainda sem ficha. "
            "A parcela vem da média mensal — o saldo e os juros você informa."
        )
        for i, (_, row) in enumerate(contratos.iterrows()):
            _bloco_sugestao(row, "sug", i)

    if not faturas.empty:
        with st.expander("Faturas de cartão (só cadastre se o rotativo for dívida)"):
            st.caption(
                "Fatura paga todo mês não é estoque — é fluxo. "
                "Cadastre só se houver saldo rotativo, parcelamento longo ou atraso."
            )
            for i, (_, row) in enumerate(faturas.iterrows()):
                _bloco_sugestao(row, "sug_fat", i)


def _renda_media_mensal(lancamentos: pd.DataFrame | None) -> float:
    if lancamentos is None or lancamentos.empty:
        return 0.0
    rec = lancamentos[lancamentos["tipo"].isin(["receita", "estorno"])]
    if rec.empty or "referencia_mes" not in rec.columns:
        return 0.0
    meses = rec["referencia_mes"].nunique()
    if meses <= 0:
        return 0.0
    return float(rec["valor"].abs().sum()) / meses


def _aba_destruidor(df: pd.DataFrame, lancamentos: pd.DataFrame | None) -> None:
    ativas = df[df["status"] != "quitada"] if not df.empty else df
    if ativas.empty:
        st.info("Cadastre pelo menos uma dívida ativa para simular a quitação.")
        return
    sem_saldo = ativas[ativas["saldo"] <= 0]
    if len(sem_saldo) == len(ativas):
        st.info("Informe o saldo restante nas fichas para o Destruidor calcular.")
        return

    extra = st.number_input(
        "Quanto consegue pagar a mais por mês (R$)",
        min_value=0.0,
        step=50.0,
        key="divida_extra_mensal",
        help="Além da soma das parcelas. Esse extra vai para a dívida-alvo da estratégia.",
    )

    renda = _renda_media_mensal(lancamentos)
    parcela_total = float(ativas["parcela_mensal"].sum())
    if renda > 0:
        razao = (parcela_total + extra) / renda
        st.caption(
            f"Parcelas + extra = {formatar_brl_md(parcela_total + extra)} "
            f"({razao * 100:.0f}% da renda média {formatar_brl_md(renda)})."
        )

    resultados = comparar_estrategias(ativas, extra_mensal=extra)
    ava = resultados[ESTRATEGIA_AVALANCHE]
    sno = resultados[ESTRATEGIA_SNOWBALL]
    mini = resultados["minimo"]

    recomendada = ESTRATEGIA_AVALANCHE
    if sno.viavel and ava.viavel and sno.juros_totais + 1 < ava.juros_totais:
        recomendada = ESTRATEGIA_SNOWBALL

    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown("**Avalanche** (maior juros primeiro)")
        st.metric("Prazo", _meses_em_texto(ava.meses) if ava.viavel else "não quita")
        st.caption(f"Juros totais {formatar_brl_md(ava.juros_totais)}")
        if recomendada == ESTRATEGIA_AVALANCHE and ava.viavel:
            st.success("Recomendada — menos juros no total.")
    with c2:
        st.markdown("**Snowball** (menor saldo primeiro)")
        st.metric("Prazo", _meses_em_texto(sno.meses) if sno.viavel else "não quita")
        st.caption(f"Juros totais {formatar_brl_md(sno.juros_totais)}")
        if recomendada == ESTRATEGIA_SNOWBALL:
            st.success("Recomendada neste recorte.")
    with c3:
        st.markdown("**Só o mínimo** (sem extra, sem redirecionar)")
        st.metric("Prazo", _meses_em_texto(mini.meses) if mini.viavel else "não quita")
        st.caption(f"Juros totais {formatar_brl_md(mini.juros_totais)}")

    st.caption(
        "Mesmo sem extra, avalanche e snowball redirecionam a parcela da dívida "
        "que zerar para a próxima."
    )

    rotulos = {
        ESTRATEGIA_AVALANCHE: "Avalanche",
        ESTRATEGIA_SNOWBALL: "Snowball",
        "minimo": "Só o mínimo",
    }
    if "divida_ver_estrategia" not in st.session_state:
        st.session_state["divida_ver_estrategia"] = recomendada
    ver = st.radio(
        "Ver cronograma de",
        list(rotulos.keys()),
        format_func=lambda k: rotulos[k],
        horizontal=True,
        key="divida_ver_estrategia",
    )
    escolhida = resultados[ver]
    if escolhida.aviso:
        st.warning(escolhida.aviso)
    if not escolhida.viavel:
        st.error(
            f"Com esse extra a dívida não zera em 50 anos "
            f"(resta {formatar_brl(escolhida.saldo_remanescente)})."
        )
    else:
        if mini.viavel and ver != "minimo":
            ganho_juros = mini.juros_totais - escolhida.juros_totais
            ganho_meses = mini.meses - escolhida.meses
            g1, g2 = st.columns(2)
            g1.metric("Juros a menos vs só o mínimo", formatar_brl(max(ganho_juros, 0)))
            g2.metric("Tempo a menos vs só o mínimo", _meses_em_texto(max(ganho_meses, 0)))

        st.subheader("Ordem de ataque")
        for i, nome in enumerate(escolhida.ordem, start=1):
            st.markdown(f"**{i}.** {nome}")

        crono = cronograma_eventos(escolhida)
        if not crono.empty:
            crono_plot = crono.copy()
            crono_plot["mês"] = crono_plot["mês"].astype(str)
            fig = px.bar(
                crono_plot,
                x="mês",
                y="juros até então",
                color="dívida",
                labels={"mês": "Mês da quitação", "juros até então": "Juros acumulados (R$)"},
                title="Quando cada dívida some",
            )
            fig.update_layout(height=320)
            st.plotly_chart(fig, use_container_width=True)
            crono_tab = crono.rename(
                columns={
                    "mês": "Mês",
                    "dívida": "Dívida quitada",
                    "juros até então": "Juros até então (R$)",
                }
            )
            crono_tab["Juros até então (R$)"] = _serie_brl(crono_tab["Juros até então (R$)"])
            st.dataframe(
                crono_tab,
                hide_index=True,
                use_container_width=True,
                column_config={"Juros até então (R$)": _COLUNA_BRL},
            )

    st.subheader("E se o extra for outro valor?")
    extras = sorted({*EXTRAS_CENAARIO, float(extra)})
    estrategia_cenario = ver if ver != "minimo" else ESTRATEGIA_AVALANCHE
    cenario = cenarios_extra(ativas, extras, estrategia=estrategia_cenario)
    tabela = cenario.copy()
    tabela["Extra (R$)"] = _serie_brl(tabela["extra"])
    tabela["Prazo"] = [
        _meses_em_texto(int(m)) if pd.notna(m) else "não quita" for m in tabela["meses"]
    ]
    tabela["Juros totais (R$)"] = _serie_brl(tabela["juros"])
    st.dataframe(
        tabela[["Extra (R$)", "Prazo", "Juros totais (R$)"]],
        hide_index=True,
        use_container_width=True,
        column_config={
            "Extra (R$)": _COLUNA_BRL,
            "Juros totais (R$)": _COLUNA_BRL,
        },
    )

    st.caption(
        "Simulação Price (juros nominais mensais = taxa anual ÷ 12). "
        "SAC e rotativo usam a parcela de hoje — revise o saldo de tempos em tempos. "
        "Pós-fixadas (CDI/TR/IPCA) não projetam variação do indexador."
    )


def render() -> None:
    st.title("Dívidas")
    st.caption(
        "Cadastro de estoque (saldo, juros, parcela) e plano para se livrar "
        "delas. Serve para casa, carro e o empréstimo de hoje — e para "
        "consignado, cartão, cheque especial ou o que aparecer depois."
    )

    df = listar_dividas_df(incluir_quitadas=True)
    _kpis(resumo_estoque(df))
    st.divider()

    lanc = carregar_lancamentos()
    aba_cad, aba_des = st.tabs(["Cadastro", "Destruidor"])
    with aba_cad:
        _tabela_cadastro(df[df["status"] != "quitada"] if not df.empty else df)
        st.divider()
        st.subheader("Ficha")
        _form_divida(df[df["status"] != "quitada"] if not df.empty else df)
        st.divider()
        if lanc is not None and not lanc.empty:
            _sugestoes(lanc, df)
        if not df.empty and (df["status"] == "quitada").any():
            with st.expander("Quitadas"):
                _tabela_cadastro(df[df["status"] == "quitada"])

    with aba_des:
        _aba_destruidor(df, lanc)


render()
