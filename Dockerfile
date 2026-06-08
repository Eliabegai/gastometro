# syntax=docker/dockerfile:1.7

# Imagem oficial multi-arch (amd64 + arm64): roda nativamente em Mac
# M-series, mini-PCs Linux x86 e Raspberry Pi 4/5. Sem precisar de
# buildx ou build manual.
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Pacotes nativos: curl pro healthcheck; tini pra encerrar processos
# zumbis (Streamlit spawn-a alguns). Limpo apt cache logo em seguida
# pra deixar a camada enxuta.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl tini \
    && rm -rf /var/lib/apt/lists/*

# Usuário não-root com UID/GID 1000 (default em Linux/Mac). Casa com o
# dono dos bind mounts em hosts comuns, evitando `chown` manual.
ARG APP_UID=1000
ARG APP_GID=1000
RUN groupadd --gid "${APP_GID}" app \
    && useradd --uid "${APP_UID}" --gid app --shell /bin/bash --create-home app

WORKDIR /app

# Stage 1 — deps. Copia só requirements.txt primeiro pra aproveitar
# cache: rebuild quando o código muda não reinstala libs.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Stage 2 — código. Copia tudo que ficou em .dockerignore após o
# corte (sem .venv, sem dados/, sem entrada/, sem tests/...).
COPY . .

# Pastas que serão montadas via bind mount mas precisam existir
# **dentro** do container caso o usuário não monte nada (smoke run).
# `chown` garante que o user `app` consegue escrever.
RUN mkdir -p /data /app/entrada /app/saida \
    && chown -R app:app /app /data

USER app

# Variáveis padrão. O docker-compose sobrescreve `GASTOMETRO_DADOS_DIR`
# pra apontar pra `/data` (bind mount), e timezone São Paulo.
#
# PYTHONPATH=/app garante que `from db.seed import ...` funcione quando
# o Streamlit carrega `app/streamlit_app.py` — Streamlit só adiciona o
# diretório do arquivo (`/app/app/`) ao sys.path, não o cwd. Sem isso,
# qualquer import de pacote-irmão (db, parsers, imports, export) quebra.
ENV PYTHONPATH=/app \
    GASTOMETRO_DADOS_DIR=/data \
    GASTOMETRO_BACKUPS_KEEP=30 \
    STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

EXPOSE 8501

# /healthz é a rota oficial do Streamlit pra liveness.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8501/_stcore/health || exit 1

# Tini PID 1 → encerra subprocessos do Streamlit limpo no `docker stop`.
# `python -m db.seed` antes do `streamlit` garante que o banco SQLite e
# as migrations já estejam aplicadas quando a UI subir — não precisamos
# esperar a primeira request humana pra criar o `.db`. Idempotente:
# no-op em subidas seguintes.
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["sh", "-c", \
     "python -m db.seed && exec streamlit run app/streamlit_app.py \
        --server.address=0.0.0.0 \
        --server.port=8501 \
        --server.headless=true"]
