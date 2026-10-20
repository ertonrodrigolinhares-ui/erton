"""Perfil de quem usa o Jarvis: nome, como quer ser chamado, cidade, profissão e preferências.

É preenchido na primeira abertura (a tela "Sobre você") e usado por todos os cérebros (Gemini, Gemma,
Groq e outra empresa), pelo Claude chefe e pelo Hermes, no lugar de qualquer nome escrito no código.

Fica em Documentos\\Jarvis Ultron\\perfil.json: fora da pasta do programa (uma versão nova do Jarvis
não o perde), nunca no git, e vai junto no backup do HD externo (automacoes/memoria_hd.py copia a
pasta Documentos). O nome, a cidade e a profissão também vão para a memória (identity), que a tela e
a saudação já liam. Quem já usava o Jarvis antes do perfil continua com o nome que estava na memória:
carregar() nunca grava nada; só salvar() grava.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

CAMPOS = ("nome", "tratamento", "cidade", "profissao", "preferencias")
LIMITES = {"nome": 80, "tratamento": 40, "cidade": 60, "profissao": 120, "preferencias": 600}
_SEM_NOME = {"", "sir", "madam", "senhor", "senhora"}  # o "Sir" que a tela antiga gravava ao pular


def pasta_dados() -> Path:
    return Path.home() / "Documents" / "Jarvis Ultron"


def arquivo() -> Path:
    return pasta_dados() / "perfil.json"


def _limpar(valor, limite: int) -> str:
    texto = " ".join(str(valor or "").split())
    return texto[:limite].strip()


def _da_memoria() -> dict:
    """O que a memória (identity) já sabe: nome, cidade e profissão. Vazio se não houver."""
    try:
        from memory.memory_manager import load_memory

        identidade = load_memory().get("identity", {}) or {}
    except Exception:
        return {}

    def valor(campo):
        entrada = identidade.get(campo)
        return entrada.get("value") if isinstance(entrada, dict) else entrada

    nome = _limpar(valor("name"), LIMITES["nome"])
    if nome.lower() in _SEM_NOME:
        nome = ""
    return {"nome": nome, "cidade": _limpar(valor("city"), LIMITES["cidade"]),
            "profissao": _limpar(valor("job"), LIMITES["profissao"])}


def carregar() -> dict:
    """O perfil, com todos os CAMPOS (vazios se não houver) e "preenchido". Nunca grava."""
    dados = {}
    try:
        lido = json.loads(arquivo().read_text(encoding="utf-8-sig"))
        if isinstance(lido, dict):
            dados = lido
    except (OSError, ValueError):
        pass
    perfil = {campo: _limpar(dados.get(campo), LIMITES[campo]) for campo in CAMPOS}
    preenchido = bool(dados.get("preenchido"))
    if not perfil["nome"]:  # quem já usava o Jarvis antes do perfil: o nome fica na memória
        antigo = _da_memoria()
        for campo, valor in antigo.items():
            if not perfil[campo]:
                perfil[campo] = valor
        if antigo.get("nome"):
            preenchido = True
    if not perfil["cidade"]:
        perfil["cidade"] = _limpar(os.environ.get("JARVIS_CIDADE", ""), LIMITES["cidade"])
    perfil["preenchido"] = preenchido
    return perfil


def salvar(dados: dict) -> dict:
    """Grava o perfil (campos que não vierem ficam vazios) e marca como preenchido, mesmo vazio:
    quem pulou a tela não é perguntado de novo. O nome, a cidade e a profissão vão também para a
    memória, que a tela e a saudação leem."""
    perfil = {campo: _limpar(dados.get(campo), LIMITES[campo]) for campo in CAMPOS}
    perfil["preenchido"] = True
    caminho = arquivo()
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(json.dumps(perfil, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    identidade = {chave: {"value": perfil[campo]}
                  for campo, chave in (("nome", "name"), ("cidade", "city"), ("profissao", "job")) if perfil[campo]}
    if identidade:
        try:
            from memory.memory_manager import update_memory

            update_memory({"identity": identidade})
        except Exception as erro:
            print(f"[Perfil] Não consegui levar o perfil para a memória: {erro}")
    return perfil


def completo() -> bool:
    """A tela "Sobre você" só aparece enquanto isto for False."""
    return carregar()["preenchido"]


def nome() -> str:
    return carregar()["nome"]


def tratamento(perfil: dict | None = None) -> str:
    """Como chamar a pessoa: o que ela escolheu, senão o primeiro nome; vazio se não souber."""
    perfil = perfil or carregar()
    return perfil["tratamento"] or perfil["nome"].split(" ")[0]


def cidade() -> str:
    return carregar()["cidade"]


ROTULOS = (("nome", "Nome"), ("tratamento", "Como chamar"), ("cidade", "Cidade"),
           ("profissao", "Profissão ou área"), ("preferencias", "Preferências e objetivos"))


def bloco_para_prompt(perfil: dict | None = None) -> str:
    """O perfil como texto para os cérebros (só os campos preenchidos); vazio se não houver nada."""
    perfil = perfil or carregar()
    linhas = [f"{rotulo}: {perfil[campo]}" for campo, rotulo in ROTULOS if perfil[campo]]
    if not linhas:
        return ""
    chamar = tratamento(perfil)
    if chamar and not perfil["tratamento"]:
        linhas.insert(1, f"Como chamar: {chamar}")
    return "[SOBRE O USUÁRIO]\n" + "\n".join(linhas) + "\n"
