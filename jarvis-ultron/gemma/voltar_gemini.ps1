# Volta o cerebro do Jarvis Ultron para o Gemini (JARVIS_CEREBRO=gemini no .env).
# O Gemma 4 continua instalado: para usar de novo, rode o "Instalar Gemma 4".
$kit = Split-Path -Parent $MyInvocation.MyCommand.Path
$envArq = Join-Path (Split-Path -Parent $kit) ".env"
$utf8 = New-Object System.Text.UTF8Encoding $false
$linhas = @()
if (Test-Path $envArq) { $linhas = [System.IO.File]::ReadAllLines($envArq) | Where-Object { $_ -notmatch '^\s*JARVIS_CEREBRO\s*=' } }
$linhas = @($linhas) + 'JARVIS_CEREBRO="gemini"'
[System.IO.File]::WriteAllText($envArq, (($linhas -join "`r`n") + "`r`n"), $utf8)
Write-Host "O Jarvis voltou a usar o Gemini como cerebro. Abra o 'Iniciar Jarvis Ultron'." -ForegroundColor Green
Write-Host "Para usar o Gemma 4 de novo, rode o 'Instalar Gemma 4' (ele pula o que ja esta pronto)."
Read-Host "Aperte Enter para fechar"
