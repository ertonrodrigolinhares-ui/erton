"""Cérebro do Jarvis usando o Google Gemini (tem plano gratuito)."""

import httpx
from google import genai
from google.genai import errors, types

from .persona import prompt_sistema


class CerebroGemini:
    def __init__(self, usuario: str, modelo: str, chave: str):
        self.cliente = genai.Client(api_key=chave)
        self.modelo = modelo
        self.config = types.GenerateContentConfig(system_instruction=prompt_sistema(usuario))
        self.esquecer()

    def esquecer(self) -> None:
        # O objeto de chat guarda o histórico da conversa sozinho.
        self.chat = self.cliente.chats.create(model=self.modelo, config=self.config)

    def perguntar(self, texto: str) -> str:
        try:
            resposta = self.chat.send_message(texto)
        except errors.ClientError as erro:
            mensagem = str(erro).lower()
            if erro.code in (401, 403) or "api key" in mensagem:
                return "Minha chave do Gemini não é válida. Clique em 'Trocar chave' e cole a chave correta."
            if erro.code == 429:
                return "Atingi o limite gratuito do Gemini por agora. Tente de novo daqui a pouco."
            if erro.code == 404:
                return f"O modelo {self.modelo} não foi encontrado. Ajuste JARVIS_GEMINI_MODELO no arquivo .env."
            return f"O Gemini recusou o pedido (erro {erro.code})."
        except errors.ServerError:
            return "O serviço do Gemini está instável agora. Tente de novo em instantes."
        except httpx.TransportError:
            return "Estou sem conexão com a internet no momento."
        return (resposta.text or "").strip() or "Não consegui responder a isso."
