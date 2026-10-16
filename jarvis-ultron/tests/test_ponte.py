import os
import sys
import textwrap
import threading
import time
import unittest
from multiprocessing import Pipe
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from core import ponte
from core.ponte import JarvisNaTela, PonteTela, UIRemota


def _esperar(condicao, segundos=10.0, app=None):
    limite = time.monotonic() + segundos
    while time.monotonic() < limite:
        if app is not None:
            app.processEvents()
        if condicao():
            return True
        time.sleep(0.02)
    return False


class UIRemotaTests(unittest.TestCase):
    def setUp(self):
        self.lado_cerebro, self.lado_tela = Pipe()
        self.ui = UIRemota(self.lado_cerebro)

    def tearDown(self):
        # fim do teste: o canal falso some; não deixar o "cérebro" encerrar o programa do teste
        self.ui._fechada.set()

    def _proxima(self, segundos=2.0):
        self.assertTrue(self.lado_tela.poll(segundos), "nenhuma mensagem chegou")
        return self.lado_tela.recv()

    def test_metodos_da_tela_viram_mensagens(self):
        self.ui.write_log("SYS: oi")
        self.ui.set_state("THINKING")
        self.ui.update_research_progress("pergunta", 40, "Lendo", artifacts=["a.md"])
        self.assertEqual(self._proxima(), ("chamar", "write_log", ("SYS: oi",), {}))
        self.assertEqual(self._proxima(), ("chamar", "set_state", ("THINKING",), {}))
        self.assertEqual(self._proxima(),
                         ("chamar", "update_research_progress", ("pergunta", 40, "Lendo"), {"artifacts": ["a.md"]}))

    def test_atributo_desconhecido_continua_desconhecido(self):
        self.assertIsNone(getattr(self.ui, "_win", None))
        self.assertTrue(getattr(self.ui, "operational_ready", True))
        with self.assertRaises(AttributeError):
            self.ui.apagar_tudo()

    def test_volume_da_voz_e_limitado(self):
        for _ in range(50):
            self.ui.set_voice_level(0.5)
        self.ui.set_voice_level(0.0)  # o zero final sempre passa (a esfera volta a descansar)
        recebidas = []
        while self.lado_tela.poll(0.2):
            recebidas.append(self.lado_tela.recv())
        self.assertLess(len(recebidas), 10)
        self.assertEqual(recebidas[-1], ("chamar", "set_voice_level", (0.0,), {}))

    def test_mudo_vale_na_hora_no_cerebro(self):
        self.ui.set_muted_threadsafe(True)
        self.assertTrue(self.ui.muted)
        self.assertEqual(self._proxima(), ("chamar", "set_muted_threadsafe", (True,), {}))
        self.ui.stop_speaking()  # mudo: não volta para "ouvindo"
        self.assertFalse(self.lado_tela.poll(0.2))

    def test_pronto_traz_a_chave_e_libera_o_cerebro(self):
        self.ui.iniciar()
        self.assertEqual(self._proxima()[0], "ola")
        with patch.dict(os.environ, {}, clear=False):
            liberado = threading.Event()
            threading.Thread(target=lambda: (self.ui.wait_for_api_key(), liberado.set()), daemon=True).start()
            self.assertFalse(liberado.wait(0.3))
            self.lado_tela.send(("pronto", {"GEMINI_API_KEY": "chave-da-tela"}))
            self.assertTrue(liberado.wait(3))
            self.assertEqual(os.environ["GEMINI_API_KEY"], "chave-da-tela")

    def test_estado_da_tela_espelhado(self):
        self.ui.iniciar()
        self._proxima()
        self.lado_tela.send(("estado_tela", {"muted": True, "current_file": "C:/nota.pdf"}))
        self.assertTrue(_esperar(lambda: self.ui.muted and self.ui.current_file == "C:/nota.pdf"))

    def test_texto_digitado_antes_do_cerebro_ficar_pronto_nao_se_perde(self):
        recebido = []
        self.ui.iniciar()
        self._proxima()
        self.lado_tela.send(("chamada", "on_text_command", ("cedo demais",)))
        time.sleep(0.3)
        self.assertEqual(recebido, [])
        self.ui.on_text_command = recebido.append  # o cérebro ficou pronto
        self.ui.ligar_jarvis(NS(_modo_reserva=False, session=None, _reserva=None))
        self.assertTrue(_esperar(lambda: recebido == ["cedo demais"]))

    def test_chamadas_da_tela_chegam_ao_cerebro(self):
        recebido = []
        self.ui.on_text_command = recebido.append
        self.ui.iniciar()
        self._proxima()
        self.ui.ligar_jarvis(NS(_modo_reserva=False, session=None, _reserva=None))
        self.lado_tela.send(("chamada", "on_text_command", ("que horas são?",)))
        self.lado_tela.send(("chamada", "apagar_tudo", ()))  # fora da lista: ignorada
        self.assertTrue(_esperar(lambda: recebido == ["que horas são?"]))

    def test_botao_do_ultron_roda_no_cerebro(self):
        feitos = []
        self.ui.ligar_jarvis(NS(_modo_reserva=False, session=None, _reserva=None,
                                rodar_automacao_ultron=lambda n, a: feitos.append((n, a))))
        self.ui.iniciar()
        self.lado_tela.send(("rodar_ultron", "pc_protection", {}))
        self.assertTrue(_esperar(lambda: feitos == [("pc_protection", {})]))

    def test_estado_do_cerebro_vai_para_a_tela(self):
        self.ui.ligar_jarvis(NS(_modo_reserva=True, session=None, _reserva=None))
        mensagens = []
        self.assertTrue(_esperar(lambda: self.lado_tela.poll(0) and mensagens.append(self.lado_tela.recv())
                                 or any(m[0] == "estado" for m in mensagens)))
        estado = next(m[1] for m in mensagens if m[0] == "estado")
        self.assertEqual(estado, {"modo_reserva": True, "conectado": False, "cerebro": "groq"})

    def test_tela_fechada_desliga_o_cerebro(self):
        saiu = []
        self.ui.on_quit_requested = lambda: saiu.append(1)
        with patch.object(ponte.os, "_exit") as sair:
            self.ui.iniciar()
            self.lado_tela.close()
            self.assertTrue(_esperar(lambda: saiu == [1]))
            self.assertTrue(_esperar(lambda: sair.called, 6))
        self.assertFalse(self.ui._enviar(("chamar", "write_log", ("x",), {})))


class AutomacoesDeTelaTests(unittest.TestCase):
    def test_paineis_rodam_no_programa_da_tela(self):
        from core.automacoes import carregar_ferramentas

        carga = carregar_ferramentas(RAIZ / "automacoes")
        self.assertIn("painel_stark.py", carga.na_tela)
        self.assertIn("painel_ultron.py", carga.na_tela)
        self.assertNotIn("lembretes.py", carga.na_tela)
        self.assertNotIn("vigia_wifi.py", carga.na_tela)

    def test_cerebro_remoto_nao_monta_paineis(self):
        import main

        rodados = []
        carga = NS(ferramentas={}, erros=[], inicios=[("painel_ultron.py", lambda j: rodados.append("painel")),
                                                       ("lembretes.py", lambda j: rodados.append("lembretes"))],
                   na_tela={"painel_ultron.py"})
        jarvis = object.__new__(main.JarvisLive)
        jarvis.ui = NS(remota=True, write_log=lambda t: None)
        with patch.object(main, "carregar_automacoes", return_value=carga), \
                patch("core.automacoes.sincronizar_habilidades", return_value=NS(habilidades=[], erros=[])):
            jarvis._preparar_automacoes()
        self.assertEqual(rodados, ["lembretes"])

    def test_jarvis_na_tela_manda_botao_pela_ponte(self):
        enviados = []
        jarvis = JarvisNaTela(ui=None, ponte=NS(enviar=enviados.append))
        jarvis.rodar_automacao_ultron("wifi_watch", {"action": "both"})
        self.assertEqual(enviados, [("rodar_ultron", "wifi_watch", {"action": "both"})])
        jarvis.atualizar({"modo_reserva": False, "conectado": True, "cerebro": "gemma"})
        self.assertIsNotNone(jarvis.session)
        from importlib import util
        spec = util.spec_from_file_location("ps", RAIZ / "automacoes" / "painel_stark.py")
        mod = util.module_from_spec(spec); spec.loader.exec_module(mod)
        self.assertEqual(mod.texto_voz(jarvis), ("Cérebro: Gemma 4 (no PC)", True))


CEREBRO_FALSO = textwrap.dedent("""
    import os, sys, time
    from multiprocessing.connection import Client
    c = Client(("127.0.0.1", int(os.environ["JARVIS_PONTE_PORTA"])),
               authkey=bytes.fromhex(os.environ["JARVIS_PONTE_CHAVE"]))
    c.send(("ola", os.getpid()))
    c.send(("chamar", "write_log", ("SYS: cérebro falso no ar",), {}))
    modo = sys.argv[1]
    if modo == "cai":
        time.sleep(0.3)
        sys.exit(7)
    while True:
        try:
            m = c.recv()
        except EOFError:
            break
        if m[0] == "pronto":
            c.send(("chamar", "write_log", ("SYS: chave " + m[1].get("GEMINI_API_KEY", "?"),), {}))
        elif m[0] == "estado_tela":
            c.send(("chamar", "write_log", ("SYS: mudo " + str(m[1]["muted"]),), {}))
        elif m[0] == "chamada" and m[1] == "on_text_command":
            c.send(("chamar", "write_log", ("Jarvis: ouvi " + m[2][0],), {}))
            c.send(("chamar", "set_voice_level", (0.7,), {}))
        elif m[0] == "chamada" and m[1] == "on_quit_requested":
            break
""")


class TelaFalsa:
    def __init__(self):
        self.logs, self.estados, self.volumes = [], [], []
        self.muted = False
        self.current_file = None
        self._win = NS(_ready=True)
        self.on_text_command = self.on_voice_change = self.on_name_change = None
        self.on_tts_provider_change = self.on_quit_requested = None

    def write_log(self, texto):
        self.logs.append(texto)

    def set_state(self, estado):
        self.estados.append(estado)

    def set_voice_level(self, nivel):
        self.volumes.append(nivel)


class PonteDeVerdadeTests(unittest.TestCase):
    """Dois programas de verdade: a ponte da tela e um cérebro falso num processo separado."""

    @classmethod
    def setUpClass(cls):
        from PyQt6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.pasta = Path(self.id().replace(".", "_"))
        self.script = Path(os.environ.get("TMPDIR", "/tmp")) / f"cerebro_falso_{os.getpid()}.py"
        self.script.write_text(CEREBRO_FALSO, encoding="utf-8")

    def tearDown(self):
        self.script.unlink(missing_ok=True)

    def _ponte(self, modo="normal", **kw):
        tela = TelaFalsa()
        p = PonteTela(tela, comando=[sys.executable, str(self.script), modo], pasta=RAIZ, **kw)
        return tela, p

    def test_conversa_completa_entre_os_dois_programas(self):
        conectou = []
        tela, p = self._ponte(ao_conectar=lambda: conectou.append(1))
        with patch.dict(os.environ, {"GEMINI_API_KEY": "minha-chave"}):
            p.iniciar()
            self.assertTrue(_esperar(lambda: "SYS: chave minha-chave" in tela.logs, 20, self.app), tela.logs)
        self.assertEqual(conectou, [1])
        self.assertIn("SYS: cérebro falso no ar", tela.logs)
        self.assertNotEqual(p._processo.pid, os.getpid())  # o cérebro é outro programa
        tela.on_text_command("bom dia")  # o usuário digitou na janela
        self.assertTrue(_esperar(lambda: "Jarvis: ouvi bom dia" in tela.logs, 10, self.app), tela.logs)
        self.assertTrue(_esperar(lambda: tela.volumes == [0.7], 5, self.app))
        tela.muted = True  # apertou o mudo
        self.assertTrue(_esperar(lambda: "SYS: mudo True" in tela.logs, 5, self.app), tela.logs)
        p.encerrar()
        self.assertIsNotNone(p._processo.poll())  # fechou junto com a janela

    def test_cerebro_que_cai_e_religado(self):
        tela, p = self._ponte("cai")
        p.iniciar()
        self.assertTrue(_esperar(lambda: any("Religando" in l for l in tela.logs), 20, self.app), tela.logs)
        self.assertTrue(_esperar(lambda: any("parou várias vezes" in l for l in tela.logs), 40, self.app),
                        tela.logs)
        self.assertEqual(sum("Religando" in l for l in tela.logs), ponte.MAX_RELIGADAS)
        p.encerrar()

    def test_sem_cerebro_volta_ao_modo_de_um_programa(self):
        falhou = []
        tela = TelaFalsa()
        p = PonteTela(tela, ao_falhar=lambda: falhou.append(1), comando=["/caminho/que/nao/existe"], pasta=RAIZ)
        p.iniciar()
        self.assertEqual(falhou, [1])
        self.assertIsNone(tela.on_text_command)  # o cérebro local registra as dele
        p.encerrar()

    def test_modo_separado_e_o_padrao(self):
        with patch.dict(os.environ, {"JARVIS_UM_PROCESSO": ""}):
            self.assertTrue(ponte.modo_separado())
        with patch.dict(os.environ, {"JARVIS_UM_PROCESSO": "1"}):
            self.assertFalse(ponte.modo_separado())


if __name__ == "__main__":
    unittest.main()
