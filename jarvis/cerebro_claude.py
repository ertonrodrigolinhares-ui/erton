"""Cérebro do Jarvis usando o Claude (API da Anthropic, paga por uso)."""

import anthropic

from .persona import prompt_sistema


class CerebroClaude:
    def __init__(self, usuario: str, modelo: str, esforco: str):
        self.cliente = anthropic.Anthropic()
        self.modelo = modelo
        self.esforco = esforco
        self.sistema = prompt_sistema(usuario) + "\nLatency-sensitive; begin your visible answer immediately."
        self.historico: list = []

    def perguntar(self, texto: str) -> str:
        self.historico.append({"role": "user", "content": texto})
        try:
            with self.cliente.beta.messages.stream(
                model=self.modelo,
                max_tokens=16000,
                system=self.sistema,
                thinking={"type": "adaptive"},
                output_config={"effort": self.esforco},
                messages=self.historico,
                # Se o modelo recusar por política, a API tenta outro modelo automaticamente.
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            ) as stream:
                resposta = stream.get_final_message()
        except anthropic.AuthenticationError:
            self.historico.pop()
            return "Não encontrei uma chave válida da Anthropic. Configure a variável ANTHROPIC_API_KEY."
        except anthropic.RateLimitError:
            self.historico.pop()
            return "Estou recebendo muitas solicitações agora. Tente de novo em alguns segundos."
        except anthropic.APIStatusError as erro:
            self.historico.pop()
            return f"O serviço de IA retornou um erro ({erro.status_code})."
        except anthropic.APIConnectionError:
            self.historico.pop()
            return "Estou sem conexão com a internet no momento."

        if resposta.stop_reason == "refusal":
            self.historico.pop()
            return "Desculpe, não posso ajudar com esse pedido."

        # Guarda o conteúdo completo (inclui blocos de raciocínio) para manter o contexto.
        self.historico.append({"role": "assistant", "content": resposta.content})
        texto_resposta = " ".join(b.text for b in resposta.content if b.type == "text").strip()
        return texto_resposta or "Não tenho uma resposta para isso agora."

    def esquecer(self) -> None:
        self.historico.clear()
