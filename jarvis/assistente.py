"""Decide como responder a cada pedido: comandos especiais, comandos locais ou IA."""

from datetime import datetime

from . import comandos

PALAVRAS_SAIR = {"sair", "tchau", "encerrar", "desligar", "ate logo"}
PALAVRAS_ESQUECER = {"esquecer conversa", "nova conversa", "limpar conversa"}

SEM_CHAVE = "Ainda não tenho a chave da IA. Clique em 'Trocar chave' para configurar."


def saudacao(nome: str) -> str:
    hora = datetime.now().hour
    periodo = "Bom dia" if hora < 12 else "Boa tarde" if hora < 18 else "Boa noite"
    return f"{periodo}, {nome}. Jarvis online. Como posso ajudar?"


def remover_palavra_ativacao(texto: str, palavra: str) -> str:
    """No modo voz contínuo, só responde quando ouve a palavra de ativação."""
    texto_normalizado = comandos.normalizar(texto)
    if palavra not in texto_normalizado:
        return ""
    return texto_normalizado.split(palavra, 1)[1].strip(" ,.!?")


def responder(texto: str, cerebro, nome: str) -> tuple[str, str | None]:
    """Devolve (resposta, ação). A ação é "sair", "esquecer" ou None."""
    pedido = comandos.normalizar(texto).strip(" .!?")
    if pedido in PALAVRAS_SAIR:
        return f"Até logo, {nome}.", "sair"
    if pedido in PALAVRAS_ESQUECER:
        if cerebro:
            cerebro.esquecer()
        return "Pronto, começamos uma nova conversa.", "esquecer"

    resposta = comandos.executar(texto)
    if resposta is None:
        resposta = cerebro.perguntar(texto) if cerebro else SEM_CHAVE
    return resposta, None
