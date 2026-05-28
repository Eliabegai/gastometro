"""Smoke tests do app Streamlit (Fase 2).

Usa `streamlit.testing.v1.AppTest` pra rodar cada script de página
contra um banco temporário (fixture `banco_temporario`) e garante que
nenhuma exceção é levantada. Não valida pixel/HTML — só que o ciclo
de render principal não quebra.

Estes testes pegam:
  - erros de import / sintaxe
  - falhas em consultas SQL ao tocar nas páginas
  - quebras quando o banco está vazio (seed_inicial sem dados)
"""

from __future__ import annotations

from pathlib import Path

import pytest

streamlit_testing = pytest.importorskip("streamlit.testing.v1")
AppTest = streamlit_testing.AppTest

RAIZ = Path(__file__).resolve().parents[1]
PAGINAS = [
    "app/streamlit_app.py",
    "app/paginas/dashboard.py",
    "app/paginas/lancamentos.py",
    "app/paginas/faturas.py",
    "app/paginas/categorias.py",
]


def _rodar(caminho: str) -> None:
    """Roda o script e levanta `AssertionError` se houve exceção."""
    abs_path = RAIZ / caminho
    at = AppTest.from_file(str(abs_path), default_timeout=30)
    at.run()
    if at.exception:
        msgs = [str(e.value) for e in at.exception]
        raise AssertionError(
            f"Exceção(ões) rodando {caminho}: {msgs}"
        )


@pytest.mark.parametrize("pagina", PAGINAS)
def test_pagina_renderiza_com_banco_vazio(
    banco_temporario, pagina: str
) -> None:
    """Cada página deve renderizar sem erro mesmo sem lançamentos."""
    _rodar(pagina)


@pytest.mark.parametrize("pagina", PAGINAS)
def test_pagina_renderiza_com_lancamentos(
    banco_temporario, pagina: str
) -> None:
    """Mesmo cenário, mas com 3 lançamentos sintéticos inseridos."""
    from db.repository import upsert_fatura
    from parsers.base import Fatura, FaturaMetadata, Transacao

    fatura = Fatura(
        metadata=FaturaMetadata(
            banco="Banco Teste",
            titular="Eliabe",
            referencia_mes="Maio/2026",
            data_fechamento="30/04/2026",
            data_vencimento="10/05/2026",
            valor_total=457.60,
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
            Transacao(
                data="18/04/2026",
                descricao="Posto BR",
                parcela="",
                cidade="Belem",
                valor=180.00,
                categoria="",
            ),
            Transacao(
                data="05/05/2026",
                descricao="Mercado XPTO",
                parcela="",
                cidade="Belem",
                valor=235.10,
                categoria="",
            ),
        ],
    )
    upsert_fatura(fatura, arquivo="sintetico_app.pdf")

    _rodar(pagina)


def test_filtrar_por_ano() -> None:
    """`filtrar_por_ano` recorta corretamente pelo ano e respeita None."""
    from datetime import date

    import pandas as pd

    from app.helpers import filtrar_por_ano

    df = pd.DataFrame(
        {
            "data": [date(2024, 1, 1), date(2025, 6, 15), date(2026, 3, 10)],
            "valor": [100.0, 200.0, 300.0],
        }
    )
    assert len(filtrar_por_ano(df, 2025)) == 1
    assert len(filtrar_por_ano(df, 2999)) == 0
    assert len(filtrar_por_ano(df, None)) == 3


def test_ano_padrao_prefere_corrente_se_existir() -> None:
    """`ano_padrao` escolhe o ano corrente quando ele tem dados; senão
    o último ano disponível."""
    from datetime import date

    from app.helpers import ano_padrao

    atual = date.today().year
    assert ano_padrao([atual - 2, atual - 1, atual]) == atual
    # Quando o ano corrente não está, devolve o último (mais recente).
    assert ano_padrao([atual - 3, atual - 2]) == atual - 2
    assert ano_padrao([]) is None
