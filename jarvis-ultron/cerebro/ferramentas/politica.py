"""Regras das ferramentas: o que pode ir para a nuvem e o que roda em fila (Etapa 12 da reorganização).

Saíram do main.py sem mudar um nome. A foto tests/dados/politicas_antes.json confere os conjuntos, e o
tests/test_invariantes.py garante que a lista do modo privado só cresce enquanto a ferramenta existir.
O main.py reexporta os nomes (core/cerebro_gemma e os testes usam main.FERRAMENTAS_NUVEM_IA). A função
bloqueio_do_modo_privado continua no main.py por enquanto (usa o carregar_automacoes, que os testes trocam).
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
