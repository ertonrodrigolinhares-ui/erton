"""Interface ULTRON: painel de automações do Jarvis (automação: salve na pasta 'automacoes').

É a "segunda cara" do Jarvis, só para as automações. Abra de três jeitos:
  - clique no botão ⚙ ULTRON (ao lado dos modos, na tela);
  - diga "Jarvis, modo Ultron" (e "modo Jarvis" para fechar);
  - pelo próprio painel, clicando em cada automação.

Cada botão do painel RODA a automação na hora, direto, sem depender do Gemini nem do Groq — então
funciona rápido e até sem internet (as que não precisam da web). O resultado aparece na tela e é
falado. Nada é publicado, enviado ou alterado: são só as automações de sempre, com as regras de sempre.

Para tirar o painel, apague este arquivo (o botão ⚙ ULTRON some junto).
"""

from __future__ import annotations

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
    ("school_tasks", "✎", "Geekie", "Atividades pendentes", {}),
]

_montado = threading.Event()


def _construir(jarvis):
    from PyQt6.QtCore import Qt, QRectF
    from PyQt6.QtGui import QPainter
    from PyQt6.QtWidgets import QGridLayout, QLabel, QPushButton, QVBoxLayout, QWidget
    import ui_stark as us

    janela = getattr(getattr(jarvis, "ui", None), "_win", None)
    tela = getattr(janela, "_tela_stark", None)
    if janela is None or tela is None:
        print("[Ultron] A tela Stark está desligada; painel não instalado.")
        return

    from main import carregar_automacoes
    disponiveis = set(carregar_automacoes().ferramentas)
    # self_diagnosis/school_tasks são ferramentas nativas do Jarvis (não da pasta), então sempre valem.
    nativas = {"self_diagnosis", "school_tasks"}
    itens = [b for b in BOTOES if b[0] in disponiveis or b[0] in nativas]

    class PainelUltron(QWidget):
        """Sobreposição escura com os botões das automações, centralizada na janela."""

        def __init__(self, pai):
            super().__init__(pai)
            self.setVisible(False)
            self._montar()

        def _montar(self):
            fora = QVBoxLayout(self)
            fora.setContentsMargins(40, 30, 40, 30)
            caixa = us.Moldura("ULTRON  ·  AUTOMAÇÕES")
            fora.addWidget(caixa)
            topo = QLabel("Clique numa automação. Ela roda na hora, sem depender da internet do cérebro.")
            topo.setFont(us.Fontes.de(10))
            topo.setStyleSheet(f"color: {us.TEXTO}; background: transparent;")
            topo.setWordWrap(True)
            caixa.corpo.addWidget(topo)
            grade = QGridLayout()
            grade.setSpacing(12)
            for i, (nome, emoji, titulo, sub, args) in enumerate(itens):
                grade.addWidget(self._botao(nome, emoji, titulo, sub, args), i // 3, i % 3)
            caixa.corpo.addLayout(grade)
            fechar = QPushButton("Fechar  ✕")
            fechar.setCursor(Qt.CursorShape.PointingHandCursor)
            fechar.setFont(us.Fontes.de(10, True, tech=True))
            fechar.setStyleSheet(
                f"QPushButton {{ color: {us.TEXTO}; background: transparent; border: 1px solid {us.AZUL_ESCURO};"
                f" border-radius: 13px; padding: 6px 18px; }} QPushButton:hover {{ color: {us.AZUL_FORTE};"
                f" border-color: {us.AZUL_FORTE}; }}")
            fechar.clicked.connect(lambda: self.abrir(False))
            caixa.corpo.addWidget(fechar, alignment=Qt.AlignmentFlag.AlignCenter)

        def _botao(self, nome, emoji, titulo, sub, args):
            b = QPushButton(f"{emoji}\n{titulo}\n{sub}")
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setMinimumHeight(96)
            b.setFont(us.Fontes.de(11, True))
            b.setStyleSheet(
                f"QPushButton {{ color: {us.TEXTO}; background: rgba(0,200,255,18); text-align: center;"
                f" border: 1px solid {us.AZUL_ESCURO}; border-radius: 12px; padding: 8px; }}"
                f"QPushButton:hover {{ color: {us.AZUL_FORTE}; border-color: {us.AZUL_FORTE};"
                f" background: rgba(0,229,255,45); }}")
            b.clicked.connect(lambda _=False, n=nome, a=args: self._rodar(n, a))
            return b

        def _rodar(self, nome, args):
            jarvis.rodar_automacao_ultron(nome, args)
            self.abrir(False)  # roda em segundo plano e fala; fecha o painel

        def paintEvent(self, _):
            p = QPainter(self)
            p.fillRect(self.rect(), us._cor(us.FUNDO, 235))  # escurece o fundo

        def abrir(self, mostrar=True):
            if mostrar:
                self.setGeometry(self.parent().rect())
                self.raise_()
            self.setVisible(bool(mostrar))

    painel = PainelUltron(tela)
    tela._painel_ultron = painel
    tela.ao_abrir_ultron = lambda: painel.abrir(not painel.isVisible())

    # comando de voz "modo ultron"/"modo jarvis" (chamado pelo main, no fio da tela)
    from core.na_tela import executar as _na_tela

    def abrir_por_voz(fechar=False):
        _na_tela(lambda: painel.abrir(not fechar))

    jarvis._abrir_ultron = abrir_por_voz
    print(f"[Ultron] Painel de automações pronto ({len(itens)} botões).")


def iniciar(jarvis) -> None:
    if _montado.is_set():
        return
    _montado.set()
    from core.na_tela import executar
    executar(lambda: _construir(jarvis))
