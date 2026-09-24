"""Conversa por voz em tempo real com o Gemini Live (a mesma API usada no projeto JARVIS-OS).

Você fala e o Gemini ouve direto, responde com voz natural e pode ser interrompido,
como numa ligação. As ferramentas do Jarvis (planilhas, WhatsApp, lembretes...) continuam
funcionando, e a resposta pode passar pelo efeito de voz escolhido (Ultron, robô).
Usa a mesma chave gratuita do Gemini.
"""

import asyncio
import threading

from google import genai
from google.genai import errors, types

from . import voz
from .persona import prompt_sistema

# Vozes do Gemini Live: nome usado pela API -> descrição na tela
VOZES_AO_VIVO = {
    "Charon": "Charon - masculina, grave e firme",
    "Fenrir": "Fenrir - masculina, enérgica",
    "Orus": "Orus - masculina, séria",
    "Puck": "Puck - masculina, animada",
    "Schedar": "Schedar - masculina, calma",
    "Zubenelgenubi": "Zubenelgenubi - masculina, casual",
    "Kore": "Kore - feminina, firme",
    "Aoede": "Aoede - feminina, leve",
    "Leda": "Leda - feminina, jovem",
}
VOZ_RESERVA = "Puck"
MODELO_PADRAO = "gemini-2.5-flash-native-audio-preview-12-2025"

TAXA_ENVIO = 16000   # o Gemini Live recebe áudio de 16 kHz
TAXA_RECEBIDA = 24000  # e devolve áudio de 24 kHz
BLOCO_MICROFONE = 1024

INSTRUCOES_AO_VIVO = """

Esta é uma conversa por voz em tempo real: fale de forma natural e breve, como numa ligação. \
Sempre em português do Brasil."""


def escolher_modelo(cliente, preferido: str = "") -> str:
    """Escolhe um modelo com suporte a conversa ao vivo disponível para a chave."""
    try:
        modelos = list(cliente.models.list())
    except Exception:
        return preferido or MODELO_PADRAO
    ao_vivo = []
    for modelo in modelos:
        acoes = {str(a).lower() for a in (getattr(modelo, "supported_actions", None) or [])}
        nome = str(getattr(modelo, "name", "") or "").removeprefix("models/")
        if "bidigeneratecontent" in acoes and nome:
            ao_vivo.append(nome)
    if not ao_vivo:
        return preferido or MODELO_PADRAO
    if preferido in ao_vivo:
        return preferido

    def prioridade(nome: str):
        n = nome.lower()
        return (0 if "native-audio" in n else 1 if "live" in n else 2, "preview" in n, nome)

    return sorted(ao_vivo, key=prioridade)[0]


class _Parar(Exception):
    """Usada para encerrar a sessão de propósito."""


class _Reconectar(Exception):
    """O servidor pediu para reconectar (sessões ao vivo têm tempo limite)."""


class SessaoAoVivo:
    def __init__(self, chave: str, usuario: str, voz_ao_vivo: str, efeito: str,
                 ferramentas: list, ao_texto, ao_estado, ao_terminar, modelo: str = ""):
        """ao_texto(quem, texto): mostra uma fala; ao_estado(texto): atualiza o status;
        ao_terminar(mensagem_ou_None): chamada uma vez, quando a sessão termina."""
        self.chave = chave
        self.usuario = usuario
        self.voz = voz_ao_vivo if voz_ao_vivo in VOZES_AO_VIVO else "Charon"
        self.efeito = efeito
        self.ferramentas = {f.__name__: f for f in ferramentas}
        self._lista_ferramentas = ferramentas
        self.ao_texto = ao_texto
        self.ao_estado = ao_estado
        self.ao_terminar = ao_terminar
        self.modelo_preferido = modelo
        self._parar = threading.Event()
        self._loop = None
        self._sessao = None
        self._alca_retomada = None  # permite continuar a mesma conversa ao reconectar
        self._falando = False
        self._fim_da_fala = False
        self.thread = None

    # ---------- controle (chamado pela janela) ----------

    def iniciar(self) -> None:
        self.thread = threading.Thread(target=self._rodar, daemon=True)
        self.thread.start()

    def parar(self) -> None:
        self._parar.set()

    def enviar_texto(self, texto: str) -> None:
        """Manda um texto digitado (ou um aviso) para a conversa ao vivo."""
        if self._loop and self._sessao:
            conteudo = {"role": "user", "parts": [{"text": texto}]}
            asyncio.run_coroutine_threadsafe(
                self._sessao.send_client_content(turns=conteudo, turn_complete=True), self._loop)

    # ---------- execução ----------

    def _rodar(self) -> None:
        mensagem = None
        try:
            asyncio.run(self._principal())
        except Exception as erro:  # nunca deixar a janela sem saber que acabou
            mensagem = _explicar_erro(erro)
        self.ao_terminar(mensagem)

    async def _principal(self) -> None:
        cliente = genai.Client(api_key=self.chave, http_options={"api_version": "v1beta"})
        self.ao_estado("Conectando ao Gemini ao vivo...")
        modelo = await asyncio.to_thread(escolher_modelo, cliente, self.modelo_preferido)
        declaracoes = [types.FunctionDeclaration.from_callable(client=cliente._api_client, callable=f)
                       for f in self._lista_ferramentas]
        falhas_seguidas = 0
        primeira_vez = True

        while not self._parar.is_set():
            try:
                config = self._configuracao(declaracoes)
                async with cliente.aio.live.connect(model=modelo, config=config) as sessao:
                    self._sessao = sessao
                    self._loop = asyncio.get_running_loop()
                    falhas_seguidas = 0
                    if primeira_vez:
                        primeira_vez = False
                        await sessao.send_client_content(turns={"role": "user", "parts": [{
                            "text": "(O usuário acabou de ligar o modo ao vivo. Cumprimente-o em uma frase curta.)"}]})
                    await self._conversar(sessao)
            except _Parar:
                return
            except _Reconectar:
                self.ao_estado("Reconectando...")
                continue
            except errors.APIError as erro:
                texto = str(erro).lower()
                if "api key" in texto or getattr(erro, "code", None) in (401, 403):
                    raise
                if "voice" in texto and self.voz != VOZ_RESERVA:
                    self.ao_texto("Jarvis", f"A voz {self.voz} não está disponível; vou usar a {VOZ_RESERVA}.")
                    self.voz = VOZ_RESERVA
                    continue
                falhas_seguidas += 1
                if falhas_seguidas >= 3:
                    raise
                self.ao_estado("Conexão instável, tentando de novo...")
                await asyncio.sleep(2 * falhas_seguidas)
            finally:
                self._sessao = None

    def _configuracao(self, declaracoes) -> types.LiveConnectConfig:
        return types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            system_instruction=prompt_sistema(self.usuario, com_ferramentas=True) + INSTRUCOES_AO_VIVO,
            tools=[types.Tool(function_declarations=declaracoes)] if declaracoes else None,
            input_audio_transcription=types.AudioTranscriptionConfig(),
            output_audio_transcription=types.AudioTranscriptionConfig(),
            speech_config=types.SpeechConfig(voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=self.voz))),
            context_window_compression=types.ContextWindowCompressionConfig(sliding_window=types.SlidingWindow()),
            session_resumption=types.SessionResumptionConfig(handle=self._alca_retomada),
        )

    async def _conversar(self, sessao) -> None:
        audio_recebido: asyncio.Queue = asyncio.Queue()
        tarefas = [
            asyncio.create_task(self._microfone(sessao)),
            asyncio.create_task(self._receber(sessao, audio_recebido)),
            asyncio.create_task(self._tocar(audio_recebido)),
            asyncio.create_task(self._vigiar_parada()),
        ]
        prontas, pendentes = await asyncio.wait(tarefas, return_when=asyncio.FIRST_EXCEPTION)
        for tarefa in pendentes:
            tarefa.cancel()
        await asyncio.gather(*pendentes, return_exceptions=True)
        for tarefa in prontas:
            if tarefa.exception():
                raise tarefa.exception()

    async def _vigiar_parada(self) -> None:
        while not self._parar.is_set():
            await asyncio.sleep(0.2)
        raise _Parar()

    async def _microfone(self, sessao) -> None:
        loop = asyncio.get_running_loop()
        fila: asyncio.Queue = asyncio.Queue()

        def ao_captar(dados, quadros, tempo, status):
            # Enquanto o Jarvis fala, o microfone fica em pausa para ele não ouvir a própria voz.
            if not self._falando:
                loop.call_soon_threadsafe(fila.put_nowait, bytes(dados))

        with voz.sounddevice.RawInputStream(samplerate=TAXA_ENVIO, channels=1, dtype="int16",
                                            blocksize=BLOCO_MICROFONE, callback=ao_captar):
            self.ao_estado("Ao vivo: pode falar")
            while True:
                dados = await fila.get()
                await sessao.send_realtime_input(
                    audio=types.Blob(data=dados, mime_type=f"audio/pcm;rate={TAXA_ENVIO}"))

    async def _receber(self, sessao, audio_recebido: asyncio.Queue) -> None:
        voce, jarvis = [], []
        while True:
            recebeu_algo = False
            async for mensagem in sessao.receive():
                recebeu_algo = True
                if mensagem.session_resumption_update and mensagem.session_resumption_update.new_handle:
                    self._alca_retomada = mensagem.session_resumption_update.new_handle
                if mensagem.go_away is not None:
                    raise _Reconectar()
                if mensagem.data:
                    self._fim_da_fala = False
                    audio_recebido.put_nowait(mensagem.data)

                conteudo = mensagem.server_content
                if conteudo:
                    if conteudo.interrupted:
                        _esvaziar(audio_recebido)
                    if conteudo.input_transcription and conteudo.input_transcription.text:
                        voce.append(conteudo.input_transcription.text)
                    if conteudo.output_transcription and conteudo.output_transcription.text:
                        jarvis.append(conteudo.output_transcription.text)
                    if conteudo.turn_complete:
                        self._fim_da_fala = True
                        for quem, partes in (("Você", voce), ("Jarvis", jarvis)):
                            texto = " ".join("".join(partes).split())
                            if texto:
                                self.ao_texto(quem, texto)
                        voce, jarvis = [], []

                if mensagem.tool_call:
                    respostas = [await self._executar(chamada)
                                 for chamada in mensagem.tool_call.function_calls or []]
                    await sessao.send_tool_response(function_responses=respostas)
                    self.ao_estado("Ao vivo: pode falar")
            if not recebeu_algo:  # o servidor fechou a conexão
                raise _Reconectar()

    async def _executar(self, chamada) -> types.FunctionResponse:
        funcao = self.ferramentas.get(chamada.name)
        if funcao is None:
            resultado = f"Ferramenta {chamada.name} não existe."
        else:
            # Roda fora do laço de áudio: a ferramenta pode pedir confirmação na tela.
            resultado = await asyncio.to_thread(funcao, **dict(chamada.args or {}))
        return types.FunctionResponse(id=chamada.id, name=chamada.name, response={"result": str(resultado)})

    async def _tocar(self, audio_recebido: asyncio.Queue) -> None:
        efeito = voz.EfeitoContinuo(self.efeito, TAXA_RECEBIDA)
        saida = voz.sounddevice.RawOutputStream(samplerate=TAXA_RECEBIDA, channels=1, dtype="int16")
        saida.start()
        try:
            while True:
                try:
                    pedaco = await asyncio.wait_for(audio_recebido.get(), timeout=0.1)
                except asyncio.TimeoutError:
                    if self._falando and self._fim_da_fala and audio_recebido.empty():
                        await asyncio.sleep(0.3)  # deixa o eco do alto-falante acabar
                        self._falando = False
                        self.ao_estado("Ao vivo: pode falar")
                    continue
                if not self._falando:
                    self._falando = True
                    self.ao_estado("Ao vivo: falando...")
                await asyncio.to_thread(saida.write, efeito.processar(pedaco))
        finally:
            saida.stop()
            saida.close()


def _esvaziar(fila: asyncio.Queue) -> None:
    while not fila.empty():
        fila.get_nowait()


def _explicar_erro(erro: Exception) -> str:
    texto = str(erro)
    if "api key" in texto.lower():
        return "Minha chave do Gemini não é válida. Clique em 'Trocar chave'."
    if isinstance(erro, errors.APIError) and getattr(erro, "code", None) == 429:
        return "O limite gratuito do modo ao vivo acabou por agora. Tente mais tarde ou use o modo normal."
    if "PortAudio" in texto or "device" in texto.lower():
        return "Não consegui usar o microfone ou o alto-falante. " + voz.diagnostico_microfone()
    return f"O modo ao vivo parou: {texto[:200]}"
