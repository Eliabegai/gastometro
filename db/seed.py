"""Seed inicial do banco — categorias, pessoas e contas básicas.

Idempotente: rodar várias vezes não duplica entradas. Só insere o que
ainda não existe (compara por `nome`).

Uso programático:
    from db.seed import seed_inicial
    seed_inicial()
"""

from __future__ import annotations

from sqlmodel import Session, select

from categorias import CATEGORIAS
from db.engine import garantir_schema, get_session
from db.models import (
    TIPO_CATEGORIA_DESPESA,
    TIPO_CATEGORIA_RECEITA,
    TIPO_CONTA_CARTAO,
    TIPO_CONTA_CORRENTE,
    Categoria,
    Conta,
    Pessoa,
)

# Categorias de receita não existem em `categorias.py` (que só cobre
# despesas via descrição de fatura). Lista mínima útil pra registrar
# entradas manuais (salário, freela, etc.) e pra mapear linhas da
# planilha familiar (Ganhos Eliabe, Ganhos Ana Letícia).
CATEGORIAS_RECEITA_PADRAO = [
    "Salário",
    "Freelance",
    "Empréstimo Familiar",
    "Doação",
    "Reembolso",
    "Estorno",
    "Outras Receitas",
]

# Categoria "guarda-chuva" usada quando o parser não conseguir bater
# nenhuma keyword. Já existe na lógica de `categorizar()`; aqui só
# garantimos que ela exista no banco.
CATEGORIA_FALLBACK_DESPESA = "Outros Gastos"

# Pessoas iniciais do casal. Pode editar depois pela UI.
PESSOAS_INICIAIS = ["Eliabe", "Ana Letícia"]

# Contas iniciais. `pessoa_nome=None` => conjunta (sem dono específico).
CONTAS_INICIAIS = [
    # nome, tipo, pessoa_nome
    ("Ailos Mastercard", TIPO_CONTA_CARTAO, "Eliabe"),
    ("Nubank Eliabe", TIPO_CONTA_CARTAO, "Eliabe"),
    ("Nubank Ana", TIPO_CONTA_CARTAO, "Ana Letícia"),
    ("Conta Corrente", TIPO_CONTA_CORRENTE, None),
    ("Planilha Familiar", TIPO_CONTA_CORRENTE, None),
]


def _semear_pessoas(session: Session) -> dict[str, int]:
    existentes = {p.nome: p.id for p in session.exec(select(Pessoa)).all()}
    for nome in PESSOAS_INICIAIS:
        if nome in existentes:
            continue
        p = Pessoa(nome=nome, ativo=True)
        session.add(p)
        session.flush()
        existentes[nome] = p.id
    return {n: i for n, i in existentes.items() if i is not None}


def _semear_contas(session: Session, mapa_pessoas: dict[str, int]) -> None:
    existentes = {c.nome for c in session.exec(select(Conta)).all()}
    for nome, tipo, pessoa_nome in CONTAS_INICIAIS:
        if nome in existentes:
            continue
        pessoa_id = mapa_pessoas.get(pessoa_nome) if pessoa_nome else None
        session.add(Conta(nome=nome, tipo=tipo, pessoa_id=pessoa_id))


def _semear_categorias(session: Session) -> None:
    existentes = {c.nome for c in session.exec(select(Categoria)).all()}

    for nome in CATEGORIAS:
        if nome in existentes:
            continue
        session.add(Categoria(nome=nome, tipo=TIPO_CATEGORIA_DESPESA))
        existentes.add(nome)

    if CATEGORIA_FALLBACK_DESPESA not in existentes:
        session.add(
            Categoria(nome=CATEGORIA_FALLBACK_DESPESA, tipo=TIPO_CATEGORIA_DESPESA)
        )
        existentes.add(CATEGORIA_FALLBACK_DESPESA)

    for nome in CATEGORIAS_RECEITA_PADRAO:
        if nome in existentes:
            continue
        session.add(Categoria(nome=nome, tipo=TIPO_CATEGORIA_RECEITA))
        existentes.add(nome)


def seed_inicial() -> dict[str, int]:
    """Popula pessoas, contas e categorias iniciais. Idempotente.

    Aplica `alembic upgrade head` antes (no-op se já estiver na
    versão atual) — garante que rodar pela primeira vez funcione
    sem o usuário precisar saber sobre Alembic.

    Devolve dicionário com contagens (`{"pessoas": N, "contas": M,
    "categorias": K}`) já considerando os totais finais (não só os
    inseridos nesta chamada).
    """
    garantir_schema()
    with get_session() as session:
        mapa = _semear_pessoas(session)
        _semear_contas(session, mapa)
        _semear_categorias(session)
        session.flush()
        totais = {
            "pessoas": len(session.exec(select(Pessoa)).all()),
            "contas": len(session.exec(select(Conta)).all()),
            "categorias": len(session.exec(select(Categoria)).all()),
        }
    return totais


if __name__ == "__main__":
    totais = seed_inicial()
    print(
        "Seed concluído. Totais atuais no banco:"
        f" {totais['pessoas']} pessoas,"
        f" {totais['contas']} contas,"
        f" {totais['categorias']} categorias."
    )
