"""Modelos SQLModel das tabelas do banco.

Convenções:
  - IDs autoincrementais (`int | None` com `primary_key=True`).
  - `valor` em `Decimal(12, 2)` — sempre positivo. `tipo` (despesa /
    receita / estorno) decide a direção do fluxo de caixa.
  - `hash_dedupe` é índice único para garantir idempotência de imports
    (mesma transação reimportada do PDF ou da planilha não duplica).
  - `referencia_mes` em `YYYY-MM` (string) — facilita ordenação e
    agrupamento sem dependência de locale.

Os "tipos enumerados" (tipo de conta, tipo de lançamento, fonte) são
strings livres validadas pelos constants em `TIPOS_*` abaixo. Isso evita
problemas de migração quando um valor novo precisa ser introduzido —
basta acrescentar à constante; o banco aceita strings arbitrárias.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from sqlmodel import Field, SQLModel


def _agora_utc() -> datetime:
    """Substitui `datetime.utcnow()` (deprecado em 3.12+). Usa
    `timezone.utc` em vez de `datetime.UTC` por compat com Python 3.10."""
    return datetime.now(timezone.utc)

TIPO_CONTA_CARTAO = "cartao_credito"
TIPO_CONTA_CORRENTE = "conta_corrente"
TIPO_CONTA_DINHEIRO = "dinheiro"
TIPO_CONTA_OUTRO = "outro"
TIPOS_CONTA = {
    TIPO_CONTA_CARTAO,
    TIPO_CONTA_CORRENTE,
    TIPO_CONTA_DINHEIRO,
    TIPO_CONTA_OUTRO,
}

TIPO_CATEGORIA_DESPESA = "despesa"
TIPO_CATEGORIA_RECEITA = "receita"
TIPOS_CATEGORIA = {TIPO_CATEGORIA_DESPESA, TIPO_CATEGORIA_RECEITA}

TIPO_LANCAMENTO_DESPESA = "despesa"
TIPO_LANCAMENTO_RECEITA = "receita"
TIPO_LANCAMENTO_ESTORNO = "estorno"
TIPO_LANCAMENTO_TRANSFERENCIA = "transferencia"
TIPOS_LANCAMENTO = {
    TIPO_LANCAMENTO_DESPESA,
    TIPO_LANCAMENTO_RECEITA,
    TIPO_LANCAMENTO_ESTORNO,
    TIPO_LANCAMENTO_TRANSFERENCIA,
}

FONTE_PDF = "pdf_fatura"
FONTE_PLANILHA = "planilha_historico"
FONTE_MANUAL = "manual"
FONTE_EXCEL_LEGADO = "excel_legado"
FONTE_CSV = "csv"
FONTES = {FONTE_PDF, FONTE_PLANILHA, FONTE_MANUAL, FONTE_EXCEL_LEGADO, FONTE_CSV}

# Streamlit reexecuta módulos no rerun; sem isso o SQLAlchemy reclama que a
# tabela já existe no MetaData global.
_TABLE_ARGS: dict[str, bool] = {"extend_existing": True}


class Pessoa(SQLModel, table=True):
    """Quem é o dono/responsável por uma despesa ou receita.

    Lançamentos com `pessoa_id is None` são tratados como conjuntos
    (do casal). Útil pra contas de casa que não pertencem a um único
    titular.

    Nota: relationships ORM (`contas`, `lancamentos`) foram omitidas
    intencionalmente — SQLModel + SQLAlchemy 2.x tem fricção com
    forward references em projetos com `from __future__ import
    annotations`. Pra navegação cross-tabela, use joins explícitos
    no `db.repository` (mais legível e performático).
    """

    __tablename__ = "pessoa"
    __table_args__ = _TABLE_ARGS

    id: int | None = Field(default=None, primary_key=True)
    nome: str = Field(index=True, unique=True)
    ativo: bool = Field(default=True)


class Conta(SQLModel, table=True):
    """Conta-corrente, cartão de crédito, dinheiro ou outro veículo financeiro.

    Distingue cartões com o mesmo banco mas titulares diferentes
    (ex.: "Nubank Eliabe" vs "Nubank Ana"). Faturas (`fatura`)
    pertencem sempre a uma `Conta` do tipo `cartao_credito`.
    """

    __tablename__ = "conta"
    __table_args__ = _TABLE_ARGS

    id: int | None = Field(default=None, primary_key=True)
    nome: str = Field(index=True, unique=True)
    tipo: str = Field(default=TIPO_CONTA_OUTRO)
    pessoa_id: int | None = Field(default=None, foreign_key="pessoa.id")


class Categoria(SQLModel, table=True):
    """Categoria canônica de despesa ou receita.

    Seed inicial vem de `categorias.py` (despesas) + lista fixa de
    receitas. Edições futuras feitas pela UI ficam na tabela; o arquivo
    `categorias.py` continua servindo apenas como semente inicial.
    """

    __tablename__ = "categoria"
    __table_args__ = _TABLE_ARGS

    id: int | None = Field(default=None, primary_key=True)
    nome: str = Field(index=True, unique=True)
    tipo: str = Field(default=TIPO_CATEGORIA_DESPESA)
    cor: str | None = Field(default=None)


class Fatura(SQLModel, table=True):
    """Cabeçalho de uma fatura de cartão de crédito (PDF parseado).

    Equivalente à aba `Informações` do Excel atual. 1 fatura → N
    `Lancamento`s vinculados via `fatura_id`. `arquivo` é único
    (nome do PDF) — bloqueia importar a mesma fatura duas vezes.
    """

    __tablename__ = "fatura"
    __table_args__ = _TABLE_ARGS

    id: int | None = Field(default=None, primary_key=True)
    conta_id: int = Field(foreign_key="conta.id", index=True)
    arquivo: str = Field(index=True, unique=True)
    referencia_mes: str = Field(index=True)
    fechamento: date | None = Field(default=None)
    vencimento: date | None = Field(default=None)
    valor_total_declarado: Decimal | None = Field(
        default=None, max_digits=12, decimal_places=2
    )
    qtde_transacoes: int = Field(default=0)
    criado_em: datetime = Field(default_factory=_agora_utc)


class Lancamento(SQLModel, table=True):
    """Uma transação individual (despesa, receita, estorno ou transferência).

    `valor` é sempre positivo; `tipo` decide o fluxo:
      - `despesa`: sai (cartão, débito, dinheiro).
      - `receita`: entra (salário, freela, doação).
      - `estorno`: crédito do banco (devolução, cashback). Para
        contabilidade, comporta-se como uma "receita" associada a um
        cartão.
      - `transferencia`: movimentação entre contas próprias.

    `hash_dedupe` (SHA1) garante idempotência:
      - Para PDF: `sha1(data|descricao_normalizada|valor|conta_id|arquivo)`.
      - Para planilha: `sha1("planilha"|categoria|ano|mes|pessoa)`.
      - Para manual: `sha1(data|descricao|valor|conta_id|timestamp_ms)`.
    """

    __tablename__ = "lancamento"
    __table_args__ = _TABLE_ARGS

    id: int | None = Field(default=None, primary_key=True)
    data: date = Field(index=True)
    descricao: str = Field(index=True)
    valor: Decimal = Field(max_digits=12, decimal_places=2)
    tipo: str = Field(default=TIPO_LANCAMENTO_DESPESA, index=True)

    categoria_id: int | None = Field(
        default=None, foreign_key="categoria.id", index=True
    )
    conta_id: int | None = Field(
        default=None, foreign_key="conta.id", index=True
    )
    pessoa_id: int | None = Field(
        default=None, foreign_key="pessoa.id", index=True
    )
    fatura_id: int | None = Field(
        default=None, foreign_key="fatura.id", index=True
    )

    referencia_mes: str | None = Field(default=None, index=True)
    parcela_atual: int | None = Field(default=None)
    parcela_total: int | None = Field(default=None)
    cidade: str | None = Field(default=None)

    fonte: str = Field(default=FONTE_MANUAL, index=True)
    arquivo_origem: str | None = Field(default=None)
    hash_dedupe: str = Field(unique=True, index=True)
    observacao: str | None = Field(default=None)

    criado_em: datetime = Field(default_factory=_agora_utc)
    atualizado_em: datetime = Field(default_factory=_agora_utc)


class OverrideCategoria(SQLModel, table=True):
    """Override manual de categoria por descrição normalizada.

    Substitui o arquivo `categorias_usuario.json`. Mesma semântica: a
    chave é a descrição normalizada (sem acentos, lowercase, espaços
    colapsados); o valor é o nome da categoria que deve prevalecer.
    Tem precedência sobre o dicionário fixo (`categorias.py`).
    """

    __tablename__ = "override_categoria"
    __table_args__ = _TABLE_ARGS

    descricao_normalizada: str = Field(primary_key=True)
    categoria_id: int = Field(foreign_key="categoria.id", index=True)
    criado_em: datetime = Field(default_factory=_agora_utc)


ESCOPO_CASAL = "casal"
ESCOPO_PESSOAL = "pessoal"
ESCOPOS = {ESCOPO_CASAL, ESCOPO_PESSOAL}


class EscopoCategoria(SQLModel, table=True):
    """Override de escopo (casal/pessoal) por categoria."""

    __tablename__ = "escopo_categoria"
    __table_args__ = _TABLE_ARGS

    categoria_id: int = Field(foreign_key="categoria.id", primary_key=True)
    escopo: str = Field(index=True)
    criado_em: datetime = Field(default_factory=_agora_utc)


class OrcamentoMeta(SQLModel, table=True):
    """Meta de orçamento mensal — casal ou pessoal."""

    __tablename__ = "orcamento_meta"
    __table_args__ = _TABLE_ARGS

    id: int | None = Field(default=None, primary_key=True)
    referencia_mes: str = Field(index=True)
    escopo: str = Field(index=True)
    pessoa_id: int | None = Field(default=None, foreign_key="pessoa.id", index=True)
    categoria_id: int | None = Field(default=None, foreign_key="categoria.id", index=True)
    valor_limite: Decimal = Field(max_digits=12, decimal_places=2)
    criado_em: datetime = Field(default_factory=_agora_utc)
    atualizado_em: datetime = Field(default_factory=_agora_utc)
