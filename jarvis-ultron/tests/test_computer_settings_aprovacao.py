"""O "ok" do Erton no computer_settings (Etapa 4 do docs/PLANO-REORGANIZACAO.md).

Desligar e reiniciar o PC, e tudo o que escreve ou aperta teclas no programa da janela da frente
(TECLAS_PEDEM_OK, type_text, press_key, reload_n), só acontecem com o "ok" dele conferido no código pelo
core/aprovacao.py, como no approve_publication e nos vídeos: a primeira chamada só pergunta (com o texto,
as teclas e a janela); a ação só roda se a PRIMEIRA fala nova dele depois da pergunta for um "ok" claro. O
confirmed=yes que o modelo preenche não basta, um "ok" dito antes da pergunta não vale, "não" cancela, o ok
vale uma vez só, e outro texto ou outra janela pedem de novo. Volume, brilho, Wi-Fi e os atalhos que o
próprio Windows atende (NAO_PEDEM_OK) continuam sem pergunta. A trava fica dentro da ação, que o
_execute_tool chama com o jarvis: vale para o Gemini, para a reserva e para qualquer outro cérebro.

Nada aqui desliga, reinicia, digita ou aperta tecla de verdade: o subprocess, o pyautogui, o pyperclip e o
ctypes da ação são sempre falsos."""

import asyncio
import ctypes
import os
import sys
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import Mock, call, patch

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
JANELA_DA_FRENTE = cs._janela_da_frente  # a de verdade (nos testes ela fica falsa)
# fora do ACTION_MAP, também mandam texto ou teclas para o programa da frente
TECLADO_FORA_DO_MAPA = {
    "type_text": {"value": "olá"}, "write_on_screen": {"value": "olá"}, "type": {"value": "olá"},
    "write": {"text": "olá"}, "press_key": {"value": "enter"}, "reload_n": {"value": "2"},
    "refresh_n": {"value": "1"}, "reload_page_n": {},
}


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
                     patch.object(cs, "time", NS(sleep=Mock(), monotonic=time.monotonic)),
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


class TecladoTests(BaseTests):
    DIGITAR = {"action": "type_text", "value": "olá mundo", "press_enter": "true"}

    def test_toda_acao_do_action_map_esta_classificada(self):
        # uma ação nova no ACTION_MAP tem de entrar numa das listas: ou pede o ok, ou diz por que não pede
        pedem, nao_pedem = set(cs.TECLAS_PEDEM_OK), set(cs.NAO_PEDEM_OK)
        self.assertEqual(pedem | nao_pedem | cs._DANGEROUS_ACTIONS, set(cs.ACTION_MAP))
        self.assertEqual(pedem & nao_pedem, set())
        self.assertEqual((pedem | nao_pedem) & cs._DANGEROUS_ACTIONS, set())
        self.assertTrue(all(motivo.strip() for motivo in cs.NAO_PEDEM_OK.values()))
        # o que manda Enter, cola, fecha ou escreve no programa da frente pede o ok
        self.assertLessEqual({"enter", "paste", "close_app", "close_window", "close_tab", "quit_app", "save",
                              "pause_video", "refresh_page", "undo", "cut", "select_all"}, pedem)

    def test_digitar_pergunta_com_o_texto_e_a_janela_e_so_digita_com_o_ok(self):
        jarvis = JarvisFalso("digita olá mundo no bloco de notas")
        primeira = self.chamar(dict(self.DIGITAR, confirmed="yes"), jarvis)
        pergunta = 'Posso digitar "olá mundo" e apertar Enter na janela "Sem título - Bloco de Notas"?'
        self.assertIn("Not done yet", primeira)
        self.assertIn(pergunta, primeira)
        self.assertTrue(any(pergunta in log for log in jarvis.logs), jarvis.logs)  # e aparece na tela
        self.assertIn("has not answered", self.chamar(dict(self.DIGITAR, confirmed="yes"), jarvis))
        self.assertEqual(self.teclado.method_calls, [])
        jarvis.falar("ok, pode fazer")
        self.assertIn("Approved", self.chamar(dict(self.DIGITAR, confirmed="yes"), jarvis))
        self.teclado.write.assert_called_once_with("olá mundo", interval=0.03)
        self.teclado.press.assert_called_once_with("enter")
        # uma vez só: chamar de novo pergunta de novo e não digita outra vez
        self.assertIn("Not done yet", self.chamar(dict(self.DIGITAR, confirmed="yes"), jarvis))
        self.teclado.write.assert_called_once()
        self.assertEqual(jarvis.avisos, [])

    def test_ok_antes_da_pergunta_nao_digita(self):
        jarvis = JarvisFalso("digita olá mundo, ok, pode fazer")
        self.chamar(self.DIGITAR, jarvis)
        self.assertIn("has not answered", self.chamar(dict(self.DIGITAR, confirmed="yes"), jarvis))
        self.assertEqual(self.teclado.method_calls, [])

    def test_nao_cancela_a_digitacao(self):
        jarvis = JarvisFalso("digita olá mundo")
        self.chamar(self.DIGITAR, jarvis)
        jarvis.falar("não")
        self.assertIn("Cancelled", self.chamar(dict(self.DIGITAR, confirmed="yes"), jarvis))
        self.assertEqual(self.teclado.method_calls, [])

    def test_texto_mudado_depois_do_ok_nao_vale(self):
        jarvis = JarvisFalso("digita oi")
        self.chamar({"action": "type_text", "value": "oi"}, jarvis)
        jarvis.falar("ok, pode fazer")
        outro = self.chamar({"action": "type_text", "value": "oi Ana", "confirmed": "yes"}, jarvis)
        self.assertIn("Not done yet", outro)  # outro texto: pergunta de novo, com o texto novo
        self.assertIn('Posso digitar "oi Ana"', outro)
        # e voltar ao "oi" na mesma fala não vale: a pergunta do "oi Ana" ainda espera a resposta
        self.assertIn("Not done", self.chamar({"action": "type_text", "value": "oi", "confirmed": "yes"}, jarvis))
        # o Enter acrescentado depois do ok também não vale
        jarvis = JarvisFalso("digita oi")
        self.chamar({"action": "type_text", "value": "oi"}, jarvis)
        jarvis.falar("ok")
        com_enter = self.chamar({"action": "type_text", "value": "oi", "press_enter": "true"}, jarvis)
        self.assertIn('Posso digitar "oi" e apertar Enter', com_enter)
        self.assertEqual(self.teclado.method_calls, [])

    def test_outra_janela_na_frente_antes_da_confirmacao_pergunta_de_novo(self):
        jarvis = JarvisFalso("digita olá mundo")
        with patch.object(cs, "_janela_da_frente", side_effect=[JANELA, (77, "Conversa com Ana - WhatsApp")]):
            self.chamar(self.DIGITAR, jarvis)
            jarvis.falar("ok, pode fazer")
            resposta = self.chamar(dict(self.DIGITAR, confirmed="yes"), jarvis)
        self.assertIn("Not done yet", resposta)
        self.assertIn('na janela "Conversa com Ana - WhatsApp"', resposta)
        self.assertEqual(self.teclado.method_calls, [])

    def test_janela_que_muda_entre_o_ok_e_a_digitacao_nao_recebe_nada(self):
        jarvis = JarvisFalso("digita olá mundo")
        with patch.object(cs, "_janela_da_frente", side_effect=[JANELA, JANELA, (77, "WhatsApp")]):
            self.chamar(self.DIGITAR, jarvis)
            jarvis.falar("ok, pode fazer")
            self.assertIn("Approved", self.chamar(dict(self.DIGITAR, confirmed="yes"), jarvis))
        self.assertEqual(self.teclado.method_calls, [])
        self.assertEqual(len(jarvis.avisos), 1)
        self.assertIn("a janela da frente mudou", jarvis.avisos[0])

    def test_mesma_janela_com_outro_titulo_e_outra_janela(self):
        # trocar de aba no navegador muda o título e mantém o número da janela: o ok dado para a aba das
        # notas não vale na aba do WhatsApp, nem antes da confirmação nem entre o ok e a digitação
        notas, whats = (42, "Notas - Google Chrome"), (42, "WhatsApp - Google Chrome")
        args = {"action": "type_text", "value": "oi", "press_enter": "true"}
        jarvis = JarvisFalso("digita oi e aperta enter")
        with patch.object(cs, "_janela_da_frente", side_effect=[notas, whats]):
            self.assertIn('na janela "Notas - Google Chrome"', self.chamar(args, jarvis))
            jarvis.falar("ok, pode fazer")
            resposta = self.chamar(args, jarvis)
        self.assertIn("Not done yet", resposta)
        self.assertIn('na janela "WhatsApp - Google Chrome"', resposta)
        cs._pendente.clear()
        jarvis = JarvisFalso("digita oi e aperta enter")
        with patch.object(cs, "_janela_da_frente", side_effect=[notas, notas, whats]):
            self.chamar(args, jarvis)
            jarvis.falar("ok, pode fazer")
            self.assertIn("Approved", self.chamar(args, jarvis))
        self.assertEqual(self.teclado.method_calls, [])
        self.assertIn("a janela da frente mudou", jarvis.avisos[0])

    def test_marca_de_nao_salvo_no_titulo_e_a_mesma_janela(self):
        # o editor põe "*" (Bloco de Notas) ou "●" (VS Code) no começo do título ao receber texto: digitar e
        # depois apertar Enter não pode pedir o ok duas vezes para o Enter por causa disso
        jarvis = JarvisFalso("aperta enter")
        sujo, codigo = (42, "*Sem título - Bloco de Notas"), (42, "app.py - Visual Studio Code")
        # cada chamada olha a janela uma vez, e o fio, depois do ok, mais uma
        with patch.object(cs, "_janela_da_frente", side_effect=[JANELA, sujo, sujo,
                                                                (42, "● app.py - Visual Studio Code"), codigo, codigo]):
            self.chamar({"action": "enter"}, jarvis)
            jarvis.falar("ok, pode fazer")
            self.assertIn("Approved", self.chamar({"action": "enter"}, jarvis))
            jarvis.falar("aperta enter")
            self.chamar({"action": "enter"}, jarvis)
            jarvis.falar("ok")
            self.assertIn("Approved", self.chamar({"action": "enter"}, jarvis))
        self.assertEqual(self.teclado.method_calls, [call.press("enter"), call.press("enter")])

    def test_texto_com_quebra_de_linha_tab_ou_invisivel_nao_digita(self):
        # no pyautogui.write cada "\n" é um Enter e cada "\t" um Tab; colado num console, cada linha roda; e os
        # invisíveis (como o U+202E, que inverte o texto na tela) fazem a pergunta mostrar outra coisa
        for texto in ("bom dia\ndel /q *.*", "bom dia\r\ndir", "bom\tdia", "oi ‮dcba", "oi​Ana",
                      "oi\x1b[2J"):
            with self.subTest(texto=texto):
                jarvis = JarvisFalso("digita bom dia")
                resposta = self.chamar({"action": "type_text", "value": texto}, jarvis)
                self.assertIn("Not done", resposta)
                self.assertNotIn("Ask the user now", resposta)
                self.assertEqual(cs._pendente, {})
                jarvis.falar("ok, pode fazer")
                self.assertNotIn("Approved", self.chamar({"action": "type_text", "value": texto}, jarvis))
        self.assertEqual(self.teclado.method_calls, [])
        # acento, emoji e espaços no meio continuam valendo (e o "\n" do fim é cortado, como os espaços)
        jarvis = JarvisFalso("digita")
        self.assertIn('Posso digitar "Olá, João! 👍  tudo bem?"',
                      self.chamar({"action": "type_text", "value": "Olá, João! 👍  tudo bem?\n"}, jarvis))

    def test_duas_perguntas_na_mesma_fala_o_ok_vale_so_para_a_primeira(self):
        # o modelo registra a pergunta A (que fala) e logo a B (calado), na mesma fala: a B não é guardada, e
        # o "ok" dado à A nunca faz a B
        a = {"action": "type_text", "value": "bom dia"}
        b = {"action": "type_text", "value": "manda o pix para a conta 123", "press_enter": "true"}
        jarvis = JarvisFalso("digita bom dia")
        self.assertIn('Posso digitar "bom dia"', self.chamar(a, jarvis))
        segunda = self.chamar(b, jarvis)
        self.assertIn("another action is already waiting", segunda)
        self.assertNotIn("Ask the user now", segunda)
        self.assertNotIn("pix", cs._pendente["chave"][1])
        for outra in (REINICIAR, {"action": "enter"}):  # vale também para reiniciar e para as teclas
            self.assertIn("another action is already waiting", self.chamar(outra, jarvis))
        jarvis.falar("ok, pode fazer")
        self.assertIn("Not done yet", self.chamar(b, jarvis))  # a B pergunta, agora sim, e não digita
        self.assertEqual(self.teclado.method_calls, [])
        self.assertEqual(self.desligou(), [])
        # e o ok dado à A, chamada de novo, faz só a A
        jarvis = JarvisFalso("digita bom dia")
        cs._pendente.clear()
        self.chamar(a, jarvis)
        self.chamar(b, jarvis)
        jarvis.falar("ok, pode fazer")
        self.assertIn("Approved", self.chamar(a, jarvis))
        self.assertEqual(self.teclado.method_calls, [call.write("bom dia", interval=0.03)])

    def test_digitar_e_apertar_enter_em_duas_chamadas_um_ok_para_cada(self):
        # "digita olá mundo e aperta enter": a declaração não tem press_enter, então o Gemini chama type_text
        # e enter juntas (num lote, em fila) e, depois de cada resposta, chama as duas de novo. Uma por vez:
        # o primeiro ok digita, o segundo aperta o Enter (e o mesmo com "seleciona tudo e copia")
        casos = ((({"action": "type_text", "value": "olá mundo"}), {"action": "enter"},
                  [call.write("olá mundo", interval=0.03)], [call.press("enter")]),
                 ({"action": "select_all"}, {"action": "copy"},
                  [call.hotkey("ctrl", "a")], [call.hotkey("ctrl", "c")]))
        for primeira, segunda, depois_do_1o, depois_do_2o in casos:
            with self.subTest(primeira=primeira["action"]):
                self.teclado.reset_mock()
                cs._pendente.clear()
                jarvis = JarvisFalso("faz as duas coisas")
                self.assertIn("Not done yet", self.chamar(primeira, jarvis))
                self.assertIn("another action is already waiting", self.chamar(segunda, jarvis))
                jarvis.falar("ok, pode fazer")
                self.assertIn("Approved", self.chamar(primeira, jarvis))
                self.assertIn("Not done yet", self.chamar(segunda, jarvis))
                self.assertEqual(self.teclado.method_calls, depois_do_1o)
                jarvis.falar("ok, pode fazer")
                self.assertIn("Not done yet", self.chamar(primeira, jarvis))  # a primeira já foi: pergunta de novo
                cs._pendente.clear()
                self.chamar(segunda, jarvis)
                jarvis.falar("ok")
                self.assertIn("Approved", self.chamar(segunda, jarvis))
                self.assertEqual(self.teclado.method_calls, depois_do_1o + depois_do_2o)

    def test_tecla_janela_e_vezes_entram_na_chave(self):
        # o ok vale para UMA ação: outra tecla, outra janela na frente ou outro número de vezes pedem de novo
        jarvis = JarvisFalso("aperta f5")
        self.chamar({"action": "press_key", "value": "f5"}, jarvis)
        jarvis.falar("ok, pode fazer")
        outra = self.chamar({"action": "press_key", "value": "enter"}, jarvis)
        self.assertIn('Posso apertar a tecla "enter"', outra)
        self.assertEqual(self.teclado.method_calls, [])
        cs._pendente.clear()
        jarvis = JarvisFalso("aperta f5")
        with patch.object(cs, "_janela_da_frente", side_effect=[JANELA, (77, "Conversa com Ana - WhatsApp")]):
            self.chamar({"action": "press_key", "value": "f5"}, jarvis)
            jarvis.falar("ok, pode fazer")
            resposta = self.chamar({"action": "press_key", "value": "f5"}, jarvis)
        self.assertIn("Not done yet", resposta)
        self.assertIn('na janela "Conversa com Ana - WhatsApp"', resposta)
        cs._pendente.clear()
        jarvis = JarvisFalso("recarrega duas vezes")
        self.assertIn("apertar F5 (recarregar a página) 2 vezes", self.chamar({"action": "reload_n", "value": "2"}, jarvis))
        jarvis.falar("ok, pode fazer")
        dez = self.chamar({"action": "reload_n", "value": "10"}, jarvis)
        self.assertIn("Not done yet", dez)
        self.assertIn("10 vezes", dez)
        self.assertEqual(self.teclado.method_calls, [])

    def test_janela_que_nao_da_para_saber_e_titulo_comprido(self):
        jarvis = JarvisFalso("aperta enter")
        with patch.object(cs, "_janela_da_frente", return_value=(0, "")):
            resposta = self.chamar({"action": "enter"}, jarvis)
        self.assertIn("Posso apertar Enter (confirmar ou enviar) na janela da frente (não consegui ver qual é)?",
                      resposta)
        cs._pendente.clear()  # na mesma fala, outra pergunta esperaria a resposta desta
        with patch.object(cs, "_janela_da_frente", return_value=(5, "x" * 100)):
            resposta = self.chamar({"action": "enter"}, jarvis)
        self.assertIn(f'na janela "{"x" * 79}…"', resposta)
        self.assertEqual(self.teclado.method_calls, [])

    def test_cada_acao_de_teclado_pede_o_ok(self):
        acoes = [(acao, {}) for acao in sorted(cs.TECLAS_PEDEM_OK)] + sorted(TECLADO_FORA_DO_MAPA.items())
        for acao, extra in acoes:
            with self.subTest(acao=acao):
                self.teclado.reset_mock()
                jarvis = JarvisFalso(f"faz {acao}")
                args = dict(extra, action=acao, confirmed="yes")
                primeira = self.chamar(args, jarvis)
                self.assertIn("Not done yet", primeira)
                self.assertIn('na janela "Sem título - Bloco de Notas"', primeira)
                if acao in cs.TECLAS_PEDEM_OK:
                    self.assertIn(f"Posso apertar {cs.TECLAS_PEDEM_OK[acao][0]} (", primeira)
                self.assertEqual(self.teclado.method_calls, [])
                jarvis.falar("ok, pode fazer")
                self.assertIn("Approved", self.chamar(args, jarvis))
                self.assertNotEqual(self.teclado.method_calls, [], "com o ok, a ação tem de rodar")
                self.assertEqual(jarvis.avisos, [])

    def test_volume_brilho_e_os_atalhos_do_windows_nao_pedem_ok(self):
        # no Windows de verdade, o tema escuro (registro) e o volume exato (pycaw) mexeriam no PC
        falsos = patch.dict(sys.modules, {"winreg": Mock(), "comtypes": Mock(), "pycaw": Mock(),
                                          "pycaw.pycaw": Mock()})
        for acao in sorted(cs.NAO_PEDEM_OK) + ["volume_set"]:
            with self.subTest(acao=acao):
                jarvis = JarvisFalso(f"faz {acao}")
                with falsos:
                    resposta = self.chamar({"action": acao, "value": "30" if acao == "volume_set" else None},
                                           jarvis)
                self.assertNotIn("Not done", resposta)
                self.assertNotIn("Approved", resposta)
                self.assertEqual(cs._pendente, {})
                self.assertEqual(jarvis.logs, [])
        # e agem na hora: o volume pela tecla de volume, o brilho pelo Windows
        teclas = [c.args[0] for c in self.teclado.press.call_args_list]
        self.assertIn("volumeup", teclas)
        self.assertIn("volumedown", teclas)
        self.assertTrue(any(c.args and c.args[0][0] == "powershell" and "WmiSetBrightness" in " ".join(c.args[0])
                            for c in self.sistema.run.call_args_list))

    def test_sem_a_conversa_nao_digita(self):
        for args in (self.DIGITAR, {"action": "press_key", "value": "enter"}, {"action": "paste"}):
            with self.subTest(args=args):
                self.assertIn("Not done", cs.computer_settings(parameters=dict(args, confirmed="yes")))
        self.assertEqual(self.teclado.method_calls, [])
        self.assertEqual(cs._pendente, {})

    def test_janela_da_frente_pelo_windows(self):
        titulo = "Sem título - Bloco de Notas"
        usuario = self.ctypes.user32
        usuario.GetForegroundWindow.return_value = 42
        usuario.GetWindowTextLengthW.return_value = len(titulo)

        def escrever(janela, buffer, tamanho):
            buffer.value = titulo[:tamanho - 1]
            return len(titulo)

        usuario.GetWindowTextW.side_effect = escrever
        self.assertEqual(JANELA_DA_FRENTE(), (42, titulo))
        with patch.object(cs, "_OS", "Linux"):
            self.assertEqual(JANELA_DA_FRENTE(), (0, ""))
        usuario.GetForegroundWindow.side_effect = OSError("sem janela")
        self.assertEqual(JANELA_DA_FRENTE(), (0, ""))


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

    def test_digitar_pelo_gemini_e_pela_reserva_so_com_o_ok(self):
        self._ambiente()
        jarvis = self._jarvis()
        self.addCleanup(lambda: getattr(jarvis, "_loop_reserva", None)
                        and jarvis._loop_reserva.call_soon_threadsafe(jarvis._loop_reserva.stop))
        digitar = {"action": "type_text", "value": "oi", "press_enter": "true", "confirmed": "yes"}
        for chamar in (self._pelo_gemini, self._pela_reserva):
            with self.subTest(cerebro=chamar.__name__):
                self.teclado.reset_mock()
                jarvis._nova_fala("digita oi e aperta enter")
                self.assertIn('Posso digitar "oi" e apertar Enter', chamar(jarvis, digitar))
                self.assertIn("has not answered", chamar(jarvis, digitar))
                # outra ação na mesma fala não troca a pergunta que espera a resposta: o ok vale só para ela
                self.assertIn("another action is already waiting",
                              chamar(jarvis, {"action": "press_key", "value": "enter"}))
                self.assertEqual(self.teclado.method_calls, [])
                jarvis._nova_fala("ok, pode fazer")
                self.assertIn("Not done yet", chamar(jarvis, {"action": "press_key", "value": "enter"}))
                self.assertEqual(self.teclado.method_calls, [])
                cs._pendente.clear()
                jarvis._nova_fala("digita oi e aperta enter")
                chamar(jarvis, digitar)
                jarvis._nova_fala("ok, pode fazer")
                self.assertIn("Approved", chamar(jarvis, digitar))
                self.assertEqual(self.teclado.method_calls, [call.write("oi", interval=0.03), call.press("enter")])

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
