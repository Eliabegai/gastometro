"""Cálculo de progresso de orçamento vs gasto real."""

from __future__ import annotations

from typing import Any

import pandas as pd

from analytics.escopo import ESCOPO_CASAL, ESCOPO_PESSOAL, marcar_escopo

CATEGORIA_CARTAO_CREDITO = "Cartão de Crédito"


def _rotulo_meta(meta: dict[str, Any]) -> str:
    escopo = meta.get("escopo", "")
    pessoa = (meta.get("pessoa") or "").strip()
    categoria = (meta.get("categoria") or "").strip()
    if escopo == ESCOPO_CASAL:
        return f"Casal — {categoria}" if categoria else "Casal (total)"
    if pessoa and categoria:
        return f"{pessoa} — {categoria}"
    if pessoa:
        return f"{pessoa} (pessoal)"
    return "Pessoal (total)"


def _gasto_para_meta(df: pd.DataFrame, meta: dict[str, Any]) -> float:
    sub = df[df["tipo"] == "despesa"].copy()
    if sub.empty:
        return 0.0

    categoria = (meta.get("categoria") or "").strip()
    pessoa = (meta.get("pessoa") or "").strip()
    escopo = meta.get("escopo", "")

    if categoria == CATEGORIA_CARTAO_CREDITO and "conta_tipo" in sub.columns:
        # Fatura agregada da planilha + compras detalhadas dos PDFs.
        sub = sub[sub["conta_tipo"] == "cartao_credito"]
        if pessoa:
            sub = sub[sub["pessoa"] == pessoa]
        elif escopo == ESCOPO_PESSOAL:
            sub = sub[sub["escopo"] == ESCOPO_PESSOAL]
    elif categoria:
        # Limite por categoria: soma todos os lançamentos da categoria no mês.
        # Assinaturas no cartão pessoal entram aqui (ex.: Casal — Assinatura Digital).
        sub = sub[sub["categoria"] == categoria]
        if pessoa:
            sub = sub[sub["pessoa"] == pessoa]
        elif escopo == ESCOPO_PESSOAL:
            sub = sub[sub["escopo"] == ESCOPO_PESSOAL]
    else:
        if escopo == ESCOPO_CASAL:
            sub = sub[sub["escopo"] == ESCOPO_CASAL]
        else:
            sub = sub[sub["escopo"] == ESCOPO_PESSOAL]
            if pessoa:
                sub = sub[sub["pessoa"] == pessoa]

    return float(sub["valor"].sum())


def calcular_progressos(
    df: pd.DataFrame,
    metas: pd.DataFrame,
    *,
    overrides_categoria: dict[str, str] | None = None,
) -> pd.DataFrame:
    """Combina metas com gasto real. Colunas: rotulo, gasto, limite, pct, status."""
    if metas.empty:
        return pd.DataFrame(
            columns=["rotulo", "gasto", "limite", "pct", "status", "escopo"]
        )

    base = marcar_escopo(df, overrides_categoria=overrides_categoria)
    linhas: list[dict[str, Any]] = []
    for row in metas.to_dict(orient="records"):
        gasto = _gasto_para_meta(base, row)
        limite = float(row.get("valor_limite") or 0)
        pct = round(gasto / limite * 100, 1) if limite > 0 else 0.0
        if pct >= 100:
            status = "estourado"
        elif pct >= 80:
            status = "alerta"
        else:
            status = "ok"
        linhas.append(
            {
                "id": row.get("id"),
                "rotulo": _rotulo_meta(row),
                "gasto": gasto,
                "limite": limite,
                "pct": pct,
                "status": status,
                "escopo": row.get("escopo", ""),
            }
        )
    return pd.DataFrame(linhas)


def listar_alertas(progressos: pd.DataFrame) -> pd.DataFrame:
    """Filtra metas em alerta (>80%) ou estouradas (>100%)."""
    if progressos.empty:
        return progressos
    return progressos[progressos["status"].isin(["alerta", "estourado"])].copy()


def resumo_alertas(progressos: pd.DataFrame) -> dict[str, int]:
    """Contagem de metas por status de alerta."""
    if progressos.empty:
        return {"estourado": 0, "alerta": 0}
    return {
        "estourado": int((progressos["status"] == "estourado").sum()),
        "alerta": int((progressos["status"] == "alerta").sum()),
    }
