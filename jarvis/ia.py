"""Escolhe qual IA o Jarvis usa (JARVIS_IA=gemini ou claude na configuração).

Com a chave do Groq configurada, ele vira a reserva do Gemini: se o Gemini travar
ou atingir o limite, o Groq responde no lugar, sozinho.
"""

from .config import Config
from .ia_base import IAIndisponivel


class CerebroComReserva:
    """Tenta a IA principal; se ela não conseguir, passa a pergunta para a reserva."""

    def __init__(self, principal, reserva, nome_reserva: str = "Groq"):
        self.principal = principal
        self.reserva = reserva
        self.nome_reserva = nome_reserva
        self.respondeu_pela_reserva = False
        principal.desistir_rapido = True  # não faz você esperar se a reserva pode responder

    @property
    def ferramentas(self):
        return self.principal.ferramentas

    def perguntar(self, texto: str) -> str:
        self.respondeu_pela_reserva = False
        try:
            return self.principal.perguntar_ou_falhar(texto)
        except IAIndisponivel as erro_principal:
            try:
                resposta = self.reserva.perguntar_ou_falhar(texto)
            except IAIndisponivel as erro_reserva:
                return f"{erro_principal} A reserva ({self.nome_reserva}) também falhou: {erro_reserva}"
            self.respondeu_pela_reserva = True
            return resposta

    def esquecer(self) -> None:
        self.principal.esquecer()
        self.reserva.esquecer()


def criar_cerebro(config: Config, confirmar=None, avisar=None, ao_usar=None):
    """Retorna o cérebro configurado, ou None se ainda não houver chave.

    confirmar/avisar/ao_usar ligam as ferramentas (planilhas, mensagens, código...).
    As ferramentas existem no Gemini e no Groq; o Claude aqui apenas conversa.
    """
    if config.ia == "claude":
        if not config.chave_api:
            return None
        from .cerebro_claude import CerebroClaude
        return CerebroClaude(config.nome_usuario, config.claude_modelo, config.claude_esforco)

    principal = reserva = None
    if config.chave_api:
        from .cerebro_gemini import CerebroGemini
        principal = CerebroGemini(config.nome_usuario, config.gemini_modelo, config.chave_api,
                                  confirmar=confirmar, avisar=avisar, ao_usar=ao_usar)
    if config.chave_groq:
        from .cerebro_groq import CerebroGroq
        reserva = CerebroGroq(config.nome_usuario, config.chave_groq, config.groq_modelo,
                              confirmar=confirmar, avisar=avisar, ao_usar=ao_usar,
                              ferramentas=principal.ferramentas if principal else None)
    if principal and reserva:
        return CerebroComReserva(principal, reserva)
    return principal or reserva
