"""Parser de fatura Ailos Mastercard."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import pdfplumber

from categorias import categorizar

from .base import (
    MESES_PT,
    Fatura,
    FaturaMetadata,
    Transacao,
    detectar_titular,
    formatar_data,
    inferir_ano_transacao,
    parse_valor_brl,
    referencia_pelo_vencimento,
)


NOME_BANCO = "Ailos"

RE_DATA = re.compile(r"^\d{2}$")
RE_VALOR = re.compile(r"^-?[\d.,]+$")
RE_PARCELA = re.compile(r"^\d{1,2}/\d{1,2}$")

ADMINISTRATIVOS = (
    "PAGTO DEB EM CONTA",
    "PAGAMENTO RECEBIDO",
    "PAGAMENTO EFETUADO",
    "SALDO ANTERIOR",
    "TOTAL DE",
    "TOTAL R$",
)


@dataclass
class _Linha:
    top: float
    data_tokens: list[str] = field(default_factory=list)
    desc_tokens: list[str] = field(default_factory=list)
    cidade_tokens: list[str] = field(default_factory=list)
    valor_tokens: list[str] = field(default_factory=list)

    @property
    def tem_data(self) -> bool:
        return (
            len(self.data_tokens) >= 2
            and RE_DATA.match(self.data_tokens[0])
            and self.data_tokens[1].upper() in MESES_PT
        )

    @property
    def tem_valor(self) -> bool:
        return any(RE_VALOR.match(t) for t in self.valor_tokens)


def detectar(texto: str) -> bool:
    """Reconhece se o PDF é uma fatura Ailos."""
    indicadores = ("AILOS MASTERCARD", "VIACREDI", "App Ailos Cartões")
    return any(ind in texto for ind in indicadores)


def extrair(caminho_pdf: Path) -> Fatura:
    """Lê o PDF da fatura Ailos e devolve metadados + transações."""
    with pdfplumber.open(caminho_pdf) as pdf:
        texto_completo = "\n".join((p.extract_text() or "") for p in pdf.pages)
        metadata = _extrair_metadata(texto_completo)

        transacoes: list[Transacao] = []
        for pagina in pdf.pages:
            meio = pagina.width / 2
            esquerda = pagina.crop((0, 0, meio, pagina.height))
            direita = pagina.crop((meio, 0, pagina.width, pagina.height))
            for coluna in (esquerda, direita):
                linhas = _processar_coluna(coluna)
                if not linhas:
                    continue
                transacoes.extend(_montar_transacoes(linhas, metadata.data_vencimento))
            transacoes.extend(
                _extrair_movimentacoes_conta(esquerda, metadata.data_vencimento)
            )

    return Fatura(metadata=metadata, transacoes=transacoes)


def _extrair_metadata(texto: str) -> FaturaMetadata:
    metadata = FaturaMetadata(banco=NOME_BANCO)

    m = re.search(r"VENCIMENTO\s+(\d{1,2})\s+([A-Z]{3})\s+(\d{4})", texto)
    if m:
        metadata.data_vencimento = formatar_data(m.group(1), m.group(2), int(m.group(3)))

    m_fech = re.search(r"DATA DE FECHAMENTO DA FATURA\s+(\d{2}/\d{2}/\d{4})", texto)
    if m_fech:
        metadata.data_fechamento = m_fech.group(1)

    m_total = re.search(r"valor total de R\$\s*([\d.,]+)", texto)
    if not m_total:
        m_total = re.search(r"TOTAL\s+R\$\s*([\d.,]+)", texto)
    if m_total:
        valor = parse_valor_brl(m_total.group(1))
        if valor is not None:
            metadata.valor_total = valor

    metadata.titular = detectar_titular(texto)
    if not metadata.titular:
        m_titular = re.search(r"Olá,\s*([^!\n]+?)\s*!", texto)
        if m_titular:
            metadata.titular = m_titular.group(1).strip().title()

    metadata.referencia_mes = referencia_pelo_vencimento(metadata.data_vencimento)
    return metadata


def _eh_administrativa(descricao: str) -> bool:
    desc = descricao.upper()
    return any(termo in desc for termo in ADMINISTRATIVOS)


def _agrupar_palavras_em_linhas(palavras, tolerancia: float = 3.0) -> list[list[dict]]:
    if not palavras:
        return []
    palavras_ord = sorted(palavras, key=lambda w: (round(w["top"], 1), w["x0"]))
    linhas: list[list[dict]] = []
    linha_atual: list[dict] = []
    top_atual = palavras_ord[0]["top"]
    for palavra in palavras_ord:
        if abs(palavra["top"] - top_atual) <= tolerancia:
            linha_atual.append(palavra)
        else:
            linhas.append(sorted(linha_atual, key=lambda w: w["x0"]))
            linha_atual = [palavra]
            top_atual = palavra["top"]
    if linha_atual:
        linhas.append(sorted(linha_atual, key=lambda w: w["x0"]))
    return linhas


def _detectar_colunas(linhas_palavras):
    for linha in linhas_palavras:
        textos = [p["text"] for p in linha]
        if "DATA" in textos and "CIDADE" in textos and "VALOR" in textos:
            posicoes: dict[str, float] = {}
            top_cabecalho = linha[0]["top"]
            for p in linha:
                if p["text"] == "DATA":
                    posicoes["data"] = p["x0"]
                elif p["text"] == "DESCRIÇÃO":
                    posicoes["descricao"] = p["x0"]
                elif p["text"] == "CIDADE":
                    posicoes["cidade"] = p["x0"]
                elif p["text"] == "VALOR":
                    posicoes["valor"] = p["x0"]
            if all(k in posicoes for k in ("data", "descricao", "cidade", "valor")):
                return posicoes, top_cabecalho
    return None, None


def _classificar_palavras_em_colunas(linhas_palavras, colunas) -> list[_Linha]:
    limite_data_desc = (colunas["data"] + colunas["descricao"]) / 2
    limite_desc_cidade = (colunas["descricao"] + colunas["cidade"]) / 2
    limite_cidade_valor = (colunas["cidade"] + colunas["valor"]) / 2

    resultado: list[_Linha] = []
    for linha in linhas_palavras:
        l = _Linha(top=linha[0]["top"])
        for palavra in linha:
            x = palavra["x0"]
            texto = palavra["text"]
            if x < limite_data_desc:
                l.data_tokens.append(texto)
            elif x < limite_desc_cidade:
                l.desc_tokens.append(texto)
            elif x < limite_cidade_valor:
                l.cidade_tokens.append(texto)
            else:
                if texto == "R$":
                    continue
                l.valor_tokens.append(texto)
        resultado.append(l)
    return resultado


def _processar_coluna(coluna_crop) -> list[_Linha]:
    palavras = coluna_crop.extract_words(use_text_flow=False, keep_blank_chars=False)
    linhas_palavras = _agrupar_palavras_em_linhas(palavras)
    colunas, top_cabecalho = _detectar_colunas(linhas_palavras)
    if not colunas:
        return []
    linhas_abaixo = [
        linha for linha in linhas_palavras
        if linha and linha[0]["top"] > top_cabecalho + 1
    ]
    return _classificar_palavras_em_colunas(linhas_abaixo, colunas)


def _montar_transacoes(linhas: list[_Linha], data_vencimento: str) -> list[Transacao]:
    transacoes: list[Transacao] = []
    desc_pendente: list[str] = []
    cidade_pendente: list[str] = []

    for linha in linhas:
        todos_tokens = (
            linha.data_tokens + linha.desc_tokens + linha.cidade_tokens + linha.valor_tokens
        )
        texto_linha = " ".join(todos_tokens).strip()

        if not texto_linha:
            continue
        if texto_linha.upper().startswith(("DATA", "ELIABE", "REF", "PÁGINA", "DE 6")):
            continue
        if any(adm in texto_linha.upper() for adm in ADMINISTRATIVOS):
            desc_pendente = []
            cidade_pendente = []
            continue

        if linha.tem_data and linha.tem_valor:
            dia = linha.data_tokens[0]
            mes = linha.data_tokens[1]
            mes_num = MESES_PT.get(mes.upper())

            desc = " ".join(desc_pendente + linha.desc_tokens).strip()
            cidade = " ".join(cidade_pendente + linha.cidade_tokens).strip()
            valor = _parse_valor_tokens(linha.valor_tokens)

            if valor is None or mes_num is None or _eh_administrativa(desc):
                desc_pendente = []
                cidade_pendente = []
                continue

            parcela = ""
            m_parc = re.search(r"\b(\d{1,2}/\d{1,2})\b", desc)
            if m_parc:
                parcela = m_parc.group(1)
                desc = (desc[: m_parc.start()] + desc[m_parc.end():]).strip()

            ano = inferir_ano_transacao(
                mes_num, data_vencimento, parcela, recuar_pelo_numero_da_parcela=True
            )
            data = formatar_data(dia, mes, ano)

            transacoes.append(
                Transacao(
                    data=data,
                    descricao=desc,
                    parcela=parcela,
                    cidade=cidade,
                    valor=valor,
                    categoria=categorizar(desc),
                )
            )
            desc_pendente = []
            cidade_pendente = []
            continue

        if (
            len(linha.desc_tokens) == 1
            and RE_PARCELA.match(linha.desc_tokens[0])
            and not linha.data_tokens
            and not linha.valor_tokens
            and transacoes
        ):
            nova_parcela = linha.desc_tokens[0]
            transacoes[-1].parcela = nova_parcela
            m_data = re.match(r"(\d{2})/(\d{2})/\d{4}", transacoes[-1].data)
            if m_data:
                dia_str, mes_str_num = m_data.group(1), m_data.group(2)
                novo_ano = inferir_ano_transacao(
                    int(mes_str_num),
                    data_vencimento,
                    nova_parcela,
                    recuar_pelo_numero_da_parcela=True,
                )
                transacoes[-1].data = formatar_data(dia_str, int(mes_str_num), novo_ano)
            continue

        if not linha.data_tokens and not linha.valor_tokens:
            tokens_extras = linha.desc_tokens + linha.cidade_tokens
            sao_fragmentos = (
                transacoes
                and not desc_pendente
                and not cidade_pendente
                and tokens_extras
                and all(len(t) <= 2 for t in tokens_extras)
            )
            if sao_fragmentos:
                transacoes[-1].descricao = (
                    transacoes[-1].descricao + "".join(tokens_extras)
                ).strip()
                transacoes[-1].categoria = categorizar(transacoes[-1].descricao)
                continue
            if linha.desc_tokens:
                desc_pendente.extend(linha.desc_tokens)
            if linha.cidade_tokens:
                cidade_pendente.extend(linha.cidade_tokens)
            continue

    return transacoes


def _parse_valor_tokens(tokens: list[str]) -> float | None:
    """Extrai o valor numérico dos tokens da coluna VALOR, preservando o sinal.

    O pdfplumber costuma separar o sinal e o prefixo monetário em tokens
    distintos (ex.: a célula `-R$ 39,99` vira `["-R$", "39,99"]`). Aqui
    detectamos tokens que sinalizam negativo (`-R$`, `-`, sinal Unicode
    de menos) antes de encontrar o token numérico em si.
    """
    negativo = False
    for token in tokens:
        if token in ("-R$", "-", "\u2212"):
            negativo = True
            continue
        if token == "R$":
            continue
        if RE_VALOR.match(token):
            valor = parse_valor_brl(token)
            if valor is None:
                continue
            return -abs(valor) if negativo else valor
    return None


RE_MOV_PARCELA_LINHA = re.compile(
    r"^\(?\d{3,5}\)?\s+(?P<parcela>\d{1,2}/\d{1,2})\s*$"
)
RE_MOV_PARCELA_INLINE = re.compile(r"\b(\d{1,2}/\d{1,2})\b")

MOV_DESCARTAR = (
    "SALDO ANTERIOR",
    "PAGTO DEB EM CONTA",
    "PAGAMENTO RECEBIDO",
    "PAGAMENTO EFETUADO",
    "TOTAL DE",
    "TOTAL R$",
)


def _localizar_secao_movimentacoes(palavras) -> tuple[float, float] | None:
    """Localiza a faixa Y (top_inicial, top_final) da seção `MOVIMENTAÇÕES
    DA CONTA` numa coluna. Retorna `None` se a seção não estiver presente.

    O início é o `top` da palavra `MOVIMENTAÇÕES` e o fim é o `top` do
    cabeçalho `DATA DESCRIÇÃO CIDADE VALOR` que abre a tabela principal.
    """
    top_inicio: float | None = None
    top_fim: float | None = None
    for palavra in palavras:
        texto = palavra["text"]
        if top_inicio is None and texto.upper().startswith("MOVIMENTA"):
            top_inicio = palavra["top"]
            continue
        if top_inicio is not None and texto == "DATA" and palavra["top"] > top_inicio:
            top_fim = palavra["top"]
            break
    if top_inicio is None or top_fim is None:
        return None
    return top_inicio, top_fim


def _extrair_movimentacoes_conta(
    coluna, data_vencimento: str
) -> list[Transacao]:
    """Captura lançamentos da seção `MOVIMENTAÇÕES DA CONTA` (acima da
    tabela principal): anuidade, desconto de anuidade e quaisquer
    lançamentos administrativos que sejam, na prática, gastos do titular.

    A seção tem um layout próprio em três linhas para a anuidade
    parcelada::

        ANUIDADE MASTERCARD
        05 MAR R$ 11.67
        (8449) 11/12

    e em uma única linha para outros lançamentos::

        12 JAN PAGTO DEB EM CONTA - C -R$ 3,523.12

    Pagamentos efetuados, saldos e totais são descartados aqui (são
    metadados da fatura, não consumo do cartão).

    Recebe a coluna já cropada (lado esquerdo da página), evitando o
    intercalamento que `extract_text()` causa entre as duas colunas.
    """
    palavras = coluna.extract_words(use_text_flow=False, keep_blank_chars=False)
    if not palavras:
        return []

    faixa = _localizar_secao_movimentacoes(palavras)
    if faixa is None:
        return []
    top_inicio, top_fim = faixa

    palavras_secao = [
        p for p in palavras if top_inicio < p["top"] < top_fim
    ]
    if not palavras_secao:
        return []

    linhas_palavras = _agrupar_palavras_em_linhas(palavras_secao)
    linhas_texto: list[str] = []
    for linha in linhas_palavras:
        textos = [p["text"] for p in linha]
        linhas_texto.append(" ".join(textos).strip())

    transacoes: list[Transacao] = []
    for i, linha in enumerate(linhas_texto):
        m = _casar_linha_movimentacao(linha)
        if not m:
            continue
        dia, mes_str, resto, valor_str = m

        valor = parse_valor_brl(valor_str)
        if valor is None:
            continue

        descricao = resto.strip()
        if not descricao and i > 0:
            anterior = linhas_texto[i - 1].strip()
            if not _casar_linha_movimentacao(anterior):
                descricao = anterior

        if not descricao:
            continue
        if any(termo in descricao.upper() for termo in MOV_DESCARTAR):
            continue

        parcela = ""
        m_inline = RE_MOV_PARCELA_INLINE.search(descricao)
        if m_inline:
            parcela = m_inline.group(1)
            descricao = (
                descricao[: m_inline.start()] + descricao[m_inline.end():]
            ).strip()
        elif i + 1 < len(linhas_texto):
            m_next = RE_MOV_PARCELA_LINHA.match(linhas_texto[i + 1])
            if m_next:
                parcela = m_next.group("parcela")

        mes_num = MESES_PT.get(mes_str.upper())
        if mes_num is None:
            continue

        ano = inferir_ano_transacao(
            mes_num,
            data_vencimento,
            parcela,
            recuar_pelo_numero_da_parcela=True,
        )
        data = formatar_data(dia, mes_num, ano)

        transacoes.append(
            Transacao(
                data=data,
                descricao=descricao,
                parcela=parcela,
                cidade="",
                valor=valor,
                categoria=categorizar(descricao),
            )
        )

    return transacoes


_RE_MOV_LINHA = re.compile(
    r"^(?P<dia>\d{2})\s+(?P<mes>[A-Za-z]{3})\b\s*(?P<resto>.*?)\s*"
    r"(?P<valor>-?R\$\s*[\d.,]+)\s*$"
)


def _casar_linha_movimentacao(linha: str) -> tuple[str, str, str, str] | None:
    """Reconhece uma linha com `DD MMM [descrição] [valor]`.

    Retorna `(dia, mes, resto, valor)` ou `None` se não casar. Valida
    também se `mes` é uma abreviação reconhecida em PT-BR para evitar
    falsos positivos quando outra linha começa com dois dígitos seguidos
    de qualquer palavra de três letras.
    """
    m = _RE_MOV_LINHA.match(linha)
    if not m:
        return None
    if m.group("mes").upper() not in MESES_PT:
        return None
    return m.group("dia"), m.group("mes"), m.group("resto") or "", m.group("valor")
