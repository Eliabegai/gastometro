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

- [ ] **1.2 — Inferência de ano errada em parcelas antigas** — P1 / S
  - `parsers/ailos.py::_ano_do_vencimento` (idem nubank/banco_brasil) aplica o ano do vencimento a todas as transações.
  - Caso de teste: `MAPFRE SEGUROS 14 JAN` em fatura de maio.
  - Regra sugerida: se mês da transação > mês do vencimento, ano = ano_vencimento - 1.

- [x] **1.3 — Avisar quando soma diverge do total da fatura** — P1 / XS
  - Concluído em 22/05/2026 (ver "Concluídas").

- [x] **1.4 — Remover dados pessoais de `PALAVRAS_NAO_TITULAR`** — P0 / XS
  - Concluído em 22/05/2026 (ver "Concluídas").

- [ ] **1.5 — `import pandas` dentro de função (3 lugares)** — P3 / XS
  - `parsers/ailos.py:126`, `parsers/nubank.py:117`, `parsers/banco_brasil.py:100`.
  - Trocar por `datetime.date.today().year` (stdlib).

- [ ] **1.6 — PDF lido duas vezes (detecção + extração)** — P2 / S
  - `parsers/__init__.py::detectar_banco` + `extrair_fatura` chamam `_ler_texto` independentemente.
  - Refatorar para abrir o PDF uma vez e reaproveitar o texto.

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

- [ ] **2.3 — Aprendizado a partir do usuário** — P2 / M
  - Criar `categorias_usuario.json` (não versionado), mapeando descrição normalizada → categoria.
  - `categorizar()` consulta esse arquivo antes do dicionário fixo.
  - Bônus: ler de volta um Excel já corrigido manualmente e auto-alimentar o arquivo.

- [ ] **2.4 — Visibilidade do "Outros Gastos"** — P2 / S
  - No fim de cada execução, imprimir top-10 descrições não categorizadas (com valor agregado), pra evoluir o dicionário.

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

- [ ] **4.2 — Mover `_ano_do_vencimento` para `parsers/base.py`** — P3 / XS
  - Triplicada hoje.

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
