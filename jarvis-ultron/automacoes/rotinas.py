"""Rotinas salvas do Jarvis Ultron: "agentes" para tarefas que você repete
(automação: salve na pasta 'automacoes' e reabra o Jarvis).

Criar:   "Jarvis, salve a rotina 'treino': veja o clima, abra o Strava e toque minha playlist de treino."
Usar:    "Jarvis, rotina treino."   (ou clique no nome dela no painel Stark)
Ver:     "Jarvis, quais rotinas eu tenho?"
Apagar:  "Jarvis, apague a rotina treino."

Cada rotina é uma lista de passos que o Jarvis faz em sequência, com as ferramentas dele.
Para tarefas longas de pesquisa na internet, peça "salve como agente do Hermes": aí o Hermes faz
em segundo plano e o Jarvis avisa quando terminar.
Já vêm duas prontas: "bom dia" e "fim do dia" (pode mudar ou apagar).
As rotinas ficam em Documentos/Jarvis Ultron/rotinas.json. Rotina salva no modo privado só aparece e só
roda no modo privado (os passos dela nunca vão para o Gemini).

Segurança: a rotina segue as mesmas regras do Jarvis. Nada é publicado, enviado, comprado ou
apagado sem o seu "ok" na hora.
"""

from __future__ import annotations

import asyncio
import json
import threading
import unicodedata
from datetime import datetime
from pathlib import Path

FERRAMENTA = {
    "name": "saved_routines",
    "description": (
        "Saved routines (the user's personal agents for repeated tasks). Use when the user says 'rotina <name>', "
        "'run/execute routine', asks to save/create/change a routine, list routines or delete one. "
        "save: name + steps (each step is one instruction in Portuguese) + optional agent ('hermes' for long web "
        "research done in the background, default 'jarvis'). run: name. After 'run', do the returned steps "
        "right away using your tools. Speak Portuguese."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "description": "run | save | list | delete"},
            "name": {"type": "STRING", "description": "Routine name, e.g. 'bom dia'"},
            "steps": {"type": "ARRAY", "items": {"type": "STRING"},
                      "description": "Steps for save, in order, one instruction each"},
            "agent": {"type": "STRING", "description": "jarvis (default) | hermes"},
        },
        "required": ["action"],
    },
}

PRONTAS = {
    "bom dia": {
        "passos": ["Diga como está o tempo hoje na minha cidade.",
                   "Diga os lembretes marcados para hoje.",
                   "Diga as atividades pendentes do Geekie que vencem logo.",
                   "Diga se há posts agendados para hoje no Metricool."],
        "agente": "jarvis",
    },
    "fim do dia": {
        "passos": ["Faça um resumo curto do que fizemos hoje.",
                   "Diga os lembretes marcados para amanhã.",
                   "Pergunte se quero marcar algum lembrete para amanhã."],
        "agente": "jarvis",
    },
}

REGRAS = ("Follow your usual safety rules: never publish, post, send messages or e-mails, buy, pay or delete "
          "anything without the user's explicit 'ok' at that moment; if a step needs that, ask and wait. "
          "If a step fails, say so briefly and continue with the next one. At the end give a short summary in "
          "Portuguese.")

_trava = threading.Lock()

SO_NO_MODO_PRIVADO = ("Essa rotina foi criada no modo privado, então só aparece e só roda no modo privado. "
                      "Para usar, diga 'modo privado'. Tell the user in Portuguese.")


def _modo_privado() -> bool:
    from core.cerebro_gemma import cerebro_gemma

    return cerebro_gemma()


def _escondida(rotina) -> bool:
    """Rotina salva no modo privado, fora do modo privado: nem o nome nem os passos vão para a nuvem."""
    return isinstance(rotina, dict) and bool(rotina.get("privado")) and not _modo_privado()


def arquivo() -> Path:
    return Path.home() / "Documents" / "Jarvis Ultron" / "rotinas.json"


def chave(nome: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", str(nome or "")).encode("ascii", "ignore").decode()
    return " ".join(sem_acento.lower().replace("rotina", " ").replace("'", " ").replace('"', " ").split())


def ler(caminho: Path | None = None) -> dict:
    caminho = caminho or arquivo()
    try:
        dados = json.loads(caminho.read_text(encoding="utf-8"))
        if isinstance(dados, dict) and isinstance(dados.get("rotinas"), dict):
            return dados
    except FileNotFoundError:
        return {"rotinas": {nome: dict(r) for nome, r in PRONTAS.items()}}
    except (OSError, ValueError):
        pass
    return {"rotinas": {}}


def gravar(dados: dict, caminho: Path | None = None) -> None:
    caminho = caminho or arquivo()
    caminho.parent.mkdir(parents=True, exist_ok=True)
    temporario = caminho.with_suffix(".tmp")
    temporario.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
    temporario.replace(caminho)


def nomes(caminho: Path | None = None) -> list[str]:
    return sorted(ler(caminho)["rotinas"])


def sugestao(dados: dict, nome: str) -> str | None:
    """Etapa 10: o microfone entende errado ("rotina trein0"): a rotina mais parecida, pelo difflib, ou
    None. Rotinas do modo privado nunca são sugeridas fora dele."""
    import difflib

    procurado = chave(nome)
    visiveis = {chave(n): n for n, r in dados["rotinas"].items() if not _escondida(r)}
    if not procurado or not visiveis:
        return None
    parecidas = difflib.get_close_matches(procurado, list(visiveis), n=1, cutoff=0.6)
    return visiveis[parecidas[0]] if parecidas else None


def _nao_achei(dados: dict, nome: str, caminho: Path | None) -> str:
    parecida = sugestao(dados, nome)
    if parecida:
        return (f"Não achei essa rotina. Você quis dizer a rotina '{parecida}'? Pergunte ao usuário antes de "
                "rodar ou apagar.")
    return "Não achei essa rotina. " + listar(caminho)


def _achar(dados: dict, nome: str) -> str | None:
    procurado = chave(nome)
    if not procurado:
        return None
    por_chave = {chave(n): n for n in dados["rotinas"]}
    if procurado in por_chave:
        return por_chave[procurado]
    parecidos = [n for c, n in por_chave.items() if procurado in c or c in procurado]
    return parecidos[0] if len(parecidos) == 1 else None


def _passos(valor) -> list[str]:
    if isinstance(valor, str):
        valor = valor.replace("\n", ";").split(";")
    return [" ".join(str(p).split()) for p in (valor or []) if str(p).strip()]


def salvar(args: dict, caminho: Path | None = None) -> str:
    nome = " ".join(str(args.get("name", "")).split()).lower().replace("rotina ", "").strip(" '\"")
    passos = _passos(args.get("steps"))
    if not nome:
        return "Falta o nome da rotina. Pergunte ao usuário."
    if not passos:
        return "Faltam os passos da rotina. Pergunte ao usuário o que ela deve fazer."
    agente = "hermes" if str(args.get("agent", "")).strip().lower() == "hermes" else "jarvis"
    with _trava:
        dados = ler(caminho)
        existente = _achar(dados, nome)
        if existente and chave(existente) == chave(nome):
            if _escondida(dados["rotinas"][existente]):
                return SO_NO_MODO_PRIVADO
            nome = existente
        dados["rotinas"][nome] = {"passos": passos[:15], "agente": agente,
                                  "criada": datetime.now().isoformat(timespec="minutes")}
        if _modo_privado():
            dados["rotinas"][nome]["privado"] = True
        gravar(dados, caminho)
    quem = "pelo Hermes, em segundo plano" if agente == "hermes" else "por mim"
    return (f"Rotina '{nome}' salva com {len(passos[:15])} passos, feita {quem}. "
            f"Para usar, diga: rotina {nome}. Confirm to the user in Portuguese, briefly.")


def listar(caminho: Path | None = None) -> str:
    todas = ler(caminho)["rotinas"]
    rotinas = {n: r for n, r in todas.items() if not _escondida(r)}
    privadas = len(todas) - len(rotinas)
    extra = (f" Há também {privadas} rotina(s) do modo privado, que só aparecem no modo privado."
             if privadas else "")
    if not rotinas:
        return "Não há rotinas salvas." + extra + " Tell the user in Portuguese and offer to create one."
    partes = [f"{n} ({len(r.get('passos', []))} passos)" for n, r in sorted(rotinas.items())]
    return "Rotinas salvas: " + ", ".join(partes) + "." + extra + " Tell the user in Portuguese."


def apagar(args: dict, caminho: Path | None = None) -> str:
    with _trava:
        dados = ler(caminho)
        nome = _achar(dados, args.get("name", ""))
        if nome is None:
            return _nao_achei(dados, args.get("name", ""), caminho)
        if _escondida(dados["rotinas"][nome]):
            return SO_NO_MODO_PRIVADO
        del dados["rotinas"][nome]
        gravar(dados, caminho)
    return f"Rotina '{nome}' apagada. Confirm in Portuguese."


def _pelo_hermes(nome: str, pedido: str, jarvis) -> str:
    esperar = getattr(jarvis, "_hermes_sem_travar", None)
    loop = getattr(jarvis, "_loop", None)
    if callable(esperar) and loop is not None:
        return asyncio.run_coroutine_threadsafe(esperar(pedido), loop).result(timeout=60)
    from core import hermes_ponte

    return hermes_ponte.perguntar(pedido)


def rodar(args: dict, jarvis, caminho: Path | None = None) -> str:
    dados = ler(caminho)
    nome = _achar(dados, args.get("name", ""))
    if nome is None:
        return _nao_achei(dados, args.get("name", ""), caminho)
    rotina = dados["rotinas"][nome]
    if _escondida(rotina):  # os passos foram ditos no modo privado: não vão para a nuvem
        return SO_NO_MODO_PRIVADO
    passos = rotina.get("passos", [])
    lista = " ".join(f"{i}) {p}" for i, p in enumerate(passos, 1))
    if rotina.get("agente") == "hermes":
        from core.cerebro_gemma import cerebro_gemma

        if cerebro_gemma():  # modo privado: o Hermes roda em IA na nuvem
            return (f"A rotina '{nome}' é feita pelo Hermes, que usa IA na nuvem, então não roda no modo "
                    "privado. Para usar, diga 'modo normal'.")
        pedido = (f"Rotina '{nome}' do usuário. Faça estes passos em ordem e responda um resumo curto em "
                  f"português: {lista}. Nunca publique, envie mensagens, compre ou apague nada.")
        return f"[Hermes, rotina {nome}] " + str(_pelo_hermes(nome, pedido, jarvis))
    return (f"Routine '{nome}' — do these steps now, in order, using your tools (one short sentence before "
            f"each tool, no need to ask permission for read-only steps): {lista}. {REGRAS}")


def executar(args: dict, jarvis) -> str:
    acao = str(args.get("action", "run") or "run").strip().lower()
    if acao in ("save", "salvar", "create", "criar", "update"):
        return salvar(args)
    if acao in ("list", "listar"):
        return listar()
    if acao in ("delete", "apagar", "remove"):
        return apagar(args)
    return rodar(args, jarvis)
