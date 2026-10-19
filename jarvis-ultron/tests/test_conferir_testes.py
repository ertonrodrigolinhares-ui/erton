"""O alarme de testes (dev/conferir_testes.py): um teste instável só é perdoado se oscilar.

Aqui o pytest nunca roda de verdade: a função que roda os testes é trocada por uma falsa."""

import contextlib
import importlib.util
import io
import tempfile
import unittest
from pathlib import Path
from unittest import mock

RAIZ = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("conferir_testes", RAIZ / "dev" / "conferir_testes.py")
conferir = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(conferir)

FIXA = "tests/test_a.py::A::test_fixa"
ANEL = "tests/test_b.py::B::test_anel"


class RodarFalso:
    """Faz o papel do pytest: a suíte inteira devolve `suite`; cada teste sozinho, a próxima resposta."""

    def __init__(self, suite, sozinho):
        self.suite, self.sozinho, self.chamadas = suite, list(sozinho), []

    def __call__(self, alvos, env=None):
        self.chamadas.append(list(alvos))
        if alvos == ["tests"]:
            return None if self.suite is None else set(self.suite)
        return self.sozinho.pop(0)


class InstaveisTests(unittest.TestCase):
    def test_instavel_que_passa_ao_repetir_nao_conta(self):
        rodar = RodarFalso(set(), [{ANEL}, set()])  # falha de novo uma vez e depois passa
        self.assertEqual(conferir.instaveis_que_sempre_falham([ANEL], rodar, vezes=3), [])
        self.assertEqual(rodar.chamadas, [[ANEL], [ANEL]])  # para de repetir quando passa

    def test_instavel_que_falha_em_todas_as_vezes_conta(self):
        rodar = RodarFalso(set(), [{ANEL}, {ANEL}, {ANEL}])
        self.assertEqual(conferir.instaveis_que_sempre_falham([ANEL], rodar, vezes=3), [ANEL])
        self.assertEqual(len(rodar.chamadas), 3)

    def test_sem_conseguir_repetir_conta_como_falha(self):
        rodar = RodarFalso(set(), [None, None])  # na dúvida, o alarme toca
        self.assertEqual(conferir.instaveis_que_sempre_falham([ANEL], rodar, vezes=2), [ANEL])


class MainTests(unittest.TestCase):
    def _main(self, suite, sozinho):
        with tempfile.TemporaryDirectory() as pasta:
            conhecidas = Path(pasta) / "falhas_conhecidas.txt"
            conhecidas.write_text(f"# comentário\n{FIXA}\ninstavel: {ANEL}\n", encoding="utf-8")
            fixas_instaveis = conferir.ler_conhecidas(conhecidas)
            rodar = RodarFalso(suite, sozinho)
            saida = io.StringIO()
            with mock.patch.object(conferir, "ler_conhecidas", return_value=fixas_instaveis), \
                    mock.patch.object(conferir, "rodar_pytest", rodar), contextlib.redirect_stdout(saida):
                codigo = conferir.main([])
        return codigo, saida.getvalue(), rodar

    def test_instavel_que_sempre_falha_e_falha_nova(self):
        # ex.: uma etapa quebra o desenho normal do anel; os testes "instáveis" falham em toda rodada
        codigo, saida, rodar = self._main({FIXA, ANEL}, [{ANEL}] * conferir.REPETIR)
        self.assertEqual(codigo, 1)
        self.assertIn("1 falha(s) nova(s)", saida)
        self.assertIn(ANEL, saida)
        self.assertNotIn("nenhuma falha nova", saida)
        self.assertEqual(rodar.chamadas, [["tests"]] + [[ANEL]] * conferir.REPETIR)

    def test_instavel_que_oscila_nao_e_falha_nova(self):
        codigo, saida, _ = self._main({FIXA, ANEL}, [set()])
        self.assertEqual(codigo, 0)
        self.assertIn("nenhuma falha nova", saida)
        self.assertIn(f"passaram ao rodar de novo, não contam: {ANEL}", saida)

    def test_so_as_conhecidas_nao_repete_nada(self):
        codigo, saida, rodar = self._main({FIXA}, [])
        self.assertEqual(codigo, 0)
        self.assertIn("nenhuma falha nova", saida)
        self.assertEqual(rodar.chamadas, [["tests"]])

    def test_falha_fora_da_lista_e_nova(self):
        outra = "tests/test_c.py::C::test_outra"
        codigo, saida, _ = self._main({FIXA, outra}, [])
        self.assertEqual(codigo, 1)
        self.assertIn(outra, saida)

    def test_sem_conseguir_rodar_a_suite_sai_com_2(self):
        codigo, _, rodar = self._main(None, [])
        self.assertEqual(codigo, 2)
        self.assertEqual(rodar.chamadas, [["tests"]])


if __name__ == "__main__":
    unittest.main()
