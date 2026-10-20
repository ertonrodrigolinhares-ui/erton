"""O nome do produto vem de core/marca.py: trocar NOME e NOME_CURTO lá renomeia o assistente nos prompts
dos cérebros, no Claude chefe, no Hermes e nas telas. O docs/RENOMEAR.md diz o que ainda é trocado à mão."""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import marca, perfil  # noqa: E402
from memory import memory_manager  # noqa: E402

RAIZ = Path(__file__).resolve().parents[1]


class MarcaTests(unittest.TestCase):
    def setUp(self):
        self.pasta = Path(tempfile.mkdtemp())
        self.trocas = [patch.object(perfil, "pasta_dados", lambda: self.pasta / "Jarvis Ultron"),
                       patch.object(memory_manager, "MEMORY_PATH", self.pasta / "long_term.json"),
                       patch.dict(os.environ)]
        for troca in self.trocas:
            troca.start()
        os.environ.pop("HERMES_JARVIS_HOME", None)

    def tearDown(self):
        for troca in reversed(self.trocas):
            troca.stop()

    def test_nome_de_hoje(self):
        self.assertEqual((marca.NOME, marca.NOME_CURTO), ("Luiz Conrado", "Luiz"))
        self.assertEqual(marca.TITULO_DA_JANELA, marca.NOME)
        self.assertEqual(marca.aplicar("o __MARCA__ (__MARCA_CURTA__)"), "o Luiz Conrado (Luiz)")

    def test_a_tela_e_a_trava_da_janela_usam_o_mesmo_titulo(self):
        from actions import computer_settings as cs

        self.assertEqual(cs.TITULO_DO_JARVIS, marca.TITULO_DA_JANELA)
        ui = (RAIZ / "ui.py").read_text(encoding="utf-8")
        self.assertIn("self.setWindowTitle(marca.TITULO_DA_JANELA)", ui)
        self.assertIn("self._tray.setToolTip(marca.TITULO_DA_JANELA)", ui)

    def test_textos_dos_cerebros_nao_escrevem_o_nome_na_mao(self):
        from core import claude_chefe as chefe
        from core.cerebro_gemma import INSTRUCOES_GEMMA
        from core.reserva_groq import INSTRUCOES

        soul = (RAIZ / "hermes" / "SOUL.md").read_text(encoding="utf-8")
        for texto in (INSTRUCOES, INSTRUCOES_GEMMA, chefe.REGRAS, chefe.REGRAS_TAREFA, chefe.REGRAS_PLANO, soul):
            for nome in ("Jarvis Ultron", marca.NOME):  # nem o nome velho nem o de hoje escritos à mão
                self.assertNotIn(nome, texto)
            self.assertIn("__MARCA", texto)

    def test_trocar_o_nome_renomeia_cerebros_claude_e_hermes(self):
        from core import claude_chefe as chefe
        from core.automacoes import sincronizar_personalidade
        from core.cerebro_gemma import CerebroGemma
        from core.reserva_groq import ReservaGroq
        from core.reserva_outra import ReservaOutra

        pasta_hermes = self.pasta / "hermes-jarvis"
        pasta_hermes.mkdir()
        with patch.object(marca, "NOME", "Atlas Assistente"), patch.object(marca, "NOME_CURTO", "Atlas"):
            for cerebro in (CerebroGemma(cliente=object()), ReservaGroq("chave", cliente=object()),
                            ReservaOutra("mistral", "chave", cliente=object())):
                self.assertIn("Você é o Atlas Assistente, assistente pessoal", cerebro.mensagens[0]["content"])
            regras = chefe._regras()
            self.assertIn('"chefe de tarefas" do Atlas Assistente, o assistente de voz de quem usa o Atlas', regras)
            self.assertTrue(sincronizar_personalidade(pasta_hermes))
            soul = (pasta_hermes / "SOUL.md").read_text(encoding="utf-8")
            self.assertIn("# Atlas Assistente (perfil", soul)
            self.assertIn("Você é o Atlas Assistente, o agente principal de quem usa o Atlas.", soul)
        for texto in (chefe._regras(), CerebroGemma(cliente=object()).mensagens[0]["content"], soul):
            self.assertNotIn("__MARCA", texto)
        self.assertIn(marca.NOME, chefe._regras())  # de volta ao nome de hoje

    def test_guia_de_renomear_existe_e_cita_o_que_fica_a_mao(self):
        guia = (RAIZ / "docs" / "RENOMEAR.md").read_text(encoding="utf-8")
        for trecho in ("core/marca.py", "Hey Jarvis", "Documentos", ".bat", "prompt.txt", "LEIA-ME"):
            self.assertIn(trecho, guia)


if __name__ == "__main__":
    unittest.main()
