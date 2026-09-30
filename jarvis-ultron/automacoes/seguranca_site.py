"""Análise de segurança de sites (automação: salve na pasta 'automacoes' e reabra o Jarvis).

Diga, por exemplo:
  - "Jarvis, verifique a segurança do site linharesprudencio.com.br"
  - "Jarvis, esse site é seguro? www.exemplo.com"

O que ele faz (SEMPRE de forma passiva, como um visitante normal):
  - confere se o site usa HTTPS e se o endereço http:// é levado para o https:// (cadeado);
  - lê o certificado de segurança: se é válido, quem emitiu e quantos dias faltam para vencer;
  - vê se o site tem as proteções recomendadas (HSTS, CSP, X-Frame-Options, etc.);
  - dá uma NOTA (A a F) e explica, em português, o que está bom e o que dá para melhorar.

O que ele NUNCA faz: invadir, testar senhas, procurar falhas para explorar ou "atacar" o site.
É só uma leitura da fachada pública, o mesmo que abrir o site no navegador. Use no seu próprio
site ou no de quem te autorizou a avaliar.
"""

from __future__ import annotations

import re
import socket
import ssl
import urllib.error
import urllib.request
from datetime import datetime, timezone

FERRAMENTA = {
    "name": "website_security_check",
    "description": (
        "Passive, read-only security checkup of a website (HTTPS, TLS certificate validity/expiry, "
        "security headers like HSTS/CSP/X-Frame-Options) and a letter grade. Use when the user asks "
        "whether a site is secure or to check a site's security level. It never attacks, scans for "
        "vulnerabilities, brute-forces or exploits anything — only reads what any visitor's browser sees. "
        "Answer the user in Portuguese, explaining the grade and what to improve."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "url": {"type": "STRING", "description": "Site address or domain, e.g. exemplo.com or https://exemplo.com"},
        },
        "required": ["url"],
    },
}

TEMPO_LIMITE = 12  # segundos
CABECALHOS_BONS = {
    "strict-transport-security": "HSTS (força o cadeado em todas as visitas)",
    "content-security-policy": "CSP (bloqueia scripts estranhos)",
    "x-frame-options": "proteção contra o site ser copiado dentro de outro (clickjacking)",
    "x-content-type-options": "impede o navegador de 'adivinhar' tipos de arquivo",
    "referrer-policy": "controla o que é enviado ao sair do site",
    "permissions-policy": "limita câmera, microfone e localização",
}
NAVEGADOR = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) JarvisUltron/1.0 (verificacao de seguranca)"


def _normalizar(url: str) -> tuple[str, str]:
    """Devolve (url_https, dominio). Aceita 'exemplo.com', 'http://...', 'https://...'."""
    url = str(url or "").strip().strip("<>\"' ")
    if not url:
        raise ValueError("faltou o endereço do site")
    if "://" not in url:
        url = "https://" + url
    dominio = re.sub(r"^\w+://", "", url).split("/")[0].split("@")[-1].split(":")[0]
    if not re.match(r"^[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", dominio):
        raise ValueError(f"'{dominio}' não parece um endereço de site válido")
    _recusar_endereco_interno(dominio)
    return "https://" + dominio + re.sub(r"^\w+://[^/]+", "", url), dominio


def _recusar_endereco_interno(dominio: str) -> None:
    """Não deixa checar endereços internos da rede/computador (evita bisbilhotar rede interna)."""
    import ipaddress
    import socket

    try:
        infos = socket.getaddrinfo(dominio, None)
    except OSError:
        return  # não resolveu: a conexão vai falhar sozinha depois
    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except ValueError:
            continue
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise ValueError("esse endereço é interno da rede; só analiso sites da internet")


def _certificado(dominio: str) -> dict:
    """Lê o certificado TLS (uma conexão, sem enviar nada). Devolve {ok, dias, emissor, erro}."""
    contexto = ssl.create_default_context()
    try:
        with socket.create_connection((dominio, 443), timeout=TEMPO_LIMITE) as bruto:
            with contexto.wrap_socket(bruto, server_hostname=dominio) as seguro:
                cert = seguro.getpeercert()
    except ssl.SSLCertVerificationError as erro:
        return {"ok": False, "erro": f"certificado inválido ({getattr(erro, 'verify_message', erro)})"}
    except (socket.timeout, TimeoutError):
        return {"ok": False, "erro": "o site demorou demais para responder na porta segura (443)"}
    except (socket.gaierror, ConnectionError, OSError, ssl.SSLError) as erro:
        return {"ok": False, "erro": f"não consegui uma conexão segura ({str(erro)[:80]})"}
    try:
        vence = datetime.strptime(cert["notAfter"], "%b %d %H:%M:%S %Y %Z").replace(tzinfo=timezone.utc)
        dias = (vence - datetime.now(timezone.utc)).days
    except (KeyError, ValueError):
        dias = None
    emissor = ""
    for parte in cert.get("issuer", ()):
        for chave, valor in parte:
            if chave == "organizationName":
                emissor = valor
    return {"ok": True, "dias": dias, "emissor": emissor, "vence": cert.get("notAfter", "")}


def _buscar(url: str) -> dict:
    """Faz um GET normal (como um navegador) e devolve status, cabeçalhos e a url final."""
    pedido = urllib.request.Request(url, headers={"User-Agent": NAVEGADOR}, method="GET")
    contexto = ssl.create_default_context()
    with urllib.request.urlopen(pedido, timeout=TEMPO_LIMITE, context=contexto) as resposta:
        cabecalhos = {k.lower(): v for k, v in resposta.headers.items()}
        return {"status": resposta.status, "url_final": resposta.geturl(), "cabecalhos": cabecalhos}


def _http_vira_https(dominio: str) -> bool | None:
    """O endereço http:// (sem cadeado) é levado para o https://?"""
    try:
        pedido = urllib.request.Request("http://" + dominio, headers={"User-Agent": NAVEGADOR}, method="HEAD")
        with urllib.request.urlopen(pedido, timeout=TEMPO_LIMITE) as resposta:
            return resposta.geturl().startswith("https://")
    except urllib.error.HTTPError as erro:
        destino = erro.headers.get("Location", "") if erro.headers else ""
        return destino.startswith("https://") if destino else None
    except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError, OSError):
        return None


def analisar(url_bruta: str) -> dict:
    """Junta tudo e calcula a nota. Não levanta erro: devolve sempre um dicionário."""
    try:
        url, dominio = _normalizar(url_bruta)
    except ValueError as erro:
        return {"erro": str(erro), "dominio": str(url_bruta)}

    resultado: dict = {"dominio": dominio, "pontos": 0, "de": 0, "bom": [], "melhorar": [], "grave": []}
    cert = _certificado(dominio)
    resultado["de"] += 3
    if not cert["ok"]:
        resultado["grave"].append(f"Sem cadeado confiável: {cert['erro']}.")
    else:
        resultado["pontos"] += 2
        resultado["bom"].append(f"Cadeado válido, emitido por {cert.get('emissor') or 'uma autoridade conhecida'}.")
        dias = cert.get("dias")
        if dias is None:
            resultado["pontos"] += 1
        elif dias < 0:
            resultado["grave"].append("O certificado está VENCIDO. Renove com urgência.")
        elif dias < 15:
            resultado["melhorar"].append(f"O certificado vence em {dias} dias. Renove logo.")
        else:
            resultado["pontos"] += 1
            resultado["bom"].append(f"Certificado válido por mais {dias} dias.")

    try:
        pagina = _buscar(url)
    except urllib.error.HTTPError as erro:
        pagina = {"status": erro.code, "url_final": url, "cabecalhos": {k.lower(): v for k, v in (erro.headers or {}).items()}}
    except (urllib.error.URLError, ssl.SSLError, socket.timeout, TimeoutError, ConnectionError, OSError) as erro:
        resultado["grave"].append(f"Não consegui abrir o site pelo endereço seguro ({str(erro)[:70]}).")
        pagina = None

    resultado["de"] += 1
    vira = _http_vira_https(dominio)
    if vira is True:
        resultado["pontos"] += 1
        resultado["bom"].append("Quem entra sem o cadeado (http) é levado para a versão segura (https).")
    elif vira is False:
        resultado["grave"].append("O endereço sem cadeado (http) NÃO é levado para o https. Ative esse redirecionamento.")

    if pagina is not None:
        cabecalhos = pagina["cabecalhos"]
        resultado["de"] += len(CABECALHOS_BONS)
        for chave, descricao in CABECALHOS_BONS.items():
            if chave in cabecalhos:
                resultado["pontos"] += 1
                resultado["bom"].append(f"Tem {descricao}.")
            else:
                resultado["melhorar"].append(f"Falta a proteção: {descricao}.")
        servidor = cabecalhos.get("server", "")
        if re.search(r"\d", servidor):
            resultado["melhorar"].append(
                f"O site mostra a versão do programa do servidor ('{servidor}'). Esconder isso dificulta ataques.")

    nota_pct = (resultado["pontos"] / resultado["de"]) if resultado["de"] else 0
    if resultado["grave"]:
        nota_pct = min(nota_pct, 0.55)
    resultado["nota"] = _letra(nota_pct)
    resultado["percentual"] = round(nota_pct * 100)
    return resultado


def _letra(pct: float) -> str:
    for limite, letra in ((0.9, "A"), (0.8, "B"), (0.65, "C"), (0.5, "D"), (0.3, "E")):
        if pct >= limite:
            return letra
    return "F"


def _frase(r: dict) -> str:
    if r.get("erro"):
        return f"Não consegui verificar '{r['dominio']}': {r['erro']}. Peça o endereço certo ao usuário."
    partes = [f"Segurança de {r['dominio']}: nota {r['nota']} ({r['percentual']}%)."]
    if r["grave"]:
        partes.append("Grave: " + " ".join(r["grave"]))
    if r["bom"]:
        partes.append("Bom: " + " ".join(r["bom"][:4]))
    if r["melhorar"]:
        partes.append("Dá para melhorar: " + " ".join(r["melhorar"][:4]))
    partes.append("Explique isso ao usuário em português, de forma simples, e diga que é uma checagem "
                  "passiva (não é invasão).")
    return " ".join(partes)


def executar(args: dict, jarvis) -> str:
    return _frase(analisar(args.get("url", "")))
