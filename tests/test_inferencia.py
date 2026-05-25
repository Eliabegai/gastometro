"""Testes para `referencia_pelo_vencimento`, `ano_do_vencimento` e
`inferir_ano_transacao`.

Cobre os pontos críticos: virada de ano em faturas de janeiro, parcelas
longas que cruzam o ano (caso real `MAPFRE 14 JAN 16/18` em fatura de
maio/2026 → compra original em 2025) e os comportamentos diferentes
entre Ailos (usa data da compra) e Nubank (usa data da cobrança).
"""

from __future__ import annotations

from parsers.base import (
    ano_do_vencimento,
    inferir_ano_transacao,
    referencia_pelo_vencimento,
)


class TestReferenciaPeloVencimento:
    def test_janeiro(self):
        assert referencia_pelo_vencimento("10/01/2026") == "Janeiro/2026"

    def test_dezembro(self):
        assert referencia_pelo_vencimento("10/12/2025") == "Dezembro/2025"

    def test_maio(self):
        assert referencia_pelo_vencimento("06/05/2026") == "Maio/2026"

    def test_formato_invalido_devolve_string_vazia(self):
        assert referencia_pelo_vencimento("xx/yy/zzzz") == ""

    def test_string_vazia(self):
        assert referencia_pelo_vencimento("") == ""


class TestAnoDoVencimento:
    def test_ano_explicito(self):
        assert ano_do_vencimento("10/05/2026") == 2026

    def test_ano_passado(self):
        assert ano_do_vencimento("10/01/2024") == 2024

    def test_formato_invalido_cai_no_ano_atual(self):
        # Não checamos o valor exato (depende de date.today()), só que
        # devolve algo entre 2024 e 2100.
        ano = ano_do_vencimento("xxxxxx")
        assert 2024 <= ano <= 2100


class TestInferirAnoSemRecuoPorParcela:
    """Regra base (sem recuo): se mês_transacao > mês_vencimento, é ano
    anterior — caso comum de compras de dezembro na fatura de janeiro.
    """

    def test_dezembro_em_fatura_de_janeiro(self):
        # Compra em dezembro, fatura vence em janeiro/2026 → 2025.
        assert inferir_ano_transacao(12, "10/01/2026") == 2025

    def test_novembro_em_fatura_de_janeiro(self):
        assert inferir_ano_transacao(11, "10/01/2026") == 2025

    def test_mesmo_mes_do_vencimento(self):
        # Compra em maio, fatura vence em maio/2026 → 2026.
        assert inferir_ano_transacao(5, "06/05/2026") == 2026

    def test_mes_anterior_ao_vencimento(self):
        # Compra em abril, fatura vence em maio/2026 → 2026.
        assert inferir_ano_transacao(4, "06/05/2026") == 2026

    def test_parcela_ignorada_quando_recuo_desligado(self):
        # Comportamento esperado para Nubank: a parcela existe mas a
        # data exibida já é a da cobrança atual, então não recua.
        assert inferir_ano_transacao(5, "06/05/2026", parcela="16/18") == 2026


class TestInferirAnoComRecuoPorParcela:
    """Caso Ailos: a fatura mostra a data da compra original."""

    def test_caso_real_mapfre_16_de_18(self):
        # Fatura: 06/05/2026. Parcela 16/18 → compra feita há 15 meses
        # (janeiro/2025). Confere a regressão original.
        assert (
            inferir_ano_transacao(
                1, "06/05/2026", parcela="16/18", recuar_pelo_numero_da_parcela=True
            )
            == 2025
        )

    def test_primeira_parcela_nao_recua(self):
        # Parcela 1/N → compra no mês corrente, sem recuo.
        # Maio em fatura de maio/2026 → 2026.
        assert (
            inferir_ano_transacao(
                5, "06/05/2026", parcela="1/12", recuar_pelo_numero_da_parcela=True
            )
            == 2026
        )

    def test_segunda_parcela_recua_um_mes(self):
        # Parcela 2/N em fatura de janeiro/2026 → compra em dezembro/2025.
        assert (
            inferir_ano_transacao(
                12, "10/01/2026", parcela="2/12", recuar_pelo_numero_da_parcela=True
            )
            == 2025
        )

    def test_parcela_curta_dentro_do_mesmo_ano(self):
        # 3/12 em fatura de maio/2026 → compra em março/2026.
        assert (
            inferir_ano_transacao(
                3, "06/05/2026", parcela="3/12", recuar_pelo_numero_da_parcela=True
            )
            == 2026
        )

    def test_parcela_invalida_cai_na_regra_base(self):
        # "X/Y" malformado → ignora recuo e aplica regra base.
        assert (
            inferir_ano_transacao(
                12, "10/01/2026", parcela="abc", recuar_pelo_numero_da_parcela=True
            )
            == 2025
        )

    def test_parcela_vazia_cai_na_regra_base(self):
        assert (
            inferir_ano_transacao(
                12, "10/01/2026", parcela="", recuar_pelo_numero_da_parcela=True
            )
            == 2025
        )


class TestVencimentoInvalido:
    """Sem data de vencimento utilizável, devolve um ano plausível."""

    def test_data_vazia(self):
        ano = inferir_ano_transacao(5, "")
        assert 2024 <= ano <= 2100

    def test_data_malformada(self):
        ano = inferir_ano_transacao(5, "qualquer-coisa")
        assert 2024 <= ano <= 2100
