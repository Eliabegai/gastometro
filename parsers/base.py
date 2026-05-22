"""Tipos compartilhados e utilidades comuns aos parsers de fatura."""

from __future__ import annotations

import re
from dataclasses import dataclass, field


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


def parse_valor_brl(texto: str) -> float | None:
    """Converte strings como 'R$ 1.234,56' ou '-R$ 932,54' em float."""
    if texto is None:
        return None
    limpo = (
        texto.replace("R$", "")
        .replace("\u2212", "-")
        .replace(" ", "")
        .strip()
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
    "ANUIDADE", "MAS", "ELIABE GAI 8449", "ELIABE GAI 7316",
}


def detectar_titular(texto: str) -> str:
    """Identifica o nome do titular procurando a linha em maiúsculas mais frequente.

    Ignora linhas que contenham palavras administrativas comuns (encargos,
    pagamento, total, etc.).
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
