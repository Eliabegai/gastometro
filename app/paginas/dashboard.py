"""Dashboard — visão geral do gastômetro.

Duas visões selecionáveis no topo:

- **Ano inteiro** (default): KPIs do ano (despesas, receitas, saldo,
  qtde), barras mensais comparando despesa vs receita, pie das
  despesas do ano por categoria e top 10 **categorias** por despesa
  do ano.

- **Mensal**: usuário escolhe um mês específico. KPIs e top 10
  categorias do mês, com delta vs mês anterior. Barras mensais
  continuam mostrando o ano todo (com o mês selecionado em destaque)
  pra dar contexto.

Top 10 mostra **categorias agregadas** (soma + qtde + ticket médio),
não lançamentos individuais — assim categorias com muitas compras
(ex.: Mercado) aparecem com o peso real.

Princípio: receita NUNCA é somada com despesa num mesmo KPI. KPIs
ficam sempre rotulados explicitamente.
"""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from analytics.escopo import (
    marcar_escopo as _marcar_escopo,
)
from analytics.escopo import (
    projetar_despesa_mes,
    resumo_escopo_despesas,
    resumo_por_pessoa,
)
from analytics.orcamento import calcular_progressos, listar_alertas, resumo_alertas
from app.estado import (
    CHAVE_ANO,
    CHAVE_MES,
    CHAVE_MODO,
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
    formatar_brl_md,
    ref_para_nome_br,
    selecionar_ano,
    selecionar_mes,
)
from app.ui_orcamento import render_barra_limite
from db.repository import listar_escopos_categoria_dict, listar_orcamentos_df

MODO_ANUAL = "Ano inteiro"
MODO_MENSAL = "Mensal"

TOP_CATEGORIAS_GRAFICO = 10

# Chave do evento de seleção do bar chart. Mantida em `st.session_state`
# pelo Streamlit quando `on_select="rerun"` está ativo.
KEY_BAR_CHART_EVT = "dashboard_bar_chart_evt"


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


def _grafico_barras_mensal(
    df: pd.DataFrame, *, ref_destaque: str | None = None
) -> None:
    """Barras mensais: 1 par por mês (Despesa vs Receita).

    Quando `ref_destaque` (ex: '2026-08') é passado, os meses não
    selecionados ficam translúcidos pra dar contexto sem competir
    visualmente com o mês em foco.
    """
    if df.empty:
        return

    sub = df[df["tipo"].isin(["despesa", "receita", "estorno"])].copy()
    if sub.empty:
        return

    sub["valor_abs"] = sub["valor"].abs()
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

    label_destaque = (
        ref_para_nome_br(ref_destaque) if ref_destaque else None
    )
    titulo = (
        f"Despesas × Receitas por mês — destaque em {label_destaque}"
        if label_destaque
        else "Despesas × Receitas por mês"
    )

    fig = px.bar(
        agg,
        x="mes_label",
        y="valor_abs",
        color="categoria_fluxo",
        barmode="group",
        title=titulo,
        labels={
            "mes_label": "Mês",
            "valor_abs": "Total (R$)",
            "categoria_fluxo": "Fluxo",
        },
        color_discrete_map={"Despesa": "#EF553B", "Receita": "#00CC96"},
    )
    if label_destaque:
        # Plotly aceita marker.opacity como lista (1 valor por barra
        # dentro do trace). Cada trace é um fluxo (Despesa/Receita).
        for trace in fig.data:
            trace.marker.opacity = [
                1.0 if rotulo == label_destaque else 0.35
                for rotulo in trace.x
            ]
    fig.update_layout(yaxis_tickprefix="R$ ", yaxis_tickformat=",.0f")
    # `on_select="rerun"` torna as barras clicáveis: cada clique salva
    # o ponto em `st.session_state[KEY_BAR_CHART_EVT]`. O `render()` lê
    # essa chave **antes** dos controles do topo pra ajustar modo/mês.
    st.plotly_chart(
        fig,
        use_container_width=True,
        on_select="rerun",
        selection_mode="points",
        key=KEY_BAR_CHART_EVT,
    )


def _ref_iso_do_label(label_pt: str, df: pd.DataFrame) -> str | None:
    """Converte 'Maio/2026' → '2026-05' usando as referências de `df`."""
    if not label_pt or df is None or df.empty:
        return None
    refs = sorted(df["referencia_mes"].dropna().unique().tolist())
    for ref in refs:
        if ref_para_nome_br(ref) == label_pt:
            return ref
    return None


def _aplicar_clique_barra(df: pd.DataFrame) -> None:
    """Se o usuário clicou numa barra, ajusta os controles para o modo
    Mensal com o mês correspondente. Deve ser chamada **antes** de
    renderizar o radio/selectbox (caso contrário Streamlit reclama de
    sobrescrita de state).
    """
    evento = st.session_state.get(KEY_BAR_CHART_EVT)
    if not evento:
        return
    selecao = getattr(evento, "selection", None)
    if selecao is None and isinstance(evento, dict):
        selecao = evento.get("selection")
    if not selecao:
        return
    if isinstance(selecao, dict):
        pontos = selecao.get("points") or []
    else:
        pontos = getattr(selecao, "points", None) or []
    if not pontos:
        return

    p0 = pontos[0]
    label = p0.get("x") if isinstance(p0, dict) else getattr(p0, "x", None)
    if not label:
        return

    ref_iso = _ref_iso_do_label(str(label), df)
    if not ref_iso:
        return

    # Garante que o ano também acompanhe o mês clicado (relevante se o
    # usuário estava em outro ano e clicou numa barra que pertencia ao
    # recorte exibido — pouco frequente, mas defensivo).
    try:
        ano_clicado = int(ref_iso.split("-")[0])
        st.session_state[CHAVE_ANO] = str(ano_clicado)
    except (ValueError, IndexError):
        pass

    st.session_state[CHAVE_MODO] = MODO_MENSAL
    # `CHAVE_MES` guarda ISO (estável p/ URL); a key auxiliar do widget
    # guarda o label PT-BR. Precisa setar AMBAS porque o `selecionar_mes`
    # só faz mirror ISO→label na primeira renderização (pra não
    # sobrescrever a escolha do user em reruns subsequentes). Como o
    # widget já foi renderizado antes desse clique, o mirror não rodaria
    # — fazemos manual aqui.
    st.session_state[CHAVE_MES] = ref_iso
    st.session_state[f"{CHAVE_MES}__widget"] = str(label)


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


# Grupos de despesa que o usuário acompanha com KPIs dedicados no
# dashboard. Cada grupo soma uma fatia específica do total de despesas:
#
#   - Cartões de Crédito: tudo que passou por conta `cartao_credito`
#     (tanto detalhe granular vindo dos PDFs quanto a célula agregada
#     da planilha familiar pra cartões sem PDF).
#   - Financiamentos: parcelas mensais de carro + casa.
#   - Casa Fixa: contas recorrentes da residência (Luz/Água/Internet).
#   - Empréstimos: parcelas + avulsos da categoria `Empréstimos`.
#
# `criterio(df)` recebe o recorte de despesas e devolve a soma do grupo.
# Mantém o critério em um lugar só pra evitar drift entre KPIs e
# eventuais drill-downs futuros.
GRUPOS_DESPESA: tuple[tuple[str, str], ...] = (
    ("Cartões de Crédito", "cartoes"),
    ("Financiamentos", "financiamentos"),
    ("Casa Fixa (Luz/Água/Internet)", "casa_fixa"),
    ("Empréstimos", "emprestimos"),
)

CATEGORIAS_FINANCIAMENTOS = ("Financiamento Carro", "Financiamento Casa")
CATEGORIAS_EMPRESTIMOS = ("Empréstimos",)

# Para "Casa Fixa" e "Empréstimos" usamos prefixos de descrição em vez
# de só categoria, pois o usuário costuma criar overrides que movem
# essas linhas pra agregadores ("Luz - Celesc" → "Casa e Construção";
# "Empréstimo Nubank (parcela)" → "Outros Gastos"). A descrição vinda
# do import da planilha familiar é estável — Luz/Água/Internet sempre
# começam com esse rótulo (Config em `imports/importar_planilha_familiar.py`).
PREFIXOS_CASA_FIXA = ("luz", "água", "agua", "internet")
PREFIXOS_EMPRESTIMOS = ("empréstimo", "emprestimo")


def _normalizar_desc(serie: pd.Series) -> pd.Series:
    """Lower + strip pra casar prefixos sem se preocupar com caixa."""
    return serie.fillna("").astype(str).str.strip().str.lower()


def _soma_grupo(df: pd.DataFrame, chave: str) -> float:
    """Soma absoluta do grupo de despesa identificado por `chave`."""
    if df.empty:
        return 0.0
    despesas = df[df["tipo"] == "despesa"]
    if despesas.empty:
        return 0.0
    if chave == "cartoes":
        # `conta_tipo` cobre PDFs (todas as compras passaram pelo cartão,
        # independente da categoria que recebeu o detalhe) e a célula
        # agregada da planilha familiar — desde que a conta tenha sido
        # marcada como `cartao_credito` (vide migração no `_obter_ou_criar_conta`).
        sub = despesas[despesas["conta_tipo"] == "cartao_credito"]
    elif chave == "financiamentos":
        # Financiamento é categoria limpa: a descrição também começa
        # com o nome, então cat ∈ {Financiamento Carro/Casa} basta.
        sub = despesas[despesas["categoria"].isin(CATEGORIAS_FINANCIAMENTOS)]
    elif chave == "casa_fixa":
        desc = _normalizar_desc(despesas["descricao"])
        sub = despesas[desc.str.startswith(PREFIXOS_CASA_FIXA)]
    elif chave == "emprestimos":
        cat_match = despesas["categoria"].isin(CATEGORIAS_EMPRESTIMOS)
        desc = _normalizar_desc(despesas["descricao"])
        desc_match = desc.str.startswith(PREFIXOS_EMPRESTIMOS)
        sub = despesas[cat_match | desc_match]
    else:
        return 0.0
    if sub.empty:
        return 0.0
    return float(sub["valor"].abs().sum())


def _banner_alertas_orcamento(progressos: pd.DataFrame) -> None:
    """Destaque visual no topo quando metas estão em alerta ou estouradas."""
    resumo = resumo_alertas(progressos)
    if resumo["estourado"] == 0 and resumo["alerta"] == 0:
        return

    partes: list[str] = []
    if resumo["estourado"]:
        n = resumo["estourado"]
        partes.append(f"**{n} meta(s) estourada(s)**")
    if resumo["alerta"]:
        n = resumo["alerta"]
        partes.append(f"**{n} meta(s) acima de 80%**")

    alertas = listar_alertas(progressos)
    if resumo["estourado"]:
        st.error("⚠️ Orçamento: " + " · ".join(partes))
    else:
        st.warning("🟡 Orçamento: " + " · ".join(partes))

    for row in alertas.itertuples(index=False):
        msg = (
            f"{row.rotulo} — {formatar_brl_md(row.gasto)} de "
            f"{formatar_brl_md(row.limite)} ({row.pct:.0f}%)"
        )
        if row.status == "estourado":
            msg += f". Estourou em {formatar_brl_md(row.gasto - row.limite)}."
            st.error(msg)
        else:
            st.warning(msg)


def _grafico_casal_pessoal(resumo: dict[str, float], por_pessoa: pd.DataFrame) -> None:
    """Donut casal vs pessoal + barras por titular."""
    total = resumo["total"]
    if total <= 0:
        st.info("Sem despesas no período.")
        return

    col_donut, col_barras = st.columns([1, 1])

    with col_donut:
        fatias = pd.DataFrame(
            {
                "escopo": ["Casal", "Pessoal"],
                "valor": [resumo["casal"], resumo["pessoal"]],
            }
        )
        fig = px.pie(
            fatias,
            names="escopo",
            values="valor",
            hole=0.55,
            title="Divisão das despesas",
            color="escopo",
            color_discrete_map={"Casal": "#2563EB", "Pessoal": "#F59E0B"},
        )
        fig.update_traces(textposition="inside", textinfo="percent+label")
        fig.update_layout(showlegend=False, margin=dict(t=40, b=20, l=20, r=20))
        st.plotly_chart(fig, use_container_width=True)

    with col_barras:
        if por_pessoa.empty:
            pct_casal = resumo["casal"] / total * 100
            st.markdown("**Participação**")
            st.progress(resumo["casal"] / total)
            st.caption(f"Casal {pct_casal:.0f}% · Pessoal {100 - pct_casal:.0f}%")
        else:
            st.markdown("**Gastos pessoais por titular**")
            fig = px.bar(
                por_pessoa,
                x="total",
                y="pessoa",
                orientation="h",
                text=por_pessoa["total"].map(lambda v: formatar_brl(float(v))),
                color_discrete_sequence=["#F59E0B"],
            )
            fig.update_traces(textposition="inside", insidetextanchor="end")
            fig.update_layout(
                yaxis_title="",
                xaxis_title="",
                margin=dict(t=10, b=10, l=10, r=10),
                height=max(160, 56 * len(por_pessoa)),
            )
            fig.update_xaxes(visible=False)
            st.plotly_chart(fig, use_container_width=True)


def _painel_escopo_e_orcamento(
    df_fluxo: pd.DataFrame, ref_mes: str | None
) -> None:
    """Gastos casal vs pessoal, projeção mensal e progresso de orçamento."""
    if df_fluxo.empty:
        return

    overrides = listar_escopos_categoria_dict()
    marcado = _marcar_escopo(df_fluxo, overrides_categoria=overrides)
    resumo = resumo_escopo_despesas(marcado)
    por_pessoa = resumo_por_pessoa(marcado)

    st.subheader("Casal vs pessoal")
    col_kpi, col_proj = st.columns([3, 1])
    with col_kpi:
        k1, k2, k3 = st.columns(3)
        k1.metric("Gastos do casal", formatar_brl(resumo["casal"]))
        k2.metric("Gastos pessoais", formatar_brl(resumo["pessoal"]))
        k3.metric("Total", formatar_brl(resumo["total"]))
    with col_proj:
        if ref_mes:
            proj = projetar_despesa_mes(marcado, referencia_mes=ref_mes)
            if proj is not None:
                st.metric(
                    "Projeção fim do mês",
                    formatar_brl(proj),
                    help="Estimativa pelo ritmo de gasto até hoje.",
                )

    _grafico_casal_pessoal(resumo, por_pessoa)

    if ref_mes:
        metas = listar_orcamentos_df(ref_mes)
        if not metas.empty:
            progressos = calcular_progressos(
                marcado, metas, overrides_categoria=overrides
            )
            _banner_alertas_orcamento(progressos)
            st.subheader("Tetos do mês")
            st.caption(
                "Gastos reais do período vs tetos cadastrados em **Orçamento**. "
                "Classificação casal/pessoal segue as regras automáticas "
                "(casa fixa, financiamento → casal; demais → titular do cartão)."
            )
            for row in progressos.itertuples(index=False):
                render_barra_limite(
                    row.rotulo,
                    row.gasto,
                    row.limite,
                    row.pct,
                    row.status,
                )
            st.caption("Ajuste os tetos na página **Orçamento**.")
        else:
            st.info(
                "Nenhum teto definido para este mês. "
                "Vá em **Orçamento** para estipular os valores máximos."
            )


def _kpis_grupos_despesa(
    df_periodo: pd.DataFrame, *, titulo_periodo: str
) -> None:
    """Renderiza 4 KPIs (cartões, financiamentos, casa fixa, empréstimos).

    Mostra o total de cada grupo + a participação % nas despesas do
    recorte. Útil pra o usuário saber rapidamente "quanto tá saindo
    pra cada bucket grande" sem precisar abrir o detalhe.
    """
    if df_periodo.empty:
        return
    despesa_total = _soma_por_tipo(df_periodo, "despesa")
    if despesa_total <= 0:
        return

    st.subheader(f"Despesas agrupadas — {titulo_periodo}")
    cols = st.columns(len(GRUPOS_DESPESA))
    for col, (rotulo, chave) in zip(cols, GRUPOS_DESPESA, strict=True):
        total = _soma_grupo(df_periodo, chave)
        pct = (total / despesa_total) * 100.0 if despesa_total else 0.0
        _kpi_card(
            col,
            rotulo,
            formatar_brl(total),
            delta=f"{pct:.1f}% das despesas",
            delta_color="off",
        )


def _top_categorias_periodo(
    df: pd.DataFrame, top_n: int = 10, *, titulo_periodo: str
) -> None:
    """Tabela: top **categorias** por despesa no recorte (mês ou ano).

    Agrega por categoria pra evitar que uma categoria com muitos
    lançamentos altos (ex.: Mercado) suma da lista quando exibimos só
    lançamentos individuais. Mostra soma, quantidade e ticket médio.
    """
    if df.empty:
        return
    sub = df[df["tipo"] == "despesa"].copy()
    if sub.empty:
        return
    agg = (
        sub.groupby("categoria")["valor"]
        .agg(soma="sum", qtde="count")
        .reset_index()
    )
    if agg.empty:
        return
    agg["ticket_medio"] = agg["soma"] / agg["qtde"]
    agg = agg.sort_values("soma", ascending=False).head(top_n)
    agg = agg.rename(
        columns={
            "categoria": "Categoria",
            "soma": "Total (R$)",
            "qtde": "Lançamentos",
            "ticket_medio": "Ticket médio (R$)",
        }
    )
    st.subheader(f"Top {top_n} categorias por despesa — {titulo_periodo}")
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


def _kpis_anuais(
    df_recorte: pd.DataFrame, rotulo_ano: str
) -> None:
    """4 KPIs do ano: Despesas, Receitas, Saldo, Qtde."""
    desp = _soma_por_tipo(df_recorte, "despesa")
    rec = _soma_por_tipo(df_recorte, "receita")
    saldo = rec - desp

    c1, c2, c3, c4 = st.columns(4)
    _kpi_card(c1, f"Despesas {rotulo_ano}", formatar_brl(desp))
    _kpi_card(c2, f"Receitas {rotulo_ano}", formatar_brl(rec))
    _kpi_card(
        c3,
        f"Saldo {rotulo_ano}",
        formatar_brl(saldo),
        delta=("Superávit" if saldo >= 0 else "Déficit"),
        delta_color="off",
    )
    _kpi_card(
        c4,
        "Lançamentos no período",
        f"{len(df_recorte):,}".replace(",", "."),
    )


def _kpis_mensais(
    df_recorte: pd.DataFrame, ref: str
) -> None:
    """4 KPIs do mês `ref`: Despesas (Δ), Receitas (Δ), Saldo, Qtde."""
    refs_anuais = _refs_ordenadas(df_recorte)
    if ref not in refs_anuais:
        st.info(f"Sem dados em {ref_para_nome_br(ref)}.")
        return
    idx = refs_anuais.index(ref)
    anterior = refs_anuais[idx - 1] if idx > 0 else ""
    dados = _kpis_mes(df_recorte, ref, anterior)

    label_mes = ref_para_nome_br(ref) or "—"
    label_ant = ref_para_nome_br(anterior) or "mês anterior"

    c1, c2, c3, c4 = st.columns(4)
    _kpi_card(
        c1,
        f"Despesas em {label_mes}",
        formatar_brl(dados["desp_atual"]),
        _formatar_delta(dados["desp_atual"], dados["desp_ant"], label_ant),
        delta_color="inverse",
    )
    _kpi_card(
        c2,
        f"Receitas em {label_mes}",
        formatar_brl(dados["rec_atual"]),
        _formatar_delta(dados["rec_atual"], dados["rec_ant"], label_ant),
    )
    saldo_mes = dados["rec_atual"] - dados["desp_atual"]
    _kpi_card(
        c3,
        f"Saldo de {label_mes}",
        formatar_brl(saldo_mes),
        delta=("Superávit" if saldo_mes >= 0 else "Déficit"),
        delta_color="off",
    )
    qtd = len(df_recorte[df_recorte["referencia_mes"] == ref])
    _kpi_card(
        c4,
        f"Lançamentos em {label_mes}",
        f"{qtd:,}".replace(",", "."),
    )


def render() -> None:
    st.title("💸 Gastômetro — Dashboard")

    # Hidrata filtros globais (`ano`, `mes`, `modo`) a partir da URL
    # antes de renderizar qualquer widget. Idempotente: só hidrata se
    # ainda não há valor em `session_state`.
    hidratar_globais()

    df = carregar_lancamentos()

    if df is None or df.empty:
        st.warning(
            "Nenhum lançamento no banco ainda. Rode `gastometro` (com PDFs em "
            "`entrada/`) ou `python -m imports.migrar_excel_legado` pra "
            "popular o histórico."
        )
        return

    # IMPORTANTE: processa o clique do bar chart ANTES de renderizar os
    # controles (radio + selectboxes). Isso permite ajustar
    # `session_state[CHAVE_MODO]` etc. sem disparar erro de "widget já
    # criado". Se o usuário clicou numa barra no run anterior, o run
    # atual já vem com modo=Mensal e mês selecionado.
    _aplicar_clique_barra(df)

    col_ano, col_modo, col_mes, col_limpar = st.columns([1, 1, 1, 0.7])
    with col_ano:
        ano = selecionar_ano(df)

    df_recorte = filtrar_por_ano(df, ano)
    if df_recorte.empty:
        st.info(
            f"Nenhum lançamento em {ano}. Tente outro ano ou 'Todos os anos'."
        )
        return

    with col_modo:
        modo = st.radio(
            "Visão",
            [MODO_ANUAL, MODO_MENSAL],
            index=0,
            horizontal=True,
            key=CHAVE_MODO,
        )

    ref_selecionada: str | None = None
    if modo == MODO_MENSAL:
        with col_mes:
            ref_selecionada = selecionar_mes(df_recorte)

    with col_limpar:
        # Alinhamento vertical: spacer fake pra empurrar o botão pra
        # base da linha (selectboxes têm label em cima).
        st.markdown("&nbsp;", unsafe_allow_html=True)
        if botao_limpar_filtros(
            CHAVES_GLOBAIS + (f"{CHAVE_MES}__widget",),
            MAPA_GLOBAIS.values(),
            key="btn_limpar_dashboard",
            rotulo_auxiliar="Volta ao ano corrente, visão anual",
        ):
            st.rerun()

    rotulo_ano = (
        f"no ano {ano}" if ano is not None else "(todo o histórico)"
    )

    # KPIs adequados à visão escolhida
    if modo == MODO_MENSAL and ref_selecionada:
        _kpis_mensais(df_recorte, ref_selecionada)
    else:
        _kpis_anuais(df_recorte, rotulo_ano)

    st.divider()

    # Recorte de fluxo (pie + top 10): ano todo na visão anual, ou só
    # o mês selecionado na visão mensal.
    if modo == MODO_MENSAL and ref_selecionada:
        df_fluxo = df_recorte[df_recorte["referencia_mes"] == ref_selecionada]
        titulo_periodo = ref_para_nome_br(ref_selecionada) or "—"
    else:
        df_fluxo = df_recorte
        titulo_periodo = rotulo_ano.replace("no ano ", "").replace(
            "(todo o histórico)", "todo o histórico"
        )

    st.caption(
        "💡 Dica: **clique em qualquer barra do gráfico abaixo** para "
        "ver os detalhes daquele mês."
    )
    col_a, col_b = st.columns([3, 2])
    with col_a:
        # Barras mensais sempre mostram o ano todo (contexto), com
        # destaque visual no mês selecionado quando aplicável.
        _grafico_barras_mensal(df_recorte, ref_destaque=ref_selecionada)
    with col_b:
        _grafico_pizza_categorias(df_fluxo)

    st.divider()
    _kpis_grupos_despesa(df_fluxo, titulo_periodo=titulo_periodo)
    _top_categorias_periodo(df_fluxo, titulo_periodo=titulo_periodo)

    st.divider()
    if modo == MODO_MENSAL and ref_selecionada:
        df_painel = df_recorte[df_recorte["referencia_mes"] == ref_selecionada]
        _painel_escopo_e_orcamento(df_painel, ref_selecionada)
    else:
        _painel_escopo_e_orcamento(df_recorte, None)

    # Persiste filtros globais na URL (idempotente). Roda no fim do
    # render pra capturar o último valor dos widgets.
    persistir_globais()


render()
