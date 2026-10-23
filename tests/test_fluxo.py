"""Testes do fluxo canônico (`analytics.fluxo`)."""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from analytics.fluxo import (
    marcar_previsto,
    mes_corrente_iso,
    meses_previstos,
    renda_media_mensal,
    resumir_fluxo,
    separar_realizado_previsto,
)

HOJE = date(2026, 10, 23)


def _df(linhas: list[dict]) -> pd.DataFrame:
    base = {"categoria": "Mercado", "referencia_mes": "2026-10"}
    return pd.DataFrame([{**base, **linha} for linha in linhas])


def test_estorno_abate_despesa_e_nao_vira_renda() -> None:
    df = _df([
        {"tipo": "despesa", "valor": 1000.0},
        {"tipo": "estorno", "valor": -80.0},  # sinal da UI
        {"tipo": "receita", "valor": 500.0, "categoria": "Salário"},
    ])
    f = resumir_fluxo(df)
    assert f.despesas_brutas == 1000.0
    assert f.estornos == 80.0
    assert f.despesas == 920.0
    assert f.renda == 500.0


def test_estorno_positivo_do_banco_tem_o_mesmo_efeito() -> None:
    df = _df([
        {"tipo": "despesa", "valor": 100.0},
        {"tipo": "estorno", "valor": 30.0},
    ])
    assert resumir_fluxo(df).despesas == 70.0


def test_emprestimo_recebido_fica_fora_da_renda() -> None:
    df = _df([
        {"tipo": "receita", "valor": 4500.0, "categoria": "Salário"},
        {"tipo": "receita", "valor": 3200.0, "categoria": "Empréstimo Recebido"},
        {"tipo": "despesa", "valor": 5000.0},
    ])
    f = resumir_fluxo(df)
    assert f.renda == 4500.0
    assert f.entradas_credito == 3200.0
    assert f.saldo == -500.0
    assert f.saldo_com_credito == 2700.0


def test_taxa_poupanca() -> None:
    df = _df([
        {"tipo": "receita", "valor": 1000.0, "categoria": "Salário"},
        {"tipo": "despesa", "valor": 900.0},
    ])
    assert resumir_fluxo(df).taxa_poupanca == pytest.approx(0.1)


def test_taxa_poupanca_none_sem_renda() -> None:
    df = _df([{"tipo": "despesa", "valor": 10.0}])
    assert resumir_fluxo(df).taxa_poupanca is None


def test_df_vazio_ou_sem_colunas() -> None:
    assert resumir_fluxo(pd.DataFrame()).despesas == 0.0
    assert resumir_fluxo(None).renda == 0.0
    assert resumir_fluxo(pd.DataFrame({"x": [1]})).saldo == 0.0


def test_df_sem_coluna_categoria_conta_toda_receita_como_renda() -> None:
    df = pd.DataFrame([{"tipo": "receita", "valor": 200.0}])
    assert resumir_fluxo(df).renda == 200.0


def test_transferencia_nao_entra_em_nada() -> None:
    df = _df([{"tipo": "transferencia", "valor": 999.0}])
    f = resumir_fluxo(df)
    assert (f.despesas, f.renda, f.entradas_credito) == (0.0, 0.0, 0.0)


def test_mes_corrente_iso() -> None:
    assert mes_corrente_iso(HOJE) == "2026-10"
    assert mes_corrente_iso(date(2026, 1, 5)) == "2026-01"


def test_marcar_previsto_usa_mes_corrente() -> None:
    df = _df([
        {"tipo": "despesa", "valor": 1.0, "referencia_mes": "2026-09"},
        {"tipo": "despesa", "valor": 1.0, "referencia_mes": "2026-10"},
        {"tipo": "despesa", "valor": 1.0, "referencia_mes": "2026-11"},
        {"tipo": "despesa", "valor": 1.0, "referencia_mes": ""},
    ])
    marcado = marcar_previsto(df, HOJE)
    assert marcado["previsto"].tolist() == [False, False, True, False]
    assert "previsto" not in df.columns  # não muta o original


def test_separar_realizado_previsto_e_meses_previstos() -> None:
    df = _df([
        {"tipo": "despesa", "valor": 10.0, "referencia_mes": "2026-10"},
        {"tipo": "despesa", "valor": 20.0, "referencia_mes": "2026-12"},
        {"tipo": "despesa", "valor": 30.0, "referencia_mes": "2026-11"},
    ])
    real, prev = separar_realizado_previsto(df, HOJE)
    assert real["valor"].sum() == 10.0
    assert prev["valor"].sum() == 50.0
    assert meses_previstos(df, HOJE) == ["2026-11", "2026-12"]


def test_separar_com_df_vazio() -> None:
    vazio = pd.DataFrame()
    real, prev = separar_realizado_previsto(vazio, HOJE)
    assert real.empty and prev.empty
    assert meses_previstos(vazio, HOJE) == []


def test_renda_media_ignora_previsto_e_emprestimo() -> None:
    df = _df([
        {"tipo": "receita", "valor": 4000.0, "categoria": "Salário",
         "referencia_mes": "2026-09"},
        {"tipo": "receita", "valor": 6000.0, "categoria": "Salário",
         "referencia_mes": "2026-10"},
        {"tipo": "receita", "valor": 3200.0, "categoria": "Empréstimo Recebido",
         "referencia_mes": "2026-10"},
        {"tipo": "receita", "valor": 9999.0, "categoria": "Salário",
         "referencia_mes": "2026-12"},
    ])
    assert renda_media_mensal(df, HOJE) == 5000.0


def test_renda_media_sem_dados() -> None:
    assert renda_media_mensal(pd.DataFrame(), HOJE) == 0.0
    assert renda_media_mensal(None, HOJE) == 0.0
