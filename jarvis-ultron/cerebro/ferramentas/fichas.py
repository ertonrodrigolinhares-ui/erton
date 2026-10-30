"""A ficha única de cada ferramenta do Jarvis (Etapa 14 da reorganização).

Antes, cada ferramenta estava espalhada por até 8 lugares (declaração, ramo do _execute_tool, lista do modo
privado, lista do servidor, lista do que roda em fila, lista da reserva, lista das desligadas...). Agora
cada uma é UMA ficha, e as listas são CALCULADAS daqui, com os mesmos nomes de antes:

- FERRAMENTAS_NUVEM_IA: as fichas com usa_ia_nuvem=True (uma regra por argumento, como o resumo do
  youtube_video, fica em REGRAS_DE_NUVEM e vale só para aquele argumento);
- MUDAM_ALGO: as fichas com muda_algo=True (rodam em fila num lote do Gemini). Desde a Etapa 14 (c) é o
  padrão: só o que SÓ LÊ (web_search, weather_report, task_status, self_diagnosis, school_tasks) marca
  False. Antes, publicar, gerar vídeo pago, abrir programa e trocar o modo de escuta podiam rodar ao mesmo
  tempo e disputar o mesmo "ok";
- CLOUD_SAFE_ACTIONS: nuvem_ok=True (as que o servidor web, hoje guardado, oferecia);
- RESERVA_FERRAMENTAS_ESSENCIAIS: essencial_na_reserva=True (vão para o Groq);
- FERRAMENTAS_DESLIGADAS: as fichas desligadas (Etapa 3), com o motivo;
- EXECUTORES: nome -> função, das fichas que têm executar.

A foto tests/dados/politicas_antes.json prova que as listas dão exatamente o que davam. Acrescentar uma
ferramenta é escrever uma ficha: não dá mais para esquecer de pô-la na lista do modo privado.
Este arquivo não lê o .env nem cria cliente do Gemini ao ser importado.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from cerebro.ferramentas import executores as ex
from cerebro.ferramentas.declaracoes import TOOL_DECLARATIONS

_DECLARACOES = {d["name"]: d for d in TOOL_DECLARATIONS}


@dataclass(frozen=True)
class Ficha:
    nome: str
    executar: Callable | None = None   # None: desligada (Etapa 3) ou tratada no próprio _execute_tool (save_memory)
    resposta_padrao: str = "Done."     # o que volta ao modelo quando a ação não devolve nada ("" = ela sempre responde)
    usa_ia_nuvem: bool = False         # manda o pedido para uma IA na nuvem: não roda no modo privado
    muda_algo: bool = True             # num lote do Gemini, roda em fila (uma depois da outra). É o padrão
                                       # seguro (Etapa 14 c): só o que SÓ LÊ marca False e roda em paralelo
    precisa_ok: bool = False           # a ação confere o "ok" do Erton no código (core/aprovacao.py)
    nuvem_ok: bool = False             # o servidor web (guardado) podia oferecê-la
    essencial_na_reserva: bool = False  # vai para o Groq no modo reserva
    desligada: str = ""                # Etapa 3: o que ela fazia (vai na resposta ao modelo); "" = ligada

    @property
    def declaracao(self) -> dict | None:
        return _DECLARACOES.get(self.nome)


# Regras do modo privado por argumento: a ferramenta pode rodar, menos quando o argumento manda o pedido
# para a nuvem (o resumo do vídeo é feito pelo Gemini; ler o Geekie de novo é trabalho do Hermes).
REGRAS_DE_NUVEM: dict[str, Callable[[dict], bool]] = {
    "youtube_video": lambda args: str(args.get("action", "")).strip().lower() == "summarize",
    "school_tasks": lambda args: bool(args.get("refresh")),
}

FICHAS: tuple[Ficha, ...] = (
    # internet e mídia
    Ficha("weather_report", ex._ex_weather_report, "Weather delivered.", muda_algo=False, essencial_na_reserva=True),
    Ficha("web_search", ex._ex_web_search, usa_ia_nuvem=True, muda_algo=False, nuvem_ok=True, essencial_na_reserva=True),
    Ficha("browser_control", ex._ex_browser_control, essencial_na_reserva=True),
    Ficha("media_control", ex._ex_media_control, essencial_na_reserva=True),
    Ficha("youtube_video", ex._ex_youtube_video, nuvem_ok=True, essencial_na_reserva=True),
    # o sistema e a própria tela
    Ficha("open_app", ex._ex_open_app, "Opened {app_name}.", essencial_na_reserva=True),
    Ficha("computer_settings", ex._ex_computer_settings, usa_ia_nuvem=True, precisa_ok=True),
    Ficha("desktop_control", ex._ex_desktop_control, usa_ia_nuvem=True),
    Ficha("file_controller", ex._ex_file_controller),
    Ficha("graphics_quality", ex._ex_graphics_quality, "JARVIS graphics quality changed to {quality}."),
    Ficha("jarvis_ui_control", ex._ex_jarvis_ui_control, "JARVIS interface action completed: {action}."),
    # e-mail e lembrete
    Ficha("email_control", ex._ex_email_control, "Email action completed.", nuvem_ok=True, essencial_na_reserva=True),
    Ficha("reminder", ex._ex_reminder, "Reminder set.", essencial_na_reserva=True),
    # o Jarvis por dentro
    Ficha("listening_mode", ex._ex_listening_mode, "", essencial_na_reserva=True),
    Ficha("hermes_agent", ex._ex_hermes_agent, "", usa_ia_nuvem=True, essencial_na_reserva=True),
    Ficha("school_tasks", ex._ex_school_tasks, "", muda_algo=False, essencial_na_reserva=True),
    Ficha("self_diagnosis", ex._ex_self_diagnosis, "", muda_algo=False, essencial_na_reserva=True),
    Ficha("approve_publication", ex._ex_approve_publication, "", usa_ia_nuvem=True, precisa_ok=True),
    Ficha("suspend_listening", ex._ex_suspend_listening, ""),
    Ficha("generate_image", ex._ex_generate_image, "", usa_ia_nuvem=True, essencial_na_reserva=True),
    # visão, arquivos e tarefas
    Ficha("screen_process", ex._ex_screen_process,
          "Vision module activated. Stay completely silent — vision module will speak directly.", usa_ia_nuvem=True),
    Ficha("file_processor", ex._ex_file_processor, usa_ia_nuvem=True),
    Ficha("deep_research", ex._ex_deep_research, "Deep research preference requested.", usa_ia_nuvem=True, nuvem_ok=True),
    Ficha("create_presentation", ex._ex_create_presentation, "Presentation preference requested.", usa_ia_nuvem=True,
          nuvem_ok=True),
    Ficha("task_status", ex._ex_task_status, "", muda_algo=False),
    # memória: tratada no próprio _execute_tool (não grava no modo privado), por isso sem executar aqui
    Ficha("save_memory", None, "ok", essencial_na_reserva=True),
    # herdada que ainda existe (a Etapa 18 decide, com o Erton)
    Ficha("flight_finder", ex._ex_flight_finder, usa_ia_nuvem=True, nuvem_ok=True),
    # desligadas de propósito (Etapa 3, decisão do Erton): sem declaração, sem executor; chamadas mesmo assim,
    # o _execute_tool responde o motivo e não chama nada
    Ficha("send_message",
          desligada="sending messages on WhatsApp, Telegram, Discord, Instagram or iMessage"),
    Ficha("prepare_message_reply", desligada="drafting and sending message replies"),
    Ficha("check_messages", desligada="reading messages and contacts"),
    Ficha("agent_task", usa_ia_nuvem=True, desligada="multi-step tasks that write and run AI-generated code"),
    Ficha("code_helper", usa_ia_nuvem=True, desligada="writing, running and building code"),
    Ficha("dev_agent", usa_ia_nuvem=True,
          desligada="building projects, installing packages and running code"),
    Ficha("computer_control", usa_ia_nuvem=True,
          desligada="clicking, typing and moving the mouse anywhere on the screen"),
    Ficha("game_updater",
          desligada="installing and updating Steam and Epic games, which could shut down the computer"),
)

POR_NOME: dict[str, Ficha] = {f.nome: f for f in FICHAS}
assert len(POR_NOME) == len(FICHAS), "ficha repetida"

EXECUTORES: dict[str, Callable] = {f.nome: f.executar for f in FICHAS if f.executar is not None}
FERRAMENTAS_NUVEM_IA = frozenset(f.nome for f in FICHAS if f.usa_ia_nuvem)
MUDAM_ALGO = frozenset(f.nome for f in FICHAS if f.muda_algo)
CLOUD_SAFE_ACTIONS = frozenset(f.nome for f in FICHAS if f.nuvem_ok)
RESERVA_FERRAMENTAS_ESSENCIAIS = frozenset(f.nome for f in FICHAS if f.essencial_na_reserva)
FERRAMENTAS_DESLIGADAS: dict[str, str] = {f.nome: f.desligada for f in FICHAS if f.desligada}
