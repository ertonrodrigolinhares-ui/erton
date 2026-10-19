"""A pasta arquivo/ guarda, por algumas semanas, peças que saíram do Jarvis na reorganização
(docs/PLANO-REORGANIZACAO.md, Etapas 5 e 11). Nada fora dela pode usar o que está lá: se usasse, o
Jarvis quebraria ao abrir, ou uma peça guardada voltaria a rodar sem ninguém ver."""

import ast
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
ARQUIVO = RAIZ / "arquivo"
NAO_OLHAR = {".git", "__pycache__", ".venv", "venv", "env", "tmp", "outputs", "node_modules", "build", "dist",
             "arquivo"}

# Módulos que foram para arquivo/. Cada peça tem a sua linha de comentário fixa, e o nome entra logo
# abaixo dela no commit que a guarda: assim um "git revert" de uma peça não esbarra no de outra.
GUARDADOS = (
    # awareness/ (Etapa 5)
    # memory/answer_cache.py (Etapa 5)
    # core/graphics_capability.py (Etapa 5)
)


def _arquivos_py():
    este = Path(__file__).resolve()
    for caminho in sorted(RAIZ.rglob("*.py")):
        if caminho.resolve() != este and not NAO_OLHAR.intersection(caminho.relative_to(RAIZ).parts[:-1]):
            yield caminho


def _guardado(nome: str) -> bool:
    return any(nome == g or nome.startswith(g + ".") for g in GUARDADOS)


class NadaUsaOArquivoTests(unittest.TestCase):
    def test_nada_fora_de_arquivo_importa_o_que_foi_guardado(self):
        problemas = []
        for caminho in _arquivos_py():
            texto = caminho.read_text(encoding="utf-8", errors="replace")
            try:
                arvore = ast.parse(texto)
            except SyntaxError:
                continue  # uma automação com erro não é assunto deste teste
            for no in ast.walk(arvore):
                if isinstance(no, ast.Import):
                    nomes = [a.name for a in no.names]
                elif isinstance(no, ast.ImportFrom) and no.module and not no.level:
                    nomes = [no.module] + [f"{no.module}.{a.name}" for a in no.names]
                elif isinstance(no, ast.Constant) and isinstance(no.value, str):
                    # alvos de patch("memory.answer_cache.x"), import_module("..."), caminhos para sys.path
                    if _guardado(no.value) or "pecas-sem-uso" in no.value:
                        problemas.append(f"{caminho.relative_to(RAIZ)}:{no.lineno}: {no.value[:80]!r}")
                    continue
                else:
                    continue
                for nome in nomes:
                    if nome.split(".")[0] == "arquivo" or _guardado(nome):
                        problemas.append(f"{caminho.relative_to(RAIZ)}:{no.lineno}: import {nome}")
        self.assertEqual(problemas, [], "o Jarvis não pode usar o que está em arquivo/")

    def test_compilacao_do_scripts_qa_so_cita_o_que_existe(self):
        arvore = ast.parse((RAIZ / "scripts" / "qa.py").read_text(encoding="utf-8"))
        listas = [no for no in ast.walk(arvore) if isinstance(no, ast.List)
                  and any(isinstance(e, ast.Constant) and e.value == "compileall" for e in no.elts)]
        self.assertEqual(len(listas), 1)
        valores = [e.value for e in listas[0].elts if isinstance(e, ast.Constant)]
        caminhos = valores[valores.index("-q") + 1:]
        self.assertTrue(caminhos)
        self.assertNotIn("arquivo", caminhos)
        for caminho in caminhos:
            self.assertTrue((RAIZ / caminho).exists(), f"scripts/qa.py compila {caminho}, que não existe mais")

    def test_testes_guardados_nao_rodam(self):
        if not ARQUIVO.is_dir():
            self.skipTest("nada guardado ainda")
        conftest = (ARQUIVO / "conftest.py").read_text(encoding="utf-8")
        self.assertIn('collect_ignore_glob = ["*"]', conftest)
        self.assertTrue((ARQUIVO / "LEIA-ME.md").is_file())


if __name__ == "__main__":
    unittest.main()
