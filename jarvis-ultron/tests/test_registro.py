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


if __name__ == "__main__":
    unittest.main()
