"""Lê e troca linhas do arquivo .env do Jarvis Ultron sem mexer nas outras."""

from __future__ import annotations

import re
from pathlib import Path


def ler_texto_env(caminho: Path | str) -> str:
    """Texto do .env, aceitando UTF-8 (com ou sem BOM) e a página de código do console do Windows.

    O iniciador grava o .env pelo console (ex.: a cidade "João Pessoa" em cp850); o Bloco de Notas
    e o próprio Jarvis gravam em UTF-8. Tenta UTF-8 primeiro e só cai para cp850/cp1252 quando o
    arquivo não é UTF-8 válido. Os instaladores .ps1 usam a mesma regra no Definir-Env.
    Arquivo que não existe levanta FileNotFoundError, como antes.
    """
    bruto = Path(caminho).read_bytes()
    for codificacao in ("utf-8-sig", "cp850", "cp1252"):
        try:
            return bruto.decode(codificacao)
        except UnicodeDecodeError:
            continue
    return bruto.decode("utf-8", errors="replace")


def atualizar_env(caminho: Path | str, chave: str, valor: str) -> None:
    caminho = Path(caminho)
    try:
        linhas = ler_texto_env(caminho).splitlines()
    except FileNotFoundError:
        linhas = []
    # Protege o .env: tira quebras de linha e escapa aspas/barra, para um caractere estranho colado
    # não quebrar o arquivo nem inventar linhas.
    valor = str(valor).replace("\r", " ").replace("\n", " ").replace("\\", "\\\\").replace('"', '\\"')
    nova = f'{chave}="{valor}"'
    padrao = re.compile(rf"^\s*{re.escape(chave)}\s*=")
    trocou = False
    for i, linha in enumerate(linhas):
        if padrao.match(linha):
            linhas[i] = nova
            trocou = True
    if not trocou:
        linhas.append(nova)
    # Grava sempre em UTF-8 sem BOM: um .env que veio na página de código do console vira UTF-8 aqui,
    # e o main.py lê UTF-8 primeiro.
    caminho.write_text("\n".join(linhas) + "\n", encoding="utf-8")
