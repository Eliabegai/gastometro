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
- macOS, Linux ou Windows.

## Instalação (somente na primeira vez)

```bash
git clone https://github.com/<seu-usuario>/gastometro.git
cd gastometro

python3 -m venv .venv
source .venv/bin/activate     # macOS / Linux
# .venv\Scripts\activate      # Windows PowerShell

pip install -r requirements.txt
```

## Como executar a extração de um PDF

Toda vez que for usar, **ative o ambiente virtual** antes:

```bash
cd /caminho/para/gastometro
source .venv/bin/activate      # macOS / Linux
# .venv\Scripts\activate       # Windows PowerShell
```

Depois rode o `extrator.py` em uma das três formas:

```bash
# 1) Um PDF específico (caminho relativo ou absoluto)
python extrator.py Fatura_05_2026.pdf
python extrator.py ~/Downloads/Nubank_2026-05-13.pdf

# 2) Todos os PDFs da pasta atual
python extrator.py

# 3) Todos os PDFs de outra pasta
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

### Saída esperada no terminal

```
Processando: Fatura_05_2026.pdf
  Banco: Ailos | Titular: Fulano De Tal | Referência: Maio/2026
  Fechamento: 05/05/2026 | Vencimento: 15/05/2026
  48 transações encontradas.
  Excel gerado: Fatura_05_2026.xlsx

Concluído.
```

### Solução de problemas

- **`command not found: python`** — use `python3` no macOS/Linux.
- **`No module named pdfplumber`** — esqueceu de ativar o `.venv` (ou
  rodar `pip install -r requirements.txt`).
- **`Não foi possível identificar o banco da fatura ...`** — o PDF é
  de um banco ainda não suportado. Abra uma issue (ou veja a seção
  "Como adicionar suporte a outro banco" abaixo).
- **0 transações encontradas** — o layout pode ter mudado. Inspecione
  o texto bruto extraído pelo `pdfplumber` para ajustar o parser:

  ```python
  import pdfplumber
  with pdfplumber.open("arquivo.pdf") as pdf:
      for i, p in enumerate(pdf.pages):
          print(f"=== PÁGINA {i+1} ===")
          print(p.extract_text())
  ```

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
gastometro/
├── extrator.py            # CLI + exportador Excel
├── categorias.py          # regras de categorização
├── parsers/
│   ├── __init__.py        # detecção automática do banco
│   ├── base.py            # tipos compartilhados + utilidades
│   ├── ailos.py           # parser Ailos Mastercard
│   ├── nubank.py          # parser Nubank
│   └── banco_brasil.py    # parser Banco do Brasil (Ourocard)
├── requirements.txt
├── README.md              # este arquivo
└── MELHORIAS.md           # backlog vivo de melhorias (priorizado)
```

## Como adicionar suporte a outro banco

1. Crie `parsers/seu_banco.py` com duas funções:
   - `detectar(texto: str) -> bool` — retorna `True` se o PDF for desse banco.
   - `extrair(caminho_pdf: Path) -> Fatura` — devolve um `Fatura` (de `parsers/base.py`) com `metadata` e `transacoes`.
2. Registre o módulo em `PARSERS_DISPONIVEIS` dentro de `parsers/__init__.py`.

## Próximos passos sugeridos

Veja `MELHORIAS.md` para o backlog completo (com prioridade, esforço
e status). Destaques:

- Interface gráfica com `streamlit` para arrastar e soltar PDFs.
- Consolidação de várias faturas em uma única planilha mensal.
- Gráficos (barras / pizza) automáticos no Excel.
- Testes automatizados com `pytest`.
- Suporte a Itaú, Bradesco, Inter e C6.
