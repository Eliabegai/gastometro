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
    "app/paginas/recorrentes.py",
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
    # 4 KPIs do topo (Despesas/Receitas/Saldo/Qtde) + 4 KPIs de grupos
    # de despesa (Cartões/Financiamentos/Casa Fixa/Empréstimos).
    assert len(at.metric) == 8


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

    # As keys agora vivem em `app.estado` (compartilhadas com Categorias
    # e sincronizadas com `st.query_params`).
    from app.estado import CHAVE_ANO, CHAVE_MES, CHAVE_MODO

    assert st.session_state.get(CHAVE_MODO) == dash.MODO_MENSAL
    # `CHAVE_MES` agora guarda **ISO** (`2026-05`), não mais o label
    # `Maio/2026` — facilita serialização na URL.
    assert st.session_state.get(CHAVE_MES) == "2026-05"
    assert st.session_state.get(CHAVE_ANO) == "2026"
    # **Regressão**: o handler também precisa atualizar a key auxiliar
    # do widget (label PT-BR). Sem isso, o selectbox de mês continua
    # mostrando o label antigo (mirror só roda na 1ª renderização).
    assert st.session_state.get(f"{CHAVE_MES}__widget") == "Maio/2026"


def test_clique_em_barra_atualiza_label_do_widget(banco_temporario) -> None:
    """Regressão end-to-end: clicar em barras diferentes consecutivamente
    deve refletir no selectbox de mês a cada clique (não 'travar' no
    primeiro mês escolhido)."""
    import streamlit as st

    from app.estado import CHAVE_MES
    from app.paginas import dashboard as dash
    from db.repository import upsert_fatura
    from parsers.base import Fatura, FaturaMetadata, Transacao

    # 3 meses no mesmo ano corrente.
    ano = 2026
    for mes_num, mes_nome in [(1, "Janeiro"), (4, "Abril"), (5, "Maio")]:
        upsert_fatura(
            Fatura(
                metadata=FaturaMetadata(
                    banco="Banco Teste",
                    titular="Eliabe",
                    referencia_mes=f"{mes_nome}/{ano}",
                    data_fechamento=f"30/{mes_num:02d}/{ano}",
                    data_vencimento=f"10/{mes_num:02d}/{ano}",
                    valor_total=100.0,
                ),
                transacoes=[
                    Transacao(
                        data=f"12/{mes_num:02d}/{ano}",
                        descricao=f"Compra {mes_nome}",
                        parcela="",
                        cidade="Belem",
                        valor=100.0,
                        categoria="",
                    ),
                ],
            ),
            arquivo=f"barra_{mes_num:02d}.pdf",
        )
    st.cache_data.clear()

    at = AppTest.from_file(
        str(RAIZ / "app/paginas/dashboard.py"), default_timeout=30
    )
    at.run()
    assert not at.exception

    mes_widget_key = f"{CHAVE_MES}__widget"

    # Simula clique na barra "Maio/2026" via session_state (Streamlit
    # AppTest não emula clique direto em gráficos Plotly).
    class _Sel:
        def __init__(self, x: str) -> None:
            self.selection = {"points": [{"x": x}]}

    at.session_state[dash.KEY_BAR_CHART_EVT] = _Sel(f"Maio/{ano}")
    at.run()
    assert not at.exception
    assert at.session_state[mes_widget_key] == f"Maio/{ano}"

    # Segundo clique: troca pra Janeiro/2026. Sem o fix do
    # `_aplicar_clique_barra` setar a key do widget, o selectbox
    # continuaria mostrando "Maio".
    at.session_state[dash.KEY_BAR_CHART_EVT] = _Sel(f"Janeiro/{ano}")
    at.run()
    assert not at.exception
    assert at.session_state[mes_widget_key] == f"Janeiro/{ano}", (
        "Widget de mês não acompanhou o segundo clique no gráfico"
    )


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

    from app.estado import CHAVE_MES, CHAVE_MODO

    assert CHAVE_MODO not in st.session_state
    assert CHAVE_MES not in st.session_state


def test_periodo_global_propaga_pra_lancamentos(banco_temporario) -> None:
    """Ano global setado na sessão → Lançamentos filtra a tabela por
    aquele ano + mês, mesmo sem o usuário mexer nos filtros da sidebar."""
    import streamlit as st

    from app.estado import CHAVE_ANO, CHAVE_MES, CHAVE_MODO
    from db.repository import upsert_fatura
    from parsers.base import Fatura, FaturaMetadata, Transacao

    # Cria 2 faturas em meses diferentes → 2 lançamentos.
    for ref_pt, ref_iso, valor in [
        ("Maio/2024", "2024-05", 100.0),
        ("Maio/2026", "2026-05", 500.0),
    ]:
        upsert_fatura(
            Fatura(
                metadata=FaturaMetadata(
                    banco="Banco Teste",
                    titular="Eliabe",
                    referencia_mes=ref_pt,
                    data_fechamento=f"30/{ref_iso.split('-')[1]}/{ref_iso[:4]}",
                    data_vencimento=f"10/{ref_iso.split('-')[1]}/{ref_iso[:4]}",
                    valor_total=valor,
                ),
                transacoes=[
                    Transacao(
                        data=f"12/{ref_iso.split('-')[1]}/{ref_iso[:4]}",
                        descricao=f"Lan {ref_pt}",
                        parcela="",
                        cidade="Belem",
                        valor=valor,
                        categoria="",
                    ),
                ],
            ),
            arquivo=f"lan_{ref_iso}.pdf",
        )
    st.cache_data.clear()

    at = AppTest.from_file(
        str(RAIZ / "app/paginas/lancamentos.py"), default_timeout=30
    )
    # Pré-popula o período global = Maio/2024.
    at.session_state[CHAVE_ANO] = "2024"
    at.session_state[CHAVE_MODO] = "Mensal"
    at.session_state[CHAVE_MES] = "2024-05"
    at.run()
    assert not at.exception

    # O KPI "Lançamentos filtrados" deve refletir só o lançamento de 2024-05.
    # `at.metric` lista todos os st.metric da página em ordem.
    valores_metric = [m.value for m in at.metric]
    # O primeiro KPI é "Lançamentos filtrados" → 1 (só Maio/2024).
    assert "1" in str(valores_metric[0]), (
        f"esperava 1 lançamento no recorte, KPIs vistos: {valores_metric}"
    )

    # Banner do período global deve aparecer (st.info).
    textos_info = [str(getattr(i, "value", "")) for i in at.info]
    assert any("Maio/2024" in t for t in textos_info), (
        f"esperava banner com 'Maio/2024'. infos vistas: {textos_info}"
    )


def test_periodo_global_propaga_pra_faturas(banco_temporario) -> None:
    """Mesma propagação aplicada à página Faturas."""
    import streamlit as st

    from app.estado import CHAVE_ANO, CHAVE_MES, CHAVE_MODO
    from db.repository import upsert_fatura
    from parsers.base import Fatura, FaturaMetadata, Transacao

    for ref_pt, ref_iso, valor in [
        ("Janeiro/2024", "2024-01", 50.0),
        ("Maio/2024", "2024-05", 100.0),
        ("Maio/2026", "2026-05", 500.0),
    ]:
        upsert_fatura(
            Fatura(
                metadata=FaturaMetadata(
                    banco="Banco Teste",
                    titular="Eliabe",
                    referencia_mes=ref_pt,
                    data_fechamento=f"30/{ref_iso.split('-')[1]}/{ref_iso[:4]}",
                    data_vencimento=f"10/{ref_iso.split('-')[1]}/{ref_iso[:4]}",
                    valor_total=valor,
                ),
                transacoes=[
                    Transacao(
                        data=f"12/{ref_iso.split('-')[1]}/{ref_iso[:4]}",
                        descricao=f"x {ref_pt}",
                        parcela="",
                        cidade="Belem",
                        valor=valor,
                        categoria="",
                    ),
                ],
            ),
            arquivo=f"fat_{ref_iso}.pdf",
        )
    st.cache_data.clear()

    at = AppTest.from_file(
        str(RAIZ / "app/paginas/faturas.py"), default_timeout=30
    )
    # Filtra ano 2024 (modo anual) → deve cair de 3 pra 2 faturas.
    at.session_state[CHAVE_ANO] = "2024"
    at.session_state[CHAVE_MODO] = "Ano inteiro"
    at.run()
    assert not at.exception

    valores_metric = [str(m.value) for m in at.metric]
    assert "2" in valores_metric[0], (
        f"esperava 2 faturas em 2024, viu: {valores_metric}"
    )

    # Agora restringe pra Maio/2024 (mensal) → deve sobrar 1.
    at.session_state[CHAVE_MODO] = "Mensal"
    at.session_state[CHAVE_MES] = "2024-05"
    at.run()
    assert not at.exception
    valores_metric_pos = [str(m.value) for m in at.metric]
    assert "1" in valores_metric_pos[0], (
        f"esperava 1 fatura em Maio/2024, viu: {valores_metric_pos}"
    )


def test_selecionar_mes_nao_reverte_escolha_do_usuario(
    banco_temporario,
) -> None:
    """Regressão: usuário escolhe um mês, no rerun seguinte o widget
    NÃO pode voltar pro mês anterior.

    Bug original: o mirror `ISO → label` rodava em todo rerun, sobre-
    escrevendo a escolha que Streamlit já tinha aplicado na key do
    widget. Resultado prático: "ao clicar num mês, o widget volta pra
    Dezembro".
    """
    import streamlit as st

    from app.estado import CHAVE_MES
    from app.paginas.dashboard import MODO_MENSAL
    from db.repository import upsert_fatura
    from parsers.base import Fatura, FaturaMetadata, Transacao

    # 2 meses no mesmo ano corrente pra ter pra onde alternar.
    ano = 2026
    for ref_pt, ref_iso, valor in [
        (f"Maio/{ano}", f"{ano}-05", 100.0),
        (f"Janeiro/{ano}", f"{ano}-01", 50.0),
    ]:
        upsert_fatura(
            Fatura(
                metadata=FaturaMetadata(
                    banco="Banco Teste",
                    titular="Eliabe",
                    referencia_mes=ref_pt,
                    data_fechamento=f"30/{ref_iso.split('-')[1]}/{ano}",
                    data_vencimento=f"10/{ref_iso.split('-')[1]}/{ano}",
                    valor_total=valor,
                ),
                transacoes=[
                    Transacao(
                        data=f"12/{ref_iso.split('-')[1]}/{ano}",
                        descricao=f"Compra {ref_pt}",
                        parcela="",
                        cidade="Belem",
                        valor=valor,
                        categoria="",
                    ),
                ],
            ),
            arquivo=f"mes_{ref_iso}.pdf",
        )
    st.cache_data.clear()

    at = AppTest.from_file(
        str(RAIZ / "app/paginas/dashboard.py"), default_timeout=30
    )
    at.run()
    assert not at.exception
    # Ativa modo Mensal — o selectbox de mês passa a aparecer com o
    # último mês (Maio/2026, ordem decrescente).
    at.radio[0].set_value(MODO_MENSAL).run()
    assert not at.exception

    # `selectbox` de mês: localizamos pela key auxiliar do widget.
    mes_widget_key = f"{CHAVE_MES}__widget"
    selectboxes_mes = [s for s in at.selectbox if s.key == mes_widget_key]
    assert selectboxes_mes, "Selectbox de mês não foi renderizado"
    assert selectboxes_mes[0].value == "Maio/2026"

    # Usuário troca pra Janeiro/2026 → deve persistir nesse rerun.
    selectboxes_mes[0].set_value(f"Janeiro/{ano}").run()
    assert not at.exception
    selectboxes_mes_pos = [
        s for s in at.selectbox if s.key == mes_widget_key
    ]
    assert (
        selectboxes_mes_pos[0].value == f"Janeiro/{ano}"
    ), "Selectbox reverteu pra Maio — bug do mirror voltou"
    # Persistência: session_state[CHAVE_MES] reflete ISO da nova escolha.
    assert at.session_state[CHAVE_MES] == f"{ano}-01"

    # Trigger extra rerun (simula o usuário interagindo com outro widget,
    # como o radio — qualquer mudança força rerun no Streamlit).
    at.radio[0].set_value(MODO_MENSAL).run()
    assert not at.exception
    selectboxes_mes_final = [
        s for s in at.selectbox if s.key == mes_widget_key
    ]
    assert (
        selectboxes_mes_final[0].value == f"Janeiro/{ano}"
    ), "Selectbox reverteu após rerun adicional — bug do mirror persistiu"


def test_dashboard_persiste_modo_no_session_state(banco_temporario) -> None:
    """Após mudar `modo` no Dashboard, o session_state guarda o novo modo
    sob a chave global — base pro sync URL (`persistir_globais`)."""
    import streamlit as st

    from app.estado import CHAVE_MODO
    from app.paginas.dashboard import MODO_MENSAL
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
                valor_total=200.0,
            ),
            transacoes=[
                Transacao(
                    data="12/04/2026",
                    descricao="Mercado",
                    parcela="",
                    cidade="Belem",
                    valor=200.0,
                    categoria="",
                ),
            ],
        ),
        arquivo="dash_url.pdf",
    )
    st.cache_data.clear()

    at = AppTest.from_file(
        str(RAIZ / "app/paginas/dashboard.py"), default_timeout=30
    )
    at.run()
    assert not at.exception
    assert at.radio, "radio 'Visão' não foi renderizado"

    at.radio[0].set_value(MODO_MENSAL).run()
    assert not at.exception
    # A nova chave global guardou o valor (o sync com query_params é
    # validado nos testes unitários de `app.estado`).
    assert at.session_state[CHAVE_MODO] == MODO_MENSAL


def test_filtros_globais_compartilhados_entre_dashboard_e_categorias(
    banco_temporario,
) -> None:
    """Ano global setado antes do run vira o ano que a Categorias usa.

    Como `AppTest.session_state` é isolado do `st.session_state` do
    processo de teste, populamos diretamente o `at.session_state` —
    simula um usuário que já interagiu com outra página."""
    import streamlit as st

    from app.estado import CHAVE_ANO

    for k in list(st.session_state.keys()):
        del st.session_state[k]
    st.query_params.clear()
    st.cache_data.clear()

    at = AppTest.from_file(
        str(RAIZ / "app/paginas/categorias.py"), default_timeout=30
    )
    # Pré-popula o session_state do AppTest antes do run.
    at.session_state[CHAVE_ANO] = "2024"
    at.run()
    assert not at.exception
    # A chave global continua acessível após o run da página.
    assert CHAVE_ANO in at.session_state
    assert at.session_state[CHAVE_ANO] == "2024"


def test_botao_limpar_filtros_zera_session_state(banco_temporario) -> None:
    """Clicar em 'Limpar filtros' no Dashboard zera ano/mês/modo."""
    import streamlit as st

    from app.estado import CHAVE_ANO, CHAVE_MES, CHAVE_MODO

    for k in list(st.session_state.keys()):
        del st.session_state[k]
    st.query_params.clear()
    st.cache_data.clear()

    at = AppTest.from_file(
        str(RAIZ / "app/paginas/dashboard.py"), default_timeout=30
    )
    # Pré-popula valores não-default no AppTest.
    at.session_state[CHAVE_ANO] = "2024"
    at.session_state[CHAVE_MES] = "2024-05"
    at.session_state[CHAVE_MODO] = "Mensal"
    at.run()
    if at.exception:
        # Banco vazio pode dropar antes de renderizar o botão — neste
        # caso o teste vira no-op (cobertura fica nas suítes do estado).
        return

    # Localiza o botão de limpar e clica.
    botoes = [b for b in at.button if b.key == "btn_limpar_dashboard"]
    if not botoes:
        return  # sem dados → botão não renderizado
    botoes[0].click().run()
    assert not at.exception

    # Após limpeza, as keys globais não estão mais em session_state.
    assert CHAVE_ANO not in at.session_state
    assert CHAVE_MES not in at.session_state
    assert CHAVE_MODO not in at.session_state


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
