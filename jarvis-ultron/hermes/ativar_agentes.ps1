# Ativa (ou desativa) os agentes guardados em hermes\agentes-futuros no perfil "jarvis" do Hermes.

$ErrorActionPreference = "Stop"
$kit = Split-Path -Parent $MyInvocation.MyCommand.Path
$guardados = Join-Path $kit "agentes-futuros"
$raizHermes = if ($env:HERMES_HOME) { $env:HERMES_HOME } else { Join-Path $env:LOCALAPPDATA "hermes" }
$ativos = Join-Path $raizHermes "profiles\jarvis\skills\jarvis"

if (-not (Test-Path $ativos)) {
    Write-Host "O Hermes do Jarvis ainda nao esta instalado. Rode o 'Instalar Hermes' primeiro." -ForegroundColor Yellow
    Read-Host "Aperte Enter para sair"
    exit 1
}

$agentes = @(Get-ChildItem $guardados -Directory | Sort-Object Name)
Write-Host ""
Write-Host "Agentes guardados:" -ForegroundColor Cyan
for ($i = 0; $i -lt $agentes.Count; $i++) {
    $nome = $agentes[$i].Name
    $estado = if (Test-Path (Join-Path $ativos $nome)) { "[LIGADO]   " } else { "[desligado]" }
    $linha = (Get-Content (Join-Path $agentes[$i].FullName "SKILL.md") | Where-Object { $_ -like "description:*" } | Select-Object -First 1)
    $descricao = if ($linha) { $linha.Substring(12).Trim() } else { "" }
    Write-Host ("{0,2}. {1} {2}" -f ($i + 1), $estado, $nome)
    Write-Host ("       {0}" -f $descricao) -ForegroundColor DarkGray
}
Write-Host ""
$resposta = Read-Host "Digite os numeros para LIGAR ou DESLIGAR (ex.: 1 4 10), ou Enter para sair"
foreach ($parte in ($resposta -split "[ ,;]+" | Where-Object { $_ })) {
    $n = 0
    if (-not [int]::TryParse($parte, [ref]$n) -or $n -lt 1 -or $n -gt $agentes.Count) { continue }
    $agente = $agentes[$n - 1]
    $destino = Join-Path $ativos $agente.Name
    if (Test-Path $destino) {
        Remove-Item $destino -Recurse -Force
        Write-Host "Desligado: $($agente.Name)" -ForegroundColor Yellow
    } else {
        Copy-Item $agente.FullName $destino -Recurse -Force
        Write-Host "Ligado: $($agente.Name)" -ForegroundColor Green
    }
}
Write-Host ""
Write-Host "Pronto. Para usar, peca ao Jarvis pelo nome, ex.: 'Hey Jarvis, pede ao Hermes o resumo dos meus treinos'."
Write-Host "Veja em agentes-futuros\LEIA-ME.md o que cada um precisa (alguns pedem conectar um app)."
Read-Host "Aperte Enter para fechar"
