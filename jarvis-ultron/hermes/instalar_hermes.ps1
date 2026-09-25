# Instalador do Hermes Agent para o Jarvis Ultron (Windows).
# Cria o perfil "jarvis" do Hermes com: OpenRouter, sub-agentes, habilidades do perfil de atleta,
# conectores Metricool e Meta, voz ElevenLabs, trava de aprovacao e a rotina diaria das 8h.

$ErrorActionPreference = "Stop"
$kit = Split-Path -Parent $MyInvocation.MyCommand.Path     # ...\jarvis-ultron\hermes
$ultron = Split-Path -Parent $kit                           # ...\jarvis-ultron
$utf8 = New-Object System.Text.UTF8Encoding $false

function Titulo($texto) {
    Write-Host ""
    Write-Host "============================================================" -ForegroundColor Cyan
    Write-Host " $texto" -ForegroundColor Cyan
    Write-Host "============================================================" -ForegroundColor Cyan
}

function Gravar($caminho, $texto) {
    [System.IO.File]::WriteAllText($caminho, $texto, $utf8)
}

function Ler-Env($caminho) {
    $valores = [ordered]@{}
    if (Test-Path $caminho) {
        foreach ($linha in [System.IO.File]::ReadAllLines($caminho)) {
            if ($linha -match '^\s*([A-Za-z0-9_]+)\s*=\s*(.*)$') {
                $valores[$matches[1]] = $matches[2].Trim().Trim('"')
            }
        }
    }
    return $valores
}

function Gravar-Env($caminho, $valores) {
    $linhas = foreach ($chave in $valores.Keys) { "$chave=`"$($valores[$chave])`"" }
    Gravar $caminho (($linhas -join "`r`n") + "`r`n")
}

function Atualizar-Path {
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
                [System.Environment]::GetEnvironmentVariable("Path", "User") + ";" + $env:Path
}

function Garantir-Git {
    # O Hermes precisa do Git (Git Bash) no Windows. O instalador dele tenta baixar uma versao
    # portatil, mas o antivirus as vezes bloqueia a extracao. Instalar o Git oficial resolve.
    if (Get-Command git -ErrorAction SilentlyContinue) { return $true }
    Write-Host "O Hermes precisa do Git. Vou instalar o Git oficial pelo Windows (winget)..."
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        winget install --id Git.Git -e --source winget --accept-source-agreements --accept-package-agreements
        Atualizar-Path
        foreach ($caminho in "$env:ProgramFiles\Git\cmd", "$env:LOCALAPPDATA\Programs\Git\cmd") {
            if ((Test-Path $caminho) -and ($env:Path -notlike "*$caminho*")) { $env:Path = "$caminho;$env:Path" }
        }
    }
    if (Get-Command git -ErrorAction SilentlyContinue) { return $true }
    Write-Host ""
    Write-Host "Nao consegui instalar o Git automaticamente." -ForegroundColor Yellow
    Write-Host "Vai abrir o site do Git: baixe, instale (pode apertar Next em tudo) e depois"
    Write-Host "abra o 'Instalar Hermes' de novo."
    Start-Process "https://git-scm.com/download/win"
    return $false
}

function Achar-Hermes {
    $comando = Get-Command hermes -ErrorAction SilentlyContinue
    if ($comando) { return $comando.Source }
    foreach ($nome in "hermes.exe", "hermes.cmd", "hermes.bat") {
        $caminho = Join-Path $env:LOCALAPPDATA "hermes\bin\$nome"
        if (Test-Path $caminho) { return $caminho }
    }
    return $null
}

# ---------------------------------------------------------------- 1. Hermes instalado?
Titulo "1/7  Hermes Agent"
$hermes = Achar-Hermes
if (-not $hermes) {
    if (-not (Garantir-Git)) {
        Read-Host "Aperte Enter para sair"
        exit 1
    }
    Write-Host "O Hermes Agent (Nous Research) ainda nao esta instalado."
    Write-Host "Vou rodar o instalador oficial: iex (irm https://hermes-agent.nousresearch.com/install.ps1)"
    Read-Host "Aperte Enter para instalar (ou feche esta janela para cancelar)"
    try {
        Invoke-Expression (Invoke-RestMethod "https://hermes-agent.nousresearch.com/install.ps1")
    } catch {
        Write-Host "O instalador do Hermes parou com erro: $_" -ForegroundColor Yellow
    }
    Atualizar-Path
    $hermes = Achar-Hermes
    if (-not $hermes) {
        Write-Host ""
        Write-Host "A instalacao do Hermes NAO terminou (veja as mensagens em vermelho acima)." -ForegroundColor Red
        Write-Host "Tire um print desta janela e mande para o suporte. Depois de resolver, abra o"
        Write-Host "'Instalar Hermes' de novo: ele continua de onde parou."
        Read-Host "Aperte Enter para sair"
        exit 1
    }
}
Write-Host "Hermes encontrado: $hermes" -ForegroundColor Green

# ---------------------------------------------------------------- 2. Perfil "jarvis"
Titulo "2/7  Perfil 'jarvis'"
$raizHermes = if ($env:HERMES_HOME) { $env:HERMES_HOME } else { Join-Path $env:LOCALAPPDATA "hermes" }
$perfil = Join-Path $raizHermes "profiles\jarvis"
if (-not (Test-Path $perfil)) {
    & $hermes profile create jarvis --description "Jarvis Ultron: orquestrador do Erton (redes do atleta, anuncios, navegador)."
}
if (-not (Test-Path $perfil)) { New-Item -ItemType Directory -Force $perfil | Out-Null }
$pastaJarvis = Join-Path $perfil "jarvis"
New-Item -ItemType Directory -Force (Join-Path $pastaJarvis "posts") | Out-Null
$pastaJarvisBarra = $pastaJarvis -replace '\\', '/'
Write-Host "Perfil: $perfil" -ForegroundColor Green

# ---------------------------------------------------------------- 3. Personalidade, habilidades e trava
Titulo "3/7  Habilidades, sub-agentes e trava de aprovacao"
Copy-Item (Join-Path $kit "SOUL.md") (Join-Path $perfil "SOUL.md") -Force
$destinoSkills = Join-Path $perfil "skills\jarvis"
New-Item -ItemType Directory -Force $destinoSkills | Out-Null
Copy-Item (Join-Path $kit "skills\jarvis\*") $destinoSkills -Recurse -Force
Get-ChildItem $destinoSkills -Recurse -Filter "SKILL.md" | ForEach-Object {
    $texto = [System.IO.File]::ReadAllText($_.FullName)
    Gravar $_.FullName ($texto.Replace("__PASTA_JARVIS__", $pastaJarvisBarra))
}
$pastaGancho = Join-Path $perfil "hooks-jarvis"
New-Item -ItemType Directory -Force $pastaGancho | Out-Null
Copy-Item (Join-Path $kit "hooks\aprovacao_jarvis.py") $pastaGancho -Force
$gancho = (Join-Path $pastaGancho "aprovacao_jarvis.py") -replace '\\', '/'
Write-Host "5 habilidades instaladas e trava de aprovacao ligada." -ForegroundColor Green

# ---------------------------------------------------------------- 4. Chaves
Titulo "4/7  Chaves (OpenRouter e ElevenLabs)"
$envHermes = Join-Path $perfil ".env"
$chaves = Ler-Env $envHermes
if (-not $chaves["OPENROUTER_API_KEY"]) {
    Write-Host "Chave do OpenRouter (o cerebro dos agentes):"
    Write-Host "  1. Vai abrir o site do OpenRouter. Entre com a sua conta do Google."
    Write-Host "  2. Clique em 'Create Key', de o nome Jarvis e copie a chave (comeca com sk-or-)."
    Start-Process "https://openrouter.ai/keys"
    do { $valor = Read-Host "Cole a chave do OpenRouter e aperte Enter" } while (-not $valor.Trim())
    $chaves["OPENROUTER_API_KEY"] = $valor.Trim()
}
if (-not $chaves.Contains("ELEVENLABS_API_KEY")) {
    Write-Host ""
    Write-Host "Chave da ElevenLabs (voz do Jarvis). Opcional: aperte Enter para pular."
    Write-Host "  No site: clique no seu nome > API Keys > Create API Key."
    Start-Process "https://elevenlabs.io/app/settings/api-keys"
    $chaves["ELEVENLABS_API_KEY"] = (Read-Host "Cole a chave da ElevenLabs (ou Enter para pular)").Trim()
    Write-Host "  ID da voz: na ElevenLabs, abra Voices, escolha a voz e copie o 'Voice ID'."
    $voz = (Read-Host "Cole o ID da voz (ou Enter para usar a voz padrao)").Trim()
    $chaves["JARVIS_VOZ_ELEVENLABS"] = if ($voz) { $voz } else { "pNInz6obpgDQGcFmaJgB" }
}
$chaves["API_SERVER_ENABLED"] = "true"
if (-not $chaves["API_SERVER_KEY"]) {
    $chaves["API_SERVER_KEY"] = -join ((48..57) + (97..122) | Get-Random -Count 40 | ForEach-Object { [char]$_ })
}
Gravar-Env $envHermes $chaves
Write-Host "Chaves salvas." -ForegroundColor Green

# ---------------------------------------------------------------- 5. config.yaml do perfil
Titulo "5/7  Configuracao (OpenRouter, Metricool, Meta, voz, trava)"
$configDestino = Join-Path $perfil "config.yaml"
if ((Test-Path $configDestino) -and -not (Test-Path "$configDestino.antes-do-jarvis")) {
    Copy-Item $configDestino "$configDestino.antes-do-jarvis"
}
$config = [System.IO.File]::ReadAllText((Join-Path $kit "config-jarvis.yaml"))
$config = $config.Replace("__GANCHO__", $gancho).Replace("__VOZ_ELEVENLABS__", $chaves["JARVIS_VOZ_ELEVENLABS"])
Gravar $configDestino $config
$permissoes = @{ approvals = @(@{ event = "pre_tool_call"; command = $gancho }) } | ConvertTo-Json -Depth 4
Gravar (Join-Path $perfil "shell-hooks-allowlist.json") $permissoes

# Liga o Jarvis Ultron ao Hermes (e a voz ElevenLabs, se houver chave).
$envUltron = Join-Path $ultron ".env"
$ultronEnv = Ler-Env $envUltron
$ultronEnv["HERMES_API_URL"] = "http://127.0.0.1:8642"
$ultronEnv["HERMES_API_KEY"] = $chaves["API_SERVER_KEY"]
$ultronEnv["HERMES_JARVIS_HOME"] = $perfil
if ($chaves["ELEVENLABS_API_KEY"]) {
    $ultronEnv["ELEVENLABS_API_KEY"] = $chaves["ELEVENLABS_API_KEY"]
    $ultronEnv["JARVIS_VOZ_ELEVENLABS"] = $chaves["JARVIS_VOZ_ELEVENLABS"]
}
Gravar-Env $envUltron $ultronEnv
Write-Host "Configuracao aplicada e Jarvis Ultron ligado ao Hermes." -ForegroundColor Green

# ---------------------------------------------------------------- 6. Conectores (login uma vez)
Titulo "6/7  Conectar Metricool e Meta (uma vez so)"
Write-Host "Vai abrir o navegador para voce autorizar o Metricool (entre na sua conta e clique em Permitir)."
Read-Host "Aperte Enter para conectar o Metricool"
& $hermes -p jarvis mcp login metricool
$meta = Read-Host "Conectar tambem os anuncios do Meta (Facebook/Instagram Ads)? Digite S ou N"
if ($meta -match '^[sS]') { & $hermes -p jarvis mcp login meta_ads }

# ---------------------------------------------------------------- 7. Rotina das 8h e inicio automatico
Titulo "7/7  Rotina diaria das 8h e inicio automatico"
$rotinas = (& $hermes -p jarvis cron list 2>&1 | Out-String)
if ($rotinas -notmatch "Rotina do atleta 8h") {
    & $hermes -p jarvis cron create "0 8 * * *" "Execute a rotina diaria do perfil de atleta do Erton." --skill rotina-atleta-8h --name "Rotina do atleta 8h" --deliver local
}
& $hermes -p jarvis gateway install
Write-Host ""
Write-Host "Pronto! O Hermes do Jarvis liga sozinho com o Windows e roda a rotina todo dia as 8h." -ForegroundColor Green
Write-Host "Abra o Jarvis Ultron e diga: 'Hey Jarvis, quais sao os posts de hoje?'"
Read-Host "Aperte Enter para fechar"
