# Instala (ou remove) os agentes do projeto "agency-agents" no Claude Code deste PC.
# Fonte: https://github.com/msitarzewski/agency-agents (licenca MIT).
# A versao fica fixa (VERSAO abaixo): assim o que entra no seu PC e o que foi conferido.
# Uso: Instalar agentes Agency.bat / Remover agentes Agency.bat
param([switch]$Remover)

$ErrorActionPreference = "Stop"
$VERSAO = "652b2692f8d8ec2b1f1a38e559073e287dfdc469"
$DIVISOES = @("academic", "design", "engineering", "finance", "game-development", "gis", "healthcare",
              "marketing", "paid-media", "product", "project-management", "research", "sales", "security",
              "spatial-computing", "specialized", "support", "testing")

# Pasta de agentes do Claude Code (vale para todos os projetos). Os agentes ficam numa subpasta
# "agency" para nao misturar com os seus e para poder remover tudo de uma vez.
if ($env:CLAUDE_CONFIG_DIR) { $base = $env:CLAUDE_CONFIG_DIR } else { $base = Join-Path $HOME ".claude" }
$destino = Join-Path (Join-Path $base "agents") "agency"

if ($Remover) {
    if (Test-Path $destino) {
        Remove-Item $destino -Recurse -Force
        Write-Host "Pronto: os agentes Agency foram removidos de $destino"
    } else {
        Write-Host "Nada para remover: a pasta $destino nao existe."
    }
    exit 0
}

$temp = Join-Path ([IO.Path]::GetTempPath()) ("agency-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $temp | Out-Null
try {
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    $zip = Join-Path $temp "agency.zip"
    Write-Host "Baixando os agentes do GitHub..."
    Invoke-WebRequest -UseBasicParsing -Uri "https://github.com/msitarzewski/agency-agents/archive/$VERSAO.zip" -OutFile $zip
    Write-Host "Extraindo..."
    Expand-Archive -Path $zip -DestinationPath $temp -Force
    $raiz = Join-Path $temp "agency-agents-$VERSAO"
    if (-not (Test-Path $raiz)) { throw "O arquivo baixado nao tem a pasta esperada." }

    # Instalacao limpa: tira a versao anterior (so a subpasta agency, nunca os seus agentes)
    if (Test-Path $destino) { Remove-Item $destino -Recurse -Force }
    New-Item -ItemType Directory -Path $destino -Force | Out-Null

    $total = 0
    foreach ($div in $DIVISOES) {
        $origem = Join-Path $raiz $div
        if (-not (Test-Path $origem)) { continue }
        $origem = (Get-Item $origem).FullName  # mesmo formato de caminho que o Get-ChildItem devolve
        Get-ChildItem -Path $origem -Recurse -Filter "*.md" | ForEach-Object {
            $relativo = $_.FullName.Substring($origem.Length).TrimStart('\', '/')
            $alvo = Join-Path (Join-Path $destino $div) $relativo
            New-Item -ItemType Directory -Path (Split-Path $alvo) -Force | Out-Null
            Copy-Item $_.FullName $alvo -Force
            $total++
        }
    }
    Copy-Item (Join-Path $raiz "LICENSE") (Join-Path $destino "LICENSE.txt") -Force

    Write-Host ""
    Write-Host "Pronto: $total agentes instalados em $destino"
    Write-Host ""
    Write-Host "Como usar:"
    Write-Host " 1. Feche e abra o Claude Code de novo."
    Write-Host " 2. Peca pelo nome, por exemplo: use o agente Code Reviewer para revisar meu codigo"
    Write-Host "    ou digite @ e escolha o agente na lista."
    Write-Host ""
    Write-Host "Os agentes sao em ingles e seguem regras dos EUA (impostos, leis)."
    Write-Host "Para remover todos: Remover agentes Agency.bat"
} finally {
    Remove-Item $temp -Recurse -Force -ErrorAction SilentlyContinue
}
