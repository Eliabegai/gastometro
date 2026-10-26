"""Painel "Este mês": quanto entra, quanto já está comprometido e o que sobra.

Responde, num olhar, "posso gastar hoje?":

- **Renda**: renda realizada do mês; se o salário ainda não entrou, usa a
  média dos últimos meses (e avisa).
- **Comprometido**: parte já certa do mês (linhas da planilha + parcelas).
- **Variável gasto**: o resto das despesas líquidas até agora.
- **Disponível**: renda − comprometido − variável. Negativo = mês no vermelho.
- **Por dia**: disponível dividido pelos dias que restam (incluindo hoje).
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date

import pandas as pd

from analytics.escopo import mascara_fixo
from analytics.fluxo import mes_corrente_iso, resumir_fluxo, separar_realizado_previsto

CONTA_CARTAO = "cartao_credito"


@dataclass(frozen=True)
class PainelMes:
    referencia_mes: str
    renda: float
    renda_estimada: bool
    comprometido: float
    variavel: float
    cartao: float
    dias_restantes: int

    @property
    def disponivel(self) -> float:
        return self.renda - self.comprometido - self.variavel

    @property
    def por_dia(self) -> float:
        """Quanto dá para gastar por dia no resto do mês (nunca negativo)."""
        if self.dias_restantes <= 0:
            return 0.0
        return max(self.disponivel, 0.0) / self.dias_restantes


def renda_recente(df: pd.DataFrame, hoje: date | None = None, n: int = 3) -> float:
    """Média da renda dos `n` últimos meses realizados anteriores ao corrente."""
    if df is None or df.empty or "referencia_mes" not in df.columns:
        return 0.0
    atual = mes_corrente_iso(hoje)
    realizado, _ = separar_realizado_previsto(df, hoje)
    anteriores = realizado[realizado["referencia_mes"].astype(str) < atual]
    rendas = [
        (str(ref), resumir_fluxo(g).renda)
        for ref, g in anteriores.groupby("referencia_mes")
    ]
    rendas = sorted((r for r in rendas if r[1] > 0), key=lambda t: t[0])[-n:]
    if not rendas:
        return 0.0
    return sum(v for _, v in rendas) / len(rendas)


def painel_mes(df: pd.DataFrame | None, hoje: date | None = None) -> PainelMes | None:
    """Painel do mês corrente. `None` se não há lançamentos nele."""
    if df is None or df.empty or "referencia_mes" not in df.columns:
        return None
    hoje = hoje or date.today()
    ref = mes_corrente_iso(hoje)
    mes = df[df["referencia_mes"].astype(str) == ref]
    if mes.empty:
        return None

    fluxo = resumir_fluxo(mes)
    renda = fluxo.renda
    estimada = False
    if renda <= 0:
        renda = renda_recente(df, hoje)
        estimada = renda > 0

    despesas = mes[mes["tipo"] == "despesa"]
    comprometido = float(despesas.loc[mascara_fixo(despesas), "valor"].sum())
    variavel = fluxo.despesas - comprometido

    cartao = 0.0
    if "conta_tipo" in mes.columns:
        cartao = resumir_fluxo(mes[mes["conta_tipo"] == CONTA_CARTAO]).despesas

    dias = calendar.monthrange(hoje.year, hoje.month)[1]
    return PainelMes(
        referencia_mes=ref,
        renda=renda,
        renda_estimada=estimada,
        comprometido=comprometido,
        variavel=variavel,
        cartao=cartao,
        dias_restantes=dias - hoje.day + 1,
    )


def cartao_por_mes(df: pd.DataFrame | None) -> pd.DataFrame:
    """Despesa líquida no cartão por mês de referência (`referencia_mes`, `valor`)."""
    vazio = pd.DataFrame(columns=["referencia_mes", "valor"])
    if df is None or df.empty or "conta_tipo" not in df.columns:
        return vazio
    cartao = df[df["conta_tipo"] == CONTA_CARTAO]
    if cartao.empty:
        return vazio
    linhas = [
        {"referencia_mes": str(ref), "valor": resumir_fluxo(g).despesas}
        for ref, g in cartao.groupby("referencia_mes")
    ]
    return pd.DataFrame(linhas).sort_values("referencia_mes").reset_index(drop=True)
