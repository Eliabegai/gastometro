"""Alertas do topo do Dashboard."""

from __future__ import annotations

from datetime import date

import pandas as pd

from analytics.alertas import NIVEL_AVISO, NIVEL_ERRO, montar_alertas
from analytics.mes_atual import PainelMes

HOJE = date(2026, 10, 10)


def _painel(**kw) -> PainelMes:
    base = {
        "referencia_mes": "2026-10",
        "renda": 5000.0,
        "renda_estimada": False,
        "comprometido": 3000.0,
        "variavel": 1000.0,
        "cartao": 800.0,
        "dias_restantes": 22,
    }
    return PainelMes(**{**base, **kw})


def test_sem_problemas_nao_gera_alertas() -> None:
    assert montar_alertas(
        painel=_painel(), progressos=None, cobertura=None, teto_cartao=2000.0, hoje=HOJE
    ) == []


def test_mes_no_vermelho_e_teto_estourado() -> None:
    alertas = montar_alertas(
        painel=_painel(variavel=3000.0, cartao=2500.0),
        progressos=None,
        cobertura=None,
        teto_cartao=2000.0,
        hoje=HOJE,
    )
    assert [a.nivel for a in alertas] == [NIVEL_ERRO, NIVEL_ERRO]
    assert "R$ 1.000,00" in alertas[0].texto
    assert "R$ 500,00" in alertas[1].texto


def test_metas_e_cobertura_recente_apenas() -> None:
    progressos = pd.DataFrame({"status": ["estourado", "alerta", "ok"]})
    cobertura = pd.DataFrame(
        [
            {"referencia_mes": "2026-09", "status": "sem_fatura"},
            {"referencia_mes": "2024-05", "status": "diferenca"},  # antigo: ignorado
            {"referencia_mes": "2026-10", "status": "ok"},
        ]
    )
    alertas = montar_alertas(
        painel=None, progressos=progressos, cobertura=cobertura, teto_cartao=None, hoje=HOJE
    )
    assert [a.nivel for a in alertas] == [NIVEL_ERRO, NIVEL_AVISO, NIVEL_AVISO]
    assert "1 pendência(s) de fatura" in alertas[-1].texto
