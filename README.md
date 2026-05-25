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

Se você atualizou as regras de categorização e quer reaplicá-las **só
nas categorias** sem reler PDFs (mantém filtros/tabelas do Excel):

```bash
python extrator.py recategorizar
```

Detalhes na seção "[Recategorizar o Excel inteiro](#recategorizar-o-excel-inteiro-recategorizar)" mais abaixo.

Para forçar a leitura do PDF de novo (ex.: alguma transação foi
extraída errada e o parser mudou):

1. Abra `saida/gastometro.xlsx`.
2. Apague a linha dessa fatura na aba **Informações** e todas as
   transações dela na aba **Transações** (filtrar por `Arquivo`).
3. Salve e rode `python extrator.py` novamente.

Para começar do zero: apague `saida/gastometro.xlsx` e rode de novo.

### Estrutura do Excel gerado

Cada execução regrava o arquivo `saida/gastometro.xlsx` com as
abas abaixo. Abas marcadas com **(filtro)** têm filtro nativo do
Excel ativado no cabeçalho — basta clicar na setinha de qualquer
coluna para fatiar os dados.

- **Informações** (filtro): uma linha por fatura processada (arquivo,
  banco, titular, **cartão**, referência, fechamento, vencimento, valor
  total, qtde. de transações).
- **Transações** (filtro): todas as transações de todas as faturas,
  ordenadas por data, com colunas `Arquivo`, `Banco`, `Titular`,
  `Cartão`, `Referência`, `Data`, `Descrição`, `Parcela`, `Cidade`,
  `Valor (R$)` e `Categoria`. Filtre por cartão para analisar um
  cartão específico, por categoria para ver só Mercado, etc.
- **Resumo por Categoria**: soma agregada por categoria + total geral.
- **Resumo Mensal**: pivot referência (mês/ano) × categoria, com total
  por mês e linha `TOTAL` no fim.
- **Resumo por Cartão**: uma linha por cartão (`Banco — Titular`) com
  qtde. de faturas, qtde. de transações, primeira/última referência,
  total gasto, média por fatura e ticket médio.
- **Cartão x Mês**: pivot referência × cartão. Responde "quanto cada
  cartão gastou em cada mês", com totais por linha e coluna.
- **Cartão x Categoria**: pivot categoria × cartão. Mostra como cada
  cartão se distribui por categoria (útil para decidir qual usar
  para quê).
- **Top Comerciantes** (filtro): top 30 descrições por valor
  acumulado, com categoria, cartão(ões) onde apareceu, qtde. de
  transações, total e ticket médio. Foco em onde o dinheiro
  realmente vai.
- **Recorrentes** (filtro): descrições que aparecem em pelo menos 3
  meses distintos, com qtde. de meses, total e média mensal real.
  Ajuda a mapear gastos fixos (assinaturas, mensalidades, seguros).

> **Cartão** é definido como `Banco — Titular`. Distingue cartões com
> o mesmo banco mas titulares diferentes e cartões do mesmo titular em
> bancos diferentes. Excels antigos sem essa coluna são migrados
> automaticamente na próxima execução, sem precisar reprocessar PDFs.

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
palavras-chave. A comparação ignora maiúsculas, acentos e espaços
extras, e exige boundary semântico (a keyword precisa estar entre
não-alfanuméricos) — `raia` não casa `RAIANE OFICINA`.

```python
CATEGORIAS = {
    "Mercado": [
        "supermerc*",        # prefix match: casa "supermercado", "supermerc 5"
        "mercado",           # estrito: NAO casa "mercadolivre", "mercado pago"
        "!mercado pago",     # regra negativa: cancela a categoria
        "!mercadolivre",
        "rancho bom",
        "kompra*", "kompro*",
        "big",               # casa "BIG SUPERMERC" mas NAO "BIGODE"
        "!bigode*",          # garante que BIGODE nao caia em Mercado
        ...
    ],
    "Combustível": ["posto*", "autoposto*", "shell*", "ipiranga", ...],
    "Farmácia":    ["raia", "drogaria*", "panvel*", ...],
    ...
}
```

Convenções:

- **Sem sufixo** (`mercado`, `raia`, `big`) — casamento estrito: a
  keyword precisa estar isolada por não-alfanuméricos. Letras antes
  ou depois invalidam o match; dígitos depois são aceitos (logo
  `RAIA` casa `RAIA419` mas não `RAIANE`).
- **Sufixo `*`** (`posto*`, `shell*`, `kompra*`) — prefix match: a
  keyword pode ser o **começo** de uma palavra maior, útil para
  descrições concatenadas comuns em fatura
  (`POSTOZ19`, `SHELLBO`, `KOMPRAO ATACADISTA`).
- **Prefixo `!`** (`!mercado pago`, `!bigode*`) — regra negativa:
  se a keyword excluída casar, a categoria atual é descartada
  mesmo que outras keywords positivas tenham casado.

A primeira categoria com pelo menos uma keyword positiva e nenhuma
negativa casando vence. Transações que não casarem com nenhuma
caem em **"Outros Gastos"**.

### Top 'Outros Gastos' no terminal

Ao final de cada execução, o extrator imprime as **10 descrições com maior
valor acumulado que caíram em "Outros Gastos"**. Use essa lista para
priorizar quais palavras-chave adicionar a `categorias.py`:

```
Top 10 descrições em 'Outros Gastos' (acumulado no Excel):
  R$    287.24  ( 6x)  MAPFRE SEGUROS
  R$    143.54  ( 1x)  MECANICA MAICON
  ...
```

### Overrides por descrição (`categorias_usuario.json`)

Para corrigir casos isolados sem inflar `categorias.py`, edite a coluna
**Categoria** no Excel gerado, salve, e rode:

```bash
python extrator.py aprender
```

O extrator compara cada linha com o resultado do dicionário fixo e grava
apenas as **diferenças** em `categorias_usuario.json` (na raiz, fora do
git). Essas entradas têm precedência sobre o dicionário em todas as
execuções futuras. A comparação ignora maiúsculas, acentos e espaços
extras.

> Cuidado: o JSON contém descrições brutas (que podem ter dados
> sensíveis) e por isso está em `.gitignore`.

### Recategorizar o Excel inteiro (`recategorizar`)

A coluna `Categoria` é **gravada como texto literal** no Excel no
momento em que cada fatura é processada — não é uma fórmula. Por isso,
quando você edita `categorias.py` ou `categorias_usuario.json` e roda
`python extrator.py`, as **linhas antigas continuam com as categorias
de quando foram inseridas** (apenas faturas novas usam as regras
atualizadas).

Para propagar as regras atuais para todo o Excel sem precisar apagar o
arquivo e reprocessar PDFs:

```bash
python extrator.py recategorizar                       # usa saida/gastometro.xlsx
python extrator.py recategorizar caminho/arquivo.xlsx  # arquivo específico
```

O comando:

- Lê `saida/gastometro.xlsx` (ou o caminho informado).
- Re-aplica `categorizar()` em toda a aba `Transações` (respeita
  `categorias_usuario.json`).
- Reconstrói **todas** as abas analíticas (Resumo por Categoria,
  Resumo Mensal, Cartão × Mês, Cartão × Categoria, Top Comerciantes,
  Recorrentes).
- Preserva linhas, ordem, formatação e cabeçalhos — seus filtros e
  segmentações de tabela continuam apontando para os mesmos nomes de
  coluna.
- Imprime um resumo: quantas categorias mudaram e o agrupado
  `antiga → nova : quantidade`.

> **Atenção**: edições manuais que você fez na coluna `Categoria` do
> Excel e que **ainda não foram capturadas** via `python extrator.py
> aprender` serão sobrescritas. Fluxo seguro:
>
> ```bash
> python extrator.py aprender        # salva edicoes do Excel no JSON
> python extrator.py recategorizar   # propaga JSON + dicionario p/ tudo
> ```

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
├── tests/                 # suite pytest (parse_valor_brl, categorias, inferencia)
├── requirements.txt
├── requirements-dev.txt   # requirements.txt + pytest
├── README.md              # este arquivo
└── MELHORIAS.md           # backlog vivo de melhorias (priorizado)
```

## Testes

A suite usa `pytest` e roda em segundos. Instale as dependências de
desenvolvimento e rode na raiz:

```bash
pip install -r requirements-dev.txt
python -m pytest -q
```

Os testes cobrem:

- `parse_valor_brl` — formatos BR e americano, negativos, trailing
  punctuation e entradas inválidas.
- `categorizar` — ≥2 positivos por categoria, boundaries semânticos
  (`raia` vs `RAIANE`), prefix match (`*`), regras negativas (`!`),
  overrides do usuário e `salvar_categorias_usuario`.
- `inferir_ano_transacao` e `referencia_pelo_vencimento` — viradas
  de ano (compras de dezembro em fatura de janeiro) e recuo por
  número de parcela para parcelamentos longos da Ailos.

Cada teste roda com um `categorias_usuario.json` temporário, isolado
do arquivo real do usuário.

## Como adicionar suporte a outro banco

1. Crie `parsers/seu_banco.py` com duas funções:
   - `detectar(texto: str) -> bool` — retorna `True` se o PDF for desse banco.
   - `extrair(caminho_pdf: Path) -> Fatura` — devolve um `Fatura` (de `parsers/base.py`) com `metadata` e `transacoes`.
2. Registre o módulo em `PARSERS_DISPONIVEIS` dentro de `parsers/__init__.py`.

## Próximos passos sugeridos

Veja `MELHORIAS.md` para o backlog completo (com prioridade, esforço
e status). Destaques:

- Interface gráfica com `streamlit` para arrastar e soltar PDFs.
- Gráficos (barras / pizza) automáticos no Excel.
- Aba `Maiores Gastos` (top transações individuais) e aba `Estornos`
  dedicada.
- Variação % vs mês anterior no Resumo Mensal.
- Suporte a Itaú, Bradesco, Inter e C6.
