"""
Regras de categorização das transações.

Cada categoria possui uma lista de palavras-chave (case-insensitive) que,
quando encontradas na descrição da transação, classificam-na naquela categoria.

Para adicionar/ajustar categorias, basta editar o dicionário CATEGORIAS abaixo.
A ordem importa: a primeira categoria que casar é usada.
"""

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


def categorizar(descricao: str) -> str:
    """Retorna a categoria que melhor corresponde à descrição informada."""
    if not descricao:
        return "Outros Gastos"

    texto = descricao.lower()
    for categoria, palavras in CATEGORIAS.items():
        for palavra in palavras:
            if palavra.lower() in texto:
                return categoria
    return "Outros Gastos"
