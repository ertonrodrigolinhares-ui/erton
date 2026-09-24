"""Ponte entre o Jarvis Ultron (voz) e o Hermes Agent (orquestrador com sub-agentes).

- perguntar(): manda um pedido para o Hermes (API local em http://127.0.0.1:8642) e devolve a
  resposta pronta para ser falada.
- aprovar_e_executar(): registra o "ok" do Erton por alguns minutos (é o que libera a trava de
  aprovação do Hermes) e pede para o Hermes publicar/executar o que foi aprovado.

O "Instalar Hermes.bat" preenche no .env: HERMES_API_URL, HERMES_API_KEY e HERMES_JARVIS_HOME.
"""

from __future__ import annotations

import json
import os
import re
import time
import unicodedata
from datetime import datetime
from pathlib import Path

JANELA_APROVACAO = 10 * 60  # segundos em que o "ok" vale
TEMPO_MAXIMO = 15 * 60  # tarefas de agentes podem demorar

PALAVRAS_OK = (
    "ok", "okay", "aprovo", "aprovado", "aprovada", "aprova", "pode publicar", "pode postar",
    "publica", "publique", "posta", "autorizo", "autorizado", "confirmo", "confirmado", "pode sim",
    "manda ver", "pode fazer", "pode mandar", "sim",
)
PALAVRAS_NAO = ("nao", "espera", "cancela", "cancele", "negativo", "jamais", "nunca", "ainda nao")

SEM_HERMES = ("O Hermes ainda não está configurado. Dê dois cliques em 'Instalar Hermes' na pasta "
              "do Jarvis Ultron e depois abra o Jarvis de novo.")


def _normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", (texto or "").lower())
    return " ".join("".join(c for c in texto if not unicodedata.combining(c)).split())


def usuario_aprovou(fala: str) -> bool:
    """True só se a última fala do Erton tiver uma aprovação clara e nenhuma negação."""
    texto = f" {re.sub(r'[^a-z0-9 ]', ' ', _normalizar(fala))} "
    texto = " ".join(texto.split())
    texto = f" {texto} "
    if any(f" {p} " in texto for p in PALAVRAS_NAO):
        return False
    return any(f" {p} " in texto for p in PALAVRAS_OK)


def configurado() -> bool:
    return bool(os.environ.get("HERMES_API_KEY", "").strip())


def perguntar(pedido: str, tempo_maximo: float = TEMPO_MAXIMO) -> str:
    if not configurado():
        return SEM_HERMES
    import requests

    url = os.environ.get("HERMES_API_URL", "http://127.0.0.1:8642").rstrip("/") + "/v1/chat/completions"
    try:
        resposta = requests.post(
            url,
            headers={"Authorization": f"Bearer {os.environ['HERMES_API_KEY'].strip()}"},
            json={"model": "hermes-agent", "messages": [{"role": "user", "content": pedido}]},
            timeout=tempo_maximo,
        )
    except requests.exceptions.ConnectionError:
        return ("O Hermes está desligado. Ele liga sozinho com o Windows; se não ligou, abra o "
                "'Instalar Hermes' de novo ou reinicie o computador.")
    except requests.exceptions.Timeout:
        return "O Hermes demorou demais para responder. A tarefa pode continuar rodando; pergunte de novo daqui a pouco."
    if resposta.status_code == 401:
        return "A chave do Hermes no .env do Jarvis não confere. Rode o 'Instalar Hermes' de novo."
    if resposta.status_code >= 400:
        return f"O Hermes respondeu com erro {resposta.status_code}: {resposta.text[:200]}"
    try:
        return resposta.json()["choices"][0]["message"]["content"].strip() or "Pronto."
    except (ValueError, KeyError, IndexError):
        return "O Hermes respondeu num formato inesperado."


def arquivo_aprovacao() -> Path:
    pasta = os.environ.get("HERMES_JARVIS_HOME", "").strip()
    return Path(pasta) / "jarvis" / "aprovacao.json"


def registrar_aprovacao(tipo: str, agora: float | None = None) -> None:
    """Libera a trava do Hermes para 'redes' (posts) ou 'anuncios' por JANELA_APROVACAO segundos."""
    agora = agora or time.time()
    arquivo = arquivo_aprovacao()
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    try:
        dados = json.loads(arquivo.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        dados = {}
    dados[tipo] = {"ate": agora + JANELA_APROVACAO, "em": datetime.fromtimestamp(agora).isoformat(timespec="seconds")}
    arquivo.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")


def aprovar_e_executar(tipo: str, detalhes: str, ultima_fala: str) -> str:
    if tipo not in ("redes", "anuncios"):
        return "Tipo de aprovação inválido. Use 'redes' (posts) ou 'anuncios'."
    if not configurado():
        return SEM_HERMES
    if not usuario_aprovou(ultima_fala):
        return ("Não registrei aprovação: o Erton precisa dizer claramente, por exemplo, "
                "'ok, pode publicar os posts 1 e 3'. Pergunte a ele antes.")
    registrar_aprovacao(tipo)
    skill = "publicar-aprovados" if tipo == "redes" else "anuncios-meta"
    return perguntar(f"O Erton aprovou agora ({tipo}): {detalhes}. Use a skill {skill} e execute "
                     "somente o que foi aprovado.")
