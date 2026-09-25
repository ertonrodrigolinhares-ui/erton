"""Lembretes falados do Jarvis Ultron (automação: salve na pasta 'automacoes' e reabra o Jarvis).

Diga, por exemplo:
  - "Jarvis, me lembra às 15h de ligar para o contador."
  - "Jarvis, daqui a 20 minutos me lembra de tirar o bolo do forno."
  - "Jarvis, todo dia às 6h me lembra do treino."        (repete todo dia)
  - "Jarvis, dias úteis às 8h me lembra de ver os e-mails." (segunda a sexta)
  - "Jarvis, quais são meus lembretes?"  /  "Jarvis, cancela o lembrete 2."

Na hora certa o Jarvis toca um som, mostra o aviso na tela e FALA o lembrete.
No modo chamada ele não interrompe: guarda o aviso e fala assim que você disser "Hey Jarvis".
Os lembretes ficam salvos em Documentos/Jarvis Ultron/lembretes.json (continuam depois de desligar).
"""

from __future__ import annotations

import json
import re
import threading
from datetime import date, datetime, timedelta
from pathlib import Path

FERRAMENTA = {
    "name": "spoken_reminders",
    "description": (
        "Spoken reminders: JARVIS says the reminder out loud at the right time (and shows it on screen). "
        "Use this (not 'reminder') whenever the user asks to be reminded of something, to list reminders or "
        "to cancel one. For 'in N minutes' use in_minutes; for a clock time use time (HH:MM, 24h) and, if "
        "not today, date (YYYY-MM-DD). repeat: none | daily | weekdays | weekly. Answer the user in Portuguese."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "description": "create | list | cancel"},
            "text": {"type": "STRING", "description": "What to remind, in Portuguese (create)"},
            "time": {"type": "STRING", "description": "Clock time HH:MM, 24h (create)"},
            "date": {"type": "STRING", "description": "YYYY-MM-DD, only if not today/next occurrence (create)"},
            "in_minutes": {"type": "INTEGER", "description": "Remind after this many minutes (create)"},
            "repeat": {"type": "STRING", "description": "none | daily | weekdays | weekly (create)"},
            "number": {"type": "INTEGER", "description": "Reminder number to cancel (cancel)"},
        },
        "required": ["action"],
    },
}

CHECAR_A_CADA = 20  # segundos
ATRASO_MAXIMO = timedelta(hours=12)  # lembrete perdido há mais tempo que isso (PC desligado): não fala mais
REPETICOES = {"none": "nao", "nao": "nao", "": "nao", "daily": "diario", "diario": "diario",
              "weekdays": "dias_uteis", "dias_uteis": "dias_uteis", "weekly": "semanal", "semanal": "semanal"}
NOME_REPETICAO = {"diario": "todo dia", "dias_uteis": "de segunda a sexta", "semanal": "toda semana"}

_trava = threading.Lock()
_iniciado = threading.Event()


def arquivo() -> Path:
    return Path.home() / "Documents" / "Jarvis Ultron" / "lembretes.json"


def ler(caminho: Path | None = None) -> dict:
    try:
        dados = json.loads((caminho or arquivo()).read_text(encoding="utf-8"))
        if isinstance(dados, dict) and isinstance(dados.get("lembretes"), list):
            return dados
    except (OSError, ValueError):
        pass
    return {"lembretes": [], "ultimo_aviso": None}


def gravar(dados: dict, caminho: Path | None = None) -> None:
    caminho = caminho or arquivo()
    caminho.parent.mkdir(parents=True, exist_ok=True)
    temporario = caminho.with_suffix(".tmp")
    temporario.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
    temporario.replace(caminho)


def proximos(dados: dict) -> list[dict]:
    return sorted(dados.get("lembretes", []), key=lambda l: l["quando"])


def _horario(texto: str) -> tuple[int, int]:
    achado = re.match(r"^\s*(\d{1,2})\s*(?:[:hH]\s*(\d{2})?)?\s*$", str(texto or ""))
    if not achado:
        raise ValueError("horário inválido (use HH:MM)")
    hora, minuto = int(achado.group(1)), int(achado.group(2) or 0)
    if hora > 23 or minuto > 59:
        raise ValueError("horário inválido (use HH:MM)")
    return hora, minuto


def calcular_quando(args: dict, agora: datetime) -> datetime:
    minutos = args.get("in_minutes")
    if minutos not in (None, "", 0):
        minutos = int(minutos)
        if minutos <= 0:
            raise ValueError("o tempo precisa ser maior que zero")
        return (agora + timedelta(minutes=minutos)).replace(second=0, microsecond=0)
    hora, minuto = _horario(args.get("time", ""))
    dia = date.fromisoformat(str(args["date"])[:10]) if args.get("date") else agora.date()
    quando = datetime.combine(dia, datetime.min.time()).replace(hour=hora, minute=minuto)
    if quando <= agora:
        if args.get("date"):
            raise ValueError("essa data e hora já passaram")
        quando += timedelta(days=1)  # "às 7h" dito depois das 7h: amanhã
    return quando


def proxima_vez(quando: datetime, repetir: str) -> datetime | None:
    if repetir == "diario":
        return quando + timedelta(days=1)
    if repetir == "semanal":
        return quando + timedelta(days=7)
    if repetir == "dias_uteis":
        seguinte = quando + timedelta(days=1)
        while seguinte.weekday() >= 5:
            seguinte += timedelta(days=1)
        return seguinte
    return None


def _falar_quando(quando: datetime, agora: datetime) -> str:
    if quando.date() == agora.date():
        dia = "hoje"
    elif quando.date() == agora.date() + timedelta(days=1):
        dia = "amanhã"
    else:
        dia = f"em {quando:%d/%m}"
    return f"{dia} às {quando:%H:%M}"


def criar(args: dict, agora: datetime | None = None, caminho: Path | None = None) -> str:
    agora = agora or datetime.now()
    texto = " ".join(str(args.get("text", "")).split())
    if not texto:
        return "Falta dizer do que lembrar. Pergunte ao usuário."
    repetir = REPETICOES.get(str(args.get("repeat", "") or "").strip().lower(), "nao")
    try:
        quando = calcular_quando(args, agora)
    except (ValueError, TypeError) as erro:
        return f"Não consegui marcar: {erro}. Pergunte ao usuário o horário."
    if repetir == "dias_uteis":
        while quando.weekday() >= 5:
            quando += timedelta(days=1)
    with _trava:
        dados = ler(caminho)
        numero = max([l.get("numero", 0) for l in dados["lembretes"]] + [0]) + 1
        dados["lembretes"].append({"numero": numero, "texto": texto, "quando": quando.isoformat(timespec="minutes"),
                                   "repetir": repetir, "criado": agora.isoformat(timespec="minutes")})
        gravar(dados, caminho)
    extra = f", e repito {NOME_REPETICAO[repetir]}" if repetir in NOME_REPETICAO else ""
    return (f"Lembrete {numero} marcado para {_falar_quando(quando, agora)}{extra}: {texto}. "
            "Confirm to the user in one short Portuguese sentence.")


def listar(agora: datetime | None = None, caminho: Path | None = None) -> str:
    agora = agora or datetime.now()
    itens = proximos(ler(caminho))
    if not itens:
        return "Não há lembretes marcados. Tell the user in Portuguese."
    partes = []
    for l in itens[:8]:
        quando = datetime.fromisoformat(l["quando"])
        repete = f" ({NOME_REPETICAO[l['repetir']]})" if l.get("repetir") in NOME_REPETICAO else ""
        partes.append(f"{l['numero']}) {_falar_quando(quando, agora)}{repete}: {l['texto']}")
    return "Lembretes: " + "; ".join(partes) + ". Tell the user in Portuguese, briefly."


def cancelar(args: dict, caminho: Path | None = None) -> str:
    numero = args.get("number")
    texto = str(args.get("text", "") or "").lower().strip()
    with _trava:
        dados = ler(caminho)
        alvo = None
        for l in dados["lembretes"]:
            if (numero not in (None, "") and int(numero) == l.get("numero")) or (
                    numero in (None, "") and texto and texto in l["texto"].lower()):
                alvo = l
                break
        if alvo is None:
            return "Não achei esse lembrete. " + listar(caminho=caminho)
        dados["lembretes"].remove(alvo)
        gravar(dados, caminho)
    return f"Lembrete {alvo['numero']} cancelado: {alvo['texto']}. Confirm in Portuguese."


def vencidos(agora: datetime | None = None, caminho: Path | None = None) -> list[str]:
    """Tira da lista (ou reagenda, se repete) os lembretes que chegaram na hora. Devolve as frases."""
    agora = agora or datetime.now()
    frases = []
    with _trava:
        dados = ler(caminho)
        mudou = False
        for l in list(dados["lembretes"]):
            quando = datetime.fromisoformat(l["quando"])
            if quando > agora:
                continue
            mudou = True
            if agora - quando <= ATRASO_MAXIMO:
                atrasado = agora - quando > timedelta(minutes=5)
                frases.append(f"{l['texto']}" + (f" (era para as {quando:%H:%M})" if atrasado else ""))
            seguinte = proxima_vez(quando, l.get("repetir", "nao"))
            while seguinte is not None and seguinte <= agora:
                seguinte = proxima_vez(seguinte, l["repetir"])
            if seguinte is None:
                dados["lembretes"].remove(l)
            else:
                l["quando"] = seguinte.isoformat(timespec="minutes")
        if frases:
            dados["ultimo_aviso"] = {"texto": " | ".join(frases), "em": agora.isoformat(timespec="seconds")}
        if mudou:
            gravar(dados, caminho)
    return frases


def _avisar(jarvis, frases: list[str]) -> None:
    texto = ("Lembrete: " if len(frases) == 1 else "Lembretes: ") + "; ".join(frases) + "."
    anunciar = getattr(jarvis, "anunciar", None)
    if callable(anunciar):
        anunciar(texto, titulo="Lembrete")
    else:  # Jarvis sem a atualização de avisos: pelo menos mostra na tela
        jarvis.ui.write_log(f"SYS: 🔔 {texto}")


def iniciar(jarvis) -> None:
    if _iniciado.is_set():
        return
    _iniciado.set()
    parar = getattr(jarvis, "_shutdown_requested", None) or threading.Event()

    def laco():
        while not parar.is_set():
            try:
                frases = vencidos()
                if frases:
                    _avisar(jarvis, frases)
            except Exception as erro:
                print(f"[Lembretes] {erro}")
            parar.wait(CHECAR_A_CADA)

    threading.Thread(target=laco, daemon=True, name="LembretesFalados").start()


def executar(args: dict, jarvis) -> str:
    acao = str(args.get("action", "create") or "create").strip().lower()
    if acao in ("list", "listar"):
        return listar()
    if acao in ("cancel", "cancelar", "delete", "apagar"):
        return cancelar(args)
    return criar(args)
