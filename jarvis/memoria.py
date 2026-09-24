"""Memória de longo prazo do Jarvis: fatos que você pede para ele lembrar.

Fica em Documentos\\Jarvis\\memoria.json e entra nas instruções da IA em toda conversa.
"""

import json
from datetime import date

from . import config


def _arquivo():
    return config.PASTA_TRABALHO / "memoria.json"


def carregar() -> dict:
    try:
        return json.loads(_arquivo().read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _salvar(memorias: dict) -> None:
    _arquivo().parent.mkdir(parents=True, exist_ok=True)
    _arquivo().write_text(json.dumps(memorias, ensure_ascii=False, indent=2), encoding="utf-8")


def lembrar(assunto: str, informacao: str) -> str:
    memorias = carregar()
    memorias[assunto.strip().lower()] = {"informacao": informacao.strip(), "data": date.today().isoformat()}
    _salvar(memorias)
    return f"Guardei na memória: {assunto}."


def esquecer(assunto: str) -> str:
    memorias = carregar()
    if memorias.pop(assunto.strip().lower(), None) is None:
        return f"Não havia nada guardado sobre {assunto}."
    _salvar(memorias)
    return f"Esqueci o que sabia sobre {assunto}."


def texto_para_prompt() -> str:
    memorias = carregar()
    if not memorias:
        return ""
    linhas = [f"- {assunto}: {dados['informacao']}" for assunto, dados in memorias.items()]
    return "\n\nO que você já sabe (memória guardada a pedido do usuário):\n" + "\n".join(linhas)
