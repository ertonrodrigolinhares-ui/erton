# Instalador do Claude Code como "chefe de tarefas" do Jarvis Ultron (Windows).
# 1) instala o Claude Code (instalador oficial da Anthropic, sem precisar de administrador);
# 2) prepara a pasta de trabalho Documentos\Jarvis Ultron\Claude com os agentes;
# 3) entra na sua conta do Claude (assinatura Pro/Max, sem chave de API);
# 4) testa e grava o caminho no .env do Jarvis.
# Pode rodar de novo quando quiser: o que ja estiver pronto e pulado.

$ErrorActionPreference = "Stop"
$kit = Split-Path -Parent $MyInvocation.MyCommand.Path     # ...\jarvis-ultron\claude
$ultron = Split-Path -Parent $kit                           # ...\jarvis-ultron
$envArq = Join-Path $ultron ".env"
$utf8 = New-Object System.Text.UTF8Encoding $false
$binDir = Join-Path $env:USERPROFILE ".local\bin"
$oficial = Join-Path $binDir "claude.exe"
$dados = Join-Path $env:USERPROFILE "Documents\Jarvis Ultron"
$pasta = Join-Path $dados "Claude"

function Titulo($texto) {
    Write-Host ""
    Write-Host "============================================================" -ForegroundColor Cyan
    Write-Host " $texto" -ForegroundColor Cyan
    Write-Host "============================================================" -ForegroundColor Cyan
}

function Sair-Com-Erro($texto) {
    Write-Host ""
    Write-Host $texto -ForegroundColor Red
    Write-Host "Tire um print desta janela e mande para o suporte. Depois e so abrir o"
    Write-Host "'Instalar Claude' de novo: ele continua de onde parou."
    Read-Host "Aperte Enter para sair"
    exit 1
}

function Definir-Env($chave, $valor) {
    # Troca (ou acrescenta) uma linha CHAVE="valor" no .env, sem mexer nas outras.
    $linhas = @()
    if (Test-Path $envArq) { $linhas = [System.IO.File]::ReadAllLines($envArq) }
    $nova = "$chave=`"$valor`""
    $achou = $false
    $saida = foreach ($linha in $linhas) {
        if ($linha -match "^\s*$chave\s*=") { $achou = $true; $nova } else { $linha }
    }
    if (-not $achou) { $saida = @($saida) + $nova }
    [System.IO.File]::WriteAllText($envArq, ((@($saida) -join "`r`n") + "`r`n"), $utf8)
}

function Atualizar-Path {
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
                [System.Environment]::GetEnvironmentVariable("Path", "User") + ";" + $env:Path
    if ($env:Path -notlike "*$binDir*") { $env:Path = "$binDir;$env:Path" }
}

function Achar-Claude {
    if (Test-Path $oficial) { return $oficial }
    Atualizar-Path
    foreach ($c in @(Get-Command claude -All -ErrorAction SilentlyContinue)) {
        # o Claude Desktop da Microsoft Store tambem se chama Claude.exe: esse nao serve
        if ($c.Source -and ($c.Source -notlike "*WindowsApps*")) { return $c.Source }
    }
    return $null
}

function Logado($exe) {
    $ErrorActionPreference = "Continue"
    & $exe auth status *> $null
    return ($LASTEXITCODE -eq 0)
}

# ---------------------------------------------------------------- 1
Titulo "1/4  Claude Code"
$exe = Achar-Claude
if ($exe) {
    Write-Host "Claude Code ja instalado: $exe" -ForegroundColor Green
} else {
    Write-Host "Instalando o Claude Code (instalador oficial da Anthropic)..."
    $ErrorActionPreference = "Continue"
    powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://claude.ai/install.ps1 | iex"
    $exe = Achar-Claude
    if (-not $exe -and (Get-Command winget -ErrorAction SilentlyContinue)) {
        Write-Host "Tentando pelo winget..."
        winget install --id Anthropic.ClaudeCode -e --accept-source-agreements --accept-package-agreements
        $exe = Achar-Claude
    }
    $ErrorActionPreference = "Stop"
    if (-not $exe) { Sair-Com-Erro "Nao consegui instalar o Claude Code. Verifique a internet e tente de novo." }
    Write-Host "Claude Code instalado: $exe" -ForegroundColor Green
}
# deixa o comando 'claude' disponivel nos proximos terminais
$pathUsuario = [Environment]::GetEnvironmentVariable("PATH", "User")
if ((Test-Path $oficial) -and ($pathUsuario -notlike "*$binDir*")) {
    [Environment]::SetEnvironmentVariable("PATH", "$pathUsuario;$binDir", "User")
}

# ---------------------------------------------------------------- 2
Titulo "2/4  Pasta de trabalho e agentes"
foreach ($sub in @("Entrada", "Relatorios", "Mudancas")) {
    New-Item -ItemType Directory -Force -Path (Join-Path $pasta $sub) | Out-Null
}
if (-not (Test-Path (Join-Path $pasta "CLAUDE.md"))) {
    Copy-Item (Join-Path $kit "CLAUDE.md") (Join-Path $pasta "CLAUDE.md")
}
$skills = Join-Path $pasta ".claude\skills"
New-Item -ItemType Directory -Force -Path $skills | Out-Null
$total = 0
foreach ($agente in @(Get-ChildItem (Join-Path $kit "skills") -Directory)) {
    $destino = Join-Path $skills $agente.Name
    New-Item -ItemType Directory -Force -Path $destino | Out-Null
    Copy-Item (Join-Path $agente.FullName "SKILL.md") (Join-Path $destino "SKILL.md") -Force
    $total++
}
Write-Host "Pasta: $pasta" -ForegroundColor Green
Write-Host "$total agentes prontos (os mesmos do Hermes, agora no Claude)." -ForegroundColor Green

# ---------------------------------------------------------------- 3
Titulo "3/4  Entrar na sua conta do Claude"
if (Logado $exe) {
    Write-Host "Ja esta conectado na sua conta." -ForegroundColor Green
} else {
    Write-Host "Agora o Claude Code vai abrir NESTA janela. Faca assim:" -ForegroundColor Yellow
    Write-Host "  1) Se ele perguntar se voce confia nesta pasta, escolha 'Yes'."
    Write-Host "  2) Escolha entrar com a conta do Claude (a mesma do claude.ai, plano Pro ou Max)"
    Write-Host "     e confirme no navegador que vai abrir."
    Write-Host "  3) Quando aparecer a caixa para digitar, escreva  /exit  e aperte Enter."
    Read-Host "Aperte Enter para abrir o Claude"
    Push-Location $pasta
    try { & $exe } finally { Pop-Location }
    if (-not (Logado $exe)) {
        Sair-Com-Erro "O Claude ainda nao esta conectado na sua conta. Abra o 'Instalar Claude' de novo e entre com a sua conta."
    }
    Write-Host "Conectado!" -ForegroundColor Green
}
if ([Environment]::GetEnvironmentVariable("ANTHROPIC_API_KEY", "User")) {
    Write-Host ""
    Write-Host "Aviso: existe uma ANTHROPIC_API_KEY nas variaveis do Windows. O Jarvis tira essa chave" -ForegroundColor Yellow
    Write-Host "quando chama o Claude (para usar a sua assinatura), mas o Claude aberto por voce no" -ForegroundColor Yellow
    Write-Host "terminal vai cobrar pela API. Se voce nao usa, apague essa variavel." -ForegroundColor Yellow
}

# ---------------------------------------------------------------- 4
Titulo "4/4  Teste"
$ErrorActionPreference = "Continue"
$env:ANTHROPIC_API_KEY = $null
Push-Location $pasta
try {
    $saida = ("Responda apenas com a palavra: pronto" | & $exe -p --output-format json --max-turns 1 --permission-mode dontAsk 2>$null | Out-String)
} finally { Pop-Location }
$ErrorActionPreference = "Stop"
try { $r = $saida | ConvertFrom-Json } catch { $r = $null }
if ($r -and -not $r.is_error) {
    Write-Host "O Claude respondeu: $($r.result)" -ForegroundColor Green
} else {
    $motivo = if ($r) { $r.result } else { $saida }
    Write-Host "O teste nao passou: $motivo" -ForegroundColor Yellow
    Write-Host "(Se for limite do plano, e so esperar; o resto ja esta instalado.)" -ForegroundColor Yellow
}
Definir-Env "JARVIS_CLAUDE_EXE" $exe

Write-Host ""
Write-Host "Pronto! Feche e abra o Jarvis de novo e diga, por exemplo:" -ForegroundColor Cyan
Write-Host "  'Jarvis, pede para o Claude pesquisar as novidades da reforma tributaria para holdings.'"
Write-Host "  'Jarvis, usa o agente proposta-comercial para o grupo tal.'"
Write-Host "Os relatorios ficam em: $pasta\Relatorios"
Read-Host "Aperte Enter para fechar"
