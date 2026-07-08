"""Testes do `db.repository`: upsert, idempotência, dedup, override.

Usam a fixture `banco_temporario` (em `conftest.py`) que aponta o
SQLite pra um arquivo temporário por teste, isolando totalmente do
banco real do usuário.
"""

from __future__ import annotations

import pytest

from parsers.base import Fatura, FaturaMetadata, Transacao


def _fatura_demo(arquivo: str = "Fatura_Demo.pdf") -> Fatura:
    """Fatura sintética com 3 lançamentos cobrindo casos relevantes."""
    return Fatura(
        metadata=FaturaMetadata(
            banco="Demo",
            titular="Joao Silva",
            referencia_mes="Maio/2026",
            data_fechamento="05/05/2026",
            data_vencimento="12/05/2026",
            valor_total=350.0,
        ),
        transacoes=[
            Transacao(
                data="01/05/2026",
                descricao="POSTO SHELL",
                parcela="",
                cidade="Sao Paulo",
                valor=200.0,
                categoria="",
            ),
            Transacao(
                data="02/05/2026",
                descricao="LOJA PARCELADA",
                parcela="02/12",
                cidade="Sao Paulo",
                valor=100.0,
                categoria="",
            ),
            Transacao(
                data="03/05/2026",
                descricao="ESTORNO DEVOLUCAO",
                parcela="",
                cidade="Sao Paulo",
                valor=-50.0,
                categoria="",
            ),
        ],
    )


def test_upsert_fatura_grava_3_lancamentos(banco_temporario):
    """Upsert de uma fatura grava todos os lançamentos + cria conta/pessoa."""
    from db.repository import (
        listar_faturas_df,
        listar_lancamentos_df,
        upsert_fatura,
    )

    fat_id, inseridos = upsert_fatura(_fatura_demo(), arquivo="Fatura_Demo.pdf")
    assert fat_id is not None
    assert inseridos == 3

    df_lanc = listar_lancamentos_df()
    df_fat = listar_faturas_df()

    assert len(df_fat) == 1
    assert len(df_lanc) == 3
    assert df_fat["arquivo"].iloc[0] == "Fatura_Demo.pdf"
    assert df_fat["conta"].iloc[0] == "Demo — Joao Silva"
    assert df_fat["pessoa"].iloc[0] == "Joao Silva"
    assert df_fat["referencia_mes"].iloc[0] == "2026-05"


def test_upsert_fatura_pessoa_override_vincula_a_existente(banco_temporario):
    """`pessoa_override` força o cartão a ser vinculado a uma pessoa
    existente, ignorando o titular do PDF. Evita criar `Pessoa`
    duplicada quando o PDF traz a grafia errada."""
    from sqlmodel import select as sql_select

    from db.engine import get_session
    from db.models import Pessoa
    from db.repository import listar_faturas_df, upsert_fatura

    # Pessoa canônica já existe.
    with get_session() as s:
        s.add(Pessoa(nome="Joao Silva Canonico"))

    fat_id, inseridos = upsert_fatura(
        _fatura_demo(),
        arquivo="Fatura_Demo.pdf",
        pessoa_override="Joao Silva Canonico",
    )
    assert fat_id is not None
    assert inseridos == 3

    df_fat = listar_faturas_df()
    assert df_fat["pessoa"].iloc[0] == "Joao Silva Canonico"
    assert df_fat["conta"].iloc[0] == "Demo — Joao Silva Canonico"

    # `Pessoa(nome="Joao Silva")` do PDF NÃO foi criada — só a canônica
    # sobrevive (+ as do seed_inicial).
    with get_session() as s:
        joao_pdf = s.exec(
            sql_select(Pessoa).where(Pessoa.nome == "Joao Silva")
        ).first()
        assert joao_pdf is None


def test_upsert_fatura_idempotente(banco_temporario):
    """Re-import da mesma fatura não duplica nada (re-run safe)."""
    from db.repository import (
        listar_faturas_df,
        listar_lancamentos_df,
        upsert_fatura,
    )

    upsert_fatura(_fatura_demo(), arquivo="Fatura_Demo.pdf")
    fat_id2, inseridos2 = upsert_fatura(_fatura_demo(), arquivo="Fatura_Demo.pdf")

    assert inseridos2 == 0
    assert fat_id2 is not None
    assert len(listar_faturas_df()) == 1
    assert len(listar_lancamentos_df()) == 3


def test_hash_dedupe_diferencia_parcelas(banco_temporario):
    """Mesma desc+valor em parcelas distintas (1/12 vs 2/12) não colapsam."""
    from db.repository import listar_lancamentos_df, upsert_fatura

    fatura = Fatura(
        metadata=FaturaMetadata(
            banco="Demo",
            titular="Maria",
            referencia_mes="Maio/2026",
            data_vencimento="12/05/2026",
            valor_total=300.0,
        ),
        transacoes=[
            Transacao(
                data="01/05/2026",
                descricao="CURSO ALURA",
                parcela="01/12",
                cidade="",
                valor=100.0,
            ),
            Transacao(
                data="01/05/2026",
                descricao="CURSO ALURA",
                parcela="02/12",
                cidade="",
                valor=100.0,
            ),
            Transacao(
                data="01/05/2026",
                descricao="CURSO ALURA",
                parcela="03/12",
                cidade="",
                valor=100.0,
            ),
        ],
    )

    _, inseridos = upsert_fatura(fatura, arquivo="Parcelas.pdf")
    assert inseridos == 3
    df = listar_lancamentos_df()
    assert df["parcela"].tolist() == ["01/12", "02/12", "03/12"]


def test_estorno_grava_valor_positivo_mas_volta_negativo_no_df(banco_temporario):
    """Estornos: armazenados com valor abs; saem com sinal `-` em listar_*."""
    from db.repository import listar_lancamentos_df, upsert_fatura

    upsert_fatura(_fatura_demo(), arquivo="Fatura_Demo.pdf")

    df = listar_lancamentos_df(sinal_estorno_negativo=True)
    estornos = df[df["tipo"] == "estorno"]
    assert len(estornos) == 1
    assert estornos["valor"].iloc[0] == -50.0

    df_bruto = listar_lancamentos_df(sinal_estorno_negativo=False)
    estornos_bruto = df_bruto[df_bruto["tipo"] == "estorno"]
    assert estornos_bruto["valor"].iloc[0] == 50.0


def test_override_categoria_tem_precedencia(banco_temporario):
    """Override salvo prevalece sobre dicionário em novos lançamentos."""
    from db.repository import (
        listar_lancamentos_df,
        salvar_override,
        upsert_fatura,
    )

    salvar_override("POSTO SHELL", "Transporte")

    upsert_fatura(_fatura_demo(), arquivo="Fatura_Demo.pdf")
    df = listar_lancamentos_df()
    linha_shell = df[df["descricao"] == "POSTO SHELL"]
    assert linha_shell["categoria"].iloc[0] == "Transporte"


def test_recategorizar_aplica_overrides_no_historico(banco_temporario):
    """`recategorizar_todos()` atualiza lançamentos já gravados."""
    from db.repository import (
        listar_lancamentos_df,
        recategorizar_todos,
        salvar_override,
        upsert_fatura,
    )

    upsert_fatura(_fatura_demo(), arquivo="Fatura_Demo.pdf")
    df_antes = listar_lancamentos_df()
    cat_inicial_shell = df_antes[df_antes["descricao"] == "POSTO SHELL"][
        "categoria"
    ].iloc[0]
    assert cat_inicial_shell == "Combustível"

    salvar_override("POSTO SHELL", "Transporte")

    resultado = recategorizar_todos()
    assert resultado["mudados"] >= 1

    df_depois = listar_lancamentos_df()
    cat_final_shell = df_depois[df_depois["descricao"] == "POSTO SHELL"][
        "categoria"
    ].iloc[0]
    assert cat_final_shell == "Transporte"


def test_respeitar_categoria_existente_pula_categorizador(banco_temporario):
    """Migração legado: usa `tx.categoria` em vez de re-categorizar."""
    from db.repository import listar_lancamentos_df, upsert_fatura

    fatura = _fatura_demo()
    fatura.transacoes[0].categoria = "Categoria Manual Exotica"

    upsert_fatura(
        fatura,
        arquivo="Fatura_Demo.pdf",
        respeitar_categoria_existente=True,
    )
    df = linha = listar_lancamentos_df()
    linha = df[df["descricao"] == "POSTO SHELL"]
    assert linha["categoria"].iloc[0] == "Categoria Manual Exotica"


@pytest.mark.parametrize(
    "iso,esperado",
    [
        ("Maio/2026", "2026-05"),
        ("Janeiro/2024", "2024-01"),
        ("Dezembro/2025", "2025-12"),
        ("", None),
        ("formato-errado", None),
    ],
)
def test_parse_referencia_iso(iso, esperado):
    from db.repository import parse_referencia

    assert parse_referencia(iso) == esperado
def test_upsert_fatura_remove_planilha_duplicada(banco_temporario):
    """Importar PDF DEPOIS da planilha familiar limpa a duplicata mensal.

    Cenário do bug original: usuário importou a planilha familiar
    (que tem o agregado mensal `Fatura Nubank (mensal)` na célula de
    maio/2026) ANTES de processar o PDF. Sem o cleanup, o dashboard
    somava o agregado da planilha + o detalhe granular do PDF e
    duplicava o gasto do cartão.
    """
    from db.models import FONTE_PLANILHA, TIPO_LANCAMENTO_DESPESA
    from db.repository import (
        listar_lancamentos_df,
        upsert_fatura,
        upsert_lancamento_manual,
    )

    upsert_lancamento_manual(
        descricao="Fatura Demo (mensal)",
        valor=500.0,
        ano=2026,
        mes=5,
        categoria_nome="Cartão de Crédito",
        pessoa_nome="Joao Silva",
        conta_nome="Demo — Joao Silva",
        tipo=TIPO_LANCAMENTO_DESPESA,
        chave_planilha="Fatura Demo (mensal)",
        fonte=FONTE_PLANILHA,
        arquivo_origem="despesas_Eliabe_Ana.xlsx",
    )

    df_antes = listar_lancamentos_df()
    assert (df_antes["fonte"] == FONTE_PLANILHA).sum() == 1

    upsert_fatura(_fatura_demo(), arquivo="Fatura_Demo.pdf")

    df_depois = listar_lancamentos_df()
    # 3 do PDF, 0 da planilha (removida) + estorno volta com sinal negativo
    assert (df_depois["fonte"] == FONTE_PLANILHA).sum() == 0
    assert len(df_depois) == 3


def test_upsert_fatura_nao_toca_planilha_de_outra_conta(banco_temporario):
    """Cleanup só atinge a (conta, ref) exata do PDF — não vaza."""
    from db.models import FONTE_PLANILHA, TIPO_LANCAMENTO_DESPESA
    from db.repository import (
        listar_lancamentos_df,
        upsert_fatura,
        upsert_lancamento_manual,
    )

    # Planilha de OUTRA conta na mesma referência: tem que sobreviver.
    upsert_lancamento_manual(
        descricao="Fatura Outro Cartao (mensal)",
        valor=300.0,
        ano=2026,
        mes=5,
        categoria_nome="Cartão de Crédito",
        pessoa_nome="Ana",
        conta_nome="Outro Banco — Ana",
        tipo=TIPO_LANCAMENTO_DESPESA,
        chave_planilha="Fatura Outro Cartao (mensal)",
        fonte=FONTE_PLANILHA,
    )
    # Planilha da MESMA conta mas referência diferente: também sobrevive.
    upsert_lancamento_manual(
        descricao="Fatura Demo (mensal)",
        valor=400.0,
        ano=2026,
        mes=4,
        categoria_nome="Cartão de Crédito",
        pessoa_nome="Joao Silva",
        conta_nome="Demo — Joao Silva",
        tipo=TIPO_LANCAMENTO_DESPESA,
        chave_planilha="Fatura Demo (mensal)",
        fonte=FONTE_PLANILHA,
    )

    upsert_fatura(_fatura_demo(), arquivo="Fatura_Demo.pdf")

    df = listar_lancamentos_df()
    planilhas = df[df["fonte"] == FONTE_PLANILHA]
    assert len(planilhas) == 2  # nenhuma deletada


def test_upsert_fatura_preserva_lancamentos_manuais(banco_temporario):
    """Cleanup só toca em `fonte=planilha_historico` — manual sobrevive."""
    from db.models import FONTE_MANUAL, TIPO_LANCAMENTO_DESPESA
    from db.repository import (
        listar_lancamentos_df,
        upsert_fatura,
        upsert_lancamento_manual,
    )

    upsert_lancamento_manual(
        descricao="Ajuste manual cartão",
        valor=15.0,
        ano=2026,
        mes=5,
        categoria_nome="Cartão de Crédito",
        pessoa_nome="Joao Silva",
        conta_nome="Demo — Joao Silva",
        tipo=TIPO_LANCAMENTO_DESPESA,
        chave_planilha="ajuste-manual-unico",
        fonte=FONTE_MANUAL,
    )

    upsert_fatura(_fatura_demo(), arquivo="Fatura_Demo.pdf")

    df = listar_lancamentos_df()
    manuais = df[df["fonte"] == FONTE_MANUAL]
    assert len(manuais) == 1


def test_limpar_planilha_quando_pdf_existe_backfill(banco_temporario):
    """Backfill remove duplicatas em bancos antigos. Idempotente."""
    from db.models import FONTE_PLANILHA, TIPO_LANCAMENTO_DESPESA
    from db.repository import (
        limpar_planilha_quando_pdf_existe,
        listar_lancamentos_df,
        upsert_fatura,
        upsert_lancamento_manual,
    )

    # Simula o estado degradado: planilha gravada, mas a regra de
    # cleanup no `upsert_fatura` foi pulada (versão antiga do código).
    # Pra reproduzir, importamos a planilha DEPOIS do PDF — assim a
    # regra de skip do `importar_planilha_familiar` não roda (estamos
    # chamando `upsert_lancamento_manual` direto) e o cleanup do
    # `upsert_fatura` já passou.
    upsert_fatura(_fatura_demo(), arquivo="Fatura_Demo.pdf")
    upsert_lancamento_manual(
        descricao="Fatura Demo (mensal)",
        valor=500.0,
        ano=2026,
        mes=5,
        categoria_nome="Cartão de Crédito",
        pessoa_nome="Joao Silva",
        conta_nome="Demo — Joao Silva",
        tipo=TIPO_LANCAMENTO_DESPESA,
        chave_planilha="Fatura Demo (mensal)",
        fonte=FONTE_PLANILHA,
    )

    df_antes = listar_lancamentos_df()
    assert (df_antes["fonte"] == FONTE_PLANILHA).sum() == 1

    resultado = limpar_planilha_quando_pdf_existe()
    assert resultado["faturas_examinadas"] == 1
    assert resultado["lancamentos_removidos"] == 1

    df_depois = listar_lancamentos_df()
    assert (df_depois["fonte"] == FONTE_PLANILHA).sum() == 0

    # Idempotência: 2ª chamada não remove nada.
    resultado2 = limpar_planilha_quando_pdf_existe()
    assert resultado2["lancamentos_removidos"] == 0
def test_upsert_lancamento_manual_atualiza_valor_quando_diverge(banco_temporario):
    """Re-import da planilha com valor alterado faz UPDATE no banco.

    Cenário real: usuário edita uma célula da planilha familiar (ex.
    descobre o valor exato do mês, atualiza de 400 → 450) e roda o
    import de novo. Antes da correção, hash batia e a linha era
    pulada — o banco continuava com o valor antigo. Agora atualiza.
    """
    from db.models import TIPO_LANCAMENTO_DESPESA
    from db.repository import listar_lancamentos_df, upsert_lancamento_manual

    _, inserido1, atualizado1 = upsert_lancamento_manual(
        descricao="Luz - Celesc",
        valor=170.0,
        ano=2026,
        mes=6,
        categoria_nome="Luz",
        chave_planilha="Luz - Celesc",
        tipo=TIPO_LANCAMENTO_DESPESA,
    )
    assert inserido1 is True
    assert atualizado1 is False

    _, inserido2, atualizado2 = upsert_lancamento_manual(
        descricao="Luz - Celesc",
        valor=199.90,
        ano=2026,
        mes=6,
        categoria_nome="Luz",
        chave_planilha="Luz - Celesc",
        tipo=TIPO_LANCAMENTO_DESPESA,
    )
    assert inserido2 is False  # não é "novo"
    assert atualizado2 is True  # valor mudou → update

    df = listar_lancamentos_df()
    luz = df[df["descricao"] == "Luz - Celesc"]
    assert len(luz) == 1
    assert float(luz["valor"].iloc[0]) == 199.90


def test_upsert_lancamento_manual_preserva_categoria_em_update(banco_temporario):
    """UPDATE no valor não derruba override de categoria existente."""
    from db.models import TIPO_LANCAMENTO_DESPESA
    from db.repository import (
        listar_lancamentos_df,
        salvar_override,
        upsert_lancamento_manual,
    )

    upsert_lancamento_manual(
        descricao="Internet - Unifique",
        valor=120.0,
        ano=2026,
        mes=6,
        categoria_nome="Outros Gastos",
        chave_planilha="Internet - Unifique",
        tipo=TIPO_LANCAMENTO_DESPESA,
    )
    # User customiza a categoria manualmente.
    salvar_override("Internet - Unifique", "Internet")
    from db.repository import recategorizar_todos

    recategorizar_todos()

    # Re-import com valor novo: categoria customizada precisa ficar.
    upsert_lancamento_manual(
        descricao="Internet - Unifique",
        valor=159.90,
        ano=2026,
        mes=6,
        categoria_nome="Outros Gastos",
        chave_planilha="Internet - Unifique",
        tipo=TIPO_LANCAMENTO_DESPESA,
    )

    df = listar_lancamentos_df()
    linha = df[df["descricao"] == "Internet - Unifique"]
    assert float(linha["valor"].iloc[0]) == 159.90
    assert linha["categoria"].iloc[0] == "Internet"


def test_remover_lancamentos_planilha_por_descricao(banco_temporario):
    """Helper limpa só fonte=planilha com a descrição exata."""
    from db.models import FONTE_MANUAL, FONTE_PLANILHA, TIPO_LANCAMENTO_DESPESA
    from db.repository import (
        listar_lancamentos_df,
        remover_lancamentos_planilha_por_descricao,
        upsert_lancamento_manual,
    )

    for mes in (3, 4, 5):
        upsert_lancamento_manual(
            descricao="Moradia (mensal)",
            valor=400.0,
            ano=2026,
            mes=mes,
            categoria_nome="Moradia",
            chave_planilha="Moradia (mensal)",
            tipo=TIPO_LANCAMENTO_DESPESA,
            fonte=FONTE_PLANILHA,
        )
    # Lançamento manual com mesma descrição tem que sobreviver.
    upsert_lancamento_manual(
        descricao="Moradia (mensal)",
        valor=50.0,
        ano=2026,
        mes=6,
        categoria_nome="Moradia",
        chave_planilha="ajuste-manual",
        tipo=TIPO_LANCAMENTO_DESPESA,
        fonte=FONTE_MANUAL,
    )

    removidos = remover_lancamentos_planilha_por_descricao("Moradia (mensal)")
    assert removidos == 3

    df = listar_lancamentos_df()
    restantes = df[df["descricao"] == "Moradia (mensal)"]
    assert len(restantes) == 1
    assert restantes["fonte"].iloc[0] == FONTE_MANUAL



def test_listar_lancamentos_df_inclui_conta_tipo(banco_temporario):
    """`conta_tipo` precisa estar disponível pra o dashboard agrupar.

    PDFs criam Conta com tipo `cartao_credito` automaticamente. Sem
    essa coluna no DF, o KPI "Cartões de Crédito" não consegue somar
    sem reconsultar o banco.
    """
    from db.repository import listar_lancamentos_df, upsert_fatura

    upsert_fatura(_fatura_demo(), arquivo="Fatura_Demo.pdf")
    df = listar_lancamentos_df()
    assert "conta_tipo" in df.columns
    assert (df["conta_tipo"] == "cartao_credito").all()


def test_planilha_lancamento_herda_conta_tipo_existente(banco_temporario):
    """Quando a planilha referencia conta que já é cartão (criada pelo
    PDF), o lançamento sintético vem com `conta_tipo=cartao_credito` —
    necessário pro KPI Cartões somar as células de meses sem PDF."""
    from db.models import FONTE_PLANILHA, TIPO_LANCAMENTO_DESPESA
    from db.repository import (
        listar_lancamentos_df,
        upsert_fatura,
        upsert_lancamento_manual,
    )

    upsert_fatura(_fatura_demo(), arquivo="Fatura_Demo.pdf")
    upsert_lancamento_manual(
        descricao="Fatura Demo (mensal)",
        valor=600.0,
        ano=2026,
        mes=4,  # ref diferente do PDF — sobrevive
        categoria_nome="Cartão de Crédito",
        pessoa_nome="Joao Silva",
        conta_nome="Demo — Joao Silva",
        tipo=TIPO_LANCAMENTO_DESPESA,
        chave_planilha="Fatura Demo (mensal)",
        fonte=FONTE_PLANILHA,
    )

    df = listar_lancamentos_df()
    planilha = df[df["fonte"] == FONTE_PLANILHA]
    assert len(planilha) == 1
    assert planilha["conta_tipo"].iloc[0] == "cartao_credito"


def test_copiar_orcamentos_de_mes(banco_temporario):
    from analytics.escopo import ESCOPO_CASAL
    from db.repository import (
        copiar_orcamentos_de_mes,
        listar_orcamentos_df,
        salvar_orcamento_meta,
    )

    salvar_orcamento_meta(
        referencia_mes="2026-04",
        escopo=ESCOPO_CASAL,
        valor_limite=3000.0,
    )
    salvar_orcamento_meta(
        referencia_mes="2026-05",
        escopo=ESCOPO_CASAL,
        valor_limite=2500.0,
    )

    n = copiar_orcamentos_de_mes("2026-04", "2026-05")
    assert n == 0

    n = copiar_orcamentos_de_mes("2026-04", "2026-06")
    assert n == 1
    metas = listar_orcamentos_df("2026-06")
    assert len(metas) == 1
    assert float(metas.iloc[0]["valor_limite"]) == 3000.0
