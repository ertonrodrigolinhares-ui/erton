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

# Etapa 14 (b): as listas são calculadas da ficha de cada ferramenta (fichas.py), com os mesmos nomes de antes.
from cerebro.ferramentas.fichas import (  # noqa: E402,F401
    EXECUTORES, FERRAMENTAS_DESLIGADAS, FERRAMENTAS_NUVEM_IA, MUDAM_ALGO,
    REGRAS_DE_NUVEM, RESERVA_FERRAMENTAS_ESSENCIAIS,
)

AVISO_MODO_PRIVADO = frase("modo_privado_nuvem")  # o texto fica no core/frases.py (Etapa 8)


def bloqueio_do_modo_privado(nome: str, args: dict | None = None) -> str | None:
    """Jarvis Ultron: no modo privado, a recusa (em português) para uma ferramenta que usa IA na nuvem;
    None quando pode rodar. Vale para o Gemma, o painel Ultron e qualquer outra chamada."""
    from core.cerebro_gemma import cerebro_gemma

    if not cerebro_gemma():
        return None
    args = args or {}
    if nome in FERRAMENTAS_NUVEM_IA:
        return AVISO_MODO_PRIVADO
    regra = REGRAS_DE_NUVEM.get(nome)  # ex.: o resumo do youtube_video é feito pelo Gemini (fichas.py)
    if regra is not None and regra(args):
        return AVISO_MODO_PRIVADO
    from cerebro.ferramentas.registro import carregar_automacoes  # (aqui, para não dar laço de import)

    automacao = carregar_automacoes().ferramentas.get(nome)
    if automacao is not None and getattr(automacao, "usa_ia_nuvem", False):
        return AVISO_MODO_PRIVADO
    return None


def resposta_de_desligada(nome: str) -> str:
    """O que volta para o modelo quando ele chama uma ferramenta desligada (nada é chamado)."""
    return (f"Tool '{nome}' ({FERRAMENTAS_DESLIGADAS[nome]}) is turned off in Jarvis Ultron. "
            "Do not try to do this with another tool. Tell the user, in one short sentence in Portuguese, "
            "that you do not do this.")
