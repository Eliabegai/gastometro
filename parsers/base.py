"""Tipos compartilhados e utilidades comuns aos parsers de fatura."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

MESES_PT = {
    "JAN": 1, "FEV": 2, "MAR": 3, "ABR": 4, "MAI": 5, "JUN": 6,
    "JUL": 7, "AGO": 8, "SET": 9, "OUT": 10, "NOV": 11, "DEZ": 12,
}

MES_POR_NUMERO = {
    1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril",
    5: "Maio", 6: "Junho", 7: "Julho", 8: "Agosto",
    9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro",
}


@dataclass
class FaturaMetadata:
    """Cabeçalho da fatura: banco, titular, datas e referência."""
    banco: str = ""
    titular: str = ""
    referencia_mes: str = ""
    data_fechamento: str = ""
    data_vencimento: str = ""
    valor_total: float = 0.0


@dataclass
class Transacao:
    """Uma linha de lançamento na fatura."""
    data: str
    descricao: str
    parcela: str
    cidade: str
    valor: float
    categoria: str = ""


@dataclass
class Fatura:
    """Resultado completo da extração de uma fatura."""
    metadata: FaturaMetadata
    transacoes: list[Transacao] = field(default_factory=list)


def parse_valor_brl(texto: str | None) -> float | None:
    """Converte strings como 'R$ 1.234,56' ou '-R$ 932,54' em float.

    Aceita formato BR clássico (`1.234,56`) e formato americano usado em
    algumas faturas (`1,234.56`). Tolera pontuação trailing herdada de
    capturas amplas por regex (ex.: `"4,422.81."`).
    """
    if texto is None:
        return None
    limpo = (
        texto.replace("R$", "")
        .replace("\u2212", "-")
        .replace(" ", "")
        .strip()
        .rstrip(".,")
    )
    if not limpo:
        return None
    negativo = limpo.startswith("-")
    if negativo:
        limpo = limpo[1:]
    if "," in limpo and "." in limpo:
        if limpo.rfind(",") > limpo.rfind("."):
            limpo = limpo.replace(".", "").replace(",", ".")
        else:
            limpo = limpo.replace(",", "")
    elif "," in limpo:
        limpo = limpo.replace(",", ".")
    try:
        valor = float(limpo)
    except ValueError:
        return None
    return -valor if negativo else valor


def formatar_data(dia: int | str, mes: int | str, ano: int) -> str:
    """Formata data como DD/MM/AAAA. `mes` aceita número (1-12) ou abreviação (JAN, FEV...)."""
    if isinstance(mes, str):
        numero = MESES_PT.get(mes.upper())
        if numero is None:
            return f"{int(dia):02d}/{mes}/{ano}"
        mes_num = numero
    else:
        mes_num = int(mes)
    return f"{int(dia):02d}/{mes_num:02d}/{ano}"


def referencia_pelo_vencimento(data_vencimento: str) -> str:
    """A referência da fatura corresponde ao mês do vencimento (ex.: 'Maio/2026')."""
    match = re.match(r"(\d{2})/(\d{2})/(\d{4})", data_vencimento)
    if not match:
        return ""
    _, mes, ano = match.groups()
    nome_mes = MES_POR_NUMERO.get(int(mes), mes)
    return f"{nome_mes}/{ano}"


def ano_do_vencimento(data_vencimento: str) -> int:
    """Extrai o ano (AAAA) de uma data no formato DD/MM/AAAA.

    Retorna o ano corrente quando a data não estiver no formato esperado.
    """
    m = re.match(r"\d{2}/\d{2}/(\d{4})", data_vencimento)
    if m:
        return int(m.group(1))
    return date.today().year


def _menos_meses(mes: int, ano: int, n: int) -> tuple[int, int]:
    """Subtrai `n` meses de `(mes, ano)` e devolve `(mes_resultante, ano_resultante)`."""
    total = ano * 12 + (mes - 1) - n
    return (total % 12) + 1, total // 12


def _numero_da_parcela(parcela: str) -> int | None:
    """Extrai o número da parcela atual (ex.: '16' de '16/18'). Retorna None se inválido."""
    if not parcela:
        return None
    m = re.match(r"\s*(\d+)\s*/\s*(\d+)\s*$", parcela)
    if not m:
        return None
    atual, total = int(m.group(1)), int(m.group(2))
    if total < 1 or atual < 1 or atual > total:
        return None
    return atual


def inferir_ano_transacao(
    mes_transacao: int,
    data_vencimento: str,
    parcela: str = "",
    *,
    recuar_pelo_numero_da_parcela: bool = False,
) -> int:
    """Infere o ano de uma transação a partir do mês dela e do vencimento da fatura.

    Regra base (sempre aplicada quando o recuo por parcela está desligado
    ou quando não há parcela `X/Y` com `X > 1`):
      - Se `mes_transacao > mes_vencimento`, a transação é do ano anterior
        (caso comum: compras de dezembro aparecendo na fatura de janeiro).
      - Caso contrário, do mesmo ano do vencimento.

    Recuo por número de parcela (`recuar_pelo_numero_da_parcela=True`):
      - Quando a fatura mostra a **data da compra original** (não a data
        da cobrança da parcela atual), o ano da transação é o da compra,
        que foi feita há `X - 1` meses se vemos a parcela `X/Y`. Recua
        `X - 1` meses a partir do mês do vencimento e devolve o ano
        resultante. Cobre parcelamentos longos que cruzam virada de ano
        (ex.: `MAPFRE 14 JAN 16/18` em fatura de maio/2026 → 2025).

    Quando ligar o recuo?
      - **Ailos**: a data exibida na fatura é a data da compra → ligar.
      - **Nubank**: a data exibida é a data da cobrança da parcela
        (sempre dia 6 do ciclo) → manter desligado.

    Limitação conhecida: assume parcelas estritamente mensais e que a 1ª
    cobrança ocorre no mesmo mês da compra. Pequenos desvios (1 mês)
    geralmente não afetam o ano resultante.
    """
    m = re.match(r"\d{2}/(\d{2})/(\d{4})", data_vencimento)
    if not m:
        return date.today().year
    mes_venc, ano_venc = int(m.group(1)), int(m.group(2))

    if recuar_pelo_numero_da_parcela:
        n_parcela = _numero_da_parcela(parcela)
        if n_parcela is not None and n_parcela > 1:
            _, ano_calc = _menos_meses(mes_venc, ano_venc, n_parcela - 1)
            return ano_calc

    if mes_transacao > mes_venc:
        return ano_venc - 1
    return ano_venc


PALAVRAS_NAO_TITULAR = {
    "ENCARGOS", "PAGAMENTO", "MÍNIMO", "MINIMO", "TOTAL", "DATA", "DESCRIÇÃO",
    "VALOR", "CIDADE", "MOVIMENTAÇÕES", "FATURA", "SALDO", "CRÉDITO", "LIMITE",
    "VENCIMENTO", "REF", "ATENÇÃO", "RESUMO", "DÍVIDA", "PARCELAMENTOS",
    "TARIFAS", "TOTAIS", "MASTERCARD", "OUROCARD", "NUBANK", "BANCO", "BRASIL",
    "AILOS", "CARTÃO", "SAQUE", "COMPRAS", "PRESENTES", "ARTIGOS", "SERVIÇOS",
    "AUTOMÓVEIS", "VEÍCULOS", "TRANSPORTES", "CONSTRUÇÃO", "REFORMA",
    "COOPERATIVAS", "PRODUTOS", "EDUCAÇÃO", "ESPORTES", "TURISMO", "LAZER",
    "ESTÉTICA", "CUIDADOS", "GASTRONOMIA", "INFORMÁTICA", "POSTOS", "GASOLINA",
    "SAÚDE", "SUPERMERCADO", "HIPERMERCADO", "VESTUÁRIO", "DIVERSOS", "SAQUES",
    "EMPRÉSTIMOS", "DINHEIRO", "MOVIMENTACOES", "CONTA", "PRO", "GOLD",
    "ANUIDADE", "MAS",
}


def detectar_titular(texto: str) -> str:
    """Identifica o nome do titular procurando a linha em maiúsculas mais frequente.

    Filtros aplicados, em ordem:
      1. Linhas com 2 a 6 palavras (nomes próprios típicos).
      2. Cada palavra deve ser composta apenas por letras maiúsculas
         acentuadas (regex `[A-ZÁÉÍÓÚÂÊÔÃÕÇ]{2,}`). Essa regra sozinha já
         elimina linhas com finais de cartão (ex.: "FULANO DE TAL 1234"),
         números de documento e códigos.
      3. Linhas com termos administrativos comuns (PAGAMENTO, TOTAL,
         CARTÃO, ANUIDADE, etc.) são ignoradas via `PALAVRAS_NAO_TITULAR`.
    """
    contagem: dict[str, int] = {}
    for linha in texto.splitlines():
        linha = linha.strip()
        if not linha:
            continue
        palavras = linha.split()
        if len(palavras) < 2 or len(palavras) > 6:
            continue
        if not all(re.fullmatch(r"[A-ZÁÉÍÓÚÂÊÔÃÕÇ]{2,}", p) for p in palavras):
            continue
        if any(p in PALAVRAS_NAO_TITULAR for p in palavras):
            continue
        contagem[linha] = contagem.get(linha, 0) + 1
    if not contagem:
        return ""
    melhor = max(contagem.items(), key=lambda x: (x[1], len(x[0])))
    return melhor[0].title()
