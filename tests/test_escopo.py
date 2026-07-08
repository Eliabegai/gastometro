"""Testes de escopo casal/pessoal e orçamento."""

from __future__ import annotations

import pandas as pd

from analytics.escopo import (
    ESCOPO_CASAL,
    ESCOPO_PESSOAL,
    classificar_escopo_linha,
    comparativo_pessoas,
    historico_escopo_mensal,
    marcar_escopo,
    projetar_despesa_mes,
    referencia_mes_anterior,
    resumo_escopo_despesas,
)
from analytics.orcamento import calcular_progressos, listar_alertas, resumo_alertas


def _df(registros: list[dict]) -> pd.DataFrame:
    base = {
        "tipo": "despesa",
        "valor": 100.0,
        "pessoa": "",
        "categoria": "Outros Gastos",
        "conta_tipo": "outro",
    }
    return pd.DataFrame([{**base, **r} for r in registros])


def test_luz_e_financiamento_sao_casal():
    assert classificar_escopo_linha(
        categoria="Outros Gastos", descricao="Luz - Celesc", pessoa="Eliabe Gai"
    ) == ESCOPO_CASAL
    assert classificar_escopo_linha(
        categoria="Financiamento Casa", descricao="Financiamento Casa - Caixa", pessoa=""
    ) == ESCOPO_CASAL


def test_gasto_pessoal_segue_pessoa():
    assert classificar_escopo_linha(
        categoria="Lazer", descricao="Cinema", pessoa="Ana Leticia Silva Maciel"
    ) == ESCOPO_PESSOAL


def test_override_categoria():
    assert classificar_escopo_linha(
        categoria="Lazer",
        descricao="Cinema",
        pessoa="Ana",
        overrides_categoria={"Lazer": ESCOPO_CASAL},
    ) == ESCOPO_CASAL


def test_resumo_escopo():
    df = _df([
        {"descricao": "Luz", "valor": 200.0, "pessoa": ""},
        {"descricao": "Cinema", "valor": 50.0, "pessoa": "Ana", "categoria": "Lazer"},
    ])
    marcado = marcar_escopo(df)
    resumo = resumo_escopo_despesas(marcado)
    assert resumo["casal"] == 200.0
    assert resumo["pessoal"] == 50.0


def test_progresso_orcamento():
    df = _df([
        {"descricao": "Luz", "valor": 400.0, "pessoa": ""},
    ])
    metas = pd.DataFrame([
        {
            "id": 1,
            "escopo": ESCOPO_CASAL,
            "pessoa": "",
            "categoria": "",
            "valor_limite": 500.0,
        }
    ])
    prog = calcular_progressos(df, metas)
    assert len(prog) == 1
    assert prog.iloc[0]["pct"] == 80.0
    assert prog.iloc[0]["status"] == "alerta"


def test_progresso_orcamento_categoria_casal():
    """Assinaturas no cartão pessoal entram no teto por categoria."""
    df = _df([
        {
            "descricao": "SPOTIFY",
            "valor": 34.90,
            "pessoa": "Eliabe Gai",
            "categoria": "Assinatura Digital",
        },
        {
            "descricao": "NETFLIX",
            "valor": 55.90,
            "pessoa": "Ana Leticia",
            "categoria": "Assinatura Digital",
        },
    ])
    metas = pd.DataFrame([
        {
            "id": 1,
            "escopo": ESCOPO_CASAL,
            "pessoa": "",
            "categoria": "Assinatura Digital",
            "valor_limite": 200.0,
        }
    ])
    prog = calcular_progressos(df, metas)
    assert prog.iloc[0]["gasto"] == 90.8
    assert prog.iloc[0]["pct"] == 45.4


def test_progresso_orcamento_cartao_credito():
    """Teto Cartão de Crédito soma conta_tipo cartao_credito (todos os cartões)."""
    df = _df([
        {"valor": 150.0, "categoria": "Mercado", "conta_tipo": "cartao_credito"},
        {"valor": 80.0, "categoria": "Lazer", "conta_tipo": "cartao_credito"},
        {
            "valor": 200.0,
            "categoria": "Cartão de Crédito",
            "conta_tipo": "cartao_credito",
        },
        {"valor": 50.0, "categoria": "Luz", "conta_tipo": "outro"},
    ])
    metas = pd.DataFrame([
        {
            "id": 1,
            "escopo": ESCOPO_CASAL,
            "pessoa": "",
            "categoria": "Cartão de Crédito",
            "valor_limite": 3000.0,
        }
    ])
    prog = calcular_progressos(df, metas)
    assert prog.iloc[0]["gasto"] == 430.0


def test_projecao_mes_corrente():
    from datetime import date

    df = _df([{"descricao": "Mercado", "valor": 300.0, "referencia_mes": "2026-07"}])
    ref = "2026-07"
    proj = projetar_despesa_mes(df, referencia_mes=ref, hoje=date(2026, 7, 8))
    assert proj is not None
    assert proj > 300.0


def test_referencia_mes_anterior():
    assert referencia_mes_anterior("2026-05") == "2026-04"
    assert referencia_mes_anterior("2026-01") == "2025-12"
    assert referencia_mes_anterior("") is None


def test_historico_escopo_mensal():
    df = _df([
        {"descricao": "Luz", "valor": 200.0, "referencia_mes": "2026-05"},
        {"descricao": "Cinema", "valor": 50.0, "pessoa": "Ana", "referencia_mes": "2026-05"},
        {"descricao": "Luz", "valor": 180.0, "referencia_mes": "2026-06"},
    ])
    hist = historico_escopo_mensal(df)
    assert len(hist) == 2
    maio = hist[hist["referencia_mes"] == "2026-05"].iloc[0]
    assert maio["casal"] == 200.0
    assert maio["pessoal"] == 50.0


def test_comparativo_pessoas():
    df = _df([
        {"descricao": "Cinema", "valor": 60.0, "pessoa": "Ana", "categoria": "Lazer"},
        {"descricao": "Jogo", "valor": 40.0, "pessoa": "Eliabe", "categoria": "Lazer"},
    ])
    comp = comparativo_pessoas(df)
    assert len(comp) == 2
    assert float(comp["participacao_pct"].sum()) == 100.0


def test_alertas_orcamento():
    metas = pd.DataFrame([
        {"id": 1, "escopo": ESCOPO_CASAL, "pessoa": "", "categoria": "", "valor_limite": 100.0},
        {"id": 2, "escopo": ESCOPO_PESSOAL, "pessoa": "Ana", "categoria": "", "valor_limite": 200.0},
    ])
    df = _df([
        {"descricao": "Luz", "valor": 110.0},
        {"descricao": "Cinema", "valor": 170.0, "pessoa": "Ana", "categoria": "Lazer"},
    ])
    prog = calcular_progressos(df, metas)
    resumo = resumo_alertas(prog)
    assert resumo["estourado"] == 1
    assert resumo["alerta"] == 1
    assert len(listar_alertas(prog)) == 2
