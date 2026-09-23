"""Escolhe qual IA o Jarvis usa (JARVIS_IA=gemini ou claude no .env)."""

from .config import Config


def criar_cerebro(config: Config):
    """Retorna o cérebro configurado, ou None se ainda não houver chave."""
    if not config.chave_api:
        return None
    if config.ia == "claude":
        from .cerebro_claude import CerebroClaude
        return CerebroClaude(config.nome_usuario, config.claude_modelo, config.claude_esforco)
    from .cerebro_gemini import CerebroGemini
    return CerebroGemini(config.nome_usuario, config.gemini_modelo, config.chave_api)
