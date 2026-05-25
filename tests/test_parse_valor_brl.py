"""Testes para `parsers.base.parse_valor_brl`.

Cobre os formatos vistos nas faturas reais (Ailos usa formato americano
`1,234.56`; Nubank usa BR `1.234,56`), além das degradações comuns que
caem aqui via captura ampla de regex.
"""

from __future__ import annotations

import pytest

from parsers.base import parse_valor_brl


class TestFormatoBR:
    """Formato brasileiro clássico: ponto como milhar, vírgula decimal."""

    def test_valor_simples_sem_milhar(self):
        assert parse_valor_brl("1234,56") == pytest.approx(1234.56)

    def test_com_separador_de_milhar(self):
        assert parse_valor_brl("1.234,56") == pytest.approx(1234.56)

    def test_milhares_grandes(self):
        assert parse_valor_brl("12.345.678,90") == pytest.approx(12345678.90)

    def test_inteiro(self):
        assert parse_valor_brl("99,00") == pytest.approx(99.0)

    def test_centavos_pequenos(self):
        assert parse_valor_brl("11,67") == pytest.approx(11.67)


class TestFormatoAmericano:
    """Formato americano (vírgula milhar, ponto decimal) — usado na Ailos."""

    def test_valor_com_milhar(self):
        assert parse_valor_brl("1,234.56") == pytest.approx(1234.56)

    def test_caso_real_fatura_ailos(self):
        assert parse_valor_brl("4,422.81") == pytest.approx(4422.81)

    def test_sem_milhar(self):
        assert parse_valor_brl("99.94") == pytest.approx(99.94)


class TestSimboloRS:
    """O símbolo `R$` (com ou sem espaço) é descartado."""

    def test_com_espaco(self):
        assert parse_valor_brl("R$ 1.234,56") == pytest.approx(1234.56)

    def test_sem_espaco(self):
        assert parse_valor_brl("R$1.234,56") == pytest.approx(1234.56)


class TestNegativos:
    """Estornos vêm como `-R$ X,XX` ou usam o sinal unicode `\u2212`."""

    def test_menos_simples(self):
        assert parse_valor_brl("-50,00") == pytest.approx(-50.0)

    def test_menos_com_simbolo(self):
        assert parse_valor_brl("-R$ 50,00") == pytest.approx(-50.0)

    def test_unicode_minus(self):
        assert parse_valor_brl("\u22125,00") == pytest.approx(-5.0)

    def test_caso_real_estorno_ailos(self):
        assert parse_valor_brl("-R$ 39,99") == pytest.approx(-39.99)


class TestTrailingPontuacao:
    """Capturas amplas por regex podem incluir `.` ou `,` no final."""

    def test_ponto_no_fim(self):
        assert parse_valor_brl("4,422.81.") == pytest.approx(4422.81)

    def test_virgula_no_fim(self):
        assert parse_valor_brl("1.234,56,") == pytest.approx(1234.56)

    def test_multiplas_pontuacoes_no_fim(self):
        assert parse_valor_brl("99,00,.,") == pytest.approx(99.0)


class TestInvalidos:
    """Entradas que não dá para interpretar como número."""

    def test_none(self):
        assert parse_valor_brl(None) is None

    def test_string_vazia(self):
        assert parse_valor_brl("") is None

    def test_so_simbolo(self):
        assert parse_valor_brl("R$") is None

    def test_so_espacos(self):
        assert parse_valor_brl("   ") is None

    def test_texto_arbitrario(self):
        assert parse_valor_brl("abc") is None

    def test_so_pontuacao(self):
        # `.,` vira string vazia após rstrip; retorna None.
        assert parse_valor_brl(".,") is None


class TestZero:
    """Zero é valor válido (fatura com Total a pagar R$ 0,00)."""

    def test_zero_brl(self):
        assert parse_valor_brl("0,00") == pytest.approx(0.0)

    def test_zero_us(self):
        assert parse_valor_brl("0.00") == pytest.approx(0.0)
