import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import reserva_outra
from core.reserva_groq import ReservaGroq
from core.reserva_outra import ReservaEmFila, ReservaOutra, reserva_da_configuracao


class RateLimitError(Exception):
    pass


class ClienteFalso:
    def __init__(self, modelos=(), roteiro=()):
        self.roteiro, self.pedidos = list(roteiro), []
        self.models = NS(list=lambda: NS(data=[NS(id=m) for m in modelos]))
        self.chat = NS(completions=NS(create=self._criar))

    def _criar(self, **pedido):
        self.pedidos.append(pedido)
        proxima = self.roteiro.pop(0) if self.roteiro else "ok"
        if isinstance(proxima, Exception):
            raise proxima
        return NS(choices=[NS(message=NS(content=proxima, tool_calls=None))])


SEM_RESERVA = {"JARVIS_RESERVA": "", "JARVIS_RESERVA_CHAVE": "", "JARVIS_RESERVA_URL": "",
               "JARVIS_RESERVA_MODELO": "", "GROQ_API_KEY": ""}


class ConfiguracaoTests(unittest.TestCase):
    def test_sem_chave_nao_tem_outra(self):
        with patch.dict(os.environ, dict(SEM_RESERVA, JARVIS_RESERVA="cerebras")):
            self.assertIsNone(ReservaOutra.da_configuracao())

    def test_empresa_conhecida_usa_o_endereco_dela(self):
        with patch.dict(os.environ, dict(SEM_RESERVA, JARVIS_RESERVA="Cerebras", JARVIS_RESERVA_CHAVE="csk-x")):
            r = ReservaOutra.da_configuracao()
        self.assertEqual(r.nome, "Cerebras")
        self.assertIn("api.cerebras.ai", str(r.cliente.base_url))

    def test_empresa_desconhecida_precisa_do_endereco(self):
        with patch.dict(os.environ, dict(SEM_RESERVA, JARVIS_RESERVA="outra", JARVIS_RESERVA_CHAVE="k")):
            self.assertIsNone(ReservaOutra.da_configuracao())
        with patch.dict(os.environ, dict(SEM_RESERVA, JARVIS_RESERVA="outra", JARVIS_RESERVA_CHAVE="k",
                                         JARVIS_RESERVA_URL="https://exemplo.com/v1")):
            self.assertIn("exemplo.com", str(ReservaOutra.da_configuracao().cliente.base_url))

    def test_groq_e_outra_ficam_em_fila_com_a_outra_primeiro(self):
        with patch.dict(os.environ, dict(SEM_RESERVA, JARVIS_RESERVA="mistral", JARVIS_RESERVA_CHAVE="m",
                                         GROQ_API_KEY="gsk_x")):
            r = reserva_da_configuracao()
        self.assertIsInstance(r, ReservaEmFila)
        self.assertEqual(r.nome, "Mistral")
        self.assertIsInstance(r.reservas[1], ReservaGroq)

    def test_so_o_groq_continua_como_antes(self):
        with patch.dict(os.environ, dict(SEM_RESERVA, GROQ_API_KEY="gsk_x")):
            self.assertIsInstance(reserva_da_configuracao(), ReservaGroq)
        with patch.dict(os.environ, SEM_RESERVA):
            self.assertIsNone(reserva_da_configuracao())


class ModeloTests(unittest.TestCase):
    def test_escolhe_o_preferido_que_a_conta_tem(self):
        r = ReservaOutra("cerebras", "k", cliente=ClienteFalso(["llama3.1-8b", "llama-3.3-70b", "gpt-oss-120b"]))
        self.assertEqual(r._escolher_modelo(), "gpt-oss-120b")

    def test_modelo_do_env_manda(self):
        r = ReservaOutra("cerebras", "k", modelo="qwen-3-32b", cliente=ClienteFalso(["gpt-oss-120b"]))
        self.assertEqual(r._escolher_modelo(), "qwen-3-32b")

    def test_instrucoes_dizem_qual_reserva(self):
        r = ReservaOutra("mistral", "k", cliente=ClienteFalso())
        self.assertIn("modo reserva (Mistral)", r.mensagens[0]["content"])
        self.assertNotIn("Groq", r.mensagens[0]["content"])


class FilaTests(unittest.TestCase):
    def test_limite_de_uma_passa_para_a_outra_e_ela_vira_a_primeira(self):
        groq = ReservaGroq("gsk", cliente=ClienteFalso(["openai/gpt-oss-120b"], [RateLimitError("limite")]))
        outra = ReservaOutra("cerebras", "k", cliente=ClienteFalso(["gpt-oss-120b"], ["Bom dia, Erton."]))
        fila = ReservaEmFila([groq, outra])
        self.assertEqual(fila.responder("bom dia"), "Bom dia, Erton.")
        self.assertIs(fila.reservas[0], outra)  # da próxima vez já começa pela que funciona
        self.assertEqual(fila.nome, "Cerebras")

    def test_erro_comum_nao_troca(self):
        class Estranho(Exception):
            pass

        a = ReservaOutra("cerebras", "k", cliente=ClienteFalso(["x"], [Estranho("x")]))
        b = ReservaOutra("mistral", "k", cliente=ClienteFalso(["y"], ["não devia"]))
        fila = ReservaEmFila([a, b])
        self.assertIn("não conseguiu responder", fila.responder("oi"))
        self.assertEqual(b.cliente.pedidos, [])


class OuvirTests(unittest.TestCase):
    def test_usa_o_whisper_do_pc_quando_instalado(self):
        r = ReservaOutra("cerebras", "k", cliente=ClienteFalso())
        with patch("core.cerebro_gemma.whisper_instalado", return_value=True), \
                patch("core.cerebro_gemma.CerebroGemma.transcrever", return_value="que horas são"), \
                patch.object(ReservaGroq, "da_configuracao", side_effect=AssertionError("não devia ir ao Groq")):
            self.assertEqual(r.transcrever(b"\x00\x00" * 160), "que horas são")

    def test_sem_whisper_do_pc_usa_o_do_groq(self):
        r = ReservaOutra("cerebras", "k", cliente=ClienteFalso())
        groq = NS(transcrever=lambda pcm, taxa=16000: "bom dia")
        with patch("core.cerebro_gemma.whisper_instalado", return_value=False), \
                patch.object(ReservaGroq, "da_configuracao", return_value=groq):
            self.assertEqual(r.transcrever(b"\x00\x00" * 160), "bom dia")


if __name__ == "__main__":
    unittest.main()
