"""Tela e cérebro do Jarvis Ultron em dois programas separados (Jarvis Ultron).

Por quê: num programa só, a tela (o anel animado) e o cérebro (voz, IA, ferramentas) disputam o
mesmo "motor" do Python. Desenhando, a tela atrasava as tarefas; pensando, o cérebro travava a tela.
Separados, cada um roda no seu próprio programa e um nunca espera pelo outro.

Como funciona:
  - O "Iniciar Jarvis Ultron" abre a TELA (main.py). Ela liga o CÉREBRO como um segundo programa
    (core/processo_cerebro.py) e os dois conversam por um canal local, só dentro deste PC, protegido
    por uma senha aleatória criada a cada abertura.
  - O cérebro usa `UIRemota`, que tem os mesmos métodos da tela de verdade (write_log, set_state...):
    cada chamada vira uma mensagem curta para a tela. Nada no cérebro precisa saber que a tela está
    em outro programa.
  - A tela usa `PonteTela`: recebe as mensagens e aplica na janela (no fio da tela), devolve ao
    cérebro o texto digitado, a troca de voz, o mudo, etc., e religa o cérebro se ele cair.
  - Automações que desenham na tela (painel Stark, painel Ultron) rodam no programa da tela, com
    `JarvisNaTela` no lugar do Jarvis.

Para voltar ao jeito antigo (um programa só): JARVIS_UM_PROCESSO=1 no .env.
"""

from __future__ import annotations

import os
import secrets
import subprocess
import sys
import threading
import time
from collections import deque
from pathlib import Path

# Métodos da tela que o cérebro pode chamar (todos de mão única: não devolvem nada).
METODOS_TELA = frozenset({
    "write_log", "set_state", "set_voice_level", "set_muted_threadsafe", "set_listening_status",
    "start_speaking", "stop_speaking", "sync_voice_display",
    "show_subtitle", "clear_subtitle", "start_subtitle_hold",
    "show_vision_preview", "hide_vision_preview",
    "show_research_progress", "update_research_progress", "finish_research_progress",
    "hide_research_progress",
    "show_presentation_progress", "update_presentation_progress", "finish_presentation_progress",
    "hide_presentation_progress",
    "show_toast", "show_tool_progress", "hide_tool_progress",
    "set_theme", "set_graphics_quality", "handle_ui_command", "toggle_compact_mode", "notificar",
})

# Avisos da tela para o cérebro (o que o usuário fez na janela).
CHAMADAS_DO_CEREBRO = ("on_text_command", "on_voice_change", "on_name_change",
                       "on_tts_provider_change", "on_quit_requested")

# Configurações que a tela pode ter mudado depois de abrir (a chave digitada na tela, a voz...).
PREFIXOS_AMBIENTE = ("GEMINI_", "JARVIS_", "GROQ_", "ELEVENLABS_", "HERMES_", "OPENAI_")

INTERVALO_VOLUME = 0.025      # no máximo 40 avisos de volume da voz por segundo
ESPERA_CONEXAO = 90           # segundos para o cérebro abrir e se conectar (1ª vez é mais lenta)
MAX_RELIGADAS = 3             # religadas automáticas a cada 5 minutos


def modo_separado() -> bool:
    """True quando a tela e o cérebro devem rodar em programas separados (o padrão)."""
    if os.environ.get("JARVIS_UM_PROCESSO", "").strip().lower() in ("1", "sim", "true", "yes"):
        return False
    if getattr(sys, "frozen", False):  # aplicativo empacotado: não dá para abrir "python -m ..."
        return False
    return True


def _ambiente_para_o_cerebro() -> dict:
    return {k: v for k, v in os.environ.items()
            if k.startswith(PREFIXOS_AMBIENTE) and not k.startswith("JARVIS_PONTE_")}


# ======================================================================= lado do CÉREBRO

class UIRemota:
    """A "tela" que o cérebro enxerga: mesmos métodos da JarvisUI, mas em outro programa."""

    remota = True
    _voice_combo = None  # o seletor de voz fica na tela; a voz chega por on_voice_change

    def __init__(self, conexao):
        self._conexao = conexao
        self._trava_envio = threading.Lock()
        self._pronto = threading.Event()
        self._fechada = threading.Event()
        self._muted = False
        self._current_file = None
        self._ultimo_volume = 0.0
        self._jarvis = None
        self._guardadas = []  # chamadas da tela que chegaram antes de o cérebro ficar pronto
        self._trava_guardadas = threading.Lock()
        self.on_text_command = None
        self.on_voice_change = None
        self.on_name_change = None
        self.on_tts_provider_change = None
        self.on_quit_requested = None

    # ----- estado espelhado da tela
    @property
    def muted(self) -> bool:
        return self._muted

    @muted.setter
    def muted(self, valor: bool) -> None:
        self.set_muted_threadsafe(bool(valor))

    @property
    def current_file(self):
        return self._current_file

    # ----- envio
    def _enviar(self, mensagem) -> bool:
        if self._fechada.is_set():
            return False
        try:
            with self._trava_envio:
                self._conexao.send(mensagem)
            return True
        except (OSError, EOFError, ValueError):
            self._tela_fechou()
            return False

    def __getattr__(self, nome):
        # só chega aqui o que não existe na classe: os métodos da tela viram mensagens
        if nome in METODOS_TELA:
            def chamar(*args, **kwargs):
                self._enviar(("chamar", nome, args, kwargs))
            return chamar
        raise AttributeError(nome)

    def set_voice_level(self, nivel: float) -> None:
        agora = time.monotonic()
        if nivel > 0 and agora - self._ultimo_volume < INTERVALO_VOLUME:
            return  # a esfera não precisa de mais que isso; poupa o canal
        self._ultimo_volume = agora
        self._enviar(("chamar", "set_voice_level", (float(nivel),), {}))

    def set_muted_threadsafe(self, valor: bool) -> None:
        self._muted = bool(valor)  # vale na hora para o cérebro, sem esperar a tela responder
        self._enviar(("chamar", "set_muted_threadsafe", (bool(valor),), {}))

    def start_speaking(self) -> None:
        self._enviar(("chamar", "set_state", ("SPEAKING",), {}))

    def stop_speaking(self) -> None:
        if not self._muted:
            self._enviar(("chamar", "set_state", ("LISTENING",), {}))

    def abrir_ultron(self, fechar: bool = False) -> None:
        self._enviar(("abrir_ultron", bool(fechar)))

    def wait_for_api_key(self) -> None:
        """Espera a tela terminar a configuração (chave do Gemini etc.)."""
        while not self._pronto.wait(0.2):
            if self._fechada.is_set():
                raise SystemExit(0)

    # ----- recepção
    def iniciar(self) -> None:
        threading.Thread(target=self._receber, daemon=True, name="PonteCerebro").start()
        self._enviar(("ola", os.getpid()))

    def ligar_jarvis(self, jarvis) -> None:
        """Manda para a tela, de tempos em tempos, o estado do cérebro (para os painéis).
        Também entrega o que o usuário digitou enquanto o cérebro ainda abria."""
        self._jarvis = jarvis
        with self._trava_guardadas:
            guardadas, self._guardadas = self._guardadas, None
        for nome, args in guardadas or ():
            self._chamar(nome, args)

        def laco():
            ultimo = None
            while not self._fechada.is_set():
                estado = estado_do_cerebro(jarvis)
                if estado != ultimo and self._enviar(("estado", estado)):
                    ultimo = estado
                time.sleep(1.0)

        threading.Thread(target=laco, daemon=True, name="PonteEstado").start()

    def _receber(self) -> None:
        while not self._fechada.is_set():
            try:
                mensagem = self._conexao.recv()
            except (OSError, EOFError, ValueError):
                self._tela_fechou()
                return
            try:
                self._tratar(mensagem)
            except Exception as erro:  # mensagem estranha nunca derruba o cérebro
                print(f"[Ponte] Mensagem da tela ignorada: {erro}")

    def _tratar(self, mensagem) -> None:
        tipo = mensagem[0]
        if tipo == "pronto":
            os.environ.update({str(k): str(v) for k, v in dict(mensagem[1]).items()})
            self._pronto.set()
        elif tipo == "estado_tela":
            estado = dict(mensagem[1])
            self._muted = bool(estado.get("muted", self._muted))
            self._current_file = estado.get("current_file", self._current_file)
        elif tipo == "chamada":
            nome, args = mensagem[1], tuple(mensagem[2])
            if nome not in CHAMADAS_DO_CEREBRO:
                return
            with self._trava_guardadas:
                if self._guardadas is not None and nome != "on_quit_requested":
                    # o cérebro ainda está abrindo: guarda (até 20) e entrega quando ficar pronto
                    if len(self._guardadas) < 20:
                        self._guardadas.append((nome, args))
                    return
            self._chamar(nome, args)
        elif tipo == "rodar_ultron":
            jarvis = self._jarvis
            if jarvis is not None:
                jarvis.rodar_automacao_ultron(str(mensagem[1]), dict(mensagem[2] or {}))

    def _chamar(self, nome, args) -> None:
        funcao = getattr(self, nome, None)
        if callable(funcao):
            # em outro fio: responder pode demorar (a IA pensando) e o canal não pode parar
            threading.Thread(target=_sem_derrubar, args=(funcao, args), daemon=True,
                             name=f"Tela-{nome}").start()

    def _tela_fechou(self) -> None:
        if self._fechada.is_set():
            return
        self._fechada.set()
        sair = self.on_quit_requested
        if callable(sair):
            _sem_derrubar(sair, ())

        def encerrar():
            time.sleep(3.0)  # tempo para o cérebro fechar a conexão com a IA
            os._exit(0)

        threading.Thread(target=encerrar, daemon=True, name="PonteFim").start()


def estado_do_cerebro(jarvis) -> dict:
    from core.cerebro_gemma import CerebroGemma

    reserva = getattr(jarvis, "_reserva", None)
    return {
        "modo_reserva": bool(getattr(jarvis, "_modo_reserva", False)),
        "conectado": getattr(jarvis, "session", None) is not None,
        "cerebro": "gemma" if isinstance(reserva, CerebroGemma) else (
            "groq" if getattr(jarvis, "_modo_reserva", False) else "gemini"),
    }


def _sem_derrubar(funcao, args) -> None:
    try:
        funcao(*args)
    except Exception as erro:
        print(f"[Ponte] {getattr(funcao, '__name__', 'chamada')}: {erro}")


# ======================================================================= lado da TELA

class JarvisNaTela:
    """O "Jarvis" que as automações de tela enxergam no programa da tela."""

    def __init__(self, ui, ponte):
        self.ui = ui
        self._ponte = ponte
        self._modo_reserva = False
        self._cerebro_nome = "gemini"
        self.session = None  # só diz se o cérebro está conectado à IA (não é usado para enviar)

    def rodar_automacao_ultron(self, nome: str, args: dict | None = None) -> None:
        self._ponte.enviar(("rodar_ultron", str(nome), dict(args or {})))

    def atualizar(self, estado: dict) -> None:
        self._modo_reserva = bool(estado.get("modo_reserva"))
        self._cerebro_nome = str(estado.get("cerebro", "gemini"))
        self.session = object() if estado.get("conectado") else None


class PonteTela:
    """No programa da tela: liga o cérebro, troca mensagens com ele e o religa se cair."""

    def __init__(self, ui, ao_falhar=None, ao_conectar=None, comando=None, pasta: Path | None = None):
        from PyQt6.QtCore import QObject, QTimer, pyqtSignal

        class _NoFioDaTela(QObject):
            pedido = pyqtSignal(object)

        self.ui = ui
        self.ao_falhar = ao_falhar  # chamado se o cérebro não abrir: volta ao modo de um programa só
        self.ao_conectar = ao_conectar  # chamado (no fio da tela) na 1ª vez que o cérebro conecta
        self._ja_conectou = False
        self._comando = list(comando or [sys.executable, "-u", "-m", "core.processo_cerebro"])
        self._pasta = Path(pasta or Path(__file__).resolve().parent.parent)
        self._conexao = None
        self._trava_envio = threading.Lock()
        self._processo = None
        self._ouvinte = None
        self._encerrando = False
        self._aberto_em = 0.0
        self._religadas = deque()
        self._pronto_enviado = False
        self._ultimo_estado_tela = None
        self.jarvis = JarvisNaTela(ui, self)

        self._no_fio = _NoFioDaTela()
        self._no_fio.pedido.connect(self._aplicar)

        self._relogio = QTimer()
        self._relogio.timeout.connect(self._vigiar)
        self._relogio.start(250)

        # o que o usuário faz na janela vai para o cérebro
        for nome in CHAMADAS_DO_CEREBRO:
            setattr(ui, nome, self._repassar(nome))

    # ----- ciclo de vida
    def iniciar(self) -> None:
        from multiprocessing.connection import Listener

        chave = secrets.token_bytes(32)
        self._ouvinte = Listener(("127.0.0.1", 0), authkey=chave)
        porta = self._ouvinte.address[1]
        ambiente = dict(os.environ)
        ambiente.update({"JARVIS_PONTE_PORTA": str(porta), "JARVIS_PONTE_CHAVE": chave.hex(),
                         "JARVIS_PROCESSO": "cerebro", "PYTHONUNBUFFERED": "1"})
        try:
            self._processo = subprocess.Popen(self._comando, cwd=str(self._pasta), env=ambiente)
        except OSError as erro:
            self._falhou(f"não consegui abrir o cérebro ({erro})")
            return
        self._aberto_em = time.monotonic()
        ouvinte = self._ouvinte
        threading.Thread(target=self._aceitar, args=(ouvinte,), daemon=True, name="PonteAceitar").start()
        print(f"[Ponte] Cérebro aberto em outro programa (pid {self._processo.pid}).")

    def _aceitar(self, ouvinte) -> None:
        try:
            conexao = ouvinte.accept()
        except Exception:
            return  # ouvinte fechado (encerrando ou desistindo)
        with self._trava_envio:
            self._conexao = conexao
        self._pronto_enviado = False
        self._ultimo_estado_tela = None
        threading.Thread(target=self._receber, args=(conexao,), daemon=True, name="PonteTela").start()

    def encerrar(self) -> None:
        """A janela fechou: avisa o cérebro e garante que ele termina."""
        if self._encerrando:
            return
        self._encerrando = True
        self._relogio.stop()
        self.enviar(("chamada", "on_quit_requested", ()))
        processo = self._processo
        if processo is not None and processo.poll() is None:
            try:
                processo.wait(timeout=4)
            except subprocess.TimeoutExpired:
                processo.kill()
        self._fechar_conexao()

    def _fechar_conexao(self) -> None:
        for coisa in (self._conexao, self._ouvinte):
            try:
                if coisa is not None:
                    coisa.close()
            except Exception:
                pass
        self._conexao = None

    def _vigiar(self) -> None:
        """A cada 1/4 de segundo: manda o que mudou na tela e confere se o cérebro está vivo."""
        processo = self._processo
        if processo is None or self._encerrando:
            return
        if processo.poll() is not None:
            self._cerebro_caiu(processo.returncode)
            return
        if self._conexao is None:
            if time.monotonic() - self._aberto_em > ESPERA_CONEXAO:
                processo.kill()
                self._falhou("o cérebro não respondeu a tempo")
            return
        win = getattr(self.ui, "_win", None)
        if not self._pronto_enviado and getattr(win, "_ready", True):
            if self.enviar(("pronto", _ambiente_para_o_cerebro())):
                self._pronto_enviado = True
        estado = {"muted": bool(getattr(self.ui, "muted", False)),
                  "current_file": _arquivo_atual(self.ui)}
        if estado != self._ultimo_estado_tela and self.enviar(("estado_tela", estado)):
            self._ultimo_estado_tela = estado

    def _cerebro_caiu(self, codigo) -> None:
        self._fechar_conexao()
        agora = time.monotonic()
        while self._religadas and agora - self._religadas[0] > 300:
            self._religadas.popleft()
        if len(self._religadas) >= MAX_RELIGADAS:
            self._processo = None
            self.ui.write_log("ERR: O cérebro do Jarvis parou várias vezes. Feche e abra o Jarvis "
                              "(ou rode o autodiagnóstico).")
            return
        self._religadas.append(agora)
        self.ui.write_log(f"SYS: O cérebro do Jarvis parou (código {codigo}). Religando...")
        self.ui.set_state("LISTENING")
        self.iniciar()

    def _falhou(self, motivo: str) -> None:
        self._fechar_conexao()
        self._processo = None
        if self._ja_conectou:
            # já funcionou antes (é uma religada): não troca de modo no meio do uso
            self.ui.write_log(f"ERR: Não consegui religar o cérebro: {motivo}. Feche e abra o Jarvis.")
            return
        print(f"[Ponte] {motivo}. Voltando ao modo de um programa só.")
        self._relogio.stop()
        for nome in CHAMADAS_DO_CEREBRO:  # o cérebro local registra as dele
            setattr(self.ui, nome, None)
        if callable(self.ao_falhar):
            self.ao_falhar()

    # ----- mensagens
    def enviar(self, mensagem) -> bool:
        with self._trava_envio:
            conexao = self._conexao
            if conexao is None:
                return False
            try:
                conexao.send(mensagem)
                return True
            except (OSError, EOFError, ValueError):
                return False

    def _repassar(self, nome):
        def repassar(*args):
            self.enviar(("chamada", nome, args))
        repassar.__name__ = f"repassar_{nome}"
        return repassar

    def _receber(self, conexao) -> None:
        while True:
            try:
                mensagem = conexao.recv()
            except (OSError, EOFError, ValueError):
                return  # o cérebro fechou; _vigiar decide se religa
            if mensagem and mensagem[0] == "chamar" and mensagem[1] == "set_voice_level":
                _sem_derrubar(self.ui.set_voice_level, tuple(mensagem[2]))  # só grava 2 números
                continue
            self._no_fio.pedido.emit(mensagem)

    def _aplicar(self, mensagem) -> None:
        """No fio da tela: aplica uma mensagem do cérebro na janela."""
        try:
            tipo = mensagem[0]
            if tipo == "chamar":
                nome, args, kwargs = mensagem[1], tuple(mensagem[2]), dict(mensagem[3])
                if nome in METODOS_TELA:
                    getattr(self.ui, nome)(*args, **kwargs)
            elif tipo == "estado":
                self.jarvis.atualizar(dict(mensagem[1]))
            elif tipo == "abrir_ultron":
                abrir = getattr(self.jarvis, "_abrir_ultron", None)
                if callable(abrir):
                    abrir(fechar=bool(mensagem[1]))
            elif tipo == "ola":
                print(f"[Ponte] Cérebro conectado (pid {mensagem[1]}).")
                if not self._ja_conectou:
                    self._ja_conectou = True
                    if callable(self.ao_conectar):
                        self.ao_conectar()
        except Exception as erro:
            print(f"[Ponte] Mensagem do cérebro com problema: {erro}")


def _arquivo_atual(ui):
    try:
        return ui.current_file
    except Exception:
        return None
