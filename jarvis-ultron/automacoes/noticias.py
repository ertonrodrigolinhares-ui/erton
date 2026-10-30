"""Notícias lidas em voz alta (automação do Jarvis Ultron, Etapa 9 da reorganização).

Diga, por exemplo:
  - "Jarvis, quais são as notícias?"  ->  ele lê de 3 a 5 manchetes do Google Notícias (sem chave, sem IA)
  - depois: "abre a segunda"          ->  só abre a matéria no navegador depois do seu "sim"/"ok"

O "sim" é conferido no código (core/aprovacao.py): tem de ser uma fala sua DEPOIS de ouvir as manchetes.
Sem ele, nada abre. Não usa IA na nuvem: vale no modo reserva (Groq) e no modo privado (Gemma).
"""

from __future__ import annotations

import threading
import time
import webbrowser

from core import aprovacao
from core.fontes_do_dia import buscar_noticias

USA_IA_NUVEM = False

FERRAMENTA = {
    "name": "news_headlines",
    "description": (
        "Reads the latest Brazilian news headlines (Google News RSS, no AI). action=list reads 3 to 5 headlines; "
        "say them to the user in Portuguese and ask if they want to open one. action=open opens headline "
        "`number` in the browser, but ONLY after the user clearly said yes/ok in a new sentence after hearing "
        "the headlines (the code checks this). Use for 'quais as notícias', 'manchetes de hoje'."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "description": "list | open"},
            "number": {"type": "INTEGER", "description": "Headline number to open (open)"},
            "limit": {"type": "INTEGER", "description": "How many headlines to read (3 to 5; default 4)"},
        },
        "required": ["action"],
    },
}

VALIDADE = 10 * 60  # segundos em que "abre a N" ainda vale depois das manchetes lidas

_trava = threading.Lock()
_ultimas: dict = {}  # {"itens": [(titulo, link)], "em": instante, "marca": fala em que foram lidas}


def _listar(limite: int, jarvis) -> str:
    limite = max(3, min(5, int(limite or 4)))
    try:
        itens = buscar_noticias(limite)
    except Exception as erro:
        return f"Não consegui buscar as notícias agora ({str(erro)[:60]}). Confira a internet."
    if not itens:
        return "Não encontrei notícias agora."
    with _trava:
        _ultimas.clear()
        _ultimas.update(itens=itens, em=time.monotonic(), marca=aprovacao.marca(jarvis))
    linhas = [f"{i}. {titulo}" for i, (titulo, _) in enumerate(itens, 1)]
    return ("Manchetes de agora:\n" + "\n".join(linhas) +
            "\nTell the user these headlines in Portuguese and ask if they want to open one (by number).")


def _abrir(numero, jarvis) -> str:
    with _trava:
        itens = list(_ultimas.get("itens") or [])
        valido = itens and time.monotonic() - _ultimas.get("em", 0) < VALIDADE
        aprovou = valido and aprovacao.aprovou_depois(jarvis, _ultimas.get("marca", 0))
    if not valido:
        return "Primeiro peça as notícias (action=list); depois escolha qual abrir."
    try:
        indice = int(numero)
    except (TypeError, ValueError):
        indice = 0
    if not 1 <= indice <= len(itens):
        return f"Escolha um número de 1 a {len(itens)}."
    if not aprovou:
        return (f"Não abri a notícia {indice}: só abro depois de um 'sim' seu, numa fala nova, depois de ouvir "
                "as manchetes. Pergunte ao usuário se pode abrir.")
    titulo, link = itens[indice - 1]
    if not link:
        return f"A notícia {indice} veio sem endereço; não consegui abrir."
    try:
        webbrowser.open(link)
    except Exception as erro:
        return f"Não consegui abrir o navegador ({str(erro)[:60]})."
    return f"Abri no navegador: {titulo}."


def executar(args: dict, jarvis) -> str:
    acao = str((args or {}).get("action", "list")).strip().lower()
    if acao == "open":
        return _abrir((args or {}).get("number"), jarvis)
    return _listar((args or {}).get("limit", 4), jarvis)
