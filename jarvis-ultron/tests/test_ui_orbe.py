import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import ANY, Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PyQt6.QtCore import QRect, Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QApplication, QLabel, QWidget

import ui
import ui_orbe


class _CofreVazio:
    def get(self, _chave):
        return None


_TROCAS = []
_GUARDADO = {}


def setUpModule():
    # As janelas destes testes nunca usam a chave de verdade. No PC do Erton, o main.py (importado por
    # outros testes) já pôs no ambiente a chave do .env, e o cofre pode ter outra: com elas, cada janela
    # mandaria a chave ao Google, gravaria o config/api_keys.json e regravaria o .env de verdade.
    pasta = tempfile.TemporaryDirectory()
    _TROCAS[:] = [
        patch.object(ui, "API_FILE", Path(pasta.name) / "api_keys.json"),
        patch.object(ui, "BASE_DIR", Path(pasta.name)),
        patch.object(ui, "get_secret_store", return_value=_CofreVazio()),
    ]
    for troca in _TROCAS:
        troca.start()
    _GUARDADO.update(pasta=pasta, chave=os.environ.pop("GEMINI_API_KEY", None))


def tearDownModule():
    for troca in reversed(_TROCAS):
        troca.stop()
    if _GUARDADO.get("chave") is not None:
        os.environ["GEMINI_API_KEY"] = _GUARDADO["chave"]  # só a chave volta; o resto fica como sempre
    _GUARDADO.pop("pasta").cleanup()


class _Janela(QWidget):
    def __init__(self):
        super().__init__()
        self.hud = ui.HudCanvas("face.png", parent=self)
        self.hud.resize(900, 600)


class OrbeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        os.environ.pop("JARVIS_VISUAL", None)
        self.win = _Janela()
        self.ctl = ui_orbe.instalar(self.win)
        self.pedidos = []
        self.ctl._pedido.connect(lambda: self.pedidos.append(1))

    def test_desenha_em_todos_os_estados(self):
        for estado, falando in [("LISTENING", False), ("SPEAKING", True), ("THINKING", False), ("MUTED", False)]:
            self.win.hud.state, self.win.hud.speaking = estado, falando
            self.win.hud.muted = estado == "MUTED"
            px = QPixmap(self.win.hud.size())
            self.win.hud.render(px)
            self.assertFalse(px.isNull())

    def test_bom_dia_do_usuario_dispara(self):
        self.ctl.ver_texto("You: Bom dia, Jarvis!")
        self.ctl.ver_texto("You: BOM DIA")
        self.assertEqual(len(self.pedidos), 2)

    def test_outras_falas_nao_disparam(self):
        self.ctl.ver_texto("Jarvis: Bom dia, senhor.")
        self.ctl.ver_texto("You: boa tarde")
        self.ctl.ver_texto("You: o bom diálogo")
        self.assertEqual(self.pedidos, [])

    def test_classico_desliga(self):
        os.environ["JARVIS_VISUAL"] = "classico"
        try:
            self.assertIsNone(ui_orbe.instalar(_Janela()))
        finally:
            os.environ.pop("JARVIS_VISUAL", None)


class CenaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_cena_cobre_a_janela_e_alterna_com_f2(self):
        os.environ.pop("JARVIS_VISUAL", None)
        os.environ.pop("JARVIS_CENA", None)
        win = ui.MainWindow("face.png")
        try:
            cena = win._orbe.cena
            self.assertIsNotNone(cena)
            self.assertIs(win.hud.parentWidget(), cena)
            cena.alternar()                      # F2: volta para a tela antiga
            self.assertFalse(cena.isVisible())
            self.assertIsNot(win.hud.parentWidget(), cena)
            cena.alternar()                      # F2 de novo: volta para a cena
            self.assertIs(win.hud.parentWidget(), cena)
        finally:
            win.close()
            win.deleteLater()

    def test_canal_mostra_as_falas(self):
        win = ui.MainWindow("face.png")
        try:
            falas = []
            win._orbe.cena.fala.connect(lambda quem, txt: falas.append((quem, txt)))
            win._orbe.ver_texto("You: que horas são?")
            win._orbe.ver_texto("Jarvis: São dez horas.")
            win._orbe.ver_texto("SYS: conectado")
            self.assertEqual(falas, [("VOCÊ", "que horas são?"), ("JARVIS", "São dez horas.")])
        finally:
            win.close()
            win.deleteLater()

    def test_pergunta_antes_de_agir_aparece_por_cima_do_anel(self):
        # a pergunta do computer_settings ("Posso digitar ...?") vai pela ui.notificar: o registro (SYS:) fica
        # embaixo da cena e o canal nem aparece na tela limpa (a padrão). O aviso do Windows, perto do relógio,
        # leva o texto inteiro; o aviso da janela aparece por cima do anel
        os.environ.pop("JARVIS_VISUAL", None)
        os.environ.pop("JARVIS_CENA", None)
        win = ui.MainWindow("face.png")
        try:
            for nome in ("_overlay", "_name_overlay"):
                if getattr(win, nome, None) is not None:
                    getattr(win, nome).hide()
            win.resize(1366, 768)
            win.show()
            win._tray = Mock(isVisible=Mock(return_value=True))  # sem balão de verdade no PC de quem testa
            cena, central = win._orbe.cena, win.centralWidget()
            self.assertTrue(cena.isVisible())
            self.assertEqual(cena.geometry(), central.rect())  # a cena cobre a janela inteira
            jarvis_ui = object.__new__(ui.JarvisUI)
            jarvis_ui._win = win
            pergunta = ('Posso digitar "olá mundo" na janela "Sem título - Bloco de Notas"? Para confirmar, '
                        'diga "ok, pode fazer".')
            with patch("core.na_tela.executar", side_effect=lambda funcao: funcao()), \
                    patch.object(ui.ToastManager, "show_toast", wraps=ui.ToastManager.show_toast) as mostrar:
                jarvis_ui.notificar("Pergunta", pergunta)
            for _ in range(5):
                self.app.processEvents()
            win._tray.showMessage.assert_called_once_with("Jarvis · Pergunta", pergunta, ANY, 10000)
            avisos = [t for t in central.findChildren(ui.ToastNotification) if t.isVisible()
                      and any(pergunta in rotulo.text() for rotulo in t.findChildren(QLabel))]
            self.assertEqual(len(avisos), 1)
            aviso = avisos[0]
            self.assertFalse(cena.isAncestorOf(aviso))
            # o que aparece no meio do aviso é ele, e não a cena que cobre a janela
            no_meio = central.childAt(aviso.geometry().center())
            self.assertTrue(no_meio is aviso or aviso.isAncestorOf(no_meio), no_meio)
            # a pergunta fica no alto da janela por mais tempo que um aviso comum (4 s): o Erton lê e responde
            self.assertGreaterEqual(mostrar.call_args.kwargs.get("duration", 0), 15000)
            # e cabe inteira, com o nome da janela e o "ok, pode fazer" (antes, só os primeiros ~50 caracteres
            # apareciam): também uma com o título mais comprido que a pergunta mostra (80 caracteres)
            comprida = (f'Posso apertar Espaço (pausar ou continuar o vídeo) na janela "{("Lofi Girl - " * 7)[:79]}…"? '
                        'Para confirmar, diga "ok, pode fazer".')
            with patch("core.na_tela.executar", side_effect=lambda funcao: funcao()):
                jarvis_ui.notificar("Pergunta", comprida)
            for _ in range(5):
                self.app.processEvents()
            for texto in (pergunta, comprida):
                with self.subTest(texto=texto):
                    aviso = next(t for t in central.findChildren(ui.ToastNotification) if t.isVisible()
                                 and any(texto in r.text() for r in t.findChildren(QLabel)))
                    rotulo = next(r for r in aviso.findChildren(QLabel) if texto in r.text())
                    self.assertTrue(rotulo.wordWrap())
                    precisa = rotulo.fontMetrics().boundingRect(
                        QRect(0, 0, rotulo.contentsRect().width(), 10000),
                        Qt.TextFlag.TextWordWrap.value, rotulo.text()).height()
                    self.assertLessEqual(precisa, rotulo.contentsRect().height())
                    self.assertTrue(central.rect().contains(aviso.geometry()))
        finally:
            win.close()
            win.deleteLater()


ITENS_ULTRON = [(f"ferramenta_{i}", "✚", f"Automação {i}", {}) for i in range(8)]


class UltronNaCenaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        os.environ.pop("JARVIS_VISUAL", None)
        os.environ.pop("JARVIS_CENA", None)
        self.win = ui.MainWindow("face.png")
        for nome in ("_overlay", "_name_overlay"):
            w = getattr(self.win, nome, None)
            if w is not None:
                w.hide()
        self.cena = self.win._orbe.cena
        self.cena.limpa = False  # estes testes conferem os painéis dos lados (botão PAINÉIS aberto)

    def tearDown(self):
        ui_orbe.definir_ultron(self.win, False)
        self.win.close()
        self.win.deleteLater()

    def _eventos(self):
        for _ in range(10):
            self.app.processEvents()

    def test_modo_ultron_deixa_textos_campo_e_botoes_laranja(self):
        cena = self.cena
        cena.montar_botoes_ultron(ITENS_ULTRON, lambda n, a: None)
        cena.canal.adicionar("JARVIS", "Às ordens.")
        cena.st["Câmera local"].definir("EM USO", ui_orbe.CIANO)
        ui_orbe.definir_ultron(self.win, True)
        laranja_texto = ui_orbe.cor(ui_orbe.TEXTO2).name()
        laranja_ciano = ui_orbe.cor(ui_orbe.CIANO).name()
        self.assertNotEqual(laranja_texto, ui_orbe.TEXTO2)
        self.assertIn(laranja_texto, cena.topo_esq.styleSheet())           # barra do topo
        self.assertIn(laranja_texto, cena.l_pedidos_sub.styleSheet())      # "pedidos nesta sessão"
        self.assertIn(laranja_ciano, cena.st["Câmera local"].styleSheet())  # chip
        entrada = cena.canal.entrada.styleSheet()
        self.assertIn(laranja_ciano, entrada)                               # campo de digitar
        self.assertNotIn("95,180,255", entrada)
        botao = cena._botoes_ultron[0].styleSheet()                        # botões do Ultron na lateral
        self.assertIn(laranja_ciano, botao)
        self.assertNotIn("58,120,216", botao)
        self.assertNotIn("95,180,255", cena.b_chamada.styleSheet() + cena.b_maos.styleSheet())
        fala = cena.canal.lista.itemAt(0).widget().text()                  # nome JARVIS no canal
        self.assertIn(laranja_ciano, fala)
        self.assertNotIn(ui_orbe.CIANO, fala)
        # avisos mantêm o sentido (verde = ok), não viram rosa/azul
        self.assertIn(ui_orbe.VERDE, cena.st["Voz"].styleSheet())
        ui_orbe.definir_ultron(self.win, False)                             # "modo Jarvis": volta ao azul
        self.assertIn(ui_orbe.TEXTO2, cena.topo_esq.styleSheet())
        self.assertIn("58,120,216", cena._botoes_ultron[0].styleSheet())
        self.assertIn(ui_orbe.CIANO, cena.canal.entrada.styleSheet())

    def test_botoes_do_ultron_nao_se_sobrepoem_em_tela_baixa(self):
        cena = self.cena
        self.win.show()
        self._eventos()
        cena.montar_botoes_ultron(ITENS_ULTRON, lambda n, a: None)
        for altura in (700, 728, 820):  # 700 = janela maximizada num notebook 1366x768
            cena.setGeometry(0, 0, 1366, altura)
            cena._organizar()
            cena.p_ultron.corpo.activate()
            self._eventos()
            self.assertTrue(cena.p_ultron.isVisible())
            caixas = [b.geometry() for b in cena._botoes_ultron]
            for i, a in enumerate(caixas):
                for b in caixas[i + 1:]:
                    self.assertFalse(a.intersects(b), f"botões um por cima do outro com altura {altura}")
            dica = cena._dica_ultron
            if dica.isVisible():
                self.assertFalse(any(dica.geometry().intersects(c) for c in caixas))
            self.assertLessEqual(cena.p_ultron.geometry().bottom(), altura)

    def _instalar_painel(self):
        import importlib.util
        import types
        from unittest.mock import patch

        from core import na_tela
        na_tela.preparar()
        falso_main = types.ModuleType("main")
        falso_main.carregar_automacoes = lambda: types.SimpleNamespace(ferramentas={"pc_protection": 1})

        class J:
            ui = types.SimpleNamespace(_win=self.win)

            def rodar_automacao_ultron(self, nome, args=None):
                pass

        spec = importlib.util.spec_from_file_location("pu_cena", "automacoes/painel_ultron.py")
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        with patch.dict(sys.modules, {"main": falso_main}):
            m._construir(J())

    def test_sem_o_painel_ultron_nao_ha_botao_nem_quadro_vazio(self):
        self.win.resize(1400, 900)
        self.win.show()
        self._eventos()
        tela = self.win._tela_stark
        self.assertTrue(tela.botao_ultron.isHidden())       # apagou painel_ultron.py: o botão some
        self.assertFalse(self.cena.p_ultron.isVisible())    # e o quadro da lateral também
        self._instalar_painel()
        self._eventos()
        self.assertFalse(tela.botao_ultron.isHidden())
        self.assertTrue(self.cena.p_ultron.isVisible())

    def test_painel_ultron_abre_por_cima_da_cena(self):
        self.win.resize(1400, 900)
        self.win.show()
        self._eventos()
        self._instalar_painel()
        tela = self.win._tela_stark
        painel = tela._painel_ultron
        central = self.win.centralWidget()
        tela.ao_abrir_ultron()                               # mesmo caminho do "modo Ultron"
        self._eventos()
        self.assertTrue(ui_orbe._ULTRON)
        w = central.childAt(central.rect().center())
        self.assertTrue(w is painel or painel.isAncestorOf(w), f"o painel ficou escondido atrás de {w}")
        self.cena.alternar()                                 # F2: o painel aberto vai junto
        self._eventos()
        self.assertIs(painel.parentWidget(), tela)
        self.assertTrue(painel.isVisible())
        self.cena.alternar()
        self._eventos()
        self.assertIs(painel.parentWidget(), self.cena)
        from PyQt6.QtWidgets import QPushButton
        fechar = next(b for b in painel.findChildren(QPushButton) if "Fechar" in b.text())
        fechar.click()                                       # o "Fechar" está ao alcance
        self.assertFalse(painel.isVisible())
        self.assertFalse(ui_orbe._ULTRON)


class PerfilNaTelaTests(unittest.TestCase):
    """A saudação e a cidade vêm do perfil (tela "Sobre você"); o .env só vale se o perfil não tiver."""

    def setUp(self):
        from core import perfil
        from memory import memory_manager

        self.pasta = Path(tempfile.mkdtemp())
        self.trocas = [patch.object(perfil, "pasta_dados", lambda: self.pasta / "Jarvis Ultron"),
                       patch.object(memory_manager, "MEMORY_PATH", self.pasta / "long_term.json"),
                       patch.dict(os.environ)]
        for troca in self.trocas:
            troca.start()
        os.environ.pop("JARVIS_NOME", None)
        os.environ.pop("JARVIS_CIDADE", None)

    def tearDown(self):
        for troca in reversed(self.trocas):
            troca.stop()

    def test_sem_perfil_vale_o_env(self):
        os.environ["JARVIS_NOME"], os.environ["JARVIS_CIDADE"] = "Fulano", "Recife"
        self.assertEqual(ui_orbe._nome_para_saudacao(), "Fulano")
        self.assertEqual(ui_orbe._cidade(), "Recife")

    def test_perfil_ganha_do_env(self):
        from core import perfil

        os.environ["JARVIS_NOME"], os.environ["JARVIS_CIDADE"] = "Fulano", "Recife"
        perfil.salvar({"nome": "Maria Souza", "cidade": "Natal"})
        self.assertEqual(ui_orbe._nome_para_saudacao(), "Maria")
        self.assertEqual(ui_orbe._cidade(), "Natal")

    def test_sem_nome_nem_cidade_nada_e_inventado_e_o_clima_nao_localiza_pelo_ip(self):
        self.assertEqual(ui_orbe._nome_para_saudacao(), "")
        with patch("ui_stark.buscar_clima", side_effect=AssertionError("não devia perguntar ao serviço")):
            self.assertEqual(ui_orbe._clima(), {"cidade": "", "ok": False})


if __name__ == "__main__":
    unittest.main()


class TelaLimpaDoVideoTests(unittest.TestCase):
    """Padrão = tela limpa do vídeo: só o anel; o botão PAINÉIS mostra e esconde os lados."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        for nome in ("JARVIS_VISUAL", "JARVIS_CENA", "JARVIS_TELA"):
            os.environ.pop(nome, None)
        self.win = ui.MainWindow("face.png")
        for nome in ("_overlay", "_name_overlay"):
            w = getattr(self.win, nome, None)
            if w is not None:
                w.hide()
        self.win.resize(1300, 860)
        self.win.show()
        for _ in range(10):
            self.app.processEvents()
        self.cena = self.win._orbe.cena

    def tearDown(self):
        self.win.close()
        self.win.deleteLater()

    def test_abre_so_com_o_anel_e_o_campo_de_digitar(self):
        cena = self.cena
        self.assertTrue(cena.limpa)
        for w in (cena.p_voz, cena.p_sistema, cena.p_status, cena.p_ativ, cena.p_rede, cena.canal):
            self.assertFalse(w.isVisible())
        self.assertTrue(cena.entrada_rapida.isVisible())
        self.assertTrue(cena.b_paineis.isVisible())

    def test_botao_paineis_mostra_e_esconde_sem_perder_o_que_foi_digitado(self):
        cena = self.cena
        cena.entrada_rapida.setText("me lembra de ligar")
        cena.alternar_paineis()
        self.assertFalse(cena.limpa)
        self.assertTrue(cena.canal.isVisible())
        self.assertTrue(cena.p_status.isVisible())
        self.assertFalse(cena.entrada_rapida.isVisible())
        self.assertEqual(cena.canal.entrada.text(), "me lembra de ligar")
        cena.alternar_paineis()
        self.assertTrue(cena.limpa)
        self.assertFalse(cena.canal.isVisible())

    def test_digitar_na_tela_limpa_manda_para_o_jarvis(self):
        enviados = []
        self.win._send = enviados.append
        self.cena.entrada_rapida.setText("bom dia")
        self.cena._enviar_rapido()
        self.assertEqual(enviados, ["bom dia"])
        self.assertEqual(self.cena.entrada_rapida.text(), "")

    def test_jarvis_tela_paineis_abre_com_os_lados(self):
        os.environ["JARVIS_TELA"] = "paineis"
        try:
            win = ui.MainWindow("face.png")
            self.assertFalse(win._orbe.cena.limpa)
            win.close(); win.deleteLater()
        finally:
            os.environ.pop("JARVIS_TELA", None)

    def test_bom_dia_fica_dentro_do_anel(self):
        r = self.win._orbe.resumo
        r._encaixar()
        W, H = self.win._orbe.hud.width(), self.win._orbe.hud.height()
        R = min(W, H) * 0.34
        g = r.geometry()
        self.assertLessEqual(g.width(), 2 * R)
        self.assertLessEqual(g.height(), 2 * R)
        self.assertAlmostEqual(g.center().x(), W / 2, delta=4)
