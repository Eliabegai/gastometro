"""Testes da leitura de gastos: projeção do mês, fixo × hábito, cobertura."""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from analytics.cobertura import (
    STATUS_DIFERENCA,
    STATUS_OK,
    STATUS_SEM_FATURA,
    matriz_cobertura,
)
from analytics.escopo import projetar_despesa_mes
from analytics.recorrentes import eh_tipo_fixo, marcar_recorrentes

HOJE = date(2026, 10, 10)


# ── projeção ──────────────────────────────────────────────────────────
def test_projecao_soma_fixo_e_extrapola_so_o_variavel() -> None:
    df = pd.DataFrame(
        [
            {"tipo": "despesa", "valor": 1000.0, "fonte": "planilha_historico", "parcela": ""},
            {"tipo": "despesa", "valor": 100.0, "fonte": "pdf", "parcela": "02/10"},
            {"tipo": "despesa", "valor": 100.0, "fonte": "pdf", "parcela": ""},
        ]
    )
    # fixo = 1100; variável = 100 em 10 dias → 310 no mês (31 dias)
    proj = projetar_despesa_mes(df, referencia_mes="2026-10", hoje=HOJE)
    assert proj == pytest.approx(1100 + 310)


def test_projecao_sem_colunas_extras_continua_pelo_ritmo() -> None:
    df = pd.DataFrame([{"tipo": "despesa", "valor": 100.0}])
    proj = projetar_despesa_mes(df, referencia_mes="2026-10", hoje=HOJE)
    assert proj == pytest.approx(310.0)


def test_projecao_fora_do_mes_corrente_e_none() -> None:
    df = pd.DataFrame([{"tipo": "despesa", "valor": 100.0}])
    assert projetar_despesa_mes(df, referencia_mes="2026-09", hoje=HOJE) is None


# ── fixo × hábito ─────────────────────────────────────────────────────
def test_eh_tipo_fixo() -> None:
    for fixo in ("assinatura", "conta_fixa", "financiamento", "doacao"):
        assert eh_tipo_fixo(fixo)
    for habito in ("compra_recorrente", "outro", ""):
        assert not eh_tipo_fixo(habito)


def test_marcar_recorrentes_expoe_eh_fixo() -> None:
    linhas = []
    for mes in ("2026-05", "2026-06", "2026-07", "2026-08"):
        linhas.append(
            {
                "descricao": "Netflix",
                "categoria": "Assinaturas",
                "conta": "Nubank",
                "valor": 39.9,
                "tipo": "despesa",
                "referencia_mes": mes,
                "parcela": "",
            }
        )
    out = marcar_recorrentes(pd.DataFrame(linhas))
    assert "eh_fixo" in out.columns
    assert out["eh_fixo"].dtype == bool
    assert marcar_recorrentes(pd.DataFrame()).columns.tolist().count("eh_fixo") == 1


# ── cobertura ─────────────────────────────────────────────────────────
def _faturas() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"arquivo": "ago.pdf", "conta": "Nubank", "referencia_mes": "2026-08",
             "valor_total_declarado": 100.0},
            {"arquivo": "out.pdf", "conta": "Nubank", "referencia_mes": "2026-10",
             "valor_total_declarado": 200.0},
        ]
    )


def test_cobertura_detecta_buraco_e_diferenca() -> None:
    lanc = pd.DataFrame(
        [
            {"arquivo": "ago.pdf", "tipo": "despesa", "valor": 100.0},
            {"arquivo": "out.pdf", "tipo": "despesa", "valor": 150.0},
        ]
    )
    cob = matriz_cobertura(_faturas(), lanc, hoje=HOJE)
    status = dict(zip(cob["referencia_mes"], cob["status"], strict=True))
    assert status == {
        "2026-08": STATUS_OK,
        "2026-09": STATUS_SEM_FATURA,
        "2026-10": STATUS_DIFERENCA,
    }
    out = cob[cob["referencia_mes"] == "2026-10"].iloc[0]
    assert out["diferenca"] == pytest.approx(-50.0)


def test_cobertura_cobra_mes_corrente_de_cartao_ativo() -> None:
    fat = _faturas().iloc[[0]].assign(referencia_mes="2026-09", arquivo="set.pdf")
    cob = matriz_cobertura(fat, pd.DataFrame(), hoje=HOJE)
    assert cob["referencia_mes"].tolist() == ["2026-09", "2026-10"]
    assert cob.iloc[-1]["status"] == STATUS_SEM_FATURA


def test_cobertura_vazia() -> None:
    assert matriz_cobertura(None, None).empty
    assert matriz_cobertura(pd.DataFrame(), pd.DataFrame()).empty
