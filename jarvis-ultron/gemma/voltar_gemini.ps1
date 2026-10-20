# Volta o cerebro do Jarvis Ultron para o Gemini (JARVIS_CEREBRO=gemini no .env).
# O Gemma 4 continua instalado: para usar de novo, rode o "Instalar Gemma 4".
$ErrorActionPreference = "Stop"
$kit = Split-Path -Parent $MyInvocation.MyCommand.Path
$envArq = Join-Path (Split-Path -Parent $kit) ".env"
$utf8 = New-Object System.Text.UTF8Encoding $false

function Ler-Linhas-Env {
    # Le o .env sem estragar acentos (a mesma regra do core\env_arquivo.py): tenta UTF-8 e, se o
    # arquivo nao for UTF-8 valido (o iniciador grava a cidade na pagina de codigo do console, cp850),
    # le como cp850. Quem grava depois grava sempre UTF-8 sem BOM.
    if (-not (Test-Path $envArq)) { return @() }
    $bytes = [System.IO.File]::ReadAllBytes($envArq)
    try { $texto = (New-Object System.Text.UTF8Encoding $false, $true).GetString($bytes) }
    catch { $texto = [System.Text.Encoding]::GetEncoding(850).GetString($bytes) }
    $texto = $texto.TrimStart([char]0xFEFF).TrimEnd([char]13, [char]10)
    if ($texto -eq "") { return @() }
    return ($texto -split "`r?`n")
}

try {
    # le tudo antes de gravar: se a leitura falhar, o .env fica como esta (nunca perde as chaves)
    $linhas = @(Ler-Linhas-Env | Where-Object { $_ -notmatch '^\s*JARVIS_CEREBRO\s*=' })
    $linhas = $linhas + 'JARVIS_CEREBRO="gemini"'
    [System.IO.File]::WriteAllText($envArq, (($linhas -join "`r`n") + "`r`n"), $utf8)
} catch {
    Write-Host ""
    Write-Host "Nao consegui mudar o arquivo .env (ele pode estar somente leitura ou aberto em outro" -ForegroundColor Red
    Write-Host "programa). O Luiz Conrado continua no Gemma 4. Feche o Luiz Conrado e rode o 'Voltar para o Gemini' de novo." -ForegroundColor Red
    Write-Host ("Detalhe: " + $_.Exception.Message)
    Read-Host "Aperte Enter para fechar"
    exit 1
}
Write-Host "O Luiz Conrado voltou a usar o Gemini como cerebro." -ForegroundColor Green
Write-Host "Se o Luiz Conrado estiver aberto (ou no icone perto do relogio), feche de verdade: botao direito"
Write-Host "no icone > Sair do Luiz Conrado. Depois abra o 'Iniciar Jarvis Ultron'."
Write-Host "Para usar o Gemma 4 de novo, rode o 'Instalar Gemma 4' (ele pula o que ja esta pronto)."
Read-Host "Aperte Enter para fechar"
