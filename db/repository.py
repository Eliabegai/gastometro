"""Camada de operações de alto nível sobre o banco.

Princípios:
  - Funções públicas abrem a própria sessão (atomicidade controlada).
  - Helpers privados (`_*`) recebem `session: Session` e não commitam.
  - Hash de dedup é determinístico: mesma fonte + mesmo conteúdo →
    mesmo hash → import idempotente (UNIQUE em `lancamento.hash_dedupe`).
  - Datas BR (`DD/MM/AAAA`) e mês de referência (`YYYY-MM`) são
    normalizados aqui — o resto da aplicação recebe `date`/`str` limpos.
"""

from __future__ import annotations

import hashlib
import re
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

import pandas as pd
from sqlmodel import Session, select

from categorias import _normalizar as normalizar_descricao  # noqa: PLC2701
from categorias import categorizar as categorizar_por_regras
from db.engine import get_session
from db.models import (
    ESCOPO_CASAL,
    ESCOPO_PESSOAL,
    FONTE_PDF,
    FONTE_PLANILHA,
    TIPO_CATEGORIA_DESPESA,
    TIPO_CONTA_OUTRO,
    TIPO_LANCAMENTO_DESPESA,
    TIPO_LANCAMENTO_ESTORNO,
    TIPO_LANCAMENTO_RECEITA,
    Categoria,
    Conta,
    EscopoCategoria,
    Fatura,
    Lancamento,
    OrcamentoMeta,
    OverrideCategoria,
    Pessoa,
    _agora_utc,
)
from parsers.base import (
    Fatura as FaturaParser,
)

RE_DATA_BR = re.compile(r"^(\d{2})/(\d{2})/(\d{4})$")
RE_REFERENCIA_NOME = re.compile(r"^(\w+)/(\d{4})$")

MES_NOME_PARA_NUMERO = {
    "janeiro": 1, "fevereiro": 2, "março": 3, "marco": 3, "abril": 4,
    "maio": 5, "junho": 6, "julho": 7, "agosto": 8, "setembro": 9,
    "outubro": 10, "novembro": 11, "dezembro": 12,
}


def parse_data_br(texto: str | None) -> date | None:
    """Converte 'DD/MM/AAAA' em `date`. Devolve `None` se vazio/inválido."""
    if not texto:
        return None
    m = RE_DATA_BR.match(texto.strip())
    if not m:
        return None
    dia, mes, ano = (int(g) for g in m.groups())
    try:
        return date(ano, mes, dia)
    except ValueError:
        return None


def parse_referencia(texto: str | None) -> str | None:
    """'Maio/2026' → '2026-05'. Devolve `None` se não casar."""
    if not texto:
        return None
    m = RE_REFERENCIA_NOME.match(texto.strip())
    if not m:
        return None
    nome, ano = m.group(1).lower(), int(m.group(2))
    num = MES_NOME_PARA_NUMERO.get(nome)
    if num is None:
        return None
    return f"{ano:04d}-{num:02d}"


def referencia_de_data(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def _arred(valor: float | Decimal) -> Decimal:
    """Quantiza pra 2 casas, evitando float drift."""
    return Decimal(str(valor)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _centavos(valor: Decimal) -> int:
    return int((valor * 100).to_integral_value(rounding=ROUND_HALF_UP))


def _hash(*partes: str) -> str:
    """SHA1 hex de partes concatenadas por `|`."""
    raw = "|".join(str(p) for p in partes)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def hash_lancamento_pdf(
    *,
    arquivo: str,
    data: date,
    descricao: str,
    valor: Decimal,
    conta_nome: str,
    parcela_atual: int | None = None,
) -> str:
    """Hash de dedup pra lançamentos vindos de PDF de fatura.

    Inclui `parcela_atual` no payload porque uma única descrição pode
    aparecer várias vezes em parcelas distintas com mesmo valor —
    sem isso, dedup colapsava parcelas múltiplas em uma só.
    """
    return _hash(
        "pdf",
        arquivo,
        data.isoformat(),
        normalizar_descricao(descricao),
        _centavos(valor),
        conta_nome,
        parcela_atual if parcela_atual is not None else "",
    )


def hash_lancamento_planilha(
    *,
    categoria_planilha: str,
    ano: int,
    mes: int,
    pessoa_nome: str | None,
) -> str:
    """Hash de dedup pra lançamentos vindos da planilha familiar (Fase 3).

    Uma linha por (categoria, mês, ano, pessoa). Reimport idempotente.
    """
    return _hash(
        "planilha",
        normalizar_descricao(categoria_planilha),
        ano,
        mes,
        pessoa_nome or "",
    )


def hash_lancamento_excel_legado(
    *,
    arquivo: str,
    data: date,
    descricao: str,
    valor: Decimal,
    conta_nome: str,
    parcela_atual: int | None = None,
) -> str:
    """Hash pra lançamentos que vêm da aba `Transações` do Excel legado.

    Usa o mesmo schema do hash de PDF — afinal, todas essas linhas
    foram originalmente extraídas de PDFs. Compatibilidade garantida:
    se você reprocessar o PDF original depois, o hash bate e a linha
    não duplica.
    """
    return hash_lancamento_pdf(
        arquivo=arquivo,
        data=data,
        descricao=descricao,
        valor=valor,
        conta_nome=conta_nome,
        parcela_atual=parcela_atual,
    )


def _obter_pessoa_por_nome(session: Session, nome: str) -> Pessoa | None:
    """Lookup case-insensitive de Pessoa por nome.

    Nota: SQLite `LOWER()` não converte caracteres não-ASCII (ex.
    `Á → Á` em vez de `á`), então comparação SQL-side falha com
    nomes acentuados. Carregamos todas (poucas linhas) e comparamos
    em Python — robusto e simples.
    """
    if not nome:
        return None
    alvo = nome.strip().lower()
    for p in session.exec(select(Pessoa)).all():
        if p.nome.strip().lower() == alvo:
            return p
    return None


def _obter_ou_criar_pessoa(session: Session, nome: str) -> Pessoa:
    p = _obter_pessoa_por_nome(session, nome)
    if p is not None:
        return p
    p = Pessoa(nome=nome.strip().title(), ativo=True)
    session.add(p)
    session.flush()
    return p


def _obter_conta_por_nome(session: Session, nome: str) -> Conta | None:
    """Lookup case-insensitive de Conta — vide nota em `_obter_pessoa_por_nome`."""
    if not nome:
        return None
    alvo = nome.strip().lower()
    for c in session.exec(select(Conta)).all():
        if c.nome.strip().lower() == alvo:
            return c
    return None


def _obter_ou_criar_conta(
    session: Session,
    *,
    nome: str,
    tipo: str = TIPO_CONTA_OUTRO,
    pessoa: Pessoa | None = None,
) -> Conta:
    c = _obter_conta_por_nome(session, nome)
    if c is not None:
        if pessoa is not None and c.pessoa_id is None:
            c.pessoa_id = pessoa.id
            session.add(c)
            session.flush()
        return c
    c = Conta(
        nome=nome.strip(),
        tipo=tipo,
        pessoa_id=pessoa.id if pessoa else None,
    )
    session.add(c)
    session.flush()
    return c


def _identificador_cartao(banco: str, titular: str) -> str:
    """Mesma regra do `extrator._identificador_cartao` — fonte única."""
    banco = (banco or "").strip()
    titular = (titular or "").strip()
    if not banco and not titular:
        return ""
    if not titular:
        return banco
    if not banco:
        return titular
    return f"{banco} — {titular}"


def _obter_categoria_por_nome(session: Session, nome: str) -> Categoria | None:
    """Lookup case-insensitive de Categoria — vide nota em `_obter_pessoa_por_nome`."""
    if not nome:
        return None
    alvo = nome.strip().lower()
    for c in session.exec(select(Categoria)).all():
        if c.nome.strip().lower() == alvo:
            return c
    return None


def _obter_ou_criar_categoria(
    session: Session,
    *,
    nome: str,
    tipo: str = TIPO_CATEGORIA_DESPESA,
) -> Categoria:
    cat = _obter_categoria_por_nome(session, nome)
    if cat is not None:
        return cat
    cat = Categoria(nome=nome, tipo=tipo)
    session.add(cat)
    session.flush()
    if cat.id is None:
        raise RuntimeError(f"Falha ao obter id da categoria recém-criada: {nome}")
    return cat


def _cache_overrides(session: Session) -> dict[str, int]:
    """Mapa descricao_normalizada -> categoria_id (lido uma vez por sessão)."""
    rows = session.exec(select(OverrideCategoria)).all()
    return {r.descricao_normalizada: r.categoria_id for r in rows}


def _categorizar_para_id(
    session: Session,
    descricao: str,
    overrides: dict[str, int],
) -> tuple[int | None, str]:
    """Devolve (categoria_id, nome). Aplica override antes do dicionário.

    Garante que a categoria existe no banco (cria sob demanda — útil
    quando o dicionário tem uma categoria nova ainda não semeada).
    """
    norm = normalizar_descricao(descricao)
    if norm in overrides:
        cat_id = overrides[norm]
        cat = session.get(Categoria, cat_id)
        nome = cat.nome if cat else ""
        return cat_id, nome

    nome = categorizar_por_regras(descricao)
    cat = _obter_ou_criar_categoria(
        session, nome=nome, tipo=TIPO_CATEGORIA_DESPESA
    )
    return cat.id, nome


def _tipo_lancamento_pdf(valor: Decimal, categoria_nome: str) -> str:
    """Decide tipo a partir do sinal do valor (PDFs).

    Valor negativo no PDF = crédito / estorno. Positivo = despesa.
    A categoria não influencia (em PDF de cartão tudo é gasto, exceto
    estornos).
    """
    if valor < 0:
        return TIPO_LANCAMENTO_ESTORNO
    return TIPO_LANCAMENTO_DESPESA


def upsert_fatura(
    fatura_pdf: FaturaParser,
    *,
    arquivo: str,
    session: Session | None = None,
    respeitar_categoria_existente: bool = False,
    fonte: str = FONTE_PDF,
    pessoa_override: str | None = None,
) -> tuple[int, int]:
    """Importa uma fatura PDF parseada para o banco.

    Devolve `(fatura_id, qtde_lancamentos_inseridos)`. Idempotente:
    - Fatura já existente (mesmo `arquivo`) → não duplica; devolve
      o ID existente e 0 inseridos.
    - Lançamentos duplicados (mesmo `hash_dedupe`) → ignorados.

    Parâmetros:
      - `respeitar_categoria_existente`: quando `True`, usa
        `tx.categoria` da entrada se estiver preenchida (e a categoria
        existir/for criada no banco) em vez de chamar o categorizador.
        Usado na migração do Excel legado pra preservar correções
        manuais que o usuário já tinha feito.
      - `fonte`: rótulo gravado em `lancamento.fonte`. Default `pdf_fatura`;
        a migração legada usa `excel_legado`.
      - `pessoa_override`: nome de pessoa já existente no banco que deve
        ser usada como dona da conta (ignora `meta.titular` do PDF).
        Útil quando o PDF traz o titular com grafia diferente da que
        já temos cadastrada — evita criar `Pessoa` duplicada e usa a
        conta canônica `{banco} — {pessoa_override}` se existir.
    """
    if session is None:
        with get_session() as s:
            return upsert_fatura(
                fatura_pdf,
                arquivo=arquivo,
                session=s,
                respeitar_categoria_existente=respeitar_categoria_existente,
                fonte=fonte,
                pessoa_override=pessoa_override,
            )

    meta = fatura_pdf.metadata

    existente = session.exec(
        select(Fatura).where(Fatura.arquivo == arquivo)
    ).first()
    if existente is not None:
        # Defensivo: planilha pode ter sido importada DEPOIS do PDF
        # original (re-import da planilha familiar com janela maior).
        # Limpa duplicatas a cada execução — idempotente.
        if existente.referencia_mes:
            _remover_planilha_duplicada(
                session,
                conta_id=existente.conta_id,
                referencia=existente.referencia_mes,
            )
        return existente.id, 0

    # `pessoa_override` vence o `meta.titular` extraído do PDF — evita
    # criar Pessoa nova quando o usuário já sabe a quem o cartão
    # pertence (corrige divergência de grafia entre PDFs antigos/novos).
    titular_efetivo = pessoa_override or meta.titular
    pessoa = (
        _obter_ou_criar_pessoa(session, titular_efetivo)
        if titular_efetivo
        else None
    )
    nome_conta = (
        _identificador_cartao(meta.banco, titular_efetivo) or "Sem Cartão"
    )
    conta = _obter_ou_criar_conta(
        session,
        nome=nome_conta,
        tipo="cartao_credito",
        pessoa=pessoa,
    )

    referencia = parse_referencia(meta.referencia_mes)
    vencimento = parse_data_br(meta.data_vencimento)
    fechamento = parse_data_br(meta.data_fechamento)

    fatura = Fatura(
        conta_id=conta.id,
        arquivo=arquivo,
        referencia_mes=referencia or "",
        fechamento=fechamento,
        vencimento=vencimento,
        valor_total_declarado=(
            _arred(meta.valor_total) if meta.valor_total else None
        ),
        qtde_transacoes=len(fatura_pdf.transacoes),
    )
    session.add(fatura)
    session.flush()

    # Cenário-chave do bug de duplicação: planilha familiar foi
    # importada ANTES desse PDF chegar. A regra de skip no
    # `importar_planilha_familiar` só atua na direção contrária —
    # aqui fechamos o outro lado, removendo a célula agregada da
    # planilha pra mesma (conta, referência).
    if referencia:
        _remover_planilha_duplicada(
            session, conta_id=conta.id, referencia=referencia
        )

    overrides = _cache_overrides(session)

    inseridos = 0
    for tx in fatura_pdf.transacoes:
        data_tx = parse_data_br(tx.data)
        if data_tx is None:
            continue
        valor = _arred(tx.valor)

        parcela_atual, parcela_total = _parse_parcela(tx.parcela)
        h = hash_lancamento_pdf(
            arquivo=arquivo,
            data=data_tx,
            descricao=tx.descricao,
            valor=valor,
            conta_nome=nome_conta,
            parcela_atual=parcela_atual,
        )
        if session.exec(
            select(Lancamento.id).where(Lancamento.hash_dedupe == h)
        ).first():
            continue

        if respeitar_categoria_existente and tx.categoria:
            cat = _obter_ou_criar_categoria(
                session, nome=tx.categoria.strip(), tipo=TIPO_CATEGORIA_DESPESA
            )
            cat_id = cat.id
        else:
            cat_id, _ = _categorizar_para_id(
                session, tx.descricao, overrides
            )
        tipo = _tipo_lancamento_pdf(valor, tx.categoria)
        valor_db = abs(valor)

        lanc = Lancamento(
            data=data_tx,
            descricao=tx.descricao,
            valor=valor_db,
            tipo=tipo,
            categoria_id=cat_id,
            conta_id=conta.id,
            pessoa_id=pessoa.id if pessoa else None,
            fatura_id=fatura.id,
            referencia_mes=referencia,
            parcela_atual=parcela_atual,
            parcela_total=parcela_total,
            cidade=tx.cidade or None,
            fonte=fonte,
            arquivo_origem=arquivo,
            hash_dedupe=h,
        )
        session.add(lanc)
        inseridos += 1

    return fatura.id, inseridos


def _remover_planilha_duplicada(
    session: Session, *, conta_id: int, referencia: str
) -> int:
    """Apaga lançamentos da planilha familiar que duplicam um PDF.

    Regra de negócio (definida pelo usuário):
      - A importação PDF traz o detalhe granular do que foi gasto.
      - A célula da planilha traz o agregado mensal pra controle.
      - Quando ambos coexistem pra mesma (conta, referência), o PDF
        vence — somar os dois infla o total.

    Removemos apenas linhas com `fonte == FONTE_PLANILHA`. Lançamentos
    manuais e PDFs nunca são tocados.
    """
    if not referencia:
        return 0
    stmt = select(Lancamento).where(
        Lancamento.conta_id == conta_id,
        Lancamento.referencia_mes == referencia,
        Lancamento.fonte == FONTE_PLANILHA,
    )
    duplicados = session.exec(stmt).all()
    for lanc in duplicados:
        session.delete(lanc)
    return len(duplicados)


def limpar_planilha_quando_pdf_existe(
    session: Session | None = None,
) -> dict[str, int]:
    """Backfill: percorre todas as Faturas PDF e remove planilha duplicada.

    Útil pra corrigir bancos antigos onde a planilha foi importada
    antes dos PDFs (a regra de dedup do `importar_planilha_familiar`
    só atua na direção planilha→PDF). Idempotente: rodar de novo não
    faz nada.

    Devolve `{"faturas_examinadas": N, "lancamentos_removidos": M}`.
    """
    if session is None:
        with get_session() as s:
            return limpar_planilha_quando_pdf_existe(session=s)

    removidos = 0
    faturas = session.exec(select(Fatura)).all()
    for fat in faturas:
        if not fat.referencia_mes:
            continue
        removidos += _remover_planilha_duplicada(
            session, conta_id=fat.conta_id, referencia=fat.referencia_mes
        )
    return {
        "faturas_examinadas": len(faturas),
        "lancamentos_removidos": removidos,
    }


def remover_lancamentos_planilha_por_descricao(
    descricao: str, *, session: Session | None = None
) -> int:
    """Apaga todos os lançamentos de fonte planilha com a `descricao` dada.

    Usado depois de adicionar uma linha em
    `imports.importar_planilha_familiar.LINHAS_IGNORADAS` pra limpar
    valores que já foram persistidos antes da regra entrar em vigor
    (ex.: linha agregada "Moradia (mensal)" que duplicava
    Luz/Água/Internet).

    Devolve a quantidade de lançamentos removidos.
    """
    if session is None:
        with get_session() as s:
            return remover_lancamentos_planilha_por_descricao(
                descricao, session=s
            )

    stmt = select(Lancamento).where(
        Lancamento.fonte == FONTE_PLANILHA,
        Lancamento.descricao == descricao,
    )
    alvos = session.exec(stmt).all()
    for lanc in alvos:
        session.delete(lanc)
    return len(alvos)


def existe_fatura_pdf(
    *,
    conta_nome: str,
    ano: int,
    mes: int,
    session: Session | None = None,
) -> bool:
    """Existe alguma Fatura PDF pra (conta, ano, mês)?

    Usado pela importação da planilha familiar pra pular linhas de
    cartão quando já temos o PDF detalhado da mesma referência —
    evita duplicar o valor agregado.
    """
    if session is None:
        with get_session() as s:
            return existe_fatura_pdf(
                conta_nome=conta_nome, ano=ano, mes=mes, session=s
            )

    referencia = f"{ano:04d}-{mes:02d}"
    conta = _obter_conta_por_nome(session, conta_nome)
    if conta is None:
        return False
    stmt = (
        select(Fatura.id)
        .where(
            Fatura.conta_id == conta.id,
            Fatura.referencia_mes == referencia,
        )
        .limit(1)
    )
    return session.exec(stmt).first() is not None


def upsert_lancamento_manual(
    *,
    descricao: str,
    valor: float | Decimal,
    ano: int,
    mes: int,
    categoria_nome: str,
    pessoa_nome: str | None = None,
    conta_nome: str | None = None,
    tipo: str = TIPO_LANCAMENTO_DESPESA,
    categoria_tipo: str = TIPO_CATEGORIA_DESPESA,
    chave_planilha: str | None = None,
    fonte: str = FONTE_PLANILHA,
    arquivo_origem: str | None = None,
    session: Session | None = None,
) -> tuple[int | None, bool, bool]:
    """Insere um lançamento sintético (planilha mensal / entrada manual).

    Diferente de `upsert_fatura`, aqui cada linha é independente: não
    pertence a uma fatura. A data é fixada no 1º dia do mês de
    referência (esses valores na planilha são agregados mensais sem
    dia exato).

    Idempotência via `hash_lancamento_planilha(chave_planilha, ano,
    mês, pessoa)`. Se `chave_planilha` não for passada, usa
    `descricao` como chave.

    Quando já existe linha com o mesmo hash:
      - Se o valor diverge, faz UPDATE no `valor` (e `atualizado_em`)
        — permite refletir edições do usuário na planilha em re-imports.
        Categoria, override e demais campos são preservados.
      - Se o valor bate, é no-op.

    Devolve `(lancamento_id, inserido_agora, atualizado_agora)`. Os
    bools são mutuamente exclusivos: `(True, False)` = linha nova,
    `(False, True)` = update de valor, `(False, False)` = no-op.
    """
    if session is None:
        with get_session() as s:
            return upsert_lancamento_manual(
                descricao=descricao,
                valor=valor,
                ano=ano,
                mes=mes,
                categoria_nome=categoria_nome,
                pessoa_nome=pessoa_nome,
                conta_nome=conta_nome,
                tipo=tipo,
                categoria_tipo=categoria_tipo,
                chave_planilha=chave_planilha,
                fonte=fonte,
                arquivo_origem=arquivo_origem,
                session=s,
            )

    chave = chave_planilha or descricao
    h = hash_lancamento_planilha(
        categoria_planilha=chave,
        ano=ano,
        mes=mes,
        pessoa_nome=pessoa_nome,
    )

    valor_dec = _arred(valor)
    existente = session.exec(
        select(Lancamento).where(Lancamento.hash_dedupe == h)
    ).first()
    if existente is not None:
        # Re-import com valor alterado na planilha: atualiza só o
        # valor (e timestamp). Categoria/override/conta/pessoa ficam
        # como estão — o usuário pode ter ajustado manualmente.
        valor_novo = abs(valor_dec)
        if Decimal(existente.valor) != valor_novo:
            existente.valor = valor_novo
            existente.atualizado_em = _agora_utc()
            session.add(existente)
            return existente.id, False, True
        return existente.id, False, False

    pessoa = (
        _obter_ou_criar_pessoa(session, pessoa_nome)
        if pessoa_nome
        else None
    )
    conta = (
        _obter_ou_criar_conta(
            session, nome=conta_nome, tipo=TIPO_CONTA_OUTRO, pessoa=pessoa
        )
        if conta_nome
        else None
    )
    categoria = _obter_ou_criar_categoria(
        session, nome=categoria_nome, tipo=categoria_tipo
    )

    data_ref = date(ano, mes, 1)
    referencia = f"{ano:04d}-{mes:02d}"

    lanc = Lancamento(
        data=data_ref,
        descricao=descricao,
        valor=abs(valor_dec),
        tipo=tipo,
        categoria_id=categoria.id,
        conta_id=conta.id if conta else None,
        pessoa_id=pessoa.id if pessoa else None,
        fatura_id=None,
        referencia_mes=referencia,
        parcela_atual=None,
        parcela_total=None,
        cidade=None,
        fonte=fonte,
        arquivo_origem=arquivo_origem,
        hash_dedupe=h,
    )
    session.add(lanc)
    session.flush()
    return lanc.id, True, False


def _parse_parcela(texto: str | None) -> tuple[int | None, int | None]:
    """'02/12' → (2, 12). Vazio/inválido → (None, None)."""
    if not texto:
        return None, None
    m = re.match(r"\s*(\d+)\s*/\s*(\d+)\s*$", texto.strip())
    if not m:
        return None, None
    atual, total = int(m.group(1)), int(m.group(2))
    if total < 1 or atual < 1 or atual > total:
        return None, None
    return atual, total


def listar_lancamentos_df(
    *,
    sinal_estorno_negativo: bool = True,
) -> pd.DataFrame:
    """Devolve todos os lançamentos como DataFrame.

    Colunas espelham (com nomes pythonicos) o que a aba `Transações`
    do Excel já tem, facilitando o `export/excel.py`.

    Quando `sinal_estorno_negativo=True` (default), estornos voltam
    como valor negativo — mantém compat com Excel atual em que
    `Valor (R$) < 0` significa estorno.
    """
    with get_session() as session:
        stmt = (
            select(Lancamento, Categoria, Conta, Pessoa, Fatura)
            .join(Categoria, Lancamento.categoria_id == Categoria.id, isouter=True)
            .join(Conta, Lancamento.conta_id == Conta.id, isouter=True)
            .join(Pessoa, Lancamento.pessoa_id == Pessoa.id, isouter=True)
            .join(Fatura, Lancamento.fatura_id == Fatura.id, isouter=True)
            .order_by(Lancamento.data, Lancamento.id)
        )
        rows = session.exec(stmt).all()

        registros: list[dict[str, Any]] = []
        for lanc, cat, conta, pessoa, fatura in rows:
            valor_dec = Decimal(lanc.valor)
            if sinal_estorno_negativo and lanc.tipo == TIPO_LANCAMENTO_ESTORNO:
                valor_dec = -valor_dec
            referencia = lanc.referencia_mes or (
                fatura.referencia_mes if fatura else ""
            )
            parcela = (
                f"{lanc.parcela_atual:02d}/{lanc.parcela_total:02d}"
                if lanc.parcela_atual and lanc.parcela_total
                else ""
            )
            registros.append(
                {
                    "id": lanc.id,
                    "data": lanc.data,
                    "descricao": lanc.descricao,
                    "valor": float(valor_dec),
                    "tipo": lanc.tipo,
                    "categoria": cat.nome if cat else "",
                    "conta": conta.nome if conta else "",
                    "conta_tipo": conta.tipo if conta else "",
                    "pessoa": pessoa.nome if pessoa else "",
                    "referencia_mes": referencia or "",
                    "parcela": parcela,
                    "cidade": lanc.cidade or "",
                    "fonte": lanc.fonte,
                    "arquivo": (
                        fatura.arquivo if fatura else (lanc.arquivo_origem or "")
                    ),
                    "observacao": lanc.observacao or "",
                }
            )
    return pd.DataFrame(registros)


def listar_faturas_df() -> pd.DataFrame:
    """Cabeçalhos das faturas (espelha aba `Informações` do Excel)."""
    with get_session() as session:
        stmt = (
            select(Fatura, Conta, Pessoa)
            .join(Conta, Fatura.conta_id == Conta.id, isouter=True)
            .join(Pessoa, Conta.pessoa_id == Pessoa.id, isouter=True)
            .order_by(Fatura.vencimento, Fatura.id)
        )
        rows = session.exec(stmt).all()

        registros: list[dict[str, Any]] = []
        for fatura, conta, pessoa in rows:
            registros.append(
                {
                    "id": fatura.id,
                    "arquivo": fatura.arquivo,
                    "conta": conta.nome if conta else "",
                    "pessoa": pessoa.nome if pessoa else "",
                    "referencia_mes": fatura.referencia_mes or "",
                    "fechamento": fatura.fechamento,
                    "vencimento": fatura.vencimento,
                    "valor_total_declarado": (
                        float(fatura.valor_total_declarado)
                        if fatura.valor_total_declarado is not None
                        else None
                    ),
                    "qtde_transacoes": fatura.qtde_transacoes,
                }
            )
    return pd.DataFrame(registros)


def faturas_ja_importadas() -> set[str]:
    """Conjunto de nomes de arquivo (PDF) já no banco. Pulado em re-runs."""
    with get_session() as session:
        rows = session.exec(select(Fatura.arquivo)).all()
    return set(rows)


def recategorizar_todos() -> dict[str, int]:
    """Re-aplica overrides + dicionário em todos os lançamentos.

    Devolve `{"mudados": N, "total": M}`. Equivalente ao subcomando
    `gastometro recategorizar` da CLI antiga, mas opera no banco em
    vez de no Excel.
    """
    mudados = 0
    total = 0
    with get_session() as session:
        overrides = _cache_overrides(session)
        lancs = session.exec(select(Lancamento)).all()
        total = len(lancs)
        for lanc in lancs:
            cat_id_novo, _ = _categorizar_para_id(
                session, lanc.descricao, overrides
            )
            if cat_id_novo != lanc.categoria_id:
                lanc.categoria_id = cat_id_novo
                session.add(lanc)
                mudados += 1
    return {"mudados": mudados, "total": total}


def salvar_override(descricao: str, categoria_nome: str) -> None:
    """Persiste um override manual (descrição → categoria).

    A descrição é normalizada antes de salvar. Se a categoria não
    existir, é criada como despesa.
    """
    norm = normalizar_descricao(descricao)
    if not norm or not categoria_nome:
        return
    with get_session() as session:
        cat = _obter_ou_criar_categoria(
            session, nome=categoria_nome.strip(), tipo=TIPO_CATEGORIA_DESPESA
        )
        existente = session.get(OverrideCategoria, norm)
        if existente is None:
            session.add(
                OverrideCategoria(
                    descricao_normalizada=norm, categoria_id=cat.id
                )
            )
        else:
            existente.categoria_id = cat.id
            session.add(existente)


def importar_categorias_usuario_json(caminho: Any) -> int:
    """Migra `categorias_usuario.json` (formato legado) pra tabela override.

    Devolve a qtde de overrides salvos. Idempotente — repetir não duplica
    (chave é `descricao_normalizada`).
    """
    import json
    from pathlib import Path

    p = Path(caminho)
    if not p.exists():
        return 0
    try:
        with p.open(encoding="utf-8") as f:
            dados = json.load(f)
    except (json.JSONDecodeError, OSError):
        return 0
    inseridos = 0
    with get_session() as session:
        for descricao, categoria in dados.items():
            if not isinstance(categoria, str) or not categoria.strip():
                continue
            norm = normalizar_descricao(str(descricao))
            if not norm:
                continue
            cat = _obter_ou_criar_categoria(
                session, nome=categoria.strip(), tipo=TIPO_CATEGORIA_DESPESA
            )
            existente = session.get(OverrideCategoria, norm)
            if existente is None:
                session.add(
                    OverrideCategoria(
                        descricao_normalizada=norm, categoria_id=cat.id
                    )
                )
                inseridos += 1
            else:
                existente.categoria_id = cat.id
                session.add(existente)
    return inseridos


def listar_overrides_dict() -> dict[str, str]:
    """Snapshot dos overrides como `{descricao_normalizada: nome_categoria}`.

    Útil pra exportar de volta pra JSON ou pra alimentar a UI.
    """
    with get_session() as session:
        stmt = select(OverrideCategoria.descricao_normalizada, Categoria.nome).join(
            Categoria, OverrideCategoria.categoria_id == Categoria.id
        )
        rows = session.exec(stmt).all()
    return {desc: nome for desc, nome in rows}


def listar_escopos_categoria_dict() -> dict[str, str]:
    """`{nome_categoria: escopo}` dos overrides persistidos."""
    with get_session() as session:
        stmt = select(Categoria.nome, EscopoCategoria.escopo).join(
            EscopoCategoria, EscopoCategoria.categoria_id == Categoria.id
        )
        rows = session.exec(stmt).all()
    return {nome: escopo for nome, escopo in rows}


def salvar_escopo_categoria(categoria_nome: str, escopo: str) -> None:
    """Persiste escopo casal/pessoal para uma categoria."""
    if escopo not in {ESCOPO_CASAL, ESCOPO_PESSOAL}:
        return
    nome = categoria_nome.strip()
    if not nome:
        return
    with get_session() as session:
        cat = session.exec(select(Categoria).where(Categoria.nome == nome)).first()
        if cat is None:
            return
        existente = session.get(EscopoCategoria, cat.id)
        if existente is None:
            session.add(EscopoCategoria(categoria_id=cat.id, escopo=escopo))
        else:
            existente.escopo = escopo
            session.add(existente)


def listar_orcamentos_df(referencia_mes: str) -> pd.DataFrame:
    """Metas de orçamento de um mês com nomes resolvidos."""
    with get_session() as session:
        stmt = (
            select(OrcamentoMeta, Categoria, Pessoa)
            .join(Categoria, OrcamentoMeta.categoria_id == Categoria.id, isouter=True)
            .join(Pessoa, OrcamentoMeta.pessoa_id == Pessoa.id, isouter=True)
            .where(OrcamentoMeta.referencia_mes == referencia_mes)
            .order_by(OrcamentoMeta.escopo, OrcamentoMeta.id)
        )
        rows = session.exec(stmt).all()

        registros: list[dict[str, Any]] = []
        for meta, cat, pessoa in rows:
            registros.append(
                {
                    "id": meta.id,
                    "referencia_mes": meta.referencia_mes,
                    "escopo": meta.escopo,
                    "pessoa": pessoa.nome if pessoa else "",
                    "pessoa_id": meta.pessoa_id,
                    "categoria": cat.nome if cat else "",
                    "categoria_id": meta.categoria_id,
                    "valor_limite": float(meta.valor_limite),
                }
            )
    return pd.DataFrame(registros)


def salvar_orcamento_meta(
    *,
    referencia_mes: str,
    escopo: str,
    valor_limite: float,
    pessoa_id: int | None = None,
    categoria_id: int | None = None,
    meta_id: int | None = None,
) -> None:
    """Cria ou atualiza uma meta de orçamento."""
    if escopo not in {ESCOPO_CASAL, ESCOPO_PESSOAL}:
        return
    limite = Decimal(str(valor_limite)).quantize(Decimal("0.01"))
    with get_session() as session:
        if meta_id is not None:
            meta = session.get(OrcamentoMeta, meta_id)
            if meta is not None:
                meta.valor_limite = limite
                meta.escopo = escopo
                meta.pessoa_id = pessoa_id
                meta.categoria_id = categoria_id
                meta.atualizado_em = _agora_utc()
                session.add(meta)
                return

        stmt = select(OrcamentoMeta).where(
            OrcamentoMeta.referencia_mes == referencia_mes,
            OrcamentoMeta.escopo == escopo,
            OrcamentoMeta.pessoa_id == pessoa_id,
            OrcamentoMeta.categoria_id == categoria_id,
        )
        existente = session.exec(stmt).first()
        if existente is not None:
            existente.valor_limite = limite
            existente.atualizado_em = _agora_utc()
            session.add(existente)
        else:
            session.add(
                OrcamentoMeta(
                    referencia_mes=referencia_mes,
                    escopo=escopo,
                    pessoa_id=pessoa_id,
                    categoria_id=categoria_id,
                    valor_limite=limite,
                )
            )


def excluir_orcamento_meta(meta_id: int) -> None:
    with get_session() as session:
        meta = session.get(OrcamentoMeta, meta_id)
        if meta is not None:
            session.delete(meta)


def copiar_orcamentos_de_mes(origem: str, destino: str) -> int:
    """Copia metas de `origem` para `destino`. Não sobrescreve metas já existentes."""
    if not origem or not destino or origem == destino:
        return 0
    with get_session() as session:
        origem_metas = session.exec(
            select(OrcamentoMeta).where(OrcamentoMeta.referencia_mes == origem)
        ).all()
        if not origem_metas:
            return 0
        destino_metas = session.exec(
            select(OrcamentoMeta).where(OrcamentoMeta.referencia_mes == destino)
        ).all()
        chaves_destino = {
            (m.escopo, m.pessoa_id, m.categoria_id) for m in destino_metas
        }
        copiados = 0
        for meta in origem_metas:
            chave = (meta.escopo, meta.pessoa_id, meta.categoria_id)
            if chave in chaves_destino:
                continue
            session.add(
                OrcamentoMeta(
                    referencia_mes=destino,
                    escopo=meta.escopo,
                    pessoa_id=meta.pessoa_id,
                    categoria_id=meta.categoria_id,
                    valor_limite=meta.valor_limite,
                )
            )
            copiados += 1
        return copiados


# Mantida para futuras categorias de receita; ainda não usada na Fase 1
# (PDFs só geram despesas/estornos), mas preparada pra Fase 3 (planilha
# familiar) e entradas manuais.
def _tipo_lancamento_receita_para_categoria(_categoria_nome: str) -> str:
    return TIPO_LANCAMENTO_RECEITA
