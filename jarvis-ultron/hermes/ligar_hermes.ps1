# Liga o Hermes do Jarvis e testa se o Jarvis consegue falar com ele (Windows).
# Use quando o Jarvis disser "O Hermes esta desligado".

$ErrorActionPreference = "Continue"
$kit = Split-Path -Parent $MyInvocation.MyCommand.Path
$ultron = Split-Path -Parent $kit

function Ler-Env($caminho) {
    $valores = @{}
    if (Test-Path $caminho) {
        foreach ($linha in [System.IO.File]::ReadAllLines($caminho)) {
            if ($linha -match '^\s*([A-Za-z0-9_]+)\s*=\s*(.*)$') { $valores[$matches[1]] = $matches[2].Trim().Trim('"') }
        }
    }
    return $valores
}

function Testar-Hermes($url, $chave) {
    foreach ($endereco in @($url, "http://127.0.0.1:8642/p/jarvis", "http://127.0.0.1:8642")) {
        try {
            $r = Invoke-WebRequest -UseBasicParsing -TimeoutSec 5 -Uri ($endereco.TrimEnd('/') + "/v1/models") `
                 -Headers @{ Authorization = "Bearer $chave" }
            if ($r.StatusCode -eq 200) { return $endereco }
        } catch { }
    }
    return $null
}

$raizHermes = if ($env:HERMES_HOME) { $env:HERMES_HOME } else { Join-Path $env:LOCALAPPDATA "hermes" }
$hermes = Join-Path $raizHermes "bin\hermes.exe"
if (-not (Test-Path $hermes)) {
    $cmd = Get-Command hermes -ErrorAction SilentlyContinue
    if ($cmd) { $hermes = $cmd.Source }
}
if (-not (Test-Path $hermes)) {
    Write-Host "O Hermes nao foi encontrado. Rode o 'Instalar Hermes' primeiro." -ForegroundColor Red
    Read-Host "Aperte Enter para sair"; exit 1
}

$ultronEnv = Ler-Env (Join-Path $ultron ".env")
$chave = $ultronEnv["HERMES_API_KEY"]
$url = if ($ultronEnv["HERMES_API_URL"]) { $ultronEnv["HERMES_API_URL"] } else { "http://127.0.0.1:8642/p/jarvis" }
$raizEnv = Ler-Env (Join-Path $raizHermes ".env")
if (-not $chave -or $raizEnv["API_SERVER_ENABLED"] -ne "true") {
    Write-Host "Falta configurar a ligacao Jarvis-Hermes. Rode o 'Instalar Hermes' de novo e depois este." -ForegroundColor Yellow
    Read-Host "Aperte Enter para sair"; exit 1
}

Write-Host "Verificando o Hermes..." -ForegroundColor Cyan
$ok = Testar-Hermes $url $chave
if (-not $ok) {
    Write-Host "Ligando o servico do Hermes (se o Windows pedir permissao, clique em Sim)..."
    & $hermes gateway restart
    if ($LASTEXITCODE -ne 0) { & $hermes gateway start }
    foreach ($i in 1..12) { Start-Sleep -Seconds 5; $ok = Testar-Hermes $url $chave; if ($ok) { break } }
}

if ($ok) {
    Write-Host ""
    Write-Host "PRONTO: o Hermes esta ligado e o Jarvis consegue falar com ele." -ForegroundColor Green
    Write-Host "Pode fechar esta janela e perguntar ao Jarvis: 'quais sao os posts de hoje?'"
    Read-Host "Aperte Enter para fechar"
    exit 0
}

Write-Host ""
Write-Host "O servico automatico do Hermes nao ligou. Situacao do servico:" -ForegroundColor Yellow
& $hermes gateway status
Write-Host ""
Write-Host "Plano B: vou ligar o Hermes NESTA janela. Deixe ela aberta (pode minimizar) enquanto usa o Jarvis." -ForegroundColor Yellow
Write-Host "Tire um print desta tela e mande para o suporte, para arrumarmos o inicio automatico."
& $hermes gateway run
