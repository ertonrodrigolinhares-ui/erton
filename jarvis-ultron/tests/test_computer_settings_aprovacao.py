"""O "ok" do Erton no computer_settings (Etapa 4 do docs/PLANO-REORGANIZACAO.md).

Desligar e reiniciar o PC só acontecem com o "ok" dele conferido no código pelo core/aprovacao.py, como
no approve_publication e nos vídeos: a primeira chamada só pergunta; a ação só roda se a PRIMEIRA fala
nova dele depois da pergunta for um "ok" claro. O confirmed=yes que o modelo preenche não basta, um "ok"
dito antes da pergunta não vale, "não" cancela e o ok vale uma vez só. A trava fica dentro da ação, que o
_execute_tool chama com o jarvis: vale para o Gemini, para a reserva e para qualquer outro cérebro.

Nada aqui desliga, reinicia, digita ou aperta tecla de verdade: o subprocess, o pyautogui, o pyperclip e o
ctypes da ação são sempre falsos."""

import asyncio
import ctypes
import os
import sys
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "tests"))

import actions.computer_settings as cs  # noqa: E402
from core import aprovacao  # noqa: E402
from test_contratos import UIFalsa  # noqa: E402

REINICIAR = {"action": "restart", "description": "restart my computer"}
DESLIGAR = {"action": "shutdown", "description": "shut down my computer"}
JANELA = (42, "Sem título - Bloco de Notas")


def _esperar_fio() -> None:
    for fio in threading.enumerate():
        if fio.name == "ComputadorOk":
            fio.join(10)


class JarvisFalso:
    """Imita o JarvisLive nas aprovações: conta as falas do Erton e guarda os avisos."""

    def __init__(self, fala=""):
        self._fala_n, self._fala_texto = 0, ""
        self.avisos, self.logs = [], []
        self.ui = NS(write_log=self.logs.append)
        if fala:
            self.falar(fala)

    def falar(self, texto):
        aprovacao.nova_fala(self, texto)

    def anunciar(self, texto, titulo="Lembrete", sigiloso=False, ao_falar=None):
        self.avisos.append(texto)
        return "falado"


class BaseTests(unittest.TestCase):
    """Tudo o que age de verdade fica falso; o pedido guardado começa e termina vazio."""

    def setUp(self):
        self.teclado = Mock()
        self.sistema = Mock()
        self.sistema.run.return_value = NS(returncode=1, stdout="", stderr="")
        self.ctypes = Mock()
        for alvo in (patch.object(cs, "_PYAUTOGUI", True), patch.object(cs, "pyautogui", self.teclado, create=True),
                     patch.object(cs, "_PYPERCLIP", False), patch.object(cs, "subprocess", self.sistema),
                     patch.object(cs, "_OS", "Windows"), patch.object(ctypes, "windll", self.ctypes, create=True),
                     patch.object(cs, "_janela_da_frente", return_value=JANELA),
                     patch.object(cs, "_detect_action", side_effect=AssertionError("foi para a nuvem"))):
            alvo.start()
            self.addCleanup(alvo.stop)
        cs._pendente.clear()
        self.addCleanup(cs._pendente.clear)
        self.addCleanup(_esperar_fio)

    def chamar(self, args, jarvis):
        resposta = cs.computer_settings(parameters=dict(args), player=None, jarvis=jarvis)
        _esperar_fio()
        return resposta

    def desligou(self):
        """Os comandos de desligar e reiniciar que foram mandados ao Windows."""
        return [c.args[0] for c in self.sistema.run.call_args_list if c.args and c.args[0][:1] == ["shutdown"]]


class DesligarEReiniciarTests(BaseTests):
    def test_confirmed_yes_sem_fala_nova_nao_reinicia(self):
        jarvis = JarvisFalso("reinicia o computador")
        primeira = self.chamar(dict(REINICIAR, confirmed="yes"), jarvis)
        self.assertIn("Not done yet", primeira)
        self.assertIn("Posso reiniciar o computador agora?", primeira)
        segunda = self.chamar(dict(REINICIAR, confirmed="yes"), jarvis)
        self.assertIn("has not answered", segunda)
        self.assertEqual(self.desligou(), [])
        self.assertEqual(jarvis.avisos, [])

    def test_ok_antes_da_pergunta_nao_vale(self):
        jarvis = JarvisFalso("reinicia o computador, ok, pode fazer")
        self.assertIn("Not done yet", self.chamar(REINICIAR, jarvis))
        self.assertIn("has not answered", self.chamar(dict(REINICIAR, confirmed="yes"), jarvis))
        self.assertEqual(self.desligou(), [])

    def test_ok_depois_da_pergunta_reinicia_uma_vez_so(self):
        jarvis = JarvisFalso("reinicia o computador")
        self.chamar(REINICIAR, jarvis)
        jarvis.falar("ok, pode fazer")
        self.assertIn("Approved", self.chamar(dict(REINICIAR, confirmed="yes"), jarvis))
        self.assertEqual(self.desligou(), [["shutdown", "/r", "/t", "10"]])  # espera 10 s e sem /f
        # o ok valeu uma vez: chamar de novo pergunta de novo, e não reinicia outra vez
        self.assertIn("Not done yet", self.chamar(dict(REINICIAR, confirmed="yes"), jarvis))
        self.assertEqual(len(self.desligou()), 1)
        self.assertEqual(jarvis.avisos, [])
        self.assertIn("SYS: ✅ Feito com o seu ok: reiniciar o computador.", jarvis.logs)

    def test_desligar_tambem_so_com_o_ok(self):
        jarvis = JarvisFalso("desliga o computador")
        self.assertIn("Posso desligar o computador agora?", self.chamar(DESLIGAR, jarvis))
        self.assertIn("has not answered", self.chamar(dict(DESLIGAR, confirmed="true"), jarvis))
        self.assertEqual(self.desligou(), [])
        jarvis.falar("ok")
        self.assertIn("Approved", self.chamar(DESLIGAR, jarvis))
        self.assertEqual(self.desligou(), [["shutdown", "/s", "/t", "10"]])

    def test_nao_cancela(self):
        jarvis = JarvisFalso("reinicia o computador")
        self.chamar(REINICIAR, jarvis)
        jarvis.falar("não")
        self.assertIn("Cancelled", self.chamar(dict(REINICIAR, confirmed="yes"), jarvis))
        self.assertEqual(cs._pendente, {})
        # um "ok" depois do "não" não ressuscita a pergunta: vira um pedido novo, que pergunta de novo
        jarvis.falar("ok, pode fazer")
        self.assertIn("Not done yet", self.chamar(dict(REINICIAR, confirmed="yes"), jarvis))
        self.assertEqual(self.desligou(), [])

    def test_so_a_primeira_resposta_vale(self):
        # depois do "não" (que o modelo não mandou), o Erton fala de outra coisa e diz "ok": não reinicia
        jarvis = JarvisFalso("reinicia o computador")
        self.chamar(REINICIAR, jarvis)
        jarvis.falar("não, deixa")
        jarvis.falar("ok")
        self.assertIn("Not done yet", self.chamar(dict(REINICIAR, confirmed="yes"), jarvis))
        self.assertEqual(self.desligou(), [])

    def test_ok_que_nao_e_claro_nao_vale(self):
        for resposta in ("ok, pode cancelar", "sim, mas depois", "ok?", "ok, entendi"):
            with self.subTest(resposta=resposta):
                jarvis = JarvisFalso("reinicia o computador")
                self.chamar(REINICIAR, jarvis)
                jarvis.falar(resposta)
                self.assertIn("Cancelled", self.chamar(dict(REINICIAR, confirmed="yes"), jarvis))
        self.assertEqual(self.desligou(), [])

    def test_ok_dado_a_um_pedido_nao_vale_para_outro(self):
        jarvis = JarvisFalso("reinicia o computador")
        self.chamar(REINICIAR, jarvis)
        jarvis.falar("ok, pode fazer")
        self.assertIn("Not done yet", self.chamar(dict(DESLIGAR, confirmed="yes"), jarvis))
        self.assertEqual(self.desligou(), [])

    def test_pergunta_vencida_pergunta_de_novo(self):
        jarvis = JarvisFalso("reinicia o computador")
        self.chamar(REINICIAR, jarvis)
        cs._pendente["em"] -= cs.VALIDADE_PEDIDO + 1
        jarvis.falar("ok")
        self.assertIn("Not done yet", self.chamar(dict(REINICIAR, confirmed="yes"), jarvis))
        self.assertEqual(self.desligou(), [])

    def test_resto_da_fala_que_desfaz_o_ok_nao_reinicia(self):
        # Gemini ao vivo: a ferramenta chega com só o "Ok," transcrito; o resto ("não, espera") chega depois
        jarvis = JarvisFalso("reinicia o computador")
        self.chamar(REINICIAR, jarvis)
        with patch.object(aprovacao, "SILENCIO", 0.2):
            numero = aprovacao.nova_fala(jarvis, "Ok,", em_pedacos=True)
            resposta = cs.computer_settings(parameters=dict(REINICIAR), jarvis=jarvis)
            aprovacao.mais_um_pedaco(jarvis, numero, "Ok, não, espera")
            aprovacao.fechar_fala(jarvis, numero)
            _esperar_fio()
        self.assertIn("Approved", resposta)
        self.assertEqual(self.desligou(), [])
        self.assertEqual(len(jarvis.avisos), 1)
        self.assertIn('Não vou reiniciar o computador: a sua resposta não foi um "ok" claro', jarvis.avisos[0])

    def test_a_pergunta_aparece_na_tela(self):
        jarvis = JarvisFalso("reinicia o computador")
        self.chamar(REINICIAR, jarvis)
        self.assertTrue(any(log.startswith("SYS: ✋") and "Posso reiniciar o computador agora?" in log
                            and '"ok, pode fazer"' in log for log in jarvis.logs), jarvis.logs)

    def test_alvo_explicito_e_desligar_o_jarvis_continuam(self):
        jarvis = JarvisFalso("reinicia")
        self.assertIn("target was not explicit", self.chamar({"action": "restart", "confirmed": "yes"}, jarvis))
        self.assertIn("self-shutdown is disabled",
                      self.chamar({"action": "shutdown", "description": "shut down jarvis", "confirmed": "yes"}, jarvis))
        self.assertEqual(cs._pendente, {})
        self.assertEqual(self.desligou(), [])

    def test_sem_a_conversa_nao_desliga(self):
        # quem chama a ação sem o jarvis (ex.: o agent/executor.py antigo) não consegue o "ok"
        for args in (REINICIAR, dict(DESLIGAR, confirmed="yes")):
            with self.subTest(args=args):
                resposta = cs.computer_settings(parameters=dict(args), player=None)
                self.assertIn("Not done", resposta)
        self.assertEqual(self.desligou(), [])
        self.assertEqual(cs._pendente, {})


class PeloExecuteToolTests(BaseTests):
    """A trava vale para qualquer cérebro: o _execute_tool passa o jarvis para a ação."""

    def _jarvis(self):
        import main

        jarvis = object.__new__(main.JarvisLive)
        jarvis.ui = jarvis.client = UIFalsa()
        jarvis.cloud_safe = False
        jarvis.speak_error = Mock()
        jarvis.anunciar = Mock(return_value="falado")
        return jarvis

    def _ambiente(self, cerebro="gemini"):
        ambiente = patch.dict(os.environ, {"JARVIS_CEREBRO": cerebro, "JARVIS_QA_MODE": "0"})
        ambiente.start()
        self.addCleanup(ambiente.stop)

    def _pelo_gemini(self, jarvis, args):
        resposta = asyncio.run(jarvis._execute_tool(NS(id="1", name="computer_settings", args=dict(args))))
        _esperar_fio()
        return resposta.response["result"]

    def _pela_reserva(self, jarvis, args):
        resposta = jarvis._executar_ferramenta_reserva("computer_settings", dict(args))
        _esperar_fio()
        return resposta

    def test_gemini_so_reinicia_com_o_ok(self):
        self._ambiente()
        jarvis = self._jarvis()
        jarvis._nova_fala("reinicia o computador")
        self.assertIn("Not done yet", self._pelo_gemini(jarvis, dict(REINICIAR, confirmed="yes")))
        self.assertIn("has not answered", self._pelo_gemini(jarvis, dict(REINICIAR, confirmed="yes")))
        self.assertEqual(self.desligou(), [])
        jarvis._nova_fala("ok, pode fazer")
        self.assertIn("Approved", self._pelo_gemini(jarvis, dict(REINICIAR, confirmed="yes")))
        self.assertEqual(self.desligou(), [["shutdown", "/r", "/t", "10"]])
        jarvis.speak_error.assert_not_called()

    def test_reserva_tambem_passa_pela_trava(self):
        # o Groq e a outra empresa (e o Gemma) rodam as ferramentas pelo mesmo _execute_tool
        self._ambiente()
        jarvis = self._jarvis()
        self.addCleanup(lambda: getattr(jarvis, "_loop_reserva", None)
                        and jarvis._loop_reserva.call_soon_threadsafe(jarvis._loop_reserva.stop))
        jarvis._nova_fala("reinicia o computador")
        self.assertIn("Not done yet", self._pela_reserva(jarvis, dict(REINICIAR, confirmed="yes")))
        self.assertEqual(self.desligou(), [])
        jarvis._nova_fala("não")
        self.assertIn("Cancelled", self._pela_reserva(jarvis, dict(REINICIAR, confirmed="yes")))
        self.assertEqual(self.desligou(), [])
        jarvis._nova_fala("reinicia o computador")
        self._pela_reserva(jarvis, REINICIAR)
        jarvis._nova_fala("ok")
        self.assertIn("Approved", self._pela_reserva(jarvis, REINICIAR))
        self.assertEqual(self.desligou(), [["shutdown", "/r", "/t", "10"]])

    def test_modo_privado_continua_recusando_o_computer_settings_inteiro(self):
        import main

        self._ambiente("gemma")
        jarvis = self._jarvis()
        jarvis._nova_fala("ok")
        for args in (REINICIAR, {"action": "volume_up"}):
            with self.subTest(args=args):
                self.assertEqual(self._pelo_gemini(jarvis, args), main.AVISO_MODO_PRIVADO)
        self.assertEqual(cs._pendente, {})
        self.assertEqual(self.desligou(), [])
        self.teclado.press.assert_not_called()


if __name__ == "__main__":
    unittest.main()
