"""Testes do módulo `app.estado` — persistência de filtros.

Cobre:
  - Serialização / deserialização de listas em URL (separador `|`).
  - Hidratação `st.query_params` → `st.session_state` com defaults.
  - Persistência `st.session_state` → `st.query_params` idempotente.
  - Skip de hidratação quando a chave já está em `session_state`.
  - Reset (`resetar`) limpa session + URL.
  - Mapas globais e por página declarados consistentemente.

Usa o mock de `st.session_state` e `st.query_params` da fixture
`streamlit_state` (criada localmente) — não precisa de `AppTest`
porque estamos testando funções puras.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
import streamlit as st

from app import estado


@pytest.fixture(autouse=True)
def _limpar_streamlit_state() -> Iterator[None]:
    """Garante que cada teste roda com `session_state` e `query_params`
    zerados — `st.session_state` é singleton da sessão de teste."""
    for k in list(st.session_state.keys()):
        del st.session_state[k]
    st.query_params.clear()
    yield
    for k in list(st.session_state.keys()):
        del st.session_state[k]
    st.query_params.clear()


# ───────────────────────────────────────────────────────────────────
# Serialização de listas
# ───────────────────────────────────────────────────────────────────
class TestSerializacaoLista:
    def test_join_simples(self) -> None:
        assert estado.serializar_lista(["A", "B"]) == "A|B"

    def test_ignora_vazias(self) -> None:
        assert estado.serializar_lista(["A", "", "B"]) == "A|B"

    def test_lista_vazia_vira_string_vazia(self) -> None:
        assert estado.serializar_lista([]) == ""

    def test_split_basico(self) -> None:
        assert estado.deserializar_lista("A|B|C") == ["A", "B", "C"]

    def test_split_filtra_vazias(self) -> None:
        assert estado.deserializar_lista("A||B") == ["A", "B"]

    def test_split_none_vira_lista_vazia(self) -> None:
        assert estado.deserializar_lista(None) == []

    def test_split_string_vazia(self) -> None:
        assert estado.deserializar_lista("") == []

    def test_round_trip(self) -> None:
        """`serializar` → `deserializar` preserva valores não vazios."""
        original = ["Eliabe Gai", "Ana Leticia"]
        assert (
            estado.deserializar_lista(estado.serializar_lista(original))
            == original
        )


# ───────────────────────────────────────────────────────────────────
# Hidratação: URL → session_state
# ───────────────────────────────────────────────────────────────────
class TestHidratar:
    def test_popula_str(self) -> None:
        st.query_params["ano"] = "2024"
        estado.hidratar_globais()
        assert st.session_state[estado.CHAVE_ANO] == "2024"

    def test_popula_lista(self) -> None:
        st.query_params["lanc_pessoas"] = "Eliabe Gai|Ana Leticia"
        estado.hidratar_lancamentos()
        assert st.session_state[estado.CHAVE_LANC_PESSOAS] == [
            "Eliabe Gai",
            "Ana Leticia",
        ]

    def test_int_invalido_e_ignorado(self) -> None:
        """Tipo `int` declarado em mapping custom: valor lixo é ignorado
        em vez de quebrar o app."""
        mapping = {"x_int": "x"}
        tipos: dict[str, object] = {"x_int": "int"}
        st.query_params["x"] = "abc"
        estado.hidratar_session_state(mapping, tipos=tipos)  # type: ignore[arg-type]
        assert "x_int" not in st.session_state

    def test_skipa_chave_ja_em_session_state(self) -> None:
        """Não sobrescreve valor já presente — URL só semeia primeira vez."""
        st.session_state[estado.CHAVE_ANO] = "2026"
        st.query_params["ano"] = "2024"
        estado.hidratar_globais()
        assert st.session_state[estado.CHAVE_ANO] == "2026"

    def test_param_ausente_nao_cria_chave(self) -> None:
        estado.hidratar_globais()
        assert estado.CHAVE_ANO not in st.session_state
        assert estado.CHAVE_MES not in st.session_state


# ───────────────────────────────────────────────────────────────────
# Persistência: session_state → URL
# ───────────────────────────────────────────────────────────────────
class TestPersistir:
    def test_escreve_str(self) -> None:
        st.session_state[estado.CHAVE_ANO] = "2024"
        estado.persistir_globais()
        assert st.query_params["ano"] == "2024"

    def test_escreve_lista(self) -> None:
        st.session_state[estado.CHAVE_LANC_PESSOAS] = ["Eliabe", "Ana"]
        estado.persistir_lancamentos()
        assert st.query_params["lanc_pessoas"] == "Eliabe|Ana"

    def test_lista_vazia_remove_param(self) -> None:
        """Filtro zerado some da URL (em vez de virar `?lanc_pessoas=`)."""
        st.query_params["lanc_pessoas"] = "Eliabe"
        st.session_state[estado.CHAVE_LANC_PESSOAS] = []
        estado.persistir_lancamentos()
        assert "lanc_pessoas" not in st.query_params

    def test_str_vazia_remove_param(self) -> None:
        st.query_params["lanc_texto"] = "mercado"
        st.session_state[estado.CHAVE_LANC_TEXTO] = ""
        estado.persistir_lancamentos()
        assert "lanc_texto" not in st.query_params

    def test_preserva_params_de_outras_paginas(self) -> None:
        """`persistir_globais` mexe só em `ano|mes|modo` — outros params
        ficam intocados (cenário onde duas páginas escrevem na URL)."""
        st.query_params["lanc_pessoas"] = "Eliabe"
        st.session_state[estado.CHAVE_ANO] = "2024"
        estado.persistir_globais()
        assert st.query_params["ano"] == "2024"
        assert st.query_params["lanc_pessoas"] == "Eliabe"

    def test_idempotente(self) -> None:
        """Chamar 2x não muda nada (curto-circuita se não houve mudança)."""
        st.session_state[estado.CHAVE_ANO] = "2024"
        estado.persistir_globais()
        antes = dict(st.query_params)
        estado.persistir_globais()
        depois = dict(st.query_params)
        assert antes == depois


# ───────────────────────────────────────────────────────────────────
# Round-trip: gravar e ler de novo
# ───────────────────────────────────────────────────────────────────
class TestRoundTrip:
    def test_globais(self) -> None:
        st.session_state[estado.CHAVE_ANO] = "2024"
        st.session_state[estado.CHAVE_MES] = "2024-05"
        st.session_state[estado.CHAVE_MODO] = "Mensal"
        estado.persistir_globais()

        for k in list(st.session_state.keys()):
            del st.session_state[k]
        estado.hidratar_globais()

        assert st.session_state[estado.CHAVE_ANO] == "2024"
        assert st.session_state[estado.CHAVE_MES] == "2024-05"
        assert st.session_state[estado.CHAVE_MODO] == "Mensal"

    def test_lancamentos_multiselect(self) -> None:
        st.session_state[estado.CHAVE_LANC_PESSOAS] = ["Eliabe Gai", "Ana"]
        st.session_state[estado.CHAVE_LANC_CATS] = ["Mercado"]
        st.session_state[estado.CHAVE_LANC_TEXTO] = "uber"
        estado.persistir_lancamentos()

        for k in list(st.session_state.keys()):
            del st.session_state[k]
        estado.hidratar_lancamentos()

        assert st.session_state[estado.CHAVE_LANC_PESSOAS] == [
            "Eliabe Gai",
            "Ana",
        ]
        assert st.session_state[estado.CHAVE_LANC_CATS] == ["Mercado"]
        assert st.session_state[estado.CHAVE_LANC_TEXTO] == "uber"


# ───────────────────────────────────────────────────────────────────
# Reset
# ───────────────────────────────────────────────────────────────────
class TestResetar:
    def test_limpa_session_state(self) -> None:
        st.session_state[estado.CHAVE_ANO] = "2024"
        st.session_state[estado.CHAVE_MES] = "2024-05"
        estado.resetar([estado.CHAVE_ANO, estado.CHAVE_MES], [])
        assert estado.CHAVE_ANO not in st.session_state
        assert estado.CHAVE_MES not in st.session_state

    def test_limpa_url(self) -> None:
        st.query_params["ano"] = "2024"
        st.query_params["mes"] = "2024-05"
        estado.resetar([], ["ano", "mes"])
        assert "ano" not in st.query_params
        assert "mes" not in st.query_params

    def test_preserva_params_fora_da_lista(self) -> None:
        st.query_params["ano"] = "2024"
        st.query_params["mes"] = "2024-05"
        st.query_params["outra_coisa"] = "X"
        estado.resetar([], ["ano", "mes"])
        assert st.query_params["outra_coisa"] == "X"

    def test_resetar_inexistente_nao_quebra(self) -> None:
        estado.resetar(["nao_existe"], ["param_inexistente"])


# ───────────────────────────────────────────────────────────────────
# Sanidade dos mapas
# ───────────────────────────────────────────────────────────────────
# ───────────────────────────────────────────────────────────────────
# Filtro de período global aplicado a um DataFrame
# ───────────────────────────────────────────────────────────────────
class TestPeriodoGlobal:
    """Cobre `filtrar_por_periodo_global` em `app.helpers`."""

    @pytest.fixture()
    def df(self):
        import pandas as pd

        return pd.DataFrame(
            [
                {"data": "2024-01-15", "referencia_mes": "2024-01", "valor": 10},
                {"data": "2024-05-15", "referencia_mes": "2024-05", "valor": 20},
                {"data": "2024-12-15", "referencia_mes": "2024-12", "valor": 30},
                {"data": "2026-05-15", "referencia_mes": "2026-05", "valor": 40},
            ]
        )

    def test_sem_filtro_retorna_df_intocado(self, df):
        from app.helpers import filtrar_por_periodo_global

        # session_state vazio (autouse fixture limpa antes do teste).
        resultado = filtrar_por_periodo_global(df)
        assert len(resultado) == 4

    def test_filtra_apenas_por_ano(self, df):
        from app.helpers import filtrar_por_periodo_global

        st.session_state[estado.CHAVE_ANO] = "2024"
        resultado = filtrar_por_periodo_global(df)
        assert len(resultado) == 3
        assert all(str(d).startswith("2024-") for d in resultado["data"])

    def test_modo_mensal_filtra_ano_e_mes(self, df):
        from app.helpers import (
            MODO_GLOBAL_MENSAL,
            filtrar_por_periodo_global,
        )

        st.session_state[estado.CHAVE_ANO] = "2024"
        st.session_state[estado.CHAVE_MODO] = MODO_GLOBAL_MENSAL
        st.session_state[estado.CHAVE_MES] = "2024-05"
        resultado = filtrar_por_periodo_global(df)
        assert len(resultado) == 1
        assert resultado["referencia_mes"].iloc[0] == "2024-05"

    def test_modo_mensal_sem_mes_filtra_so_ano(self, df):
        """Se modo=Mensal mas mês não setado, comporta como anual."""
        from app.helpers import (
            MODO_GLOBAL_MENSAL,
            filtrar_por_periodo_global,
        )

        st.session_state[estado.CHAVE_ANO] = "2024"
        st.session_state[estado.CHAVE_MODO] = MODO_GLOBAL_MENSAL
        resultado = filtrar_por_periodo_global(df)
        assert len(resultado) == 3

    def test_ano_todos_nao_filtra(self, df):
        from app.helpers import OPCAO_TODOS_ANOS, filtrar_por_periodo_global

        st.session_state[estado.CHAVE_ANO] = OPCAO_TODOS_ANOS
        resultado = filtrar_por_periodo_global(df)
        assert len(resultado) == 4

    def test_df_vazio_retorna_df_vazio(self):
        import pandas as pd

        from app.helpers import filtrar_por_periodo_global

        st.session_state[estado.CHAVE_ANO] = "2024"
        vazio = pd.DataFrame()
        resultado = filtrar_por_periodo_global(vazio)
        assert resultado.empty


class TestRotuloPeriodo:
    """Texto PT-BR mostrado no banner ('Maio/2024', 'ano 2024', etc.)."""

    def test_sem_filtro(self) -> None:
        from app.helpers import periodo_global_ativo, rotulo_periodo_global

        assert rotulo_periodo_global() == "todo o histórico"
        assert periodo_global_ativo() is False

    def test_apenas_ano(self) -> None:
        from app.helpers import periodo_global_ativo, rotulo_periodo_global

        st.session_state[estado.CHAVE_ANO] = "2024"
        assert rotulo_periodo_global() == "ano 2024"
        assert periodo_global_ativo() is True

    def test_mensal_com_mes(self) -> None:
        from app.helpers import (
            MODO_GLOBAL_MENSAL,
            rotulo_periodo_global,
        )

        st.session_state[estado.CHAVE_ANO] = "2024"
        st.session_state[estado.CHAVE_MODO] = MODO_GLOBAL_MENSAL
        st.session_state[estado.CHAVE_MES] = "2024-05"
        assert rotulo_periodo_global() == "Maio/2024"


class TestMapas:
    def test_chaves_globais_estao_no_mapa(self) -> None:
        for chave in estado.CHAVES_GLOBAIS:
            assert chave in estado.MAPA_GLOBAIS

    def test_todas_globais_tem_tipo(self) -> None:
        for chave in estado.MAPA_GLOBAIS:
            assert chave in estado.TIPOS_GLOBAIS

    def test_todas_lancamentos_tem_tipo(self) -> None:
        for chave in estado.MAPA_LANCAMENTOS:
            assert chave in estado.TIPOS_LANCAMENTOS

    def test_params_url_unicos(self) -> None:
        """Nenhum param da URL aparece nos dois mapas (evita colisão)."""
        intersec = set(estado.MAPA_GLOBAIS.values()) & set(
            estado.MAPA_LANCAMENTOS.values()
        )
        assert intersec == set()
