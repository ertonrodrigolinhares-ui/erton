# Liga o Hermes do Jarvis ao Telegram (Windows).
# Depois disso voce manda tarefas para o Hermes pelo Telegram do celular, de qualquer lugar,
# enquanto o PC estiver ligado. So o SEU usuario do Telegram pode usar o robo.

$ErrorActionPreference = "Continue"
$kit = Split-Path -Parent $MyInvocation.MyCommand.Path     # ...\jarvis-ultron\hermes
$ultron = Split-Path -Parent $kit                           # ...\jarvis-ultron
$utf8 = New-Object System.Text.UTF8Encoding $false

function Titulo($texto) {
    Write-Host ""
    Write-Host "============================================================" -ForegroundColor Cyan
    Write-Host " $texto" -ForegroundColor Cyan
    Write-Host "============================================================" -ForegroundColor Cyan
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
    if (Test-Path $caminho) { Copy-Item $caminho "$caminho.antes-do-telegram" -Force }
    $linhas = foreach ($chave in $valores.Keys) { "$chave=`"$($valores[$chave])`"" }
    [System.IO.File]::WriteAllText($caminho, (($linhas -join "`r`n") + "`r`n"), $utf8)
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

function Sair($codigo) { Read-Host "Aperte Enter para fechar"; exit $codigo }

# ---------------------------------------------------------------- 0. Hermes instalado?
$hermes = Achar-Hermes
if (-not $hermes) {
    Write-Host "O Hermes nao foi encontrado. Rode o 'Instalar Hermes' primeiro." -ForegroundColor Red
    Sair 1
}
$raizHermes = if ($env:HERMES_HOME) { $env:HERMES_HOME } else { Join-Path $env:LOCALAPPDATA "hermes" }
$ultronEnv = Ler-Env (Join-Path $ultron ".env")
$perfil = $ultronEnv["HERMES_JARVIS_HOME"]
if (-not $perfil) { $perfil = Join-Path $raizHermes "profiles\jarvis" }
if (-not (Test-Path $perfil)) {
    Write-Host "O perfil 'jarvis' do Hermes nao foi encontrado. Rode o 'Instalar Hermes' primeiro." -ForegroundColor Red
    Sair 1
}

# ---------------------------------------------------------------- 1. Robo do Telegram
Titulo "1/4  Criar o seu robo no Telegram"
Write-Host "Vai abrir o @BotFather (o criador oficial de robos do Telegram)."
Write-Host "  1. Clique em INICIAR (ou mande /start)."
Write-Host "  2. Mande:  /newbot"
Write-Host "  3. Nome do robo: por exemplo  Jarvis Hermes"
Write-Host "  4. Usuario do robo: precisa terminar em 'bot', por exemplo  jarvis_erton_bot"
Write-Host "  5. Ele responde com um CODIGO (token), parecido com  123456789:ABCdef..."
Write-Host "NUNCA mande esse codigo para ninguem." -ForegroundColor Yellow
Start-Process "https://t.me/BotFather"
$token = ""
$nomeRobo = ""
while (-not $nomeRobo) {
    $token = (Read-Host "Cole aqui o codigo (token) que o BotFather mandou").Trim().Trim('"')
    if ($token -notmatch '^\d{5,}:[A-Za-z0-9_-]{30,}$') {
        Write-Host "Esse codigo nao parece certo. Copie a linha inteira depois de 'Use this token'." -ForegroundColor Yellow
        continue
    }
    try {
        $resposta = Invoke-RestMethod -TimeoutSec 15 -Uri "https://api.telegram.org/bot$token/getMe"
        if ($resposta.ok) { $nomeRobo = $resposta.result.username }
    } catch {
        Write-Host "O Telegram recusou esse codigo. Confira se copiou inteiro e tente de novo." -ForegroundColor Yellow
    }
}
Write-Host "Robo encontrado: @$nomeRobo" -ForegroundColor Green

# ---------------------------------------------------------------- 2. Seu numero de usuario
Titulo "2/4  O seu numero de usuario do Telegram"
Write-Host "So VOCE vai poder usar o robo. Para isso ele precisa do seu numero de usuario."
Write-Host "Vai abrir o @userinfobot: clique em INICIAR e ele responde 'Id: 123456789'."
Start-Process "https://t.me/userinfobot"
$usuario = ""
while ($usuario -notmatch '^\d{5,15}$') {
    $usuario = (Read-Host "Cole aqui o numero (so os numeros do 'Id')").Trim()
}

# ---------------------------------------------------------------- 3. Gravar no perfil jarvis
Titulo "3/4  Ligando o Telegram ao Hermes do Jarvis"
$envPerfil = Join-Path $perfil ".env"
$chaves = Ler-Env $envPerfil
$chaves["TELEGRAM_BOT_TOKEN"] = $token
$chaves["TELEGRAM_ALLOWED_USERS"] = $usuario
Gravar-Env $envPerfil $chaves
# O mesmo robo nao pode estar em dois perfis ao mesmo tempo (o Telegram recusa).
$envRaiz = Join-Path $raizHermes ".env"
$raizEnv = Ler-Env $envRaiz
if ($raizEnv.Contains("TELEGRAM_BOT_TOKEN") -and $raizEnv["TELEGRAM_BOT_TOKEN"] -eq $token) {
    $raizEnv.Remove("TELEGRAM_BOT_TOKEN")
    Gravar-Env $envRaiz $raizEnv
}
Write-Host "Telegram gravado no perfil jarvis (so o usuario $usuario pode usar)." -ForegroundColor Green

Write-Host "Reiniciando o Hermes (se o Windows pedir permissao, clique em Sim)..."
& $hermes gateway restart
if ($LASTEXITCODE -ne 0) { & $hermes gateway start }
Start-Sleep -Seconds 15

try {
    $texto = "Jarvis Ultron: Telegram conectado ao Hermes. Mande 'oi' aqui para testar."
    Invoke-RestMethod -TimeoutSec 15 -Method Post -Uri "https://api.telegram.org/bot$token/sendMessage" `
        -Body @{ chat_id = $usuario; text = $texto } | Out-Null
    Write-Host "Mandei uma mensagem de teste para voce no Telegram." -ForegroundColor Green
} catch {
    Write-Host "Nao consegui mandar a mensagem de teste. Abra o robo @$nomeRobo no Telegram e clique em INICIAR." -ForegroundColor Yellow
}

# ---------------------------------------------------------------- 4. PC acordado (opcional)
Titulo "4/4  Deixar o PC acordado (opcional)"
Write-Host "O Hermes so responde com o PC LIGADO. Se o PC 'dormir', o robo para de responder."
$acordado = (Read-Host "Quer que o PC nunca durma quando estiver na TOMADA? (S/N)").Trim().ToUpper()
if ($acordado -eq "S") {
    powercfg /change standby-timeout-ac 0
    Write-Host "Pronto: na tomada o PC nao dorme mais (a tela ainda pode apagar)." -ForegroundColor Green
}

Write-Host ""
Write-Host "PRONTO!" -ForegroundColor Green
Write-Host "No Telegram, abra o robo @$nomeRobo, clique em INICIAR e mande: oi"
Write-Host "Depois peca tarefas, por exemplo: 'quais sao os melhores horarios para postar esta semana?'"
Write-Host "Publicar, agendar ou mexer em anuncios continua precisando do seu 'ok' dado ao Jarvis."
Sair 0
