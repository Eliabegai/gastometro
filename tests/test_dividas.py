"""Testes do estoque de dívidas e do destruidor (avalanche / snowball)."""

from __future__ import annotations

import pandas as pd

from analytics.dividas import (
    ESTRATEGIA_AVALANCHE,
    ESTRATEGIA_SNOWBALL,
    cenarios_extra,
    comparar_estrategias,
    credor_do_nome,
    indexador_padrao_tipo,
    prazo_price_meses,
    resumo_estoque,
    rotulo_tipo_divida,
    simular_estrategia,
    sistema_padrao_tipo,
    sugerir_a_partir_de_recorrentes,
)
from db.models import TIPO_DIVIDA_IMOVEL, TIPO_DIVIDA_PESSOAL, TIPO_DIVIDA_VEICULO


def _df(registros: list[dict]) -> pd.DataFrame:
    base = {
        "status": "ativa",
        "taxa_juros_aa": 0.0,
        "parcela_mensal": 100.0,
        "tipo": TIPO_DIVIDA_PESSOAL,
        "id": 1,
    }
    linhas = []
    for i, r in enumerate(registros, start=1):
        row = {**base, "id": i, **r}
        linhas.append(row)
    return pd.DataFrame(linhas)


def test_resumo_estoque_pondera_taxa_pelo_saldo():
    df = _df(
        [
            {"nome": "A", "saldo": 1000, "taxa_juros_aa": 10, "parcela_mensal": 50},
            {"nome": "B", "saldo": 3000, "taxa_juros_aa": 20, "parcela_mensal": 150},
        ]
    )
    resumo = resumo_estoque(df)
    assert resumo["qtde"] == 2
    assert resumo["saldo"] == 4000
    assert resumo["parcela"] == 200
    assert abs(resumo["taxa_media"] - 17.5) < 1e-9


def test_avalanche_quita_maior_juros_primeiro():
    df = _df(
        [
            {
                "nome": "Caro",
                "saldo": 5000,
                "taxa_juros_aa": 24,
                "parcela_mensal": 50,
            },
            {
                "nome": "Barato",
                "saldo": 800,
                "taxa_juros_aa": 8,
                "parcela_mensal": 20,
            },
        ]
    )
    avalanche = simular_estrategia(df, extra_mensal=150, estrategia=ESTRATEGIA_AVALANCHE)
    snowball = simular_estrategia(df, extra_mensal=150, estrategia=ESTRATEGIA_SNOWBALL)
    assert avalanche.viavel
    assert snowball.viavel
    assert avalanche.ordem[0] == "Caro"
    assert snowball.ordem[0] == "Barato"
    assert avalanche.juros_totais <= snowball.juros_totais + 0.05


def test_extra_encurta_o_prazo():
    df = _df(
        [
            {
                "nome": "Empréstimo",
                "saldo": 2000,
                "taxa_juros_aa": 12,
                "parcela_mensal": 80,
            }
        ]
    )
    so_parcela = simular_estrategia(df, extra_mensal=0, estrategia=ESTRATEGIA_AVALANCHE)
    com_extra = simular_estrategia(df, extra_mensal=80, estrategia=ESTRATEGIA_AVALANCHE)
    assert com_extra.meses < so_parcela.meses
    assert com_extra.juros_totais < so_parcela.juros_totais


def test_comparar_estrategias_tem_tres_cenarios():
    df = _df(
        [
            {"nome": "A", "saldo": 1000, "taxa_juros_aa": 15, "parcela_mensal": 60},
            {"nome": "B", "saldo": 400, "taxa_juros_aa": 5, "parcela_mensal": 40},
        ]
    )
    cmp_ = comparar_estrategias(df, extra_mensal=50)
    assert set(cmp_) == {"avalanche", "snowball", "minimo"}
    assert cmp_["avalanche"].viavel
    assert cmp_["minimo"].meses >= cmp_["avalanche"].meses


def test_sugerir_recorrentes_ignora_ja_cadastradas():
    lanc = pd.DataFrame(
        [
            {
                "descricao": "Financiamento Casa - Caixa",
                "valor": 1500,
                "referencia_mes": f"2025-{m:02d}",
                "categoria": "Financiamento Casa",
                "conta": "Conta",
                "tipo": "despesa",
                "parcela": "",
            }
            for m in range(1, 5)
        ]
    )
    vazias = pd.DataFrame()
    sug = sugerir_a_partir_de_recorrentes(lanc, vazias)
    assert not sug.empty
    assert sug.iloc[0]["tipo"] == TIPO_DIVIDA_IMOVEL
    assert sug.iloc[0]["credor"] == "Caixa"
    assert sug.iloc[0]["sistema_amortizacao"] == "sac"

    ja = pd.DataFrame([{"nome": sug.iloc[0]["nome"]}])
    assert sugerir_a_partir_de_recorrentes(lanc, ja).empty


def test_rotulo_tipo_conhecido():
    assert "imóvel" in rotulo_tipo_divida(TIPO_DIVIDA_IMOVEL).lower()
    assert "veículo" in rotulo_tipo_divida(TIPO_DIVIDA_VEICULO).lower()


def test_credor_e_defaults_por_tipo():
    assert credor_do_nome("Financiamento Casa - Caixa") == "Caixa"
    assert credor_do_nome("Empréstimo Nubank (parcela)") == ""
    assert sistema_padrao_tipo(TIPO_DIVIDA_IMOVEL) == "sac"
    assert sistema_padrao_tipo(TIPO_DIVIDA_VEICULO) == "price"
    assert sistema_padrao_tipo("cartao_credito") == "rotativo"
    assert indexador_padrao_tipo(TIPO_DIVIDA_IMOVEL) == "tr"
    assert indexador_padrao_tipo(TIPO_DIVIDA_PESSOAL) == "pre"


def test_prazo_price_meses():
    assert prazo_price_meses(1000, 0, 100) == 10
    assert prazo_price_meses(0, 12, 100) == 0
    assert prazo_price_meses(1000, 12, 1) is None
    n = prazo_price_meses(1000, 12, 100)
    assert n is not None and n >= 10


def test_cenarios_extra_encurta_com_mais_pagamento():
    df = _df(
        [
            {
                "nome": "Empréstimo",
                "saldo": 2000,
                "taxa_juros_aa": 12,
                "parcela_mensal": 80,
            }
        ]
    )
    cenario = cenarios_extra(df, [0, 80, 80], estrategia=ESTRATEGIA_AVALANCHE)
    assert len(cenario) == 2
    zero = cenario[cenario["extra"] == 0].iloc[0]
    extra = cenario[cenario["extra"] == 80].iloc[0]
    assert extra["viavel"]
    assert extra["meses"] < zero["meses"]
    assert extra["juros"] < zero["juros"]


def test_crud_divida_no_banco(banco_temporario):
    from db.repository import (
        excluir_divida,
        listar_dividas_df,
        marcar_divida_quitada,
        salvar_divida,
    )

    did = salvar_divida(
        nome="Financiamento do carro",
        tipo=TIPO_DIVIDA_VEICULO,
        credor="Banco X",
        saldo=40000,
        taxa_juros_aa=18.5,
        parcela_mensal=1200,
    )
    assert did is not None
    df = listar_dividas_df()
    assert len(df) == 1
    assert df.iloc[0]["nome"] == "Financiamento do carro"
    assert float(df.iloc[0]["saldo"]) == 40000

    salvar_divida(
        divida_id=did,
        nome="Financiamento do carro",
        tipo=TIPO_DIVIDA_VEICULO,
        saldo=38000,
        parcela_mensal=1200,
        taxa_juros_aa=18.5,
    )
    df = listar_dividas_df()
    assert float(df.iloc[0]["saldo"]) == 38000

    marcar_divida_quitada(did)
    assert listar_dividas_df().empty
    quitadas = listar_dividas_df(incluir_quitadas=True)
    assert len(quitadas) == 1
    assert quitadas.iloc[0]["status"] == "quitada"

    excluir_divida(did)
    assert listar_dividas_df(incluir_quitadas=True).empty
