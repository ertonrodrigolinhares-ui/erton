# Liga o Gmail ao Hermes do Jarvis (Windows), para o agente de e-mail ler e sugerir respostas.
# Usa uma SENHA DE APP do Google (16 letras), nunca a sua senha normal. O codigo fica escondido.

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
    if (Test-Path $caminho) { Copy-Item $caminho "$caminho.antes-do-gmail" -Force }
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

$hermes = Achar-Hermes
if (-not $hermes) { Write-Host "O Hermes nao foi encontrado. Rode o 'Instalar Hermes' primeiro." -ForegroundColor Red; Sair 1 }
$raizHermes = if ($env:HERMES_HOME) { $env:HERMES_HOME } else { Join-Path $env:LOCALAPPDATA "hermes" }
$ultronEnv = Ler-Env (Join-Path $ultron ".env")
$perfil = $ultronEnv["HERMES_JARVIS_HOME"]
if (-not $perfil) { $perfil = Join-Path $raizHermes "profiles\jarvis" }
if (-not (Test-Path $perfil)) { Write-Host "Perfil 'jarvis' do Hermes nao encontrado. Rode o 'Instalar Hermes'." -ForegroundColor Red; Sair 1 }

Titulo "1/3  Senha de app do Google"
Write-Host "O Google NAO deixa usar a sua senha normal aqui. Voce precisa de uma 'senha de app' (16 letras)."
Write-Host ""
Write-Host "  1. Ligue a Verificacao em duas etapas na sua conta Google (se ainda nao tiver)."
Write-Host "  2. Vou abrir a pagina de senhas de app. Crie uma (escolha 'E-mail' ou 'Outro')."
Write-Host "  3. Copie o codigo de 16 letras que aparecer."
Write-Host ""
Start-Process "https://myaccount.google.com/apppasswords"
$email = ""
while ($email -notmatch '^[^@\s]+@[^@\s]+\.[^@\s]+$') {
    $email = (Read-Host "Digite o e-mail (ex.: voce@gmail.com)").Trim()
}
Write-Host "Agora cole a SENHA DE APP (16 letras). Ela fica escondida enquanto voce cola." -ForegroundColor Yellow
$segredo = Read-Host "Senha de app" -AsSecureString
$senha = ([System.Net.NetworkCredential]::new("", $segredo).Password).Replace(" ", "").Trim()
if ($senha.Length -lt 12) {
    Write-Host "Isso nao parece uma senha de app (deveria ter 16 letras). Rode de novo com o codigo certo." -ForegroundColor Red
    Sair 1
}

Titulo "2/3  Gravando no Hermes"
$imap = if ($email -match "(?i)@gmail\.|@googlemail\.") { "imap.gmail.com" }
        elseif ($email -match "(?i)@(outlook|hotmail|live)\.") { "outlook.office365.com" }
        else { Read-Host "Servidor IMAP do seu e-mail (ex.: imap.seuprovedor.com)" }
$smtp = if ($imap -eq "imap.gmail.com") { "smtp.gmail.com" }
        elseif ($imap -eq "outlook.office365.com") { "smtp.office365.com" }
        else { Read-Host "Servidor SMTP do seu e-mail (ex.: smtp.seuprovedor.com)" }

$envPerfil = Join-Path $perfil ".env"
$chaves = Ler-Env $envPerfil
$chaves["EMAIL_ADDRESS"] = $email
$chaves["EMAIL_PASSWORD"] = $senha
$chaves["EMAIL_IMAP_HOST"] = $imap
$chaves["EMAIL_SMTP_HOST"] = $smtp
$chaves["EMAIL_IMAP_PORT"] = "993"
$chaves["EMAIL_SMTP_PORT"] = "587"
Gravar-Env $envPerfil $chaves
Write-Host "E-mail $email gravado no Hermes (a senha fica so no seu PC)." -ForegroundColor Green

Titulo "3/3  Reiniciando o Hermes"
Write-Host "Se o Windows pedir permissao, clique em Sim..."
& $hermes gateway restart
if ($LASTEXITCODE -ne 0) { & $hermes gateway start }
Start-Sleep -Seconds 15

Write-Host ""
Write-Host "PRONTO!" -ForegroundColor Green
Write-Host "Ligue o agente 'email-triagem' no 'Ativar Agentes' (se ainda nao ligou)."
Write-Host "Depois peca ao Jarvis: 'Hey Jarvis, pede ao Hermes para separar meus e-mails'."
Write-Host ""
Write-Host "Seguranca: para cancelar esse acesso, apague a senha de app em" -ForegroundColor DarkGray
Write-Host "https://myaccount.google.com/apppasswords (nao mexe na sua conta)." -ForegroundColor DarkGray
Sair 0
