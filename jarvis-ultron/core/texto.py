"""Comparar a fala do Erton com palavras, por palavra inteira (Etapa 10 da reorganização).

O assistente de referência comparava com "palavra in frase": "time" batia em "sometimes", "sim" em
"simples". Aqui a comparação é por palavra inteira, sem acento e sem maiúsculas. Nesta etapa só o código
novo usa isto (música local); as travas do "ok" (core/hermes_ponte.py) não mudam.
"""

from __future__ import annotations

import re
import unicodedata


def normalizar(fala: str) -> str:
    """Minúsculas, sem acentos, só letras/números e espaços simples: "Tambaú, João!" -> "tambau joao"."""
    sem_acento = unicodedata.normalize("NFKD", str(fala or "")).encode("ascii", "ignore").decode()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", sem_acento.lower()).split())


def palavras(fala: str) -> list[str]:
    return normalizar(fala).split()


def tem_palavra(texto: str, palavra: str) -> bool:
    """True se `palavra` (uma ou mais palavras) aparece inteira em `texto`: "time" não bate em "sometimes"."""
    alvo = normalizar(palavra)
    if not alvo:
        return False
    return f" {alvo} " in f" {normalizar(texto)} "


def tem_todas(texto: str, pedido: str) -> bool:
    """True se cada palavra do pedido aparece inteira no texto, em qualquer ordem."""
    lista = palavras(pedido)
    return bool(lista) and all(tem_palavra(texto, p) for p in lista)
