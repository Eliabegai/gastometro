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

- **Dashboard** — toggle **Ano inteiro × Mensal** no topo. No modo
  anual, KPIs (Despesas, Receitas, Saldo, Qtde) do ano selecionado +
  pie e top 10 do ano todo. No modo mensal, escolhe o mês e os KPIs
  passam a mostrar despesas/receitas do mês com delta vs mês anterior;
  o pie e top 10 também recortam pro mês selecionado. As barras
  mensais sempre mostram o ano inteiro pra dar contexto (mês
  selecionado fica em destaque visual). **Clicar numa barra** muda
  pro modo Mensal já com o mês clicado selecionado — atalho rápido
  pra fazer drill-down. O **Top 10** lista as maiores **categorias**
  (soma + quantidade + ticket médio), não lançamentos individuais —
  evita que uma categoria com muitas compras (ex.: Mercado) seja
  subestimada na visão.
- **Lançamentos** — tabela completa com filtros por pessoa, conta,
  categoria, tipo, mês, data e busca por descrição. Export CSV.
- **Faturas** — uma linha por PDF importado, drill-down nos lançamentos
  da fatura selecionada.
- **Categorias** — mesmo toggle **Ano × Mensal** do Dashboard,
  filtrando o resumo de categorias e o top "Outros Gastos" pelo
  período escolhido. Inclui editor de categorias, overrides ativos,
  override manual e botão de re-categorizar histórico (essa última
  ação é global, ignora o filtro).
- **Importar** — dois blocos:
  1. **PDFs de fatura**: uploader pra enviar um ou mais PDFs (mesma
     lógica do CLI `gastometro`). Checkboxes pra arquivar em
     `entrada/` e regenerar o Excel.
  2. **Planilha familiar (Google Sheets)**: cola a URL pública da
     planilha uma vez (Compartilhar → "Qualquer pessoa com o link
     pode ver") e dali pra frente é um clique no botão
     **🔄 Atualizar do Google Sheets** — baixa o XLSX e roda o
     importador idempotente.
  O bloco de PDFs também aparece num expander no topo da página
  **Faturas**.

### Persistência dos filtros (URL + sessão)

Os filtros não somem mais quando você troca de página ou recarrega
o browser. Funciona em dois níveis:

- **Globais** (compartilhados entre Dashboard, Categorias e
  Lançamentos): `ano`, `mês` e `modo` (Anual/Mensal). Setou em uma
  página → todas as outras já abrem com o mesmo recorte.
- **Por página** (Lançamentos): `pessoa`, `conta`, `categoria`,
  `tipo`, `referência`, `busca` ficam memorizados na **própria**
  página.

Tudo viaja na URL (`?ano=2024&mes=2024-05&modo=Mensal&lanc_pessoas=Eliabe%20Gai|Ana`),
então:

- F5 / fechar e abrir o browser preserva os filtros.
- Você pode **compartilhar um link** com filtros já aplicados (ex.:
  mandar pra esposa "olha o consumo de maio").
- Cada página tem um botão **🧹 Limpar filtros** (no topo do
  Dashboard/Categorias, no rodapé da sidebar em Lançamentos) que
  volta tudo ao default.

A UI sempre lê do banco em `dados/gastometro.db`. Se você ainda não
populou, rode antes:

```bash
gastometro                                # processa PDFs em entrada/
python -m imports.migrar_excel_legado     # importa saida/gastometro.xlsx histórico
python -m imports.importar_planilha_familiar  # importa despesas_Eliabe_Ana.xlsx (Total)
```

## Importação da planilha familiar (Fase 3)

O script `imports/importar_planilha_familiar.py` lê a aba **Total** da
`despesas_Eliabe_Ana.xlsx` (layout pivotado: categorias nas linhas,
meses/anos nas colunas) e gera 1 lançamento por célula no banco.

```bash
python -m imports.importar_planilha_familiar
# ou apontando pra outro arquivo:
python -m imports.importar_planilha_familiar caminho/da/planilha.xlsx
```

Regras aplicadas durante o import:

- **Linhas de soma ignoradas**: `Total Gastos`, `Saldo`, `Défice |
  Superávit`, `Poupança`, `Meta`, `Dízimos` (soma de Eliabe+Ana),
  `Faculdade` (igual à linha Uninter detalhada), `Outros` (soma da
  seção de despesas diversas).
- **Regra anti-PDF**: linhas "Cartão de Crédito - Viacredi/Nubank
  Eliabe" e "Cartão de Crédito - Nubank Ana" pulam meses onde já
  existe a fatura PDF correspondente (o PDF tem o detalhe granular).
- **Receitas**: linhas `Ganhos Eliabe`, `Ganhos Ana Letícia` e
  `Empréstimo` viram `tipo='receita'` com categorias `Salário` /
  `Empréstimo Recebido`.
- **Idempotência**: hash determinístico por `(descrição canônica,
  ano, mês, pessoa)`. Reimport não duplica.
- **Data**: como a planilha tem só mês/ano, fixa no 1º dia do mês de
  referência (`YYYY-MM-01`).

Pra incluir uma linha nova da planilha, edite o dicionário `CONFIG`
em `imports/importar_planilha_familiar.py`.

## Sincronização com Google Sheets

Pra continuar atualizando a planilha familiar no Google Sheets e
puxar pro banco com um clique:

1. No Google Sheets, abra a planilha → **Compartilhar** → mude o
   acesso pra "Qualquer pessoa com o link" (pode ser só
   visualização — não precisa de edição).
2. Copie a URL da barra de endereços (qualquer formato funciona —
   o script extrai o ID automaticamente).
3. Cole a URL no campo da página **Importar** (Streamlit) e
   clique em **🔄 Atualizar do Google Sheets**. A URL fica salva
   em `dados/planilha_url.txt` (gitignored) — nas próximas vezes
   é só clicar no botão.

Ou via CLI:

```bash
# 1ª vez (informa a URL — fica salva):
python -m imports.baixar_planilha_familiar "https://docs.google.com/spreadsheets/d/.../edit"

# Próximas vezes:
python -m imports.baixar_planilha_familiar
python -m imports.importar_planilha_familiar dados/planilha_familiar_baixada.xlsx
```

Alternativa via env var: defina `GASTOMETRO_PLANILHA_URL` no `.envrc`
(direnv) ou `.env` e o script lê automaticamente.

Como o importador é **idempotente** (hash determinístico por
descrição+ano+mês+pessoa), você pode re-baixar quantas vezes quiser —
só os valores novos/alterados entram. Linhas duplicadas viram
"skip" silencioso.

## Rodar com Docker (full-time em qualquer máquina)

Pra ter o app rodando 24/7 num mini-PC, Raspberry Pi, NAS ou Mac que
fica sempre ligado — e poder acessar de outros PCs / celular via
browser na mesma rede — basta o `docker-compose.yml` incluso.

Pré-requisitos: [Docker Desktop](https://www.docker.com/products/docker-desktop/)
(Mac/Windows) ou Docker Engine + Compose (Linux).

### Subir, parar, atualizar

```bash
# 1ª vez (build da imagem + sobe em background):
docker compose up -d --build

# Acompanhar logs:
docker compose logs -f gastometro

# Parar (preserva os volumes ./dados, ./entrada, ./saida):
docker compose down

# Atualizar após mexer no código:
docker compose up -d --build

# Status / saúde:
docker compose ps
```

Depois de subir, acesse:

- No host: `http://localhost:8501`
- Em outros PCs/celular na mesma rede: `http://<ip-do-host>:8501`
  (descubra o IP com `ipconfig getifaddr en0` no Mac ou
  `hostname -I` no Linux).

### Detalhes da arquitetura

- **Imagem multi-arch**: `python:3.12-slim` cobre Mac (M1/M2/M3 arm64
  e Intel amd64), Linux x86 e Raspberry Pi 4/5 (arm64) sem
  configuração extra.
- **Bind mounts** (3): `./dados → /data` (banco + backups), `./entrada
  → /app/entrada` (PDFs arquivados pelo uploader) e `./saida →
  /app/saida` (Excel acumulativo). Você vê e mexe nos arquivos
  direto da pasta do projeto.
- **Usuário não-root** (UID/GID 1000): casa com o dono do bind mount
  em Linux/Mac. Pra ajustar ao seu UID real, rode
  `APP_UID=$(id -u) APP_GID=$(id -g) docker compose up -d --build`.
- **Schema automático**: `garantir_schema()` roda `alembic upgrade
  head` no boot — primeira subida cria o banco do zero, subidas
  seguintes são no-op.
- **Restart automático**: `restart: unless-stopped` traz o app de
  volta após reboot do host ou crash.
- **Healthcheck**: bate em `/_stcore/health` a cada 30s. `docker
  compose ps` mostra `(healthy)` quando tudo OK.

### Variáveis de ambiente úteis

Pode definir no `.env` da raiz (mesmo arquivo que o `direnv` usa):

```bash
# .env
GASTOMETRO_PLANILHA_URL=https://docs.google.com/spreadsheets/d/.../edit
GASTOMETRO_BACKUPS_KEEP=60         # default 30
```

### Backup off-site (opcional, com Litestream)

Pra replicar o SQLite continuamente pra S3 / Backblaze B2 / MinIO,
descomente o bloco `litestream:` do `docker-compose.yml` e siga as
instruções inline. Aí restaurar em outro PC é um comando:

```bash
litestream restore -o dados/gastometro.db s3://meu-bucket/gastometro.db
```

## Mudar de PC / sincronizar 2 PCs

Três abordagens, do melhor pro mais simples — escolha conforme a
realidade do seu uso.

### A. Servidor central + clientes web (recomendado)

Suba o container Docker num PC/Mac/Raspberry/NAS que fica sempre
ligado (seção acima). Os outros PCs **não rodam o app** — só abrem
`http://<ip-do-servidor>:8501` no browser.

- Vantagem: zero cópia de banco, zero risco de conflito, dados
  sempre sincronizados.
- Quando faz sentido: você tem uma máquina sempre ligada (Mac mini,
  mini-PC, Raspberry Pi 4+).

### B. Migração one-shot via `restaurar_banco`

Quando trocar de notebook ou levar os dados pra outra máquina:

```bash
# No PC antigo, copie o banco:
scp dados/gastometro.db usuario@novo-pc:~/backup_gastometro.db
# (ou via AirDrop, pen drive, Drive…)

# No PC novo, clone o repo, instale e restaure:
git clone https://github.com/.../gastometro && cd gastometro
pip install -r requirements.txt
python -m scripts.restaurar_banco ~/backup_gastometro.db
streamlit run app/streamlit_app.py # porta padrão 8501
#ou
streamlit run app/streamlit_app.py --server.port 8502
```

O `scripts/restaurar_banco.py`:

- Valida que é um SQLite válido (header `SQLite format 3`).
- Faz **backup automático** do banco atual (motivo
  `pre_restauracao`) antes de sobrescrever — você pode reverter via
  `dados/backups/`.
- Roda `alembic upgrade head` no banco restaurado (útil se veio de
  uma versão um pouco mais antiga do app).
- Flags: `--destino <path>` muda o destino; `--sem-checagem` ignora
  magic bytes; `--sem-migration` pula o Alembic.

### C. Pasta `dados/` sincronizada via Drive/iCloud/Dropbox

Use `GASTOMETRO_DADOS_DIR` (ou no Docker, mude o bind mount) pra
apontar pra uma pasta sincronizada:

```bash
# Mac com iCloud Drive:
export GASTOMETRO_DADOS_DIR="$HOME/Library/Mobile Documents/com~apple~CloudDocs/gastometro"
```

> **Aviso**: SQLite **não tolera escrita concorrente** num arquivo
> sincronizado por cloud. Use essa abordagem só se você **nunca**
> abre o app em dois PCs ao mesmo tempo. Se rolar conflito, o serviço
> de sync vai criar `gastometro (conflicted copy).db` e você terá
> que escolher manualmente qual versão manter.
>
> Pra uso simultâneo seguro, prefira a abordagem **A**.

## Consolidar contas duplicadas

Se você vier de uma versão antiga do projeto, talvez tenha no banco
duplicatas tipo `Ailos Mastercard` (do seed antigo) **e** `Ailos —
Eliabe Gai` (criada pelos parsers de PDF) — apontando pro mesmo
cartão. O comando abaixo funde tudo no nome canônico (`{Banco} —
{Titular}`), preservando os lançamentos da conta antiga:

```bash
python -m db.consolidar_contas
```

É idempotente — rodar várias vezes não muda nada depois da primeira
execução. O `seed_inicial` já foi atualizado pra criar as contas
diretamente no formato canônico, então **bancos novos não precisam
desse passo**.

## Estrutura do projeto

```
gastometro/
├── entrada/                       # coloque os PDFs aqui (gitignored)
├── saida/                         # gastometro.xlsx é gerado aqui (gitignored)
├── dados/                         # SQLite + backups + cache de URL (gitignored)
├── extrator.py                    # CLI + orquestra DB + export Excel
├── categorias.py                  # regras de categorização (fallback)
├── parsers/                       # parsers por banco (PDF → Fatura)
├── db/                            # SQLModel + Alembic + repo + backup + consolidação
├── imports/                       # ETL: Excel legado + planilha familiar + Google Sheets
├── export/                        # banco → Excel
├── scripts/                       # CLIs utilitários (restaurar_banco, etc.)
├── app/                           # UI Streamlit (Fase 2)
│   ├── streamlit_app.py           # entrypoint
│   ├── helpers.py                 # filtros, formato BR, cache
│   ├── estado.py                  # persistência de filtros (session + URL)
│   └── paginas/                   # dashboard, lancamentos, faturas, categorias, importar
├── alembic/                       # migrations versionadas
├── tests/                         # pytest (parsers, repo, export, app)
├── Dockerfile                     # imagem multi-arch (amd64 + arm64)
├── docker-compose.yml             # serviço gastometro + Litestream opcional
├── .dockerignore                  # enxuga a imagem (sem .venv, dados, tests…)
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

python -m pytest                       # 223 testes (parsers + repo + export + app + planilha + consolidação + upload + sync + restore + filtros persistentes)
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
