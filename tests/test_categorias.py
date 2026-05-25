"""Testes para a categorização (`categorias.categorizar`).

Cobre:
  - Casos positivos para cada categoria do dicionário (smoke por
    categoria).
  - Boundary semântico: `raia` não casa `RAIANE`; `big` não casa
    `BIGODE`.
  - Prefix match com `*`: `posto*` casa `POSTOZ19`; `shell*` casa
    `SHELLBO`.
  - Regras negativas com `!`: `mercado` casa "Mercado" mas
    `MERCADO PAGO` não.
  - Overrides do usuário (`categorias_usuario.json`) têm precedência
    sobre o dicionário.
  - `categorizar_pelo_dicionario` ignora overrides.
  - `salvar_categorias_usuario` persiste, normaliza e roda
    cache-clear.
"""

from __future__ import annotations

import json

import pytest

import categorias
from categorias import (
    categorizar,
    categorizar_pelo_dicionario,
    salvar_categorias_usuario,
)


# ---------------------------------------------------------------------------
# Smoke por categoria — pelo menos 2 positivos por categoria
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "descricao, esperado",
    [
        # Combustível
        ("POSTO IPIRANGA AVENIDA", "Combustível"),
        ("SHELL SELECT", "Combustível"),
        ("POSTOZ19 COMBUSTIVEIS", "Combustível"),
        ("PETROBRAS BR MANIA", "Combustível"),
        # Mercado
        ("SUPERMERCADO ANGELONI", "Mercado"),
        ("CARREFOUR HIPER", "Mercado"),
        ("ATACADAO LIMEIRA", "Mercado"),
        ("KOMPRAO ATACADISTA", "Mercado"),
        # Alimentação
        ("RESTAURANTE TIO SAM", "Alimentação"),
        ("MCDONALD'S BR", "Alimentação"),
        ("IFD*HAMBURGUERIA", "Alimentação"),
        ("BIGODE LANCHES", "Alimentação"),  # `lanch*` casa
        ("PIZZARIA DO ZE", "Alimentação"),
        ("TECNOPAN FIGUEIRA", "Alimentação"),
        # Farmácia
        ("DROGARIA RAIA 419", "Farmácia"),
        ("DROGASIL FILIAL", "Farmácia"),
        ("PANVEL CENTRO", "Farmácia"),
        # Saúde
        ("HOSPITAL SAO LUCAS", "Saúde"),
        ("CLINICA UNIODONTO", "Saúde"),
        ("UNIMED PLANO", "Saúde"),
        # Lazer
        ("CINEMARK SHOPPING", "Lazer"),
        # Assinatura Digital
        ("NETFLIX.COM", "Assinatura Digital"),
        ("SPOTIFY P*123", "Assinatura Digital"),
        # Compra Digital
        ("AMAZON BR PRIME", "Compra Digital"),
        ("SHOPEE BRASIL", "Compra Digital"),
        ("MERCADO PAGO COMPRA", "Compra Digital"),
        # Vestuário
        ("RENNER LOJA 12", "Vestuário"),
        ("CALCADOS ITAPUA", "Vestuário"),
        # Manutenção Carro
        ("MECANICA DO JOAO", "Manutenção Carro"),
        ("OFICINA RAIANE", "Manutenção Carro"),
        # Transporte
        ("UBER *TRIP", "Transporte"),
        ("ESTAPAR ESTACIONAMENTO", "Transporte"),
        # Casa e Construção
        ("LEROY MERLIN", "Casa e Construção"),
        ("CASA DOS TUBOS", "Casa e Construção"),
        # Educação
        ("UDEMY *CURSO PYTHON", "Educação"),
        ("DESCOMPLICA EDUCACAO", "Educação"),
        # Seguro
        ("MAPFRE SEGUROS", "Seguro"),
        ("SEGURO RESIDENCIAL", "Seguro"),
        # Serviços / Assinaturas
        ("ANUIDADE DIFERENCIADA", "Serviços / Assinaturas"),
        ("TARIFA BANCARIA", "Serviços / Assinaturas"),
    ],
)
def test_categorias_positivas(descricao, esperado):
    assert categorizar(descricao) == esperado


# ---------------------------------------------------------------------------
# Boundary semântico — keyword não pode virar substring acidental
# ---------------------------------------------------------------------------


class TestBoundarySemantico:
    def test_raia_nao_casa_raiane(self):
        # `raia` (estrito) não pode virar substring de `RAIANE`.
        assert categorizar("RAIANE OFICINA") != "Farmácia"

    def test_raia_casa_raia419(self):
        # Permitir dígito logo depois (`RAIA419`) é necessário para
        # capturar lojas reais (`DROGARIA RAIA 419`).
        assert categorizar("DROGARIA RAIA419") == "Farmácia"

    def test_big_nao_casa_bigode(self):
        # `big` é uma keyword arriscada — não pode virar substring de
        # `BIGODE LANCHES` (que deve cair em Alimentação).
        assert categorizar("BIGODE LANCHES") == "Alimentação"

    def test_mercado_nao_casa_eomercado(self):
        # O boundary inicial precisa bloquear letra antes da keyword.
        assert categorizar("EOMERCADO XPTO") == "Outros Gastos"


# ---------------------------------------------------------------------------
# Prefix match `*`
# ---------------------------------------------------------------------------


class TestPrefixMatch:
    def test_posto_casa_postoz19(self):
        assert categorizar("POSTOZ19 COMBUSTIVEIS") == "Combustível"

    def test_shell_casa_shellbo(self):
        # `shell*` deve casar marcas grudadas (`SHELLBO`).
        assert categorizar("SHELLBO ESTRADA") == "Combustível"

    def test_lanch_casa_lanchonete(self):
        assert categorizar("LANCHONETE DO ZE") == "Alimentação"


# ---------------------------------------------------------------------------
# Regras negativas `!`
# ---------------------------------------------------------------------------


class TestRegrasNegativas:
    def test_mercado_pago_nao_eh_mercado(self):
        # `mercado` casaria, mas `!mercado pago` na lista descarta a
        # categoria; o fallback positivo é "Compra Digital".
        assert categorizar("MERCADO PAGO BR") == "Compra Digital"

    def test_mercado_livre_nao_eh_mercado(self):
        assert categorizar("MERCADO LIVRE COMPRA") == "Compra Digital"

    def test_supermercado_continua_mercado(self):
        # `supermerc*` casa antes e nenhuma exclusão se aplica.
        assert categorizar("SUPERMERCADO ANGELONI") == "Mercado"


# ---------------------------------------------------------------------------
# Outros Gastos / fallback
# ---------------------------------------------------------------------------


class TestFallback:
    def test_descricao_vazia(self):
        assert categorizar("") == "Outros Gastos"

    def test_descricao_none(self):
        assert categorizar(None) == "Outros Gastos"  # type: ignore[arg-type]

    def test_sem_palavra_chave(self):
        assert categorizar("XPTO 12345 LTDA") == "Outros Gastos"


# ---------------------------------------------------------------------------
# Normalização (acentos, caixa, espaços)
# ---------------------------------------------------------------------------


class TestNormalizacao:
    def test_acentos_sao_ignorados(self):
        # A keyword é `farmácia*`; sem acento também tem que casar.
        assert categorizar("FARMACIA POPULAR") == "Farmácia"

    def test_caixa_baixa(self):
        assert categorizar("netflix.com") == "Assinatura Digital"

    def test_espacos_extras(self):
        assert categorizar("  IFOOD   *RESTAURANTE  ") == "Alimentação"


# ---------------------------------------------------------------------------
# Overrides do usuário
# ---------------------------------------------------------------------------


class TestOverridesDoUsuario:
    def test_override_precede_dicionario(self, tmp_path, monkeypatch):
        # Mesmo que `posto*` casaria, override força outra categoria.
        fake = tmp_path / "categorias_usuario.json"
        fake.write_text(
            json.dumps({"POSTO XPTO": "Transporte"}, ensure_ascii=False),
            encoding="utf-8",
        )
        monkeypatch.setattr(categorias, "CATEGORIAS_USUARIO_ARQUIVO", fake)
        categorias._carregar_categorias_usuario.cache_clear()

        assert categorizar("POSTO XPTO") == "Transporte"

    def test_override_normaliza_chave(self, tmp_path, monkeypatch):
        fake = tmp_path / "categorias_usuario.json"
        # Chave gravada com acento/caixa diferente; precisa casar igual.
        fake.write_text(
            json.dumps({"Padaria do Zé": "Outros Gastos"}, ensure_ascii=False),
            encoding="utf-8",
        )
        monkeypatch.setattr(categorias, "CATEGORIAS_USUARIO_ARQUIVO", fake)
        categorias._carregar_categorias_usuario.cache_clear()

        assert categorizar("PADARIA DO ZE") == "Outros Gastos"

    def test_categorizar_pelo_dicionario_ignora_overrides(
        self, tmp_path, monkeypatch
    ):
        fake = tmp_path / "categorias_usuario.json"
        fake.write_text(
            json.dumps({"POSTO XPTO": "Transporte"}, ensure_ascii=False),
            encoding="utf-8",
        )
        monkeypatch.setattr(categorias, "CATEGORIAS_USUARIO_ARQUIVO", fake)
        categorias._carregar_categorias_usuario.cache_clear()

        # Atalho que pula overrides → cai no dicionário fixo.
        assert categorizar_pelo_dicionario("POSTO XPTO") == "Combustível"

    def test_json_corrompido_nao_quebra(self, tmp_path, monkeypatch):
        fake = tmp_path / "categorias_usuario.json"
        fake.write_text("{lixo invalido", encoding="utf-8")
        monkeypatch.setattr(categorias, "CATEGORIAS_USUARIO_ARQUIVO", fake)
        categorias._carregar_categorias_usuario.cache_clear()

        # Não deve lançar; cai no dicionário fixo.
        assert categorizar("NETFLIX.COM") == "Assinatura Digital"


# ---------------------------------------------------------------------------
# salvar_categorias_usuario
# ---------------------------------------------------------------------------


class TestSalvarCategoriasUsuario:
    def test_persiste_no_disco_e_normaliza_chave(self, tmp_path, monkeypatch):
        fake = tmp_path / "categorias_usuario.json"
        monkeypatch.setattr(categorias, "CATEGORIAS_USUARIO_ARQUIVO", fake)

        salvos = salvar_categorias_usuario({"Padaria do Zé": "Alimentação"})

        assert salvos == 1
        gravado = json.loads(fake.read_text(encoding="utf-8"))
        # A chave deve ser normalizada (sem acento, lowercase, etc.).
        assert "padaria do ze" in gravado
        assert gravado["padaria do ze"] == "Alimentação"

    def test_descarta_valores_vazios(self, tmp_path, monkeypatch):
        fake = tmp_path / "categorias_usuario.json"
        monkeypatch.setattr(categorias, "CATEGORIAS_USUARIO_ARQUIVO", fake)

        salvos = salvar_categorias_usuario(
            {"valida": "Alimentação", "": "X", "vazia": "", "outra": "   "}
        )

        assert salvos == 1
        gravado = json.loads(fake.read_text(encoding="utf-8"))
        assert list(gravado.keys()) == ["valida"]

    def test_invalida_cache_apos_salvar(self, tmp_path, monkeypatch):
        fake = tmp_path / "categorias_usuario.json"
        monkeypatch.setattr(categorias, "CATEGORIAS_USUARIO_ARQUIVO", fake)

        # Primeira leitura: vazio.
        assert categorizar("NOVA DESCRICAO XPTO") == "Outros Gastos"

        # Salva override e a próxima chamada precisa enxergar.
        salvar_categorias_usuario({"NOVA DESCRICAO XPTO": "Transporte"})
        assert categorizar("NOVA DESCRICAO XPTO") == "Transporte"
