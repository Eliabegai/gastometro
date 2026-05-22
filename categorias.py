"""
Regras de categorização das transações.

Cada categoria possui uma lista de palavras-chave (case-insensitive) que,
quando encontradas na descrição da transação, classificam-na naquela categoria.

Para adicionar/ajustar categorias, basta editar o dicionário CATEGORIAS abaixo.
A ordem importa: a primeira categoria que casar é usada.

O usuário pode também criar um arquivo `categorias_usuario.json` na raiz do
projeto (fora do versionamento) com overrides manuais no formato
`{"descrição": "Categoria"}`. Esses overrides têm precedência sobre o
dicionário fixo; a comparação é feita após normalização (lowercase + sem
acentos + espaços colapsados).
"""

from __future__ import annotations

import json
import unicodedata
from functools import lru_cache
from pathlib import Path


CATEGORIAS_USUARIO_ARQUIVO = Path(__file__).parent / "categorias_usuario.json"


CATEGORIAS = {
    "Combustível": [
        "posto",
        "shell",
        "ipiranga",
        "petrobras",
        "br mania",
        "ale combustiveis",
        "auto posto",
        "petropen",
    ],
    "Mercado": [
        "supermerc",
        "mercado",
        "rancho bom",
        "kompra",
        "cooper filial",
        "hortifruti",
        "atacad",
        "big",
        "carrefour",
        "assai",
        "fort atacad",
        "angeloni",
        "giassi",
    ],
    "Alimentação": [
        "restaurante",
        "pizzaria",
        "pizzar",
        "lanchonete",
        "padaria",
        "cafe",
        "café",
        "burger",
        "mcdonald",
        "mc donald",
        "subway",
        "ifood",
        "rappi",
        "uber eats",
        "confeitaria",
        "docesabor",
        "doce sabor",
        "rodosnack",
        "tulipa",
        "casarao da faco",
        "dlara",
        "zoet",
        "lounge",
    ],
    "Farmácia": [
        "farmacia",
        "farmácia",
        "drogaria",
        "drogasil",
        "pague menos",
        "raia",
        "panvel",
        "ultrafarma",
    ],
    "Saúde": [
        "hospital",
        "clinica",
        "clínica",
        "laboratorio",
        "laboratório",
        "consulta",
        "dentista",
        "odonto",
        "psicolog",
        "fisio",
        "mapfre seguros",
        "unimed",
        "amil",
        "bradesco saude",
    ],
    "Lazer": [
        "cinema",
    ],
    "Assinatura Digital": [
        "netflix",
        "spotify",
        "prime video",
        "hbo",
        "disney",
        "apple combill",
        "apple.com/bill",
        "google play",
        "microsoft",
        "sky",
    ],
    "Compra Digital": [
        "steam",
        "playstation",
        "xbox",
        "applecombill",
        "apple.com/bill",
        "google play",
        "shopee",
        "amazon",
        "amazonmkt",
        "magazineluiza",
        "magalu",
        "mercadolivre",
        "kodadeck",
        "mercado livre",
        "mercado pago",
        "mercado pago",
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
    ],
    "Transporte": [
        "uber",
        "99 ",
        "99app",
        "cabify",
        "taxi",
        "estapar",
        "estacionamento",
        "mecanica",
        "mecânica",
        "oficina",
    ],
    "Casa e Construção": [
        "casa dos tubos",
        "tecnopan",
        "leroy",
        "telhanorte",
        "lojao da marechal",
        "construcao",
        "construção",
        "ferragens",
        "monte carlo",
    ],
    "Educação": [
        "escola",
        "faculdade",
        "universidade",
        "udemy",
        "alura",
        "curso",
        "livraria",
    ],
    "Serviços / Assinaturas": [
        "anuidade",
        "tarifa",
        "mensalidade",
        "seguro",
    ],
}


def _normalizar(texto: str) -> str:
    """Normaliza a descrição para comparação tolerante a maiúsculas, acentos
    e espaços extras. Usado para casar overrides do usuário."""
    if not texto:
        return ""
    nfd = unicodedata.normalize("NFD", texto)
    sem_acentos = "".join(c for c in nfd if unicodedata.category(c) != "Mn")
    return " ".join(sem_acentos.lower().split())


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
    (por exemplo, ao detectar overrides manuais ao aprender de um Excel)."""
    if not descricao:
        return "Outros Gastos"
    texto = descricao.lower()
    for categoria, palavras in CATEGORIAS.items():
        for palavra in palavras:
            if palavra.lower() in texto:
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
