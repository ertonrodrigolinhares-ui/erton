<#
.SYNOPSIS
    Auditoria defensiva da SUA rede Wi-Fi (Windows).

.DESCRIPTION
    Verifica tres coisas na rede a que este computador esta conectado:
      1. Seguranca do Wi-Fi  - autenticacao (WPA3/WPA2/WEP/aberta), cifra e forca da senha salva
      2. Dispositivos        - todos os aparelhos que respondem na sub-rede (IP, MAC, nome, fabricante)
      3. Portas expostas     - servicos abertos nos aparelhos encontrados, com alerta para os de risco

    Gera um relatorio HTML e um CSV na Area de Trabalho.

    Restricoes de seguranca embutidas:
      - So roda em sub-redes privadas (10.x, 172.16-31.x, 192.168.x).
      - So varre a sub-rede local (no maximo /22 = 1022 hosts).
      - Exige confirmacao de que voce e responsavel pela rede.
      - A senha do Wi-Fi nunca e exibida nem gravada; so a avaliacao de forca.

    USE APENAS EM REDES QUE VOCE POSSUI OU TEM AUTORIZACAO POR ESCRITO PARA TESTAR.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\Auditoria-WiFi.ps1
.EXAMPLE
    .\Auditoria-WiFi.ps1 -SemPortas          # so Wi-Fi e dispositivos
.EXAMPLE
    .\Auditoria-WiFi.ps1 -TimeoutMs 500      # redes lentas
#>
[CmdletBinding()]
param(
    [switch]$SemPortas,
    [int]$TimeoutMs = 300,
    [string]$Saida = [Environment]::GetFolderPath('Desktop')
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

# ---------------------------------------------------------------- utilidades
$Achados = New-Object System.Collections.Generic.List[object]

function Add-Achado {
    param([ValidateSet('CRITICO','ALTO','MEDIO','BAIXO','OK')]$Nivel, $Area, $Item, $Recomendacao)
    $Achados.Add([pscustomobject]@{ Nivel = $Nivel; Area = $Area; Item = $Item; Recomendacao = $Recomendacao })
    $cor = @{ CRITICO='Red'; ALTO='Red'; MEDIO='Yellow'; BAIXO='Cyan'; OK='Green' }[$Nivel]
    Write-Host ("  [{0,-7}] {1}" -f $Nivel, $Item) -ForegroundColor $cor
}

function Write-Secao($t) { Write-Host "`n=== $t ===" -ForegroundColor White }

function Test-IpPrivado([System.Net.IPAddress]$ip) {
    $b = $ip.GetAddressBytes()
    return ($b[0] -eq 10) -or ($b[0] -eq 172 -and $b[1] -ge 16 -and $b[1] -le 31) -or ($b[0] -eq 192 -and $b[1] -eq 168)
}

function ConvertTo-UInt32([System.Net.IPAddress]$ip) {
    $b = $ip.GetAddressBytes(); [array]::Reverse($b); [BitConverter]::ToUInt32($b, 0)
}
function ConvertFrom-UInt32([uint32]$n) {
    $b = [BitConverter]::GetBytes($n); [array]::Reverse($b); [System.Net.IPAddress]::new($b)
}

# Prefixos OUI comuns (offline). MACs com o 2o digito 2/6/A/E sao aleatorios (privacidade do celular).
$OUI = @{
    '00:1A:11'='Google';  'F4:F5:D8'='Google';   '3C:5A:B4'='Google'
    'F0:18:98'='Apple';   'AC:BC:32'='Apple';    '3C:22:FB'='Apple';  'A4:83:E7'='Apple'
    '