"""Clima falado, em português, com dados de verdade (Etapa 9 da reorganização).

Antes esta ação só abria uma busca do Google em inglês e dizia "Showing the weather… sir". Agora ela
lê o wttr.in (core/fontes_do_dia.py) para a cidade pedida ou a do .env (JARVIS_CIDADE) e devolve a
frase pronta. Nunca localiza pelo IP. Só abre o navegador se o usuário pedir (open_browser).
Não usa IA: vale no modo reserva (Groq) e no modo privado (Gemma).
"""

from __future__ import annotations

import webbrowser
from urllib.parse import quote

from core import fontes_do_dia


def weather_action(
    parameters: dict,
    player=None,
    session_memory=None,
) -> str:
    parameters = parameters or {}
    cidade = str(parameters.get("city") or "").strip() or fontes_do_dia.cidade_configurada()
    abrir = _verdadeiro(parameters.get("open_browser"))

    try:
        msg = fontes_do_dia.clima_falado(cidade)
    except Exception as erro:
        msg = f"Não consegui ver o clima de {cidade} agora ({str(erro)[:60]}). Confira a internet e tente de novo."
        _log(msg, player)
        return msg

    if abrir:
        try:
            if not webbrowser.open(f"https://wttr.in/{quote(cidade)}?lang=pt"):
                raise RuntimeError("o navegador não abriu")
        except Exception as erro:
            msg += f" (Não consegui abrir o navegador: {str(erro)[:60]}.)"

    _log(msg, player)
    if session_memory:
        try:
            session_memory.set_last_search(query=f"clima em {cidade}", response=msg)
        except Exception:
            pass
    return msg


def _verdadeiro(valor) -> bool:
    return str(valor or "").strip().lower() in ("1", "true", "yes", "sim")


def _log(message: str, player=None) -> None:
    print(f"[Clima] {message}")
    if player:
        try:
            player.write_log(f"JARVIS: {message}")
        except Exception:
            pass
