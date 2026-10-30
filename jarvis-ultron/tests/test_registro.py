"""Etapa 13 da reorganização: o registro das ferramentas conferido POR IMPORTAÇÃO, não pelo texto.

Três coisas: toda ferramenta declarada ao Gemini tem quem a execute; todo executor da tabela tem declaração;
e nenhum nome se repete entre as ferramentas nativas e as automações da pasta. Enquanto a tabela EXECUTORES
é preenchida (um grupo por commit), uma ferramenta pode ainda estar no "elif" do _execute_tool: o
core/qa_audit.dispatch_names() enxerga os dois caminhos."""

import os
import sys
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import main  # noqa: E402
from cerebro.ferramentas.declaracoes import TOOL_DECLARATIONS  # noqa: E402
from core.qa_audit import dispatch_names  # noqa: E402


class RegistroTests(unittest.TestCase):
    def test_toda_ferramenta_declarada_tem_executor(self):
        declaradas = [d["name"] for d in TOOL_DECLARATIONS]
        caminhos = dispatch_names(RAIZ / "main.py")
        self.assertEqual(sorted(set(declaradas) - caminhos), [])

    def test_todo_executor_da_tabela_tem_declaracao(self):
        declaradas = {d["name"] for d in TOOL_DECLARATIONS}
        self.assertEqual(sorted(set(main.EXECUTORES) - declaradas), [])
        # a cadeia de "elif" acabou: só o save_memory fica fora da tabela (regra própria do modo privado)
        self.assertEqual(set(main.EXECUTORES), declaradas - {"save_memory"})
        self.assertNotIn('elif name == "', (RAIZ / "main.py").read_text(encoding="utf-8"))
        for nome, executor in main.EXECUTORES.items():
            self.assertTrue(callable(executor), nome)

    def test_nenhum_nome_se_repete(self):
        declaradas = [d["name"] for d in TOOL_DECLARATIONS]
        self.assertEqual(len(declaradas), len(set(declaradas)), "declaração repetida")
        automacoes = set(main.carregar_automacoes().ferramentas)
        self.assertEqual(set(declaradas) & automacoes, set(), "automação com o nome de uma ferramenta nativa")
        self.assertEqual(set(declaradas) & set(main.FERRAMENTAS_DESLIGADAS), set(), "desligada ainda declarada")
        self.assertEqual(set(main.EXECUTORES) & set(main.FERRAMENTAS_DESLIGADAS), set())


class FichasTests(unittest.TestCase):
    """Etapa 14 (b): a ficha única de cada ferramenta; as listas antigas são calculadas dela."""

    def test_toda_ferramenta_declarada_tem_ficha_e_toda_ficha_ligada_tem_declaracao(self):
        from cerebro.ferramentas import fichas

        declaradas = {d["name"] for d in TOOL_DECLARATIONS}
        ligadas = {f.nome for f in fichas.FICHAS if not f.desligada}
        self.assertEqual(ligadas, declaradas)
        for f in fichas.FICHAS:
            with self.subTest(ferramenta=f.nome):
                self.assertEqual(f.declaracao is not None, not bool(f.desligada))
                self.assertEqual(f.executar is None, bool(f.desligada) or f.nome == "save_memory")

    def test_listas_antigas_sao_calculadas_das_fichas(self):
        from cerebro.ferramentas import fichas, politica

        self.assertIs(main.FERRAMENTAS_NUVEM_IA, fichas.FERRAMENTAS_NUVEM_IA)
        self.assertIs(politica.MUDAM_ALGO, fichas.MUDAM_ALGO)
        self.assertIs(main.JarvisLive.RESERVA_FERRAMENTAS_ESSENCIAIS, fichas.RESERVA_FERRAMENTAS_ESSENCIAIS)
        self.assertEqual(main.FERRAMENTAS_DESLIGADAS, fichas.FERRAMENTAS_DESLIGADAS)
        self.assertEqual(set(main.EXECUTORES), {f.nome for f in fichas.FICHAS if f.executar is not None})

    def test_regra_por_argumento_do_modo_privado_vem_da_ficha(self):
        from cerebro.ferramentas import fichas

        self.assertTrue(fichas.REGRAS_DE_NUVEM["youtube_video"]({"action": "Summarize"}))
        self.assertFalse(fichas.REGRAS_DE_NUVEM["youtube_video"]({"action": "play"}))
        self.assertTrue(fichas.REGRAS_DE_NUVEM["school_tasks"]({"refresh": True}))
        self.assertNotIn("youtube_video", fichas.FERRAMENTAS_NUVEM_IA)  # só o resumo vai para a nuvem

    def test_resposta_padrao_da_ficha_e_a_do_executor(self):
        # a frase da ficha é a que o executor devolve quando a ação não devolve nada (ou o molde dela)
        import inspect

        from cerebro.ferramentas import fichas

        for f in fichas.FICHAS:
            if f.executar is None or not f.resposta_padrao or "{" in f.resposta_padrao:
                continue  # sem executor, sempre responde, ou a frase tem um {campo}
            with self.subTest(ferramenta=f.nome):
                self.assertIn(f.resposta_padrao, inspect.getsource(f.executar))


if __name__ == "__main__":
    unittest.main()
