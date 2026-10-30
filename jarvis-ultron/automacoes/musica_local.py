"""Música do próprio PC, sem internet (automação do Jarvis Ultron, Etapa 10 da reorganização).

Diga: "Jarvis, toca Evidências do meu PC" -> procura na pasta Música (e subpastas) um arquivo cujo nome
tenha todas as palavras pedidas, inteiras (core/texto.py: "sim" não bate em "simples"), e abre no programa
de música padrão do Windows. Achando várias, diz quantas achou e lista as primeiras, em vez de sortear.
Não usa IA nem internet: vale no modo privado.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from core.texto import tem_todas

USA_IA_NUVEM = False

FERRAMENTA = {
    "name": "local_music",
    "description": (
        "Plays a song that is on the user's own computer (Music folder), with no internet. Use when the user "
        "asks to play a song 'do meu PC', 'do computador', 'da minha pasta' or names a file. `title`: the "
        "words the user said. If several files match, the result lists them: ask the user which one. "
        "Answer the user in Portuguese."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "title": {"type": "STRING", "description": "Song or artist words, as the user said them"},
        },
        "required": ["title"],
    },
}

EXTENSOES = {".mp3", ".m4a", ".flac", ".wav", ".ogg", ".wma", ".aac", ".opus"}
MOSTRAR_NO_MAXIMO = 5


def pasta_musica() -> Path:
    return Path(os.environ.get("JARVIS_PASTA_MUSICA", "").strip() or (Path.home() / "Music"))


def procurar(pedido: str, pasta: Path | None = None) -> list[Path]:
    pasta = pasta or pasta_musica()
    if not pasta.is_dir():
        return []
    achados = []
    for caminho in sorted(pasta.rglob("*")):
        if caminho.suffix.lower() in EXTENSOES and tem_todas(caminho.stem, pedido):
            achados.append(caminho)
    return achados


def tocar(caminho: Path) -> None:
    """Abre no programa de música padrão (Windows: os.startfile; outros: o abridor do sistema)."""
    if hasattr(os, "startfile"):
        os.startfile(str(caminho))  # noqa: S606 - abre o arquivo do próprio usuário no programa padrão
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(caminho)])
    else:
        subprocess.Popen(["xdg-open", str(caminho)])


def executar(args: dict, jarvis) -> str:
    pedido = " ".join(str((args or {}).get("title", "")).split())
    if not pedido:
        return "Faltou dizer qual música."
    achados = procurar(pedido)
    if not achados:
        return f"Não achei nenhuma música com '{pedido}' na pasta Música ({pasta_musica()})."
    if len(achados) > 1:
        nomes = "; ".join(c.stem for c in achados[:MOSTRAR_NO_MAXIMO])
        extra = f" e mais {len(achados) - MOSTRAR_NO_MAXIMO}" if len(achados) > MOSTRAR_NO_MAXIMO else ""
        return (f"Achei {len(achados)} músicas com '{pedido}': {nomes}{extra}. "
                "Pergunte ao usuário qual delas tocar.")
    try:
        tocar(achados[0])
    except OSError as erro:
        return f"Não consegui abrir a música ({str(erro)[:60]})."
    return f"Tocando {achados[0].stem}."
