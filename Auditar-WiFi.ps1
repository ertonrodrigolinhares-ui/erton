<#
================================================================================
  Auditar-WiFi.ps1  -  Auditoria defensiva da SUA PROPRIA rede Wi-Fi
================================================================================

  AUTORIZACAO / USO LEGAL
  -----------------------
  Rode este script APENAS na rede que voce controla (sua casa / sua empresa)
  e com permissao de quem responde por ela. Testar rede de terceiros sem
  autorizacao por escrito e crime (no Brasil, Lei 12.737/2012 e Lei 14.155/2021).

  O que ele faz (tudo passivo/defensivo):
    1. Lista os dispositivos conectados a rede (IP, MAC, fabricante aproximado)
    2. Verifica a criptografia e a configuracao do Wi-Fi (WPA2/WPA3, WPS, senha)
    3. Verifica portas abertas nos SEUS proprios equipamentos (ex: o roteador)

  O que ele NAO faz: nao quebra senhas, nao captura trafego de outros,
  nao ataca nenhum alvo. E uma radiografia da sua propria rede.

  COMO EXECUTAR
  -------------
    1. Abra o PowerShell COMO ADMINISTRADOR
       (menu Iniciar > digite PowerShell > clique com botao direito >
        "Executar como administrador")
    2. Libere a execucao so para esta sessao:
         Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
    3. Rode:
         .\Auditar-WiFi.ps1
       Para incluir o scan de portas:
         .\Auditar-WiFi.ps1 -ScanPortas
================================================================================
#>

[CmdletBinding()]
param(
    # Faz o scan de portas nos equipamentos encontrados (mais demorado).
    [switch]$ScanPortas,

    # Portas verificadas no scan (as mais comuns em roteadores/IoT).
    [int[]]$Portas = @(21,22,23,53,80,443,445,554,1900,3389,5000,7547,8080,8443,9000),

    # Pasta onde o relatorio sera salvo.
    [string]$PastaSaida = "$env:USERPROFILE\Desktop"
)

$ErrorActionPreference = 'Stop'
$agora   = Get-Date
$relat   = @()
$achados = [System.Collections.Generic.List[object]]::new()

function Secao($t) {
    Write-Host ""
    Write-Host ("=" * 72) -ForegroundColor Cyan
    Write-Host "  $t" -ForegroundColor Cyan
    Write-Host ("=" * 72) -ForegroundColor Cyan
}
function Alerta($nivel,$msg) {
    $cor = switch ($nivel) { 'ALTO' {'Red'} 'MEDIO' {'Yellow'} default {'Green'} }
    Write-Host "  [$nivel] $msg" -ForegroundColor $cor
    $achados.Add([pscustomobject]@{ Nivel=$nivel; Mensagem=$msg })
}

# Checagem de admin ---------------------------------------------------------
$ehAdmin = ([Security.Principal.WindowsPrincipal] `
    [Security.Principal.WindowsIdentity]::GetCurrent()
).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $ehAdmin) {
    Write-Warning "Rode como ADMINISTRADOR para ver a senha do Wi-Fi e todos os detalhes."
}

Write-Host ""
Write-Host "  AUDITORIA DE SEGURANCA DA REDE WI-FI" -ForegroundColor White
Write-Host "  $agora" -ForegroundColor DarkGray
Write-Host "  Use SOMENTE na sua propria rede, com autorizacao." -ForegroundColor DarkGray

# ===========================================================================
# 2. CONFIGURACAO E CRIPTOGRAFIA DO WI-FI
# ===========================================================================
Secao "2. Criptografia e configuracao do Wi-Fi"

$ssidAtual = $null
try {
    $ifInfo = netsh wlan show interfaces 2>$null
    $linhaSsid = $ifInfo | Select-String '^\s*SSID\s*:' | Select-Object -First 1
    if ($linhaSsid) {
        $ssidAtual = ($linhaSsid -split ':',2)[1].Trim()
        Write-Host "  Rede conectada agora: $ssidAtual" -ForegroundColor White

        $autent = ($ifInfo | Select-String 'Authentication|Autentica' | Select-Object -First 1)
        $cifra  = ($ifInfo | Select-String 'Cipher|Codifica|Cifra'     | Select-Object -First 1)
        if ($autent) { Write-Host "  $($autent.ToString().Trim())" }
        if ($cifra)  { Write-Host "  $($cifra.ToString().Trim())" }

        $txtAut = if ($autent) { $autent.ToString() } else { '' }
        if ($txtAut -match 'WPA3') {
            Alerta 'OK' "Autenticacao WPA3 (otimo)."
        } elseif ($txtAut -match 'WPA2') {
            Alerta 'OK' "WPA2 em uso. Se o roteador suportar, migre para WPA3/WPA2."
        } elseif ($txtAut -match 'WPA\b') {
            Alerta 'MEDIO' "WPA (v1) e fraco. Mude para WPA2 ou WPA3."
        } elseif ($txtAut -match 'WEP|Open|Aberta') {
            Alerta 'ALTO' "Rede sem criptografia forte (WEP/aberta). Troque JA para WPA2/WPA3."
        }
    }
} catch { Write-Warning "Nao consegui ler a interface Wi-Fi: $_" }

# Perfis salvos + forca da senha (precisa de admin) -------------------------
try {
    $perfis = (netsh wlan show profiles) 2>$null |
              Select-String ':\s*(.+)$' |
              ForEach-Object { $_.Matches.Groups[1].Value.Trim() } |
              Where-Object { $_ -and $_ -notmatch 'User profiles|Perfis de' }

    foreach ($p in $perfis) {
        $det = netsh wlan show profile name="$p" key=clear 2>$null
        $segLinha = $det | Select-String 'Authentication|Autentica' | Select-Object -First 1
        $keyLinha = $det | Select-String 'Key Content|Conteudo da Chave' | Select-Object -First 1
        $senha = if ($keyLinha) { ($keyLinha -split ':',2)[1].Trim() } else { $null }

        $info = "Perfil salvo: '$p'"
        if ($segLinha) { $info += " | $(($segLinha -split ':',2)[1].Trim())" }
        Write-Host "  $info"

        if ($senha) {
            if ($senha.Length -lt 12) {
                Alerta 'MEDIO' "Senha da rede '$p' tem so $($senha.Length) caracteres. Use 15+ (frase longa)."
            } else {
                Alerta 'OK' "Senha da rede '$p' tem comprimento razoavel ($($senha.Length) caracteres)."
            }
            # Dicionario minimo de senhas obvias
            if ($senha -match '^(?i)(12345678|senha|password|admin|000000|abc123|internet|wifi)') {
                Alerta 'ALTO' "A senha da rede '$p' parece trivial. Troque imediatamente."
            }
        }
    }
} catch { Write-Warning "Nao consegui listar perfis Wi-Fi (rode como admin): $_" }

# ===========================================================================
# 1. DISPOSITIVOS NA REDE
# ===========================================================================
Secao "1. Dispositivos conectados a rede"

# Gateway (roteador) e sub-rede
$cfg = Get-NetIPConfiguration | Where-Object { $_.IPv4DefaultGateway -and $_.NetAdapter.Status -eq 'Up' } | Select-Object -First 1
$gateway = $cfg.IPv4DefaultGateway.NextHop
$meuIP   = $cfg.IPv4Address.IPAddress
Write-Host "  Seu IP:      $meuIP"
Write-Host "  Roteador:    $gateway"

# "Acorda" a tabela ARP pingando a faixa /24 em paralelo
if ($meuIP -match '^(\d+\.\d+\.\d+)\.\d+$') {
    $base = $Matches[1]
    Write-Host "  Varrendo $base.1-254 (ping) para popular a tabela ARP..." -ForegroundColor DarkGray
    1..254 | ForEach-Object -ThrottleLimit 64 -Parallel {
        $null = Test-Connection -TargetName "$using:base.$_" -Count 1 -TimeoutSeconds 1 -Quiet -ErrorAction SilentlyContinue
    }
}

# Le a tabela ARP (vizinhos descobertos)
$vizinhos = Get-NetNeighbor -AddressFamily IPv4 -ErrorAction SilentlyContinue |
    Where-Object { $_.State -in 'Reachable','Stale','Permanent' -and $_.LinkLayerAddress -and $_.LinkLayerAddress -ne '00-00-00-00-00-00' } |
    Sort-Object { [version]($_.IPAddress -replace '\.','.') } -ErrorAction SilentlyContinue |
    Select-Object IPAddress, LinkLayerAddress

$dispositivos = @()
foreach ($v in $vizinhos) {
    $nome = $null
    try { $nome = (Resolve-DnsName -Name $v.IPAddress -ErrorAction SilentlyContinue | Select-Object -First 1).NameHost } catch {}
    $fab = $v.LinkLayerAddress.Substring(0,8)  # OUI do fabricante (6 primeiros digitos)
    $dispositivos += [pscustomobject]@{
        IP         = $v.IPAddress
        MAC        = $v.LinkLayerAddress
        OUI        = $fab
        Nome       = $nome
        EhRoteador = ($v.IPAddress -eq $gateway)
    }
}
$dispositivos | Format-Table -AutoSize
Alerta 'OK' "$($dispositivos.Count) dispositivos vistos na rede. Confira se voce reconhece TODOS."
Write-Host "  Dica: compare esta lista com a lista de clientes DHCP no painel do roteador." -ForegroundColor DarkGray

# ===========================================================================
# 3. PORTAS ABERTAS NOS SEUS EQUIPAMENTOS
# ===========================================================================
if ($ScanPortas) {
    Secao "3. Portas abertas (nos seus proprios equipamentos)"
    Write-Host "  Verificando portas: $($Portas -join ', ')" -ForegroundColor DarkGray

    $arriscadas = @{ 21='FTP sem criptografia'; 23='Telnet (inseguro)'; 445='SMB exposto';
                     3389='RDP exposto'; 7547='TR-069 (gestao remota do provedor)';
                     1900='UPnP/SSDP'; 5000='UPnP/painel'; 554='RTSP (cameras)' }

    foreach ($d in $dispositivos) {
        $abertas = @()
        foreach ($porta in $Portas) {
            $r = Test-NetConnection -ComputerName $d.IP -Port $porta -WarningAction SilentlyContinue -InformationLevel Quiet
            if ($r) { $abertas += $porta }
        }
        if ($abertas.Count) {
            $tag = if ($d.EhRoteador) { ' (ROTEADOR)' } else { '' }
            Write-Host ""
            Write-Host "  $($d.IP)$tag  ->  portas abertas: $($abertas -join ', ')" -ForegroundColor White
            foreach ($a in $abertas) {
                if ($arriscadas.ContainsKey($a)) {
                    Alerta 'MEDIO' "$($d.IP): porta $a aberta - $($arriscadas[$a]). Desligue se nao usa."
                }
            }
        }
    }
    Alerta 'OK' "Scan de portas concluido. Feche o que nao for necessario, principalmente no roteador."
} else {
    Write-Host ""
    Write-Host "  (Scan de portas pulado. Rode com -ScanPortas para incluir.)" -ForegroundColor DarkGray
}

# ===========================================================================
# CHECKLIST FINAL + RELATORIO
# ===========================================================================
Secao "Checklist de hardening do roteador (verifique manualmente)"
@(
 "[ ] Trocou a senha PADRAO de administrador do roteador (nao e a senha do Wi-Fi)"
 "[ ] Firmware do roteador atualizado"
 "[ ] WPS DESLIGADO (facilita invasao por PIN)"
 "[ ] Administracao remota (via internet) DESLIGADA"
 "[ ] UPnP desligado, a menos que precise"
 "[ ] Rede de visitantes separada para IoT/convidados"
 "[ ] WPA2 ou WPA3 com senha longa (15+ caracteres)"
 "[ ] DNS confiavel configurado"
) | ForEach-Object { Write-Host "  $_" }

# Salva relatorio
if (-not (Test-Path $PastaSaida)) { $PastaSaida = $env:USERPROFILE }
$arq = Join-Path $PastaSaida ("Auditoria-WiFi_{0:yyyy-MM-dd_HHmm}.txt" -f $agora)
$conteudo = @()
$conteudo += "AUDITORIA DE SEGURANCA WI-FI  -  $agora"
$conteudo += "Rede: $ssidAtual   Roteador: $gateway"
$conteudo += ""
$conteudo += "ACHADOS:"
foreach ($a in $achados) { $conteudo += "  [$($a.Nivel)] $($a.Mensagem)" }
$conteudo += ""
$conteudo += "DISPOSITIVOS:"
foreach ($d in $dispositivos) { $conteudo += "  $($d.IP)  $($d.MAC)  $($d.Nome)" }
$conteudo | Out-File -FilePath $arq -Encoding UTF8

Write-Host ""
Write-Host "  Relatorio salvo em: $arq" -ForegroundColor Green
Write-Host ""
