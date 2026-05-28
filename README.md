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

# Opção A — instalação editável + ferramentas de dev (recomendado).
#           Habilita o comando `gastometro` no PATH do venv.
pip install -e ".[dev]"

# Opção B — só as dependências de runtime (sem entry point CLI).
#           Aí use `python extrator.py …` em vez de `gastometro …`.
# pip install -r requirements.txt
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

### Ativação automática do `.venv` (opcional)

Pra não precisar rodar `source .venv/bin/activate` toda vez, o projeto
já vem com um arquivo [`.envrc`](.envrc) versionado pronto pra uso com
o [direnv](https://direnv.net/) — ferramenta que ativa o venv ao entrar
na pasta e desativa ao sair, automaticamente.

#### macOS / Linux

```bash
brew install direnv                       # macOS (Homebrew)
# sudo apt install direnv                 # Debian / Ubuntu
# sudo dnf install direnv                 # Fedora

# Plug do shell (escolha o seu)
echo 'eval "$(direnv hook zsh)"'  >> ~/.zshrc
# echo 'eval "$(direnv hook bash)"' >> ~/.bashrc

# Reinicie o terminal e autorize o .envrc deste projeto (1x só)
cd /caminho/para/gastometro
direnv allow
```

A partir daí, ao entrar em `gastometro/` o venv ativa sozinho; ao sair,
desativa. Funciona pra `gastometro`, `pytest`, `ruff`, `mypy` — qualquer
binário do venv.

#### Windows

`direnv` não tem build oficial pra Windows nativo. Duas alternativas:

**1. Via WSL (Windows Subsystem for Linux) — experiência idêntica à do
macOS/Linux.** Dentro do WSL, siga o passo a passo acima.

**2. Função no perfil do PowerShell — sem instalar nada extra.** Abra
o `$PROFILE` (`notepad $PROFILE`; se não existir, o PowerShell cria) e
adicione:

```powershell
function gastometro {
    & "$HOME\Projects\gastometro\.venv\Scripts\gastometro.exe" @args
}
```

Recarregue com `. $PROFILE` (ou abra um terminal novo). Agora
`gastometro …` funciona de qualquer pasta, sem ativar venv. Replique
o padrão pra `pytest`, `ruff` e `mypy` se quiser o mesmo conforto com
os comandos de dev.

### Comandos do CLI

Depois da instalação editável (`pip install -e ".[dev]"`), o comando
`gastometro` fica disponível no `PATH` do venv. Os dois comandos abaixo
são equivalentes — escolha o estilo que preferir:

```bash
gastometro [argumentos]        # entry point declarado em pyproject.toml
python extrator.py [argumentos]  # alternativa sem instalação editável
```

Referência rápida:

| Comando | O que faz |
| --- | --- |
| `gastometro` | Processa **todos** os PDFs de `entrada/` e atualiza `saida/gastometro.xlsx`. |
| `gastometro entrada/Fatura.pdf` | Processa **um único PDF** específico. |
| `gastometro ~/Downloads/faturas/` | Processa todos os PDFs de **outra pasta**. |
| `gastometro recategorizar` | Re-aplica `categorizar()` em todo o Excel (sem reler PDFs). Mantém filtros e tabelas; reconstrói as abas analíticas. |
| `gastometro recategorizar caminho.xlsx` | Idem, num Excel em local arbitrário. |
| `gastometro aprender` | Lê edições manuais da coluna `Categoria` no Excel e salva em `categorias_usuario.json` como overrides. |
| `gastometro aprender caminho.xlsx` | Idem, num Excel em local arbitrário. |

Comandos de qualidade (instalados pelo extra `[dev]`):

```bash
pytest          # roda a suite (109 testes hoje)
ruff check .    # lint + imports + upgrades
ruff check . --fix   # com auto-fix
mypy .          # checagem de tipos
```

### Fluxo padrão (recomendado)

```bash
# 1) Coloque os PDFs em entrada/
mv ~/Downloads/Fatura_05_2026.pdf entrada/
mv ~/Downloads/Nubank_2026-05-13.pdf entrada/

# 2) Rode o extrator
gastometro
# (equivalente: python extrator.py)
```

O resultado fica em `saida/gastometro.xlsx`. Cada execução **acumula**
faturas novas no mesmo arquivo. Faturas com nome de PDF já presente no
Excel são ignoradas (mostra "Ignorado (já no Excel)" no terminal).

### Alternativas (sobrescrevem a pasta padrão)

```bash
# Processar um único PDF fora de entrada/
gastometro ~/Downloads/Fatura_05_2026.pdf

# Processar todos os PDFs de outra pasta
gastometro ~/Downloads/faturas/
```

Em qualquer modo, a saída sempre vai para `saida/gastometro.xlsx`.

### Re-processar uma fatura

Se você atualizou as regras de categorização e quer reaplicá-las **só
nas categorias** sem reler PDFs (mantém filtros/tabelas do Excel):

```bash
gastometro recategorizar
```

Detalhes na seção "[Recategorizar o Excel inteiro](#recategorizar-o-excel-inteiro-recategorizar)" mais abaixo.

Para forçar a leitura do PDF de novo (ex.: alguma transação foi
extraída errada e o parser mudou):

1. Abra `saida/gastometro.xlsx`.
2. Apague a linha dessa fatura na aba **Informações** e todas as
   transações dela na aba **Transações** (filtrar por `Arquivo`).
3. Salve e rode `gastometro` novamente.

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
  Inclui **gráfico de pizza** "Distribuição por Categoria" ao lado dos
  dados.
- **Resumo Mensal**: pivot referência (mês/ano) × categoria, com total
  por mês, coluna `Variação %` (variação % do total vs mês anterior)
  e linha `TOTAL` no fim. Inclui **gráfico de barras** "Total Mensal"
  abaixo dos dados.
- **Comparativo** (filtro): versão tabular do comparativo mensal —
  uma linha por categoria com `<penúltimo mês> (R$)`, `<último
  mês> (R$)`, `Δ Absoluto (R$)` e `Δ %`. Ordenada por |Δ| desc,
  com linha `TOTAL` no fim. Os nomes dos meses no cabeçalho são
  dinâmicos.
- **Resumo por Cartão**: uma linha por cartão (`Banco — Titular`) com
  qtde. de faturas, qtde. de transações, primeira/última referência,
  total gasto, média por fatura e ticket médio.
- **Cartão x Mês**: pivot referência × cartão. Responde "quanto cada
  cartão gastou em cada mês", com totais por linha e coluna. Inclui
  **gráfico de linha** "Tendência por Cartão" abaixo dos dados,
  facilitando ver disparos ou quedas individuais.
- **Cartão x Categoria**: pivot categoria × cartão. Mostra como cada
  cartão se distribui por categoria (útil para decidir qual usar
  para quê).
- **Maiores Gastos** (filtro): top 20 transações individuais por
  valor (apenas gastos, ignora estornos). Diferente de
  `Top Comerciantes` (agrupado por descrição), aqui cada linha é
  uma compra isolada — ótimo para revisar parcelas altas, hotéis,
  eletrodomésticos.
- **Estornos** (filtro): todas as transações com `Valor (R$) < 0`
  (devoluções, descontos de anuidade, parcelas canceladas).
  Ordenadas pelas referências mais recentes (e desempate pelo
  maior valor absoluto). Útil para conferir que os estornos não
  estão sendo "esquecidos" no meio das demais.
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

Top 10 descrições em 'Outros Gastos' (acumulado no Excel):
  R$    928.00  ( 4x)  G B Tucurivi Comercio
  ...

Comparativo: Maio/2026 vs Abril/2026
  TOTAL                    R$ 5.355,35  (+9.5% / +462,78 vs R$ 4.892,57)
  Alimentação                 R$ 897,63  (+267.9% / +653,64)
  Mercado                   R$ 1.184,66  (-33.1% / -586,45)
  Combustível               R$ 1.233,59  (+46.4% / +390,86)
  ...

Concluído.
```

O comparativo mensal mostra automaticamente a variação % e absoluta
do último mês vs o anterior, destacando as categorias com maior
movimento.

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
gastometro aprender
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
`gastometro`, as **linhas antigas continuam com as categorias
de quando foram inseridas** (apenas faturas novas usam as regras
atualizadas).

Para propagar as regras atuais para todo o Excel sem precisar apagar o
arquivo e reprocessar PDFs:

```bash
gastometro recategorizar                       # usa saida/gastometro.xlsx
gastometro recategorizar caminho/arquivo.xlsx  # arquivo específico
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
> Excel e que **ainda não foram capturadas** via `gastometro aprender`
> serão sobrescritas. Fluxo seguro:
>
> ```bash
> gastometro aprender        # salva edicoes do Excel no JSON
> gastometro recategorizar   # propaga JSON + dicionario p/ tudo
> ```

## Interface Web (Streamlit)

A partir da Fase 2 o projeto também tem uma UI Streamlit pra consumir
os dados do banco SQLite local (mesma fonte que alimenta o Excel).

```bash
streamlit run app/streamlit_app.py
# ou, equivalente com porta fixa e sem telemetria:
streamlit run app/streamlit_app.py --server.port=8501 --browser.gatherUsageStats=false
```

Páginas disponíveis (sidebar):

- **Dashboard** — KPIs (mês atual vs anterior, acumulado), barras
  mensais e pie por categoria.
- **Lançamentos** — tabela completa com filtros por pessoa, conta,
  categoria, tipo, mês, data e busca por descrição. Export CSV.
- **Faturas** — uma linha por PDF importado, drill-down nos lançamentos
  da fatura selecionada.
- **Categorias** — top "Outros Gastos" com editor de categorias,
  overrides ativos, override manual e botão de re-categorizar histórico.

A UI sempre lê do banco em `dados/gastometro.db`. Se você ainda não
populou, rode antes:

```bash
gastometro                         # processa PDFs em entrada/
python -m imports.migrar_excel_legado  # importa saida/gastometro.xlsx histórico
```

## Estrutura do projeto

```
gastometro/
├── entrada/                       # coloque os PDFs aqui (gitignored)
├── saida/                         # gastometro.xlsx é gerado aqui (gitignored)
├── dados/                         # SQLite + backups (gitignored)
├── extrator.py                    # CLI + orquestra DB + export Excel
├── categorias.py                  # regras de categorização (fallback)
├── parsers/                       # parsers por banco (PDF → Fatura)
├── db/                            # SQLModel + Alembic + repo + backup
├── imports/                       # ETL legado (Excel → banco)
├── export/                        # banco → Excel
├── app/                           # UI Streamlit (Fase 2)
│   ├── streamlit_app.py           # entrypoint
│   ├── helpers.py                 # filtros, formato BR, cache
│   └── paginas/                   # dashboard, lancamentos, faturas, categorias
├── alembic/                       # migrations versionadas
├── tests/                         # pytest (parsers, repo, export, app)
├── pyproject.toml                 # build + ruff + mypy + pytest
├── requirements.txt
├── requirements-dev.txt           # requirements.txt + pytest + ruff + mypy
├── README.md                      # este arquivo
└── MELHORIAS.md                   # backlog vivo de melhorias (priorizado)
```

## Testes, lint e tipos

O projeto usa `pytest`, `ruff` (lint + imports + upgrades) e `mypy`
(tipos). Instale as dependências de dev e rode na raiz:

```bash
pip install -r requirements-dev.txt   # ou: pip install -e ".[dev]"

python -m pytest                       # 145 testes (parsers + repo + export + app)
ruff check .                           # lint
ruff check . --fix                     # lint com auto-fix
mypy .                                 # tipos
```

Toda a configuração (ruff, mypy, pytest) vive em `pyproject.toml`.
Targets: Python 3.10+, line-length 100, regras pragmáticas (`E`,
`F`, `I`, `B`, `UP`, `W`, `SIM`).

### Integração Contínua

Cada `push` em `main` e cada pull request dispara o workflow
`.github/workflows/ci.yml`, que roda em paralelo:

- **`lint-and-types`** — `ruff check .` + `mypy .` em Python 3.12.
- **`test`** — `pytest` em matrix Python 3.10 / 3.11 / 3.12.

Builds antigos do mesmo PR são cancelados automaticamente
(`concurrency.cancel-in-progress: true`).

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
