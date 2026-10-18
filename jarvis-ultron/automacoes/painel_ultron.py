"""Interface ULTRON: painel de automações do Jarvis (automação: salve na pasta 'automacoes').

É a "segunda cara" do Jarvis, só para as automações. Abra de três jeitos:
  - clique no botão ⚙ ULTRON (ao lado dos modos, na tela);
  - diga "Jarvis, modo Ultron" (e "modo Jarvis" para fechar);
  - pelo próprio painel, clicando em cada automação.

Cada botão do painel RODA a automação na hora, direto, sem depender do Gemini nem do Groq — então
funciona rápido e até sem internet (as que não precisam da web). O resultado aparece na tela e é
falado. Nada é publicado, enviado ou alterado: são só as automações de sempre, com as regras de sempre.

Além das automações fixas, cada AGENTE ligado (no "Ativar Agentes", na pasta do Jarvis) vira um
botão: ele pede ao Claude para rodar aquele agente. O painel se atualiza toda vez que abre.

Para tirar o painel, apague este arquivo (o botão ⚙ ULTRON e o quadro "Ultron · automações" da
lateral somem junto).
"""

from __future__ import annotations

# Desenha na janela: com tela e cérebro separados, roda no programa da tela.
NA_TELA = True

import threading

# Botões do painel: (nome_da_ferramenta, emoji, título, subtítulo, argumentos).
# Só entram os que valem um clique (sem digitar nada). Só aparece o que estiver instalado.
BOTOES = [
    ("self_diagnosis", "✚", "Autodiagnóstico", "Vê o que está com defeito", {}),
    ("self_repair", "🔧", "Autoconserto", "Conserta sozinho o que é seguro", {}),
    ("pc_protection", "🛡️", "Proteção do PC", "Antivírus, firewall, updates", {}),
    ("wifi_watch", "📶", "Vigia do Wi-Fi", "Quem está na rede + senha", {"action": "both"}),
    ("spoken_reminders", "⏰", "Meus lembretes", "O que está marcado", {"action": "list"}),
    ("saved_routines", "▶", "Minhas rotinas", "As rotinas salvas", {"action": "list"}),
    ("external_memory_drive", "💾", "Memória no HD", "Como está o backup", {"action": "status"}),
]

# Nome curto para a lateral da tela do orbe (coluna estreita: os nomes longos eram cortados)
CURTOS = {"Autodiagnóstico": "Diagnóstico", "Proteção do PC": "Proteção PC", "Vigia do Wi-Fi": "Vigia Wi-Fi",
          "Meus lembretes": "Lembretes", "Minhas rotinas": "Rotinas", "Memória no HD": "Backup HD"}

_montado = threading.Event()


def _construir(jarvis):
    from PyQt6.QtCore import Qt, QRectF
    from PyQt6.QtGui import QFont, QPainter
    from PyQt6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget
    import ui_stark as us

    janela = getattr(getattr(jarvis, "ui", None), "_win", None)
    tela = getattr(janela, "_tela_stark", None)
    if janela is None or tela is None:
        print("[Ultron] A tela Stark está desligada; painel não instalado.")
        return

    from main import carregar_automacoes
    disponiveis = set(carregar_automacoes().ferramentas)
    # self_diagnosis é ferramenta nativa do Jarvis (não da pasta), então sempre vale.
    nativas = {"self_diagnosis"}
    fixos = [b for b in BOTOES if b[0] in disponiveis or b[0] in nativas]

    def itens_atuais():
        """As automações fixas + um botão por agente ligado (lido de novo a cada abertura)."""
        try:
            from core import agentes
            dos_agentes = agentes.botoes_dos_ligados() if "claude_task" in disponiveis else []
        except Exception as erro:
            print(f"[Ultron] Não consegui ler os agentes ligados: {erro}")
            dos_agentes = []
        return fixos + dos_agentes

    def curto(titulo, args):
        from core.agentes import NOMES_CURTOS
        return CURTOS.get(titulo) or NOMES_CURTOS.get((args or {}).get("agent", ""), titulo[:12])

    itens = itens_atuais()

    class PainelUltron(QWidget):
        """Sobreposição escura com os botões das automações, centralizada na janela."""

        def __init__(self, pai):
            super().__init__(pai)
            self.setVisible(False)
            self._montar()

        def _montar(self):
            # Como a tela limpa do vídeo: um bloco no centro, por cima do anel (que aparece atrás)
            fora = QVBoxLayout(self)
            fora.setContentsMargins(24, 24, 24, 24)
            fora.addStretch(1)
            self._bloco = QWidget()
            self._bloco.setMaximumWidth(860)
            coluna = QVBoxLayout(self._bloco)
            coluna.setSpacing(10)
            self._sobre = QLabel("U L T R O N")
            self._titulo = QLabel("Automações")
            self._dica = QLabel("Toque numa automação: ela roda na hora, sem depender da internet do cérebro.")
            for rotulo in (self._sobre, self._titulo, self._dica):
                rotulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
                rotulo.setWordWrap(True)
                coluna.addWidget(rotulo)
            coluna.addSpacing(8)
            self._grade = QGridLayout()
            self._grade.setSpacing(12)
            self._botoes = []
            coluna.addLayout(self._grade)
            self._sem_agentes = QLabel('Ligue agentes no "Ativar Agentes" (pasta do Jarvis) e eles aparecem aqui.')
            self._sem_agentes.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._sem_agentes.setWordWrap(True)
            coluna.addWidget(self._sem_agentes)
            coluna.addSpacing(10)
            self._itens = []
            self._preencher(itens)
            self._fechar = QPushButton("Fechar  ✕")
            self._fechar.setCursor(Qt.CursorShape.PointingHandCursor)
            self._fechar.clicked.connect(lambda: self.abrir(False))
            coluna.addWidget(self._fechar, alignment=Qt.AlignmentFlag.AlignCenter)
            self._rodape = QLabel('ou diga "modo Jarvis"')
            self._rodape.setAlignment(Qt.AlignmentFlag.AlignCenter)
            coluna.addWidget(self._rodape)
            linha = QHBoxLayout()
            linha.addStretch(1)
            linha.addWidget(self._bloco, 10)
            linha.addStretch(1)
            fora.addLayout(linha)
            fora.addStretch(1)
            self._tingir()

        def _preencher(self, novos):
            """Monta (ou remonta) os botões: fixos + agentes ligados."""
            while self._grade.count():
                w = self._grade.takeAt(0).widget()
                if w is not None:
                    w.setParent(None)
                    w.deleteLater()
            self._botoes = []
            self._itens = list(novos)
            muitos = len(novos) > 8
            colunas = 4 if len(novos) > 6 else 3
            for i, (nome, emoji, titulo, sub, args) in enumerate(novos):
                self._grade.addWidget(self._botao(nome, emoji, titulo, sub, args, compacto=muitos),
                                      i // colunas, i % colunas)
            self._sem_agentes.setVisible(not any(n == "claude_task" for n, *_ in novos))
            if hasattr(self, "_fechar"):
                self._tingir()

        def _botao(self, nome, emoji, titulo, sub, args, compacto=False):
            b = QPushButton()
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setMinimumHeight(74 if compacto else 108)
            b.setToolTip(f"{titulo}: {sub}")
            caixa = QVBoxLayout(b)
            caixa.setContentsMargins(10, 10, 10, 10)
            caixa.setSpacing(3)
            partes = []
            partes_do_botao = ((emoji, 15, False), (titulo, 10, True)) if compacto else \
                ((emoji, 18, False), (titulo, 10.5, True), (sub, 8.5, False))
            for texto, tamanho, negrito in partes_do_botao:
                l = QLabel(texto)
                l.setAlignment(Qt.AlignmentFlag.AlignCenter)
                l.setWordWrap(True)
                l.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
                l.setProperty("tamanho", (tamanho, negrito))
                caixa.addWidget(l)
                partes.append(l)
            b.clicked.connect(lambda _=False, n=nome, a=args: self._rodar(n, a))
            self._botoes.append((b, partes))
            return b

        def _tingir(self):
            """Cores do momento (azul no Jarvis, laranja no Ultron) e fontes da tela do orbe."""
            import ui_orbe as uo

            texto, texto2, ciano = uo.cor(uo.TEXTO).name(), uo.cor(uo.TEXTO2).name(), uo.cor(uo.CIANO).name()
            self._sobre.setFont(uo.fonte(uo.MONO, 9, QFont.Weight.Bold, 6))
            self._sobre.setStyleSheet(f"color:{ciano}; background: transparent;")
            self._titulo.setFont(uo.fonte(uo.SANS, 24, QFont.Weight.Bold))
            self._titulo.setStyleSheet(f"color:{texto}; background: transparent;")
            for l in (self._dica, self._rodape, self._sem_agentes):
                l.setFont(uo.fonte(uo.SANS, 9.5))
                l.setStyleSheet(f"color:{texto2}; background: transparent;")
            for b, partes in self._botoes:
                b.setStyleSheet(
                    f"QPushButton {{ background: {uo._rgba('#041438', 170)}; border:1px solid {uo._rgba('#3a78d8', 120)};"
                    f" border-radius:14px; }} QPushButton:hover {{ background: {uo._rgba('#00e5ff', 40)};"
                    f" border-color:{ciano}; }}")
                for l in partes:
                    tamanho, negrito = l.property("tamanho")
                    l.setFont(uo.fonte(uo.SANS, tamanho, QFont.Weight.Bold if negrito else QFont.Weight.Normal))
                    tom = texto if negrito or tamanho > 12 else texto2
                    l.setStyleSheet(f"color:{tom}; background: transparent;")
            self._fechar.setFont(uo.fonte(uo.MONO, 9, QFont.Weight.Bold, 2))
            self._fechar.setStyleSheet(
                f"QPushButton {{ color:{texto}; background: {uo._rgba('#041438', 150)};"
                f" border:1px solid {uo._rgba('#3a78d8', 120)}; border-radius:15px; padding:7px 22px; }}"
                f" QPushButton:hover {{ color:{ciano}; border-color:{ciano}; }}")

        def _rodar(self, nome, args):
            jarvis.rodar_automacao_ultron(nome, args)
            self.abrir(False)  # roda em segundo plano e fala; fecha o painel

        def paintEvent(self, _):
            p = QPainter(self)
            p.fillRect(self.rect(), us._cor(us.FUNDO, 175))  # escurece, mas o anel continua aparecendo atrás

        def abrir(self, mostrar=True):
            if mostrar:
                novos = itens_atuais()
                if [(n, a) for n, _e, _t, _s, a in novos] != [(n, a) for n, _e, _t, _s, a in self._itens]:
                    self._preencher(novos)
                    encaixar_na_cena(novos)
                # Na tela do orbe (o padrão), a cena cobre a tela Stark inteira: o painel tem de abrir
                # por cima da cena, senão só a cor muda e o painel (e o "Fechar") ficam escondidos.
                orbe = getattr(janela, "_orbe", None)
                cena = getattr(orbe, "cena", None) if orbe is not None else None
                na_cena = cena is not None and getattr(cena, "ativa", False) and not cena.isHidden()
                pai = cena if na_cena else tela
                if self.parentWidget() is not pai:
                    self.setParent(pai)
                self.setGeometry(pai.rect())
                self.raise_()
            self.setVisible(bool(mostrar))
            # Ultron ligado = a interface inteira fica LARANJA; Jarvis = volta ao azul.
            try:
                import ui_orbe
                ui_orbe.definir_ultron(janela, bool(mostrar))
                if mostrar:
                    self._tingir()  # já com o laranja do Ultron
            except Exception as erro:
                print(f"[Ultron] Não consegui trocar a cor: {erro}")

    painel = PainelUltron(tela)
    tela._painel_ultron = painel
    tela.ao_abrir_ultron = lambda: painel.abrir(not painel.isVisible())
    botao = getattr(tela, "botao_ultron", None)
    if botao is not None:
        botao.setVisible(True)  # o botão ⚙ ULTRON só aparece com o painel instalado

    # comando de voz "modo ultron"/"modo jarvis" (chamado pelo main, no fio da tela)
    from core.na_tela import executar as _na_tela

    def abrir_por_voz(fechar=False):
        _na_tela(lambda: painel.abrir(not fechar))

    jarvis._abrir_ultron = abrir_por_voz

    # Também coloca os botões na lateral da tela do orbe (a tela cheia do vídeo).
    from PyQt6.QtCore import QTimer

    acao = lambda n, a: jarvis.rodar_automacao_ultron(n, a)
    tentativas = {"n": 0}

    def encaixar_na_cena(lista=None):
        lista = itens if lista is None else lista
        itens_lateral = [(nome, emoji, curto(titulo, args), args, f"{titulo}: {sub}")
                         for (nome, emoji, titulo, sub, args) in lista]
        orbe = getattr(janela, "_orbe", None)
        cena = getattr(orbe, "cena", None) if orbe is not None else None
        if cena is not None and hasattr(cena, "montar_botoes_ultron"):
            cena.montar_botoes_ultron(itens_lateral, acao)
            print("[Ultron] Botões colocados na lateral da tela do orbe.")
            return
        tentativas["n"] += 1
        if tentativas["n"] <= 30:  # a cena pode demorar a montar; tenta por ~15s
            QTimer.singleShot(500, lambda: encaixar_na_cena(lista))

    encaixar_na_cena()
    print(f"[Ultron] Painel de automações pronto ({len(itens)} botões).")


def iniciar(jarvis) -> None:
    if _montado.is_set():
        return
    _montado.set()
    from core.na_tela import executar
    executar(lambda: _construir(jarvis))
