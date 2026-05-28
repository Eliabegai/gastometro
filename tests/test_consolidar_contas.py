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
