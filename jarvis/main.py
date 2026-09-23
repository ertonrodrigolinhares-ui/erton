"""Ponto de entrada do Jarvis.

    python -m jarvis           # modo voz (se disponível)
    python -m jarvis --texto   # modo texto, pelo terminal
"""

import argparse
from datetime import datetime

from . import comandos
from .config import Config
from .voz import Interface

PALAVRAS_SAIR = {"sair", "tchau", "encerrar", "desligar", "ate logo", "até logo"}
PALAVRAS_ESQUECER = {"esquecer conversa", "nova conversa", "limpar conversa"}


def saudacao(nome: str) -> str:
    hora = datetime.now().hour
    periodo = "Bom dia" if hora < 12 else "Boa tarde" if hora < 18 else "Boa noite"
    return f"{periodo}, {nome}. Jarvis online. Como posso ajudar?"


def remover_palavra_ativacao(texto: str, palavra: str) -> str:
    """No modo voz, só responde quando ouve a palavra de ativação ("Jarvis, que horas são?")."""
    texto_normalizado = comandos.normalizar(texto)
    if palavra not in texto_normalizado:
        return ""
    return texto_normalizado.split(palavra, 1)[1].strip(" ,.!?")


def main() -> None:
    parser = argparse.ArgumentParser(description="Jarvis - assistente pessoal em Python")
    parser.add_argument("--texto", action="store_true", help="usar o terminal em vez de voz")
    parser.add_argument("--sem-ia", action="store_true", help="usar apenas os comandos locais")
    args = parser.parse_args()

    config = Config.carregar()
    interface = Interface(usar_voz=not args.texto, idioma=config.idioma)

    cerebro = None
    if not args.sem_ia:
        from .cerebro import Cerebro
        cerebro = Cerebro(config.nome_usuario, config.modelo, config.esforco)

    interface.falar(saudacao(config.nome_usuario))
    if interface.usar_voz:
        interface.falar(f"Diga '{config.palavra_ativacao}' antes de cada pedido.")

    while True:
        entrada = interface.ouvir()
        if not entrada:
            continue
        if interface.usar_voz:
            entrada = remover_palavra_ativacao(entrada, config.palavra_ativacao)
            if not entrada:
                continue

        pedido = comandos.normalizar(entrada)
        if pedido in {comandos.normalizar(p) for p in PALAVRAS_SAIR}:
            interface.falar(f"Até logo, {config.nome_usuario}.")
            break
        if pedido in PALAVRAS_ESQUECER and cerebro:
            cerebro.esquecer()
            interface.falar("Pronto, começamos uma nova conversa.")
            continue

        resposta = comandos.executar(entrada)
        if resposta is None:
            if cerebro:
                resposta = cerebro.perguntar(entrada)
            else:
                resposta = "Não conheço esse comando. Rode sem --sem-ia para eu usar a inteligência artificial."
        interface.falar(resposta)


if __name__ == "__main__":
    main()
