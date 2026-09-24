"""Cérebro do Jarvis usando o Google Gemini (tem plano gratuito).

Se o modelo estiver sobrecarregado ou sem cota, tenta de novo e depois troca
automaticamente para outro modelo do Gemini, mantendo a conversa.
"""

import time

import httpx
from google import genai
from google.genai import errors, types

from .ferramentas import criar_ferramentas
from .ia_base import IAIndisponivel
from .persona import prompt_sistema

# Usados, em ordem, quando o modelo principal falha. Cada um tem sua própria cota gratuita.
MODELOS_RESERVA = ["gemini-flash-lite-latest", "gemini-2.5-flash", "gemini-2.5-flash-lite"]
ESPERAS = [0, 2, 5]  # segundos entre as tentativas no mesmo modelo


class CerebroGemini:
    def __init__(self, usuario: str, modelo: str, chave: str,
                 confirmar=None, avisar=None, ao_usar=None):
        self.cliente = genai.Client(api_key=chave)
        self.modelos = [modelo] + [m for m in MODELOS_RESERVA if m != modelo]
        self.modelo = modelo
        self.usuario = usuario
        self.desistir_rapido = False
        self.ferramentas = []
        if confirmar and avisar:
            self.ferramentas = criar_ferramentas(confirmar, avisar, self.pesquisar, ao_usar,
                                                 analisar_imagem=self.analisar_imagem)
        self.esquecer()

    def esquecer(self) -> None:
        # Recria as instruções (para incluir a memória atualizada) e começa uma conversa nova.
        self.config = types.GenerateContentConfig(
            system_instruction=prompt_sistema(self.usuario, com_ferramentas=bool(self.ferramentas)),
            tools=self.ferramentas or None,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(maximum_remote_calls=20),
        )
        # O objeto de chat guarda o histórico da conversa sozinho.
        self.chat = self.cliente.chats.create(model=self.modelo, config=self.config)

    def _trocar_modelo(self, modelo: str) -> None:
        self.modelo = modelo
        self.chat = self.cliente.chats.create(model=modelo, config=self.config,
                                              history=self.chat.get_history())

    def perguntar(self, texto: str) -> str:
        try:
            return self.perguntar_ou_falhar(texto)
        except IAIndisponivel as erro:
            return str(erro)

    def perguntar_ou_falhar(self, texto: str) -> str:
        """Como perguntar(), mas levanta IAIndisponivel quando o Gemini não consegue responder
        (assim o Jarvis pode passar a pergunta para a IA reserva)."""
        # Com uma IA reserva configurada, desiste mais rápido para não deixar você esperando.
        modelos = [self.modelo] + [m for m in self.modelos if m != self.modelo]
        esperas = ESPERAS
        if self.desistir_rapido:
            modelos, esperas = modelos[:2], ESPERAS[:2]
        ultimo_erro = None
        for modelo in modelos:
            if modelo != self.modelo:
                self._trocar_modelo(modelo)
            for espera in esperas:
                time.sleep(espera)
                try:
                    resposta = self.chat.send_message(texto)
                    return (resposta.text or "").strip() or "Pronto."
                except errors.ClientError as erro:
                    ultimo_erro = erro
                    mensagem = str(erro).lower()
                    if erro.code in (401, 403) or "api key" in mensagem:
                        raise IAIndisponivel("Minha chave do Gemini não é válida. "
                                             "Clique em 'Trocar chave' e cole a chave correta.") from erro
                    if erro.code in (404, 429):
                        break  # modelo inexistente ou cota esgotada: vai para o próximo modelo
                    return f"O Gemini recusou o pedido (erro {erro.code}: {_resumo(erro)})."
                except errors.ServerError as erro:
                    ultimo_erro = erro  # sobrecarregado: espera e tenta de novo
                except httpx.TransportError as erro:
                    raise IAIndisponivel("Estou sem conexão com a internet no momento.") from erro

        if isinstance(ultimo_erro, errors.ClientError) and ultimo_erro.code == 429:
            raise IAIndisponivel("Atingi o limite gratuito do Gemini por agora. "
                                 "Tente de novo daqui a alguns minutos.")
        codigo = getattr(ultimo_erro, "code", "?")
        raise IAIndisponivel(f"O Gemini está sobrecarregado agora (erro {codigo}). "
                             "Tentei outros modelos e não consegui. Tente de novo em um minuto.")

    def pesquisar(self, pergunta: str) -> str:
        """Faz uma consulta separada com a Pesquisa Google ligada e devolve o resumo com fontes."""
        config = types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())],
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )
        ultimo_erro = None
        for modelo in [self.modelo] + [m for m in self.modelos if m != self.modelo]:
            try:
                resposta = self.cliente.models.generate_content(model=modelo, contents=pergunta, config=config)
            except (errors.APIError, httpx.TransportError) as erro:
                ultimo_erro = erro
                continue
            fontes = []
            try:
                for trecho in resposta.candidates[0].grounding_metadata.grounding_chunks or []:
                    if trecho.web:
                        fontes.append(f"- {trecho.web.title}: {trecho.web.uri}")
            except (AttributeError, IndexError, TypeError):
                pass
            texto = (resposta.text or "").strip()
            return texto + ("\n\nFontes:\n" + "\n".join(fontes[:5]) if fontes else "")
        return f"A pesquisa na internet falhou ({_resumo(ultimo_erro)})."


    def analisar_imagem(self, pergunta: str, png: bytes) -> str:
        """Responde uma pergunta sobre uma imagem (usado para ver a tela)."""
        conteudo = [types.Part.from_bytes(data=png, mime_type="image/png"),
                    f"Responda em português do Brasil, de forma objetiva: {pergunta}"]
        ultimo_erro = None
        for modelo in [self.modelo] + [m for m in self.modelos if m != self.modelo]:
            try:
                resposta = self.cliente.models.generate_content(model=modelo, contents=conteudo)
                return (resposta.text or "").strip() or "Não consegui entender a imagem."
            except (errors.APIError, httpx.TransportError) as erro:
                ultimo_erro = erro
        return f"Não consegui analisar a tela ({_resumo(ultimo_erro)})."


def _resumo(erro) -> str:
    return (getattr(erro, "message", None) or str(erro))[:200]
