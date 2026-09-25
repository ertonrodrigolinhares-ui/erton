"""Troca uma linha do arquivo .env do Jarvis Ultron sem mexer nas outras."""

from __future__ import annotations

import re
from pathlib import Path


def atualizar_env(caminho: Path | str, chave: str, valor: str) -> None:
    caminho = Path(caminho)
    try:
        linhas = caminho.read_text(encoding="utf-8-sig").splitlines()
    except FileNotFoundError:
        linhas = []
    nova = f'{chave}="{valor}"'
    padrao = re.compile(rf"^\s*{re.escape(chave)}\s*=")
    trocou = False
    for i, linha in enumerate(linhas):
        if padrao.match(linha):
            linhas[i] = nova
            trocou = True
    if not trocou:
        linhas.append(nova)
    caminho.write_text("\n".join(linhas) + "\n", encoding="utf-8")
