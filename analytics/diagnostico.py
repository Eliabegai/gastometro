"""Motor de diagnóstico financeiro — auditoria de fluxo e vazamentos.

Regras determinísticas sobre lançamentos, padrões recorrentes e tetos
de orçamento. Sem IA. Dívidas com saldo/juros vivem em `analytics.dividas`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Literal

import pandas as pd

from analytics.recorrentes import chave_merchant, detectar_recorrentes

PAPEL_AUDITORIA = "auditoria"
PAPEL_VAZAMENTO = "vazamento"
Papel = Literal["auditoria", "vazamento"]
Severidade = Literal["critico", "alerta", "info"]
Impacto = Literal["baixo", "medio", "alto"]

PESO_IMPACTO: dict[str, int] = {"baixo": 1, "medio": 2, "alto": 5}

MESES_MINIMOS = 2
TAXA_POUPANCA_ALERTA = 0.10
TAXA_POUPANCA_OK = 0.20
COMPROMETIMENTO_RECORRENTE = 0.35
OUTROS_GASTOS_MAX = 0.10
INFLACAO_PCT = 25.0
VARIACAO_RECORRENTE_PCT = 25.0
IMPULSO_MULT = 3.0
IMPULSO_MIN_BRL = 80.0
TICKET_MULT = 5.0

CATEGORIA_OUTROS = "Outros Gastos"

CATEGORIAS_ESSENCIAIS = frozenset(
    {
        "Saúde",
        "Farmácia",
        "Educação",
        "Dízimos",
        "Financiamento Carro",
        "Financiamento Casa",
        "Empréstimos",
    }
)

CATEGORIAS_TICKET_EXCLUIDAS = frozenset(
    {
        "Saúde",
        "Farmácia",
        "Financiamento Carro",
        "Financiamento Casa",
        "Empréstimos",
    }
)

CATEGORIAS_IMPULSO = frozenset(
    {
        "Lazer",
        "Compra Digital",
        "Vestuário",
    }
)

CATEGORIAS_DISCRICIONARIAS = frozenset(
    {
        "Lazer",
        "Alimentação",
        "Vestuário",
        "Compra Digital",
        "Assinatura Digital",
    }
)

CATEGORIAS_IMPACTO_BAIXO = frozenset(
    {
        "Assinatura Digital",
        "Compra Digital",
        "Serviços / Assinaturas",
    }
)

CATEGORIAS_IMPACTO_MEDIO = frozenset(
    {
        "Lazer",
        "Alimentação",
        "Vestuário",
        CATEGORIA_OUTROS,
    }
)

TIPOS_COMPROMETIMENTO = frozenset({"assinatura", "conta_fixa", "educacao"})

GRUPOS_ASSINATURA: dict[str, tuple[str, ...]] = {
    "streaming": ("netflix", "prime", "disney", "hbo", "paramount", "discovery"),
    "musica": ("spotify", "youtube", "deezer"),
}

ROTULO_GRUPO_ASSINATURA = {
    "streaming": "streaming",
    "musica": "música / vídeo",
}


def _brl(valor: float) -> str:
    s = f"{abs(valor):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"-R$ {s}" if valor < 0 else f"R$ {s}"


def _slug(texto: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "-" for ch in texto).strip("-")


@dataclass(frozen=True)
class Evidencia:
    descricao: str
    referencia_mes: str
    valor: float


@dataclass(frozen=True)
class Achado:
    id: str
    papeis: tuple[str, ...]
    severidade: Severidade
    titulo: str
    detalhe: str
    custo_mensal: float
    custo_anual: float
    impacto_estilo: Impacto
    tratamento: str
    economia_mensal_estimada: float
    evidencias: tuple[Evidencia, ...] = field(default_factory=tuple)

    @property
    def score(self) -> float:
        return score_tratamento(self)


@dataclass(frozen=True)
class KpisFluxo:
    receitas: float
    despesas: float
    saldo: float
    taxa_poupanca: float | None
    meses: int


@dataclass(frozen=True)
class Diagnostico:
    kpis: KpisFluxo
    achados: tuple[Achado, ...]
    meses_com_despesa: int


def score_tratamento(achado: Achado) -> float:
    """Maior = atacar primeiro. Essenciais com economia 0 ficam no fim."""
    peso = PESO_IMPACTO.get(achado.impacto_estilo, 5)
    if peso <= 0:
        return 0.0
    return achado.economia_mensal_estimada / peso


def tem_papel(achado: Achado, papel: str) -> bool:
    return papel in achado.papeis


def plano_simples(achados: list[Achado] | tuple[Achado, ...], n: int = 5) -> list[Achado]:
    """Top N achados com economia estimada, ranqueados pelo score."""
    candidatos = [a for a in achados if a.economia_mensal_estimada > 0]
    return sorted(
        candidatos,
        key=lambda a: (a.score, a.economia_mensal_estimada, a.custo_anual),
        reverse=True,
    )[:n]


def filtrar_papel(achados: list[Achado] | tuple[Achado, ...], papel: str) -> list[Achado]:
    return [a for a in achados if tem_papel(a, papel)]


def meses_com_despesa(df: pd.DataFrame) -> int:
    desp = _despesas(df)
    if desp.empty or "referencia_mes" not in desp.columns:
        return 0
    refs = desp["referencia_mes"].astype(str)
    refs = refs[refs.notna() & (refs != "") & (refs != "nan")]
    return int(refs.nunique())


def kpis_fluxo(df: pd.DataFrame) -> KpisFluxo:
    receitas = _soma_tipo(df, "receita")
    despesas = _soma_tipo(df, "despesa")
    saldo = receitas - despesas
    taxa = (saldo / receitas) if receitas > 0 else None
    return KpisFluxo(
        receitas=receitas,
        despesas=despesas,
        saldo=saldo,
        taxa_poupanca=taxa,
        meses=_meses_no_recorte(df),
    )


def diagnosticar(
    df: pd.DataFrame,
    *,
    padroes: pd.DataFrame | None = None,
    progressos: pd.DataFrame | None = None,
) -> Diagnostico:
    """Roda todas as regras no recorte `df` e devolve KPIs + achados."""
    kpis = kpis_fluxo(df)
    n_meses = meses_com_despesa(df)
    if df is None or df.empty:
        return Diagnostico(kpis=kpis, achados=(), meses_com_despesa=0)

    if padroes is None:
        padroes = detectar_recorrentes(df)
    if padroes is None:
        padroes = pd.DataFrame()

    achados: list[Achado] = []
    achados.extend(_regra_poupanca(kpis))
    achados.extend(_regra_tetos(progressos if progressos is not None else pd.DataFrame()))
    achados.extend(_regra_comprometimento(kpis, padroes))
    achados.extend(_regra_outros_gastos(df, kpis))
    achados.extend(_regra_inflacao(df))
    achados.extend(_regra_assinaturas(df, padroes))
    achados.extend(_regra_compra_inflada(df, padroes))
    achados.extend(_regra_impulsos_e_tickets(df, padroes))
    achados.extend(_regra_escondidos(df))

    return Diagnostico(
        kpis=kpis,
        achados=tuple(achados),
        meses_com_despesa=n_meses,
    )


def _soma_tipo(df: pd.DataFrame, tipo: str) -> float:
    if df is None or df.empty or "tipo" not in df.columns:
        return 0.0
    if tipo == "receita":
        sub = df[df["tipo"].isin(["receita", "estorno"])]
    else:
        sub = df[df["tipo"] == tipo]
    if sub.empty:
        return 0.0
    return float(sub["valor"].abs().sum())


def _despesas(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty or "tipo" not in df.columns:
        return pd.DataFrame()
    sub = df[df["tipo"] == "despesa"].copy()
    if sub.empty:
        return sub
    return sub[sub["valor"] > 0]


def _meses_no_recorte(df: pd.DataFrame) -> int:
    if df is None or df.empty or "referencia_mes" not in df.columns:
        return 0
    refs = df["referencia_mes"].astype(str)
    refs = refs[refs.notna() & (refs != "") & (refs != "nan")]
    return int(refs.nunique())


def _impacto_categoria(categoria: str) -> Impacto:
    cat = (categoria or "").strip()
    if cat in CATEGORIAS_IMPACTO_BAIXO:
        return "baixo"
    if cat in CATEGORIAS_IMPACTO_MEDIO:
        return "medio"
    return "alto"


def _eh_essencial(categoria: str) -> bool:
    return (categoria or "").strip() in CATEGORIAS_ESSENCIAIS


def _tratamento_cortar(acao: str, categoria: str) -> tuple[str, float]:
    """Devolve (texto, economia_factor). Essenciais: revisar, economia 0."""
    if _eh_essencial(categoria):
        return (
            "Revisar este gasto — categoria essencial, não sugerimos cortar.",
            0.0,
        )
    return acao, 1.0


def _evidencias(df: pd.DataFrame, mascara: pd.Series, n: int = 4) -> tuple[Evidencia, ...]:
    if df.empty or mascara is None:
        return ()
    sub = df.loc[mascara]
    if sub.empty:
        return ()
    col_ref = "referencia_mes" if "referencia_mes" in sub.columns else None
    ordenado = sub
    if col_ref:
        ordenado = sub.sort_values(col_ref, ascending=False)
    linhas = []
    for _, row in ordenado.head(n).iterrows():
        linhas.append(
            Evidencia(
                descricao=str(row.get("descricao", "")),
                referencia_mes=str(row.get("referencia_mes", "") or ""),
                valor=float(row.get("valor", 0) or 0),
            )
        )
    return tuple(linhas)


def _chaves_recorrentes(padroes: pd.DataFrame) -> set[str]:
    if padroes is None or padroes.empty or "chave" not in padroes.columns:
        return set()
    return set(padroes["chave"].astype(str))


# ── Auditoria ────────────────────────────────────────────────────────


def _regra_poupanca(kpis: KpisFluxo) -> list[Achado]:
    if kpis.receitas <= 0:
        return [
            Achado(
                id="poupanca:sem-receita",
                papeis=(PAPEL_AUDITORIA,),
                severidade="info",
                titulo="Receitas insuficientes para auditar",
                detalhe=(
                    "Não há receita no recorte. Sem renda registrada não dá "
                    "para calcular taxa de poupança nem saldo real."
                ),
                custo_mensal=kpis.despesas / kpis.meses if kpis.meses else kpis.despesas,
                custo_anual=kpis.despesas,
                impacto_estilo="alto",
                tratamento="Registrar salários e outras receitas no período.",
                economia_mensal_estimada=0.0,
            )
        ]

    if kpis.saldo < 0:
        buraco = -kpis.saldo
        mensal = buraco / kpis.meses if kpis.meses else buraco
        return [
            Achado(
                id="saldo:negativo",
                papeis=(PAPEL_AUDITORIA,),
                severidade="critico",
                titulo="Saldo negativo no recorte",
                detalhe=(
                    f"Despesas ({_brl(kpis.despesas)}) superam receitas "
                    f"({_brl(kpis.receitas)}) em {_brl(buraco)}."
                ),
                custo_mensal=mensal,
                custo_anual=buraco,
                impacto_estilo="alto",
                tratamento=(
                    "Fechar o buraco cortando vazamentos de baixo impacto "
                    "e conferindo se alguma receita ficou de fora."
                ),
                economia_mensal_estimada=mensal,
            )
        ]

    taxa = kpis.taxa_poupanca if kpis.taxa_poupanca is not None else 0.0
    if taxa >= TAXA_POUPANCA_OK:
        return []

    if taxa < TAXA_POUPANCA_ALERTA:
        severidade: Severidade = "alerta"
        titulo = "Taxa de poupança baixa"
        alvo = TAXA_POUPANCA_ALERTA
    else:
        severidade = "info"
        titulo = "Taxa de poupança ainda abaixo de 20%"
        alvo = TAXA_POUPANCA_OK

    falta = max(alvo * kpis.receitas - kpis.saldo, 0.0)
    mensal = falta / kpis.meses if kpis.meses else falta
    pct = taxa * 100
    return [
        Achado(
            id=f"poupanca:{severidade}",
            papeis=(PAPEL_AUDITORIA,),
            severidade=severidade,
            titulo=titulo,
            detalhe=(
                f"Sobrou {_brl(kpis.saldo)} de {_brl(kpis.receitas)} "
                f"({pct:.1f}%). Meta implícita: {alvo * 100:.0f}%."
            ),
            custo_mensal=mensal,
            custo_anual=falta,
            impacto_estilo="medio",
            tratamento=(
                f"Aumentar a sobra em cerca de {_brl(mensal)}/mês "
                f"para chegar a {alvo * 100:.0f}% da renda."
            ),
            economia_mensal_estimada=mensal,
        )
    ]


def _regra_tetos(progressos: pd.DataFrame) -> list[Achado]:
    if progressos is None or progressos.empty or "status" not in progressos.columns:
        return []
    alertas = progressos[progressos["status"].isin(["alerta", "estourado"])]
    achados: list[Achado] = []
    for _, row in alertas.iterrows():
        rotulo = str(row.get("rotulo", "teto"))
        gasto = float(row.get("gasto", 0) or 0)
        limite = float(row.get("limite", 0) or 0)
        pct = float(row.get("pct", 0) or 0)
        excesso = max(gasto - limite, 0.0)
        status = str(row.get("status", "alerta"))
        severidade: Severidade = "critico" if status == "estourado" else "alerta"
        verbo = "estourou" if status == "estourado" else "está perto de estourar"
        achados.append(
            Achado(
                id=f"teto:{_slug(rotulo)}",
                papeis=(PAPEL_AUDITORIA,),
                severidade=severidade,
                titulo=f"Teto {verbo}: {rotulo}",
                detalhe=(f"Gasto {_brl(gasto)} contra teto {_brl(limite)} ({pct:.0f}%)."),
                custo_mensal=excesso,
                custo_anual=excesso * 12,
                impacto_estilo="medio",
                tratamento=f"Voltar ao teto de {_brl(limite)} (hoje {_brl(gasto)}).",
                economia_mensal_estimada=excesso,
            )
        )
    return achados


def _regra_comprometimento(kpis: KpisFluxo, padroes: pd.DataFrame) -> list[Achado]:
    if padroes is None or padroes.empty or kpis.receitas <= 0 or kpis.meses <= 0:
        return []
    if "tipo_recorrente" not in padroes.columns:
        return []
    sub = padroes[padroes["tipo_recorrente"].isin(TIPOS_COMPROMETIMENTO)]
    if sub.empty:
        return []
    mensal = float(sub["media_mensal"].sum())
    receita_media = kpis.receitas / kpis.meses
    if receita_media <= 0:
        return []
    razao = mensal / receita_media
    if razao <= COMPROMETIMENTO_RECORRENTE:
        return []
    excesso = mensal - COMPROMETIMENTO_RECORRENTE * receita_media
    evidencias = tuple(
        Evidencia(
            descricao=str(row["descricao"]),
            referencia_mes="",
            valor=float(row["media_mensal"]),
        )
        for _, row in sub.sort_values("media_mensal", ascending=False).head(6).iterrows()
    )
    return [
        Achado(
            id="recorrente:comprometimento",
            papeis=(PAPEL_AUDITORIA,),
            severidade="alerta",
            titulo="Recorrentes comprometem demais a renda",
            detalhe=(
                f"Assinaturas, contas fixas e educação somam {_brl(mensal)}/mês "
                f"({razao * 100:.0f}% da renda média {_brl(receita_media)})."
            ),
            custo_mensal=mensal,
            custo_anual=mensal * 12,
            impacto_estilo="medio",
            tratamento=(
                f"Revisar esses contratos até caber em 35% da renda "
                f"(folga de cerca de {_brl(excesso)}/mês)."
            ),
            economia_mensal_estimada=max(excesso, 0.0),
            evidencias=evidencias,
        )
    ]


def _regra_outros_gastos(df: pd.DataFrame, kpis: KpisFluxo) -> list[Achado]:
    if kpis.despesas <= 0:
        return []
    desp = _despesas(df)
    if desp.empty or "categoria" not in desp.columns:
        return []
    outros = desp[desp["categoria"] == CATEGORIA_OUTROS]
    total = float(outros["valor"].sum()) if not outros.empty else 0.0
    if total / kpis.despesas <= OUTROS_GASTOS_MAX:
        return []
    mensal = total / kpis.meses if kpis.meses else total
    return [
        Achado(
            id="outros-gastos:alto",
            papeis=(PAPEL_AUDITORIA,),
            severidade="alerta",
            titulo="Demais gastos sem categoria",
            detalhe=(
                f"{CATEGORIA_OUTROS} soma {_brl(total)} "
                f"({total / kpis.despesas * 100:.0f}% das despesas). "
                "Isso esconde vazamentos."
            ),
            custo_mensal=mensal,
            custo_anual=mensal * 12,
            impacto_estilo="medio",
            tratamento="Recategorizar esses lançamentos para achar o vazamento real.",
            economia_mensal_estimada=0.0,
            evidencias=_evidencias(outros, pd.Series(True, index=outros.index), n=4),
        )
    ]


def _ultimo_mes_completo(refs: list[str], hoje: date | None = None) -> str | None:
    if not refs:
        return None
    hoje = hoje or date.today()
    corrente = f"{hoje.year:04d}-{hoje.month:02d}"
    anteriores = [r for r in refs if r < corrente]
    if anteriores:
        return anteriores[-1]
    return refs[-1]


def _regra_inflacao(df: pd.DataFrame, hoje: date | None = None) -> list[Achado]:
    desp = _despesas(df)
    if desp.empty or "categoria" not in desp.columns:
        return []
    refs = sorted(
        {str(r) for r in desp["referencia_mes"].astype(str) if r and r not in {"", "nan"}}
    )
    atual = _ultimo_mes_completo(refs, hoje=hoje)
    if not atual:
        return []
    anteriores = [r for r in refs if r < atual][-3:]
    if len(anteriores) < 3:
        return []

    achados: list[Achado] = []
    for cat in sorted(CATEGORIAS_DISCRICIONARIAS):
        sub = desp[desp["categoria"] == cat]
        if sub.empty:
            continue
        gasto_atual = float(sub.loc[sub["referencia_mes"] == atual, "valor"].sum())
        if gasto_atual <= 0:
            continue
        media_ant = (
            sum(float(sub.loc[sub["referencia_mes"] == r, "valor"].sum()) for r in anteriores) / 3.0
        )
        if media_ant <= 0:
            continue
        alta = (gasto_atual - media_ant) / media_ant * 100.0
        if alta < INFLACAO_PCT:
            continue
        excesso = gasto_atual - media_ant
        acao, fator = _tratamento_cortar(
            f"Voltar {cat} à média de {_brl(media_ant)}/mês (hoje {_brl(gasto_atual)}).",
            cat,
        )
        mascara = (desp["categoria"] == cat) & (desp["referencia_mes"] == atual)
        achados.append(
            Achado(
                id=f"inflacao:{_slug(cat)}",
                papeis=(PAPEL_AUDITORIA, PAPEL_VAZAMENTO),
                severidade="alerta",
                titulo=f"Inflação de estilo de vida: {cat}",
                detalhe=(
                    f"Em {atual}, {cat} ficou {alta:.0f}% acima da média "
                    f"dos 3 meses anteriores ({_brl(media_ant)} → {_brl(gasto_atual)})."
                ),
                custo_mensal=excesso,
                custo_anual=excesso * 12,
                impacto_estilo=_impacto_categoria(cat),
                tratamento=acao,
                economia_mensal_estimada=excesso * fator,
                evidencias=_evidencias(desp, mascara),
            )
        )
    return achados


# ── Vazamentos ───────────────────────────────────────────────────────


def _regra_assinaturas(df: pd.DataFrame, padroes: pd.DataFrame) -> list[Achado]:
    if padroes is None or padroes.empty or "tipo_recorrente" not in padroes.columns:
        return []
    assinaturas = padroes[padroes["tipo_recorrente"] == "assinatura"]
    achados: list[Achado] = []
    for _, row in assinaturas.iterrows():
        chave = str(row.get("chave", ""))
        descricao = str(row.get("descricao", chave))
        categoria = str(row.get("categoria", "Assinatura Digital") or "Assinatura Digital")
        media = float(row.get("media_mensal", 0) or 0)
        acao, fator = _tratamento_cortar(
            f"Avaliar cancelar {descricao}; economia anual ≈ {_brl(media * 12)}.",
            categoria,
        )
        mascara = (
            df["descricao"].astype(str).map(chave_merchant) == chave
            if "descricao" in df.columns
            else None
        )
        evidencias = _evidencias(df, mascara) if mascara is not None else ()
        achados.append(
            Achado(
                id=f"assinatura:{chave}",
                papeis=(PAPEL_VAZAMENTO,),
                severidade="info",
                titulo=f"Assinatura: {descricao}",
                detalhe=(
                    f"Média {_brl(media)}/mês ({int(row.get('meses', 0) or 0)} meses). "
                    f"Custo anualizado {_brl(media * 12)}."
                ),
                custo_mensal=media,
                custo_anual=media * 12,
                impacto_estilo="baixo",
                tratamento=acao,
                economia_mensal_estimada=media * fator,
                evidencias=evidencias,
            )
        )

    achados.extend(_assinaturas_duplicadas(assinaturas))
    return achados


def _grupo_assinatura(chave: str, descricao: str) -> str | None:
    texto = f"{chave} {descricao}".lower()
    for grupo, tokens in GRUPOS_ASSINATURA.items():
        if any(tok in texto for tok in tokens):
            return grupo
    return None


def _assinaturas_duplicadas(assinaturas: pd.DataFrame) -> list[Achado]:
    if assinaturas.empty:
        return []
    por_grupo: dict[str, list[pd.Series]] = {}
    for _, row in assinaturas.iterrows():
        grupo = _grupo_assinatura(str(row.get("chave", "")), str(row.get("descricao", "")))
        if grupo:
            por_grupo.setdefault(grupo, []).append(row)

    achados: list[Achado] = []
    for grupo, linhas in por_grupo.items():
        if len(linhas) < 2:
            continue
        ordenadas = sorted(linhas, key=lambda r: float(r.get("media_mensal", 0) or 0), reverse=True)
        extras = ordenadas[1:]
        economia = sum(float(r.get("media_mensal", 0) or 0) for r in extras)
        nomes = ", ".join(str(r.get("descricao", "")) for r in ordenadas)
        rotulo = ROTULO_GRUPO_ASSINATURA.get(grupo, grupo)
        evidencias = tuple(
            Evidencia(
                descricao=str(r.get("descricao", "")),
                referencia_mes="",
                valor=float(r.get("media_mensal", 0) or 0),
            )
            for r in ordenadas
        )
        achados.append(
            Achado(
                id=f"assinatura-duplicada:{grupo}",
                papeis=(PAPEL_VAZAMENTO,),
                severidade="alerta",
                titulo=f"Assinaturas duplicadas de {rotulo}",
                detalhe=(
                    f"Há {len(ordenadas)} serviços no mesmo grupo: {nomes}. "
                    "Dá para ficar com um e cancelar o restante."
                ),
                custo_mensal=economia,
                custo_anual=economia * 12,
                impacto_estilo="baixo",
                tratamento=(f"Manter o principal e cancelar o restante (~{_brl(economia)}/mês)."),
                economia_mensal_estimada=economia,
                evidencias=evidencias,
            )
        )
    return achados


def _regra_compra_inflada(df: pd.DataFrame, padroes: pd.DataFrame) -> list[Achado]:
    if padroes is None or padroes.empty or "tipo_recorrente" not in padroes.columns:
        return []
    compras = padroes[padroes["tipo_recorrente"] == "compra_recorrente"]
    if compras.empty:
        return []

    achados: list[Achado] = []
    for _, row in compras.iterrows():
        variacao = float(row.get("variacao_pct", 0) or 0)
        chave = str(row.get("chave", ""))
        inflou_trimestre = _inflou_trimestre(df, chave)
        if variacao < VARIACAO_RECORRENTE_PCT and not inflou_trimestre:
            continue
        descricao = str(row.get("descricao", chave))
        categoria = str(row.get("categoria", "") or "")
        media = float(row.get("media_mensal", 0) or 0)
        if inflou_trimestre:
            excesso = inflou_trimestre
            detalhe = (
                f"{descricao} subiu no trimestre recente em relação ao anterior "
                f"(+{_brl(excesso)}/mês)."
            )
        else:
            excesso = media * (variacao / (100.0 + variacao)) if variacao else 0.0
            detalhe = (
                f"{descricao} variou {variacao:.0f}% entre o menor e o maior "
                f"valor cobrado (média {_brl(media)}/mês)."
            )
        acao, fator = _tratamento_cortar(
            f"Reduzir {descricao} de volta ao patamar anterior.",
            categoria,
        )
        mascara = (
            df["descricao"].astype(str).map(chave_merchant) == chave
            if "descricao" in df.columns
            else None
        )
        achados.append(
            Achado(
                id=f"compra-inflada:{chave}",
                papeis=(PAPEL_VAZAMENTO,),
                severidade="alerta",
                titulo=f"Compra recorrente inflada: {descricao}",
                detalhe=detalhe,
                custo_mensal=excesso,
                custo_anual=excesso * 12,
                impacto_estilo=_impacto_categoria(categoria),
                tratamento=acao,
                economia_mensal_estimada=excesso * fator,
                evidencias=_evidencias(df, mascara) if mascara is not None else (),
            )
        )
    return achados


def _inflou_trimestre(df: pd.DataFrame, chave: str) -> float | None:
    desp = _despesas(df)
    if desp.empty or "descricao" not in desp.columns:
        return None
    sub = desp[desp["descricao"].astype(str).map(chave_merchant) == chave]
    if sub.empty:
        return None
    mensal = (
        sub.groupby("referencia_mes", as_index=False)["valor"].sum().sort_values("referencia_mes")
    )
    if len(mensal) < 6:
        return None
    recente = float(mensal["valor"].iloc[-3:].mean())
    anterior = float(mensal["valor"].iloc[-6:-3].mean())
    if anterior <= 0:
        return None
    if (recente - anterior) / anterior * 100.0 < INFLACAO_PCT:
        return None
    return recente - anterior


def _regra_impulsos_e_tickets(df: pd.DataFrame, padroes: pd.DataFrame) -> list[Achado]:
    desp = _despesas(df)
    if desp.empty or "categoria" not in desp.columns:
        return []
    chaves = _chaves_recorrentes(padroes)
    desp = desp.copy()
    desp["_chave"] = desp["descricao"].astype(str).map(chave_merchant)
    medianas = desp.groupby("categoria")["valor"].median()

    impulsos: dict[str, Achado] = {}
    tickets: dict[str, Achado] = {}

    for _, row in desp.iterrows():
        cat = str(row.get("categoria", "") or "")
        valor = float(row.get("valor", 0) or 0)
        chave = str(row.get("_chave", ""))
        if not chave or chave in chaves:
            continue
        mediana = float(medianas.get(cat, 0) or 0)
        if mediana <= 0:
            continue
        if cat in CATEGORIAS_IMPULSO and valor >= max(IMPULSO_MULT * mediana, IMPULSO_MIN_BRL):
            atual = impulsos.get(chave)
            if atual is not None and valor <= atual.custo_mensal:
                continue
            acao, fator = _tratamento_cortar(
                f"Evitar repetir este impulso ({_brl(valor)} vs mediana {_brl(mediana)}).",
                cat,
            )
            impulsos[chave] = Achado(
                id=f"impulso:{chave}",
                papeis=(PAPEL_VAZAMENTO,),
                severidade="alerta",
                titulo=f"Compra por impulso: {row.get('descricao', '')}",
                detalhe=(
                    f"{cat} {_brl(valor)} em {row.get('referencia_mes', '')} "
                    f"— {valor / mediana:.1f}× a mediana da categoria ({_brl(mediana)})."
                ),
                custo_mensal=valor,
                custo_anual=valor,
                impacto_estilo=_impacto_categoria(cat),
                tratamento=acao,
                economia_mensal_estimada=valor * fator,
                evidencias=(
                    Evidencia(
                        descricao=str(row.get("descricao", "")),
                        referencia_mes=str(row.get("referencia_mes", "") or ""),
                        valor=valor,
                    ),
                ),
            )

    for _, row in desp.iterrows():
        cat = str(row.get("categoria", "") or "")
        valor = float(row.get("valor", 0) or 0)
        chave = str(row.get("_chave", ""))
        if not chave or chave in chaves or chave in impulsos:
            continue
        if cat in CATEGORIAS_TICKET_EXCLUIDAS:
            continue
        mediana = float(medianas.get(cat, 0) or 0)
        if mediana <= 0 or valor < TICKET_MULT * mediana:
            continue
        atual = tickets.get(chave)
        if atual is not None and valor <= atual.custo_mensal:
            continue
        acao, fator = _tratamento_cortar(
            f"Investigar este ticket atípico ({_brl(valor)} vs mediana {_brl(mediana)}).",
            cat,
        )
        tickets[chave] = Achado(
            id=f"ticket:{chave}",
            papeis=(PAPEL_VAZAMENTO,),
            severidade="alerta",
            titulo=f"Ticket atípico: {row.get('descricao', '')}",
            detalhe=(f"{cat} {_brl(valor)} — {valor / mediana:.1f}× a mediana ({_brl(mediana)})."),
            custo_mensal=valor,
            custo_anual=valor,
            impacto_estilo=_impacto_categoria(cat),
            tratamento=acao,
            economia_mensal_estimada=valor * fator,
            evidencias=(
                Evidencia(
                    descricao=str(row.get("descricao", "")),
                    referencia_mes=str(row.get("referencia_mes", "") or ""),
                    valor=valor,
                ),
            ),
        )
    return list(impulsos.values()) + list(tickets.values())


def _regra_escondidos(df: pd.DataFrame) -> list[Achado]:
    desp = _despesas(df)
    if desp.empty or "categoria" not in desp.columns:
        return []
    outros = desp[desp["categoria"] == CATEGORIA_OUTROS].copy()
    if outros.empty:
        return []
    outros["_chave"] = outros["descricao"].astype(str).map(chave_merchant)
    outros = outros[outros["_chave"] != ""]
    if outros.empty:
        return []

    achados: list[Achado] = []
    agrupado = outros.groupby("_chave", as_index=False).agg(
        descricao=("descricao", lambda s: s.mode().iat[0] if not s.mode().empty else s.iloc[0]),
        qtde=("valor", "count"),
        total=("valor", "sum"),
        meses=("referencia_mes", "nunique"),
    )
    agrupado = agrupado[agrupado["qtde"] >= 2]
    for _, row in agrupado.iterrows():
        meses = max(int(row["meses"]), 1)
        media = float(row["total"]) / meses
        chave = str(row["_chave"])
        descricao = str(row["descricao"])
        mascara = outros["_chave"] == chave
        achados.append(
            Achado(
                id=f"escondido:{chave}",
                papeis=(PAPEL_VAZAMENTO,),
                severidade="info",
                titulo=f"Vazamento escondido: {descricao}",
                detalhe=(
                    f"{int(row['qtde'])} lançamentos em {CATEGORIA_OUTROS} "
                    f"(média {_brl(media)}/mês observado). "
                    f"Anualizado {_brl(media * 12)}."
                ),
                custo_mensal=media,
                custo_anual=media * 12,
                impacto_estilo="medio",
                tratamento="Recategorizar e decidir se vale manter.",
                economia_mensal_estimada=0.0,
                evidencias=_evidencias(outros, mascara),
            )
        )
    return achados


def vazamento_anualizavel(achados: list[Achado] | tuple[Achado, ...]) -> float:
    """Soma do custo anual dos achados de vazamento com economia > 0."""
    return sum(
        a.custo_anual
        for a in achados
        if tem_papel(a, PAPEL_VAZAMENTO) and a.economia_mensal_estimada > 0
    )
