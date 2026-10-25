"""Visão resumida (celular): toggle, URL e blocos exibidos."""

from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

RAIZ = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _limpar_cache() -> None:
    import streamlit as st

    st.cache_data.clear()


def _semear() -> None:
    from db.repository import upsert_fatura
    from parsers.base import Fatura, FaturaMetadata, Transacao

    upsert_fatura(
        Fatura(
            metadata=FaturaMetadata(
                banco="Banco Teste",
                titular="Eliabe",
                referencia_mes="Maio/2026",
                data_fechamento="30/04/2026",
                data_vencimento="10/05/2026",
                valor_total=42.50,
            ),
            transacoes=[
                Transacao(
                    data="12/04/2026",
                    descricao="Padaria Central",
                    parcela="",
                    cidade="Belem",
                    valor=42.50,
                    categoria="",
                ),
            ],
        ),
        arquivo="visao.pdf",
    )


def _abrir(pagina: str) -> AppTest:
    at = AppTest.from_file(str(RAIZ / pagina), default_timeout=30)
    return at


def test_dashboard_resumido_via_url_mostra_so_o_essencial(banco_temporario) -> None:
    _semear()
    completo = _abrir("app/paginas/dashboard.py").run()
    assert not completo.exception

    at = _abrir("app/paginas/dashboard.py")
    at.query_params["resumo"] = "1"
    at.run()
    assert not at.exception
    assert at.toggle[0].value is True
    # Sem grupos de despesa nem painel casal/pessoal: só os 4 KPIs.
    assert len(at.metric) == 4
    assert len(at.metric) < len(completo.metric)


def test_toggle_liga_e_desliga_o_param_da_url(banco_temporario) -> None:
    _semear()
    at = _abrir("app/paginas/dashboard.py").run()
    assert at.toggle[0].value is False

    at.toggle[0].set_value(True).run()
    assert not at.exception
    assert at.query_params.get("resumo") == ["1"] or at.query_params.get("resumo") == "1"

    at.toggle[0].set_value(False).run()
    assert not at.exception
    assert "resumo" not in at.query_params


def test_lancamentos_resumido_renderiza(banco_temporario) -> None:
    _semear()
    at = _abrir("app/paginas/lancamentos.py")
    at.query_params["resumo"] = "1"
    at.run()
    assert not at.exception
    assert at.toggle[0].value is True
