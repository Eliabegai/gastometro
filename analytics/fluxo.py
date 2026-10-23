"""Fluxo de caixa canônico — fonte única de receita, despesa e saldo.

Antes, cada tela somava à sua maneira (Lançamentos subtraía estornos da
receita, Dashboard e Diagnóstico somavam estornos *na* receita, e a
"Soma" misturava despesas com receitas). Aqui ficam as regras, em um
lugar só:

- **Despesa líquida** = despesas − estornos. Estorno é dinheiro que o
  banco devolveu de uma compra; abate o gasto, não vira renda.
- **Renda** = lançamentos `receita` que não são dinheiro emprestado.
- **Entrada de crédito** = receita de empréstimo (`Empréstimo Recebido`).
  Entra no caixa, mas vira dívida; não é renda e não pode esconder um
  déficit.
- **Saldo** = renda − despesa líquida.
- **Previsto** = mês de referência posterior ao mês corrente (valores
  vindos da planilha, ainda sem fatura). Fica separado do realizado.

Aceita estornos com valor positivo (banco) ou negativo (DataFrame da UI,
`listar_lancamentos_df(sinal_estorno_negativo=True)`).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd

TIPO_DESPESA = "despesa"
TIPO_RECEITA = "receita"
TIPO_ESTORNO = "estorno"

# Receitas que são dinheiro emprestado: entram no caixa, mas viram dívida.
CATEGORIAS_ENTRADA_CREDITO = frozenset({"Empréstimo Recebido", "Empréstimo Familiar"})


@dataclass(frozen=True)
class Fluxo:
    """Totais de um recorte de lançamentos (valores sempre positivos)."""

    despesas_brutas: float
    estornos: float
    renda: float
    entradas_credito: float

    @property
    def despesas(self) -> float:
        """Despesa líquida: compras menos o que o banco estornou."""
        return self.despesas_brutas - self.estornos

    @property
    def saldo(self) -> float:
        """Renda − despesa líquida (sem contar empréstimos)."""
        return self.renda - self.despesas

    @property
    def saldo_com_credito(self) -> float:
        """Saldo somando os empréstimos recebidos (só pra comparação)."""
        return self.saldo + self.entradas_credito

    @property
    def taxa_poupanca(self) -> float | None:
        """Fração da renda que sobra. `None` sem renda."""
        if self.renda <= 0:
            return None
        return self.saldo / self.renda


def resumir_fluxo(df: pd.DataFrame | None) -> Fluxo:
    """Calcula o `Fluxo` de um DataFrame de lançamentos."""
    vazio = Fluxo(0.0, 0.0, 0.0, 0.0)
    if df is None or df.empty or "tipo" not in df.columns or "valor" not in df.columns:
        return vazio

    tipo = df["tipo"]
    despesas_brutas = float(df.loc[tipo == TIPO_DESPESA, "valor"].sum())
    estornos = float(df.loc[tipo == TIPO_ESTORNO, "valor"].abs().sum())

    receitas = df[tipo == TIPO_RECEITA]
    if "categoria" in receitas.columns:
        credito = receitas["categoria"].isin(CATEGORIAS_ENTRADA_CREDITO)
    else:
        credito = pd.Series(False, index=receitas.index)
    renda = float(receitas.loc[~credito, "valor"].abs().sum())
    entradas_credito = float(receitas.loc[credito, "valor"].abs().sum())

    return Fluxo(
        despesas_brutas=despesas_brutas,
        estornos=estornos,
        renda=renda,
        entradas_credito=entradas_credito,
    )


# ───────────────────────────────────────────────────────────────────
# Realizado × previsto
# ───────────────────────────────────────────────────────────────────
def mes_corrente_iso(hoje: date | None = None) -> str:
    """'2026-10' para o mês de `hoje` (default: hoje)."""
    hoje = hoje or date.today()
    return f"{hoje.year:04d}-{hoje.month:02d}"


def _mascara_previsto(df: pd.DataFrame, hoje: date | None) -> pd.Series:
    if "referencia_mes" not in df.columns:
        return pd.Series(False, index=df.index)
    ref = df["referencia_mes"].fillna("").astype(str)
    # ISO `YYYY-MM` ordena corretamente como texto.
    return (ref != "") & (ref > mes_corrente_iso(hoje))


def marcar_previsto(df: pd.DataFrame, hoje: date | None = None) -> pd.DataFrame:
    """Devolve cópia com a coluna booleana `previsto`."""
    out = df.copy()
    if out.empty:
        out["previsto"] = pd.Series(dtype=bool)
        return out
    out["previsto"] = _mascara_previsto(out, hoje)
    return out


def separar_realizado_previsto(
    df: pd.DataFrame, hoje: date | None = None
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Divide `df` em `(realizado, previsto)` pelo mês de referência."""
    if df is None or df.empty:
        return df, df
    previsto = _mascara_previsto(df, hoje)
    return df[~previsto], df[previsto]


def meses_previstos(df: pd.DataFrame, hoje: date | None = None) -> list[str]:
    """Referências ISO previstas presentes em `df`, em ordem cronológica."""
    if df is None or df.empty or "referencia_mes" not in df.columns:
        return []
    previsto = df[_mascara_previsto(df, hoje)]
    return sorted({str(r) for r in previsto["referencia_mes"]})


def renda_media_mensal(df: pd.DataFrame | None, hoje: date | None = None) -> float:
    """Renda média por mês **realizado** que teve renda (sem empréstimos)."""
    if df is None or df.empty or "tipo" not in df.columns:
        return 0.0
    realizado, _ = separar_realizado_previsto(df, hoje)
    if realizado is None or realizado.empty:
        return 0.0
    receitas = realizado[realizado["tipo"] == TIPO_RECEITA]
    if "categoria" in receitas.columns:
        receitas = receitas[~receitas["categoria"].isin(CATEGORIAS_ENTRADA_CREDITO)]
    if receitas.empty or "referencia_mes" not in receitas.columns:
        return 0.0
    meses = receitas["referencia_mes"].nunique()
    if meses <= 0:
        return 0.0
    return float(receitas["valor"].abs().sum()) / meses
