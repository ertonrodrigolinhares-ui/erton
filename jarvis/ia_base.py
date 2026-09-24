"""Peças comuns aos cérebros do Jarvis."""


class IAIndisponivel(Exception):
    """A IA não conseguiu responder (sem cota, sobrecarregada, sem internet, chave inválida).
    A mensagem já vem pronta para mostrar ao usuário."""
