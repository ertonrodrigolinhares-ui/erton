"""Cérebro reserva do Jarvis usando o Groq (tem plano gratuito, é muito rápido).

Entra em ação quando o Gemini trava ou atinge o limite gratuito. Usa as mesmas
ferramentas do Jarvis (planilhas, lembretes, WhatsApp...), mas não faz conversa ao vivo.
"""

import json

import groq
from google.genai import types

from .ferramentas import criar_ferramentas
from .ia_base import IAIndisponivel
from .persona import prompt_sistema

# Em ordem de preferência; o Jarvis usa o primeiro que estiver disponível na sua conta.
MODELOS_PREFERIDOS = [
    "openai/gpt-oss-120b",
    "llama-3.3-70b-versatile",
    "moonshotai/kimi-k2-instruct",
    "openai/gpt-oss-20b",
    "llama-3.1-8b-instant",
]
MAX_PASSOS = 10  # quantas rodadas de ferramentas por pergunta, no máximo
LIMITE_HISTORICO = 40  # mensagens guardadas da conversa


def _minusculo(no):
    """Converte os tipos do formato do Gemini ("STRING") para JSON Schema ("string")."""
    if isinstance(no, dict):
        return {k: (v.lower() if k == "type" and isinstance(v, str) else _minusculo(v)) for k, v in no.items()}
    if isinstance(no, list):
        return [_minusculo(v) for v in no]
    return no


def esquema_ferramenta(funcao) -> dict:
    """Descreve uma ferramenta do Jarvis no formato que o Groq entende."""
    declaracao = types.FunctionDeclaration.from_callable_with_api_option(callable=funcao)
    parametros = {"type": "object", "properties": {}}
    if declaracao.parameters:
        parametros = _minusculo(declaracao.parameters.model_dump(mode="json", exclude_none=True))
    return {"type": "function", "function": {
        "name": declaracao.name, "description": declaracao.description or "", "parameters": parametros}}


class CerebroGroq:
    def __init__(self, usuario: str, chave: str, modelo: str = "", confirmar=None, avisar=None,
                 ao_usar=None, ferramentas=None):
        self.cliente = groq.Groq(api_key=chave, max_retries=1, timeout=60)
        self.usuario = usuario
        self.modelo_preferido = modelo
        self.modelo = None
        if ferramentas is None and confirmar and avisar:
            ferramentas = criar_ferramentas(confirmar, avisar, ao_usar=ao_usar)
        self.ferramentas = ferramentas or []
        self.funcoes = {f.__name__: f for f in self.ferramentas}
        self.esquemas = [esquema_ferramenta(f) for f in self.ferramentas]
        self.esquecer()

    def esquecer(self) -> None:
        self.mensagens = [{"role": "system",
                           "content": prompt_sistema(self.usuario, com_ferramentas=bool(self.funcoes))}]

    def _escolher_modelo(self) -> None:
        if self.modelo:
            return
        try:
            disponiveis = {m.id for m in self.cliente.models.list().data}
        except Exception:
            self.modelo = self.modelo_preferido or MODELOS_PREFERIDOS[0]
            return
        for candidato in [self.modelo_preferido] + MODELOS_PREFERIDOS:
            if candidato and candidato in disponiveis:
                self.modelo = candidato
                return
        self.modelo = sorted(disponiveis)[0] if disponiveis else MODELOS_PREFERIDOS[0]

    def perguntar(self, texto: str) -> str:
        try:
            return self.perguntar_ou_falhar(texto)
        except IAIndisponivel as erro:
            return str(erro)

    def perguntar_ou_falhar(self, texto: str) -> str:
        self._escolher_modelo()
        tamanho_antes = len(self.mensagens)
        self.mensagens.append({"role": "user", "content": texto})
        try:
            for _ in range(MAX_PASSOS):
                extras = {"tools": self.esquemas, "tool_choice": "auto"} if self.esquemas else {}
                resposta = self.cliente.chat.completions.create(
                    model=self.modelo, messages=self.mensagens, **extras)
                mensagem = resposta.choices[0].message
                chamadas = mensagem.tool_calls or []
                registro = {"role": "assistant", "content": mensagem.content or ""}
                if chamadas:
                    registro["tool_calls"] = [{
                        "id": c.id, "type": "function",
                        "function": {"name": c.function.name, "arguments": c.function.arguments},
                    } for c in chamadas]
                self.mensagens.append(registro)
                if not chamadas:
                    self._aparar()
                    return (mensagem.content or "").strip() or "Pronto."
                for chamada in chamadas:
                    self.mensagens.append({"role": "tool", "tool_call_id": chamada.id,
                                           "content": self._executar(chamada.function.name,
                                                                     chamada.function.arguments)})
            return "Fiz vários passos e parei para não entrar em repetição. Como quer que eu continue?"
        except groq.APIError as erro:
            del self.mensagens[tamanho_antes:]  # não deixa a conversa pela metade no histórico
            raise IAIndisponivel(_explicar_erro(erro)) from erro

    def _executar(self, nome: str, argumentos: str) -> str:
        funcao = self.funcoes.get(nome)
        if funcao is None:
            return f"A ferramenta {nome} não existe."
        try:
            parametros = json.loads(argumentos or "{}")
        except json.JSONDecodeError:
            return "Os parâmetros vieram inválidos. Tente de novo."
        try:
            return str(funcao(**parametros))
        except TypeError as erro:
            return f"Parâmetros errados para {nome}: {erro}"

    def _aparar(self) -> None:
        """Mantém só as mensagens recentes, começando sempre numa pergunta do usuário."""
        if len(self.mensagens) <= LIMITE_HISTORICO + 1:
            return
        corte = len(self.mensagens) - LIMITE_HISTORICO
        while corte < len(self.mensagens) and self.mensagens[corte]["role"] != "user":
            corte += 1
        self.mensagens = [self.mensagens[0]] + self.mensagens[corte:]


def _explicar_erro(erro: Exception) -> str:
    if isinstance(erro, groq.AuthenticationError):
        return "Minha chave do Groq não é válida. Clique em 'Trocar chave' e cole a chave correta."
    if isinstance(erro, groq.RateLimitError):
        return "Atingi o limite gratuito do Groq por agora."
    if isinstance(erro, groq.APIConnectionError):
        return "Estou sem conexão com a internet no momento."
    codigo = getattr(erro, "status_code", "?")
    return f"O Groq não conseguiu responder agora (erro {codigo})."
