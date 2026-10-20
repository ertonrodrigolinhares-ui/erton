"""IA reserva do Jarvis Ultron com OUTRA empresa no lugar (ou além) do Groq.

Quando o Gemini ao vivo cai, o Jarvis responde pela reserva. Se o limite grátis do Groq acabar, dá
para usar outra API compatível (o mesmo "idioma" da OpenAI). No .env:

  JARVIS_RESERVA="cerebras"          # cerebras, openrouter, mistral, deepseek, openai, together ou outra
  JARVIS_RESERVA_CHAVE="..."         # a chave dessa empresa
  JARVIS_RESERVA_MODELO="..."        # opcional: o Jarvis escolhe sozinho se ficar vazio
  JARVIS_RESERVA_URL="https://..."   # só para "outra" (ou para trocar o endereço)

Se o GROQ_API_KEY também estiver no .env, os dois ficam em fila: a outra empresa primeiro e, quando
o limite dela acabar, o Groq (e vice-versa na próxima vez). A transcrição da voz usa o Whisper do
próprio PC quando instalado ("Instalar voz local"); senão, o Whisper da OpenAI (se for ela) ou o do Groq.

Planos grátis não devem receber dados de clientes: para isso use o modo privado (Gemma 4 no PC).
"""

from __future__ import annotations

import os

from core import marca
from core.reserva_groq import INSTRUCOES, ReservaGroq, instrucoes_com_perfil

# Endereços conhecidos e os modelos preferidos de cada uma (o Jarvis usa o primeiro que a conta tiver).
EMPRESAS = {
    "cerebras": ("Cerebras", "https://api.cerebras.ai/v1", ["gpt-oss-120b", "llama-3.3-70b", "qwen-3", "llama"]),
    "openrouter": ("OpenRouter", "https://openrouter.ai/api/v1",
                   ["gpt-oss-120b:free", "llama-3.3-70b-instruct:free", ":free"]),
    "mistral": ("Mistral", "https://api.mistral.ai/v1", ["mistral-small-latest", "mistral-medium-latest",
                                                         "mistral-large-latest"]),
    "deepseek": ("DeepSeek", "https://api.deepseek.com/v1", ["deepseek-chat"]),
    "openai": ("OpenAI", "https://api.openai.com/v1", ["gpt-4.1-mini", "gpt-4o-mini", "gpt-4.1", "gpt-4o"]),
    "together": ("Together", "https://api.together.xyz/v1", ["gpt-oss-120b", "Llama-3.3-70B", "llama"]),
}


class ReservaOutra(ReservaGroq):
    """Mesmo jeito de conversar e de chamar as ferramentas da reserva, com outra empresa."""

    def __init__(self, empresa: str, chave: str, url: str = "", modelo: str = "", cliente=None):
        nome, url_padrao, preferidos = EMPRESAS.get(empresa, (empresa.capitalize() or "Reserva", "", []))
        self.empresa, self.nome, self.preferidos = empresa, nome, preferidos
        if cliente is None:
            import openai

            cliente = openai.OpenAI(base_url=url or url_padrao, api_key=chave, max_retries=1, timeout=60)
        self.cliente = cliente
        self.modelo = modelo or None
        self.mensagens = [{"role": "system",
                           "content": instrucoes_com_perfil(INSTRUCOES.replace("modo reserva (Groq)", f"modo reserva ({nome})"))}]
        self._ouvido = None

    @classmethod
    def da_configuracao(cls) -> "ReservaOutra | None":
        chave = os.environ.get("JARVIS_RESERVA_CHAVE", "").strip()
        empresa = os.environ.get("JARVIS_RESERVA", "").strip().lower()
        url = os.environ.get("JARVIS_RESERVA_URL", "").strip()
        if not chave or not empresa or (empresa not in EMPRESAS and not url):
            return None
        try:
            return cls(empresa, chave, url, os.environ.get("JARVIS_RESERVA_MODELO", "").strip())
        except Exception as erro:
            print(f"[Reserva] {empresa} indisponível: {erro}")
            return None

    def _escolher_modelo(self) -> str:
        if self.modelo:
            return self.modelo
        try:
            disponiveis = [m.id for m in self.cliente.models.list().data]
        except Exception:
            disponiveis = []
        for desejado in self.preferidos:
            achado = next((m for m in disponiveis if desejado.lower() in m.lower()), None)
            if achado:
                self.modelo = achado
                return achado
        self.modelo = (disponiveis[0] if disponiveis else (self.preferidos[0] if self.preferidos else "gpt-4o-mini"))
        return self.modelo

    def transcrever(self, pcm: bytes, taxa: int = 16000) -> str:
        """Voz -> texto: Whisper do PC (se instalado), senão o da OpenAI (se for ela), senão o do Groq."""
        from core.cerebro_gemma import whisper_instalado

        if whisper_instalado():
            if self._ouvido is None:
                from core.cerebro_gemma import CerebroGemma

                self._ouvido = CerebroGemma(cliente=object())  # só a parte de ouvir (Whisper no PC)
            texto = self._ouvido.transcrever(pcm, taxa)
            if texto:
                return texto
        if self.empresa == "openai":
            return _whisper_da_api(self.cliente, pcm, taxa, ["whisper-1", "gpt-4o-mini-transcribe"])
        groq = ReservaGroq.da_configuracao()
        if groq is not None:
            return groq.transcrever(pcm, taxa)
        print("[Reserva] Sem como transcrever a voz: rode o 'Instalar voz local' (ou digite).")
        return ""

    def _explicar(self, erro: Exception) -> str:
        tipo = type(erro).__name__
        if tipo == "AuthenticationError":
            return f"A chave da {self.nome} não é válida. Confira a linha JARVIS_RESERVA_CHAVE no arquivo .env."
        if tipo == "RateLimitError":
            return f"Atingi o limite da {self.nome} por agora. Tente de novo em alguns minutos."
        if tipo in ("APIConnectionError", "APITimeoutError"):
            return "Estou sem conexão com a internet no momento."
        if tipo == "NotFoundError":
            return (f"A {self.nome} não tem o modelo {self.modelo}. Apague a linha JARVIS_RESERVA_MODELO do .env "
                    f"para o {marca.NOME_CURTO} escolher sozinho.")
        return f"A reserva ({self.nome}) não conseguiu responder agora ({tipo})."


def _whisper_da_api(cliente, pcm: bytes, taxa: int, modelos) -> str:
    import io
    import wave

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as arquivo:
        arquivo.setnchannels(1)
        arquivo.setsampwidth(2)
        arquivo.setframerate(taxa)
        arquivo.writeframes(pcm)
    for modelo in modelos:
        try:
            r = cliente.audio.transcriptions.create(file=("fala.wav", buffer.getvalue()), model=modelo, language="pt")
            return (getattr(r, "text", "") or "").strip()
        except Exception as erro:
            print(f"[Reserva] Transcrição ({modelo}) falhou: {erro}")
    return ""


ERROS_DE_LIMITE = ("RateLimitError", "AuthenticationError", "PermissionDeniedError", "InternalServerError",
                   "APIConnectionError", "APITimeoutError", "NotFoundError", "ConnectError", "ConnectionError")


class ReservaEmFila:
    """Várias reservas em fila: quando a da vez bate no limite (ou a chave falha), a próxima responde
    e passa a ser a primeira."""

    def __init__(self, reservas):
        self.reservas = list(reservas)

    @property
    def nome(self) -> str:
        return getattr(self.reservas[0], "nome", "Groq")

    def responder(self, texto: str, ferramentas=None, executar=None) -> str:
        ultima = ""
        for i, reserva in enumerate(list(self.reservas)):
            erros = []
            explicar = reserva._explicar
            reserva._explicar = lambda erro, e=erros, x=explicar: (e.append(erro), x(erro))[1]
            try:
                resposta = reserva.responder(texto, ferramentas=ferramentas, executar=executar)
            finally:
                reserva._explicar = explicar
            if not erros or type(erros[-1]).__name__ not in ERROS_DE_LIMITE:
                if i:  # esta funcionou: vira a primeira da fila
                    self.reservas.insert(0, self.reservas.pop(i))
                    print(f"[Reserva] Usando {getattr(reserva, 'nome', 'Groq')} (a anterior bateu no limite).")
                return resposta
            ultima = resposta
        return ultima

    def transcrever(self, pcm: bytes, taxa: int = 16000) -> str:
        for reserva in self.reservas:
            texto = reserva.transcrever(pcm, taxa)
            if texto:
                return texto
        return ""


def _gemma_reserva():
    """O Gemma 4 do PC como primeira reserva, quando instalado (o "Instalar Gemma 4" grava
    JARVIS_GEMMA_MODELO). JARVIS_RESERVA_GEMMA=0 no .env tira ele da fila."""
    if os.environ.get("JARVIS_RESERVA_GEMMA", "1").strip().lower() in ("0", "nao", "não", "false", "off"):
        return None
    if not os.environ.get("JARVIS_GEMMA_MODELO", "").strip():
        return None
    from core.cerebro_gemma import CerebroGemma

    return CerebroGemma.da_configuracao()


def reserva_da_configuracao():
    """A reserva do Jarvis, em fila: Gemma 4 do PC (se instalado), a outra empresa e o Groq."""
    gemma = _gemma_reserva()
    fila = [r for r in (gemma, ReservaOutra.da_configuracao(), ReservaGroq.da_configuracao()) if r is not None]
    if not fila:
        return None
    if gemma is not None:  # sempre em fila: o Gemma aqui é reserva, não o modo privado
        return ReservaEmFila(fila)
    return fila[0] if len(fila) == 1 else ReservaEmFila(fila)
