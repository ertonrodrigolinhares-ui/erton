"""IA reserva do Jarvis Ultron: Groq (plano gratuito).

Quando o Gemini ao vivo não consegue conectar (cota esgotada, sobrecarga, fora do ar),
o Jarvis continua funcionando pelo Groq:
- ouve você (depois do "Hey Jarvis") e transcreve com o Whisper do Groq;
- responde com um modelo de texto do Groq;
- fala a resposta com a voz grátis da Microsoft.

Coloque GROQ_API_KEY="gsk_..." no .env (chave grátis em https://console.groq.com/keys).
No modo reserva o Jarvis conversa E executa as tarefas (abrir sites, Metricool, lembretes, análise de
sites...), usando as mesmas ferramentas do Jarvis (chamada de função do Groq).
"""

from __future__ import annotations

import io
import json
import os
import wave

MODELOS_PREFERIDOS = [
    "openai/gpt-oss-120b",
    "llama-3.3-70b-versatile",
    "moonshotai/kimi-k2-instruct",
    "openai/gpt-oss-20b",
    "llama-3.1-8b-instant",
]
MODELOS_TRANSCRICAO = ["whisper-large-v3-turbo", "whisper-large-v3"]
LIMITE_HISTORICO = 30

INSTRUCOES = (
    "Você é o Jarvis Ultron, assistente pessoal do Erton. Responda sempre em português do Brasil, "
    "de forma calma, confiante e precisa, em no máximo 3 frases, porque a resposta será falada. "
    "Não use markdown, listas ou emojis. Você está no modo reserva (Groq), mas MESMO ASSIM consegue "
    "executar tarefas: quando o pedido precisar de uma ação (abrir um site ou app, ver o clima, "
    "Metricool, lembretes, analisar um site, autodiagnóstico, etc.), CHAME a ferramenta certa em vez "
    "de dizer que não consegue. Nunca publique, envie mensagens, compre ou apague nada sem o 'ok' do "
    "Erton na hora. Depois que a ferramenta responder, resuma o resultado em uma ou duas frases."
)
MAX_VOLTAS_FERRAMENTA = 3  # menos idas e vindas = menos gasto do limite grátis do Groq


def gemini_para_groq(declaracoes: list[dict]) -> list[dict]:
    """Converte as ferramentas do Jarvis (formato Gemini) para o formato do Groq/OpenAI."""
    def tipo(t):
        return {"OBJECT": "object", "STRING": "string", "BOOLEAN": "boolean", "ARRAY": "array",
                "INTEGER": "integer", "NUMBER": "number"}.get(str(t or "").upper(), str(t or "string").lower())

    def esquema(no):
        if not isinstance(no, dict):
            return {"type": "string"}
        novo = {"type": tipo(no.get("type", "string"))}
        if no.get("description"):
            novo["description"] = no["description"]
        if "enum" in no:
            novo["enum"] = no["enum"]
        if "properties" in no:
            novo["properties"] = {k: esquema(v) for k, v in no["properties"].items()}
            if no.get("required"):
                novo["required"] = list(no["required"])
        if "items" in no:
            novo["items"] = esquema(no["items"])
        return novo

    ferramentas = []
    for d in declaracoes or []:
        params = d.get("parameters") or {"type": "OBJECT", "properties": {}}
        ferramentas.append({"type": "function", "function": {
            "name": d.get("name", ""), "description": d.get("description", "")[:1024],
            "parameters": esquema(params)}})
    return ferramentas


class ReservaGroq:
    def __init__(self, chave: str, cliente=None):
        if cliente is None:
            import groq

            cliente = groq.Groq(api_key=chave, max_retries=1, timeout=60)
        self.cliente = cliente
        self.modelo = os.environ.get("JARVIS_GROQ_MODELO", "").strip() or None
        self.mensagens = [{"role": "system", "content": INSTRUCOES}]

    @classmethod
    def da_configuracao(cls) -> "ReservaGroq | None":
        chave = os.environ.get("GROQ_API_KEY", "").strip()
        if not chave:
            return None
        try:
            return cls(chave)
        except Exception as erro:
            print(f"[Reserva] Groq indisponível: {erro}")
            return None

    def _escolher_modelo(self) -> str:
        if self.modelo:
            return self.modelo
        try:
            disponiveis = {m.id for m in self.cliente.models.list().data}
            self.modelo = next((m for m in MODELOS_PREFERIDOS if m in disponiveis), None) \
                or (sorted(disponiveis)[0] if disponiveis else MODELOS_PREFERIDOS[0])
        except Exception:
            self.modelo = MODELOS_PREFERIDOS[0]
        return self.modelo

    def responder(self, texto: str, ferramentas=None, executar=None) -> str:
        """Responde e, se `ferramentas`/`executar` forem dados, pode chamar as ferramentas do Jarvis.

        - ferramentas: lista no formato Groq (use gemini_para_groq nas ferramentas do Jarvis);
        - executar: função executar(nome, args_dict) -> texto do resultado.
        """
        self.mensagens.append({"role": "user", "content": texto})
        try:
            conteudo = self._conversar(ferramentas, executar)
        except Exception as erro:
            # tira o pedido do usuário para não sujar o histórico
            while self.mensagens and self.mensagens[-1]["role"] != "system":
                if self.mensagens[-1]["role"] == "user":
                    self.mensagens.pop()
                    break
                self.mensagens.pop()
            return _explicar(erro)
        self._aparar_historico()
        return conteudo

    def _conversar(self, ferramentas, executar) -> str:
        modelo = self._escolher_modelo()
        usar = bool(ferramentas) and callable(executar)
        for _ in range(MAX_VOLTAS_FERRAMENTA if usar else 1):
            extra = {"tools": ferramentas, "tool_choice": "auto"} if usar else {}
            resposta = self.cliente.chat.completions.create(
                model=modelo, messages=self.mensagens, **extra)
            msg = resposta.choices[0].message
            chamadas = getattr(msg, "tool_calls", None) or []
            if not chamadas:
                conteudo = (msg.content or "").strip() or "Pronto."
                self.mensagens.append({"role": "assistant", "content": conteudo})
                return conteudo
            self.mensagens.append({"role": "assistant", "content": msg.content or "",
                                   "tool_calls": [_chamada_dict(c) for c in chamadas]})
            for chamada in chamadas:
                self.mensagens.append({"role": "tool", "tool_call_id": chamada.id,
                                       "content": _rodar_ferramenta(chamada, executar)})
        # Estourou o limite de idas e vindas: pede uma resposta final sem mais ferramentas.
        resposta = self.cliente.chat.completions.create(model=modelo, messages=self.mensagens)
        return (resposta.choices[0].message.content or "").strip() or "Pronto."

    def _aparar_historico(self) -> None:
        if len(self.mensagens) <= LIMITE_HISTORICO + 1:
            return
        cauda = self.mensagens[-LIMITE_HISTORICO:]
        # o histórico não pode começar com uma resposta de ferramenta órfã
        while cauda and cauda[0].get("role") == "tool":
            cauda.pop(0)
        self.mensagens = [self.mensagens[0]] + cauda

    def transcrever(self, pcm: bytes, taxa: int = 16000) -> str:
        """Transforma a fala (PCM int16 mono) em texto com o Whisper do Groq."""
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as arquivo:
            arquivo.setnchannels(1)
            arquivo.setsampwidth(2)
            arquivo.setframerate(taxa)
            arquivo.writeframes(pcm)
        ultimo = None
        for modelo in MODELOS_TRANSCRICAO:
            try:
                resultado = self.cliente.audio.transcriptions.create(
                    file=("fala.wav", buffer.getvalue()), model=modelo, language="pt")
                return (getattr(resultado, "text", "") or "").strip()
            except Exception as erro:
                ultimo = erro
        print(f"[Reserva] Transcrição falhou: {ultimo}")
        return ""


def _chamada_dict(chamada) -> dict:
    return {"id": chamada.id, "type": "function",
            "function": {"name": chamada.function.name, "arguments": chamada.function.arguments}}


def _rodar_ferramenta(chamada, executar) -> str:
    nome = chamada.function.name
    try:
        args = json.loads(chamada.function.arguments or "{}")
        if not isinstance(args, dict):
            args = {}
    except (ValueError, TypeError):
        args = {}
    try:
        resultado = executar(nome, args)
    except Exception as erro:
        return f"A ferramenta {nome} falhou: {str(erro)[:150]}"
    return str(resultado)[:4000] if resultado is not None else "ok"


def _explicar(erro: Exception) -> str:
    nome = type(erro).__name__
    if nome == "AuthenticationError":
        return "A chave do Groq não é válida. Confira a linha GROQ_API_KEY no arquivo .env."
    if nome == "RateLimitError":
        return "Atingi o limite gratuito do Groq por agora. Tente de novo em alguns minutos."
    if nome in ("APIConnectionError", "APITimeoutError"):
        return "Estou sem conexão com a internet no momento."
    return f"A reserva não conseguiu responder agora ({nome})."


# ---------- microfone do modo reserva ----------

BLOCO = 1280  # 80 ms a 16 kHz
VOLUME_FALA = 450  # acima disso consideramos que alguém está falando
SILENCIO_FIM = 1.2  # segundos de silêncio que encerram a frase
FALA_MAXIMA = 15.0


def separar_falas(blocos, portao, pode_ouvir=lambda: True, taxa: int = 16000):
    """Recebe blocos de áudio (int16) e entrega cada frase falada (PCM em bytes).

    Só considera o áudio que o porteiro da palavra de ativação liberar.
    """
    import numpy as np

    gravando, falou, silencio, duracao = [], False, 0.0, 0.0
    for bloco in blocos:
        if not pode_ouvir():
            gravando, falou, silencio, duracao = [], False, 0.0, 0.0
            continue
        liberado = portao.processar(bloco)
        if not liberado:
            continue
        audio = np.frombuffer(liberado, dtype=np.int16)
        segundos = len(audio) / taxa
        volume = float(np.sqrt(np.mean(audio.astype(np.float32) ** 2))) if len(audio) else 0.0
        gravando.append(audio)
        duracao += segundos
        if volume > VOLUME_FALA:
            falou, silencio = True, 0.0
        else:
            silencio += segundos
            if not falou:  # antes de começar a fala, guarda só um pedacinho
                while len(gravando) > 1 and sum(len(a) for a in gravando[1:]) / taxa > 0.5:
                    duracao -= len(gravando.pop(0)) / taxa
        if falou and (silencio >= SILENCIO_FIM or duracao >= FALA_MAXIMA):
            yield np.concatenate(gravando).tobytes()
            gravando, falou, silencio, duracao = [], False, 0.0, 0.0


def capturar_falas(continuar, pode_ouvir, portao, taxa: int = 16000):
    """Abre o microfone e entrega cada frase falada enquanto continuar() for verdadeiro."""
    import sounddevice as sd

    def blocos():
        with sd.InputStream(samplerate=taxa, channels=1, dtype="int16", blocksize=BLOCO) as entrada:
            while continuar():
                dados, _ = entrada.read(BLOCO)
                yield dados[:, 0].copy()

    yield from separar_falas(blocos(), portao, pode_ouvir, taxa)
