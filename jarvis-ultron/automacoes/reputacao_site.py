"""Reputação e confiança de um site (automação: salve na pasta 'automacoes' e reabra o Jarvis).

Diga, por exemplo:
  - "Jarvis, esse site é confiável? loja-oferta-imperdivel.xyz"
  - "Jarvis, é seguro comprar em www.exemplo.com?"
  - "Jarvis, esse link é golpe?"

O que ele checa (só com dados PÚBLICOS, sem acessar o site por dentro):
  - há quanto tempo o domínio existe (sites de golpe costumam ser bem novos);
  - se o endereço tenta se disfarçar de um site conhecido (banco, loja, Instagram...);
  - hífens/números demais, terminações (.xyz, .top...) muito usadas por golpes;
  - se tem cadeado (HTTPS) válido.
No fim diz a confiança (boa / média / baixa) e orienta a não digitar senha ou cartão em site duvidoso.

É uma consulta de informação pública, o mesmo que olhar o CNPJ de uma empresa. Não invade nada.
"""

from __future__ import annotations

import json
import re
import socket
import ssl
import urllib.error
import urllib.request
from datetime import datetime, timezone

FERRAMENTA = {
    "name": "website_reputation_check",
    "description": (
        "Passive reputation/trust check of a website using PUBLIC data only (domain age via RDAP, "
        "look-alike/typosquatting and scam signals in the domain name, risky TLD, valid HTTPS). Use when the "
        "user asks whether a site is trustworthy, a scam, safe to buy from, or safe to enter personal data. "
        "It never accesses the site's internals or attacks anything. Answer the user in Portuguese, simply."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {"url": {"type": "STRING", "description": "Site address or domain, e.g. exemplo.com"}},
        "required": ["url"],
    },
}

TEMPO_LIMITE = 12
NAVEGADOR = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) JarvisUltron/1.0 (verificacao de reputacao)"
TLDS_ARRISCADAS = {"zip", "mov", "xyz", "top", "click", "gq", "cf", "tk", "ml", "work", "loan",
                   "country", "kim", "science", "stream", "download", "review", "date", "rest"}
MARCAS_COMUNS = ("google", "facebook", "instagram", "whatsapp", "nubank", "bradesco", "itau",
                 "santander", "caixa", "mercadolivre", "correios", "apple", "microsoft",
                 "netflix", "amazon", "receita", "serasa", "magalu", "americanas")


def _normalizar(url: str) -> str:
    url = str(url or "").strip().strip("<>\"' ")
    if not url:
        raise ValueError("faltou o endereço do site")
    dominio = re.sub(r"^\w+://", "", url).split("/")[0].split("@")[-1].split(":")[0].lower()
    if not re.match(r"^[a-z0-9.-]+\.[a-z]{2,}$", dominio):
        raise ValueError(f"'{dominio}' não parece um endereço de site válido")
    return dominio


def _cadeado_ok(dominio: str) -> bool:
    contexto = ssl.create_default_context()
    try:
        with socket.create_connection((dominio, 443), timeout=TEMPO_LIMITE) as bruto:
            with contexto.wrap_socket(bruto, server_hostname=dominio):
                return True
    except (ssl.SSLError, socket.timeout, TimeoutError, ConnectionError, OSError):
        return False


def _rdap_criacao(dominio: str) -> datetime | None:
    """Data de registro do domínio pelo RDAP (público, JSON). None se não der."""
    try:
        pedido = urllib.request.Request("https://rdap.org/domain/" + dominio,
                                        headers={"User-Agent": NAVEGADOR, "Accept": "application/rdap+json"})
        with urllib.request.urlopen(pedido, timeout=TEMPO_LIMITE) as resposta:
            dados = json.loads(resposta.read().decode("utf-8", "replace"))
    except (urllib.error.URLError, socket.timeout, TimeoutError, ValueError, OSError):
        return None
    for evento in dados.get("events", []):
        if str(evento.get("eventAction", "")).lower() in ("registration", "registered"):
            try:
                return datetime.fromisoformat(str(evento["eventDate"]).replace("Z", "+00:00"))
            except (KeyError, ValueError):
                return None
    return None


def sinais_do_nome(dominio: str) -> list[str]:
    """Pistas de golpe que estão no próprio endereço (sem acessar o site)."""
    alertas = []
    if "xn--" in dominio:
        alertas.append("O endereço usa caracteres disfarçados (pode imitar outro site).")
    if dominio.count("-") >= 3:
        alertas.append("O endereço tem muitos hífens, comum em sites de golpe.")
    if len(re.findall(r"\d", dominio)) >= 4:
        alertas.append("O endereço tem muitos números, comum em sites de golpe.")
    tld = dominio.rsplit(".", 1)[-1]
    if tld in TLDS_ARRISCADAS:
        alertas.append(f"A terminação '.{tld}' é muito usada por sites suspeitos.")
    for marca in MARCAS_COMUNS:
        if marca in dominio and not (dominio == marca + ".com" or dominio.endswith("." + marca + ".com")
                                     or dominio.endswith(marca + ".com.br") or dominio.endswith("." + marca + ".com.br")):
            alertas.append(f"O endereço usa o nome '{marca}' fora do site oficial: pode ser uma imitação.")
            break
    return alertas


def reputacao(url_bruta: str, agora: datetime | None = None) -> dict:
    try:
        dominio = _normalizar(url_bruta)
    except ValueError as erro:
        return {"erro": str(erro), "dominio": str(url_bruta)}
    agora = agora or datetime.now(timezone.utc)
    r = {"dominio": dominio, "alertas": list(sinais_do_nome(dominio)), "bom": []}
    criado = _rdap_criacao(dominio)
    r["idade"] = None
    if criado is not None:
        if criado.tzinfo is None:  # RDAP às vezes devolve data sem fuso; evita erro ao subtrair
            criado = criado.replace(tzinfo=timezone.utc)
        dias = (agora - criado).days
        r["idade"] = dias
        if dias < 90:
            r["alertas"].append(f"O domínio foi criado há só {dias} dias. Sites de golpe costumam ser bem novos.")
        elif dias < 365:
            r["bom"].append(f"O domínio existe há {dias} dias.")
        else:
            r["bom"].append(f"O domínio existe há {dias // 365} ano(s), o que passa mais confiança.")
    if _cadeado_ok(dominio):
        r["bom"].append("Tem cadeado (HTTPS) válido.")
    else:
        r["alertas"].append("Não tem um cadeado confiável: cuidado ao digitar dados.")
    r["confianca"] = "baixa" if len(r["alertas"]) >= 2 else ("média" if r["alertas"] else "boa")
    return r


def _frase(r: dict) -> str:
    if r.get("erro"):
        return f"Não consegui checar '{r['dominio']}': {r['erro']}. Peça o endereço certo ao usuário."
    partes = [f"Confiança de {r['dominio']}: {r['confianca']}."]
    if r["alertas"]:
        partes.append("Sinais de alerta: " + " ".join(r["alertas"]))
    if r["bom"]:
        partes.append("A favor: " + " ".join(r["bom"]))
    if r["confianca"] != "boa":
        partes.append("Oriente o usuário a NÃO digitar senha, dados ou cartão nesse site sem confirmar que é o oficial.")
    partes.append("Explique ao usuário em português, de forma simples. É uma consulta de dados públicos, não é invasão.")
    return " ".join(partes)


def executar(args: dict, jarvis) -> str:
    return _frase(reputacao(args.get("url", "")))
