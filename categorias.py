"""
Regras de categorização das transações.

Cada categoria possui uma lista de palavras-chave que são procuradas na
descrição da transação. A comparação é tolerante a maiúsculas, acentos e
espaços extras; a palavra-chave precisa aparecer como **token completo**
(entre não-alfanuméricos), evitando falsos positivos por substring (o
keyword `raia` não casa `RAIANE OFICINA`, `big` não casa `BIGODE
LANCHES`).

Convenções no dicionário:
  - `"raia"`             → casamento estrito: precisa estar entre não
                          alfanuméricos (não casa `RAIANE`, mas casa
                          `RAIA 419` e `RAIA-DROG`). Use para palavras
                          que possam virar substring acidental em
                          outras palavras (raia, big, mercado, ...).
  - `"posto*"`           → prefix match: a keyword pode ser o começo
                          de uma palavra maior (`posto*` casa `posto`,
                          `postos`, `POSTOZ19`, `POSTO BR`). Use para
                          marcas/sufixos comuns em fatura
                          (`shell*`, `komprao*`, `youtube*`,
                          `spotify*`, `descomplica*`, ...).
  - `"!mercado pago"`    → palavra a EXCLUIR. Se aparecer na descrição,
                          a categoria atual é descartada (mesmo que
                          outra keyword positiva casaria).

A regra "estrita vs prefix" se aplica apenas ao **final** da keyword;
o início **sempre** exige boundary (não-alfanumérico antes ou começo
de string), garantindo que `mercado` em `EOMERCADO` não case.

O usuário pode também criar um arquivo `categorias_usuario.json` na raiz
do projeto (fora do versionamento) com overrides manuais no formato
`{"descrição": "Categoria"}`. Esses overrides têm precedência sobre o
dicionário fixo; a comparação é feita após a mesma normalização.
"""

from __future__ import annotations

import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path


CATEGORIAS_USUARIO_ARQUIVO = Path(__file__).parent / "categorias_usuario.json"


CATEGORIAS = {
    "Combustível": [
        "posto*",
        "autoposto*",
        "shell*",
        "ipiranga",
        "petrobras",
        "br mania",
        "ale combustiveis",
        "auto posto",
        "petropen",
    ],
    "Mercado": [
        "supermerc*",
        "mercado",
        "!mercado pago",
        "!mercado livre",
        "!mercadolivre",
        "!mercado libre",
        "rancho bom",
        "ranchobom*",
        "kompra*",
        "kompro*",
        "cooper*",
        "hortifruti",
        "atacad*",
        "big",
        "!bigode*",
        "carrefour",
        "assai",
        "fort atacad",
        "angeloni",
        "giassi",
        "condor*",
        "eskimo*",
    ],
    "Alimentação": [
        "restaurante*",
        "pizza*",
        "lanch*",
        "padaria*",
        "panif*",
        "cafe*",
        "café*",
        "burger*",
        "mcdonald*",
        "mc donald",
        "subway",
        "ifood",
        "ifd*",
        "rappi",
        "uber eats",
        "confeitaria",
        "marmitaria*",
        "docesabor*",
        "doce sabor",
        "sorvete*",
        "acai*",
        "açai*",
        "açaí*",
        "assados*",
        "alexandria",
        "divino fogao",
        "divino fogão",
        "rodosnack",
        "tulipa",
        "casarao da faco",
        "dlara",
        "zoet",
        "lounge",
        "tecnopan*",
    ],
    "Farmácia": [
        "farmacia*",
        "farmácia*",
        "drogaria*",
        "drogasil",
        "pague menos",
        "raia",
        "panvel*",
        "ultrafarma*",
    ],
    "Saúde": [
        "hospital*",
        "clinica*",
        "clínica*",
        "laboratorio*",
        "laboratório*",
        "consulta",
        "dentista",
        "odonto*",
        "psicolog*",
        "fisio*",
        "unimed*",
        "amil",
        "bradesco saude",
        "cartao de todos",
        "cartão de todos",
    ],
    "Lazer": [
        "cinema*",
        "boliche*",
    ],
    "Assinatura Digital": [
        "netflix",
        "spotify*",
        "youtube*",
        "prime video",
        "hbo*",
        "disney*",
        "discovery*",
        "apple combill",
        "apple.com/bill",
        "google play",
        "microsoft*",
        "sky",
    ],
    "Compra Digital": [
        "steam*",
        "playstation*",
        "xbox*",
        "applecombill*",
        "apple.com/bill",
        "google play",
        "shopee*",
        "amazon*",
        "magazineluiz*",
        "magalu",
        "mercadolivre*",
        "mercado livre",
        "mercadopago*",
        "mercado pago",
        "kodadeck",
        "kabum*",
        "shein*",
    ],
    "Vestuário": [
        "c e a",
        "renner",
        "riachuelo",
        "lojas americanas",
        "havan",
        "studio z",
        "centauro",
        "marisa",
        "zara",
        "lunelli*",
        "netshoes*",
        "lingerie*",
        "calcados*",
        "calçados*",
        "lojas gang",
        "modas",
    ],
    "Manutenção Carro": [
        "autoeletrica*",
        "auto eletrica*",
        "autoelétrica*",
        "auto elétrica*",
        "mecanica*",
        "mecânica*",
        "oficina*",
    ],
    "Transporte": [
        "uber*",
        "99 ",
        "99app",
        "cabify",
        "taxi",
        "estapar*",
        "estacionamento*",
        "epar estacionament*",
        "parking*",
        "sem parar*",
        "sem*parar*",
        "localiza*",
    ],
    "Casa e Construção": [
        "casa dos tubos",
        "casa das tintas",
        "leroy*",
        "telhanorte",
        "lojao da marechal",
        "construcao",
        "construção",
        "ferragens",
        "monte carlo",
        "balaroti*",
    ],
    "Educação": [
        "escola*",
        "faculdade*",
        "universidade*",
        "udemy",
        "alura",
        "curso*",
        "livraria*",
        "descomplica*",
    ],
    "Seguro": [
        "seguro*",
        "mapfre*",
    ],
    "Serviços / Assinaturas": [
        "anuidade*",
        "tarifa*",
        "mensalidade*",
    ],
}


def _normalizar(texto: str) -> str:
    """Normaliza a descrição para comparação tolerante a maiúsculas, acentos
    e espaços extras. Usado tanto para casar overrides do usuário quanto
    palavras-chave do dicionário."""
    if not texto:
        return ""
    nfd = unicodedata.normalize("NFD", texto)
    sem_acentos = "".join(c for c in nfd if unicodedata.category(c) != "Mn")
    return " ".join(sem_acentos.lower().split())


def _padrao_token_completo(palavra_normalizada: str) -> re.Pattern[str]:
    """Compila um padrão para casar uma keyword na descrição normalizada.

    Regras:
      - O início **sempre** exige boundary (não-alfanumérico ou começo
        de string) — evita falsos positivos por meio de palavra
        (`EOMERCADO` não casa `mercado`).
      - O final é estrito por padrão (não permite letra depois), mas
        admite dígitos (`RAIA` casa `RAIA419`; `RAIANE` não).
      - Quando a keyword termina em `*`, vira prefix match e a
        continuação por letra/dígito é permitida (`shell*` casa
        `SHELLBO`, `posto*` casa `POSTOZ19`).
    """
    prefix_match = palavra_normalizada.endswith("*")
    if prefix_match:
        palavra_normalizada = palavra_normalizada[:-1].rstrip()
    if not palavra_normalizada:
        return re.compile(r"(?!)")
    sufixo = "" if prefix_match else r"(?![a-z])"
    return re.compile(
        r"(?<![a-z0-9])" + re.escape(palavra_normalizada) + sufixo
    )


@lru_cache(maxsize=1)
def _regras_compiladas() -> tuple[tuple[str, tuple[re.Pattern[str], ...], tuple[re.Pattern[str], ...]], ...]:
    """Pré-compila as listas de palavras-chave em padrões regex, separando
    inclusões das exclusões (prefixadas por `!`)."""
    regras: list[tuple[str, tuple[re.Pattern[str], ...], tuple[re.Pattern[str], ...]]] = []
    for categoria, palavras in CATEGORIAS.items():
        incluir: list[re.Pattern[str]] = []
        excluir: list[re.Pattern[str]] = []
        for raw in palavras:
            kw = raw.strip()
            if not kw:
                continue
            negativa = kw.startswith("!")
            if negativa:
                kw = kw[1:].strip()
            if not kw:
                continue
            padrao = _padrao_token_completo(_normalizar(kw))
            (excluir if negativa else incluir).append(padrao)
        regras.append((categoria, tuple(incluir), tuple(excluir)))
    return tuple(regras)


@lru_cache(maxsize=1)
def _carregar_categorias_usuario() -> dict[str, str]:
    """Lê `categorias_usuario.json` (se existir) e devolve um mapa com as
    chaves já normalizadas. Em caso de erro de leitura, devolve mapa vazio
    e segue silenciosamente (override é opcional)."""
    if not CATEGORIAS_USUARIO_ARQUIVO.exists():
        return {}
    try:
        with CATEGORIAS_USUARIO_ARQUIVO.open(encoding="utf-8") as f:
            dados = json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}
    return {_normalizar(k): v for k, v in dados.items() if isinstance(v, str) and v}


def categorizar_pelo_dicionario(descricao: str) -> str:
    """Aplica apenas o dicionário fixo `CATEGORIAS`, ignorando os overrides
    do usuário. Útil para descobrir o que o dicionário sozinho devolveria
    (por exemplo, ao detectar overrides manuais ao aprender de um Excel).

    A primeira categoria com pelo menos uma palavra-chave de inclusão
    casando E nenhuma palavra-chave de exclusão casando vence. A
    comparação é feita após normalização (sem acentos, lower, espaços
    colapsados) e exige que a palavra-chave apareça como token completo
    (cercada por não-alfanuméricos)."""
    if not descricao:
        return "Outros Gastos"
    norm = _normalizar(descricao)
    for categoria, incluir, excluir in _regras_compiladas():
        if not any(p.search(norm) for p in incluir):
            continue
        if any(p.search(norm) for p in excluir):
            continue
        return categoria
    return "Outros Gastos"


def categorizar(descricao: str) -> str:
    """Retorna a categoria que melhor corresponde à descrição informada.

    Ordem de precedência:
      1. `categorias_usuario.json` (override manual por descrição
         normalizada).
      2. Dicionário fixo `CATEGORIAS` (primeira palavra-chave que casa).
      3. `"Outros Gastos"` como fallback.
    """
    if not descricao:
        return "Outros Gastos"

    usuario = _carregar_categorias_usuario()
    if usuario:
        norm = _normalizar(descricao)
        if norm in usuario:
            return usuario[norm]

    return categorizar_pelo_dicionario(descricao)


def salvar_categorias_usuario(mapa: dict[str, str]) -> int:
    """Persiste `mapa` (descrição → categoria) em `categorias_usuario.json`,
    substituindo o conteúdo atual. As chaves são normalizadas antes de
    serem gravadas. Devolve a quantidade de entradas efetivamente salvas."""
    normalizado: dict[str, str] = {}
    for chave, valor in mapa.items():
        norm = _normalizar(str(chave))
        if not norm or not isinstance(valor, str) or not valor.strip():
            continue
        normalizado[norm] = valor.strip()

    CATEGORIAS_USUARIO_ARQUIVO.write_text(
        json.dumps(normalizado, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _carregar_categorias_usuario.cache_clear()
    return len(normalizado)
