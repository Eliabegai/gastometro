# Build da imagem e deploy no Swarm
$ErrorActionPreference = "Stop"
$root = $PSScriptRoot

Write-Host "Construindo imagem gastometro:latest..."
docker build -t gastometro:latest $root

if ($LASTEXITCODE -ne 0) {
    Write-Error "Build falhou"
}

# Carrega .env se existir
$envFile = Join-Path $root ".env"
if (Test-Path $envFile) {
    Get-Content $envFile | Where-Object { $_ -match '^\s*[^#=]+=.+' } | ForEach-Object {
        $parts = $_ -split '=', 2
        [Environment]::SetEnvironmentVariable($parts[0].Trim(), $parts[1].Trim(), 'Process')
    }
}

# Auth obrigatória em deploy público — sem isso qualquer um acessa os dados.
$authEnabled = if ($env:GASTOMETRO_AUTH_ENABLED) { $env:GASTOMETRO_AUTH_ENABLED } else { "false" }
$authEnabled = $authEnabled.Trim().ToLower()
$authOn = $authEnabled -in @("1", "true", "yes", "on")
$allowedEmails = if ($env:GASTOMETRO_ALLOWED_EMAILS) { $env:GASTOMETRO_ALLOWED_EMAILS } else { "" }
$allowedEmails = $allowedEmails.Trim()
$secretsFile = Join-Path $root ".streamlit\secrets.toml"

if (-not $authOn) {
    Write-Error @"
GASTOMETRO_AUTH_ENABLED nao esta true no .env.
Deploy publico sem login Google deixa os dados abertos para qualquer visitante.
Defina GASTOMETRO_AUTH_ENABLED=true e rode de novo.
"@
}
if (-not $allowedEmails) {
    Write-Error @"
GASTOMETRO_ALLOWED_EMAILS vazio no .env.
Defina pelo menos um e-mail autorizado (ex.: voce@gmail.com).
"@
}
if (-not (Test-Path $secretsFile)) {
    Write-Error @"
Arquivo $secretsFile nao encontrado.
Copie .streamlit/secrets.toml.example, preencha OAuth Google e tente de novo.
"@
}

Write-Host "Auth Google: ON ($allowedEmails)"

Write-Host "Deploying stack 'gastometro'..."
docker stack deploy -c (Join-Path $root "docker-compose.swarm.yml") gastometro

Write-Host ""
Write-Host "Status:"
docker stack services gastometro
