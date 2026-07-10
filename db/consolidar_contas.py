"""Consolida pessoas e contas duplicadas no banco.

Cenário: o `seed` original criou contas com nomes curtos
("Ailos Mastercard", "Nubank Eliabe", "Nubank Ana") enquanto os parsers
de PDF e o importador da planilha familiar geram nomes canônicos no
formato `"{Banco} — {Titular}"` (ex.: "Ailos — Eliabe Gai"). Em paralelo,
PDFs novos podem trazer o titular com grafia diferente da já existente
(ex.: "Ana Leticia Maciel Gai" num PDF recente vs. "Ana Leticia Silva
Maciel" do histórico) — o `detectar_titular` cria uma `Pessoa` nova e
uma `Conta` nova vinculada a ela, partindo o cartão em dois.

Esse módulo aplica dois passes idempotentes:

  1. `consolidar_pessoas(MERGE_PESSOAS)`: pra cada par
     (velha → canônica), move `Lancamento.pessoa_id` e
     `Conta.pessoa_id` da velha pra canônica e deleta a pessoa velha.
  2. `consolidar(MERGE_CONTAS)`: pra cada par (nome_velho → canônico),
     renomeia se a canônica não existe ou move `Lancamento.conta_id`
     e deleta a antiga se ambas existem.

A ordem importa: rodamos pessoas primeiro pra que as contas órfãs já
estejam com a pessoa correta antes de serem fundidas. Pode ser rodado
quantas vezes quiser; depois da 1ª execução as seguintes viram no-op.

CLI:

    python -m db.consolidar_contas
"""

from __future__ import annotations

from sqlmodel import func, select

from db.engine import get_session
from db.models import Conta, Fatura, Lancamento, Pessoa

# (nome_velho, nome_canonico). Ordem não importa.
MERGE_CONTAS: list[tuple[str, str]] = [
    ("Ailos Mastercard", "Ailos — Eliabe Gai"),
    ("Nubank Eliabe", "Nubank — Eliabe Gai"),
    ("Nubank Ana", "Nubank — Ana Leticia Silva Maciel"),
    ("Nubank — Ana Leticia Maciel Gai", "Nubank — Ana Leticia Silva Maciel"),
]

# (nome_velho, nome_canonico). Aplicado ANTES das contas: garante que
# as contas residuais já pertençam à pessoa canônica quando o pass de
# contas executar.
MERGE_PESSOAS: list[tuple[str, str]] = [
    ("Ana Leticia Maciel Gai", "Ana Leticia Silva Maciel"),
]


def consolidar_pessoas(
    pares: list[tuple[str, str]] | None = None,
) -> dict[str, int]:
    """Funde pessoas duplicadas conforme `pares` (default = `MERGE_PESSOAS`).

    Pra cada par (velha → canônica):
      - Se a velha não existe: no-op.
      - Se só a velha existe: renomeia in-place pra canônica.
      - Se ambas existem: move `Lancamento.pessoa_id` e `Conta.pessoa_id`
        da velha pra canônica e deleta a velha.

    Devolve:
        {"renomeadas": N, "lancs_movidos": L, "contas_movidas": C,
         "pessoas_removidas": K}
    """
    pares = pares if pares is not None else MERGE_PESSOAS
    renomeadas = 0
    lancs_movidos = 0
    contas_movidas = 0
    removidas = 0

    with get_session() as session:
        for nome_velho, nome_canonico in pares:
            velha = session.exec(
                select(Pessoa).where(Pessoa.nome == nome_velho)
            ).first()
            if not velha:
                continue

            canonica = session.exec(
                select(Pessoa).where(Pessoa.nome == nome_canonico)
            ).first()

            # Caso 1: canônica não existe — só renomeia.
            if not canonica:
                velha.nome = nome_canonico
                session.add(velha)
                renomeadas += 1
                continue

            # Caso 2: defensivo — velha já é a canônica.
            if velha.id == canonica.id:
                continue

            # Caso 3: ambas existem. Reaponta `Lancamento` e `Conta`,
            # depois apaga a Pessoa velha.
            lancs = session.exec(
                select(Lancamento).where(Lancamento.pessoa_id == velha.id)
            ).all()
            for lanc in lancs:
                lanc.pessoa_id = canonica.id
                session.add(lanc)
                lancs_movidos += 1

            contas = session.exec(
                select(Conta).where(Conta.pessoa_id == velha.id)
            ).all()
            for conta in contas:
                conta.pessoa_id = canonica.id
                session.add(conta)
                contas_movidas += 1

            session.delete(velha)
            removidas += 1

    return {
        "renomeadas": renomeadas,
        "lancs_movidos": lancs_movidos,
        "contas_movidas": contas_movidas,
        "pessoas_removidas": removidas,
    }


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

            # Caso 3: ambas existem. Move lançamentos E faturas da antiga
            # pra nova (Fatura.conta_id é FK NOT NULL — sem reapontar
            # primeiro, o delete da Conta falha com FOREIGN KEY error).
            lancs = session.exec(
                select(Lancamento).where(Lancamento.conta_id == antiga.id)
            ).all()
            for lanc in lancs:
                lanc.conta_id = nova.id
                session.add(lanc)
                movidos += 1
            faturas = session.exec(
                select(Fatura).where(Fatura.conta_id == antiga.id)
            ).all()
            assert nova.id is not None  # garantido pelo SELECT logo acima
            for fat in faturas:
                fat.conta_id = nova.id
                session.add(fat)
            session.flush()
            session.delete(antiga)
            removidas += 1

    return {
        "renomeadas": renomeadas,
        "lancs_movidos": movidos,
        "contas_removidas": removidas,
    }


def remover_pessoas_orfas() -> int:
    """Apaga `Pessoa` que não tem nenhuma `Conta` nem `Lancamento` associado.

    Esses são restos do seed antigo ou da fusão de pessoas — pessoas
    "fantasma" que ficam só ocupando espaço no dropdown de filtros e
    no relatório. Idempotente.

    Pessoas com `Conta` ou `Lancamento` ainda vinculados NUNCA são
    apagadas — a função é segura mesmo se chamada com o banco vivo.
    """
    removidas = 0
    with get_session() as session:
        pessoas = session.exec(select(Pessoa)).all()
        for pessoa in pessoas:
            n_contas = session.exec(
                select(func.count())
                .select_from(Conta)
                .where(Conta.pessoa_id == pessoa.id)
            ).one()
            n_lancs = session.exec(
                select(func.count())
                .select_from(Lancamento)
                .where(Lancamento.pessoa_id == pessoa.id)
            ).one()
            if n_contas == 0 and n_lancs == 0:
                session.delete(pessoa)
                removidas += 1
    return removidas


def main() -> None:
    # Ordem importa:
    # 1. Pessoas duplicadas → garante contas residuais já apontam pra
    #    pessoa canônica antes do passe de contas rodar.
    # 2. Contas duplicadas → funde cartões "Banco Curto" vs
    #    "Banco — Titular", reapontando lancs E faturas.
    # 3. Limpa duplicação planilha×PDF — depois do merge, planilha
    #    histórica pode coexistir com PDF migrado pra mesma conta.
    # 4. Remove Pessoas fantasma — sem contas, sem lançamentos.
    from db.repository import (
        limpar_planilha_quando_pdf_existe,
        remover_faturas_pdf_duplicadas,
    )

    res_p = consolidar_pessoas()
    res_c = consolidar()
    res_planilha = limpar_planilha_quando_pdf_existe()
    res_faturas = remover_faturas_pdf_duplicadas()
    orfas = remover_pessoas_orfas()

    print("Consolidação concluída.")
    print()
    print("Pessoas:")
    print(f"  Renomeadas              : {res_p['renomeadas']}")
    print(f"  Lançamentos reapontados : {res_p['lancs_movidos']}")
    print(f"  Contas reapontadas      : {res_p['contas_movidas']}")
    print(f"  Pessoas duplicadas (rm) : {res_p['pessoas_removidas']}")
    print(f"  Pessoas órfãs (rm)      : {orfas}")
    print()
    print("Contas:")
    print(f"  Renomeadas              : {res_c['renomeadas']}")
    print(f"  Lançamentos movidos     : {res_c['lancs_movidos']}")
    print(f"  Contas duplicadas (rm)  : {res_c['contas_removidas']}")
    print()
    print("Planilha × PDF:")
    print(f"  Faturas examinadas      : {res_planilha['faturas_examinadas']}")
    print(f"  Linhas planilha apagadas: {res_planilha['lancamentos_removidos']}")
    print()
    print("Faturas PDF duplicadas:")
    print(f"  Grupos (conta+mês)      : {res_faturas['grupos']}")
    print(f"  Faturas removidas       : {res_faturas['faturas_removidas']}")
    print(f"  Lançamentos removidos   : {res_faturas['lancamentos_removidos']}")
    nada_a_fazer = (
        not any(res_p.values())
        and not any(res_c.values())
        and not res_planilha["lancamentos_removidos"]
        and not res_faturas["faturas_removidas"]
        and not orfas
    )
    if nada_a_fazer:
        print()
        print("  (Nada a fazer — banco já consolidado.)")


if __name__ == "__main__":
    main()
