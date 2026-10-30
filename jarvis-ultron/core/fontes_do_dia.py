"""Clima e notícias sem IA na nuvem e sem PyQt (Etapa 9 da reorganização).

O buscar_clima e o buscar_noticias moraram no ui_stark.py (código de tela); agora o cérebro usa os dois
sem carregar o PyQt6. O ui_stark continua reexportando os nomes.

- Clima: wttr.in, em português, pela cidade do .env (JARVIS_CIDADE). Nunca localiza pelo IP e nunca
  diz latitude e longitude (eram os defeitos do assistente de referência).
- Notícias: RSS do Google Notícias (não precisa de chave).
- clima_falado() monta a frase que o Jarvis fala, em português.
Nada aqui usa IA: vale também no modo reserva (Groq) e no modo privado (Gemma).
"""

from __future__ import annotations

import datetime as dt
import os
import xml.etree.ElementTree as ET
from urllib.parse import quote

CIDADE_PADRAO = "Campina Grande"
DIAS = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]
TEMPO_LIMITE = 15  # segundos para a internet responder


def cidade_configurada() -> str:
    """A cidade do .env (JARVIS_CIDADE), ou a padrão. Nunca a do IP."""
    return os.environ.get("JARVIS_CIDADE", "").strip() or CIDADE_PADRAO


def _dados_do_clima(cidade: str) -> dict:
    import requests

    r = requests.get(f"https://wttr.in/{quote(cidade)}?format=j1&lang=pt", timeout=TEMPO_LIMITE,
                     headers={"User-Agent": "JarvisUltron"})
    r.raise_for_status()
    return r.json()


def buscar_clima(cidade: str) -> str:
    """As linhas do painel de clima (tela Stark e cartão do bom dia): "27°C  Parcialmente nublado",
    "Sensação 29°C · Umidade 70%" e três dias de mínima/máxima."""
    dados = _dados_do_clima(cidade)
    atual = dados["current_condition"][0]
    descricao = (atual.get("lang_pt") or atual.get("weatherDesc") or [{"value": ""}])[0]["value"]
    linhas = [f"{atual['temp_C']}°C  {descricao}", f"Sensação {atual['FeelsLikeC']}°C · Umidade {atual['humidity']}%"]
    for dia in dados.get("weather", [])[:3]:
        data = dt.date.fromisoformat(dia["date"])
        linhas.append(f"{DIAS[data.weekday()][:3]}  {dia['mintempC']}° / {dia['maxtempC']}°")
    return "\n".join(linhas)


def clima_falado(cidade: str | None = None) -> str:
    """A frase que o Jarvis fala: "Em Campina Grande agora faz 27 graus, parcialmente nublado, sensação de
    29 e umidade de 70%. Hoje, mínima de 22 e máxima de 31, com 40% de chance de chuva."."""
    cidade = (cidade or "").strip() or cidade_configurada()
    dados = _dados_do_clima(cidade)
    atual = dados["current_condition"][0]
    descricao = (atual.get("lang_pt") or atual.get("weatherDesc") or [{"value": ""}])[0]["value"].strip()
    frase = f"Em {cidade} agora faz {atual['temp_C']} graus"
    if descricao:
        frase += f", {descricao[0].lower() + descricao[1:]}"
    frase += f", sensação de {atual['FeelsLikeC']} e umidade de {atual['humidity']}%."
    hoje = (dados.get("weather") or [{}])[0]
    if hoje.get("mintempC") and hoje.get("maxtempC"):
        frase += f" Hoje, mínima de {hoje['mintempC']} e máxima de {hoje['maxtempC']}"
        chances = []
        for hora in hoje.get("hourly") or []:
            try:
                chances.append(int(hora.get("chanceofrain", 0)))
            except (TypeError, ValueError):
                continue
        if chances:
            frase += f", com {max(chances)}% de chance de chuva"
        frase += "."
    return frase


def buscar_noticias(limite: int = 5) -> list[tuple[str, str]]:
    """(título, link) das manchetes do Google Notícias em português."""
    import requests

    r = requests.get("https://news.google.com/rss?hl=pt-BR&gl=BR&ceid=BR:pt-419", timeout=TEMPO_LIMITE,
                     headers={"User-Agent": "JarvisUltron"})
    r.raise_for_status()
    itens = []
    for item in ET.fromstring(r.content).iter("item"):
        titulo = (item.findtext("title") or "").rsplit(" - ", 1)[0].strip()
        if titulo:
            itens.append((titulo, item.findtext("link") or ""))
        if len(itens) >= limite:
            break
    return itens
