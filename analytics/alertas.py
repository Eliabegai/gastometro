"""Alertas do topo do Dashboard: só o que pede ação agora.

Reúne em uma lista curta: mês no vermelho, teto do cartão estourado,
metas de orçamento em alerta e pendências recentes de fatura. Pendências
antigas (de meses atrás) ficam de fora para não virar ruído.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd

from analytics.cobertura import STATUS_OK
from analytics.fluxo import mes_corrente_iso
from analytics.mes_atual import PainelMes
from analytics.orcamento import resumo_alertas

NIVEL_ERRO = "erro"
NIVEL_AVISO = "aviso"


@dataclass(frozen=True)
class Alerta:
    nivel: str
    texto: str


def _brl(valor: float) -> str:
    texto = f"{abs(valor):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {texto}"


def _ref_ha_meses(ref: str, meses: int) -> str:
    ano, mes = (int(p) for p in ref.split("-", 1))
    total = ano * 12 + (mes - 1) - meses
    return f"{total // 12:04d}-{total % 12 + 1:02d}"


def montar_alertas(
    *,
    painel: PainelMes | None,
    progressos: pd.DataFrame | None,
    cobertura: pd.DataFrame | None,
    teto_cartao: float | None,
    meses_recentes: int = 3,
    hoje: date | None = None,
) -> list[Alerta]:
    """Lista de alertas, erros primeiro."""
    alertas: list[Alerta] = []

    if painel is not None and painel.disponivel < 0:
        alertas.append(
            Alerta(
                NIVEL_ERRO,
                f"O mês já está {_brl(painel.disponivel)} no vermelho "
                "(renda − comprometido − gasto variável).",
            )
        )
    if painel is not None and teto_cartao and painel.cartao > teto_cartao:
        alertas.append(
            Alerta(
                NIVEL_ERRO,
                f"Teto do cartão estourado em {_brl(painel.cartao - teto_cartao)}.",
            )
        )

    if progressos is not None and not progressos.empty:
        resumo = resumo_alertas(progressos)
        if resumo["estourado"]:
            alertas.append(
                Alerta(NIVEL_ERRO, f"{resumo['estourado']} meta(s) de orçamento estourada(s).")
            )
        if resumo["alerta"]:
            alertas.append(
                Alerta(NIVEL_AVISO, f"{resumo['alerta']} meta(s) de orçamento acima de 80%.")
            )

    if cobertura is not None and not cobertura.empty:
        corte = _ref_ha_meses(mes_corrente_iso(hoje), meses_recentes)
        recentes = cobertura[
            (cobertura["status"] != STATUS_OK) & (cobertura["referencia_mes"] >= corte)
        ]
        if not recentes.empty:
            alertas.append(
                Alerta(
                    NIVEL_AVISO,
                    f"{len(recentes)} pendência(s) de fatura nos últimos "
                    f"{meses_recentes} meses (mês sem PDF ou total que não fecha) — veja Faturas.",
                )
            )

    alertas.sort(key=lambda a: a.nivel != NIVEL_ERRO)
    return alertas
