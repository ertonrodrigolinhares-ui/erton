"""Etapa 10 da reorganização: print salvo, música do próprio PC e "você quis dizer…?". Tudo sem nuvem."""

import importlib.util
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from core import texto  # noqa: E402


def _automacao(nome: str):
    spec = importlib.util.spec_from_file_location(f"teste10_{nome}", RAIZ / "automacoes" / f"{nome}.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


class TextoTests(unittest.TestCase):
    def test_normalizar_tira_acento_maiuscula_e_pontuacao(self):
        self.assertEqual(texto.normalizar("  Praia de Tambaú, João!  "), "praia de tambau joao")

    def test_palavra_inteira_e_nao_pedaco(self):
        self.assertTrue(texto.tem_palavra("que horas são, hein", "horas"))
        self.assertFalse(texto.tem_palavra("sometimes it rains", "time"))
        self.assertFalse(texto.tem_palavra("é simples", "sim"))
        self.assertTrue(texto.tem_palavra("sim, pode", "sim"))
        self.assertTrue(texto.tem_todas("Evidências - Chitãozinho & Xororó.mp3", "evidencias chitaozinho"))
        self.assertFalse(texto.tem_todas("Evidências", "evidencias ao vivo"))
        self.assertFalse(texto.tem_todas("qualquer coisa", ""))


class PrintSalvoTests(unittest.TestCase):
    def test_salva_png_com_data_e_hora_na_pasta_capturas(self):
        import actions.computer_settings as cs

        gravados = []

        class Sct:
            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

            def shot(self, mon, output):
                gravados.append((mon, output))
                Path(output).write_bytes(b"\x89PNG")
                return output

        with tempfile.TemporaryDirectory() as pasta, \
                patch.object(cs, "pasta_capturas", return_value=Path(pasta) / "Capturas"), \
                patch.dict(sys.modules, {"mss": type("M", (), {"mss": staticmethod(lambda: Sct())})}):
            caminho = cs.save_screenshot(datetime(2026, 10, 30, 14, 5, 9))
            self.assertEqual(caminho, Path(pasta) / "Capturas" / "2026-10-30_14-05-09.png")
            self.assertTrue(caminho.exists())
            self.assertEqual(gravados[0][0], -1)  # a tela inteira
            # pela ferramenta do Jarvis: responde onde salvou, sem pedir "ok" (não digita nem aperta tecla)
            with patch.object(cs, "_PYAUTOGUI", True):
                resposta = cs.computer_settings({"action": "save_screenshot"})
        self.assertIn("Print salvo em", resposta)
        self.assertIn("Capturas", resposta)
        self.assertIn("save_screenshot", cs.ACTION_MAP)
        self.assertIn("save_screenshot", cs.NAO_PEDEM_OK)
        self.assertNotIn("save_screenshot", cs.TECLAS_PEDEM_OK)

    def test_memoria_do_hd_nao_copia_a_pasta_capturas(self):
        m = _automacao("memoria_hd")
        with tempfile.TemporaryDirectory() as base:
            base = Path(base)
            docs = base / "docs"
            (docs / "Capturas").mkdir(parents=True)
            (docs / "Capturas" / "2026-10-30_14-05-09.png").write_bytes(b"png")
            (docs / "lembretes.json").write_text("{}", encoding="utf-8")
            copiados, total = m._copiar_pasta(docs, base / "HD" / "documentos", None)
            self.assertEqual((copiados, total), (1, 1))
            self.assertTrue((base / "HD" / "documentos" / "lembretes.json").exists())
            self.assertFalse((base / "HD" / "documentos" / "Capturas").exists())


class MusicaLocalTests(unittest.TestCase):
    def setUp(self):
        self.m = _automacao("musica_local")
        self.pasta = Path(tempfile.mkdtemp())
        for nome in ("Evidências - Chitãozinho.mp3", "Evidências (ao vivo).m4a", "Simples Assim.flac",
                     "capa.jpg", "Sim ou Não.wav"):
            (self.pasta / nome).write_bytes(b"x")
        (self.pasta / "Antigas").mkdir()
        (self.pasta / "Antigas" / "Evidências remix.ogg").write_bytes(b"x")
        self.ambiente = patch.dict(os.environ, {"JARVIS_PASTA_MUSICA": str(self.pasta)})
        self.ambiente.start()

    def tearDown(self):
        self.ambiente.stop()

    def test_compara_palavra_inteira_e_com_varias_diz_quantas_achou(self):
        with patch.object(self.m, "tocar") as tocar:
            resposta = self.m.executar({"title": "evidências"}, None)
        tocar.assert_not_called()  # 3 músicas: não sorteia uma
        self.assertIn("Achei 3 músicas", resposta)
        self.assertIn("Evidências remix", resposta)  # procura nas subpastas também
        with patch.object(self.m, "tocar") as tocar:
            resposta = self.m.executar({"title": "sim"}, None)  # "sim" não bate em "Simples Assim"
        self.assertEqual(tocar.call_args.args[0].name, "Sim ou Não.wav")
        self.assertIn("Tocando Sim ou Não", resposta)

    def test_sem_resultado_e_sem_pedido(self):
        with patch.object(self.m, "tocar") as tocar:
            self.assertIn("Não achei nenhuma música", self.m.executar({"title": "bossa nova"}, None))
            self.assertIn("Faltou dizer", self.m.executar({}, None))
        tocar.assert_not_called()

    def test_nao_usa_ia_na_nuvem(self):
        import main

        self.assertFalse(self.m.USA_IA_NUVEM)
        self.assertNotIn("local_music", main.FERRAMENTAS_NUVEM_IA)


class VoceQuisDizerTests(unittest.TestCase):
    def test_rotina_com_nome_entendido_errado(self):
        r = _automacao("rotinas")
        pasta = Path(tempfile.mkdtemp())
        arquivo = pasta / "rotinas.json"
        arquivo.write_text(json.dumps({"rotinas": {
            "treino": {"passos": ["abrir o spotify"]},
            "cobrança joão": {"passos": ["ligar"], "privado": True}}}), encoding="utf-8")
        with patch.dict(os.environ, {"JARVIS_CEREBRO": "gemini"}):
            resposta = r.rodar({"name": "rotina trein0"}, None, arquivo)
            self.assertIn("Não achei essa rotina", resposta)
            self.assertIn("Você quis dizer a rotina 'treino'?", resposta)
            self.assertIn("Você quis dizer a rotina 'treino'?", r.apagar({"name": "treinu"}, arquivo))
            self.assertTrue((arquivo.exists()) and "treino" in arquivo.read_text(encoding="utf-8"))  # não apagou
            # a rotina do modo privado nunca é sugerida fora dele
            self.assertNotIn("cobrança", r.rodar({"name": "cobranca joao"}, None, arquivo))
            self.assertIn("Não achei essa rotina", r.rodar({"name": "xyz"}, None, arquivo))

    def test_lembrete_com_texto_entendido_errado(self):
        lembretes = _automacao("lembretes")
        pasta = Path(tempfile.mkdtemp())
        arquivo = pasta / "lembretes.json"
        agora = datetime(2026, 9, 25, 14, 0)
        lembretes.criar({"text": "ligar para o contador", "time": "18:00"}, agora, arquivo)
        lembretes.criar({"text": "treino", "time": "19:00"}, agora, arquivo)
        resposta = lembretes.cancelar({"text": "ligar para o contadir"}, arquivo)
        self.assertIn("Não achei esse lembrete", resposta)
        self.assertIn("Você quis dizer o lembrete 1: ligar para o contador?", resposta)
        self.assertEqual(len(lembretes.ler(arquivo)["lembretes"]), 2)  # não cancelou nada
        self.assertIn("Não achei esse lembrete. Lembretes:", lembretes.cancelar({"text": "dentista"}, arquivo))


if __name__ == "__main__":
    unittest.main()
