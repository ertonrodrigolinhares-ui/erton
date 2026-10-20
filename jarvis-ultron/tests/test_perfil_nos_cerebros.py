"""O perfil de quem usa o Jarvis (core/perfil.py) chega a todos os cérebros (Gemini, Gemma, Groq e
outra empresa), ao Claude chefe e ao Hermes, e nenhum deles traz mais o nome de uma pessoa escrito no
código. Tudo numa pasta temporária: nem o perfil nem a memória de verdade são tocados."""

import asyncio
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
MARIA = {"nome": "Maria Souza", "tratamento": "", "cidade": "Natal", "profissao": "advogada",
         "preferencias": "respostas curtas"}
BLOCO = ("[SOBRE O USUÁRIO]\nNome: Maria Souza\nComo chamar: Maria\nCidade: Natal\nProfissão ou área: advogada\n"
         "Preferências e objetivos: respostas curtas\n")


class Base(unittest.TestCase):
    def setUp(self):
        self.pasta = Path(tempfile.mkdtemp())
        self.trocas = [patch.object(perfil, "pasta_dados", lambda: self.pasta / "Jarvis Ultron"),
                       patch.object(memory_manager, "MEMORY_PATH", self.pasta / "long_term.json"),
                       patch.dict(os.environ)]
        for troca in self.trocas:
            troca.start()
        for nome in ("JARVIS_CIDADE", "JARVIS_NOME", "HERMES_JARVIS_HOME"):
            os.environ.pop(nome, None)

    def tearDown(self):
        for troca in reversed(self.trocas):
            troca.stop()


class GeminiTests(Base):
    def _instrucoes(self) -> str:
        import main

        jarvis = object.__new__(main.JarvisLive)
        jarvis.voice_name = "charon"
        with patch("main.load_memory", return_value={}), \
                patch.object(main.JarvisLive, "_get_current_voice", return_value="charon"):
            config = jarvis._build_config()
        return config.system_instruction if isinstance(config.system_instruction, str) else str(config.system_instruction)

    def test_instrucoes_levam_o_perfil_e_como_chamar(self):
        perfil.salvar(MARIA)
        texto = self._instrucoes()
        self.assertIn(BLOCO, texto)
        self.assertIn("address the user as 'Maria' (never as 'Sir' or 'Madam')", texto)
        self.assertNotIn("as 'Sir' or 'Madam' where appropriate", texto)  # a regra antiga do JARVIS-OS
        self.assertNotIn("Erton", texto)

    def test_sem_perfil_nenhum_nome_vem_do_codigo(self):
        texto = self._instrucoes()
        self.assertNotIn("[SOBRE O USUÁRIO]\nNome:", texto)  # o prompt só cita o nome do bloco
        self.assertNotIn("Erton", texto)
        self.assertIn("without 'Sir' or 'Madam'", texto)

    def _saudacao(self) -> str:
        import main

        jarvis = object.__new__(main.JarvisLive)
        jarvis._ja_cumprimentou = False
        jarvis._chamada_fechada = lambda: False
        enviados = []

        class Sessao:
            async def send_client_content(self, **kw):
                enviados.append(kw)

        jarvis.session = Sessao()
        asyncio.run(jarvis._announce_startup())
        return enviados[0]["turns"]["parts"][0]["text"]

    def test_saudacao_usa_o_nome_do_perfil(self):
        perfil.salvar({"nome": "Maria Souza", "tratamento": "Dra. Maria"})
        self.assertIn("Cumprimente Dra. Maria em português", self._saudacao())

    def test_saudacao_sem_perfil_nao_inventa_nome(self):
        texto = self._saudacao()
        self.assertIn("Cumprimente quem está falando com você", texto)
        self.assertNotIn("Erton", texto)


class ReservasEGemmaTests(Base):
    def test_gemma_groq_e_outra_empresa_recebem_o_perfil(self):
        from core.cerebro_gemma import CerebroGemma
        from core.reserva_groq import ReservaGroq
        from core.reserva_outra import ReservaOutra

        perfil.salvar(MARIA)
        for cerebro in (CerebroGemma(cliente=object()), ReservaGroq("chave", cliente=object()),
                        ReservaOutra("mistral", "chave", cliente=object())):
            sistema = cerebro.mensagens[0]["content"]
            self.assertEqual(cerebro.mensagens[0]["role"], "system")
            self.assertTrue(sistema.rstrip().endswith(BLOCO.rstrip()), type(cerebro).__name__)
            self.assertIn("assistente pessoal do usuário", sistema)
            self.assertNotIn("Erton", sistema)
        self.assertIn("modo reserva (Mistral)", ReservaOutra("mistral", "chave", cliente=object()).mensagens[0]["content"])

    def test_sem_perfil_as_instrucoes_ficam_como_eram(self):
        from core.cerebro_gemma import INSTRUCOES_GEMMA, CerebroGemma
        from core.reserva_groq import INSTRUCOES, ReservaGroq

        self.assertEqual(CerebroGemma(cliente=object()).mensagens[0]["content"], marca.aplicar(INSTRUCOES_GEMMA))
        self.assertEqual(ReservaGroq("chave", cliente=object()).mensagens[0]["content"], marca.aplicar(INSTRUCOES))


class ClaudeChefeTests(Base):
    def _pedidos(self, *chamadas):
        from core import claude_chefe as chefe

        textos = []
        with patch.object(chefe, "preparar_pasta", return_value=self.pasta / "Claude"), \
                patch.object(chefe, "rodar", side_effect=lambda texto, *a, **k: textos.append(texto)):
            for chamada in chamadas:
                chamada(chefe)
        return textos

    def test_tarefa_e_plano_levam_o_perfil_e_nao_o_nome_de_ninguem(self):
        perfil.salvar(MARIA)
        tarefa, plano = self._pedidos(lambda c: c.fazer_tarefa("pesquise X"), lambda c: c.planejar("mude a cor"))
        for texto in (tarefa, plano):
            self.assertIn(BLOCO.rstrip(), texto)
            self.assertIn("PEDIDO DO USUÁRIO:", texto)
            self.assertNotIn("Erton", texto)
            self.assertNotIn("Ironman", texto)

    def test_sem_perfil_o_claude_sabe_que_nao_conhece_a_pessoa(self):
        (tarefa,) = self._pedidos(lambda c: c.fazer_tarefa("pesquise X"))
        self.assertNotIn("[SOBRE O USUÁRIO]\n", tarefa)
        self.assertIn("quando houver, vem no bloco [SOBRE O USUÁRIO]", tarefa)
        self.assertNotIn("Erton", tarefa)

    def test_modelo_do_claude_md_nao_traz_ninguem(self):
        from core import claude_chefe as chefe

        texto = (RAIZ / "claude" / "CLAUDE.md").read_text(encoding="utf-8")
        self.assertIn("## Quem usa o Jarvis\n", texto)
        self.assertIsNotNone(chefe._QUEM_E.search(texto))
        for nome in ("Erton", "Ironman", "Emanuele", "Yvnna", "clientes.txt"):
            self.assertNotIn(nome, texto)


class HermesTests(Base):
    def test_personalidade_leva_o_perfil(self):
        from core.automacoes import sincronizar_personalidade

        perfil.salvar(MARIA)
        pasta_perfil = self.pasta / "hermes" / "profiles" / "jarvis"
        pasta_perfil.mkdir(parents=True)
        self.assertTrue(sincronizar_personalidade(pasta_perfil))
        soul = (pasta_perfil / "SOUL.md").read_text(encoding="utf-8")
        self.assertIn(BLOCO.rstrip(), soul)
        self.assertNotIn("__PERFIL__", soul)
        self.assertNotIn("Erton", soul)

    def test_sem_perfil_a_marca_sai_e_sem_hermes_nada_e_escrito(self):
        from core.automacoes import sincronizar_personalidade

        pasta_perfil = self.pasta / "jarvis"
        pasta_perfil.mkdir()
        self.assertTrue(sincronizar_personalidade(pasta_perfil))
        self.assertNotIn("__PERFIL__", (pasta_perfil / "SOUL.md").read_text(encoding="utf-8"))
        self.assertFalse(sincronizar_personalidade(self.pasta / "nao-existe"))
        self.assertFalse(sincronizar_personalidade())  # HERMES_JARVIS_HOME vazio: Hermes não instalado
        self.assertFalse((self.pasta / "nao-existe").exists())

    def test_textos_das_travas_e_do_prompt_nao_trazem_ninguem(self):
        import importlib.util

        from core.reserva_groq import INSTRUCOES
        from core.cerebro_gemma import INSTRUCOES_GEMMA
        from core import claude_chefe as chefe

        spec = importlib.util.spec_from_file_location("aprovacao_jarvis", RAIZ / "hermes" / "hooks" / "aprovacao_jarvis.py")
        gancho = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(gancho)
        for texto in (INSTRUCOES, INSTRUCOES_GEMMA, chefe.REGRAS, chefe.REGRAS_TAREFA, chefe.REGRAS_PLANO,
                      chefe.REGRAS_APLICAR, *gancho.MENSAGEM.values(),
                      (RAIZ / "core" / "prompt.txt").read_text(encoding="utf-8"),
                      (RAIZ / "hermes" / "SOUL.md").read_text(encoding="utf-8")):
            self.assertNotIn("Erton", texto)


if __name__ == "__main__":
    unittest.main()
