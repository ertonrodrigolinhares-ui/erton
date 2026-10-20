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

from core import marca

USA_IA_NUVEM = True  # o Claude roda na nuvem: desligado no modo privado

_AGENTES = sorted(p.parent.name for p in (Path(__file__).resolve().parents[1] / "claude" / "skills").glob("*/SKILL.md"))

FERRAMENTA = {
    "name": "claude_task",
    "description": (
        "Hands a BIG task to Claude (the task chief running on the user's PC; slow, takes minutes, and uses the "
        "user's Claude plan). NEVER use it for quick things you can answer or do with another tool right away: "
        "today's news/headlines, weather, time, a quick web search, opening sites or apps, reminders. Use it for: "
        "deep research with sources, "
        "analysis of documents in the Claude 'Entrada' folder, reports, proposals, multi-step thinking, one of "
        f"the {marca.NOME} agents (agent=name; available: " + (", ".join(_AGENTES) or "none") + "; Claude also has "
        "hundreds of English-named specialist agents, so if the user names another agent or specialist, "
        "e.g. 'Tax Strategist', pass that name as agent), "
        f"or changing {marca.NOME}'s own code (kind='codigo'). It runs in the background; tell the user, in one short "
        "Portuguese sentence, that Claude is working and you will warn when it is ready. Claude cannot publish, "
        "send or buy anything. For kind='codigo': the first call makes only a PLAN; when the plan is told to the "
        "user, call again with confirm=true ONLY after the user clearly approves in their own words."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "request": {"type": "STRING", "description": "The complete task, in Portuguese, with all details the user gave"},
            "kind": {"type": "STRING", "description": f"tarefa (default) | codigo (change {marca.NOME}'s own code)"},
            "agent": {"type": "STRING", "description": f"Optional agent to follow: a {marca.NOME} agent name or a specialist name the user said"},
            "continue_last": {"type": "BOOLEAN", "description": "true to continue the previous Claude task (follow-up)"},
            "confirm": {"type": "BOOLEAN", "description": "kind=codigo only: true ONLY after the user approved the plan"},
        },
        "required": ["request"],
    },
}

_trava = threading.Lock()
_ocupado = threading.Lock()   # uma tarefa do Claude por vez
_estado: dict = {"plano": None, "ultima_sessao": None}


def _avisar(jarvis, texto: str, ao_falar=None, sigiloso: bool = False) -> str:
    """Avisa o Erton. Devolve "guardado" se o aviso ficou esperando o "Hey Jarvis" (aí ao_falar é
    chamado quando ele for falado de verdade). sigiloso=True: o texto pode ter dados de clientes (o
    Claude lê clientes.txt, Faturas...), então o Jarvis fala só com a voz do PC, sem mandar para o Gemini."""
    extra = {"sigiloso": True} if sigiloso else {}
    anunciar = getattr(jarvis, "anunciar", None)
    if callable(anunciar):
        if ao_falar is None:
            return str(anunciar(texto, "Claude", **extra) or "")
        return str(anunciar(texto, "Claude", ao_falar=ao_falar, **extra) or "")
    ui = getattr(jarvis, "ui", None)
    if ui is not None:
        ui.write_log(f"SYS: 🤖 Claude: {texto}")
    falar = getattr(jarvis, "_falar_aviso", None)
    if callable(falar):
        falar(texto, **extra)
    return "falado"


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
    # Nome que não é de nenhum agente não se perde: o chefe manda como dica (limpa) para o Claude procurar
    conhecido = bool(chefe.agente_do_jarvis(agente) or (agente and chefe.agente_agency(agente)))
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
    _log(jarvis, "SYS: 🤖 Claude trabalhando" + (f" (agente {agente})" if conhecido else "") + "...")
    return ("Claude is working on it in the background. Tell the user, in one short Portuguese sentence, that "
            "you will warn when it is ready. Do not wait.")


def _codigo(args: dict, jarvis, chefe) -> str:
    if getattr(sys, "frozen", False):
        return f"This packaged {marca.NOME} cannot change its own code. Tell the user in Portuguese."
    pedido = str(args.get("request", "")).strip()

    from core import aprovacao

    if not args.get("confirm"):
        def planejar():
            resposta = chefe.planejar(pedido)
            if not resposta.ok:
                _avisar(jarvis, f"O Claude não conseguiu fazer o plano: {resposta.erro}.")
                return
            fala, plano = chefe.separar_fala(resposta.texto)
            # o "ok" só vale numa fala DEPOIS de o plano ser contado. No modo chamada o aviso fica
            # guardado até o "Hey Jarvis": até lá o plano não foi contado ("em" e "marca" vazios).
            pendente = {"pedido": pedido, "plano": plano or resposta.texto, "sessao": resposta.sessao,
                        "em": None, "marca": None}
            with _trava:
                _estado["plano"] = pendente

            def contado():  # agora o Erton ouviu: a validade e a marca da fala começam aqui
                with _trava:
                    if _estado["plano"] is pendente:
                        pendente.update(em=time.monotonic(), marca=aprovacao.marca(jarvis))

            _log(jarvis, f"SYS: 🤖 Plano do Claude:\n{(plano or resposta.texto)[:1500]}")
            if _avisar(jarvis, f"O plano do Claude está pronto: {fala} Para aplicar, diga 'ok, pode fazer'.",
                       ao_falar=contado) != "guardado":
                contado()

        if _em_segundo_plano(jarvis, "ClaudePlano", planejar) is None:
            return "Claude is still working on the previous task. Tell the user to wait for it to finish."
        _log(jarvis, "SYS: 🤖 Claude lendo o código e fazendo o plano (não muda nada ainda)...")
        return ("Claude is reading the code and writing a PLAN (nothing is changed yet). Tell the user, in one short "
                "Portuguese sentence, that you will tell the plan when it is ready.")

    with _trava:
        pendente = _estado["plano"]
        contado = pendente is not None and pendente["em"] is not None
        valido = contado and time.monotonic() - pendente["em"] < chefe.VALIDADE_PLANO
        fala_do_ok = aprovacao.fala_que_aprovou(jarvis, pendente["marca"]) if valido else 0
        if fala_do_ok:
            _estado["plano"] = None
    if pendente is not None and not contado:
        return ("Not confirmed: the plan was not told to the user yet (it is waiting to be spoken). Wait until "
                "the user hears the plan and then approves it in their own words.")
    if not valido:
        return ("Not confirmed: there is no recent plan from Claude. Call with confirm=false first to make the plan, "
                "tell it to the user and wait for an explicit ok.")
    if not fala_do_ok:
        return "Not confirmed: the user did not clearly approve the plan. Ask for an explicit ok (e.g. 'ok, pode fazer')."

    def aplicar():
        # A ferramenta pode ter chegado com só o começo da resposta transcrito ("Ok," ... "pode
        # cancelar"): antes de mexer no código, confere de novo com a fala inteira.
        if not aprovacao.ainda_aprovado(jarvis, fala_do_ok):
            with _trava:
                if _estado["plano"] is None:  # o plano continua valendo para um "ok" claro numa fala nova
                    pendente["marca"] = aprovacao.marca(jarvis)
                    _estado["plano"] = pendente
            _avisar(jarvis, "Não apliquei o plano do Claude: a sua resposta não foi um 'ok' claro, então nada "
                            "foi mudado. Se quiser aplicar, diga 'ok, pode fazer'.")
            return
        resultado = chefe.aplicar_plano(pendente["plano"], pendente["sessao"], pendente["pedido"])
        if resultado.detalhes:
            _log(jarvis, f"SYS: 🤖 {resultado.detalhes}")
        _avisar(jarvis, resultado.fala)

    if _em_segundo_plano(jarvis, "ClaudeAplicar", aplicar) is None:
        with _trava:
            _estado["plano"] = pendente  # devolve o plano: o ok continua valendo para depois
        return "Claude is still working on the previous task. Tell the user to wait for it to finish."
    _log(jarvis, f"SYS: 🤖 Backup feito; Claude aplicando o plano aprovado (o {marca.NOME_CURTO} testa e desfaz se quebrar)...")
    return (f"Approved. Claude is applying the plan in the background; {marca.NOME} makes a backup, runs the tests and "
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
                f"'Instalar Claude' in the {marca.NOME} folder (it signs in with their Claude account).")
    if str(args.get("kind", "") or "").strip().lower() in ("codigo", "código", "code"):
        return _codigo(args, jarvis, chefe)
    return _tarefa(args, jarvis, chefe)
