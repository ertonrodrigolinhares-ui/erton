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
        self.assertGreaterEqual(len(lista), 10)
        for a in lista:
            self.assertTrue(a["titulo"])
            self.assertLessEqual(len(a["curto"]), 13, a["nome"])
            self.assertTrue(a["emoji"])

    def test_ligar_e_desligar(self):
        self.assertEqual(agentes.ligados(), [])
        self.assertTrue(agentes.ligar("proposta-comercial"))
        self.assertTrue(agentes.ligar("viagens"))
        self.assertTrue(agentes.ligar("viagens"))  # duas vezes não duplica
        self.assertFalse(agentes.ligar("nao-existe"))
        self.assertEqual(agentes.ligados(), ["proposta-comercial", "viagens"])
        self.assertTrue(agentes.desligar("proposta-comercial"))
        self.assertEqual(agentes.ligados(), ["viagens"])

    def test_cada_agente_ligado_vira_um_botao_que_chama_o_claude(self):
        agentes.ligar("resumo-reuniao")
        (ferramenta, emoji, titulo, sub, args), = agentes.botoes_dos_ligados()
        self.assertEqual(ferramenta, "claude_task")
        self.assertEqual(args["agent"], "resumo-reuniao")
        self.assertIn("resumo-reuniao", args["request"])
        self.assertTrue(titulo)


class PacoteDoDonoTests(unittest.TestCase):
    """Os agentes do dono (atleta, família, escola, contabilidade) ficam em pacotes/erton e só entram com
    JARVIS_PACOTE=erton no .env: o produto que o cliente recebe não os tem."""

    DO_DONO = ("rotina-atleta-8h", "conteudo-atleta", "treino-semana", "prazos-fiscais", "holding-sucessao", "legislacao")

    def test_sem_pacote_o_produto_so_tem_os_genericos(self):
        with patch.dict(os.environ):
            os.environ.pop("JARVIS_PACOTE", None)
            nomes = {a["nome"] for a in agentes.todos()}
        self.assertIn("resumo-reuniao", nomes)
        self.assertEqual(nomes & set(self.DO_DONO), set())
        for a in agentes.todos():
            texto = (agentes.pasta_agentes() / a["nome"] / "SKILL.md").read_text(encoding="utf-8")
            for proibido in ("Erton", "Ironman", "contáb", "tribut", "fiscal", "holding", "Yvnna"):
                self.assertNotIn(proibido, texto, a["nome"])

    def test_com_o_pacote_os_agentes_do_dono_entram(self):
        with patch.dict(os.environ, {"JARVIS_PACOTE": "erton"}):
            nomes = {a["nome"] for a in agentes.todos()}
            self.assertTrue(set(self.DO_DONO) <= nomes, nomes)
            self.assertIn("resumo-reuniao", nomes)
            self.assertTrue(agentes.ligar("rotina-atleta-8h"))
        with patch.dict(os.environ, {"JARVIS_PACOTE": "nao-existe"}):
            self.assertEqual({a["nome"] for a in agentes.todos()} & set(self.DO_DONO), set())
        with patch.dict(os.environ, {"JARVIS_PACOTE": "../erton"}):  # nome inválido não vira caminho
            self.assertEqual({a["nome"] for a in agentes.todos()} & set(self.DO_DONO), set())

    def setUp(self):
        self.arquivo = Path(tempfile.mkdtemp()) / "agentes_ligados.txt"
        self.p = patch.object(agentes, "arquivo_ligados", lambda: self.arquivo)
        self.p.start()

    def tearDown(self):
        self.p.stop()


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
