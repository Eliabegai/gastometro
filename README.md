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

O fluxo padrão usa duas pastas dedicadas:

- `entrada/` — coloque aqui os PDFs das faturas a processar.
- `saida/` — recebe o Excel único acumulativo (`saida/gastometro.xlsx`).

Ambas são criadas automaticamente na primeira execução.

Toda vez que for usar, **ative o ambiente virtual** antes:

```bash
cd /caminho/para/gastometro
source .venv/bin/activate      # macOS / Linux
# .venv\Scripts\activate       # Windows PowerShell
```

### Fluxo padrão (recomendado)

```bash
# 1) Coloque os PDFs em entrada/
mv ~/Downloads/Fatura_05_2026.pdf entrada/
mv ~/Downloads/Nubank_2026-05-13.pdf entrada/

# 2) Rode o extrator
python extrator.py
```

O resultado fica em `saida/gastometro.xlsx`. Cada execução **acumula**
faturas novas no mesmo arquivo. Faturas com nome de PDF já presente no
Excel são ignoradas (mostra "Ignorado (já no Excel)" no terminal).

### Alternativas (sobrescrevem a pasta padrão)

```bash
# Processar um único PDF fora de entrada/
python extrator.py ~/Downloads/Fatura_05_2026.pdf

# Processar todos os PDFs de outra pasta
python extrator.py ~/Downloads/faturas/
```

Em qualquer modo, a saída sempre vai para `saida/gastometro.xlsx`.

### Re-processar uma fatura

Se você atualizou as regras de categorização e quer reaplicá-las a uma
fatura já no Excel:

1. Abra `saida/gastometro.xlsx`.
2. Apague a linha dessa fatura na aba **Informações** e todas as
   transações dela na aba **Transações** (filtrar por `Arquivo`).
3. Salve e rode `python extrator.py` novamente.

Para começar do zero: apague `saida/gastometro.xlsx` e rode de novo.

### Estrutura do Excel gerado

- **Informações**: uma linha por fatura processada (arquivo, banco,
  titular, referência, fechamento, vencimento, valor total, qtde. de
  transações).
- **Transações**: todas as transações de todas as faturas, ordenadas
  por data, com a coluna `Arquivo` indicando a origem.
- **Resumo por Categoria**: soma agregada por categoria + total geral.
- **Resumo Mensal**: pivot com referência (mês/ano) nas linhas e
  categorias nas colunas, mais total por mês e linha `TOTAL` no fim.

### Saída esperada no terminal

```
Processando: Fatura_05_2026.pdf
  Banco: Ailos | Titular: Fulano De Tal | Referência: Maio/2026
  Fechamento: 04/05/2026 | Vencimento: 11/05/2026
  48 transações encontradas.

Processando: Nubank_2026-05-13.pdf
  Banco: Nubank | Titular: Fulano De Tal | Referência: Maio/2026
  Fechamento: 06/05/2026 | Vencimento: 13/05/2026
  10 transações encontradas.

Excel acumulativo atualizado: /caminho/gastometro/saida/gastometro.xlsx
  Total no arquivo: 2 faturas, 58 transações.
  Faturas adicionadas nesta execução: 2.

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
├── entrada/               # coloque os PDFs aqui (gitignored)
├── saida/                 # gastometro.xlsx é gerado aqui (gitignored)
├── extrator.py            # CLI + exportador Excel acumulativo
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
