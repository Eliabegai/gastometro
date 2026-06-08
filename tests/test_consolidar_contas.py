"""Testes do `db.consolidar_contas` — merge idempotente de contas duplicadas.

Cobre os 3 caminhos do `consolidar()`:
  1. Só a antiga existe → renomeia in-place.
  2. Ambas existem → move lançamentos e deleta a antiga.
  3. Nenhuma das duas existe (ou já é canônica) → no-op.
"""

from __future__ import annotations

from datetime import date

from sqlmodel import select

from db.consolidar_contas import consolidar
from db.engine import get_session
from db.models import (
    TIPO_CONTA_CARTAO,
    TIPO_LANCAMENTO_DESPESA,
    Conta,
    Lancamento,
)


def _criar_conta(session, nome: str, pessoa_id: int | None = None) -> Conta:
    conta = Conta(nome=nome, tipo=TIPO_CONTA_CARTAO, pessoa_id=pessoa_id)
    session.add(conta)
    session.flush()
    return conta


def _criar_lanc(
    session, conta_id: int | None, hash_id: str, valor: float = 10.0
) -> None:
    """Cria um Lancamento mínimo válido (só com os campos NOT NULL)."""
    assert conta_id is not None, "conta_id é obrigatório no teste"
    lanc = Lancamento(
        descricao=f"teste {hash_id}",
        valor=valor,
        tipo=TIPO_LANCAMENTO_DESPESA,
        data=date(2026, 1, 1),
        referencia_mes="2026-01",
        conta_id=conta_id,
        hash_dedupe=f"hash_{hash_id}",
    )
    session.add(lanc)


def test_consolidar_apenas_antiga_renomeia(banco_temporario) -> None:
    """Quando só a antiga existe, a função renomeia in-place — preserva o ID
    e os lançamentos associados, sem perder histórico."""
    with get_session() as s:
        antiga = _criar_conta(s, "Cartão Antigo X")
        _criar_lanc(s, antiga.id, "renomeada")
        id_antiga = antiga.id

    res = consolidar([("Cartão Antigo X", "Cartão Novo X")])

    assert res == {
        "renomeadas": 1,
        "lancs_movidos": 0,
        "contas_removidas": 0,
    }

    with get_session() as s:
        renomeada = s.exec(
            select(Conta).where(Conta.nome == "Cartão Novo X")
        ).first()
        assert renomeada is not None
        assert renomeada.id == id_antiga
        antiga_persiste = s.exec(
            select(Conta).where(Conta.nome == "Cartão Antigo X")
        ).first()
        assert antiga_persiste is None


def test_consolidar_funde_quando_ambas_existem(banco_temporario) -> None:
    """Ambas existem: move lançamentos da antiga pra canônica e deleta a antiga."""
    with get_session() as s:
        antiga = _criar_conta(s, "Cartão Antigo Y")
        canonica = _criar_conta(s, "Cartão Canônico Y")
        _criar_lanc(s, antiga.id, "y_a1")
        _criar_lanc(s, antiga.id, "y_a2")
        _criar_lanc(s, canonica.id, "y_c1")
        id_antiga = antiga.id
        id_canonica = canonica.id

    res = consolidar([("Cartão Antigo Y", "Cartão Canônico Y")])

    assert res == {
        "renomeadas": 0,
        "lancs_movidos": 2,
        "contas_removidas": 1,
    }

    with get_session() as s:
        # Antiga foi deletada.
        antiga_gone = s.exec(
            select(Conta).where(Conta.id == id_antiga)
        ).first()
        assert antiga_gone is None
        # Canônica tem todos os 3 lançamentos (2 movidos + 1 original).
        lancs = s.exec(
            select(Lancamento).where(Lancamento.conta_id == id_canonica)
        ).all()
        assert len(lancs) == 3


def test_consolidar_idempotente(banco_temporario) -> None:
    """Rodar 2x não duplica nada — a segunda chamada vira no-op."""
    with get_session() as s:
        _criar_conta(s, "Cartão Z Antigo")
        canonica = _criar_conta(s, "Cartão Z Canônico")
        _criar_lanc(s, canonica.id, "z1")

    pares = [("Cartão Z Antigo", "Cartão Z Canônico")]
    primeira = consolidar(pares)
    segunda = consolidar(pares)

    assert primeira["contas_removidas"] == 1
    assert segunda == {
        "renomeadas": 0,
        "lancs_movidos": 0,
        "contas_removidas": 0,
    }


def test_consolidar_sem_antiga_eh_noop(banco_temporario) -> None:
    """Se a antiga não existe, nada acontece."""
    with get_session() as s:
        _criar_conta(s, "Outro Cartão")

    res = consolidar([("Não Existe", "Outro Nome")])
    assert res == {
        "renomeadas": 0,
        "lancs_movidos": 0,
        "contas_removidas": 0,
    }


def test_seed_cria_contas_no_formato_canonico(banco_temporario) -> None:
    """O `seed_inicial` (rodado pelo fixture) cria as contas dos cartões já
    no formato `{Banco} — {Titular}`, evitando duplicação com PDFs."""
    with get_session() as s:
        nomes = {c.nome for c in s.exec(select(Conta)).all()}
    assert "Ailos — Eliabe Gai" in nomes
    assert "Nubank — Eliabe Gai" in nomes
    assert "Nubank — Ana Leticia Silva Maciel" in nomes
    # Os nomes antigos NÃO devem existir num banco recém-semeado.
    assert "Ailos Mastercard" not in nomes
    assert "Nubank Eliabe" not in nomes
    assert "Nubank Ana" not in nomes



def test_consolidar_pessoas_apenas_velha_renomeia(banco_temporario) -> None:
    """Velha sem canônica: a função só renomeia in-place, preservando ID."""
    from db.consolidar_contas import consolidar_pessoas
    from db.models import Pessoa

    with get_session() as s:
        p = Pessoa(nome="Maria de Souza", ativo=True)
        s.add(p)
        s.flush()
        id_velha = p.id

    res = consolidar_pessoas([("Maria de Souza", "Maria Souza")])

    assert res == {
        "renomeadas": 1,
        "lancs_movidos": 0,
        "contas_movidas": 0,
        "pessoas_removidas": 0,
    }
    with get_session() as s:
        p = s.exec(select(Pessoa).where(Pessoa.nome == "Maria Souza")).first()
        assert p is not None and p.id == id_velha


def test_consolidar_pessoas_funde_ambas(banco_temporario) -> None:
    """Quando ambas existem: lança e conta da velha viram da canônica;
    a velha é apagada."""
    from db.consolidar_contas import consolidar_pessoas
    from db.models import Pessoa

    with get_session() as s:
        velha = Pessoa(nome="Ana Velha")
        canonica = Pessoa(nome="Ana Canônica")
        s.add(velha)
        s.add(canonica)
        s.flush()
        conta_velha = _criar_conta(s, "Nubank — Ana Velha", pessoa_id=velha.id)
        # Lançamento amarrado por `pessoa_id` direto (cenário import PDF
        # com novo titular).
        lanc = Lancamento(
            descricao="compra A",
            valor=10.0,
            tipo=TIPO_LANCAMENTO_DESPESA,
            data=date(2026, 1, 1),
            referencia_mes="2026-01",
            conta_id=conta_velha.id,
            pessoa_id=velha.id,
            hash_dedupe="hash_p_a",
        )
        s.add(lanc)
        id_velha = velha.id
        id_canonica = canonica.id

    res = consolidar_pessoas([("Ana Velha", "Ana Canônica")])

    assert res["pessoas_removidas"] == 1
    assert res["lancs_movidos"] == 1
    assert res["contas_movidas"] == 1

    with get_session() as s:
        velha_gone = s.exec(select(Pessoa).where(Pessoa.id == id_velha)).first()
        assert velha_gone is None
        conta = s.exec(
            select(Conta).where(Conta.nome == "Nubank — Ana Velha")
        ).first()
        assert conta is not None
        assert conta.pessoa_id == id_canonica
        lanc = s.exec(
            select(Lancamento).where(Lancamento.descricao == "compra A")
        ).first()
        assert lanc is not None
        assert lanc.pessoa_id == id_canonica


def test_consolidar_pessoas_idempotente(banco_temporario) -> None:
    """Roda duas vezes: segunda chamada é no-op."""
    from db.consolidar_contas import consolidar_pessoas
    from db.models import Pessoa

    with get_session() as s:
        s.add(Pessoa(nome="X Velha"))
        s.add(Pessoa(nome="X Canônica"))
        s.flush()

    pares = [("X Velha", "X Canônica")]
    primeira = consolidar_pessoas(pares)
    segunda = consolidar_pessoas(pares)

    assert primeira["pessoas_removidas"] == 1
    assert segunda == {
        "renomeadas": 0,
        "lancs_movidos": 0,
        "contas_movidas": 0,
        "pessoas_removidas": 0,
    }


def test_pipeline_pessoa_depois_conta_resolve_pdf_com_nome_novo(
    banco_temporario,
) -> None:
    """Cenário reportado pelo usuário: PDF da Ana chega com titular
    `Ana Leticia Maciel Gai` e o sistema cria Pessoa + Conta separadas
    da `Ana Leticia Silva Maciel` já existente no banco. Rodar o
    consolidador deve fundir tudo num único cartão e numa única
    pessoa, sem perder lançamentos."""
    from db.consolidar_contas import consolidar, consolidar_pessoas
    from db.models import Pessoa

    # `seed_inicial` (do fixture) já cria "Ana Leticia Silva Maciel" +
    # "Nubank — Ana Leticia Silva Maciel". Só precisamos simular a
    # pessoa/conta duplicadas criadas pelo PDF novo.
    with get_session() as s:
        ana_canonica = s.exec(
            select(Pessoa).where(Pessoa.nome == "Ana Leticia Silva Maciel")
        ).first()
        assert ana_canonica is not None
        ana_pdf = Pessoa(nome="Ana Leticia Maciel Gai")
        s.add(ana_pdf)
        s.flush()
        legada = s.exec(
            select(Conta).where(
                Conta.nome == "Nubank — Ana Leticia Silva Maciel"
            )
        ).first()
        assert legada is not None
        for i in range(5):
            _criar_lanc(s, legada.id, f"legado_{i}")
        nova = _criar_conta(
            s, "Nubank — Ana Leticia Maciel Gai", pessoa_id=ana_pdf.id
        )
        for i in range(20):
            _criar_lanc(s, nova.id, f"novo_{i}")

    res_p = consolidar_pessoas()
    res_c = consolidar()

    assert res_p["pessoas_removidas"] == 1, res_p
    assert res_c["contas_removidas"] == 1, res_c

    with get_session() as s:
        ana_pdf_gone = s.exec(
            select(Pessoa).where(Pessoa.nome == "Ana Leticia Maciel Gai")
        ).first()
        assert ana_pdf_gone is None
        conta_pdf_gone = s.exec(
            select(Conta).where(
                Conta.nome == "Nubank — Ana Leticia Maciel Gai"
            )
        ).first()
        assert conta_pdf_gone is None
        canonica = s.exec(
            select(Conta).where(
                Conta.nome == "Nubank — Ana Leticia Silva Maciel"
            )
        ).first()
        assert canonica is not None
        lancs = s.exec(
            select(Lancamento).where(Lancamento.conta_id == canonica.id)
        ).all()
        assert len(lancs) == 25



def test_remover_pessoas_orfas_apaga_sem_contas_e_sem_lancs(
    banco_temporario,
) -> None:
    """Pessoa sem nenhuma Conta e sem nenhum Lancamento é apagada."""
    from db.consolidar_contas import remover_pessoas_orfas
    from db.models import Pessoa

    with get_session() as s:
        s.add(Pessoa(nome="Fantasma Solitário"))
        s.flush()

    n = remover_pessoas_orfas()
    assert n >= 1
    with get_session() as s:
        sumiu = s.exec(
            select(Pessoa).where(Pessoa.nome == "Fantasma Solitário")
        ).first()
        assert sumiu is None


def test_remover_pessoas_orfas_preserva_com_conta(banco_temporario) -> None:
    """Pessoa que tem ao menos uma Conta nunca é apagada — mesmo sem
    lançamentos."""
    from db.consolidar_contas import remover_pessoas_orfas
    from db.models import Pessoa

    with get_session() as s:
        p = Pessoa(nome="Tem Cartão Só")
        s.add(p)
        s.flush()
        _criar_conta(s, "Cartão da Pessoa", pessoa_id=p.id)
        id_p = p.id

    remover_pessoas_orfas()
    with get_session() as s:
        ainda = s.exec(select(Pessoa).where(Pessoa.id == id_p)).first()
        assert ainda is not None


def test_remover_pessoas_orfas_preserva_com_lancamento(
    banco_temporario,
) -> None:
    """Pessoa que tem ao menos um Lancamento nunca é apagada — mesmo
    sem contas vinculadas (lançamento manual avulso)."""
    from db.consolidar_contas import remover_pessoas_orfas
    from db.models import Pessoa

    with get_session() as s:
        p = Pessoa(nome="Tem Lanc Só")
        s.add(p)
        s.flush()
        # Conta auxiliar (não-pessoa) só pra satisfazer FK do Lancamento.
        conta_aux = _criar_conta(s, "Conta Aux")
        lanc = Lancamento(
            descricao="manual avulso",
            valor=1.0,
            tipo=TIPO_LANCAMENTO_DESPESA,
            data=date(2026, 1, 1),
            referencia_mes="2026-01",
            conta_id=conta_aux.id,
            pessoa_id=p.id,
            hash_dedupe="orfa_lanc",
        )
        s.add(lanc)
        id_p = p.id

    remover_pessoas_orfas()
    with get_session() as s:
        ainda = s.exec(select(Pessoa).where(Pessoa.id == id_p)).first()
        assert ainda is not None


def test_remover_pessoas_orfas_idempotente(banco_temporario) -> None:
    """Rodar 2x: segunda chamada não apaga nada."""
    from db.consolidar_contas import remover_pessoas_orfas
    from db.models import Pessoa

    with get_session() as s:
        s.add(Pessoa(nome="Fant 1"))
        s.add(Pessoa(nome="Fant 2"))
        s.flush()

    n1 = remover_pessoas_orfas()
    n2 = remover_pessoas_orfas()
    assert n1 >= 2
    assert n2 == 0
