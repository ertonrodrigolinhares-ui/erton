# Liga (ou desliga) os agentes do Jarvis Ultron. Cada agente ligado vira um botao no painel Ultron
# e roda no Claude. Se o Hermes estiver instalado, o agente tambem e ligado no perfil "jarvis" dele.
# A lista dos ligados fica em Documentos\Jarvis Ultron\agentes_ligados.txt (um nome por linha).

$ErrorActionPreference = "Stop"
$kit = Split-Path -Parent $MyInvocation.MyCommand.Path        # ...\jarvis-ultron\hermes
$ultron = Split-Path -Parent $kit
$skills = Join-Path $ultron "claude\skills"
$guardados = Join-Path $kit "agentes-futuros"
# Pacote do dono (JARVIS_PACOTE no .env): os agentes dele entram na lista junto com os do produto
$pacote = ""
$envUltron = Join-Path $ultron ".env"
if (Test-Path $envUltron) {
    foreach ($linha in [System.IO.File]::ReadAllLines($envUltron)) {
        if ($linha -match '^\s*JARVIS_PACOTE\s*=\s*"?([A-Za-z0-9-]+)"?') { $pacote = $matches[1].ToLower() }
    }
}
$pastasSkills = @($skills)
$pastasGuardados = @($guardados)
if ($pacote -and (Test-Path (Join-Path $ultron "pacotes\$pacote"))) {
    $pastasSkills += Join-Path $ultron "pacotes\$pacote\claude\skills"
    $pastasGuardados += Join-Path $ultron "pacotes\$pacote\hermes\agentes-futuros"
}
$dados = Join-Path $env:USERPROFILE "Documents\Jarvis Ultron"
$lista = Join-Path $dados "agentes_ligados.txt"
$utf8 = New-Object System.Text.UTF8Encoding $false
$raizHermes = if ($env:HERMES_HOME) { $env:HERMES_HOME } else { Join-Path $env:LOCALAPPDATA "hermes" }
$ativosHermes = Join-Path $raizHermes "profiles\jarvis\skills\jarvis"
$comHermes = Test-Path $ativosHermes

function Ler-Ligados {
    if (-not (Test-Path $lista)) { return @() }
    return @([System.IO.File]::ReadAllLines($lista) | ForEach-Object { $_.Trim() } | Where-Object { $_ })
}

function Gravar-Ligados($nomes) {
    New-Item -ItemType Directory -Force -Path $dados | Out-Null
    $texto = ""
    foreach ($n in $nomes) { $texto += "$n`n" }
    [System.IO.File]::WriteAllText($lista, $texto, $utf8)
}

$agentes = @($pastasSkills | Where-Object { Test-Path $_ } | ForEach-Object { Get-ChildItem $_ -Directory } | Sort-Object Name)
$ligados = @(Ler-Ligados)
Write-Host ""
Write-Host "Agentes do Luiz (os LIGADOS viram botoes no painel Ultron e rodam no Claude):" -ForegroundColor Cyan
for ($i = 0; $i -lt $agentes.Count; $i++) {
    $nome = $agentes[$i].Name
    $estado = if ($ligados -contains $nome) { "[LIGADO]   " } else { "[desligado]" }
    $linha = (Get-Content (Join-Path $agentes[$i].FullName "SKILL.md") -Encoding UTF8 | Where-Object { $_ -like "description:*" } | Select-Object -First 1)
    $descricao = if ($linha) { $linha.Substring(12).Trim().Trim('"') } else { "" }
    Write-Host ("{0,2}. {1} {2}" -f ($i + 1), $estado, $nome)
    Write-Host ("       {0}" -f $descricao) -ForegroundColor DarkGray
}
Write-Host ""
$resposta = Read-Host "Digite os numeros para LIGAR ou DESLIGAR (ex.: 1 4 10), ou Enter para sair"
foreach ($parte in ($resposta -split "[ ,;]+" | Where-Object { $_ })) {
    $n = 0
    if (-not [int]::TryParse($parte, [ref]$n) -or $n -lt 1 -or $n -gt $agentes.Count) { continue }
    $nome = $agentes[$n - 1].Name
    $noHermes = Join-Path $ativosHermes $nome
    if ($ligados -contains $nome) {
        $ligados = @($ligados | Where-Object { $_ -ne $nome })
        if ($comHermes -and (Test-Path $noHermes)) { Remove-Item $noHermes -Recurse -Force }
        Write-Host "Desligado: $nome" -ForegroundColor Yellow
    } else {
        $ligados = @($ligados) + $nome
        $origemHermes = $null
        foreach ($g in $pastasGuardados) { $cand = Join-Path $g $nome; if (Test-Path $cand) { $origemHermes = $cand } }
        if ($comHermes -and $origemHermes) { Copy-Item $origemHermes $noHermes -Recurse -Force }
        Write-Host "Ligado: $nome" -ForegroundColor Green
    }
}
Gravar-Ligados $ligados
Write-Host ""
Write-Host "Pronto. Abra o painel Ultron (diga 'Luiz, modo Ultron'): os agentes ligados aparecem como botoes."
Write-Host "Eles rodam no Claude: rode o 'Instalar Claude' antes, se ainda nao rodou."
Read-Host "Aperte Enter para fechar"
