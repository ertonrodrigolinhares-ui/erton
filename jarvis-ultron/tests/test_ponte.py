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

    def test_botao_do_ultron_antes_do_cerebro_ficar_pronto_nao_se_perde(self):
        feitos = []
        self.ui.iniciar()
        self._proxima()
        self.lado_tela.send(("rodar_ultron", "pc_protection", {}))
        aviso = self._proxima()  # a tela fica sabendo que vai rodar quando o cérebro abrir
        self.assertEqual(aviso[:2], ("chamar", "write_log"))
        self.assertIn("pc_protection", aviso[2][0])
        self.assertEqual(feitos, [])
        self.ui.ligar_jarvis(NS(_modo_reserva=False, session=None, _reserva=None,
                                rodar_automacao_ultron=lambda n, a: feitos.append((n, a))))
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
        with patch("cerebro.pontes.carregar_automacoes", return_value=carga), \
                patch("core.automacoes.sincronizar_habilidades", return_value=NS(habilidades=[], erros=[])):
            jarvis._preparar_automacoes()
        self.assertEqual(rodados, ["lembretes"])

    def test_jarvis_na_tela_manda_botao_pela_ponte(self):
        enviados = []
        jarvis = JarvisNaTela(ui=None, ponte=NS(entregar=enviados.append))
        jarvis.rodar_automacao_ultron("wifi_watch", {"action": "both"})
        self.assertEqual(enviados, [("rodar_ultron", "wifi_watch", {"action": "both"})])
        jarvis.atualizar({"modo_reserva": False, "conectado": True, "cerebro": "gemma"})
        self.assertIsNotNone(jarvis.session)
        from importlib import util
        spec = util.spec_from_file_location("ps", RAIZ / "automacoes" / "painel_stark.py")
        mod = util.module_from_spec(spec); spec.loader.exec_module(mod)
        self.assertEqual(mod.texto_voz(jarvis), ("Cérebro: Gemma 4 (no PC)", True))
        jarvis.parado = True  # a tela desistiu de religar o cérebro: nada de verde
        self.assertEqual(mod.texto_voz(jarvis), ("Cérebro parado — feche e abra o Jarvis", False))
        jarvis.atualizar({"modo_reserva": False, "conectado": True, "cerebro": "gemini"})
        self.assertEqual(mod.texto_voz(jarvis), ("Voz: Gemini ao vivo", True))


class RodarCerebroTests(unittest.TestCase):
    def test_voz_trocada_enquanto_o_cerebro_abria_chega_ao_cerebro(self):
        import main

        lado_cerebro, lado_tela = Pipe()
        ui = UIRemota(lado_cerebro)
        ui._pronto.set()
        # o usuário trocou a voz e o TTS na tela antes de o cérebro ficar pronto
        ui._tratar(("chamada", "on_voice_change", ("Kore",)))
        ui._tratar(("chamada", "on_tts_provider_change", ("gemini", "", "Puck")))
        vozes = []

        class JarvisFalso:
            def __init__(self, tela, voz):
                self.ui, self.session, self._loop, self._modo_reserva, self._reserva = tela, None, None, False, None

            def update_voice(self, voz):
                vozes.append(voz)

            def request_shutdown(self):
                pass

            async def run(self):
                pass

        sem = ("ELEVENLABS_API_KEY",)
        try:
            with patch.object(main, "JarvisLive", JarvisFalso), \
                    patch.object(main, "_load_voice_name", return_value="Charon"), patch.dict(os.environ):
                for nome in sem:
                    os.environ.pop(nome, None)
                main.rodar_cerebro(ui)
            self.assertTrue(_esperar(lambda: sorted(vozes) == ["Kore", "Puck"]), vozes)
        finally:
            ui._fechada.set()
            lado_tela.close()


CEREBRO_FALSO = textwrap.dedent("""
    import os, sys, time
    from multiprocessing.connection import Client
    modo = sys.argv[1]
    if modo == "devagar":
        time.sleep(1.5)  # dá tempo de outro programa bater na porta antes do cérebro
    c = Client(("127.0.0.1", int(os.environ["JARVIS_PONTE_PORTA"])),
               authkey=bytes.fromhex(os.environ["JARVIS_PONTE_CHAVE"]))
    c.send(("ola", os.getpid()))
    c.send(("chamar", "write_log", ("SYS: cérebro falso no ar",), {}))
    c.send(("chamar", "write_log", ("SYS: nasci com cerebro=" + os.environ.get("JARVIS_CEREBRO", "?"),), {}))
    if modo == "troca" and os.environ.get("JARVIS_CEREBRO") != "gemma":
        c.send(("trocar_cerebro", "gemma"))
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
        self.logs, self.estados, self.volumes, self.comandos = [], [], [], []
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

    def handle_ui_command(self, acao):
        self.comandos.append(acao)


class PonteTelaSemCerebroTests(unittest.TestCase):
    """A ponte da tela enquanto o cérebro abre, religa ou desiste (sem programa de verdade)."""

    @classmethod
    def setUpClass(cls):
        from PyQt6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.tela = TelaFalsa()
        self.p = PonteTela(self.tela, comando=["nao-roda"], pasta=RAIZ)
        self.p._relogio.stop()  # aqui o teste faz o papel do relógio
        self.p.iniciar = lambda: None  # "religar" não abre programa nenhum
        self.p._processo = NS(poll=lambda: None, returncode=None, pid=1)  # cérebro abrindo
        self.canais = []

    def tearDown(self):
        self.p._processo = None
        self.p.encerrar()
        for canal in self.canais:
            canal.close()

    def _conectar(self):
        """O cérebro novo conecta: devolve o lado do cérebro do canal."""
        lado_cerebro, lado_tela = Pipe()
        self.canais += [lado_cerebro, lado_tela]
        ouvinte = NS(accept=lambda: lado_tela)
        self.p._ouvinte = ouvinte
        self.p._aceitar(ouvinte)
        return lado_cerebro

    def _recebidas(self, canal):
        recebidas = []
        while canal.poll(0.3):
            recebidas.append(canal.recv())
        return recebidas

    def test_pedidos_enquanto_o_cerebro_religa_sao_entregues_quando_ele_conecta(self):
        self.p._ja_conectou = True  # o cérebro já funcionou antes: é uma religada
        self.tela.on_text_command("que horas são?")
        self.p.jarvis.rodar_automacao_ultron("pc_protection", {})
        self.tela.on_quit_requested()  # fechar nunca fica guardado
        self.assertEqual(sum("religando" in l for l in self.tela.logs), 1)  # avisa uma vez, não some calado
        cerebro = self._conectar()
        self.assertEqual(self._recebidas(cerebro), [("chamada", "on_text_command", ("que horas são?",)),
                                                    ("rodar_ultron", "pc_protection", {})])
        self.tela.on_text_command("e agora?")  # conectado: vai direto
        self.assertEqual(self._recebidas(cerebro), [("chamada", "on_text_command", ("e agora?",))])

    def test_na_troca_de_cerebro_o_pedido_vai_para_o_novo(self):
        antigo = self._conectar()
        self.p._religando_desde = time.monotonic()  # pediu "modo privado": o antigo está saindo
        self.tela.on_text_command("pergunta depois do modo privado")
        self.assertEqual(self._recebidas(antigo), [])
        self.p._religando_desde = None
        self.p._fechar_conexao()
        novo = self._conectar()
        self.assertEqual(self._recebidas(novo),
                         [("chamada", "on_text_command", ("pergunta depois do modo privado",))])

    def test_cerebro_parado_avisa_em_vez_de_sumir_com_o_pedido(self):
        self.p._processo = None  # a tela desistiu de religar
        self.tela.on_text_command("oi")
        self.assertTrue(any(l.startswith("ERR:") and "Feche e abra" in l for l in self.tela.logs))
        self.assertEqual(list(self.p._pendentes), [])

    def _texto_voz(self):
        from importlib import util
        spec = util.spec_from_file_location("ps", RAIZ / "automacoes" / "painel_stark.py")
        mod = util.module_from_spec(spec); spec.loader.exec_module(mod)
        return mod.texto_voz(self.p.jarvis)

    def test_painel_nao_fica_verde_com_o_cerebro_caido(self):
        self.p.jarvis.atualizar({"modo_reserva": False, "conectado": True, "cerebro": "gemma"})
        self.p._cerebro_caiu(1)  # religando: "conectando...", não "Gemma 4" em verde
        self.assertEqual(self._texto_voz(), ("Voz: conectando...", False))
        for _ in range(ponte.MAX_RELIGADAS):
            self.p._cerebro_caiu(1)
        self.assertIsNone(self.p._processo)  # desistiu
        self.assertEqual(self._texto_voz(), ("Cérebro parado — feche e abra o Jarvis", False))

    def test_painel_mostra_parado_quando_a_religada_falha(self):
        self.p._ja_conectou = True
        self.p.jarvis.atualizar({"modo_reserva": False, "conectado": True, "cerebro": "gemini"})
        self.p._falhou("o cérebro não respondeu a tempo")
        self.assertEqual(self._texto_voz(), ("Cérebro parado — feche e abra o Jarvis", False))

    def test_na_primeira_abertura_sem_cerebro_o_pedido_vai_para_o_cerebro_local(self):
        self.p.ao_falhar = lambda: None  # (main.py abre o cérebro local num fio)
        self.tela.on_text_command("oi, Jarvis")
        self.tela.on_voice_change("Kore")
        self.p.jarvis.rodar_automacao_ultron("pc_protection", {})
        avisos = [l for l in self.tela.logs if "entrego" in l]
        self.assertEqual(len(avisos), 1)
        self.assertIn("abrindo", avisos[0])  # ainda não conectou nenhuma vez: não é "religando"
        self.p._falhou("o cérebro não respondeu a tempo")  # volta ao modo de um programa só
        self.assertFalse(any(l.startswith("ERR:") for l in self.tela.logs), self.tela.logs)
        # o cérebro local registra as funções dele e, no fim, rodar_cerebro chama ligar_jarvis
        recebidos = []
        self.tela.on_text_command = lambda t: recebidos.append(("texto", t))
        self.tela.on_voice_change = lambda v: recebidos.append(("voz", v))
        self.tela.ligar_jarvis(NS(rodar_automacao_ultron=lambda n, a: recebidos.append(("ultron", n))))
        self.assertTrue(_esperar(lambda: len(recebidos) == 3), recebidos)
        self.assertEqual(recebidos, [("texto", "oi, Jarvis"), ("voz", "Kore"), ("ultron", "pc_protection")])
        self.assertFalse(hasattr(self.tela, "ligar_jarvis"))  # uma vez só
        self.assertEqual(list(self.p._pendentes), [])

    def test_quando_a_tela_desiste_avisa_que_o_guardado_nao_foi_entregue(self):
        self.p._ja_conectou = True
        self.tela.on_text_command("oi")
        self.p._falhou("o cérebro não respondeu a tempo")
        erros = [l for l in self.tela.logs if l.startswith("ERR:")]
        self.assertEqual(len(erros), 1)
        self.assertIn("não foi entregue", erros[0])
        self.assertEqual(list(self.p._pendentes), [])

    def test_quando_o_cerebro_cai_varias_vezes_avisa_que_o_guardado_nao_foi_entregue(self):
        self.p._ja_conectou = True
        self.p._cerebro_caiu(1)
        self.tela.on_text_command("oi")  # religando: fica guardado
        for _ in range(ponte.MAX_RELIGADAS):
            self.p._cerebro_caiu(1)
        self.assertIsNone(self.p._processo)
        self.assertIn("não foi entregue", self.tela.logs[-1])
        self.assertEqual(list(self.p._pendentes), [])


class TextoAntesDoGeminiConectarTests(unittest.TestCase):
    """O cérebro acabou de abrir (ou a tela entregou o que guardou) e o Gemini ainda não conectou."""

    def _jarvis(self):
        import main

        jarvis = object.__new__(main.JarvisLive)
        logs = []
        jarvis.ui = NS(logs=logs, write_log=logs.append, set_state=lambda estado: None)
        jarvis.session, jarvis._loop, jarvis._reserva, jarvis._modo_reserva = None, None, None, False
        jarvis._api_key = "chave-de-teste"
        jarvis._falhas_seguidas = 0
        jarvis._shutdown_requested = threading.Event()
        return jarvis

    def _rodar_ate_mandar(self, jarvis, quantos):
        """Roda o run() com um Gemini falso; devolve os textos que chegaram à sessão."""
        import contextlib
        import asyncio
        import main

        enviados, conexoes = [], []

        class Sessao:
            async def send_client_content(self, turns, turn_complete):
                enviados.append(turns["parts"][0]["text"])
                if len(enviados) >= quantos:
                    jarvis._shutdown_requested.set()

        @contextlib.asynccontextmanager
        async def conectar(model, config):
            conexoes.append(model)
            if len(conexoes) > 1:  # não mandou o que devia: encerra em vez de travar o teste
                jarvis._shutdown_requested.set()
                raise RuntimeError("segunda conexão")
            yield Sessao()

        async def nada():
            return None

        jarvis._build_config = lambda modelo: None
        jarvis._send_realtime = jarvis._receive_audio = jarvis._play_audio = jarvis._listen_audio = nada
        cliente = NS(aio=NS(live=NS(connect=conectar)))
        with patch.object(main.genai, "Client", return_value=cliente), \
                patch.object(main, "pick_live_model", return_value="models/voz-teste"), \
                patch("core.modelos.resolver", side_effect=lambda pedido: pedido):
            asyncio.run(jarvis.run())
        return enviados

    def test_texto_antes_de_conectar_fica_guardado_e_vai_quando_conecta(self):
        jarvis = self._jarvis()
        with patch.dict(os.environ):
            for nome in ("JARVIS_CEREBRO", "JARVIS_SEM_GEMINI"):
                os.environ.pop(nome, None)
            jarvis._on_text_command("que horas são?")  # antes: sumia calado (sem log, sem nada)
            jarvis._on_text_command("e o tempo amanhã?")
            self.assertEqual(sum("conectando ao Gemini" in l for l in jarvis.ui.logs), 1, jarvis.ui.logs)
            enviados = self._rodar_ate_mandar(jarvis, 2)
        # na ordem, e sem a saudação na frente (o Erton já pediu algo)
        self.assertEqual(enviados, ["que horas são?", "e o tempo amanhã?"])
        self.assertEqual(jarvis._textos_esperando, [])

    def test_no_modo_privado_sem_gemma_o_texto_nao_fica_guardado_para_a_nuvem(self):
        jarvis = self._jarvis()
        with patch.dict(os.environ, {"JARVIS_CEREBRO": "gemma"}):
            jarvis._on_text_command("dados do cliente")
        self.assertEqual(getattr(jarvis, "_textos_esperando", []), [])
        self.assertTrue(any("não vai para a nuvem" in l for l in jarvis.ui.logs), jarvis.ui.logs)


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

    def test_conexao_estranha_na_porta_nao_trava_o_cerebro(self):
        import socket
        from multiprocessing import AuthenticationError
        from multiprocessing.connection import Client

        tela, p = self._ponte("devagar")
        p.iniciar()
        endereco = ("127.0.0.1", p._ouvinte.address[1])
        with self.assertRaises(AuthenticationError):
            Client(endereco, authkey=b"senha-errada")  # outro programa, sem a senha
        socket.create_connection(endereco, timeout=2).close()  # abre e fecha
        self.assertTrue(_esperar(lambda: "SYS: cérebro falso no ar" in tela.logs, 20, self.app), tela.logs)
        p.encerrar()

    def test_sem_cerebro_volta_ao_modo_de_um_programa(self):
        falhou = []
        tela = TelaFalsa()
        p = PonteTela(tela, ao_falhar=lambda: falhou.append(1), comando=["/caminho/que/nao/existe"], pasta=RAIZ)
        p.iniciar()
        self.assertEqual(falhou, [1])
        self.assertIsNone(tela.on_text_command)  # o cérebro local registra as dele
        p.encerrar()

    def test_modo_privado_religa_o_cerebro_no_gemma(self):
        import tempfile
        pasta = Path(tempfile.mkdtemp())
        (pasta / ".env").write_text('GEMINI_API_KEY="x"\nJARVIS_CEREBRO="gemini"\n')
        tela = TelaFalsa()
        p = PonteTela(tela, comando=[sys.executable, str(self.script), "troca"], pasta=pasta)
        with patch.dict(os.environ, {"JARVIS_CEREBRO": "gemini"}):
            p.iniciar()
            primeiro = p._processo.pid
            self.assertTrue(_esperar(lambda: "SYS: nasci com cerebro=gemma" in tela.logs, 30, self.app), tela.logs)
            self.assertEqual(os.environ["JARVIS_CEREBRO"], "gemma")
        self.assertNotEqual(p._processo.pid, primeiro)  # é outro programa do cérebro
        self.assertIn('JARVIS_CEREBRO="gemma"', (pasta / ".env").read_text())
        self.assertIn('GEMINI_API_KEY="x"', (pasta / ".env").read_text())
        self.assertFalse(any("parou" in l for l in tela.logs))  # troca não é contada como queda
        self.assertTrue(any("Modo privado ligado" in l for l in tela.logs))
        p.encerrar()

    def test_modo_privado_avisa_na_tela_quando_nao_grava_no_env(self):
        import tempfile
        pasta = Path(tempfile.mkdtemp())
        (pasta / ".env").mkdir()  # .env que não dá para ler nem gravar
        tela = TelaFalsa()
        p = PonteTela(tela, comando=["/caminho/que/nao/existe"], pasta=pasta)
        try:
            with patch.dict(os.environ, {"JARVIS_CEREBRO": "gemini"}):
                p.trocar_cerebro("gemma")
                self.assertEqual(os.environ["JARVIS_CEREBRO"], "gemma")  # vale para agora
        finally:
            p.encerrar()
        self.assertTrue(any(l.startswith("ERR:") and ".env" in l for l in tela.logs), tela.logs)

    def test_modo_separado_e_o_padrao(self):
        with patch.dict(os.environ, {"JARVIS_UM_PROCESSO": ""}):
            self.assertTrue(ponte.modo_separado())
        with patch.dict(os.environ, {"JARVIS_UM_PROCESSO": "1"}):
            self.assertFalse(ponte.modo_separado())


if __name__ == "__main__":
    unittest.main()
