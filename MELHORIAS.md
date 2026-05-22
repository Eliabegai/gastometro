# Melhorias — Projeto gastometro

> Backlog vivo de melhorias do projeto. Atualizar conforme itens são
> concluídos ou novos são propostos.
>
> **Como usar**: marque `[x]` quando concluir, mova para a seção
> "Concluídas" no fim do arquivo, registre a data e o commit relacionado.

## Legenda

- **Prioridade**: P0 (crítico) / P1 (alto) / P2 (médio) / P3 (baixo)
- **Esforço**: XS (<30 min) / S (~1h) / M (meio dia) / L (1 dia+)
- **Status**: `[ ]` pendente / `[~]` em andamento / `[x]` concluído

---

## 1. Robustez e correção de bugs

- [ ] **1.1 — Testes e robustez de `parse_valor_brl`** — P2 / S
  - Verificado em 22/05/2026 que o caso `"1.234.56"` (ponto como milhar e
    decimal) descrito originalmente no HANDOFF **não ocorre** nas faturas
    Ailos reais; o que aparece é o formato americano `"1,234.56"` (já
    suportado). O bug do trailing `.` foi corrigido junto com o item 1.3
    (`rstrip(".,")` na função).
  - Pendente: bateria de testes unitários cobrindo
    `"1.234,56"`, `"1,234.56"`, `"1234,56"`, `"4,422.81."`,
    `"-R$ 50,00"`, `"R$ 0,00"`, `"\u22125,00"`, vazios e `None`.

- [x] **1.2 — Inferência de ano errada em parcelas antigas** — P1 / S
  - Concluído em 22/05/2026 (ver "Concluídas").

- [x] **1.3 — Avisar quando soma diverge do total da fatura** — P1 / XS
  - Concluído em 22/05/2026 (ver "Concluídas").

- [x] **1.4 — Remover dados pessoais de `PALAVRAS_NAO_TITULAR`** — P0 / XS
  - Concluído em 22/05/2026 (ver "Concluídas").

- [x] **1.5 — `import pandas` dentro de função (3 lugares)** — P3 / XS
  - Concluído em 22/05/2026 (ver "Concluídas").

- [ ] **1.6 — PDF lido duas vezes (detecção + extração)** — P2 / S
  - `parsers/__init__.py::detectar_banco` + `extrair_fatura` chamam `_ler_texto` independentemente.
  - Refatorar para abrir o PDF uma vez e reaproveitar o texto.

- [x] **1.7 — Capturar anuidade e preservar sinal de estornos (Ailos)** — P1 / S
  - **Anuidade**: aparece na seção `MOVIMENTAÇÕES DA CONTA` acima do
    cabeçalho da tabela principal, em layout próprio (3 linhas:
    descrição / data+valor / `(NNNN) X/Y`). Hoje o parser descarta
    tudo acima do cabeçalho. Resultado: o `valor_total` declarado
    pela fatura diverge da soma das transações (caso visto:
    `Fatura_02_2026.pdf` com diferença de R$ 11,67).
  - **Estornos**: o pdfplumber separa `"-R$"` e o número em dois
    tokens distintos; `_parse_valor_tokens` pega o numérico primeiro
    e perde o sinal, registrando o estorno como valor positivo
    (caso visto: `Fatura_04_2026.pdf`, MERCADOLIVRE*TOTALMO 2026-03-04,
    `-R$ 39,99` registrado como `+R$ 39,99` → soma 4.270,35 vs total
    4.190,37 = +R$ 79,98).
  - Lançamentos administrativos a manter como descartados: `SALDO
    ANTERIOR`, `PAGTO DEB EM CONTA`, `PAGAMENTO RECEBIDO/EFETUADO`,
    `TOTAL DE`, `TOTAL R$`.
  - Lançamentos a aceitar como transações reais: `ANUIDADE
    MASTERCARD`, `DESC ANUIDADE` (desconto/isenção, valor negativo
    ou zero), estornos comuns na tabela principal.

- [x] **1.8 — Divergências em algumas faturas Nubank** — P1 / M
  - Resolvidas todas as divergências de cálculo (de 7 → 0); restam
    apenas 3 avisos informativos sobre **estornos**, conforme detalhe
    na seção "Concluídas" abaixo.

- [x] **1.9 — Parcela do Ailos vazando para a coluna Cidade** — P1 / XS
  - Concluído em 22/05/2026 (ver "Concluídas").

- [ ] **1.10 — Cidade truncada em algumas linhas Ailos (`DO JARAGUA DO`)** — P2 / S
  - Quando a descrição é longa, o Ailos quebra o lançamento em **duas
    linhas visuais** com `top` ~4pt de diferença (ex.: linha 1
    "00401 SH JARAGUA DO" + linha 2 "11 NOV JARAGUA DO SU R$ 93.23").
    `_agrupar_palavras_em_linhas` usa tolerância 3pt e separa as
    duas → metade do nome da loja vai para `desc` e a outra metade
    fica como "cidade" (`DO JARAGUA DO`).
  - Subir a tolerância para ~5pt ou implementar um pós-merge das
    linhas adjacentes do mesmo lançamento.

## 2. Categorização (`categorias.py`)

- [ ] **2.1 — Duplicatas e conflitos no dicionário** — P2 / XS
  - `apple.com/bill` e `google play` estão em "Assinatura Digital" **e** "Compra Digital" (a segunda nunca pega).
  - `"mercado pago"` aparece duas vezes na mesma categoria.
  - Consolidar e decidir critério.

- [ ] **2.2 — Casamento por substring gera falsos positivos** — P1 / M
  - `"big"` casa `"BIGODE LANCHES"`, `"raia"` casa `"RAIANE OFICINA"`, etc.
  - Suporte a regex com `\b...\b`.
  - Normalização de acentos (remover diacríticos antes de comparar).
  - Considerar pesos ("quem casa mais palavras vence" em vez de "primeira que casa").
  - Permitir regras negativas ("posto" → Combustível, exceto se também contiver "vet" ou "saúde").

- [x] **2.3 — Aprendizado a partir do usuário** — P2 / M
  - Concluído em 22/05/2026 (ver "Concluídas").

- [x] **2.4 — Visibilidade do "Outros Gastos"** — P2 / S
  - Concluído em 22/05/2026 (ver "Concluídas").

## 3. Testes automatizados

- [ ] **3.1 — Setup do pytest** — P1 / XS
  - Pasta `tests/`, `pytest` em dev-requirements (ou extras `[dev]` no `pyproject.toml`).

- [ ] **3.2 — Testes de `parse_valor_brl`** — P1 / S

- [ ] **3.3 — Testes de `categorizar`** — P1 / S
  - Pelo menos 2 positivos e 1 negativo por categoria.

- [ ] **3.4 — Testes de `referencia_pelo_vencimento` e ano por parcela** — P1 / XS

- [ ] **3.5 — Smoke tests dos parsers com fixtures de texto** — P2 / M
  - Salvar o texto bruto extraído de cada PDF de teste em `tests/fixtures/*.txt` e validar contagem/total.

- [ ] **3.6 — Anonimizar 1 PDF de exemplo em `exemplos/`** — P3 / M
  - Trocar nome do titular por "FULANO TESTE" e mascarar finais de cartão.

## 4. Arquitetura

- [ ] **4.1 — Desacoplar parser de categorização** — P2 / S
  - Parsers devolvem `Transacao` com `categoria=""`; o `extrator.py` aplica `categorizar()` num passo separado.
  - Remove import `from categorias import categorizar` dos 3 parsers.
  - Permite reprocessar Excel sem reabrir PDF.

- [x] **4.2 — Mover `_ano_do_vencimento` para `parsers/base.py`** — P3 / XS
  - Concluído em 22/05/2026 (ver "Concluídas").

- [ ] **4.3 — Definir Protocol/ABC para parser** — P3 / S
  - Contrato `detectar() -> bool`, `extrair(pdf) -> Fatura`, `NOME_BANCO: str`.

- [ ] **4.4 — Refatorar `_montar_transacoes` do Ailos** — P2 / M
  - 85 linhas com várias mutações de estado (`desc_pendente`, `cidade_pendente`).
  - Quebrar em funções menores ou pequena máquina de estados.

## 5. Features

- [ ] **5.1 — Consolidação multi-fatura** — P1 / M
  - Excel mestre com aba `Consolidado` (todas as transações de N PDFs) + `Comparativo` (categoria × mês).

- [ ] **5.2 — Gráficos no Excel** — P2 / S
  - `openpyxl.chart.PieChart` (categorias) e `BarChart` (mensal).

- [ ] **5.3 — Interface Streamlit** — P2 / M
  - Drag-and-drop de PDF, baixar Excel.

- [ ] **5.4 — Suporte a outros bancos populares** — P2 / L
  - Itaú, Bradesco, Inter, C6. Um arquivo por banco em `parsers/`.

- [ ] **5.5 — Detecção de duplicatas entre faturas** — P2 / S
  - Útil ao consolidar; pega cobrança em duplicidade.

- [ ] **5.6 — Comparativo mensal automático** — P2 / S
  - "Mercado R$ X (+12% vs mês passado)".

- [ ] **5.7 — Exportar JSON/CSV além de Excel** — P3 / XS

- [ ] **5.8 — Modo "diff" (apenas lançamentos novos)** — P3 / M

- [ ] **5.9 — Alertas configuráveis (`config.yaml`)** — P3 / M

- [x] **5.10 — Excel único acumulativo + pastas `entrada/`/`saida/`** — P1 / S
  - Concluído em 22/05/2026 (ver "Concluídas").

## 6. Tooling / DX

- [ ] **6.1 — `pyproject.toml` + `ruff` + `mypy`** — P2 / S

- [ ] **6.2 — GitHub Actions: `pytest` + `ruff` em cada push** — P2 / S

- [ ] **6.3 — `pre-commit` bloqueando PDFs/XLSX por engano** — P3 / S

- [ ] **6.4 — Substituir `print` por `logging`** — P3 / S
  - Permite `--quiet`, `--debug` e log em arquivo.

- [ ] **6.5 — Pacote instalável (`pip install -e .`) com entrypoint `gastometro`** — P2 / S

- [ ] **6.6 — `argparse` no lugar de `sys.argv[1]`** — P2 / XS
  - Flags: `--output`, `--quiet`, `--banco=ailos`, `--no-categorize`.

## 7. Segurança e privacidade

- [x] **7.1 — Limpar dados pessoais do código** — P0 / XS
  - Duplicado do 1.4. Concluído em 22/05/2026.

- [ ] **7.2 — Verificar histórico do git por PDFs commitados** — P1 / XS
  - `git log --all -- '*.pdf' '*.xlsx'` para confirmar que nunca vazaram.

- [ ] **7.3 — `pre-commit` hook bloqueando dados sensíveis** — P2 / S
  - Mesma ideia do 6.3.

## 8. Documentação

- [ ] **8.1 — Corrigir typo `gastrometro/` no README** — P3 / XS
  - Linha 81 do `README.md`.

- [ ] **8.2 — Adicionar LICENSE (MIT)** — P3 / XS

- [ ] **8.3 — Criar CHANGELOG.md** — P3 / XS

- [ ] **8.4 — Tutorial "adicionar um banco" com exemplo concreto** — P3 / S

- [ ] **8.5 — Screenshot/GIF do Excel gerado no README** — P3 / S

---

## Concluídas

### 22/05/2026

- **1.9 — Parcela do Ailos vazando para a coluna Cidade**
  - `parsers/ailos.py::_classificar_palavras_em_colunas` aplicava
    classificação puramente posicional: tokens com X dentro do
    range da coluna `cidade` (limite_desc_cidade ≤ x <
    limite_cidade_valor) viravam `cidade_tokens`, **mesmo sendo
    indicadores de parcela** (`NN/MM`). O `_montar_transacoes`, por
    sua vez, só procurava parcela na descrição, então a parcela
    nunca era detectada e ficava grudada na cidade (ex.: cidade
    `'02/02 SAO PAULO'`).
  - Fix: classificação semântica antes da posicional — qualquer
    token que case `RE_PARCELA` (`^\d{1,2}/\d{1,2}$`) vai direto
    para `desc_tokens`, independente do X. Seguro porque `NN/MM`
    nunca aparece em data (`DD MMM`) ou valor (com `R$` ou só
    dígitos com `,`/`.`).
  - **Validação**: 15/15 Ailos seguem batendo total (delta R$ 0,00).
    Faturas afetadas:
    - `Fatura_01_2026.pdf`: MLP*NetshoesV agora com parc `02/02`
      e cidade `SAO PAULO`.
    - `Fatura_12_2025.pdf`: MLP*NetshoesV com parc `01/02`,
      cidade `SAO PAULO`.
    - 9 faturas tiveram aumento na contagem de parcelas detectadas
      (totais inalterados).
  - **Lateral encontrado e registrado em 1.10**: em algumas linhas
    longas (ex.: `00401 SH JARAGUA DO ... SU`) o agrupamento por
    `top` quebra a linha em duas (delta ~4pt > tolerância 3pt), e o
    resultado é uma cidade truncada (`DO JARAGUA DO`). Não afeta
    o total nem a parcela.

- **2.3 + 2.4 — Aprendizado por descrição + visibilidade dos "Outros Gastos"**
  - **2.3**: novo arquivo opcional `categorias_usuario.json` (na raiz,
    fora do git) com mapa `descrição → categoria`. Em `categorias.py`:
    - `_normalizar(texto)` aplica `unicodedata.NFD` para remover
      acentos, baixa caixa e colapsa espaços (`"MAPFRE  Seguros"` e
      `"mapfre seguros"` viram a mesma chave).
    - `_carregar_categorias_usuario()` lê o JSON com `lru_cache`,
      tolerando ausência ou JSON inválido (segue silencioso, item é
      opcional).
    - `categorizar()` consulta o override antes do dicionário fixo;
      cai no `categorizar_pelo_dicionario()` quando não há match.
    - `salvar_categorias_usuario(mapa)` persiste o JSON com chaves
      já normalizadas e invalida o cache.
  - **Comando `python extrator.py aprender [excel]`**: lê o Excel
    (padrão `saida/gastometro.xlsx`) e registra como override apenas
    as linhas cuja categoria salva difere do que o dicionário
    devolveria. Sobrescreve o JSON anterior. Útil para reaproveitar
    correções manuais que o usuário fez na coluna `Categoria` do
    Excel sem precisar inflar `categorias.py`.
  - **2.4**: `extrator.py::_imprimir_top_outros_gastos` lê o
    `DataFrame` final de transações, filtra `Categoria == "Outros
    Gastos"` com `Valor > 0` (ignora estornos), agrupa por descrição
    e imprime as 10 com maior soma. Mostra também a contagem
    (`N×`) e instruções de como categorizar.
  - **Privacidade**: `categorias_usuario.json` entrou no `.gitignore`
    (pode conter descrições com dados sensíveis).
  - **Validação**: ciclo completo testado nos 33 PDFs reais. Edição
    de 24 linhas do Excel (3 descrições distintas: `Localiza`,
    `MP *AUTOELETRICAA`, `Google YouTubePremiu`) gerou 5 entradas
    no JSON (graças à normalização) e, após apagar o Excel e
    reprocessar, todas as 24 transações foram categorizadas
    corretamente via override. As 3 descrições saíram do top-10 de
    "Outros Gastos".

- **1.8 — Divergências em faturas Nubank**
  - **`valor_total`**: agora `parsers/nubank.py::_extrair_metadata`
    prioriza `Total de compras` do `RESUMO DA FATURA` em vez de
    `Total a pagar`. Esse é o número correto para comparar com a
    soma das transações: `Total a pagar` inclui IOF, juros, multa
    e pagamentos parciais que não são "compras do mês".
  - **Formato antigo (até meados/2024)**: `RE_TRANSACAO` ficou mais
    permissivo — agora aceita linhas sem `R$` antes do valor
    (`DD MMM Descrição [- X/Y] valor`) e sinal negativo isolado
    (`-` ou `\u2212`) antes do valor. Resultado: `Nubank_2024-05-13.pdf`
    saiu de 0 para 27 transações.
  - **Parcelas no formato antigo**: novo `RE_PARCELA` aceita tanto
    `- Parcela X/Y` (formato atual) quanto `- X/Y` (formato antigo).
  - **Estornos**: linhas iniciadas por `Estorno de "X"` são
    registradas com valor negativo (crédito recebido), refletindo
    a realidade dos gastos do titular.
  - **Conciliação informativa**: `extrator.py::_conciliar_total`
    agora identifica quando a diferença bate com a soma dos
    estornos detectados e troca a mensagem padrão por uma
    informativa ("o banco computa o total bruto"). Útil porque o
    Nubank inclui o valor estornado dentro do `Total de compras`,
    enquanto nosso parser, corretamente, o trata como crédito.
  - **Validação**: 19/19 PDFs Nubank rodando sem erro; 16/19 com
    soma = `Total de compras` (delta R$ 0,00); os 3 restantes têm
    apenas estornos com mensagem informativa
    (`Nubank_2024-05/08/09-13.pdf`). 15/15 Ailos também continuam
    batendo exato. Excel total: 32 faturas, 942 transações
    (vs 914 antes — +28 transações capturadas da Nubank antiga).

- **1.7 — Anuidade Ailos capturada e estornos com sinal correto**
  - **Estornos**: `parsers/ailos.py::_parse_valor_tokens` agora detecta
    tokens `-R$`, `-` ou `\u2212` antes do número e propaga o sinal
    negativo. Caso `Fatura_04_2026.pdf` MERCADOLIVRE*TOTALMO 2026-03-04
    `-R$ 39,99` corrigido de `+39,99` para `-39,99`.
  - **Anuidade**: nova função `_extrair_movimentacoes_conta(coluna,
    data_vencimento)` processa a seção `MOVIMENTAÇÕES DA CONTA` que
    fica acima da tabela principal. Para evitar o intercalamento entre
    colunas que `extract_text()` causa, recebe o crop da coluna
    esquerda direto e localiza a faixa Y entre `MOVIMENTAÇÕES` e o
    cabeçalho `DATA DESCRIÇÃO`, depois agrupa palavras em linhas e
    aceita o padrão "descrição (linha anterior) / DD MMM valor /
    `(NNNN) X/Y` (linha seguinte)".
  - `ADMINISTRATIVOS` reduzido para os termos que realmente são
    metadados (`SALDO ANTERIOR`, `PAGTO DEB EM CONTA`, `PAGAMENTO
    RECEBIDO/EFETUADO`, `TOTAL DE`, `TOTAL R$`); `ANUIDADE
    MASTERCARD`, `DESC ANUIDADE` e `ESTORNO` saíram da lista e voltam
    como transações reais quando aplicável.
  - **Validação**: 15 PDFs Ailos rodados pelo `extrator.py`, todos
    com soma das transações batendo exatamente o `valor_total`
    declarado (delta R$ 0,00). Casos relevantes:
    - `Fatura_02_2026.pdf`: anuidade R$ 11,67 (11/12) capturada → total
      R$ 933,59 bate.
    - `Fatura_03_2026.pdf`: anuidade R$ 11,63 (12/12 — última parcela)
      capturada.
    - `Fatura_04_2026.pdf`: estorno R$ −39,99 preservado.
    - `Fatura_05_2026.pdf`: anuidade R$ 13,50 (01/12 — nova série)
      junto com `DESC ANUIDADE POR USO` R$ −13,50, refletindo o
      desconto integral por uso. Cobre o cenário "se passa de um certo
      valor é abatida".

- **1.2 + 4.2 — Inferência correta do ano da transação + consolidação em `base.py`**
  - Nova função `inferir_ano_transacao(mes_tx, data_vencimento, parcela,
    *, recuar_pelo_numero_da_parcela=False)` em `parsers/base.py`, com
    duas estratégias:
    - **Regra base** (sempre aplicada): se `mes_tx > mes_venc`, ano =
      `ano_venc - 1` (compras de meses anteriores que entram numa
      fatura mais recente, ex.: dezembro caindo na fatura de janeiro).
      Senão, mesmo ano do vencimento.
    - **Recuo por parcela** (`recuar_pelo_numero_da_parcela=True`):
      quando o banco exibe a **data da compra original** (não a data
      da cobrança da parcela atual), o ano da compra é calculado
      recuando `X - 1` meses a partir do mês do vencimento, sendo `X`
      o número da parcela atual em `X/Y`. Cobre o caso `MAPFRE
      SEGUROS 14 JAN 16/18` em fatura maio/2026 → 14/01/2025.
  - **Por banco**:
    - **Ailos**: liga o recuo (mostra data da compra). Inclui ajuste no
      caso especial em que a parcela vem em linha separada do nome do
      produto — a data é recalculada quando a parcela é descoberta.
    - **Nubank**: mantém o recuo desligado (mostra a data da cobrança
      da parcela, sempre próxima do dia 6 do ciclo).
    - **Banco do Brasil**: mantém desligado por enquanto (sem PDF real
      para validar; pode mudar quando houver fatura de teste).
  - **4.2**: a função antiga `_ano_do_vencimento` foi consolidada em
    `parsers/base.py::ano_do_vencimento` (pública) e removida dos 3
    parsers, eliminando triplicação e a importação `from datetime import
    date` redundante nos parsers.
  - **Validação**: rodada com 18 PDFs reais (Ailos + 17 Nubank, indo de
    mai/2024 a mai/2026) → 325 transações, R$ 26.641,41 no total. Em
    `Nubank_2025-01-13.pdf` (fatura jan/2025), as 49 transações com
    data `06 DEZ` foram corretamente atribuídas a 2024; as 2 com data
    em janeiro ficaram em 2025. `MAPFRE SEGUROS 16/18` agora consta
    como 14/01/2025.

- **1.5 — Substituído `import pandas` por `datetime.date` nos parsers**
  - Os três parsers (Ailos, Nubank, BB) usavam `pd.Timestamp.now().year`
    apenas como fallback do ano de vencimento, importando `pandas`
    dentro da função. Trocado por `datetime.date.today().year` (stdlib),
    com `from datetime import date` no topo do módulo.
  - A função `_ano_do_vencimento` ainda está triplicada nos 3 parsers —
    consolidar em `parsers/base.py` está mapeado como item 4.2.
  - Validação: extração nos PDFs reais segue idêntica (48 + 10
    transações); fallback testado retornando o ano atual correto.

- **1.3 — Avisar quando soma diverge do total da fatura**
  - Novo helper `_conciliar_total` em `extrator.py` comparando o
    `valor_total` que o parser extraiu do PDF com a soma das
    transações; imprime aviso amarelo quando há divergência além de
    R$ 0,01, ou quando o total não foi extraído (usa soma como
    fallback e avisa).
  - Removida a auto-correção silenciosa `valor_total = sum(...)` dos 3
    parsers (Ailos, Nubank, Banco do Brasil) — esse comportamento
    mascarava bugs reais de extração. Agora o `extrator.py` é a
    autoridade sobre conciliação.
  - **Bug real descoberto e corrigido**: a regex do parser Ailos
    capturava `"4,422.81."` (com ponto final), e `parse_valor_brl`
    devolvia `None` → o total da fatura nunca era extraído. Adicionado
    `.rstrip(".,")` no início de `parse_valor_brl` para tolerar
    pontuação trailing herdada de capturas amplas. Verificado também
    que o caso `"1.234.56"` (ponto como milhar + decimal, descrito no
    HANDOFF) **não ocorre** nos PDFs Ailos reais — o formato real é o
    americano `"1,234.56"`.
  - Validação: 4 cenários sintéticos (bate, total > soma, total < soma,
    total ausente) + execução real nos 2 PDFs sem avisos espúrios.

- **5.10 — Excel único acumulativo + pastas `entrada/`/`saida/`**
  - `extrator.py` reescrito: PDFs lidos por padrão de `entrada/`,
    resultado gravado sempre em `saida/gastometro.xlsx` (criadas
    automaticamente na primeira execução).
  - Excel agora é único e acumulativo. Cada execução adiciona apenas as
    faturas cujo nome de arquivo ainda não consta na aba `Informações`;
    duplicatas são ignoradas com mensagem clara no terminal.
  - 4 abas no resultado: `Informações` (uma linha por fatura),
    `Transações` (acumulativo com coluna `Arquivo`), `Resumo por
    Categoria` (recalculado) e nova aba `Resumo Mensal` (pivot
    referência × categoria, com totais por linha e coluna).
  - Argumentos posicionais ainda funcionam (PDF avulso ou pasta) e
    continuam gravando em `saida/gastometro.xlsx`.
  - README atualizado com o novo fluxo e instruções para re-processar
    uma fatura.
  - Validação: rodar duas vezes seguidas mantém 2 faturas e 58
    transações (R$ 5.355,35 = R$ 4.422,81 Ailos + R$ 932,54 Nubank);
    duplicar um PDF com outro nome adiciona corretamente como 3ª
    fatura.

- **1.4 / 7.1 — Remover dados pessoais de `PALAVRAS_NAO_TITULAR`**
  - Removidas as entradas `"ELIABE GAI 8449"` e `"ELIABE GAI 7316"` de
    `parsers/base.py`.
  - Análise feita antes de remover: o regex
    `[A-ZÁÉÍÓÚÂÊÔÃÕÇ]{2,}` aplicado token a token já descarta linhas que
    contenham finais de cartão (qualquer dígito), então essas entradas
    eram funcionalmente inúteis (nunca consultadas) e apenas vazavam
    dado pessoal.
  - Adicionado docstring detalhado em `detectar_titular` explicando as
    três camadas de filtro.
  - Validação: extração nos dois PDFs reais segue identificando titular
    `Eliabe Gai`, 48 transações Ailos (R$ 4.422,81) e 10 Nubank
    (R$ 932,54) — idêntico ao baseline do HANDOFF.

---

## Notas para evoluir este arquivo

- Ao iniciar uma melhoria: marcar `[~]` e adicionar `(em andamento)`.
- Ao concluir: marcar `[x]`, mover para a seção "Concluídas" com data e referência do commit.
- Ao propor algo novo: adicionar na seção temática certa, com prioridade e esforço.
- Sempre que rodar `git commit`, citar o número do item no corpo (ex: `feat: 5.1 consolida\u00e7\u00e3o multi-fatura`).
