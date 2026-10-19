"""O LEIA-ME e o VERSAO.txt são o manual do Erton (não é programador), e o dev/ROTEIRO_DE_5_MINUTOS.md é
como ele confere cada versão: o que eles prometem precisa bater com o código. Cada teste aqui guarda uma
promessa que estava errada numa conferência."""

import importlib.util
import os
import re
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

LEIA_ME = (RAIZ / "LEIA-ME.md").read_text(encoding="utf-8")
VERSAO = (RAIZ / "VERSAO.txt").read_text(encoding="utf-8")


def _uma_linha(texto: str) -> str:
    return re.sub(r"\s+", " ", texto)


def _secao(titulo: str) -> str:
    """Texto de uma seção do LEIA-ME (do título até o próximo título do mesmo nível ou acima)."""
    inicio = LEIA_ME.index(titulo)
    nivel = len(titulo) - len(titulo.lstrip("#"))
    resto = LEIA_ME[inicio + len(titulo):]
    fim = re.search(r"^#{1,%d} " % nivel, resto, re.M)
    return _uma_linha(resto[:fim.start()] if fim else resto)


class LeiaMeBateComOCodigoTests(unittest.TestCase):
    def test_reserva_groq_executa_as_tarefas(self):
        # main.RESERVA_FERRAMENTAS_ESSENCIAIS manda e-mail, Hermes, agentes... ao Groq
        import main

        self.assertTrue({"email_control", "hermes_agent"} <= main.JarvisLive.RESERVA_FERRAMENTAS_ESSENCIAIS)
        texto = _uma_linha(LEIA_ME)
        self.assertNotIn("mas não usa as ferramentas", texto)
        self.assertIn("executa as tarefas principais", texto)
        self.assertIn("JARVIS_RESERVA_FERRAMENTAS=0", texto)

    def test_ferramentas_desligadas_estao_no_leia_me(self):
        # main.FERRAMENTAS_DESLIGADAS (Etapa 3): o que o Jarvis não faz mais tem de estar contado ao Erton
        import main

        secao = _secao("## O que o Jarvis não faz mais")
        contadas = {"send_message": "**Mensagens**", "prepare_message_reply": "**Mensagens**",
                    "check_messages": "**Mensagens**",
                    "agent_task": '**"Faça tal tarefa no PC"**',
                    "code_helper": "**O programador antigo**", "dev_agent": "**O programador antigo**",
                    "computer_control": "**Controle livre do mouse**",
                    "game_updater": "**Atualizar jogos**"}
        for nome in main.FERRAMENTAS_DESLIGADAS:
            self.assertIn(nome, contadas, f"{nome} foi desligada e o LEIA-ME não conta")
            self.assertIn(contadas[nome], secao, nome)
        self.assertIn("pasta da versão anterior", secao)
        self.assertNotIn("Gmail, Instagram, Spotify", LEIA_ME)  # o Instagram era das mensagens
        # o navegador e a lixeira ainda agem sem o "ok"; desligar e reiniciar pedem o ok desde a Etapa 4
        self.assertNotIn('nada age sem o seu "ok"', LEIA_ME)
        self.assertNotIn("hoje quem confirma é a própria IA", LEIA_ME)

    def test_digitar_e_apertar_teclas_so_com_o_ok_e_o_leia_me_conta(self):
        # o computer_control saiu, e o computer_settings (oferecido ao Gemini: "typing text on screen")
        # continua digitando e apertando teclas, Enter inclusive, mas desde a Etapa 4 só com o "ok" do
        # Erton numa fala nova depois da pergunta (test_computer_settings_aprovacao confere). O LEIA-ME e o
        # VERSAO não podem dizer que o teclado saiu, nem que ele digita sem perguntar, e têm de contar como
        # é o "ok", o que continua sem pergunta e que o navegador ainda digita sem o "ok"
        import actions.computer_settings as cs
        import main

        declaracao = next(d for d in main.get_tool_declarations() if d["name"] == "computer_settings")
        self.assertIn("typing text on screen", declaracao["description"])
        self.assertTrue(callable(cs.type_text) and callable(cs.press_key))
        self.assertLessEqual({"enter", "paste", "close_tab", "pause_video"}, set(cs.TECLAS_PEDEM_OK))
        self.assertLessEqual({"volume_up", "brightness_up", "toggle_wifi", "minimize", "open_settings"},
                             set(cs.NAO_PEDEM_OK))
        secao = _secao("## O que o Jarvis não faz mais")
        self.assertNotIn("mouse e do teclado", secao)
        self.assertNotIn("Antes ele podia digitar e apertar Enter sozinho", secao)
        self.assertNotIn('continuam funcionando, sem o seu "ok"', LEIA_ME)
        self.assertIn('digitar também, agora com o seu "ok"', secao)
        ok = _secao("## Antes de desligar, reiniciar, digitar ou apertar teclas, o Jarvis pergunta")
        for trecho in ('**só acontecem com o seu "ok"**', "Enter", "em que janela", "aparece escrita na tela",
                       '**resposta seguinte**', '**"ok, pode fazer"**', '"Não", ou qualquer outra resposta, cancela',
                       "antes da pergunta, não vale", "uma vez só", "Se a janela da frente mudar", "`shutdown /a`",
                       "Continuam sem perguntar", "volume, brilho", "abrir as Configurações",
                       "**navegador que o Jarvis controla**", 'sem esse "ok"', "não deixe uma conversa do WhatsApp"):
            self.assertIn(trecho, ok)
        novidades = _uma_linha(VERSAO[:VERSAO.index("Versão anterior")])
        for trecho in ('Desligar, reiniciar, digitar e apertar teclas só com o seu "ok"', "pergunta antes",
                       "em que janela", "resposta seguinte", '"não", ou qualquer outra resposta, cancela',
                       "antes da pergunta não vale", "continuam sem perguntar",
                       "No navegador que o Jarvis controla, ele ainda digita sem perguntar"):
            self.assertIn(trecho, novidades)
        linha = _uma_linha(VERSAO[VERSAO.index("- Ferramentas antigas"):VERSAO.index("- Reserva com outra empresa")])
        self.assertNotIn("mouse e do teclado", linha)

    def test_leia_me_conta_cada_tecla_que_pede_o_ok(self):
        # a lista do LEIA-ME parecia completa e deixava de fora 7 das ações de TECLAS_PEDEM_OK (Page Down,
        # aba nova...): o Erton levaria uma pergunta que o manual não avisou. Ação nova na lista do código
        # tem de ganhar o seu trecho aqui e no LEIA-ME
        import actions.computer_settings as cs

        no_leia_me = {
            "pause_video": "pausar o vídeo com o Espaço", "play_pause": "pausar o vídeo com o Espaço",
            "close_app": "fechar o programa", "quit_app": "fechar o programa", "close_window": "a janela ou a aba",
            "close_tab": "a janela ou a aba", "full_screen": "tela cheia", "fullscreen": "tela cheia",
            "focus_search": "ir para a barra de endereço", "refresh_page": "recarregar", "reload": "recarregar",
            "new_tab": "abrir aba nova", "next_tab": "trocar de aba", "prev_tab": "trocar de aba",
            "go_back": "voltar e avançar", "go_forward": "voltar e avançar", "zoom_in": "zoom", "zoom_out": "zoom",
            "zoom_reset": "zoom", "find_on_page": "procurar", "scroll_top": "ir para o começo ou o fim",
            "scroll_bottom": "ir para o começo ou o fim", "page_up": "(Page Up/Page Down)",
            "page_down": "(Page Up/Page Down)", "copy": "copiar", "paste": "colar", "cut": "recortar",
            "undo": "desfazer", "redo": "refazer", "save": "salvar", "select_all": "selecionar tudo",
            "enter": "(Enter, Esc", "escape": "(Enter, Esc",
        }
        self.assertEqual(set(no_leia_me), set(cs.TECLAS_PEDEM_OK))
        ok = _secao("## Antes de desligar, reiniciar, digitar ou apertar teclas, o Jarvis pergunta")
        lista = ok[:ok.index("1. Você pede")]
        for acao, trecho in no_leia_me.items():
            self.assertIn(trecho, lista, acao)
        self.assertIn("ir para a barra de endereço", (RAIZ / "core" / "SEGURANCA.md").read_text(encoding="utf-8"))

    def test_leia_me_conta_o_ok_falado_uma_pergunta_por_vez_e_a_aba(self):
        # o ok DIGITADO no campo do Jarvis põe a janela do Jarvis na frente: para digitar ou apertar teclas,
        # ele pergunta de novo, agora com a janela do Jarvis (test_computer_settings_aprovacao); duas ações
        # pedidas juntas vão uma de cada vez; outra aba do navegador é outra janela; e texto de várias linhas
        # não é digitado
        ok = _secao("## Antes de desligar, reiniciar, digitar ou apertar teclas, o Jarvis pergunta")
        for trecho in ('responda **falando**', "campo do Jarvis", 'responder "não"', "uma de cada vez",
                       "outra aba do navegador", "numa linha só"):
            self.assertIn(trecho, ok)
        novidades = _uma_linha(VERSAO[:VERSAO.index("Versão anterior")])
        for trecho in ("responda falando", "uma de cada vez", "numa linha só"):
            self.assertIn(trecho, novidades)
        roteiro = _uma_linha((RAIZ / "dev" / "ROTEIRO_DE_5_MINUTOS.md").read_text(encoding="utf-8"))
        digitar = roteiro[roteiro.index('**Digitar com "ok":**'):roteiro.index("**F2:**")]
        self.assertIn("responda falando", digitar)

    def test_o_x_da_janela_so_esconde_o_jarvis(self):
        secao = _secao("## Tela e cérebro separados")
        self.assertNotIn("Fechando a janela, o cérebro fecha junto", secao)
        self.assertIn("continua ouvindo", secao)
        self.assertIn("Quit JARVIS", secao)
        claude = _secao("## Claude como chefe de tarefas")
        self.assertNotIn("valem quando você reabrir o Jarvis", claude)
        self.assertIn("Quit JARVIS", claude)

    def test_modo_privado_avisa_da_voz_da_microsoft(self):
        # main._falar_reserva manda o texto para a voz da internet sem JARVIS_VOZ_PRIVADA=1
        secao = _secao("### Modo privado por voz")
        self.assertNotIn("nada mais vai para a nuvem", secao)
        self.assertIn("JARVIS_VOZ_PRIVADA=1", secao)
        linha = _uma_linha(VERSAO[VERSAO.index("- Modo privado por voz"):VERSAO.index("- Vídeos com IA")])
        self.assertNotIn("(nada vai para a nuvem)", linha)
        self.assertIn("JARVIS_VOZ_PRIVADA=1", linha)

    def test_selo_do_modo_privado_so_na_tela_azul(self):
        secao = _secao("### Modo privado por voz")
        self.assertIn("tela antiga", secao)
        self.assertIn("🔒 Modo privado ligado", secao)  # a linha que core/ponte.py escreve ao trocar

    def test_trocar_a_chave_nao_manda_apagar_o_env(self):
        # o iniciador recria o .env só com a chave, o Groq e a cidade: o modo privado e o Hermes somem
        secao = _secao("## Trocar a chave do Gemini")
        self.assertNotIn("apague o arquivo", secao)
        self.assertIn("Testar chave do Gemini", secao)
        self.assertIn("Não apague o `.env`", secao)
        for perdido in ("modo privado", "Hermes"):
            self.assertIn(perdido, secao)

    def test_travas_do_claude_contam_o_modo_de_mudar_o_codigo(self):
        # planejar() lê e _aplicar_e_conferir() lê e muda a pasta do programa do Jarvis
        travas = _uma_linha(LEIA_ME[LEIA_ME.index("Travas (no código"):LEIA_ME.index("No **modo privado** nada vai para o Claude")])
        self.assertNotIn("fora das pastas dele, não lê nada", travas)
        self.assertIn("Nas **tarefas**", travas)
        self.assertIn("pasta do programa do Jarvis", travas)
        linha = _uma_linha(VERSAO[VERSAO.index("- Claude como chefe"):VERSAO.index("- Modo privado por voz")])
        self.assertIn("Nas tarefas, ele só escreve", linha)
        self.assertIn("lê e muda a pasta do programa", linha)

    def test_instaladores_mandam_fechar_de_verdade_antes_de_abrir(self):
        # o X só esconde o Jarvis perto do relógio, e ele não relê o .env: depois do "Instalar Gemma 4",
        # o Jarvis antigo continuava no Gemini, ouvindo, ao lado do novo (conversa de cliente na nuvem)
        for nome in ("gemma/instalar_gemma.ps1", "gemma/voltar_gemini.ps1", "claude/instalar_claude.ps1",
                     "hermes/instalar_hermes.ps1"):
            texto = (RAIZ / nome).read_text(encoding="ascii")  # .ps1 só em ASCII (PowerShell 5.1)
            final = texto[texto.rindex("Pronto!" if "Pronto!" in texto else "voltou a usar o Gemini"):]
            self.assertIn("Quit JARVIS", final, nome)
            self.assertNotIn("Feche e abra o Jarvis de novo", texto, nome)
        gemma = _secao("## Cérebro Gemma 4 no seu PC")
        passo = gemma[gemma.index("2. "):gemma.index("Para voltar ao Gemini")]
        self.assertIn("Quit JARVIS", passo)
        self.assertNotIn("Abra o **\"Iniciar Jarvis Ultron\"** normalmente", gemma)

    def test_voz_privada_na_reserva_nao_promete_que_nada_sai_do_pc(self):
        # JARVIS_VOZ_PRIVADA=1 só troca a voz: na reserva, a voz do Erton e os pedidos seguem para o Groq
        linha = next(l for l in LEIA_ME.splitlines() if l.startswith("| `JARVIS_VOZ_PRIVADA"))
        self.assertNotIn("voz do Windows: nada sai do PC", linha)
        self.assertIn("Groq", linha)

    def test_observacoes_nao_contam_as_71_falhas_que_sairam(self):
        # a Etapa 2 tirou os testes que cobravam telas do JARVIS-OS: o que sobra fica anotado na lista
        secao = _secao("## Observações")
        self.assertNotIn("71 falhas", secao)
        self.assertNotIn("não mudaram nenhum resultado", secao)
        self.assertIn("antes-da-reorganizacao", secao)
        for arquivo in ("tests/dados/falhas_conhecidas.txt", "dev/conferir_testes.py"):
            self.assertIn(arquivo, secao)
            self.assertTrue((RAIZ / arquivo).exists(), arquivo)


class FecharNoXTests(unittest.TestCase):
    def test_aviso_da_bandeja_em_portugues_diz_que_continua_ouvindo(self):
        import ui

        bandeja = MagicMock()
        bandeja.isVisible.return_value = True
        janela = SimpleNamespace(_tray=bandeja, _force_quit=False, _vision_preview=None, hide=MagicMock())
        evento = MagicMock()
        ui.MainWindow.closeEvent(janela, evento)
        evento.ignore.assert_called_once()
        janela.hide.assert_called_once()
        titulo, texto = bandeja.showMessage.call_args[0][:2]
        self.assertIn("continua ouvindo", texto)
        self.assertIn("Quit JARVIS", texto)
        self.assertNotIn("Running in background", titulo + texto)


class RoteiroBateComOCodigoTests(unittest.TestCase):
    def test_reiniciar_com_nao_e_digitar_com_ok_no_roteiro(self):
        # o teste de PC da Etapa 4: "reinicia o computador" -> pergunta -> "não" -> nada; e digitar no Bloco
        # de Notas -> pergunta com o texto e a janela -> "ok" -> digita (o código: _pedir_ok, shutdown /t 10)
        import inspect

        import actions.computer_settings as cs

        roteiro = _uma_linha((RAIZ / "dev" / "ROTEIRO_DE_5_MINUTOS.md").read_text(encoding="utf-8"))
        reiniciar = roteiro[roteiro.index('**Reiniciar com "não":**'):roteiro.index('**Digitar com "ok":**')]
        self.assertIn('**"Jarvis, reinicia o computador"**', reiniciar)
        self.assertIn('responda **"não"**', reiniciar)
        self.assertIn("Nada acontece", reiniciar)
        self.assertIn("`shutdown /a`", reiniciar)
        self.assertIn('"shutdown", "/r", "/t", "10"', inspect.getsource(cs.restart_computer))
        digitar = roteiro[roteiro.index('**Digitar com "ok":**'):roteiro.index("**F2:**")]
        self.assertIn("**Bloco de Notas**", digitar)
        self.assertIn('**"Jarvis, digita olá mundo"**', digitar)
        self.assertIn("o nome da janela", digitar)
        self.assertIn('Responda **"ok, pode fazer"**', digitar)
        self.assertIn("uma vez só", digitar)
        self.assertIn("Se ele digitar sem perguntar", digitar)
        from core.hermes_ponte import usuario_aprovou

        self.assertTrue(usuario_aprovou("ok, pode fazer"))  # a resposta do roteiro vale como "ok"
        self.assertFalse(usuario_aprovou("não"))

    def test_painel_ultron_pelos_botoes_que_existem_na_tela_azul(self):
        # na tela azul (a padrão) a cena cobre a tela antiga inteira: o botão ⚙ ULTRON fica escondido, e
        # procurando por ele o Erton acharia que a versão quebrou
        roteiro = _uma_linha((RAIZ / "dev" / "ROTEIRO_DE_5_MINUTOS.md").read_text(encoding="utf-8"))
        passo = roteiro[roteiro.index("**Painel Ultron:**"):roteiro.index("**Vídeo com")]
        self.assertNotIn("clique no botão **⚙ ULTRON**", passo)
        self.assertIn("**⚙ ULTRON** (ele só aparece na tela antiga, a do F2)", passo)
        self.assertIn('BotaoModo("⚙  ULTRON"', (RAIZ / "ui_stark.py").read_text(encoding="utf-8"))
        orbe = (RAIZ / "ui_orbe.py").read_text(encoding="utf-8")
        self.assertNotIn("⚙", orbe)
        # os nomes que o passo manda procurar são os da tela
        spec = importlib.util.spec_from_file_location("pu_roteiro", RAIZ / "automacoes" / "painel_ultron.py")
        painel = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(painel)
        self.assertIn(("⏰", "Meus lembretes"), [(emoji, titulo) for _n, emoji, titulo, *_ in painel.BOTOES])
        self.assertIn("**⏰ Meus lembretes**", passo)
        self.assertEqual(painel.CURTOS["Meus lembretes"], "Lembretes")
        self.assertIn("**⏰ Lembretes**", passo)
        self.assertIn('Vidro("Ultron · automações"', orbe)
        self.assertIn("**Ultron · automações**", passo)
        self.assertIn('"☰  PAINÉIS"', orbe)
        self.assertIn("**☰ PAINÉIS**", passo)

    def test_mensagem_tem_de_ser_recusada_no_pc(self):
        # Etapa 3: as ferramentas de mensagem saíram, mas o computer_settings e o navegador ainda digitam e
        # apertam Enter. No Gemini ao vivo, a recusa só depende do prompt, e só se confere no PC (o teste de
        # PC da Etapa 3 no plano). Com o WhatsApp fechado: se a trava falhar, o "oi" não sai de verdade
        import main

        self.assertLessEqual({"send_message", "prepare_message_reply", "check_messages"}, set(main.FERRAMENTAS_DESLIGADAS))
        roteiro = _uma_linha((RAIZ / "dev" / "ROTEIRO_DE_5_MINUTOS.md").read_text(encoding="utf-8"))
        passo = roteiro[roteiro.index("**Mensagem"):roteiro.index("**F2:**")]
        self.assertIn('**"Jarvis, manda oi no WhatsApp para a Ana"**', passo)
        self.assertIn("**feche o WhatsApp**", passo)
        self.assertIn("não envia mensagens", passo)
        self.assertIn("nada pode ser digitado", passo)
        self.assertIn("Quit JARVIS", passo)


if __name__ == "__main__":
    unittest.main()
