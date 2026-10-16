import asyncio
import os
import sys
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import cerebro_gemma
from core.cerebro_gemma import CerebroGemma


class ClienteOllamaFalso:
    """Imita o Ollama (API compatível com a da OpenAI)."""

    def __init__(self, roteiro=()):
        self.roteiro = list(roteiro)
        self.pedidos = []
        self.chat = NS(completions=NS(create=self._criar))

    def _criar(self, **pedido):
        self.pedidos.append({**pedido, "messages": list(pedido["messages"])})
        proxima = self.roteiro.pop(0) if self.roteiro else NS(content="ok", tool_calls=None)
        if isinstance(proxima, Exception):
            raise proxima
        return NS(choices=[NS(message=proxima)])


class WhisperFalso:
    def __init__(self):
        self.recebido = None

    def transcribe(self, audio, language, beam_size):
        self.recebido = (audio, language)
        return iter([NS(text=" que horas "), NS(text="são? ")]), None


class CerebroGemmaTests(unittest.TestCase):
    def test_liga_pelo_env(self):
        for valor, esperado in (("gemma", True), ("Gemma4", True), ("local", True), ("gemini", False), ("", False)):
            with patch.dict(os.environ, {"JARVIS_CEREBRO": valor}):
                self.assertEqual(cerebro_gemma.cerebro_gemma(), esperado, valor)

    def test_usa_o_modelo_do_ollama_e_as_instrucoes_do_gemma(self):
        cliente = ClienteOllamaFalso([NS(content="Olá, Erton.", tool_calls=None)])
        with patch.dict(os.environ, {"JARVIS_GEMMA_MODELO": ""}):
            cerebro = CerebroGemma(cliente=cliente)
        self.assertEqual(cerebro.responder("oi"), "Olá, Erton.")
        self.assertEqual(cliente.pedidos[0]["model"], "jarvis-gemma")
        self.assertIn("Jarvis Ultron", cliente.pedidos[0]["messages"][0]["content"])
        self.assertNotIn("Groq", cliente.pedidos[0]["messages"][0]["content"])

    def test_modelo_do_env(self):
        with patch.dict(os.environ, {"JARVIS_GEMMA_MODELO": "gemma4:26b"}):
            self.assertEqual(CerebroGemma(cliente=ClienteOllamaFalso()).modelo, "gemma4:26b")

    def test_chama_ferramenta_e_resume(self):
        chamada = NS(id="1", function=NS(name="weather_report", arguments='{"city":"Campina Grande"}'))
        cliente = ClienteOllamaFalso([NS(content="", tool_calls=[chamada]),
                                      NS(content="Faz 26 graus em Campina Grande.", tool_calls=None)])
        cerebro = CerebroGemma(cliente=cliente)
        feitos = []
        resposta = cerebro.responder("como está o tempo?",
                                     ferramentas=[{"type": "function", "function": {"name": "weather_report"}}],
                                     executar=lambda n, a: feitos.append((n, a)) or "26 graus")
        self.assertEqual(resposta, "Faz 26 graus em Campina Grande.")
        self.assertEqual(feitos, [("weather_report", {"city": "Campina Grande"})])

    def test_ollama_desligado_vira_aviso_em_portugues_e_nao_suja_o_historico(self):
        class APIConnectionError(Exception):
            pass

        cerebro = CerebroGemma(cliente=ClienteOllamaFalso([APIConnectionError("Connection refused")]))
        with patch.object(cerebro_gemma, "ollama_respondendo", return_value=False), \
                patch.object(cerebro_gemma, "garantir_ollama", return_value=False):
            resposta = cerebro.responder("oi")
        self.assertIn("Ollama", resposta)
        self.assertEqual(len(cerebro.mensagens), 1)

    def test_modelo_nao_baixado(self):
        class NotFoundError(Exception):
            pass

        cerebro = CerebroGemma(cliente=ClienteOllamaFalso([NotFoundError("model not found")]))
        self.assertIn("Instalar Gemma 4", cerebro.responder("oi"))

    def test_pedidos_simultaneos_entram_em_fila(self):
        dentro, maximo = [0], [0]
        trava = threading.Lock()

        class Lento(ClienteOllamaFalso):
            def _criar(self, **pedido):
                with trava:
                    dentro[0] += 1
                    maximo[0] = max(maximo[0], dentro[0])
                threading.Event().wait(0.05)
                with trava:
                    dentro[0] -= 1
                return NS(choices=[NS(message=NS(content="ok", tool_calls=None))])

        cerebro = CerebroGemma(cliente=Lento())
        fios = [threading.Thread(target=cerebro.responder, args=(f"pedido {i}",)) for i in range(4)]
        for f in fios:
            f.start()
        for f in fios:
            f.join()
        self.assertEqual(maximo[0], 1)
        self.assertEqual([m["role"] for m in cerebro.mensagens].count("user"), 4)

    def test_transcreve_com_whisper_local(self):
        whisper = WhisperFalso()
        cerebro = CerebroGemma(cliente=ClienteOllamaFalso(), ouvido=("local", whisper))
        texto = cerebro.transcrever(b"\x00\x10" * 16000)
        self.assertEqual(texto, "que horas são?")
        audio, idioma = whisper.recebido
        self.assertEqual(idioma, "pt")
        self.assertEqual(len(audio), 16000)
        self.assertLessEqual(float(abs(audio).max()), 1.0)

    def test_sem_whisper_local_nunca_usa_o_groq(self):
        # modo privado: sem o faster-whisper (ou com "DLL load failed"), a voz NÃO vai para o Groq
        class GroqProibido:
            def Groq(self, *a, **k):
                raise AssertionError("não pode mandar a voz para o Groq no modo privado")

        cerebro = CerebroGemma(cliente=ClienteOllamaFalso())
        with patch.dict(os.environ, {"GROQ_API_KEY": "gsk_falsa", "JARVIS_CEREBRO": "gemma"}), \
                patch.dict(sys.modules, {"faster_whisper": None, "groq": GroqProibido()}):
            self.assertIsNone(cerebro._preparar_ouvido())
            self.assertEqual(cerebro.transcrever(b"\x00\x10" * 16000), "")
        self.assertEqual(cerebro.erro_ouvido, cerebro_gemma.AVISO_SEM_WHISPER)
        self.assertIn("Instalar Gemma 4", cerebro.erro_ouvido)

    def test_checar_ouvido_na_abertura(self):
        cerebro = CerebroGemma(cliente=ClienteOllamaFalso())
        with patch.object(cerebro_gemma, "whisper_instalado", return_value=False):
            self.assertFalse(cerebro.checar_ouvido())
        self.assertEqual(cerebro.erro_ouvido, cerebro_gemma.AVISO_SEM_WHISPER)
        with patch.object(cerebro_gemma, "whisper_instalado", return_value=True):
            self.assertTrue(CerebroGemma(cliente=ClienteOllamaFalso()).checar_ouvido())

    def test_whisper_que_falhou_ao_carregar_tenta_de_novo(self):
        # ex.: sem internet no 1º download do modelo: antes ficava surdo até reabrir o Jarvis
        tentativas = []

        class WhisperModel:
            def __init__(self, *a, **k):
                tentativas.append(1)
                if len(tentativas) == 1:
                    raise RuntimeError("sem internet")

            def transcribe(self, audio, language, beam_size):
                return iter([NS(text="oi")]), None

        cerebro = CerebroGemma(cliente=ClienteOllamaFalso())
        with patch.dict(sys.modules, {"faster_whisper": NS(WhisperModel=WhisperModel)}):
            self.assertEqual(cerebro.transcrever(b"\x00\x10" * 1600), "")
            self.assertEqual(cerebro.erro_ouvido, cerebro_gemma.AVISO_WHISPER_FALHOU)
            self.assertEqual(cerebro.transcrever(b"\x00\x10" * 1600), "")  # espera antes de tentar
            self.assertEqual(len(tentativas), 1)
            cerebro._tentar_ouvido_apos = 0.0  # passou o tempo de espera
            self.assertEqual(cerebro.transcrever(b"\x00\x10" * 1600), "oi")
        self.assertEqual(len(tentativas), 2)
        self.assertIsNone(cerebro.erro_ouvido)

    def test_aquecer_faz_pedido_minimo_com_as_ferramentas(self):
        cliente = ClienteOllamaFalso()
        cerebro = CerebroGemma(cliente=cliente)
        ferramentas = [{"type": "function", "function": {"name": "x"}}]
        with patch.object(cerebro_gemma, "garantir_ollama", return_value=True):
            self.assertTrue(cerebro.aquecer(ferramentas))
        pedido = cliente.pedidos[0]
        self.assertEqual(pedido["max_tokens"], 1)
        self.assertEqual(pedido["tools"], ferramentas)
        self.assertEqual(len(cerebro.mensagens), 1)  # aquecer não entra no histórico


class GemmaNoJarvisTests(unittest.TestCase):
    def _jarvis(self, cerebro):
        import main
        from core.palavra_ativacao import PortaoDeVoz

        class UI:
            def __init__(s):
                s.logs = []
                s.muted = False

            def write_log(s, t):
                s.logs.append(t)

            def set_state(s, estado):
                pass

        jarvis = object.__new__(main.JarvisLive)
        jarvis.ui = UI()
        jarvis._loop = jarvis.session = None
        jarvis._modo_reserva = False
        jarvis._reserva = cerebro
        jarvis._portao = PortaoDeVoz(None, ativo=False)
        jarvis._shutdown_requested = threading.Event()
        jarvis.cloud_safe = False
        jarvis.falado = []
        jarvis._falar_reserva = jarvis.falado.append
        jarvis._reserva_ferramentas = []
        return jarvis

    def test_liga_o_gemma_aquece_e_avisa(self):
        cerebro = CerebroGemma(cliente=ClienteOllamaFalso())
        jarvis = self._jarvis(cerebro)
        with patch.object(type(jarvis), "_escutar_reserva", lambda self: None), \
                patch.object(cerebro_gemma, "garantir_ollama", return_value=True):
            jarvis._ativar_modo_reserva()
            for t in threading.enumerate():
                if t.name == "GemmaAquecer":
                    t.join(5)
        self.assertTrue(jarvis._modo_reserva)
        self.assertTrue(any("Gemma 4 pronto" in l for l in jarvis.ui.logs), jarvis.ui.logs)
        self.assertIn("Gemma 4", jarvis.falado[0])
        self.assertFalse(any("Groq" in l for l in jarvis.ui.logs))

    def test_run_no_modo_gemma_nao_conecta_no_gemini(self):
        jarvis = self._jarvis(CerebroGemma(cliente=ClienteOllamaFalso()))
        ligou = []
        jarvis._ativar_modo_reserva = lambda: ligou.append(1)
        threading.Timer(0.3, jarvis._shutdown_requested.set).start()
        with patch.dict(os.environ, {"JARVIS_CEREBRO": "gemma"}), \
                patch("main.genai.Client", side_effect=AssertionError("não deveria usar o Gemini")):
            asyncio.run(asyncio.wait_for(jarvis.run(), 5))
        self.assertEqual(ligou, [1])

    def test_texto_digitado_vai_para_o_gemma(self):
        cliente = ClienteOllamaFalso([NS(content="Estou aqui, Erton.", tool_calls=None)])
        jarvis = self._jarvis(CerebroGemma(cliente=cliente))
        jarvis._responder_pela_reserva("oi")
        self.assertEqual(jarvis.falado, ["Estou aqui, Erton."])

    def test_modo_privado_sem_gemma_nao_cai_no_gemini(self):
        jarvis = self._jarvis(None)
        jarvis._ativar_modo_reserva = lambda: self.fail("sem Gemma não há reserva para ligar")
        threading.Timer(0.3, jarvis._shutdown_requested.set).start()
        with patch.dict(os.environ, {"JARVIS_CEREBRO": "gemma"}), \
                patch("main.genai.Client", side_effect=AssertionError("não deveria usar o Gemini")), \
                patch("actions.tts_engine.falar_com_voz_do_windows") as voz:
            asyncio.run(asyncio.wait_for(jarvis.run(), 5))
            for t in threading.enumerate():
                if t.name == "AvisoPrivado":
                    t.join(5)
        self.assertTrue(any(l.startswith("ERR: 🔒") and "não vou usar a nuvem" in l for l in jarvis.ui.logs),
                        jarvis.ui.logs)
        voz.assert_called_once()

    def _nomes(self, jarvis):
        ferramentas, _ = jarvis._ferramentas_da_reserva()
        return {f["function"]["name"] for f in ferramentas}

    def test_modo_privado_so_oferece_ferramentas_sem_ia_na_nuvem(self):
        import main

        jarvis = self._jarvis(CerebroGemma(cliente=ClienteOllamaFalso()))
        jarvis._reserva_ferramentas = None
        with patch.dict(os.environ, {"JARVIS_CEREBRO": "gemma"}):
            nomes = self._nomes(jarvis)
        proibidas = set(main.FERRAMENTAS_NUVEM_IA) | {"save_memory", "generate_video", "claude_task"}
        self.assertEqual(nomes & proibidas, set())
        self.assertTrue({"open_app", "reminder", "media_control", "saved_routines"} <= nomes, nomes)
        # fora do modo privado a reserva (Groq) continua com as de sempre
        jarvis._reserva_ferramentas = None
        with patch.dict(os.environ, {"JARVIS_CEREBRO": "gemini"}):
            self.assertTrue({"web_search", "save_memory", "generate_video"} <= self._nomes(jarvis))

    def _ferramenta(self, jarvis, nome, **args):
        resposta = asyncio.run(jarvis._execute_tool(NS(name=nome, args=args, id="1")))
        return resposta.response

    def test_modo_privado_recusa_no_codigo_o_que_vai_para_a_nuvem(self):
        import main

        jarvis = self._jarvis(CerebroGemma(cliente=ClienteOllamaFalso()))
        nuvem = AssertionError("não pode mandar para a IA na nuvem no modo privado")
        with patch.dict(os.environ, {"JARVIS_CEREBRO": "gemma"}), \
                patch("main.web_search_action", side_effect=nuvem), \
                patch("core.hermes_ponte.perguntar", side_effect=nuvem), \
                patch("core.modelos.gerar_imagem", side_effect=nuvem), \
                patch("main.youtube_video", side_effect=nuvem):
            for nome, args in (("web_search", {"query": "cliente Fulano CNPJ 123"}),
                               ("hermes_agent", {"request": "resumo do cliente Fulano"}),
                               ("generate_image", {"prompt": "x"}),
                               ("youtube_video", {"action": "summarize"}),
                               ("school_tasks", {"refresh": True}),
                               ("generate_video", {"description": "cliente Fulano", "confirm": True})):
                self.assertEqual(self._ferramenta(jarvis, nome, **args)["result"], main.AVISO_MODO_PRIVADO, nome)
        self.assertTrue(any("🔒 web_search" in l for l in jarvis.ui.logs))

    def test_modo_privado_nao_grava_memoria(self):
        jarvis = self._jarvis(CerebroGemma(cliente=ClienteOllamaFalso()))
        with patch.dict(os.environ, {"JARVIS_CEREBRO": "gemma"}), patch("main.update_memory") as gravar:
            resposta = self._ferramenta(jarvis, "save_memory", category="relationships",
                                        key="cliente_joao", value="deve 200 mil")
        gravar.assert_not_called()
        self.assertTrue(resposta["silent"])
        with patch.dict(os.environ, {"JARVIS_CEREBRO": "gemini"}), patch("main.update_memory") as gravar:
            self._ferramenta(jarvis, "save_memory", category="notes", key="k", value="v")
        gravar.assert_called_once()

    def test_sem_ouvido_avisa_uma_vez_e_nao_manda_a_voz_para_fora(self):
        cerebro = CerebroGemma(cliente=ClienteOllamaFalso())
        jarvis = self._jarvis(cerebro)
        jarvis._modo_reserva = True
        jarvis._is_speaking = False
        jarvis._responder_pela_reserva = lambda texto: self.fail("não ouviu nada para responder")
        with patch("core.reserva_groq.capturar_falas", lambda **k: iter([b"\x00\x10" * 1600] * 3)), \
                patch.dict(os.environ, {"GROQ_API_KEY": "gsk_falsa"}), \
                patch.dict(sys.modules, {"faster_whisper": None}):
            jarvis._escutar_reserva()
        avisos = [l for l in jarvis.ui.logs if "não consigo ouvir" in l]
        self.assertEqual(len(avisos), 1, jarvis.ui.logs)
        self.assertEqual(jarvis.falado, [cerebro_gemma.AVISO_SEM_WHISPER])


class ModoPrivadoPorVozTests(unittest.TestCase):
    def _jarvis(self, cerebro_nome="gemini", com_ponte=True):
        import main

        class UI:
            remota = True

            def __init__(s):
                s.logs, s.trocas, s.muted = [], [], False

            def write_log(s, t):
                s.logs.append(t)

            def set_muted_threadsafe(s, valor):
                s.muted = valor

        ui = UI()
        if com_ponte:
            ui.trocar_cerebro = ui.trocas.append
        jarvis = object.__new__(main.JarvisLive)
        jarvis.ui = ui
        jarvis._cerebro_nome = cerebro_nome
        jarvis.avisos = []
        jarvis._falar_aviso = jarvis.avisos.append
        return jarvis

    def _esperar_troca(self):
        for t in threading.enumerate():
            if t.name == "TrocarCerebro":
                t.join(5)

    def test_modo_privado_troca_para_o_gemma(self):
        jarvis = self._jarvis()
        with patch("core.cerebro_gemma.modelo_instalado", return_value=True), \
                patch("core.cerebro_gemma.whisper_instalado", return_value=True):
            self.assertTrue(jarvis._pedido_de_cerebro("Jarvis, modo privado"))
            self._esperar_troca()
        self.assertEqual(jarvis.ui.trocas, ["gemma"])

    def test_sem_whisper_local_nao_liga_o_modo_privado(self):
        jarvis = self._jarvis()
        with patch("core.cerebro_gemma.modelo_instalado", return_value=True), \
                patch("core.cerebro_gemma.whisper_instalado", return_value=False):
            jarvis._pedido_de_cerebro("modo privado")
            self._esperar_troca()
        self.assertEqual(jarvis.ui.trocas, [])
        self.assertIn("transcrição local", jarvis.avisos[0])
        self.assertFalse(jarvis._trocando_cerebro)

    def test_durante_a_troca_nada_vai_para_a_nuvem(self):
        import numpy as np
        from core.palavra_ativacao import PortaoDeVoz

        liberar, checando = threading.Event(), threading.Event()

        def modelo_instalado_lento():
            checando.set()
            liberar.wait(5)
            return False  # o Ollama não subiu: não troca

        jarvis = self._jarvis()
        jarvis._shutdown_requested = threading.Event()
        jarvis._speaking_lock, jarvis._is_speaking = threading.Lock(), False
        jarvis._portao = PortaoDeVoz(None, ativo=False)
        microfone = {}

        class Microfone:
            def __init__(s, callback=None, **k):
                microfone["callback"] = callback

            def __enter__(s):
                return s

            def __exit__(s, *a):
                return False

        fala = np.zeros((160, 1), dtype=np.int16)

        async def cenario():
            jarvis.out_queue = asyncio.Queue()
            tarefa = asyncio.ensure_future(jarvis._listen_audio())
            await asyncio.sleep(0.2)
            with patch("core.cerebro_gemma.modelo_instalado", modelo_instalado_lento), \
                    patch("core.cerebro_gemma.whisper_instalado", return_value=True):
                self.assertTrue(jarvis._pedido_de_cerebro("Jarvis, modo privado"))
                await asyncio.to_thread(checando.wait, 5)
                self.assertTrue(jarvis._trocando_cerebro)
                microfone["callback"](fala, 160, None, None)
                await asyncio.sleep(0.1)
                self.assertTrue(jarvis.out_queue.empty())  # o microfone não foi para o Gemini
                self.assertFalse(await jarvis.send_audio_chunk(b"\x00\x01"))
                liberar.set()
                await asyncio.to_thread(self._esperar_troca)
            self.assertFalse(jarvis._trocando_cerebro)  # não trocou: libera de novo
            microfone["callback"](fala, 160, None, None)
            await asyncio.sleep(0.1)
            self.assertFalse(jarvis.out_queue.empty())
            jarvis._shutdown_requested.set()
            await asyncio.wait_for(tarefa, 2)

        with patch("main.sd.InputStream", Microfone):
            asyncio.run(cenario())
        self.assertEqual(jarvis.ui.trocas, [])
        self.assertTrue(any("Preparando o modo privado" in l for l in jarvis.ui.logs))

    def test_frase_negada_nao_sai_do_modo_privado(self):
        jarvis = self._jarvis("gemma")
        for fala in ("Jarvis, não quero sair do modo privado", "não é pra sair do modo privado",
                     "nada de modo normal agora", "ele quer sair do modo privado"):
            self.assertFalse(jarvis._pedido_de_cerebro(fala), fala)
        self._esperar_troca()
        self.assertEqual(jarvis.ui.trocas, [])

    def test_um_programa_so_avisa_em_voz_e_desliga_o_microfone(self):
        jarvis = self._jarvis(com_ponte=False)
        with patch.dict(os.environ, {"JARVIS_UM_PROCESSO": ""}):
            jarvis._pedido_de_cerebro("Jarvis, modo privado")
            self._esperar_troca()
        self.assertIn("NÃO foi ligado", jarvis.avisos[0])
        self.assertTrue(jarvis.ui.muted)
        self.assertFalse(jarvis._trocando_cerebro)
        self.assertTrue(any("NÃO ligado" in l for l in jarvis.ui.logs))
        self.assertFalse(any("JARVIS_UM_PROCESSO" in l for l in jarvis.ui.logs))

    def test_sem_gemma_instalado_avisa_e_nao_troca(self):
        jarvis = self._jarvis()
        with patch("core.cerebro_gemma.modelo_instalado", return_value=False):
            jarvis._pedido_de_cerebro("modo privado")
            self._esperar_troca()
        self.assertEqual(jarvis.ui.trocas, [])
        self.assertIn("Instalar Gemma 4", jarvis.avisos[0])

    def test_ja_no_modo_pedido(self):
        jarvis = self._jarvis("gemma")
        jarvis._pedido_de_cerebro("modo privado")
        self._esperar_troca()
        self.assertEqual(jarvis.ui.trocas, [])
        self.assertIn("Já estou no modo privado", jarvis.avisos[0])

    def test_modo_normal_volta_ao_gemini(self):
        jarvis = self._jarvis("gemma")
        jarvis._pedido_de_cerebro("sair do modo privado")
        self._esperar_troca()
        self.assertEqual(jarvis.ui.trocas, ["gemini"])

    def test_conversa_comum_nao_troca(self):
        jarvis = self._jarvis()
        self.assertFalse(jarvis._pedido_de_cerebro("me fala sobre o modo privado do navegador que eu li ontem"))


class PedidoDePrivacidadeTests(unittest.TestCase):
    def test_negacao_nunca_troca(self):
        for fala in ("Jarvis, não quero sair do modo privado", "não é pra sair do modo privado",
                     "nada de modo normal agora", "não volte ao modo normal", "Jarvis, não quero modo normal",
                     "eu não quero modo normal", "não pode sair do modo privado", "nunca sair do modo privado"):
            self.assertIsNone(cerebro_gemma.pedido_de_privacidade(fala), fala)

    def test_volta_para_a_nuvem_so_com_o_pedido_sozinho(self):
        for fala in ("Jarvis, modo normal", "modo normal.", "sair do modo privado", "Jarvis, sair do modo privado.",
                     "Jarvis, volta pro modo normal, por favor", "ok Jarvis, modo público"):
            self.assertEqual(cerebro_gemma.pedido_de_privacidade(fala), "gemini", fala)
        for fala in ("ele quer sair do modo privado", "o cliente usa o modo normal"):
            self.assertIsNone(cerebro_gemma.pedido_de_privacidade(fala), fala)

    def test_entrar_no_modo_privado_continua_facil(self):
        for fala in ("Jarvis, modo privado", "modo privado", "Jarvis, modo sigiloso agora",
                     "modo privado sem demora"):
            self.assertEqual(cerebro_gemma.pedido_de_privacidade(fala), "gemma", fala)


class InstaladorGemmaTests(unittest.TestCase):
    def test_so_liga_o_gemma_com_o_whisper_local_pronto(self):
        texto = (Path(__file__).resolve().parents[1] / "gemma" / "instalar_gemma.ps1").read_text(encoding="ascii")
        senao = texto.index("} else {", texto.index("if ($whisperOk) {"))
        ligar = texto.index('Definir-Env "JARVIS_CEREBRO" "gemma"')
        self.assertIn("exit 0", texto[senao:ligar])  # sem Whisper, sai antes de ligar o modo privado
        self.assertNotIn("Groq", texto[senao:ligar])


class TelaSemChaveNoModoGemmaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PyQt6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def test_abre_sem_pedir_a_chave_do_gemini(self):
        import ui
        from PyQt6.QtCore import QCoreApplication

        with patch.dict(os.environ, {"JARVIS_CEREBRO": "gemma", "GEMINI_API_KEY": ""}):
            win = ui.MainWindow("face.png")
            try:
                for _ in range(5):
                    QCoreApplication.processEvents()
                self.assertTrue(win._ready)
                self.assertIsNone(win._overlay)
                self.assertNotEqual(os.environ.get("JARVIS_SEM_GEMINI"), "1")
            finally:
                win.close()
                win.deleteLater()


if __name__ == "__main__":
    unittest.main()
