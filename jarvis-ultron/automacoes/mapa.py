"""Mapa por voz (automação do Jarvis Ultron, Etapa 9 da reorganização).

Diga: "Jarvis, mostra no mapa a praia de Tambaú" -> abre o Google Maps no navegador com o lugar procurado.
O endereço é montado do jeito certo (https://www.google.com/maps/search/?api=1&query=...), com acentos e
espaços codificados; o assistente de referência mandava para o google.nl, sem codificar e com "&amp;".
Não usa IA na nuvem: vale no modo reserva (Groq) e no modo privado (Gemma).
"""

from __future__ import annotations

import webbrowser
from urllib.parse import quote

USA_IA_NUVEM = False

FERRAMENTA = {
    "name": "show_map",
    "description": (
        "Opens Google Maps in the browser searching for a place or address (no AI). Use for 'mostra no mapa', "
        "'onde fica', 'como chegar em'. Answer the user in Portuguese."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "place": {"type": "STRING", "description": "Place or address to search, as the user said it"},
        },
        "required": ["place"],
    },
}


def endereco_do_mapa(lugar: str) -> str:
    return "https://www.google.com/maps/search/?api=1&query=" + quote(" ".join(str(lugar or "").split()))


def executar(args: dict, jarvis) -> str:
    lugar = " ".join(str((args or {}).get("place", "")).split())
    if not lugar:
        return "Faltou dizer o lugar para mostrar no mapa."
    try:
        if not webbrowser.open(endereco_do_mapa(lugar)):
            raise RuntimeError("o navegador não abriu")
    except Exception as erro:
        return f"Não consegui abrir o mapa ({str(erro)[:60]})."
    return f"Abri o mapa de {lugar} no navegador."
