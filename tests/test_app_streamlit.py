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
    "app/paginas/importar.py",
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


def test_categorias_alterna_para_visao_mensal(banco_temporario) -> None:
    """Categorias também respeita o toggle Ano × Mensal."""
    import streamlit as st

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
        arquivo="cat_mensal.pdf",
    )
    st.cache_data.clear()

    at = AppTest.from_file(
        str(RAIZ / "app/paginas/categorias.py"), default_timeout=30
    )
    at.run()
    assert not at.exception
    assert at.radio, "radio 'Visão' não foi renderizado em Categorias"

    at.radio[0].set_value("Mensal").run()
    assert not at.exception
    # Modo mensal acrescenta o selectbox de mês ao seletor de ano.
    valores = [s.value for s in at.selectbox]
    assert "2026" in valores, valores
    assert any("/2026" in str(v) for v in valores), valores


def test_dashboard_alterna_para_visao_mensal(banco_temporario) -> None:
    """Trocar o radio 'Visão' pra 'Mensal' não pode quebrar o render.

    Cobre o fluxo completo: ano default → modo mensal → seletor de mês
    aparece com o último mês com dados.
    """
    import streamlit as st

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
        arquivo="dash_mensal.pdf",
    )
    # Limpa o cache pra não pegar leituras vazias dos testes anteriores.
    st.cache_data.clear()

    at = AppTest.from_file(
        str(RAIZ / "app/paginas/dashboard.py"), default_timeout=30
    )
    at.run()
    assert not at.exception
    assert at.radio, "radio 'Visão' não foi renderizado"

    at.radio[0].set_value("Mensal").run()
    assert not at.exception
    # Ano (1) + Mês (1) = 2 selectboxes no modo mensal
    assert len(at.selectbox) == 2
    assert len(at.metric) == 4


def test_importar_pdf_via_uploader(banco_temporario, tmp_path) -> None:
    """`_processar_uploads` integra parser → banco → Excel (opcional).

    Usa um PDF real de `entrada/` se existir; senão pula. Cobre o
    caminho `arquivar=False` (arquivo temporário) pra não poluir
    `entrada/` durante testes.
    """
    pdfs = list((RAIZ / "entrada").glob("*.pdf"))
    if not pdfs:
        pytest.skip("Nenhum PDF em entrada/ pra testar upload real.")

    pdf_real = pdfs[0]

    class _UploadFake:
        def __init__(self, path: Path) -> None:
            self.name = path.name
            self._data = path.read_bytes()

        def getvalue(self) -> bytes:
            return self._data

    from app.paginas._importar_pdfs import _processar_uploads

    resultados, caminho_excel = _processar_uploads(
        [_UploadFake(pdf_real)],
        arquivar=False,
        regerar_xlsx=False,
    )

    assert len(resultados) == 1
    r = resultados[0]
    assert r["arquivo"] == pdf_real.name
    # PDF real precisa ter sido reconhecido (status != "erro" e banco preenchido).
    assert r["status"] in {"novo", "ja_no_banco"}, r
    assert r["banco"], "banco não foi detectado pelo parser"
    # Como o banco do teste começa vazio, o primeiro upload sempre é 'novo'.
    assert r["status"] == "novo"
    assert r["novos"] > 0
    assert caminho_excel is None  # regerar_xlsx=False


def test_importar_pdf_idempotente(banco_temporario) -> None:
    """Subir o mesmo PDF 2x não duplica lançamentos (`status='ja_no_banco'`)."""
    pdfs = list((RAIZ / "entrada").glob("*.pdf"))
    if not pdfs:
        pytest.skip("Nenhum PDF em entrada/ pra testar upload real.")

    pdf_real = pdfs[0]

    class _UploadFake:
        def __init__(self, path: Path) -> None:
            self.name = path.name
            self._data = path.read_bytes()

        def getvalue(self) -> bytes:
            return self._data

    from app.paginas._importar_pdfs import _processar_uploads

    r1, _ = _processar_uploads(
        [_UploadFake(pdf_real)], arquivar=False, regerar_xlsx=False
    )
    r2, _ = _processar_uploads(
        [_UploadFake(pdf_real)], arquivar=False, regerar_xlsx=False
    )
    assert r1[0]["status"] == "novo"
    assert r2[0]["status"] == "ja_no_banco"
    assert r2[0]["novos"] == 0


def test_clique_em_barra_ativa_modo_mensal() -> None:
    """Quando o usuário clica numa barra do gráfico, o handler
    `_aplicar_clique_barra` deve preparar o `st.session_state` pra que o
    próximo run renderize o modo Mensal com o mês clicado já selecionado.
    """
    import pandas as pd
    import streamlit as st

    from app.paginas import dashboard as dash

    df = pd.DataFrame(
        [
            {
                "referencia_mes": "2026-05",
                "valor": 100.0,
                "tipo": "despesa",
                "data": "2026-05-01",
            },
            {
                "referencia_mes": "2026-04",
                "valor": 50.0,
                "tipo": "despesa",
                "data": "2026-04-01",
            },
        ]
    )

    class _SelObj:
        def __init__(self, x_label: str) -> None:
            self.selection = {"points": [{"x": x_label}]}

    for k in list(st.session_state.keys()):
        del st.session_state[k]

    st.session_state[dash.KEY_BAR_CHART_EVT] = _SelObj("Maio/2026")
    dash._aplicar_clique_barra(df)

    assert st.session_state.get("dashboard_modo") == dash.MODO_MENSAL
    assert st.session_state.get("dashboard_mes") == "Maio/2026"
    assert st.session_state.get("dashboard_ano") == "2026"


def test_sem_clique_nao_muda_session_state() -> None:
    """Sem evento de seleção (ou seleção vazia), o handler vira no-op."""
    import pandas as pd
    import streamlit as st

    from app.paginas import dashboard as dash

    df = pd.DataFrame(
        [
            {
                "referencia_mes": "2026-05",
                "valor": 100.0,
                "tipo": "despesa",
                "data": "2026-05-01",
            },
        ]
    )

    for k in list(st.session_state.keys()):
        del st.session_state[k]

    dash._aplicar_clique_barra(df)
    assert "dashboard_modo" not in st.session_state
    assert "dashboard_mes" not in st.session_state


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
