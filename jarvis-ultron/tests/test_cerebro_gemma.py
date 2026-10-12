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
