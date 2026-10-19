"""O que a tela de hoje precisa garantir (Etapa 2 da reorganização).

Curto de propósito: cada teste confere uma coisa da tela que o Erton usa ou que protege a chave, o modo
privado ou a ponte com o cérebro. Os testes do JARVIS-OS que cobravam telas que não existem mais
(apresentação inicial, tour guiado...) saíram do tests/test_ui_regressions.py; ficam guardados na
etiqueta git "antes-da-reorganizacao".

A janela de teste nunca lê nem grava as configurações, a chave, o cofre ou o .env de verdade: tudo vai
para uma pasta temporária e o cofre é trocado por um vazio. A chave que o main.py (importado por outros
testes) já pôs no ambiente, lida do .env do Erton, sai enquanto a janela existe: sem chave, a tela não
tenta falar com o Google. E, se algo ainda tentar, o validador é falso e responde "não conferida".
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import QApplication, QLineEdit

import ui
from core.api_key_validator import ApiKeyValidationResult
from core.ponte import METODOS_TELA


class _CofreVazio:
    def get(self, _chave):
        return None


class TelaContratosTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls._pasta = tempfile.TemporaryDirectory()
        pasta = Path(cls._pasta.name)
        cls._trocas = [
            patch.dict(os.environ),  # devolve as variáveis como estavam no fim
            patch.object(ui, "UI_SETTINGS_FILE", pasta / "settings.json"),
            patch.object(ui, "LAYOUT_SETTINGS_FILE", pasta / "layout_settings.json"),
            patch.object(ui, "API_FILE", pasta / "api_keys.json"),
            patch.object(ui, "get_secret_store", return_value=_CofreVazio()),
            patch.object(ui, "BASE_DIR", pasta),  # o .env que a tela regrava ao aceitar uma chave
            # a tela importa o validador na hora de conferir: ele nunca chega ao Google no teste
            patch("core.api_key_validator.validate_gemini_api_key", side_effect=cls._validador_falso),
        ]
        cls._chaves_conferidas = []
        for troca in cls._trocas:
            troca.start()
        for nome in ("JARVIS_VISUAL", "JARVIS_CENA", "JARVIS_TELA", "JARVIS_CEREBRO"):
            os.environ.pop(nome, None)  # a tela padrão: o anel azul (Cena), tela limpa, cérebro Gemini
        os.environ.pop("GEMINI_API_KEY", None)  # a do .env do Erton, se o main.py já foi importado
        cls.janela = ui.MainWindow("face.png")
        cls.janela.show()
        cls.app.processEvents()
        # a fachada que o cérebro usa, em cima da mesma janela (sem abrir uma segunda)
        cls.fachada = ui.JarvisUI.__new__(ui.JarvisUI)
        cls.fachada._win = cls.janela

    @classmethod
    def _validador_falso(cls, chave, *_args, **_kwargs):
        cls._chaves_conferidas.append(chave)
        return ApiKeyValidationResult(False, "Não conferida no teste.")

    @classmethod
    def tearDownClass(cls):
        cls.janela.hide()
        cls.janela.deleteLater()
        cls.app.processEvents()
        for troca in reversed(cls._trocas):
            troca.stop()
        cls._pasta.cleanup()

    def test_campo_da_chave_fica_mascarado(self):
        # a tela da chave do Gemini (a da janela e uma nova) e a da chave da voz externa
        tutorial = ui.KeyTutorialOverlay(None, "elevenlabs")
        nova = ui.SetupOverlay()
        try:
            self.assertIsNotNone(self.janela._overlay)  # sem chave salva, a tela da chave abre
            for campo in (self.janela._overlay._key_input, nova._key_input, tutorial._key_input):
                self.assertEqual(campo.echoMode(), QLineEdit.EchoMode.Password)
                campo.setText("AIza-chave-de-teste")
                self.assertNotIn("AIza", campo.displayText())  # o que aparece na tela
                campo.clear()
        finally:
            nova.deleteLater()
            tutorial.deleteLater()

    def test_a_chave_de_verdade_nunca_vai_ao_google(self):
        # no PC do Erton, a chave do .env já está no ambiente quando a janela de teste abre: ela não pode
        # ser mandada ao Google nem regravada no .env de verdade (o _on_setup_done grava em BASE_DIR)
        self.assertIsNotNone(self.janela._overlay)  # a tela da chave continua aberta, esperando
        self.assertFalse(self.janela._overlay._validation_pending)  # nem começou a conferir uma chave
        self.assertEqual(self._chaves_conferidas, [])
        self.assertFalse(self.janela._ready)
        self.assertEqual(ui.BASE_DIR, Path(self._pasta.name))

    def test_jarvis_ui_tem_todos_os_nomes_da_ponte(self):
        # o cérebro (outro programa) chama a tela por estes nomes, via core/ponte.py
        faltam = sorted(nome for nome in METODOS_TELA if not callable(getattr(ui.JarvisUI, nome, None)))
        self.assertEqual(faltam, [])

    def test_voice_combo_existe_e_informa_a_voz_atual(self):
        combo = self.fachada._voice_combo  # o main.py (_get_current_voice) lê a voz por aqui
        self.assertIs(combo, self.janela._voice_combo)
        antes = self.janela._get_selected_voice()
        try:
            self.fachada.sync_voice_display("kore")  # o cérebro avisa qual voz está usando
            self.app.processEvents()
            self.assertEqual(combo.itemData(combo.currentIndex()), "kore")
            self.assertEqual(self.janela._get_selected_voice(), "kore")
        finally:
            self.janela._sync_voice_combo(antes)

    def test_chat_bubble_nasce_antes_do_focus_dialogue(self):
        # o FocusDialogue se liga ao _chat_bubble ao nascer: se a ordem de montagem mudar, a fala some
        self.assertIs(self.janela._log, self.janela._chat_bubble)
        self.fachada.write_log("Jarvis: Tudo pronto.")
        self.app.processEvents()
        self.assertEqual(self.janela._focus_dialogue._speaker_lbl.text(), "JARVIS")
        self.assertEqual(self.janela._focus_dialogue._message_lbl.text(), "Tudo pronto.")

    def test_cena_cobre_a_janela_e_f2_alterna(self):
        cena = self.janela._orbe.cena
        self.assertIsNotNone(cena)
        self.assertTrue(cena.isVisible())
        self.assertEqual(cena.geometry(), self.janela.centralWidget().rect())
        f2 = [a for a in self.janela.findChildren(QShortcut) if a.key() == QKeySequence("F2")]
        self.assertEqual(len(f2), 1)
        try:
            f2[0].activated.emit()  # F2: vai para a tela antiga
            self.assertFalse(cena.isVisible())
            f2[0].activated.emit()  # F2 de novo: a cena volta e cobre a janela
            self.assertTrue(cena.isVisible())
            self.assertEqual(cena.geometry(), self.janela.centralWidget().rect())
        finally:
            if not cena.isVisible():
                cena.alternar()

    def test_selo_do_modo_privado_com_o_gemma(self):
        cena = self.janela._orbe.cena
        with patch.dict(os.environ, {"JARVIS_CEREBRO": "gemma"}):
            cena._atualizar()
            self.assertTrue(cena.topo_esq.isVisible())
            self.assertTrue(cena.topo_esq.text().startswith("🔒"), cena.topo_esq.text())
            self.assertIn("MODO PRIVADO", cena.topo_esq.text())
        cena._atualizar()  # de volta ao Gemini: o selo sai
        self.assertNotIn("🔒", cena.topo_esq.text())
        self.assertIn("PRINCIPAL", cena.topo_esq.text())


if __name__ == "__main__":
    unittest.main()
