"""Pacote do dono: agentes e habilidades que são de UMA pessoa (por exemplo, o perfil de atleta de quem
criou o Jarvis), fora do produto que o cliente recebe.

Ficam em pacotes/<nome>/ (claude/skills, hermes/agentes-futuros, hermes/skills/jarvis) e só entram
quando o .env diz JARVIS_PACOTE=<nome>: no PC de quem tem o pacote, os agentes aparecem no "Ativar
Agentes", no painel Ultron e no Claude como os outros; no PC do cliente, não existem.
"""

from __future__ import annotations

import os
import re
from pathlib import Path


def raiz() -> Path:
    return Path(__file__).resolve().parents[1]


def nome() -> str:
    """O nome do pacote ligado no .env (só letras, números e -), ou vazio."""
    valor = os.environ.get("JARVIS_PACOTE", "").strip().lower()
    return valor if re.fullmatch(r"[a-z0-9][a-z0-9-]{0,40}", valor) else ""


def pasta(base: Path | None = None) -> Path | None:
    """A pasta do pacote ligado, se existir."""
    if not nome():
        return None
    caminho = (base or raiz()) / "pacotes" / nome()
    return caminho if caminho.is_dir() else None


def pastas_de_skills(base: Path | None = None) -> list[Path]:
    """As pastas de agentes do Claude: a do produto (claude/skills) e, se ligado, a do pacote."""
    base = base or raiz()
    pastas = [base / "claude" / "skills"]
    do_pacote = pasta(base)
    if do_pacote and (do_pacote / "claude" / "skills").is_dir():
        pastas.append(do_pacote / "claude" / "skills")
    return pastas
