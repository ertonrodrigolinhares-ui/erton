"""Pendências do Geekie One e lembretes de prazo (Jarvis Ultron).

O Hermes (skill geekie-pendencias, às 7h e às 18h) lê as atividades do aluno no Geekie One, sem
alterar nada, e grava a lista em <perfil jarvis do Hermes>/jarvis/geekie/pendencias.json.
Aqui o Jarvis lê essa lista, monta o resumo falado e decide quais lembretes dar
("faltam 2 dias para a atividade de História"), um por atividade por dia.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

DIAS_AVISO = 2  # avisa quando faltam 2 dias ou menos (e no dia)
VALIDADE_HORAS = 14  # lista mais velha que isso: pede ao Hermes para ler de novo


@dataclass
class Atividade:
    disciplina: str
    titulo: str
    prazo: date | None
    status: str

    @property
    def chave(self) -> str:
        return f"{self.disciplina}|{self.titulo}|{self.prazo or ''}"


def pasta(base: Path | str | None = None) -> Path | None:
    raiz = base or os.environ.get("HERMES_JARVIS_HOME", "").strip()
    return Path(raiz) / "jarvis" / "geekie" if raiz else None


def _data(texto: str) -> date | None:
    try:
        return date.fromisoformat(str(texto or "")[:10])
    except ValueError:
        return None


def ler(base: Path | str | None = None) -> tuple[list[Atividade], datetime | None]:
    """(atividades, quando o Hermes atualizou). Lista vazia se ainda não houver arquivo."""
    local = pasta(base)
    if local is None:
        return [], None
    try:
        dados = json.loads((local / "pendencias.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return [], None
    atividades = [
        Atividade(str(a.get("disciplina", "")).strip(), str(a.get("titulo", "")).strip(),
                  _data(a.get("prazo", "")), str(a.get("status", "pendente")).strip().lower())
        for a in dados.get("atividades", []) if isinstance(a, dict)
    ]
    try:
        atualizado = datetime.fromisoformat(str(dados.get("atualizado_em", ""))[:16])
    except ValueError:
        atualizado = None
    return atividades, atualizado


def desatualizada(atualizado: datetime | None, agora: datetime | None = None) -> bool:
    agora = agora or datetime.now()
    return atualizado is None or (agora - atualizado).total_seconds() > VALIDADE_HORAS * 3600


def abertas(atividades: list[Atividade]) -> list[Atividade]:
    """Pendentes e atrasadas, das que vencem primeiro para as sem prazo."""
    pendentes = [a for a in atividades if a.status != "feita"]
    return sorted(pendentes, key=lambda a: (a.prazo is None, a.prazo or date.max, a.disciplina))


def _quando(prazo: date | None, hoje: date) -> str:
    if prazo is None:
        return "sem prazo"
    dias = (prazo - hoje).days
    if dias < 0:
        return f"atrasada desde {prazo:%d/%m}"
    if dias == 0:
        return "vence hoje"
    if dias == 1:
        return "vence amanhã"
    return f"até {prazo:%d/%m} (faltam {dias} dias)"


def resumo(atividades: list[Atividade], hoje: date | None = None, limite: int = 6) -> str:
    hoje = hoje or date.today()
    lista = abertas(atividades)
    if not lista:
        return "Não há atividades pendentes no Geekie."
    partes = [f"{a.disciplina}: {a.titulo}, {_quando(a.prazo, hoje)}" for a in lista[:limite]]
    extra = f" E mais {len(lista) - limite}." if len(lista) > limite else ""
    total = len(lista)
    return (f"No Geekie há {total} atividade{'s' if total > 1 else ''} pendente{'s' if total > 1 else ''}: "
            + "; ".join(partes) + "." + extra)


def lembretes_do_dia(atividades: list[Atividade], ja_avisados: dict, hoje: date | None = None) -> list[Atividade]:
    """Atividades abertas que vencem em até DIAS_AVISO dias (ou atrasadas) e ainda não foram
    lembradas hoje."""
    hoje = hoje or date.today()
    devidas = []
    for a in abertas(atividades):
        if a.prazo is None or (a.prazo - hoje).days > DIAS_AVISO:
            continue
        if ja_avisados.get(a.chave) == hoje.isoformat():
            continue
        devidas.append(a)
    return devidas


def frase_lembrete(a: Atividade, hoje: date | None = None) -> str:
    hoje = hoje or date.today()
    dias = (a.prazo - hoje).days if a.prazo else None
    if dias is None:
        return f"Lembrete do Geekie: {a.disciplina}, {a.titulo}."
    if dias < 0:
        return f"Atenção: a atividade de {a.disciplina}, {a.titulo}, está atrasada."
    if dias == 0:
        return f"Lembrete: a atividade de {a.disciplina}, {a.titulo}, vence hoje."
    if dias == 1:
        return f"Lembrete: a atividade de {a.disciplina}, {a.titulo}, vence amanhã."
    return f"Lembrete: faltam {dias} dias para a atividade de {a.disciplina}, {a.titulo}."


def carregar_avisados(base: Path | str | None = None) -> dict:
    local = pasta(base)
    try:
        return json.loads((local / "lembretes.json").read_text(encoding="utf-8")) if local else {}
    except (OSError, ValueError):
        return {}


def marcar_avisados(itens: list[Atividade], base: Path | str | None = None, hoje: date | None = None) -> None:
    local = pasta(base)
    if local is None:
        return
    hoje = hoje or date.today()
    avisados = carregar_avisados(base)
    for a in itens:
        avisados[a.chave] = hoje.isoformat()
    local.mkdir(parents=True, exist_ok=True)
    (local / "lembretes.json").write_text(json.dumps(avisados, ensure_ascii=False, indent=2), encoding="utf-8")
