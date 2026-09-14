"""Estoque de dívidas e estratégias de quitação (avalanche / snowball).

A simulação usa tabela Price aproximada: juros nominais mensais =
`taxa_aa / 12`. SAC e rotativo entram com a parcela atual informada
(conservador: não reduz a parcela sozinha ao longo do tempo).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Literal

import pandas as pd

from analytics.recorrentes import detectar_recorrentes
from db.models import (
    TIPO_DIVIDA_CARTAO,
    TIPO_DIVIDA_CHEQUE_ESPECIAL,
    TIPO_DIVIDA_CONSIGNADO,
    TIPO_DIVIDA_IMOVEL,
    TIPO_DIVIDA_OUTRO,
    TIPO_DIVIDA_PESSOAL,
    TIPO_DIVIDA_VEICULO,
)

ESTRATEGIA_AVALANCHE = "avalanche"
ESTRATEGIA_SNOWBALL = "snowball"
ESTRATEGIA_MINIMO = "minimo"
Estrategia = Literal["avalanche", "snowball", "minimo"]

MAX_MESES = 600
_EPS = 0.01

TIPOS_RECORRENTE_DIVIDA = frozenset({"financiamento", "emprestimo", "fatura_cartao"})

ROTULO_TIPO_DIVIDA: dict[str, str] = {
    TIPO_DIVIDA_IMOVEL: "Financiamento de imóvel",
    TIPO_DIVIDA_VEICULO: "Financiamento de veículo",
    TIPO_DIVIDA_PESSOAL: "Empréstimo pessoal",
    TIPO_DIVIDA_CONSIGNADO: "Empréstimo consignado",
    "emprestimo_estudantil": "Empréstimo estudantil",
    TIPO_DIVIDA_CARTAO: "Cartão de crédito (rotativo)",
    "cheque_especial": "Cheque especial",
    TIPO_DIVIDA_OUTRO: "Outra dívida",
}

ROTULO_INDEXADOR = {
    "pre": "Pré-fixada",
    "cdi": "Pós (CDI)",
    "tr": "Pós (TR)",
    "ipca": "Pós (IPCA)",
    "outro": "Outro",
}

ROTULO_SISTEMA = {
    "price": "Price (parcela fixa)",
    "sac": "SAC (parcela decrescente)",
    "rotativo": "Rotativo / mínimo",
    "outro": "Outro",
}

ROTULO_STATUS = {
    "ativa": "Ativa",
    "quitada": "Quitada",
    "renegociada": "Renegociada",
}


@dataclass
class EstadoDivida:
    id: int
    nome: str
    saldo: float
    taxa_aa: float
    parcela: float


@dataclass
class EventoQuitacao:
    mes: int
    divida_id: int
    nome: str
    juros_acumulados: float


@dataclass
class ResultadoEstrategia:
    estrategia: str
    meses: int
    juros_totais: float
    ordem: list[str]
    eventos: list[EventoQuitacao] = field(default_factory=list)
    viavel: bool = True
    aviso: str | None = None
    saldo_remanescente: float = 0.0


def rotulo_tipo_divida(tipo: str) -> str:
    return ROTULO_TIPO_DIVIDA.get(tipo, tipo.replace("_", " ").title())


def taxa_mensal(taxa_aa: float) -> float:
    return max(float(taxa_aa), 0.0) / 100.0 / 12.0


def credor_do_nome(nome: str) -> str:
    """Pega o trecho depois do último ` - ` (`Financiamento Casa - Caixa`)."""
    texto = (nome or "").strip()
    if " - " not in texto:
        return ""
    return texto.rsplit(" - ", 1)[-1].strip()


def sistema_padrao_tipo(tipo: str) -> str:
    if tipo in {TIPO_DIVIDA_CARTAO, TIPO_DIVIDA_CHEQUE_ESPECIAL}:
        return "rotativo"
    if tipo == TIPO_DIVIDA_IMOVEL:
        return "sac"
    return "price"


def indexador_padrao_tipo(tipo: str) -> str:
    if tipo == TIPO_DIVIDA_IMOVEL:
        return "tr"
    return "pre"


def juros_mensal_atual(saldo: float, taxa_aa: float) -> float:
    return max(float(saldo), 0.0) * taxa_mensal(taxa_aa)


def prazo_price_meses(saldo: float, taxa_aa: float, parcela: float) -> int | None:
    """Meses restantes pagando só a parcela (Price). `None` se não zera."""
    s = max(float(saldo), 0.0)
    p = max(float(parcela), 0.0)
    if s <= _EPS:
        return 0
    if p <= _EPS:
        return None
    i = taxa_mensal(taxa_aa)
    if i <= 0:
        return int(math.ceil(s / p - 1e-12))
    juros = s * i
    if p <= juros + _EPS:
        return None
    n = math.log(p / (p - s * i)) / math.log(1.0 + i)
    return max(int(math.ceil(n - 1e-9)), 1)


def resumo_estoque(df: pd.DataFrame) -> dict[str, float]:
    """Totais das dívidas ativas no DataFrame de `listar_dividas_df`."""
    vazio = {"qtde": 0, "saldo": 0.0, "parcela": 0.0, "taxa_media": 0.0}
    if df is None or df.empty:
        return vazio
    ativas = df[df["status"] != "quitada"] if "status" in df.columns else df
    if ativas.empty:
        return vazio
    saldo = float(ativas["saldo"].sum())
    parcela = float(ativas["parcela_mensal"].sum())
    if saldo > 0:
        taxa_media = float((ativas["saldo"] * ativas["taxa_juros_aa"]).sum() / saldo)
    else:
        taxa_media = 0.0
    return {
        "qtde": int(len(ativas)),
        "saldo": saldo,
        "parcela": parcela,
        "taxa_media": taxa_media,
    }


def _estados_de_df(df: pd.DataFrame) -> list[EstadoDivida]:
    ativas = df[df["status"] != "quitada"] if "status" in df.columns else df
    estados: list[EstadoDivida] = []
    for _, row in ativas.iterrows():
        saldo = float(row.get("saldo", 0) or 0)
        if saldo <= _EPS:
            continue
        estados.append(
            EstadoDivida(
                id=int(row.get("id") or 0),
                nome=str(row.get("nome", "")),
                saldo=saldo,
                taxa_aa=float(row.get("taxa_juros_aa", 0) or 0),
                parcela=float(row.get("parcela_mensal", 0) or 0),
            )
        )
    return estados


def _escolher_alvo(ativos: list[EstadoDivida], estrategia: str) -> EstadoDivida | None:
    vivos = [d for d in ativos if d.saldo > _EPS]
    if not vivos:
        return None
    if estrategia == ESTRATEGIA_SNOWBALL:
        return min(vivos, key=lambda d: (d.saldo, -d.taxa_aa, d.nome))
    return max(vivos, key=lambda d: (d.taxa_aa, d.saldo, d.nome))


def simular_estrategia(
    df: pd.DataFrame,
    *,
    extra_mensal: float = 0.0,
    estrategia: str = ESTRATEGIA_AVALANCHE,
    max_meses: int = MAX_MESES,
) -> ResultadoEstrategia:
    """Simula quitação com orçamento constante = soma das parcelas + extra.

    Quando uma dívida zera, a parcela dela continua no orçamento e é
    redirecionada à próxima (efeito bola de neve / avalanche).
    """
    estados = _estados_de_df(df)
    if not estados:
        return ResultadoEstrategia(
            estrategia=estrategia,
            meses=0,
            juros_totais=0.0,
            ordem=[],
            viavel=True,
            aviso="Nenhuma dívida ativa com saldo.",
        )

    extra = max(float(extra_mensal), 0.0)
    orcamento = sum(d.parcela for d in estados) + extra
    juros_totais = 0.0
    eventos: list[EventoQuitacao] = []
    ordem: list[str] = []
    aviso: str | None = None

    for d in estados:
        juros_m = d.saldo * taxa_mensal(d.taxa_aa)
        if extra == 0 and d.parcela + 1e-9 < juros_m:
            aviso = (
                f"{d.nome}: a parcela não cobre os juros mensais "
                f"(~{juros_m:.2f}). Sem extra a dívida não diminui."
            )

    usar_extra_no_alvo = estrategia != ESTRATEGIA_MINIMO

    for mes in range(1, max_meses + 1):
        vivos = [d for d in estados if d.saldo > _EPS]
        if not vivos:
            return ResultadoEstrategia(
                estrategia=estrategia,
                meses=mes - 1,
                juros_totais=round(juros_totais, 2),
                ordem=ordem,
                eventos=eventos,
                viavel=True,
                aviso=aviso,
            )

        for d in vivos:
            j = d.saldo * taxa_mensal(d.taxa_aa)
            d.saldo += j
            juros_totais += j

        restante = orcamento
        vivos = [d for d in estados if d.saldo > _EPS]
        for d in vivos:
            minimo = min(d.parcela, d.saldo, restante)
            d.saldo -= minimo
            restante -= minimo
            if d.saldo <= _EPS and d.nome not in ordem:
                d.saldo = 0.0
                ordem.append(d.nome)
                eventos.append(
                    EventoQuitacao(
                        mes=mes,
                        divida_id=d.id,
                        nome=d.nome,
                        juros_acumulados=round(juros_totais, 2),
                    )
                )

        if usar_extra_no_alvo:
            while restante > _EPS:
                alvo = _escolher_alvo(estados, estrategia)
                if alvo is None or alvo.saldo <= _EPS:
                    break
                pago = min(restante, alvo.saldo)
                alvo.saldo -= pago
                restante -= pago
                if alvo.saldo <= _EPS and alvo.nome not in ordem:
                    alvo.saldo = 0.0
                    ordem.append(alvo.nome)
                    eventos.append(
                        EventoQuitacao(
                            mes=mes,
                            divida_id=alvo.id,
                            nome=alvo.nome,
                            juros_acumulados=round(juros_totais, 2),
                        )
                    )

    remanescente = sum(d.saldo for d in estados if d.saldo > _EPS)
    return ResultadoEstrategia(
        estrategia=estrategia,
        meses=max_meses,
        juros_totais=round(juros_totais, 2),
        ordem=ordem,
        eventos=eventos,
        viavel=remanescente <= _EPS,
        aviso=aviso
        or ("Não quitou no horizonte simulado (50 anos). Aumente o extra ou confira as taxas."),
        saldo_remanescente=round(remanescente, 2),
    )


def comparar_estrategias(
    df: pd.DataFrame, *, extra_mensal: float = 0.0
) -> dict[str, ResultadoEstrategia]:
    """Roda avalanche, snowball e só-mínimo no mesmo recorte."""
    return {
        ESTRATEGIA_AVALANCHE: simular_estrategia(
            df, extra_mensal=extra_mensal, estrategia=ESTRATEGIA_AVALANCHE
        ),
        ESTRATEGIA_SNOWBALL: simular_estrategia(
            df, extra_mensal=extra_mensal, estrategia=ESTRATEGIA_SNOWBALL
        ),
        ESTRATEGIA_MINIMO: simular_estrategia(df, extra_mensal=0.0, estrategia=ESTRATEGIA_MINIMO),
    }


def cenarios_extra(
    df: pd.DataFrame,
    extras: list[float],
    *,
    estrategia: str = ESTRATEGIA_AVALANCHE,
) -> pd.DataFrame:
    """Compara prazos e juros para vários valores de extra mensal."""
    linhas = []
    vistos: set[float] = set()
    for extra in extras:
        valor = max(float(extra), 0.0)
        if valor in vistos:
            continue
        vistos.add(valor)
        r = simular_estrategia(df, extra_mensal=valor, estrategia=estrategia)
        linhas.append(
            {
                "extra": valor,
                "meses": r.meses if r.viavel else None,
                "juros": r.juros_totais,
                "viavel": r.viavel,
            }
        )
    return pd.DataFrame(linhas)


def cronograma_eventos(resultado: ResultadoEstrategia) -> pd.DataFrame:
    if not resultado.eventos:
        return pd.DataFrame(columns=["mês", "dívida", "juros até então"])
    return pd.DataFrame(
        [
            {
                "mês": e.mes,
                "dívida": e.nome,
                "juros até então": e.juros_acumulados,
            }
            for e in resultado.eventos
        ]
    )


def _inferir_tipo_recorrente(tipo_recorrente: str, descricao: str, categoria: str) -> str:
    blob = f"{descricao} {categoria}".lower()
    if tipo_recorrente == "fatura_cartao" or "cartão" in blob or "cartao" in blob:
        return TIPO_DIVIDA_CARTAO
    if "casa" in blob or "imóv" in blob or "imov" in blob:
        return TIPO_DIVIDA_IMOVEL
    if "carro" in blob or "veíc" in blob or "veic" in blob:
        return TIPO_DIVIDA_VEICULO
    if "consignado" in blob:
        return TIPO_DIVIDA_CONSIGNADO
    if tipo_recorrente == "emprestimo":
        return TIPO_DIVIDA_PESSOAL
    if tipo_recorrente == "financiamento":
        return TIPO_DIVIDA_OUTRO
    return TIPO_DIVIDA_OUTRO


def sugerir_a_partir_de_recorrentes(
    lancamentos: pd.DataFrame,
    dividas: pd.DataFrame,
) -> pd.DataFrame:
    """Padrões de financiamento/empréstimo ainda sem ficha de dívida."""
    if lancamentos is None or lancamentos.empty:
        return pd.DataFrame()
    padroes = detectar_recorrentes(lancamentos)
    if padroes.empty or "tipo_recorrente" not in padroes.columns:
        return pd.DataFrame()
    candidatos = padroes[padroes["tipo_recorrente"].isin(TIPOS_RECORRENTE_DIVIDA)].copy()
    if candidatos.empty:
        return pd.DataFrame()

    nomes_existentes = set()
    if dividas is not None and not dividas.empty:
        nomes_existentes = {str(n).strip().lower() for n in dividas["nome"]}

    linhas = []
    for _, row in candidatos.iterrows():
        nome = str(row.get("descricao", "")).strip()
        if not nome or nome.lower() in nomes_existentes:
            continue
        tipo = _inferir_tipo_recorrente(
            str(row.get("tipo_recorrente", "")),
            nome,
            str(row.get("categoria", "") or ""),
        )
        linhas.append(
            {
                "nome": nome,
                "tipo": tipo,
                "credor": credor_do_nome(nome),
                "parcela_sugerida": float(row.get("media_mensal", 0) or 0),
                "categoria": str(row.get("categoria", "") or ""),
                "meses": int(row.get("meses", 0) or 0),
                "tipo_recorrente": str(row.get("tipo_recorrente", "")),
                "sistema_amortizacao": sistema_padrao_tipo(tipo),
                "indexador": indexador_padrao_tipo(tipo),
            }
        )
    if not linhas:
        return pd.DataFrame()
    return pd.DataFrame(linhas).sort_values("parcela_sugerida", ascending=False)
