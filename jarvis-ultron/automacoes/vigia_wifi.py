"""Vigia do meu Wi-Fi (automação: salve na pasta 'automacoes' e reabra o Jarvis).

Diga, por exemplo:
  - "Jarvis, quem está conectado no meu Wi-Fi?"
  - "Jarvis, minha rede está segura?"
  - "Jarvis, apareceu algum aparelho novo na rede?"

O que ele faz (SÓ na SUA rede, só lendo o que o seu próprio PC já sabe):
  - lista os aparelhos que aparecem na sua rede (pela tabela ARP do Windows) e AVISA quando surge um
    aparelho que ele nunca tinha visto;
  - confere a segurança do SEU Wi-Fi atual: se está com senha (WPA2/WPA3), aberta ou fraca (WEP).

O que ele NÃO faz: não invade aparelhos, não abre arquivos de ninguém, não faz varredura na rede de
outras pessoas e não vê o que os outros estão fazendo. É só a fachada da SUA própria rede.
Os aparelhos conhecidos ficam salvos em Documentos/Jarvis Ultron/wifi_dispositivos.json.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from datetime import date

FERRAMENTA = {
    "name": "wifi_watch",
    "description": (
        "Read-only watch over the user's OWN Wi-Fi/LAN: lists devices seen on the local network (from the "
        "PC's ARP cache), flags a device never seen before, and checks whether the current Wi-Fi is secure "
        "(WPA2/WPA3 vs open/WEP). Use when the user asks who is connected to their Wi-Fi, if a new device "
        "appeared, or if their network is secure. It never scans other people's networks, opens other "
        "computers or accesses anyone's files. Answer in Portuguese."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "description": "devices | security | both (default both)"},
        },
    },
}

_MAC = re.compile(r"([0-9a-f]{2}[-:]){5}[0-9a-f]{2}", re.IGNORECASE)
_LINHA_ARP = re.compile(r"^\s*(\d{1,3}(?:\.\d{1,3}){3})\s+([0-9a-fA-F][0-9a-f:-]{16})\s+(\w+)", re.MULTILINE)


def arquivo_conhecidos() -> "os.PathLike":
    from pathlib import Path
    return Path.home() / "Documents" / "Jarvis Ultron" / "wifi_dispositivos.json"


def _normalizar_mac(mac: str) -> str:
    return mac.strip().lower().replace("-", ":")


def analisar_arp(texto: str) -> list[dict]:
    """Lê a saída do 'arp -a' e devolve os aparelhos reais da rede (sem broadcast/multicast)."""
    aparelhos = []
    for ip, mac, tipo in _LINHA_ARP.findall(texto or ""):
        if not _MAC.fullmatch(mac):
            continue
        m = _normalizar_mac(mac)
        if m == "ff:ff:ff:ff:ff:ff" or m.startswith("01:00:5e") or m.startswith("33:33") or ip.endswith(".255"):
            continue  # broadcast/multicast, não são aparelhos de verdade
        if ip.startswith(("224.", "239.", "255.")):
            continue
        aparelhos.append({"ip": ip, "mac": m, "tipo": tipo.lower()})
    # tira repetidos (mesma MAC), mantendo o primeiro IP
    vistos, unicos = set(), []
    for a in aparelhos:
        if a["mac"] not in vistos:
            vistos.add(a["mac"])
            unicos.append(a)
    return unicos


def analisar_wifi(texto: str) -> dict:
    """Lê o 'netsh wlan show interfaces' (pt-BR ou inglês) e devolve rede e segurança."""
    def achar(*rotulos):
        for rotulo in rotulos:
            m = re.search(rf"^\s*{rotulo}\s*:\s*(.+)$", texto or "", re.MULTILINE | re.IGNORECASE)
            if m:
                return m.group(1).strip()
        return ""
    ssid = achar("SSID")
    # em algumas versões aparece "BSSID" também; garante que não é o BSSID
    if ssid.count(":") >= 5:
        ssid = achar(r"SSID(?!\s*BSSID)")
    return {
        "ssid": ssid,
        "autenticacao": achar("Autenticação", "Authentication", "Autenticacao"),
        "sinal": achar("Sinal", "Signal"),
    }


def _seguranca_do_wifi(info: dict) -> dict:
    r = {"bom": [], "alerta": [], "grave": []}
    if not info.get("ssid"):
        r["alerta"].append("Não consegui ver a rede Wi-Fi atual (talvez esteja no cabo).")
        return r
    auth = info.get("autenticacao", "").lower()
    rede = info["ssid"]
    if not auth or "aberta" in auth or "open" in auth or "none" in auth:
        r["grave"].append(f"Sua rede '{rede}' está SEM SENHA (aberta). Qualquer um por perto entra. "
                          "Coloque uma senha WPA2/WPA3 nas configurações do roteador.")
    elif "wep" in auth:
        r["grave"].append(f"Sua rede '{rede}' usa WEP, que é fácil de quebrar. Mude para WPA2 ou WPA3 no roteador.")
    elif "wpa3" in auth:
        r["bom"].append(f"Sua rede '{rede}' usa WPA3 (o mais seguro).")
    elif "wpa2" in auth:
        r["bom"].append(f"Sua rede '{rede}' usa WPA2 (seguro).")
    elif "wpa" in auth:
        r["alerta"].append(f"Sua rede '{rede}' usa WPA (antigo). Se o roteador permitir, mude para WPA2 ou WPA3.")
    else:
        r["bom"].append(f"Rede '{rede}' com autenticação {info.get('autenticacao')}.")
    return r


def _rodar(comando: list[str]) -> str:
    if os.name != "nt":
        return ""
    try:
        return subprocess.run(comando, capture_output=True, text=True, timeout=30).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def carregar_conhecidos(caminho=None) -> dict:
    try:
        return json.loads((caminho or arquivo_conhecidos()).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def salvar_conhecidos(dados: dict, caminho=None) -> None:
    caminho = caminho or arquivo_conhecidos()
    from pathlib import Path
    Path(caminho).parent.mkdir(parents=True, exist_ok=True)
    Path(caminho).write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")


def conferir_dispositivos(aparelhos: list[dict], conhecidos: dict, hoje: date | None = None) -> tuple[list, dict]:
    """Marca quais aparelhos são novos e atualiza a lista de conhecidos. Devolve (novos, conhecidos)."""
    hoje = hoje or date.today()
    novos = []
    for a in aparelhos:
        if a["mac"] not in conhecidos:
            conhecidos[a["mac"]] = {"nome": "", "primeiro": hoje.isoformat(), "ip": a["ip"]}
            novos.append(a)
        else:
            conhecidos[a["mac"]]["ip"] = a["ip"]
    return novos, conhecidos


def _frase(acao: str, aparelhos, novos, seg, tem_dados) -> str:
    partes = []
    if acao in ("devices", "both"):
        if not tem_dados:
            partes.append("Não consegui ler os aparelhos da rede (isso funciona no Windows).")
        else:
            partes.append(f"Vejo {len(aparelhos)} aparelho(s) na sua rede.")
            if novos:
                lista = ", ".join(f"{a['ip']} ({a['mac']})" for a in novos[:5])
                partes.append(f"ATENÇÃO: {len(novos)} aparelho(s) NOVO(s) que eu não conhecia: {lista}. "
                              "Se não for seu, troque a senha do Wi-Fi.")
            else:
                partes.append("Nenhum aparelho novo desde a última vez.")
    if acao in ("security", "both") and seg is not None:
        for g in seg.get("grave", []):
            partes.append("Grave: " + g)
        for a in seg.get("alerta", []):
            partes.append("Atenção: " + a)
        for b in seg.get("bom", []):
            partes.append(b)
    partes.append("Explique ao usuário em português, de forma simples. É a leitura da própria rede dele, "
                  "não mexe em nada nem em aparelho de ninguém.")
    return " ".join(partes)


def executar(args: dict, jarvis) -> str:
    acao = str(args.get("action", "both") or "both").strip().lower()
    if acao not in ("devices", "security", "both"):
        acao = "both"
    aparelhos, novos, seg, tem_dados = [], [], None, True
    if acao in ("devices", "both"):
        texto = _rodar(["arp", "-a"])
        tem_dados = bool(texto)
        aparelhos = analisar_arp(texto)
        conhecidos = carregar_conhecidos()
        novos, conhecidos = conferir_dispositivos(aparelhos, conhecidos)
        if tem_dados:
            try:
                salvar_conhecidos(conhecidos)
            except OSError:
                pass
    if acao in ("security", "both"):
        seg = _seguranca_do_wifi(analisar_wifi(_rodar(["netsh", "wlan", "show", "interfaces"])))
    return _frase(acao, aparelhos, novos, seg, tem_dados)
