"""O perfil de quem usa o Jarvis (core/perfil.py): preenchido na primeira abertura, guardado em
Documentos/Jarvis Ultron/perfil.json e usado pelos cérebros no lugar de um nome escrito no código.
Tudo numa pasta temporária: nem o perfil nem a memória de verdade são tocados."""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import perfil  # noqa: E402
from memory import memory_manager  # noqa: E402


class PerfilTests(unittest.TestCase):
    def setUp(self):
        self.pasta = Path(tempfile.mkdtemp())
        self.trocas = [patch.object(perfil, "pasta_dados", lambda: self.pasta / "Jarvis Ultron"),
                       patch.object(memory_manager, "MEMORY_PATH", self.pasta / "long_term.json"),
                       patch.dict(os.environ)]
        for troca in self.trocas:
            troca.start()
        os.environ.pop("JARVIS_CIDADE", None)

    def tearDown(self):
        for troca in reversed(self.trocas):
            troca.stop()

    def test_sem_nada_o_perfil_e_vazio_e_nao_grava(self):
        p = perfil.carregar()
        self.assertEqual({c: p[c] for c in perfil.CAMPOS}, {c: "" for c in perfil.CAMPOS})
        self.assertFalse(p["preenchido"])
        self.assertFalse(perfil.completo())
        self.assertEqual(perfil.tratamento(), "")
        self.assertEqual(perfil.bloco_para_prompt(), "")
        self.assertFalse(perfil.arquivo().exists())
        self.assertFalse((self.pasta / "long_term.json").exists())

    def test_salvar_e_carregar(self):
        perfil.salvar({"nome": "  Maria   Souza ", "cidade": " João Pessoa ", "profissao": "advogada",
                       "preferencias": "respostas curtas\n\nfoco em produtividade"})
        p = perfil.carregar()
        self.assertEqual(p["nome"], "Maria Souza")
        self.assertEqual(p["tratamento"], "")
        self.assertEqual(p["cidade"], "João Pessoa")
        self.assertEqual(p["preferencias"], "respostas curtas foco em produtividade")
        self.assertTrue(p["preenchido"])
        self.assertTrue(perfil.completo())
        self.assertEqual(perfil.tratamento(), "Maria")  # primeiro nome, quando não escolheu
        self.assertEqual(perfil.cidade(), "João Pessoa")
        gravado = json.loads(perfil.arquivo().read_text(encoding="utf-8"))
        self.assertEqual(gravado["nome"], "Maria Souza")
        identidade = memory_manager.load_memory()["identity"]  # a tela e a saudação leem daqui
        self.assertEqual(identidade["name"]["value"], "Maria Souza")
        self.assertEqual(identidade["city"]["value"], "João Pessoa")
        self.assertEqual(identidade["job"]["value"], "advogada")

    def test_tratamento_escolhido_ganha_do_primeiro_nome(self):
        perfil.salvar({"nome": "Maria Souza", "tratamento": "Dra. Maria"})
        self.assertEqual(perfil.tratamento(), "Dra. Maria")

    def test_quem_ja_usava_continua_com_o_nome_da_memoria(self):
        memory_manager.update_memory({"identity": {"name": {"value": "Erton"}, "city": {"value": "Campina Grande"}}})
        p = perfil.carregar()
        self.assertEqual((p["nome"], p["cidade"]), ("Erton", "Campina Grande"))
        self.assertTrue(perfil.completo())  # a tela "Sobre você" não aparece para ele
        self.assertFalse(perfil.arquivo().exists())  # carregar nunca grava

    def test_o_sir_da_tela_antiga_nao_conta_como_nome(self):
        memory_manager.update_memory({"identity": {"name": {"value": "Sir"}}})
        self.assertEqual(perfil.nome(), "")
        self.assertFalse(perfil.completo())

    def test_cidade_do_env_vale_quando_o_perfil_nao_tem(self):
        os.environ["JARVIS_CIDADE"] = "Recife"
        self.assertEqual(perfil.cidade(), "Recife")
        perfil.salvar({"nome": "Ana", "cidade": "Natal"})
        self.assertEqual(perfil.cidade(), "Natal")

    def test_pular_a_tela_grava_vazio_e_nao_pergunta_de_novo(self):
        perfil.salvar({})
        self.assertTrue(perfil.completo())
        self.assertEqual(perfil.tratamento(), "")
        self.assertEqual(perfil.bloco_para_prompt(), "")
        self.assertFalse((self.pasta / "long_term.json").exists())  # nada para levar à memória

    def test_bloco_para_prompt_so_com_o_que_foi_preenchido(self):
        perfil.salvar({"nome": "Maria Souza", "cidade": "Natal", "preferencias": "gosta de listas curtas"})
        self.assertEqual(perfil.bloco_para_prompt(),
                         "[SOBRE O USUÁRIO]\nNome: Maria Souza\nComo chamar: Maria\nCidade: Natal\n"
                         "Preferências e objetivos: gosta de listas curtas\n")
        perfil.salvar({"nome": "Maria Souza", "tratamento": "Dra. Maria"})
        self.assertEqual(perfil.bloco_para_prompt(), "[SOBRE O USUÁRIO]\nNome: Maria Souza\nComo chamar: Dra. Maria\n")

    def test_campos_tem_limite_de_tamanho(self):
        perfil.salvar({"nome": "x" * 300, "preferencias": "y" * 2000})
        p = perfil.carregar()
        self.assertEqual(len(p["nome"]), perfil.LIMITES["nome"])
        self.assertEqual(len(p["preferencias"]), perfil.LIMITES["preferencias"])

    def test_arquivo_estragado_nao_quebra(self):
        perfil.arquivo().parent.mkdir(parents=True)
        perfil.arquivo().write_text("{isso nao e json", encoding="utf-8")
        self.assertEqual(perfil.nome(), "")
        perfil.salvar({"nome": "Ana"})
        self.assertEqual(perfil.nome(), "Ana")
        perfil.arquivo().write_bytes(("\ufeff" + json.dumps({"nome": "Bia", "preenchido": True})).encode("utf-8"))
        self.assertEqual(perfil.nome(), "Bia")  # salvo com BOM pelo Bloco de Notas


if __name__ == "__main__":
    unittest.main()
