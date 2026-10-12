# Instalador do Gemma 4 como cerebro do Jarvis Ultron (Windows).
# Instala o Ollama, baixa o Gemma 4 no tamanho certo para a memoria do PC, instala a transcricao
# local (Whisper) e liga o Jarvis no Gemma (JARVIS_CEREBRO=gemma no .env).
# Pode rodar de novo quando quiser: o que ja estiver pronto e pulado.

$ErrorActionPreference = "Stop"
$kit = Split-Path -Parent $MyInvocation.MyCommand.Path     # ...\jarvis-ultron\gemma
$ultron = Split-Path -Parent $kit                           # ...\jarvis-ultron
$envArq = Join-Path $ultron ".env"
$utf8 = New-Object System.Text.UTF8Encoding $false
$apelido = "jarvis-gemma"

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
    Write-Host "'Instalar Gemma 4' de novo: ele continua de onde parou."
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
    $pasta = Join-Path $env:LOCALAPPDATA "Programs\Ollama"
    if ((Test-Path $pasta) -and ($env:Path -notlike "*$pasta*")) { $env:Path = "$pasta;$env:Path" }
}

function Ollama-Respondendo {
    try {
        Invoke-RestMethod -Uri "http://localhost:11434/api/tags" -TimeoutSec 3 | Out-Null
        return $true
    } catch { return $false }
}

function Versao-Ollama {
    $ErrorActionPreference = "Continue"   # avisos do ollama na saida de erro nao sao falha
    try {
        $texto = (& ollama --version 2>&1 | Out-String)
        if ($texto -match "(\d+)\.(\d+)\.(\d+)") { return [version]"$($matches[1]).$($matches[2]).$($matches[3])" }
    } catch {}
    return $null
}

# ---------------------------------------------------------------- 1. memoria do PC
Titulo "1/6  Memoria do computador"
$ramGB = [math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB)
Write-Host "Memoria (RAM): $ramGB GB"
if ($ramGB -ge 30) {
    $modelos = @("gemma4:26b", "gemma4:e4b", "gemma4:e2b"); $contexto = 16384
    Write-Host "Vou usar o Gemma 4 26B (o mais inteligente que cabe aqui; baixa uns 18 GB)." -ForegroundColor Green
} elseif ($ramGB -ge 14) {
    $modelos = @("gemma4:e4b", "gemma4:e2b"); $contexto = 12288
    Write-Host "Vou usar o Gemma 4 E4B (equilibrado; baixa uns 10 GB)." -ForegroundColor Green
} else {
    $modelos = @("gemma4:e2b"); $contexto = 8192
    Write-Host "Vou usar o Gemma 4 E2B (o mais leve)." -ForegroundColor Yellow
    if ($ramGB -lt 8) {
        Write-Host "Atencao: com menos de 8 GB o Gemma pode deixar o PC lento. O Gemini continua sendo" -ForegroundColor Yellow
        Write-Host "a melhor opcao neste computador. Feche esta janela se preferir nao continuar." -ForegroundColor Yellow
        Read-Host "Aperte Enter para continuar mesmo assim"
    }
}
$livreGB = [math]::Round((Get-PSDrive -Name ($env:LOCALAPPDATA.Substring(0, 1))).Free / 1GB)
Write-Host "Espaco livre no disco: $livreGB GB"
if ($livreGB -lt 25) {
    Write-Host "Pouco espaco livre. O Gemma precisa de 10 a 20 GB. Libere espaco se o download falhar." -ForegroundColor Yellow
}

# ---------------------------------------------------------------- 2. Ollama
Titulo "2/6  Ollama (o programa que roda o Gemma)"
Atualizar-Path
if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) {
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        Write-Host "Vai abrir o site do Ollama: baixe, instale (Next em tudo) e abra este instalador de novo."
        Start-Process "https://ollama.com/download/windows"
        Read-Host "Aperte Enter para sair"
        exit 1
    }
    Write-Host "Instalando o Ollama pelo Windows (winget). Se o Windows pedir permissao, aceite..."
    winget install --id Ollama.Ollama -e --source winget --accept-source-agreements --accept-package-agreements
    Atualizar-Path
    if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) {
        Sair-Com-Erro "O Ollama nao foi instalado."
    }
}
$versao = Versao-Ollama
if ($versao -and $versao -lt [version]"0.22.0") {
    Write-Host "Ollama $versao e antigo para o Gemma 4. Atualizando..."
    winget upgrade --id Ollama.Ollama -e --source winget --accept-source-agreements --accept-package-agreements
    Atualizar-Path
}
Write-Host "Ollama: $(Versao-Ollama)" -ForegroundColor Green

# O modelo fica carregado na memoria por 30 min depois do ultimo uso (responde rapido).
[System.Environment]::SetEnvironmentVariable("OLLAMA_KEEP_ALIVE", "30m", "User")
$env:OLLAMA_KEEP_ALIVE = "30m"

# ---------------------------------------------------------------- 3. ligar o Ollama
Titulo "3/6  Ligando o Ollama"
if (-not (Ollama-Respondendo)) {
    Start-Process -FilePath "ollama" -ArgumentList "serve" -WindowStyle Hidden
    $limite = (Get-Date).AddSeconds(40)
    while (-not (Ollama-Respondendo) -and (Get-Date) -lt $limite) { Start-Sleep -Seconds 1 }
}
if (-not (Ollama-Respondendo)) { Sair-Com-Erro "O Ollama nao ligou." }
Write-Host "Ollama ligado." -ForegroundColor Green

# ---------------------------------------------------------------- 4. baixar o Gemma 4
Titulo "4/6  Baixando o Gemma 4 (pode demorar bastante na primeira vez)"
$ErrorActionPreference = "Continue"
$instalados = (& ollama list 2>&1 | Out-String)
$ErrorActionPreference = "Stop"
$escolhido = $null
foreach ($m in $modelos) {
    if ($instalados -match [regex]::Escape($m)) { $escolhido = $m; Write-Host "$m ja estava baixado."; break }
    Write-Host "Baixando $m..."
    & ollama pull $m
    if ($LASTEXITCODE -eq 0) { $escolhido = $m; break }
    Write-Host "Nao consegui baixar $m. Tentando um menor..." -ForegroundColor Yellow
}
if (-not $escolhido) { Sair-Com-Erro "Nao consegui baixar o Gemma 4 (confira a internet e o espaco em disco)." }
Write-Host "Gemma 4 pronto: $escolhido" -ForegroundColor Green

# ---------------------------------------------------------------- 5. perfil do Jarvis no Ollama
Titulo "5/6  Preparando o Gemma para o Jarvis"
# Memoria de conversa maior que o padrao (4 mil), senao as ferramentas do Jarvis nao cabem.
$modelfile = Join-Path $kit "Modelfile"
[System.IO.File]::WriteAllText($modelfile, "FROM $escolhido`nPARAMETER num_ctx $contexto`n", $utf8)
& ollama create $apelido -f $modelfile
if ($LASTEXITCODE -ne 0) { Sair-Com-Erro "Nao consegui preparar o modelo $apelido." }
Write-Host "Modelo '$apelido' criado (base: $escolhido, memoria de conversa: $contexto)." -ForegroundColor Green

Write-Host "Testando o Gemma (a primeira resposta demora porque ele carrega na memoria)..."
try {
    $corpo = @{ model = $apelido; stream = $false
                messages = @(@{ role = "user"; content = "Responda apenas: Jarvis pronto." }) } | ConvertTo-Json -Depth 5
    $r = Invoke-RestMethod -Uri "http://localhost:11434/api/chat" -Method Post -Body $corpo `
         -ContentType "application/json; charset=utf-8" -TimeoutSec 600
    Write-Host "Gemma respondeu: $($r.message.content)" -ForegroundColor Green
} catch {
    Write-Host "O teste nao respondeu a tempo ($($_.Exception.Message)). O Jarvis tenta de novo ao abrir." -ForegroundColor Yellow
}

# ---------------------------------------------------------------- 6. ouvir sem internet
Titulo "6/6  Transcricao da sua voz no proprio PC (Whisper)"
$py = Join-Path $ultron ".venv\Scripts\python.exe"
$whisperOk = $false
if (Test-Path $py) {
    Write-Host "Instalando o Whisper local..."
    & $py -m pip install --disable-pip-version-check faster-whisper
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Baixando o modelo de voz em portugues (uns 500 MB, so na primeira vez)..."
        & $py -c "from faster_whisper import WhisperModel; WhisperModel('small', device='cpu', compute_type='int8'); print('ok')"
        $whisperOk = ($LASTEXITCODE -eq 0)
    }
}
if ($whisperOk) {
    Write-Host "Whisper local pronto: sua voz e transcrita no PC." -ForegroundColor Green
} else {
    Write-Host "O Whisper local nao foi instalado agora." -ForegroundColor Yellow
    Write-Host "Abra o 'Iniciar Jarvis Ultron' uma vez (ele prepara o Jarvis) e depois rode este"
    Write-Host "instalador de novo. Ate la, a voz e transcrita pelo Groq (se a chave dele estiver no .env)."
}

# ---------------------------------------------------------------- ligar o Jarvis no Gemma
Definir-Env "JARVIS_CEREBRO" "gemma"
Definir-Env "JARVIS_GEMMA_MODELO" $apelido

Write-Host ""
Write-Host "Voz do Jarvis no modo Gemma:"
Write-Host "  N = voz da Microsoft pela internet (mais natural; o texto da resposta vai para a Microsoft)"
Write-Host "  S = voz do proprio Windows (mais robotica; nada sai do PC)"
$privada = (Read-Host "Quer a voz 100% privada? Digite S ou N (Enter = N)").Trim().ToUpper()
Definir-Env "JARVIS_VOZ_PRIVADA" ($(if ($privada -eq "S") { "1" } else { "0" }))

Write-Host ""
Write-Host "Pronto! O cerebro do Jarvis agora e o Gemma 4, rodando no seu computador." -ForegroundColor Green
Write-Host "Abra o 'Iniciar Jarvis Ultron'. Para voltar ao Gemini: 'Voltar para o Gemini'."
Read-Host "Aperte Enter para fechar"
