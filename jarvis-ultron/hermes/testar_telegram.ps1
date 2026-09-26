# Descobre por que o robo do Telegram nao responde e conserta o que der (Windows).
# Nunca mostra o codigo (token) do robo na tela.

$ErrorActionPreference = "Continue"
$kit = Split-Path -Parent $MyInvocation.MyCommand.Path     # ...\jarvis-ultron\hermes
$ultron = Split-Path -Parent $kit                           # ...\jarvis-ultron
$utf8 = New-Object System.Text.UTF8Encoding $false
$relatorio = New-Object System.Collections.Generic.List[string]

function Ok($texto)       { Write-Host "[OK] $texto" -ForegroundColor Green;  $relatorio.Add("[OK] $texto") }
function Problema($texto) { Write-Host "[PROBLEMA] $texto" -ForegroundColor Red; $relatorio.Add("[PROBLEMA] $texto") }
function Aviso($texto)    { Write-Host "[ATENCAO] $texto" -ForegroundColor Yellow; $relatorio.Add("[ATENCAO] $texto") }

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
    if (Test-Path $caminho) { Copy-Item $caminho "$caminho.antes-do-teste-telegram" -Force }
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

function Telegram($token, $metodo) {
    try {
        return Invoke-RestMethod -TimeoutSec 15 -Uri "https://api.telegram.org/bot$token/$metodo"
    } catch {
        $codigo = $null
        try { $codigo = [int]$_.Exception.Response.StatusCode } catch { }
        return [pscustomobject]@{ ok = $false; error_code = $codigo; description = "$($_.Exception.Message)" }
    }
}

Write-Host "Testando o robo do Telegram do Hermes..." -ForegroundColor Cyan
Write-Host ""

# ---------------------------------------------------------------- 1. Hermes e perfil
$hermes = Achar-Hermes
if (-not $hermes) { Problema "O Hermes nao esta instalado. Rode o 'Instalar Hermes'."; Read-Host "Enter para fechar"; exit 1 }
$raizHermes = if ($env:HERMES_HOME) { $env:HERMES_HOME } else { Join-Path $env:LOCALAPPDATA "hermes" }
$envUltronCaminho = Join-Path $ultron ".env"
$ultronEnv = Ler-Env $envUltronCaminho
$perfil = $ultronEnv["HERMES_JARVIS_HOME"]
if (-not $perfil) { $perfil = Join-Path $raizHermes "profiles\jarvis" }
if (-not (Test-Path $perfil)) { Problema "Perfil 'jarvis' do Hermes nao encontrado. Rode o 'Instalar Hermes'."; Read-Host "Enter para fechar"; exit 1 }
Ok "Hermes e perfil jarvis encontrados."

# ---------------------------------------------------------------- 2. Codigo do robo no lugar certo
$envPerfilCaminho = Join-Path $perfil ".env"
$perfilEnv = Ler-Env $envPerfilCaminho
$token = $perfilEnv["TELEGRAM_BOT_TOKEN"]
if (-not $token -and $ultronEnv["TELEGRAM_BOT_TOKEN"]) {
    # O codigo foi colocado no .env do Jarvis (lugar errado): leva para o Hermes.
    $token = $ultronEnv["TELEGRAM_BOT_TOKEN"]
    $perfilEnv["TELEGRAM_BOT_TOKEN"] = $token
    if ($ultronEnv["TELEGRAM_ALLOWED_USERS"] -and -not $perfilEnv["TELEGRAM_ALLOWED_USERS"]) {
        $perfilEnv["TELEGRAM_ALLOWED_USERS"] = $ultronEnv["TELEGRAM_ALLOWED_USERS"]
    }
    Gravar-Env $envPerfilCaminho $perfilEnv
    $ultronEnv.Remove("TELEGRAM_BOT_TOKEN")
    $ultronEnv.Remove("TELEGRAM_ALLOWED_USERS")
    Gravar-Env $envUltronCaminho $ultronEnv
    Aviso "O codigo do robo estava no .env do Jarvis (lugar errado). Mudei para o Hermes."
}
if (-not $token) {
    Problema "O Hermes nao tem o codigo do robo. Rode o 'Ligar Telegram' e cole o codigo (token)."
    Read-Host "Enter para fechar"; exit 1
}
Ok "Codigo do robo gravado no Hermes (termina em ...$($token.Substring([Math]::Max(0, $token.Length - 4))))."

$usuarios = $perfilEnv["TELEGRAM_ALLOWED_USERS"]
if (-not $usuarios) {
    Problema "Falta o seu numero de usuario. Sem ele o robo ignora todo mundo. Rode o 'Ligar Telegram' de novo."
} elseif ($usuarios -notmatch '^\d{5,15}(,\s*\d{5,15})*$') {
    Problema "O numero de usuario gravado nao parece certo ($usuarios). Deve ser so numeros, do @userinfobot."
} else {
    Ok "So o usuario $usuarios pode usar o robo."
}

# ---------------------------------------------------------------- 3. O Telegram aceita o codigo?
$eu = Telegram $token "getMe"
if (-not $eu.ok) {
    Problema "O Telegram recusou o codigo do robo ($($eu.description)). Crie um codigo novo no @BotFather (/token) e rode o 'Ligar Telegram'."
    Read-Host "Enter para fechar"; exit 1
}
Ok "Robo @$($eu.result.username) existe e o codigo funciona."

$gancho = Telegram $token "getWebhookInfo"
if ($gancho.ok -and $gancho.result.url) {
    Telegram $token "deleteWebhook" | Out-Null
    Aviso "O robo estava ligado a outro servico (webhook). Desliguei para o Hermes poder receber as mensagens."
}

# ---------------------------------------------------------------- 4. O Hermes esta ouvindo o robo?
# Mensagens que ninguem pegou ficam esperando no Telegram. Se o Hermes esta ouvindo, a fila fica vazia.
function Mensagens-Esperando {
    $info = Telegram $token "getWebhookInfo"
    if ($info.ok) { return [int]$info.result.pending_update_count }
    return -1
}

function Testar-Recebimento {
    Write-Host ""
    Write-Host "Agora abra o robo @$($eu.result.username) no Telegram e mande:  oi" -ForegroundColor Yellow
    Read-Host "Depois de mandar, aperte Enter aqui"
    Start-Sleep -Seconds 10
    return (Mensagens-Esperando)
}

$esperando = Testar-Recebimento
if ($esperando -gt 0) {
    Aviso "A mensagem nao foi pega pelo Hermes. Vou reiniciar o Hermes (se o Windows pedir permissao, clique em Sim)..."
    & $hermes gateway restart
    if ($LASTEXITCODE -ne 0) { & $hermes gateway start }
    Start-Sleep -Seconds 25
    $esperando = Testar-Recebimento
}
if ($esperando -gt 0) {
    # Um Hermes antigo (ligado antes do Telegram) pode ter ficado aberto e segurando a porta 8642:
    # o novo, que tem o Telegram, nao consegue ficar de pe. Fecha todos os Hermes e liga um so.
    Aviso "Ainda nao pegou. Vou fechar todos os Hermes que ficaram abertos e ligar um so, do zero..."
    & $hermes gateway stop
    Start-Sleep -Seconds 5
    $restos = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -and $_.CommandLine -match '(?i)hermes' -and $_.CommandLine -match '(?i)gateway' }
    foreach ($processo in $restos) {
        Stop-Process -Id $processo.ProcessId -Force -ErrorAction SilentlyContinue
    }
    if ($restos) { Aviso "Fechei $(@($restos).Count) Hermes que tinham ficado abertos." }
    Start-Sleep -Seconds 5
    & $hermes gateway start
    Start-Sleep -Seconds 30
    $esperando = Testar-Recebimento
}
if ($esperando -eq 0) {
    Ok "O Hermes pegou a sua mensagem. A resposta chega no Telegram em alguns segundos."
} elseif ($esperando -gt 0) {
    Problema "O Hermes nao esta recebendo as mensagens do robo. Veja as linhas do registro abaixo."
} else {
    Aviso "Nao consegui conferir a fila de mensagens do Telegram."
}

# ---------------------------------------------------------------- 5. Situacao do Hermes e registro
Write-Host ""
Write-Host "---- Situacao do servico do Hermes ----" -ForegroundColor Cyan
$situacao = (& $hermes gateway status 2>&1 | Out-String)
Write-Host $situacao
$relatorio.Add("---- hermes gateway status ----"); $relatorio.Add($situacao)

Write-Host "---- Ultimas linhas do registro sobre o Telegram ----" -ForegroundColor Cyan
$logs = @()
foreach ($pasta in @((Join-Path $raizHermes "logs"), (Join-Path $perfil "logs"))) {
    foreach ($nome in "gateway.log", "errors.log") {
        $arquivo = Join-Path $pasta $nome
        if (Test-Path $arquivo) {
            $logs += Get-Content $arquivo -Tail 400 | Where-Object { $_ -match '(?i)telegram' } | Select-Object -Last 12
        }
    }
}
$logs = $logs | ForEach-Object { $_ -replace [regex]::Escape($token), "<codigo-do-robo>" -replace '\d{6,}:[A-Za-z0-9_-]{30,}', "<codigo>" }
if ($logs) { $logs | ForEach-Object { Write-Host $_ } } else { Write-Host "(nenhuma linha sobre o Telegram no registro)" }
$relatorio.Add("---- registro (telegram) ----"); $logs | ForEach-Object { $relatorio.Add($_) }

$pastaDocs = Join-Path ([Environment]::GetFolderPath("MyDocuments")) "Jarvis Ultron"
New-Item -ItemType Directory -Force $pastaDocs | Out-Null
$saida = Join-Path $pastaDocs "teste-telegram.txt"
[System.IO.File]::WriteAllLines($saida, $relatorio, $utf8)
Write-Host ""
Write-Host "Relatorio salvo em: $saida" -ForegroundColor Cyan
Write-Host "Se ainda nao funcionar, mande um print desta janela para o suporte (o codigo do robo nao aparece aqui)."
Read-Host "Aperte Enter para fechar"
