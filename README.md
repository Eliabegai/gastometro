# Leitor de Fatura PDF → Excel

Lê faturas em PDF, identifica automaticamente o banco emissor, extrai os
lançamentos, categoriza cada gasto e gera uma planilha Excel com cabeçalho
da fatura, transações e resumo por categoria.

## Bancos suportados

| Banco           | Status         |
| --------------- | -------------- |
| Ailos Mastercard | Totalmente suportado |
| Nubank          | Totalmente suportado |
| Banco do Brasil (Ourocard) | Estrutura inicial — adapta automaticamente para o layout padrão; envie um PDF se algo escapar |

## Por que Python?

- **`pdfplumber`** lê PDFs preservando posições (x, y), essencial para
  faturas com duas colunas (Ailos).
- **`pandas` + `openpyxl`** geram Excel formatado em poucas linhas.
- Roda em qualquer SO (Windows, macOS, Linux) sem compilação.
- Fácil de evoluir: novos bancos viram um arquivo em `parsers/`.

## Pré-requisitos

- Python 3.10+. Verifique com `python3 --version`.

## Instalação (1 vez só)

```bash
python3 -m venv .venv
source .venv/bin/activate     # macOS / Linux
# .venv\Scripts\activate      # Windows PowerShell
pip install -r requirements.txt
```

## Uso

Com o ambiente virtual ativo:

```bash
# Processa um PDF específico
python extrator.py Fatura_05_2026.pdf

# Processa todos os PDFs da pasta atual
python extrator.py

# Processa todos os PDFs de outra pasta
python extrator.py ~/Downloads/faturas/
```

Para cada `Fatura.pdf` será criado um `Fatura.xlsx` no mesmo diretório
com três abas:

- **Informações**: banco, titular, referência (mês/ano), data de
  fechamento, data de vencimento, valor total e quantidade de
  transações.
- **Transações**: banco, titular, referência, data, descrição, parcela,
  cidade, valor e categoria de cada lançamento.
- **Resumo por Categoria**: total gasto por categoria + total geral.

## Categorias

As regras ficam em `categorias.py`. Cada categoria é uma lista de
palavras-chave (case-insensitive). Para criar uma nova categoria ou
refinar a classificação, edite esse arquivo:

```python
CATEGORIAS = {
    "Mercado": ["supermerc", "mercado", "rancho bom", ...],
    "Combustível": ["posto", "shell", "ipiranga", ...],
    "Farmácia": ["raia", "drogasil", "panvel", ...],
    ...
}
```

Transações que não casarem com nenhuma palavra-chave caem em **"Outros Gastos"**.

## Estrutura do projeto

```
leitor-pdf/
├── extrator.py            # CLI + exportador Excel
├── categorias.py          # regras de categorização
├── parsers/
│   ├── __init__.py        # detecção automática do banco
│   ├── base.py            # tipos compartilhados + utilidades
│   ├── ailos.py           # parser Ailos Mastercard
│   ├── nubank.py          # parser Nubank
│   └── banco_brasil.py    # parser Banco do Brasil (Ourocard)
├── requirements.txt
└── README.md
```

## Como adicionar suporte a outro banco

1. Crie `parsers/seu_banco.py` com duas funções:
   - `detectar(texto: str) -> bool` — retorna `True` se o PDF for desse banco.
   - `extrair(caminho_pdf: Path) -> Fatura` — devolve um `Fatura` (de `parsers/base.py`) com `metadata` e `transacoes`.
2. Registre o módulo em `PARSERS_DISPONIVEIS` dentro de `parsers/__init__.py`.

## Próximos passos sugeridos

- Interface gráfica com `streamlit` para arrastar e soltar PDFs.
- Consolidação de várias faturas em uma única planilha mensal.
- Gráficos (barras / pizza) automáticos no Excel.
