"""Regras das ferramentas: o que pode ir para a nuvem e o que roda em fila (Etapa 12 da reorganização).

Saíram do main.py sem mudar um nome. A foto tests/dados/politicas_antes.json confere os conjuntos, e o
tests/test_invariantes.py garante que a lista do modo privado só cresce enquanto a ferramenta existir.
O main.py reexporta os nomes (core/cerebro_gemma e os testes usam main.FERRAMENTAS_NUVEM_IA). Desde a
Etapa 14 moram aqui também as ferramentas DESLIGADAS e o bloqueio_do_modo_privado, a trava que recusa, no
modo privado, tudo o que mandaria o pedido para uma IA na nuvem (os testes que mexem nela fazem patch em
cerebro.ferramentas.politica.FERRAMENTAS_NUVEM_IA e em cerebro.ferramentas.registro.carregar_automacoes).
"""

from __future__ import annotations

from core.frases import frase

# Tool names exposed by hosted clients. The names here are Gemini function
# declaration names (which differ from a few implementation module names).
CLOUD_SAFE_ACTIONS = frozenset({
    "web_search",
    "deep_research",
    "create_presentation",
    "flight_finder",
    "email_control",
    "youtube_video",
})

# Jarvis Ultron: no modo privado (JARVIS_CEREBRO=gemma) nada vai para IA na nuvem. Estas ferramentas
# mandam o pedido (ou a tela) para o Gemini, o Hermes (modelos grátis da Nous) ou outra IA na nuvem:
# não são oferecidas ao Gemma e são recusadas em _execute_tool. As automações da pasta marcam isso
# com USA_IA_NUVEM = True (ex.: claude_task, generate_video).
FERRAMENTAS_NUVEM_IA = frozenset({
    "web_search", "deep_research", "agent_task", "generate_image", "hermes_agent", "approve_publication",
    "create_presentation", "code_helper", "dev_agent", "file_processor", "screen_process", "flight_finder",
    "computer_control", "desktop_control", "computer_settings",
})

AVISO_MODO_PRIVADO = frase("modo_privado_nuvem")  # o texto fica no core/frases.py (Etapa 8)

# Ferramentas que mudam algo: num lote do Gemini, rodam em fila, uma depois da outra (as outras rodam
# juntas). Era o conjunto "mutating" do _execute_tool_batch; a Etapa 14 passa a calculá-lo pela ficha de
# cada ferramenta.
MUDAM_ALGO = frozenset({
    "send_message", "prepare_message_reply", "email_control", "reminder",
    "computer_settings", "computer_control", "desktop_control", "file_controller",
    "file_processor", "code_helper", "dev_agent", "game_updater",
    "create_presentation", "save_memory", "jarvis_ui_control", "graphics_quality",
})


def bloqueio_do_modo_privado(nome: str, args: dict | None = None) -> str | None:
    """Jarvis Ultron: no modo privado, a recusa (em português) para uma ferramenta que usa IA na nuvem;
    None quando pode rodar. Vale para o Gemma, o painel Ultron e qualquer outra chamada."""
    from core.cerebro_gemma import cerebro_gemma

    if not cerebro_gemma():
        return None
    args = args or {}
    if nome in FERRAMENTAS_NUVEM_IA:
        return AVISO_MODO_PRIVADO
    if nome == "youtube_video" and str(args.get("action", "")).strip().lower() == "summarize":
        return AVISO_MODO_PRIVADO  # o resumo do vídeo é feito pelo Gemini
    if nome == "school_tasks" and args.get("refresh"):
        return AVISO_MODO_PRIVADO  # ler o Geekie de novo é trabalho do Hermes
    from cerebro.ferramentas.registro import carregar_automacoes  # (aqui, para não dar laço de import)

    automacao = carregar_automacoes().ferramentas.get(nome)
    if automacao is not None and getattr(automacao, "usa_ia_nuvem", False):
        return AVISO_MODO_PRIVADO
    return None


# Jarvis Ultron: ferramentas herdadas DESLIGADAS de propósito (Etapa 3 do docs/PLANO-REORGANIZACAO.md,
# decisão do Erton): agiam sem o "ok" dele conferido no código, ou ele não usa. Saíram da lista que o
# Gemini vê, da reserva e do prompt; os arquivos ficam no lugar até a Etapa 18. Se alguém chamar mesmo
# assim (um nome antigo, o modelo inventando), o _execute_tool responde isto e não chama nada.
# Nome -> o que ela fazia (vai na resposta ao modelo, em inglês como as outras).
FERRAMENTAS_DESLIGADAS = {
    "send_message": "sending messages on WhatsApp, Telegram, Discord, Instagram or iMessage",
    "prepare_message_reply": "drafting and sending message replies",
    "check_messages": "reading messages and contacts",
    "agent_task": "multi-step tasks that write and run AI-generated code",
    "code_helper": "writing, running and building code",
    "dev_agent": "building projects, installing packages and running code",
    "computer_control": "clicking, typing and moving the mouse anywhere on the screen",
    "game_updater": "installing and updating Steam and Epic games, which could shut down the computer",
}


def resposta_de_desligada(nome: str) -> str:
    """O que volta para o modelo quando ele chama uma ferramenta desligada (nada é chamado)."""
    return (f"Tool '{nome}' ({FERRAMENTAS_DESLIGADAS[nome]}) is turned off in Jarvis Ultron. "
            "Do not try to do this with another tool. Tell the user, in one short sentence in Portuguese, "
            "that you do not do this.")
