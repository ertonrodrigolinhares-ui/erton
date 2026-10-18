import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import agentes


class AgentesLigadosTests(unittest.TestCase):
    def setUp(self):
        self.arquivo = Path(tempfile.mkdtemp()) / "agentes_ligados.txt"
        self.p = patch.object(agentes, "arquivo_ligados", lambda: self.arquivo)
        self.p.start()

    def tearDown(self):
        self.p.stop()

    def test_todos_os_agentes_tem_titulo_emoji_e_nome_curto(self):
        lista = agentes.todos()
        self.assertGreaterEqual(len(lista), 20)
        for a in lista:
            self.assertTrue(a["titulo"])
            self.assertLessEqual(len(a["curto"]), 13, a["nome"])
            self.assertTrue(a["emoji"])

    def test_ligar_e_desligar(self):
        self.assertEqual(agentes.ligados(), [])
        self.assertTrue(agentes.ligar("proposta-comercial"))
        self.assertTrue(agentes.ligar("legislacao"))
        self.assertTrue(agentes.ligar("legislacao"))  # duas vezes não duplica
        self.assertFalse(agentes.ligar("nao-existe"))
        self.assertEqual(agentes.ligados(), ["proposta-comercial", "legislacao"])
        self.assertTrue(agentes.desligar("proposta-comercial"))
        self.assertEqual(agentes.ligados(), ["legislacao"])

    def test_cada_agente_ligado_vira_um_botao_que_chama_o_claude(self):
        agentes.ligar("holding-sucessao")
        (ferramenta, emoji, titulo, sub, args), = agentes.botoes_dos_ligados()
        self.assertEqual(ferramenta, "claude_task")
        self.assertEqual(args["agent"], "holding-sucessao")
        self.assertIn("holding-sucessao", args["request"])
        self.assertTrue(titulo)


class PainelSemGeekieTests(unittest.TestCase):
    def test_geekie_saiu_do_painel_ultron(self):
        import importlib.util

        raiz = Path(__file__).resolve().parents[1]
        spec = importlib.util.spec_from_file_location("pu_sem_geekie", raiz / "automacoes" / "painel_ultron.py")
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        self.assertNotIn("school_tasks", [b[0] for b in m.BOTOES])


if __name__ == "__main__":
    unittest.main()
