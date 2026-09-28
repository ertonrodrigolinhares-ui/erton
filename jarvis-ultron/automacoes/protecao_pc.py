"""Proteção do PC (automação: salve na pasta 'automacoes' e reabra o Jarvis).

Diga, por exemplo:
  - "Jarvis, meu computador está protegido?"
  - "Jarvis, faça a checagem de segurança do PC"

Ele confere (SÓ LENDO, sem mudar nada) as defesas do SEU próprio Windows e diz o que melhorar:
  - antivírus (Windows Defender) ligado e com a "vacina" em dia;
  - firewall ligado nos três perfis;
  - se o Windows está atualizado;
  - se o acesso remoto (área de trabalho remota) está aberto — risco comum;
  - se o disco está criptografado (BitLocker);
  - quais programas abrem junto com o Windows (para você notar algum estranho).

É tudo no seu próprio computador. Não mexe em rede, não acessa outros PCs, não invade nada.
Para LIGAR o que estiver desligado, ele te diz como, mas quem clica é você (algumas coisas pedem
permissão de administrador).
"""

from __future__ import annotations

import json
import os
import subprocess
from datetime import date, datetime

FERRAMENTA = {
    "name": "pc_protection",
    "description": (
        "Read-only security checkup of THIS Windows PC (Defender antivirus, firewall, Windows Update "
        "recency, Remote Desktop exposure, BitLocker, startup programs). Use when the user asks if their "
        "computer is protected/secure or for a PC security check. It only reads local settings, never "
        "changes anything and never touches the network or other computers. Answer in Portuguese, saying "
        "what is OK and what to fix."
    ),
    "parameters": {"type": "OBJECT", "properties": {}},
}

# Script PowerShell que só LÊ as configurações e devolve tudo em JSON.
_SCRIPT = r"""
$out = [ordered]@{}
try { $d = Get-MpComputerStatus -ErrorAction Stop
      $out.defender = @{ antivirus = [bool]$d.AntivirusEnabled; realtime = [bool]$d.RealTimeProtectionEnabled
                         sigAgeDays = [int]$d.AntivirusSignatureAge } } catch {}
try { $out.firewall = @(Get-NetFirewallProfile -ErrorAction Stop | ForEach-Object {
                         @{ name = "$($_.Name)"; enabled = [bool]$_.Enabled } }) } catch {}
try { $hf = Get-HotFix -ErrorAction Stop | Where-Object { $_.InstalledOn } |
            Sort-Object InstalledOn -Descending | Select-Object -First 1
      if ($hf) { $out.lastUpdate = $hf.InstalledOn.ToString('yyyy-MM-dd') } } catch {}
try { $out.rdpDenied = [int](Get-ItemProperty 'HKLM:\System\CurrentControlSet\Control\Terminal Server' `
                             -Name fDenyTSConnections -ErrorAction Stop).fDenyTSConnections } catch {}
try { $out.bitlocker = @(Get-BitLockerVolume -ErrorAction Stop | ForEach-Object {
                         @{ drive = "$($_.MountPoint)"; status = "$($_.ProtectionStatus)" } }) } catch {}
try { $out.startup = @(Get-CimInstance Win32_StartupCommand -ErrorAction Stop |
                       ForEach-Object { "$($_.Name)" } | Where-Object { $_ } | Select-Object -First 25) } catch {}
$out | ConvertTo-Json -Depth 5 -Compress
"""

VACINA_MAX_DIAS = 3       # antivírus com assinatura mais velha que isso: avisar
UPDATE_MAX_DIAS = 45      # sem atualizar o Windows há mais que isso: avisar


def _coletar() -> dict:
    """Roda o PowerShell só-leitura e devolve o dicionário. {} se não for Windows ou falhar."""
    if os.name != "nt":
        return {}
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", _SCRIPT],
            capture_output=True, text=True, timeout=90)
        return json.loads(proc.stdout.strip() or "{}")
    except (OSError, ValueError, subprocess.SubprocessError):
        return {}


def avaliar(dados: dict, hoje: date | None = None) -> dict:
    """Transforma a leitura em bom/alerta/grave. Fácil de testar (sem tocar no Windows)."""
    hoje = hoje or date.today()
    r = {"bom": [], "alerta": [], "grave": [], "info": []}

    defender = dados.get("defender")
    if isinstance(defender, dict):
        if not defender.get("antivirus") or not defender.get("realtime"):
            r["grave"].append("O antivírus (Windows Defender) ou a proteção em tempo real está DESLIGADA. "
                              "Ligue em: Segurança do Windows > Proteção contra vírus e ameaças.")
        else:
            r["bom"].append("Antivírus ligado com proteção em tempo real.")
            idade = defender.get("sigAgeDays")
            if isinstance(idade, int) and idade > VACINA_MAX_DIAS:
                r["alerta"].append(f"A vacina do antivírus está com {idade} dias. Atualize em "
                                   "Segurança do Windows > Proteção contra vírus > Verificar se há atualizações.")
            else:
                r["bom"].append("Vacina do antivírus em dia.")

    firewall = dados.get("firewall")
    if isinstance(firewall, list) and firewall:
        desligados = [f.get("name", "?") for f in firewall if not f.get("enabled")]
        if desligados:
            r["grave"].append("O firewall está DESLIGADO em: " + ", ".join(desligados) +
                              ". Ligue em: Segurança do Windows > Firewall e proteção de rede.")
        else:
            r["bom"].append("Firewall ligado em todos os perfis.")

    ultimo = dados.get("lastUpdate")
    if ultimo:
        try:
            dias = (hoje - date.fromisoformat(str(ultimo)[:10])).days
            if dias > UPDATE_MAX_DIAS:
                r["alerta"].append(f"O Windows não recebe atualização há cerca de {dias} dias. "
                                   "Abra Configurações > Windows Update > Verificar se há atualizações.")
            else:
                r["bom"].append("Windows atualizado recentemente.")
        except ValueError:
            pass

    rdp = dados.get("rdpDenied")
    if rdp == 0:
        r["grave"].append("A Área de Trabalho Remota está LIGADA. Se você não usa, desligue: "
                          "Configurações > Sistema > Área de Trabalho Remota. Isso fecha uma porta de ataque.")
    elif rdp == 1:
        r["bom"].append("Acesso remoto desligado (mais seguro).")

    bitlocker = dados.get("bitlocker")
    if isinstance(bitlocker, list) and bitlocker:
        desprotegidos = [b.get("drive", "?") for b in bitlocker
                         if str(b.get("status", "")).lower() not in ("on", "1")]
        if desprotegidos:
            r["info"].append("O disco não está criptografado (BitLocker). Se roubarem o PC, podem ler seus "
                             "arquivos. Considere ativar o BitLocker no disco " + ", ".join(desprotegidos) + ".")
        else:
            r["bom"].append("Disco criptografado (BitLocker ligado).")

    inicio = dados.get("startup")
    if isinstance(inicio, list) and inicio:
        r["info"].append(f"{len(inicio)} programas abrem junto com o Windows. Se ver algum nome estranho, "
                         "pode desligar em Gerenciador de Tarefas > Inicializar. Ex.: " + ", ".join(inicio[:6]) + ".")

    total_problemas = len(r["grave"]) + len(r["alerta"])
    r["nivel"] = "bom" if total_problemas == 0 else ("atenção" if not r["grave"] else "precisa de ajuste")
    return r


def _frase(r: dict, tem_dados: bool) -> str:
    if not tem_dados:
        return ("Não consegui ler as proteções do computador (isso funciona no Windows). "
                "Tell the user in Portuguese.")
    partes = [f"Proteção do PC: {r['nivel']}."]
    if r["grave"]:
        partes.append("Precisa arrumar: " + " ".join(r["grave"]))
    if r["alerta"]:
        partes.append("Atenção: " + " ".join(r["alerta"]))
    if r["bom"]:
        partes.append("Está bom: " + " ".join(r["bom"]))
    if r["info"]:
        partes.append("Para saber: " + " ".join(r["info"]))
    partes.append("Explique ao usuário em português, de forma simples, começando pelo que precisa arrumar. "
                  "É uma leitura do próprio PC, não mexe em nada.")
    return " ".join(partes)


def executar(args: dict, jarvis) -> str:
    dados = _coletar()
    return _frase(avaliar(dados), bool(dados))
