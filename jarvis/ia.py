"""Escolhe qual IA o Jarvis usa (JARVIS_IA=gemini ou claude na configuração)."""

from .config import Config


def criar_cerebro(config: Config, confirmar=None, avisar=None, ao_usar=None):
    """Retorna o cérebro configurado, ou None se ainda não houver chave.

    confirmar/avisar/ao_usar ligam as ferramentas (planilhas, mensagens, código...).
    As ferramentas só existem no Gemini; o Claude aqui apenas conversa.
    """
    if not config.chave_api:
        return None
    if config.ia == "claude":
        from .cerebro_claude import CerebroClaude
        return CerebroClaude(config.nome_usuario, config.claude_modelo, config.claude_esforco)
    from .cerebro_gemini import CerebroGemini
    return CerebroGemini(config.nome_usuario, config.gemini_modelo, config.chave_api,
                         confirmar=confirmar, avisar=avisar, ao_usar=ao_usar)
