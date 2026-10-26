"""Painel "Este mês", gasto de cartão por mês e preferências."""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from analytics.mes_atual import cartao_por_mes, painel_mes, renda_recente

HOJE = date(2026, 10, 10)


def _linha(**kw) -> dict:
    base = {
        "tipo": "despesa",
        "valor": 0.0,
        "categoria": "Mercado",
        "referencia_mes": "2026-10",
        "fonte": "pdf",
        "parcela": "",
        "conta_tipo": "cartao_credito",
    }
    return {**base, **kw}


def _df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            _linha(tipo="receita", valor=5000.0, categoria="Salário", conta_tipo="corrente"),
            _linha(valor=1500.0, fonte="planilha_historico", conta_tipo="corrente"),
            _linha(valor=300.0, parcela="02/10"),
            _linha(valor=700.0),
            _linha(tipo="estorno", valor=-100.0),
        ]
    )


def test_painel_separa_comprometido_e_variavel() -> None:
    p = painel_mes(_df(), HOJE)
    assert p is not None
    assert p.renda == 5000.0 and not p.renda_estimada
    assert p.comprometido == 1800.0  # planilha + parcela
    assert p.variavel == pytest.approx(600.0)  # 700 − 100 estorno
    assert p.disponivel == pytest.approx(5000 - 1800 - 600)
    assert p.dias_restantes == 22
    assert p.por_dia == pytest.approx(p.disponivel / 22)


def test_painel_no_vermelho_nao_tem_por_dia() -> None:
    df = pd.DataFrame([_linha(valor=900.0), _linha(tipo="receita", valor=100.0, categoria="Salário")])
    p = painel_mes(df, HOJE)
    assert p is not None and p.disponivel < 0 and p.por_dia == 0.0


def test_painel_usa_renda_media_quando_salario_nao_entrou() -> None:
    df = pd.DataFrame(
        [
            _linha(tipo="receita", valor=4000.0, categoria="Salário", referencia_mes="2026-08"),
            _linha(tipo="receita", valor=6000.0, categoria="Salário", referencia_mes="2026-09"),
            _linha(valor=500.0),
        ]
    )
    p = painel_mes(df, HOJE)
    assert p is not None and p.renda_estimada and p.renda == 5000.0
    assert renda_recente(df, HOJE) == 5000.0


def test_painel_sem_lancamentos_no_mes_corrente() -> None:
    df = pd.DataFrame([_linha(referencia_mes="2026-09", valor=10.0)])
    assert painel_mes(df, HOJE) is None
    assert painel_mes(pd.DataFrame(), HOJE) is None


def test_cartao_por_mes_so_cartao_e_liquido() -> None:
    cartao = cartao_por_mes(_df())
    assert cartao["referencia_mes"].tolist() == ["2026-10"]
    assert cartao["valor"].iloc[0] == pytest.approx(900.0)  # 300 + 700 − 100
    assert cartao_por_mes(pd.DataFrame()).empty


def test_preferencias_teto_cartao(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("GASTOMETRO_DADOS_DIR", str(tmp_path))
    from app.preferencias import salvar_teto_cartao, teto_cartao

    assert teto_cartao() is None
    salvar_teto_cartao(3500)
    assert teto_cartao() == 3500.0
    salvar_teto_cartao(0)
    assert teto_cartao() is None
    (tmp_path / "preferencias.json").write_text("{quebrado", encoding="utf-8")
    assert teto_cartao() is None
