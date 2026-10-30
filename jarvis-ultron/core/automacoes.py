"""Automações em um arquivo só (Jarvis Ultron).

Coloque o arquivo na pasta `automacoes` do Jarvis e abra o Jarvis de novo. Dois tipos:

1. `nome.py`: uma ferramenta nova que o Jarvis usa por voz. O arquivo precisa ter:
       FERRAMENTA = {"name": "nome_em_ingles", "description": "...", "parameters": {...}}
       def executar(args: dict, jarvis) -> str: ...
   (a mesma forma das ferramentas do Gemini; "parameters" pode ser omitido).
   Opcional: `def iniciar(jarvis): ...` roda uma vez quando o Jarvis abre (para automações que
   trabalham sozinhas, como lembretes, ou que acrescentam algo na tela). Um arquivo pode ter só o
   `iniciar`, sem FERRAMENTA. Para mexer na tela, use `core.na_tela.executar(funcao)` e ponha
   `NA_TELA = True` no arquivo (assim o `iniciar` roda no programa da tela).
   Se a ferramenta manda o pedido para uma IA na nuvem (Gemini, Claude, Hermes...), ponha
   `USA_IA_NUVEM = True`: no modo privado ela não é oferecida ao Gemma nem roda.
   Toda automação é tratada como algo que MUDA alguma coisa: num lote do Gemini, roda em fila, uma
   depois da outra. Se a sua só lê (não abre nada, não grava, não envia), ponha `MUDA_ALGO = False`
   para ela poder rodar junto com as outras.

2. `nome.md`: um agente/habilidade para o Hermes (mesmo formato de SKILL.md, com
   `name:` no cabeçalho). O Jarvis copia para o perfil jarvis do Hermes ao abrir. Se o cabeçalho
   tiver `agenda: "0 7 * * *"`, a rotina é criada no Hermes nesse horário.

Arquivos que começam com "_" ou terminam em ".exemplo" são ignorados.
"""

from __future__ import annotations

import importlib.util
import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

NOME_VALIDO = re.compile(r"^[a-z][a-z0-9_]{2,40}$")


@dataclass
class Automacao:
    nome: str
    declaracao: dict
    executar: Callable
    arquivo: Path
    usa_ia_nuvem: bool = False  # USA_IA_NUVEM = True no arquivo: fica desligada no modo privado
    muda_algo: bool = True  # MUDA_ALGO = False no arquivo: só lê, pode rodar junto com outras num lote


@dataclass
class Carga:
    ferramentas: dict = field(default_factory=dict)  # nome -> Automacao
    erros: list = field(default_factory=list)  # (arquivo, motivo)
    habilidades: list = field(default_factory=list)  # nomes das skills copiadas para o Hermes
    inicios: list = field(default_factory=list)  # (arquivo, iniciar) que rodam quando o Jarvis abre
    na_tela: set = field(default_factory=set)  # arquivos cujo iniciar desenha na tela (rodam no programa da tela)


def pasta_padrao() -> Path:
    return Path(__file__).resolve().parent.parent / "automacoes"


def _arquivos(pasta: Path, extensao: str) -> list[Path]:
    if not pasta.is_dir():
        return []
    return sorted(p for p in pasta.glob(f"*{extensao}") if not p.name.startswith("_"))


def carregar_ferramentas(pasta: Path | None = None, reservados: set[str] | None = None) -> Carga:
    """Importa cada automacoes/*.py. Um arquivo com erro nunca impede o Jarvis de abrir."""
    pasta = Path(pasta or pasta_padrao())
    reservados = set(reservados or ())
    carga = Carga()
    for arquivo in _arquivos(pasta, ".py"):
        try:
            spec = importlib.util.spec_from_file_location(f"automacao_{arquivo.stem}", arquivo)
            modulo = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(modulo)
            iniciar = getattr(modulo, "iniciar", None)
            if iniciar is not None and not callable(iniciar):
                raise ValueError("'iniciar' precisa ser uma função iniciar(jarvis)")
            if iniciar is not None and _desenha_na_tela(modulo, arquivo):
                carga.na_tela.add(arquivo.name)
            if not hasattr(modulo, "FERRAMENTA"):
                if iniciar is None:
                    raise ValueError("falta FERRAMENTA (ou a função iniciar(jarvis))")
                carga.inicios.append((arquivo.name, iniciar))
                continue
            declaracao = dict(getattr(modulo, "FERRAMENTA"))
            executar = getattr(modulo, "executar", None)
            nome = str(declaracao.get("name", "")).strip()
            if not NOME_VALIDO.match(nome):
                raise ValueError(f"nome inválido '{nome}' (use letras minúsculas, números e _)")
            if nome in reservados or nome in carga.ferramentas:
                raise ValueError(f"o nome '{nome}' já existe no Jarvis")
            if not callable(executar):
                raise ValueError("falta a função executar(args, jarvis)")
            if not str(declaracao.get("description", "")).strip():
                raise ValueError("falta a descrição (description)")
            declaracao.setdefault("parameters", {"type": "OBJECT", "properties": {}})
            carga.ferramentas[nome] = Automacao(nome, declaracao, executar, arquivo,
                                                bool(getattr(modulo, "USA_IA_NUVEM", False)),
                                                bool(getattr(modulo, "MUDA_ALGO", True)))
            if iniciar is not None:
                carga.inicios.append((arquivo.name, iniciar))
        except Exception as erro:
            carga.erros.append((arquivo.name, str(erro)[:160]))
    return carga


def _desenha_na_tela(modulo, arquivo: Path) -> bool:
    """A automação mexe na janela? (NA_TELA = True no arquivo, ou usa core.na_tela.)
    Com tela e cérebro em programas separados, essas rodam no programa da tela."""
    marcado = getattr(modulo, "NA_TELA", None)
    if marcado is not None:
        return bool(marcado)
    try:
        # errors="replace": um arquivo salvo em ANSI (com "# -*- coding: cp1252 -*-") carrega normal no
        # Python; ler aqui não pode recusá-lo. "core.na_tela" é só ASCII, então ainda é achado.
        return "core.na_tela" in arquivo.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False


def _cabecalho(texto: str) -> dict:
    if not texto.startswith("---"):
        return {}
    partes = texto.split("---", 2)
    if len(partes) < 3:
        return {}
    dados = {}
    for linha in partes[1].splitlines():
        if ":" in linha and not linha.startswith((" ", "\t")):
            chave, _, valor = linha.partition(":")
            dados[chave.strip()] = valor.strip().strip('"').strip("'")
    return dados


def _hermes() -> str | None:
    raiz = os.environ.get("HERMES_HOME") or os.path.join(os.environ.get("LOCALAPPDATA", ""), "hermes")
    candidato = Path(raiz) / "bin" / ("hermes.exe" if os.name == "nt" else "hermes")
    return str(candidato) if candidato.exists() else shutil.which("hermes")


def sincronizar_habilidades(pasta: Path | None = None, perfil: Path | str | None = None,
                            criar_rotinas: bool = True) -> Carga:
    """Copia automacoes/*.md para as skills do perfil jarvis do Hermes (e cria as rotinas)."""
    pasta = Path(pasta or pasta_padrao())
    perfil = perfil or os.environ.get("HERMES_JARVIS_HOME", "").strip()
    carga = Carga()
    arquivos = _arquivos(pasta, ".md")
    arquivos = [a for a in arquivos if a.name.lower() not in {"leia-me.md", "readme.md"}]
    if not arquivos:
        return carga
    if not perfil:
        carga.erros.append(("(Hermes)", "o Hermes não está instalado; rode o 'Instalar Hermes'"))
        return carga
    pasta_jarvis = (Path(perfil) / "jarvis").as_posix()
    rotinas_existentes = None
    for arquivo in arquivos:
        try:
            texto = arquivo.read_text(encoding="utf-8")
            info = _cabecalho(texto)
            nome = info.get("name", "")
            if not re.match(r"^[a-z0-9][a-z0-9-]{2,60}$", nome):
                raise ValueError("o cabeçalho precisa de 'name:' (letras minúsculas, números e -)")
            destino = Path(perfil) / "skills" / "jarvis" / nome / "SKILL.md"
            destino.parent.mkdir(parents=True, exist_ok=True)
            destino.write_text(texto.replace("__PASTA_JARVIS__", pasta_jarvis), encoding="utf-8")
            carga.habilidades.append(nome)
            agenda = info.get("agenda", "")
            if agenda and criar_rotinas:
                hermes = _hermes()
                if not hermes:
                    raise ValueError("não achei o Hermes para criar a rotina")
                rotulo = f"Automacao {nome}"
                if rotinas_existentes is None:
                    rotinas_existentes = subprocess.run([hermes, "-p", "jarvis", "cron", "list"],
                                                        capture_output=True, text=True, timeout=60).stdout
                if rotulo not in rotinas_existentes:
                    subprocess.run([hermes, "-p", "jarvis", "cron", "create", agenda,
                                    f"Execute a automacao {nome}.", "--skill", nome,
                                    "--name", rotulo, "--deliver", "local"],
                                   capture_output=True, text=True, timeout=60)
        except Exception as erro:
            carga.erros.append((arquivo.name, str(erro)[:160]))
    return carga
