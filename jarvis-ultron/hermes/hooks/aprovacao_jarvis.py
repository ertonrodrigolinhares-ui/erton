"""Trava de aprovação do Jarvis (gancho pre_tool_call do Hermes).

Toda vez que o Hermes vai usar uma ferramenta do Metricool (redes sociais) ou do Meta
(anúncios), este script roda antes. Ferramentas que só LEEM (métricas, listas, relatórios)
passam direto. Ferramentas que PUBLICAM, AGENDAM, EDITAM, APAGAM ou GASTAM só passam se o
Erton tiver dado o "ok" nos últimos minutos. O "ok" é registrado pelo Jarvis Ultron no
arquivo jarvis/aprovacao.json dentro da pasta do perfil do Hermes.

Assim, a rotina das 8h pode preparar tudo, mas nunca publica sozinha.

Protocolo do Hermes: recebe um JSON pela entrada padrão e responde um JSON pela saída.
Sem resposta = pode seguir. {"action": "block", ...} = bloqueia.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

# servidor MCP (nome no config.yaml) -> tipo de aprovação necessário
CATEGORIAS = {"metricool": "redes", "meta_ads": "anuncios"}

PALAVRAS_ESCRITA = (
    "create", "publish", "post", "schedule", "update", "edit", "delete", "remove", "pause",
    "activate", "enable", "disable", "set", "upload", "send", "duplicate", "boost", "budget",
    "launch", "approve", "reschedule", "cancel", "add", "modify", "change", "write", "save",
)
PALAVRAS_LEITURA = (
    "get", "list", "search", "read", "fetch", "find", "best_time", "analytics", "analyze",
    "report", "insight", "stats", "metric", "overview", "describe", "show", "lookup", "preview",
    "estimate", "check", "summary", "status",
)

MENSAGEM = {
    "redes": ("Publicação bloqueada: falta o 'ok' do Erton. Salve o post como proposta e peça "
              "aprovação. Ele aprova dizendo ao Jarvis, por exemplo: 'ok, pode publicar'."),
    "anuncios": ("Alteração de anúncio bloqueada: falta o 'ok' do Erton. Descreva a mudança (e o "
                 "custo, se houver) e peça aprovação antes de mexer em qualquer campanha."),
}


def pasta_do_perfil() -> Path:
    return Path(os.environ.get("HERMES_HOME") or Path.home() / ".hermes")


def arquivo_aprovacao() -> Path:
    return pasta_do_perfil() / "jarvis" / "aprovacao.json"


def separar(nome_ferramenta: str) -> tuple[str, str] | None:
    """'mcp__metricool__create_post' -> ('metricool', 'create_post')."""
    achado = re.match(r"^mcp__([^_].*?)__(.+)$", nome_ferramenta or "")
    return (achado.group(1), achado.group(2)) if achado else None


def eh_escrita(ferramenta: str) -> bool:
    """Decide pelo verbo do começo do nome ("get_...", "create_..."); em dúvida, trata como
    escrita (mais seguro)."""
    nome = ferramenta.lower()
    if nome.startswith(PALAVRAS_LEITURA):
        return False
    if nome.startswith(PALAVRAS_ESCRITA):
        return True
    palavras = [p for p in re.split(r"[^a-z]+", nome) if p]
    if any(p.startswith(PALAVRAS_ESCRITA) for p in palavras):
        return True
    return not any(p.startswith(PALAVRAS_LEITURA) for p in palavras)


def aprovado(categoria: str, agora: float | None = None) -> bool:
    try:
        dados = json.loads(arquivo_aprovacao().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return float(dados.get(categoria, {}).get("ate", 0)) > (agora or time.time())


def decidir(evento: dict, agora: float | None = None) -> dict | None:
    partes = separar(evento.get("tool_name") or "")
    if not partes:
        return None
    servidor, ferramenta = partes
    categoria = CATEGORIAS.get(servidor)
    if categoria is None or not eh_escrita(ferramenta):
        return None
    if aprovado(categoria, agora):
        return None
    return {"action": "block", "message": MENSAGEM[categoria]}


def main() -> None:
    try:
        evento = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        evento = {}
    resposta = decidir(evento)
    if resposta:
        print(json.dumps(resposta, ensure_ascii=False))


if __name__ == "__main__":
    main()
