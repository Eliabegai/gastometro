"""Consolida contas duplicadas no banco.

Cenário: o `seed` original criou contas com nomes curtos
("Ailos Mastercard", "Nubank Eliabe", "Nubank Ana") enquanto os parsers
de PDF e o importador da planilha familiar geram nomes canônicos no
formato `"{Banco} — {Titular}"` (ex.: "Ailos — Eliabe Gai"). O banco
acabou com 2 contas equivalentes pro mesmo cartão real.

Esse módulo aplica um `MERGE_CONTAS` (mapping `nome_antigo →
nome_canonico`) idempotente:

  1. Se só existe a antiga: renomeia in-place.
  2. Se só existe a canônica: ignora.
  3. Se existem ambas: move todos os `Lancamento` da antiga pra
     canônica e deleta a antiga.

Pode ser rodado quantas vezes quiser; depois da 1ª execução as
seguintes viram no-op.

CLI:

    python -m db.consolidar_contas
"""

from __future__ import annotations

from sqlmodel import select

from db.engine import get_session
from db.models import Conta, Lancamento

# (nome_antigo, nome_canonico). Ordem não importa.
MERGE_CONTAS: list[tuple[str, str]] = [
    ("Ailos Mastercard", "Ailos — Eliabe Gai"),
    ("Nubank Eliabe", "Nubank — Eliabe Gai"),
    ("Nubank Ana", "Nubank — Ana Leticia Silva Maciel"),
]


def consolidar(
    pares: list[tuple[str, str]] | None = None,
) -> dict[str, int]:
    """Funde contas duplicadas conforme `pares` (default = `MERGE_CONTAS`).

    Devolve:
        {"renomeadas": N, "lancs_movidos": M, "contas_removidas": K}
    """
    pares = pares if pares is not None else MERGE_CONTAS
    renomeadas = 0
    movidos = 0
    removidas = 0

    with get_session() as session:
        for nome_velho, nome_canonico in pares:
            antiga = session.exec(
                select(Conta).where(Conta.nome == nome_velho)
            ).first()
            if not antiga:
                continue

            nova = session.exec(
                select(Conta).where(Conta.nome == nome_canonico)
            ).first()

            # Caso 1: não existe a canônica ainda — só renomeia a antiga.
            if not nova:
                antiga.nome = nome_canonico
                session.add(antiga)
                renomeadas += 1
                continue

            # Caso 2: a "antiga" já é a canônica (raro, defensivo).
            if antiga.id == nova.id:
                continue

            # Caso 3: ambas existem. Move lançamentos da antiga pra nova.
            lancs = session.exec(
                select(Lancamento).where(Lancamento.conta_id == antiga.id)
            ).all()
            for lanc in lancs:
                lanc.conta_id = nova.id
                session.add(lanc)
                movidos += 1
            session.delete(antiga)
            removidas += 1

    return {
        "renomeadas": renomeadas,
        "lancs_movidos": movidos,
        "contas_removidas": removidas,
    }


def main() -> None:
    res = consolidar()
    print("Consolidação concluída.")
    print(f"  Contas renomeadas       : {res['renomeadas']}")
    print(f"  Lançamentos movidos     : {res['lancs_movidos']}")
    print(f"  Contas duplicadas (rm)  : {res['contas_removidas']}")
    if not any(res.values()):
        print("  (Nada a fazer — banco já consolidado.)")


if __name__ == "__main__":
    main()
