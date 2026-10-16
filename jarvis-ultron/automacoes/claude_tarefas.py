"""Claude como chefe de tarefas do Jarvis Ultron (automação: salve na pasta 'automacoes' e reabra o Jarvis).

Diga, por exemplo:
  - "Jarvis, pede para o Claude pesquisar as mudanças da reforma tributária para holdings familiares."
  - "Jarvis, manda o Claude analisar a planilha que eu deixei na pasta Entrada."
  - "Jarvis, usa o agente proposta-comercial para o grupo X." (os agentes ficam em claude/skills)
  - "Jarvis, pede para o Claude mudar o seu código para ... " (ele planeja, você aprova, ele aplica)

Precisa do "Instalar Claude" (Claude Code no PC, entrando com a sua conta do Claude Pro/Max).
O Claude trabalha em segundo plano: dá para continuar conversando; o Jarvis avisa quando terminar.
Os relatórios ficam em Documentos/Jarvis Ultron/Claude/Relatorios. Travas: veja core/claude_chefe.py.
"""

from __future__ import annotations

import os
import sys
import threading
import time
from pathlib import Path

USA_IA_NUVEM = True  # o Claude roda na nuvem: desligado no modo privado

_AGENTES = sorted(p.parent.name for p in (Path(__file__).resolve().parents[1] / "claude" / "skills").glob("*/SKILL.md"))

FERRAMENTA = {
    "name": "claude_task",
    "description": (
        "Hands a big task to Claude (the task chief running on the user's PC): deep research with sources, "
        "analysis of documents in the Claude 'Entrada' folder, reports, proposals, multi-step thinking, one of "
        "the Jarvis agents (agent=name; available: " + (", ".join(_AGENTES) or "none") + "), "
        "or changing the Jarvis's own code (kind='codigo'). It runs in the background; tell the user, in one short "
        "Portuguese sentence, that Claude is working and you will warn when it is ready. Claude cannot publish, "
        "send or buy anything. For kind='codigo': the first call makes only a PLAN; when the plan is told to the "
        "user, call again with confirm=true ONLY after the user clearly approves in their own words."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "request": {"type": "STRING", "description": "The complete task, in Portuguese, with all details the user gave"},
            "kind": {"type": "STRING", "description": "tarefa (default) | codigo (change the Jarvis's own code)"},
            "agent": {"type": "STRING", "description": "Optional agent (skill) name to follow"},
            "continue_last": {"type": "BOOLEAN", "description": "true to continue the previous Claude task (follow-up)"},
            "confirm": {"type": "BOOLEAN", "description": "kind=codigo only: true ONLY after the user approved the plan"},
        },
        "required": ["request"],
    },
}

_trava = threading.Lock()
_ocupado = threading.Lock()   # uma tarefa do Claude por vez
_estado: dict = {"plano": None, "ultima_sessao": None}


def _fala_atual(jarvis) -> str:
    return str(getattr(jarvis, "_current_input_transcript", "") or getattr(jarvis, "_last_input_transcript", "") or "")


def _avisar(jarvis, texto: str, sigiloso: bool = False) -> None:
    """sigiloso=True: o texto pode ter dados de clientes (o Claude lê clientes.txt, Faturas...),
    então o Jarvis fala só com a voz do PC, sem mandar para o Gemini."""
    extra = {"sigiloso": True} if sigiloso else {}
    anunciar = getattr(jarvis, "anunciar", None)
    if callable(anunciar):
        anunciar(texto, "Claude", **extra)
        return
    ui = getattr(jarvis, "ui", None)
    if ui is not None:
        ui.write_log(f"SYS: 🤖 Claude: {texto}")
    falar = getattr(jarvis, "_falar_aviso", None)
    if callable(falar):
        falar(texto, **extra)


def _log(jarvis, texto: str) -> None:
    ui = getattr(jarvis, "ui", None)
    if ui is not None:
        ui.write_log(texto)


def _em_segundo_plano(jarvis, nome: str, trabalho) -> str | None:
    """Roda 'trabalho' num fio próprio; None se já houver outra tarefa do Claude rodando."""
    if not _ocupado.acquire(blocking=False):
        return None

    def rodar():
        try:
            trabalho()
        except Exception as erro:  # nunca deixa o fio morrer calado
            _avisar(jarvis, f"O Claude teve um problema: {str(erro)[:160]}.")
        finally:
            _ocupado.release()

    threading.Thread(target=rodar, daemon=True, name=nome).start()
    return "ok"


def _tarefa(args: dict, jarvis, chefe) -> str:
    pedido = str(args.get("request", "")).strip()
    agente = str(args.get("agent", "") or "").strip() or None
    if agente and agente not in chefe.agentes():
        agente = None
    with _trava:
        sessao = _estado["ultima_sessao"] if args.get("continue_last") else None

    def trabalhar():
        resposta = chefe.fazer_tarefa(pedido, agente=agente, sessao=sessao)
        if not resposta.ok:
            _avisar(jarvis, f"O Claude não conseguiu terminar: {resposta.erro}.")
            return
        with _trava:
            _estado["ultima_sessao"] = resposta.sessao
        fala, conteudo = chefe.separar_fala(resposta.texto)
        arquivo = chefe.salvar_relatorio(pedido, conteudo)
        if arquivo is not None:
            _log(jarvis, f"SYS: 🤖 Relatório do Claude salvo em {arquivo}")
            _abrir(arquivo)
        _avisar(jarvis, fala + (" O relatório completo está aberto na tela." if arquivo else ""), sigiloso=True)

    if _em_segundo_plano(jarvis, "ClaudeTarefa", trabalhar) is None:
        return "Claude is still working on the previous task. Tell the user to wait for it to finish."
    _log(jarvis, "SYS: 🤖 Claude trabalhando" + (f" (agente {agente})" if agente else "") + "...")
    return ("Claude is working on it in the background. Tell the user, in one short Portuguese sentence, that "
            "you will warn when it is ready. Do not wait.")


def _codigo(args: dict, jarvis, chefe) -> str:
    if getattr(sys, "frozen", False):
        return "This packaged Jarvis cannot change its own code. Tell the user in Portuguese."
    pedido = str(args.get("request", "")).strip()

    if not args.get("confirm"):
        def planejar():
            resposta = chefe.planejar(pedido)
            if not resposta.ok:
                _avisar(jarvis, f"O Claude não conseguiu fazer o plano: {resposta.erro}.")
                return
            fala, plano = chefe.separar_fala(resposta.texto)
            with _trava:  # o "ok" só vale numa fala DEPOIS de o plano ser contado
                _estado["plano"] = {"pedido": pedido, "plano": plano or resposta.texto, "sessao": resposta.sessao,
                                    "em": time.monotonic(), "fala": _fala_atual(jarvis).strip().lower()}
            _log(jarvis, f"SYS: 🤖 Plano do Claude:\n{(plano or resposta.texto)[:1500]}")
            _avisar(jarvis, f"O plano do Claude está pronto: {fala} Para aplicar, diga 'ok, pode fazer'.")

        if _em_segundo_plano(jarvis, "ClaudePlano", planejar) is None:
            return "Claude is still working on the previous task. Tell the user to wait for it to finish."
        _log(jarvis, "SYS: 🤖 Claude lendo o código e fazendo o plano (não muda nada ainda)...")
        return ("Claude is reading the code and writing a PLAN (nothing is changed yet). Tell the user, in one short "
                "Portuguese sentence, that you will tell the plan when it is ready.")

    from core.hermes_ponte import usuario_aprovou

    fala = _fala_atual(jarvis)
    with _trava:
        pendente = _estado["plano"]
        valido = pendente is not None and time.monotonic() - pendente["em"] < chefe.VALIDADE_PLANO
        aprovado = valido and fala.strip().lower() != pendente["fala"] and usuario_aprovou(fala)
        if aprovado:
            _estado["plano"] = None
    if not valido:
        return ("Not confirmed: there is no recent plan from Claude. Call with confirm=false first to make the plan, "
                "tell it to the user and wait for an explicit ok.")
    if not aprovado:
        return "Not confirmed: the user did not clearly approve the plan. Ask for an explicit ok (e.g. 'ok, pode fazer')."

    def aplicar():
        resultado = chefe.aplicar_plano(pendente["plano"], pendente["sessao"], pendente["pedido"])
        if resultado.detalhes:
            _log(jarvis, f"SYS: 🤖 {resultado.detalhes}")
        _avisar(jarvis, resultado.fala)

    if _em_segundo_plano(jarvis, "ClaudeAplicar", aplicar) is None:
        with _trava:
            _estado["plano"] = pendente  # devolve o plano: o ok continua valendo para depois
        return "Claude is still working on the previous task. Tell the user to wait for it to finish."
    _log(jarvis, "SYS: 🤖 Backup feito; Claude aplicando o plano aprovado (o Jarvis testa e desfaz se quebrar)...")
    return ("Approved. Claude is applying the plan in the background; the Jarvis makes a backup, runs the tests and "
            "undoes everything if something breaks. Tell the user in one short Portuguese sentence.")


def _abrir(arquivo) -> None:
    try:
        if sys.platform == "win32":
            os.startfile(str(arquivo))  # type: ignore[attr-defined]
    except Exception as erro:
        print(f"[Claude] Não consegui abrir o relatório: {erro}")


def executar(args: dict, jarvis) -> str:
    from core import claude_chefe as chefe

    if not str(args.get("request", "")).strip() and not args.get("confirm"):
        return "Missing the task for Claude."
    if chefe.no_modo_privado():
        return ("Private mode is on, so nothing is sent to Claude (it runs in the cloud). Tell the user in Portuguese "
                "that in modo privado the Gemma answers alone, and that saying 'modo normal' turns Claude back on.")
    if not chefe.achar_claude():
        return ("Claude Code is not installed on this PC. Tell the user in Portuguese to double-click "
                "'Instalar Claude' in the Jarvis folder (it signs in with their Claude account).")
    if str(args.get("kind", "") or "").strip().lower() in ("codigo", "código", "code"):
        return _codigo(args, jarvis, chefe)
    return _tarefa(args, jarvis, chefe)
