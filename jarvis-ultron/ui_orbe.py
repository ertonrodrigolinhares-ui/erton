"""Jarvis Ultron: visual "Orbe" (no estilo do vídeo do J.A.R.V.I.S.).

- Cena: a tela inteira vira um ambiente azul com grade. O anel de energia fica
  no centro e painéis de vidro flutuam dos lados (voz, sistema, atividade, rede
  e o canal de conversa, com campo para digitar).
- Orbe: anel de fios de luz entrelaçados. Cresce e brilha com a voz e mostra no
  topo o estado em português (FALANDO, OUVINDO, PENSANDO...).
- Biometria: no "bom dia", a câmera abre dentro do anel e procura um rosto.
  Tudo local: nenhuma imagem é gravada nem enviada.
- Briefing matinal: um cartão central mostra as etapas (agenda, e-mails,
  notícias, clima, prioridades) e depois vêm os cartões do dia.

Configurações (.env):
- JARVIS_VISUAL=classico  volta para a esfera antiga (e a tela antiga).
- JARVIS_CENA=0           mantém o anel, mas dentro da tela antiga.
- JARVIS_BIOMETRIA=0      pula a câmera no "bom dia".
- JARVIS_NOME=Erton       nome usado na saudação.
Tecla F2 alterna entre a cena e a tela antiga.
"""

from __future__ import annotations

import datetime as dt
import json
import math
import os
import random
import re
import socket
import threading
import time
import unicodedata
from collections import deque
from pathlib import Path

from PyQt6.QtCore import QEasingCurve, QEvent, QObject, QPointF, QPropertyAnimation, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import (QBrush, QColor, QFont, QImage, QKeySequence, QLinearGradient, QPainter, QPainterPath, QPen,
                         QPixmap, QRadialGradient, QShortcut)
from PyQt6.QtWidgets import (QGraphicsOpacityEffect, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout,
                             QWidget)

AZUL = "#2b7fff"        # fio principal
CIANO = "#29d4ff"       # brilho
GELO = "#d8f6ff"        # miolo dos fios
TEXTO = "#e8f8ff"
TEXTO2 = "#8fc3e6"
APAGADO = "#4f7fa8"
VERDE = "#2dffa8"
AMBAR = "#ffc14d"
VERMELHO = "#ff5a6e"

MONO = "JetBrains Mono"
SANS = "Space Grotesk"

ESTADOS_PT = {
    "SPEAKING": "FALANDO",
    "LISTENING": "OUVINDO",
    "THINKING": "PENSANDO",
    "PROCESSING": "EXECUTANDO",
    "INITIALISING": "INICIANDO",
    "MUTED": "MUDO",
}


def ligado() -> bool:
    return os.environ.get("JARVIS_VISUAL", "orbe").strip().lower() not in ("classico", "clássico", "0", "off")


def cena_ligada() -> bool:
    return os.environ.get("JARVIS_CENA", "1").strip().lower() not in ("0", "nao", "não", "off")


def cor(h: str, a: float = 255) -> QColor:
    c = QColor(h)
    c.setAlpha(max(0, min(255, int(a))))
    return c


def fonte(familia: str, pt: float, peso=QFont.Weight.Normal, espaco: float = 0) -> QFont:
    f = QFont(familia)
    f.setPointSizeF(pt)
    f.setWeight(peso)
    if familia == MONO:
        f.setStyleHint(QFont.StyleHint.Monospace)
    if espaco:
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, espaco)
    return f


def _sem_acento(texto: str) -> str:
    return unicodedata.normalize("NFD", texto).encode("ascii", "ignore").decode().lower()


def pintar_fundo(p: QPainter, W: float, H: float) -> None:
    """Azul da sala escura com grade, como no monitor do vídeo."""
    cx, cy = W / 2, H / 2
    fundo = QRadialGradient(QPointF(cx, cy * 0.95), max(W, H) * 0.8)
    fundo.setColorAt(0.0, cor("#0d3f99"))
    fundo.setColorAt(0.45, cor("#082c74"))
    fundo.setColorAt(1.0, cor("#031444"))
    p.fillRect(QRectF(0, 0, W, H), fundo)
    passo = max(34, int(min(W, H) / 13))
    p.setPen(QPen(cor("#3a78d8", 55), 1))
    x = cx % passo
    while x < W:
        p.drawLine(QPointF(x, 0), QPointF(x, H))
        x += passo
    y = cy % passo
    while y < H:
        p.drawLine(QPointF(0, y), QPointF(W, y))
        y += passo
    # vinheta nas bordas
    vin = QRadialGradient(QPointF(cx, cy), max(W, H) * 0.75)
    vin.setColorAt(0.6, cor("#000000", 0))
    vin.setColorAt(1.0, cor("#000814", 150))
    p.fillRect(QRectF(0, 0, W, H), vin)


# ---------------------------------------------------------------- orbe

class Orbe:
    """Desenha o anel de fios de energia dentro do HudCanvas."""

    FIOS = 18
    PONTOS = 160

    def __init__(self):
        rnd = random.Random(11)
        self.fios = []
        for _ in range(self.FIOS):
            harm = [
                (2, rnd.uniform(0.03, 0.08), rnd.uniform(0, math.tau), rnd.uniform(-0.35, 0.35)),
                (3, rnd.uniform(0.02, 0.06), rnd.uniform(0, math.tau), rnd.uniform(-0.5, 0.5)),
                (rnd.randint(4, 6), rnd.uniform(0.008, 0.025), rnd.uniform(0, math.tau), rnd.uniform(-0.9, 0.9)),
            ]
            self.fios.append({
                "harm": harm,
                "raio": rnd.uniform(0.84, 1.12),
                "achat": rnd.uniform(0.82, 1.0),
                "giro": rnd.uniform(0, math.pi),
                "vel_giro": rnd.uniform(-0.18, 0.18),
                "largura": rnd.uniform(0.7, 1.4),
                "fase_brilho": rnd.uniform(0, math.tau),
                "falha": rnd.uniform(0, math.tau),   # trecho mais apagado, dá aspecto de fio solto
            })
        self.faiscas = [(rnd.randrange(self.FIOS), rnd.uniform(0, math.tau), rnd.uniform(0.2, 0.6)) for _ in range(14)]
        self._inicio = time.time()

    def _ponto(self, fio: dict, ang: float, t: float, R: float, cx: float, cy: float, agito: float) -> QPointF:
        r = fio["raio"]
        for k, amp, fase, vel in fio["harm"]:
            r += amp * agito * math.sin(k * ang + fase + t * vel)
        x = math.cos(ang) * r
        y = math.sin(ang) * r * fio["achat"]
        g = fio["giro"] + t * fio["vel_giro"] * 0.25
        return QPointF(cx + (x * math.cos(g) - y * math.sin(g)) * R, cy + (x * math.sin(g) + y * math.cos(g)) * R)

    def pintar(self, hud, p: QPainter) -> None:
        W, H = hud.width(), hud.height()
        cx, cy = W / 2, H / 2
        fw = min(W, H)
        t = time.time() - self._inicio
        voz = getattr(hud, "_nivel_suave", 0.0)
        falando = bool(hud.speaking) and not hud.muted
        pensando = hud.state in ("THINKING", "PROCESSING")
        leve = getattr(hud, "_render_stride", 1) > 1
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        pintar_fundo(p, W, H)

        R = fw * 0.34 * (1.0 + 0.08 * voz)
        agito = 1.0 + (1.2 * voz if falando else 0.0) + (0.35 if pensando else 0.0)
        tt = t * (1.0 + (1.0 if pensando else 0.0) + (0.7 * voz if falando else 0.0))
        brilho = 0.75 + 0.25 * (voz if falando else 0.0) + (0.1 if pensando else 0.0)
        if hud.muted:
            brilho *= 0.45

        # Luz difusa atrás do anel
        halo = QRadialGradient(QPointF(cx, cy), R * 1.35)
        halo.setColorAt(0.0, cor("#1d6dff", 30 * brilho))
        halo.setColorAt(0.75, cor("#1d6dff", 55 * brilho))
        halo.setColorAt(1.0, cor("#1d6dff", 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(halo))
        p.drawEllipse(QPointF(cx, cy), R * 1.35, R * 1.35)

        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
        passo = math.tau / (self.PONTOS // (2 if leve else 1))
        fios = self.fios[:: 2 if leve else 1]
        cams = []
        for fio in fios:
            cam = QPainterPath()
            ang = 0.0
            cam.moveTo(self._ponto(fio, ang, tt, R, cx, cy, agito))
            while ang < math.tau:
                ang += passo
                cam.lineTo(self._ponto(fio, ang, tt, R, cx, cy, agito))
            cam.closeSubpath()
            cams.append((cam, fio, 0.55 + 0.45 * math.sin(t * 1.1 + fio["fase_brilho"])))

        p.setBrush(Qt.BrushStyle.NoBrush)
        camadas = [(9.0, CIANO, 10), (3.5, AZUL, 40), (1.6, CIANO, 120), (0.7, GELO, 120)]
        if leve:
            camadas = camadas[1:]
        for largura, tom, alfa in camadas:
            for cam, fio, pulso in cams:
                pen = QPen(cor(tom, alfa * brilho * pulso), largura * fio["largura"])
                pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                p.setPen(pen)
                p.drawPath(cam)

        for i, ang0, vel in self.faiscas:
            fio = self.fios[i]
            pt = self._ponto(fio, ang0 + tt * vel, tt, R, cx, cy, agito)
            g = QRadialGradient(pt, 14)
            g.setColorAt(0.0, cor("#ffffff", 190 * brilho))
            g.setColorAt(0.25, cor(CIANO, 110 * brilho))
            g.setColorAt(1.0, cor(CIANO, 0))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(g))
            p.drawEllipse(pt, 14, 14)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

        # Estado no topo, com linha pontilhada embaixo
        estado = "MUDO" if hud.muted else ("FALANDO" if hud.speaking else ESTADOS_PT.get(hud.state, hud.state))
        topo = max(16.0, cy - R * 1.42)
        p.setFont(fonte(MONO, 11, QFont.Weight.Bold, 6))
        p.setPen(QPen(cor(CIANO, 235), 1))
        p.drawText(QRectF(0, topo, W, 22), Qt.AlignmentFlag.AlignCenter, estado)
        p.setPen(Qt.PenStyle.NoPen)
        for i in range(-44, 45):
            a = 150 * (1 - abs(i) / 46)
            p.setBrush(QBrush(cor(CIANO, a)))
            p.drawRect(QRectF(cx + i * 4.2, topo + 30, 2, 2))

        if not getattr(hud, "_cena", False):  # na cena, o botão é um widget de verdade
            by = min(H - 26.0, cy + R * 1.35)
            p.setPen(QPen(cor(CIANO, 150), 1.4))
            p.setBrush(QBrush(cor("#06244a", 220)))
            p.drawEllipse(QPointF(cx, by), 13, 13)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(cor(CIANO, 140 + 100 * (0.5 + 0.5 * math.sin(t * 2.2)))))
            p.drawEllipse(QPointF(cx, by), 4.5, 4.5)


# ---------------------------------------------------------------- vidro (base dos painéis)

class Vidro(QWidget):
    """Painel de vidro azul com cantos arredondados e cabeçalho pequeno."""

    def __init__(self, titulo: str = "", parent=None, etiqueta: str = "", forte: bool = False):
        super().__init__(parent)
        self.titulo = titulo
        self.etiqueta = etiqueta
        self.forte = forte
        self.corpo = QVBoxLayout(self)
        self.corpo.setContentsMargins(14, 32 if titulo else 12, 14, 12)
        self.corpo.setSpacing(5)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        g = QLinearGradient(r.topLeft(), r.bottomLeft())
        g.setColorAt(0.0, cor("#123a7a", 215 if self.forte else 175))
        g.setColorAt(1.0, cor("#0a2356", 225 if self.forte else 185))
        p.setBrush(QBrush(g))
        p.setPen(QPen(cor("#5fb4ff", 120 if self.forte else 70), 1))
        p.drawRoundedRect(r, 10, 10)
        p.setPen(QPen(cor("#9fe3ff", 40), 1))           # reflexo do vidro
        p.drawLine(QPointF(r.left() + 10, r.top() + 1.5), QPointF(r.right() - 10, r.top() + 1.5))
        if self.titulo:
            p.setFont(fonte(MONO, 7.2, QFont.Weight.Bold, 1.6))
            p.setPen(QPen(cor(CIANO, 220), 1))
            p.drawText(QRectF(14, 9, r.width() - 28, 16), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                       self.titulo.upper())
        if self.etiqueta:
            p.setFont(fonte(MONO, 6.8, QFont.Weight.Bold, 1))
            larg = p.fontMetrics().horizontalAdvance(self.etiqueta) + 14
            caixa = QRectF(r.right() - larg - 10, 8, larg, 17)
            p.setPen(QPen(cor(CIANO, 160), 1))
            p.setBrush(QBrush(cor("#0b4aa0", 160)))
            p.drawRoundedRect(caixa, 4, 4)
            p.drawText(caixa, Qt.AlignmentFlag.AlignCenter, self.etiqueta)


def rotulo(texto: str, tom: str = TEXTO2, pt: float = 9, peso=QFont.Weight.Normal, familia: str = SANS,
           quebra: bool = True) -> QLabel:
    l = QLabel(texto)
    l.setWordWrap(quebra)
    l.setFont(fonte(familia, pt, peso))
    l.setStyleSheet(f"color:{tom}; background: transparent;")
    return l


# ---------------------------------------------------------------- painéis da cena

class OndaVoz(QWidget):
    """Barras de áudio que seguem a voz do Jarvis."""

    def __init__(self, hud, parent=None):
        super().__init__(parent)
        self.hud = hud
        self.setMinimumHeight(54)
        self._barras = [0.1] * 34
        self._t = QTimer(self)
        self._t.timeout.connect(self._passo)
        self._t.start(70)

    def _passo(self):
        if not self.isVisible():
            return
        voz = getattr(self.hud, "_nivel_suave", 0.0) if self.hud.speaking else 0.0
        base = 0.06 + (0.05 if self.hud.state == "LISTENING" else 0)
        self._barras = self._barras[1:] + [min(1.0, base + voz * random.uniform(0.5, 1.2))]
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        W, H = self.width(), self.height()
        n = len(self._barras)
        bw = W / n
        for i, v in enumerate(self._barras):
            h = max(2.0, v * (H - 4))
            g = QLinearGradient(QPointF(0, H / 2 - h / 2), QPointF(0, H / 2 + h / 2))
            g.setColorAt(0.0, cor(CIANO, 230)); g.setColorAt(1.0, cor(AZUL, 200))
            p.fillRect(QRectF(i * bw + 1, H / 2 - h / 2, bw - 2, h), QBrush(g))


class Anel(QWidget):
    """Medidor redondo (CPU, memória)."""

    def __init__(self, nome: str, parent=None):
        super().__init__(parent)
        self.nome = nome
        self.valor = 0.0
        self.setFixedSize(76, 88)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(8, 4, 60, 60)
        p.setPen(QPen(cor("#2b5ea8", 160), 5))
        p.drawArc(r, 0, 360 * 16)
        tom = VERDE if self.valor < 60 else (AMBAR if self.valor < 85 else VERMELHO)
        pen = QPen(cor(tom, 230), 5); pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.drawArc(r, 90 * 16, int(-self.valor / 100 * 360 * 16))
        p.setPen(QPen(cor(TEXTO, 240), 1))
        p.setFont(fonte(MONO, 10, QFont.Weight.Bold))
        p.drawText(r, Qt.AlignmentFlag.AlignCenter, f"{self.valor:.0f}%")
        p.setFont(fonte(MONO, 6.8, QFont.Weight.Bold, 1.5))
        p.setPen(QPen(cor(TEXTO2, 220), 1))
        p.drawText(QRectF(0, 68, 76, 16), Qt.AlignmentFlag.AlignCenter, self.nome)


class Linha(QWidget):
    """Gráfico de linha pequeno (histórico da voz)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.valores = deque([0.0] * 60, maxlen=60)
        self.setMinimumHeight(46)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()
        vals = list(self.valores)
        cam = QPainterPath()
        for i, v in enumerate(vals):
            pt = QPointF(i * W / (len(vals) - 1), H - 3 - v * (H - 8))
            cam.moveTo(pt) if i == 0 else cam.lineTo(pt)
        area = QPainterPath(cam)
        area.lineTo(W, H); area.lineTo(0, H); area.closeSubpath()
        g = QLinearGradient(QPointF(0, 0), QPointF(0, H))
        g.setColorAt(0.0, cor(CIANO, 90)); g.setColorAt(1.0, cor(CIANO, 0))
        p.fillPath(area, QBrush(g))
        p.setPen(QPen(cor(CIANO, 230), 1.6))
        p.drawPath(cam)


class Chip(QLabel):
    def __init__(self, texto: str = "", tom: str = VERDE, parent=None):
        super().__init__(texto, parent)
        self.setFont(fonte(MONO, 7, QFont.Weight.Bold, 1))
        self.definir(texto, tom)

    def definir(self, texto: str, tom: str):
        self.setText(texto)
        c = QColor(tom)
        self.setStyleSheet(f"color:{tom}; background: rgba({c.red()},{c.green()},{c.blue()},38);"
                           f"border:1px solid rgba({c.red()},{c.green()},{c.blue()},120); border-radius:4px; padding:1px 7px;")


class Canal(Vidro):
    """Conversa: últimas falas e campo para digitar."""

    def __init__(self, win, parent=None):
        super().__init__("Jarvis · canal ativo", parent, forte=True)
        self.win = win
        self.lista = QVBoxLayout()
        self.lista.setSpacing(6)
        self.corpo.addLayout(self.lista)
        self.corpo.addStretch(1)
        self.entrada = QLineEdit()
        self.entrada.setPlaceholderText("Converse com o JARVIS...")
        self.entrada.setFont(fonte(SANS, 9.5))
        self.entrada.setStyleSheet(
            "QLineEdit{color:#e8f8ff; background: rgba(4,20,56,190); border:1px solid rgba(95,180,255,90);"
            "border-radius:6px; padding:7px 10px;} QLineEdit:focus{border-color:#29d4ff;}")
        self.entrada.returnPressed.connect(self._enviar)
        self.corpo.addWidget(self.entrada)
        self._falas = deque(maxlen=7)

    def _enviar(self):
        txt = self.entrada.text().strip()
        if not txt:
            return
        self.entrada.clear()
        self.win._send(txt)          # mesmo caminho do campo antigo
        ctl = getattr(self.win, "_orbe", None)
        if ctl is not None:
            ctl.ver_texto("You: " + txt)

    def adicionar(self, quem: str, texto: str):
        self._falas.append((quem, texto))
        while self.lista.count():
            w = self.lista.takeAt(0).widget()
            if w is not None:
                w.hide()
                w.deleteLater()
        for quem, texto in self._falas:
            tom = VERDE if quem == "VOCÊ" else CIANO
            curto = texto if len(texto) < 160 else texto[:157] + "..."
            l = rotulo(f'<span style="color:{tom}; font-weight:700">{quem}</span>'
                       f'<span style="color:{TEXTO2}"> • </span>'
                       f'<span style="color:{TEXTO}">{_escapar(curto)}</span>', TEXTO, 9)
            l.setTextFormat(Qt.TextFormat.RichText)
            self.lista.addWidget(l)


def _escapar(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


class BotaoNucleo(QPushButton):
    """Botão redondo embaixo do anel: liga e desliga o microfone."""

    def __init__(self, hud, parent=None):
        super().__init__(parent)
        self.hud = hud
        self.setFixedSize(46, 46)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Ligar/desligar o microfone")
        self.setStyleSheet("background: transparent; border: none;")
        self._t = QTimer(self); self._t.timeout.connect(self.update); self._t.start(80)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        c = QPointF(23, 23)
        tom = AMBAR if self.hud.muted else CIANO
        g = QRadialGradient(c, 23)
        g.setColorAt(0.0, cor(tom, 110)); g.setColorAt(1.0, cor(tom, 0))
        p.setPen(Qt.PenStyle.NoPen); p.setBrush(QBrush(g)); p.drawEllipse(c, 23, 23)
        p.setPen(QPen(cor(tom, 200), 1.5)); p.setBrush(QBrush(cor("#082a66", 230))); p.drawEllipse(c, 15, 15)
        pulso = 0.5 + 0.5 * math.sin(time.time() * 2.4)
        p.setPen(Qt.PenStyle.NoPen); p.setBrush(QBrush(cor(tom, 150 + 100 * pulso))); p.drawEllipse(c, 5.5, 5.5)


class Cena(QWidget):
    """Tela inteira no estilo do vídeo: anel no centro e painéis de vidro dos lados."""

    fala = pyqtSignal(str, str)

    LARG = 250

    def __init__(self, win):
        central = win.centralWidget()
        super().__init__(central)
        self.win = win
        self.hud = win.hud
        self.central = central
        self._antigo_layout = self.hud.parentWidget().layout() if self.hud.parentWidget() else None
        self._antigo_indice = self._antigo_layout.indexOf(self.hud) if self._antigo_layout else -1
        self._pedidos = 0
        self._ultimo = None
        self._rede = ("VERIFICANDO", AMBAR, "")

        self.ativa = True
        self.hud.setParent(self)
        self.hud._cena = True
        self.hud.show()

        # Barra do topo
        self.topo_esq = rotulo("◉  JARVIS ULTRON  ·  PRINCIPAL", TEXTO2, 7.5, QFont.Weight.Bold, MONO, False)
        self.topo_dir = rotulo("", TEXTO2, 7.5, QFont.Weight.Bold, MONO, False)
        for w in (self.topo_esq, self.topo_dir):
            w.setParent(self)

        # Coluna da esquerda
        self.p_voz = Vidro("Voz · entrada", self, etiqueta="AO VIVO")
        self.onda = OndaVoz(self.hud); self.p_voz.corpo.addWidget(self.onda)

        self.p_sistema = Vidro("Tempo real", self, etiqueta="SISTEMA")
        linha_aneis = QHBoxLayout(); linha_aneis.setSpacing(6)
        self.a_cpu, self.a_mem, self.a_disco = Anel("CPU"), Anel("MEMÓRIA"), Anel("DISCO")
        for a in (self.a_cpu, self.a_mem, self.a_disco):
            linha_aneis.addWidget(a)
        self.p_sistema.corpo.addLayout(linha_aneis)

        self.p_status = Vidro("Status", self, etiqueta="OPERACIONAL")
        self.st = {}
        for nome in ("Voz", "Microfone", "Inteligência", "Câmera local"):
            linha = QHBoxLayout()
            linha.addWidget(rotulo(nome, TEXTO, 9, quebra=False)); linha.addStretch(1)
            chip = Chip("ATIVO"); chip.setMinimumWidth(78); chip.setAlignment(Qt.AlignmentFlag.AlignCenter)
            linha.addWidget(chip)
            self.st[nome] = chip
            self.p_status.corpo.addLayout(linha)

        # Coluna da direita
        self.p_ativ = Vidro("Atividade · agora", self)
        self.l_pedidos = rotulo("0", TEXTO, 22, QFont.Weight.Bold, MONO, False)
        self.l_pedidos_sub = rotulo("pedidos nesta sessão", TEXTO2, 8, quebra=False)
        self.p_ativ.corpo.addWidget(self.l_pedidos); self.p_ativ.corpo.addWidget(self.l_pedidos_sub)

        self.p_hist = Vidro("Voz · últimos 60 s", self)
        self.linha_voz = Linha(); self.p_hist.corpo.addWidget(self.linha_voz)

        self.p_rede = Vidro("Rede · diagnóstico", self)
        linha = QHBoxLayout()
        self.l_rede = rotulo("VERIFICANDO", AMBAR, 12, QFont.Weight.Bold, MONO, False)
        self.l_lat = rotulo("", TEXTO2, 8, quebra=False)
        linha.addWidget(self.l_rede); linha.addStretch(1); linha.addWidget(self.l_lat)
        self.p_rede.corpo.addLayout(linha)
        self.l_rede_sub = rotulo("Internet, voz e IA", TEXTO2, 8)
        self.p_rede.corpo.addWidget(self.l_rede_sub)

        self.canal = Canal(win, self)
        self.fala.connect(self.canal.adicionar)

        self.botao = BotaoNucleo(self.hud, self)
        self.botao.clicked.connect(lambda: getattr(win, "_toggle_mute", lambda: None)())

        self._painel = [self.p_voz, self.p_sistema, self.p_status, self.p_ativ, self.p_hist, self.p_rede, self.canal]

        self._t = QTimer(self); self._t.timeout.connect(self._atualizar); self._t.start(1000)
        self._t_voz = QTimer(self); self._t_voz.timeout.connect(self._amostra_voz); self._t_voz.start(1000)
        self._t_rede = QTimer(self); self._t_rede.timeout.connect(self._checar_rede); self._t_rede.start(30_000)
        self._checar_rede()

        central.installEventFilter(self)
        self.setGeometry(central.rect())
        self._organizar()
        self.show()
        self.raise_()
        self._trazer_janelas()
        self._atualizar()

    # ----- posição
    def eventFilter(self, obj, ev):
        if obj is self.central and ev.type() in (QEvent.Type.Resize, QEvent.Type.Show) and not self.isHidden():
            self.setGeometry(self.central.rect())
            self.raise_()
            self._organizar()
            self._trazer_janelas()
        return False

    def _trazer_janelas(self):
        """A tela de chave do Gemini e a de nome precisam ficar por cima da cena."""
        for nome in ("_overlay", "_name_overlay"):
            w = getattr(self.win, nome, None)
            if w is not None and w.isVisible():
                w.raise_()

    def _organizar(self):
        W, H = self.width(), self.height()
        self.hud.setGeometry(0, 0, W, H)
        m, L = 18, self.LARG
        mostrar_lados = W >= 980
        self.topo_esq.setGeometry(m, 8, 400, 20)
        self.topo_dir.setGeometry(W - 420 - m, 8, 420, 20)
        self.topo_dir.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        y0 = 40
        esq = [(self.p_voz, 104), (self.p_sistema, 132), (self.p_status, 150)]
        y = y0
        for w, h in esq:
            w.setGeometry(m, y, L, h); w.setVisible(mostrar_lados); y += h + 12
        dir_ = [(self.p_ativ, 92), (self.p_hist, 92), (self.p_rede, 86)]
        y = y0
        for w, h in dir_:
            w.setGeometry(W - L - m, y, L, h); w.setVisible(mostrar_lados); y += h + 12
        altura_canal = max(170, H - y - 70)
        if mostrar_lados:
            self.canal.setGeometry(W - L - m, y, L, altura_canal)
        else:
            self.canal.setGeometry(m, H - 230, W - 2 * m, 170)
        self.botao.move(int(W / 2 - 23), H - 58)
        for w in self._painel:
            w.raise_()
        self.botao.raise_()
        ctl = getattr(self.win, "_orbe", None)
        if ctl is not None:
            ctl.reencaixar()

    # ----- dados
    def registrar(self, texto: str):
        """Recebe linhas do log (qualquer fio): conta pedidos e alimenta o canal."""
        if texto.startswith(("You:", "Você:")):
            self._pedidos += 1
            self._ultimo = time.time()
            self.fala.emit("VOCÊ", texto.split(":", 1)[1].strip())
        elif texto.startswith(("Jarvis:", "JARVIS:")):
            self.fala.emit("JARVIS", texto.split(":", 1)[1].strip())

    def _amostra_voz(self):
        self.linha_voz.valores.append(getattr(self.hud, "_nivel_suave", 0.0) if self.hud.speaking else 0.0)
        self.linha_voz.update()

    def _checar_rede(self):
        def teste():
            t0 = time.time()
            try:
                socket.create_connection(("8.8.8.8", 53), timeout=3).close()
                self._rede = ("ONLINE", VERDE, f"{(time.time() - t0) * 1000:.0f} ms")
            except OSError:
                self._rede = ("OFFLINE", VERMELHO, "")
        threading.Thread(target=teste, daemon=True).start()

    def _atualizar(self):
        if not self.isVisible():
            return
        agora = dt.datetime.now()
        rede = self._rede[0]
        self.topo_dir.setText(f"● SISTEMA {'ONLINE' if rede == 'ONLINE' else rede}   ·   "
                              f"VOZ {'MUDA' if self.hud.muted else 'ATIVA'}   ·   {agora:%H:%M}")
        try:
            import psutil
            self.a_cpu.valor = psutil.cpu_percent(interval=None)
            self.a_mem.valor = psutil.virtual_memory().percent
            self.a_disco.valor = psutil.disk_usage(str(Path.home().anchor or "/")).percent
        except Exception:
            pass
        for a in (self.a_cpu, self.a_mem, self.a_disco):
            a.update()
        mudo = self.hud.muted
        self.st["Voz"].definir("FALANDO" if self.hud.speaking else "ATIVO", VERDE)
        self.st["Microfone"].definir("MUDO" if mudo else "ATIVO", AMBAR if mudo else VERDE)
        self.st["Inteligência"].definir("PENSANDO" if self.hud.state in ("THINKING", "PROCESSING") else "PRONTA", VERDE)
        cam = getattr(self.win, "_orbe", None)
        ligada = cam is not None and cam.biometria.isVisible()
        self.st["Câmera local"].definir("EM USO" if ligada else "LIVRE", CIANO if ligada else APAGADO)
        self.l_pedidos.setText(str(self._pedidos))
        self.l_pedidos_sub.setText("pedidos nesta sessão" + (
            f" · último {dt.datetime.fromtimestamp(self._ultimo):%H:%M}" if self._ultimo else ""))
        nome, tom, lat = self._rede
        self.l_rede.setText(nome); self.l_rede.setStyleSheet(f"color:{tom}; background: transparent;")
        self.l_lat.setText(lat)
        self.l_rede_sub.setText("Internet ok · voz e IA disponíveis" if nome == "ONLINE"
                                else ("Sem internet: a IA não responde" if nome == "OFFLINE" else "Testando a conexão..."))

    # ----- alternar com a tela antiga (F2)
    def alternar(self):
        if self.ativa:
            self.ativa = False
            self.hide()
            self.hud._cena = False
            if self._antigo_layout is not None:
                self._antigo_layout.insertWidget(max(0, self._antigo_indice), self.hud, 4)
            self.hud.show()
        else:
            self.ativa = True
            self.hud._cena = True
            if self._antigo_layout is not None:
                self._antigo_layout.removeWidget(self.hud)
            self.hud.setParent(self)
            self.hud.show()
            self.setGeometry(self.central.rect())
            self.show(); self.raise_()
            self._organizar()
            self._trazer_janelas()


# ---------------------------------------------------------------- câmera

def _indice_camera() -> int:
    try:
        from ui import API_FILE
        dados = json.loads(API_FILE.read_text(encoding="utf-8")) if API_FILE.exists() else {}
        return int(dados.get("camera_index", 0))
    except Exception:
        return 0


def _detector_rosto(cv2):
    pastas = []
    dados = getattr(cv2, "data", None)
    if dados is not None and getattr(dados, "haarcascades", None):
        pastas.append(Path(dados.haarcascades))
    pastas.append(Path(cv2.__file__).parent / "data")
    for pasta in pastas:
        arq = pasta / "haarcascade_frontalface_default.xml"
        if arq.exists():
            det = cv2.CascadeClassifier(str(arq))
            if not det.empty():
                return det
    return None


class _LeitorCamera(threading.Thread):
    """Lê a câmera fora da tela, para a janela não travar enquanto ela liga."""

    def __init__(self):
        super().__init__(daemon=True)
        self.quadro = None
        self.rostos = 0
        self.tem_detector = False
        self.erro = ""
        self.pronta = False
        self._parar = threading.Event()

    def parar(self):
        self._parar.set()

    def run(self):
        try:
            import cv2
        except Exception:
            self.erro = "sem opencv"
            return
        import platform
        backend = cv2.CAP_DSHOW if platform.system() == "Windows" else cv2.CAP_ANY
        cam = cv2.VideoCapture(_indice_camera(), backend)
        if not cam.isOpened():
            self.erro = "câmera indisponível"
            return
        det = _detector_rosto(cv2)
        self.tem_detector = det is not None
        self.pronta = True
        n = 0
        try:
            while not self._parar.is_set():
                ok, q = cam.read()
                if not ok:
                    time.sleep(0.05)
                    continue
                q = cv2.flip(q, 1)
                self.quadro = q
                n += 1
                if det is not None and n % 3 == 0:
                    cinza = cv2.cvtColor(cv2.resize(q, (320, int(320 * q.shape[0] / q.shape[1]))), cv2.COLOR_BGR2GRAY)
                    achou = len(det.detectMultiScale(cinza, 1.2, 5, minSize=(50, 50))) > 0
                    self.rostos = self.rostos + 1 if achou else 0
                time.sleep(0.02)
        finally:
            cam.release()


class Biometria(QWidget):
    """Câmera dentro do anel, com varredura, até achar um rosto."""

    concluida = pyqtSignal(bool)
    PRAZO = 9.0

    def __init__(self, hud):
        super().__init__(hud)
        self.hud = hud
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._leitor = None
        self._px = None
        self._fase = "busca"
        self._t0 = 0.0
        self._t_fim = 0.0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._passo)
        self.hide()

    def iniciar(self):
        self._leitor = _LeitorCamera()
        self._leitor.start()
        self._px = None
        self._fase = "busca"
        self._t0 = time.time()
        self._encaixar()
        self.show()
        self.raise_()
        self._timer.start(40)

    def _encaixar(self):
        self.setGeometry(self.hud.rect())

    def _terminar(self, achou: bool):
        self._timer.stop()
        if self._leitor:
            self._leitor.parar()
        self.hide()
        self.concluida.emit(achou)

    def _passo(self):
        agora = time.time()
        lt = self._leitor
        if self._fase == "busca":
            if lt.erro:
                self._terminar(False)
                return
            if lt.quadro is not None:
                self._px = self._para_pixmap(lt.quadro)
            confirmou = lt.rostos >= 4 or (lt.pronta and not lt.tem_detector and agora - self._t0 > 2.5 and lt.quadro is not None)
            if confirmou:
                self._fase, self._t_fim = "ok", agora
            elif agora - self._t0 > self.PRAZO:
                self._fase, self._t_fim = "falhou", agora
        elif agora - self._t_fim > 1.4:
            self._terminar(self._fase == "ok")
            return
        elif lt.quadro is not None and self._fase == "ok":
            self._px = self._para_pixmap(lt.quadro)
        self.update()

    def _para_pixmap(self, q) -> QPixmap:
        h, w = q.shape[:2]
        lado = min(h, w)
        y0, x0 = (h - lado) // 2, (w - lado) // 2
        corte = q[y0:y0 + lado, x0:x0 + lado].copy()
        img = QImage(corte.data, lado, lado, 3 * lado, QImage.Format.Format_BGR888)
        return QPixmap.fromImage(img.copy())

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()
        c = QPointF(W / 2, H / 2)
        r = min(W, H) * 0.14
        agora = time.time()
        p.setFont(fonte(MONO, 8, QFont.Weight.Bold, 3))
        self._legenda(p, c.y() - r - 46, "◦ IDENTIFICAÇÃO BIOMÉTRICA — LOCAL", CIANO)

        cam = QPainterPath(); cam.addEllipse(c, r, r)
        p.save(); p.setClipPath(cam)
        if self._px is not None:
            p.drawPixmap(QRectF(c.x() - r, c.y() - r, 2 * r, 2 * r), self._px, QRectF(self._px.rect()))
        else:
            p.fillRect(QRectF(c.x() - r, c.y() - r, 2 * r, 2 * r), cor("#031a38", 230))
            p.setPen(QPen(cor(TEXTO2, 200), 1))
            p.drawText(QRectF(c.x() - r, c.y() - 8, 2 * r, 16), Qt.AlignmentFlag.AlignCenter, "LIGANDO CÂMERA")
        if self._fase == "busca":
            yv = c.y() - r + (2 * r) * (0.5 + 0.5 * math.sin((agora - self._t0) * 2.4))
            g = QLinearGradient(QPointF(0, yv - 14), QPointF(0, yv + 2))
            g.setColorAt(0.0, cor(CIANO, 0)); g.setColorAt(1.0, cor(CIANO, 150))
            p.fillRect(QRectF(c.x() - r, yv - 14, 2 * r, 16), QBrush(g))
        p.restore()

        tom = VERDE if self._fase == "ok" else (VERMELHO if self._fase == "falhou" else CIANO)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(cor(tom, 230), 3))
        p.drawEllipse(c, r + 6, r + 6)
        p.setPen(QPen(cor(tom, 90), 1.2))
        giro = (agora - self._t0) * 90
        caixa = QRectF(c.x() - r - 16, c.y() - r - 16, 2 * r + 32, 2 * r + 32)
        p.drawArc(caixa, int(giro * 16), 100 * 16)
        p.drawArc(caixa, int((giro + 180) * 16), 100 * 16)
        texto = {"busca": "PROCURANDO ROSTO", "ok": "PRESENÇA CONFIRMADA", "falhou": "ROSTO NÃO ENCONTRADO"}[self._fase]
        self._legenda(p, c.y() + r + 30, texto, tom)

    def _legenda(self, p: QPainter, y: float, texto: str, tom: str) -> None:
        largura = p.fontMetrics().horizontalAdvance(texto) + 24
        caixa = QRectF((self.width() - largura) / 2, y - 3, largura, 22)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(cor("#031a4a", 210)))
        p.drawRoundedRect(caixa, 4, 4)
        p.setPen(QPen(cor(tom, 235), 1))
        p.drawText(caixa, Qt.AlignmentFlag.AlignCenter, texto)


# ---------------------------------------------------------------- dados do briefing

def _clima() -> dict:
    cidade = os.environ.get("JARVIS_CIDADE", "Campina Grande")
    try:
        from ui_stark import buscar_clima
        linhas = buscar_clima(cidade).splitlines()
    except Exception:
        return {"cidade": cidade, "ok": False}
    d = {"cidade": cidade, "ok": True, "linhas": linhas, "temp": "", "desc": "", "min": "", "max": "", "extra": ""}
    m = re.match(r"\s*(-?\d+)°C\s*(.*)", linhas[0] if linhas else "")
    if m:
        d["temp"], d["desc"] = m.group(1) + "°", m.group(2).strip()
    if len(linhas) > 1:
        d["extra"] = linhas[1]
    if len(linhas) > 2:
        m2 = re.search(r"(-?\d+)°\s*/\s*(-?\d+)°", linhas[2])
        if m2:
            d["min"], d["max"] = m2.group(1) + "°", m2.group(2) + "°"
    return d


def _noticias() -> list[str]:
    try:
        from ui_stark import buscar_noticias
        return [t for t, _ in buscar_noticias(4)]
    except Exception:
        return []


def _lembretes_hoje() -> list[str]:
    try:
        from automacoes import lembretes
        hoje = dt.date.today()
        itens = []
        for l in lembretes.proximos(lembretes.ler()):
            quando = dt.datetime.fromisoformat(l["quando"])
            if quando.date() == hoje:
                itens.append(f"{quando:%H:%M}  {l['texto']}")
        return itens[:5]
    except Exception:
        return []


def _emails() -> dict:
    """E-mails não lidos da caixa de entrada, só se o Gmail já estiver conectado."""
    try:
        from actions import email_control as ec
        servico = ec._gmail_service()
    except Exception:
        return {"conectado": False, "itens": []}
    try:
        res = servico.users().messages().list(userId="me", q="is:unread in:inbox", maxResults=4).execute()
        total = int(res.get("resultSizeEstimate", 0))
        itens = []
        for m in res.get("messages", []) or []:
            msg = servico.users().messages().get(userId="me", id=m["id"], format="metadata",
                                                 metadataHeaders=["From", "Subject"]).execute()
            cab = ec._headers_map(msg.get("payload", {}))
            remetente = re.sub(r"\s*<.*?>", "", cab.get("from", "")).strip('" ') or "Sem remetente"
            itens.append((remetente, cab.get("subject", "(sem assunto)")))
        return {"conectado": True, "total": total, "itens": itens}
    except Exception:
        return {"conectado": True, "total": 0, "itens": [], "erro": "Não consegui ler a caixa agora."}


DIAS = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"]
MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro",
         "novembro", "dezembro"]

ETAPAS = [
    ("AGENDA", "Conferindo sua agenda...", "Lendo lembretes e compromissos de hoje."),
    ("E-MAILS", "Filtrando e-mails importantes...", "Separando ações, riscos e mensagens que exigem sua atenção."),
    ("NOTÍCIAS", "Atualizando o radar de notícias...", "Consultando as manchetes mais relevantes desde ontem."),
    ("CLIMA", "Checando o clima...", "Previsão do dia para a sua cidade."),
    ("PRIORIDADES", "Montando suas prioridades...", "Convertendo os sinais do dia em um resumo falado e objetivo."),
]
CHAVES = ["lembretes", "emails", "noticias", "clima", None]


# ---------------------------------------------------------------- briefing

class CartaoEtapas(Vidro):
    """Cartão central: título grande, etapas e barra de progresso."""

    def __init__(self, parent=None):
        super().__init__("", parent, forte=True)
        self.corpo.setContentsMargins(22, 14, 22, 16)
        self.corpo.setSpacing(6)
        self.sobre = rotulo("BRIEFING MATINAL", CIANO, 7.5, QFont.Weight.Bold, MONO)
        self.sobre.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.titulo_l = rotulo("", TEXTO, 17, QFont.Weight.Bold, MONO)
        self.titulo_l.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.sub = rotulo("", TEXTO2, 8.5, familia=MONO)
        self.sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.corpo.addWidget(self.sobre); self.corpo.addWidget(self.titulo_l); self.corpo.addWidget(self.sub)
        linha = QHBoxLayout(); linha.setSpacing(6)
        self.chips = []
        for nome, _, _ in ETAPAS:
            c = QLabel(nome)
            c.setAlignment(Qt.AlignmentFlag.AlignCenter)
            c.setFont(fonte(MONO, 7, QFont.Weight.Bold, 1))
            linha.addWidget(c, 1)
            self.chips.append(c)
        self.corpo.addSpacing(4)
        self.corpo.addLayout(linha)
        self.barra = QWidget(); self.barra.setFixedHeight(6)
        self.barra.paintEvent = self._pintar_barra
        self.corpo.addWidget(self.barra)
        self.progresso = 0.0

    def mostrar(self, indice: int, titulo: str, sub: str, sobre: str = "BRIEFING MATINAL"):
        self.sobre.setText(sobre)
        self.titulo_l.setText(titulo)
        self.sub.setText(sub)
        for i, c in enumerate(self.chips):
            if i == indice:
                estilo = "color:#e8fbff; background: rgba(41,212,255,70); border:1px solid #29d4ff;"
            elif i < indice or indice < 0:
                estilo = "color:#8fe9ff; background: rgba(41,212,255,18); border:1px solid rgba(41,212,255,90);"
            else:
                estilo = "color:#6f9cc8; background: rgba(10,40,90,120); border:1px solid rgba(95,180,255,60);"
            c.setStyleSheet(estilo + " border-radius:4px; padding:4px 2px;")
        self.barra.update()

    def _pintar_barra(self, _):
        p = QPainter(self.barra)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W = self.barra.width()
        larg = W * 0.55
        x0 = (W - larg) / 2
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(cor("#0b3a7a", 200))); p.drawRoundedRect(QRectF(x0, 1, larg, 4), 2, 2)
        g = QLinearGradient(QPointF(x0, 0), QPointF(x0 + larg, 0))
        g.setColorAt(0.0, cor(CIANO, 255)); g.setColorAt(1.0, cor(VERDE, 255))
        p.setBrush(QBrush(g)); p.drawRoundedRect(QRectF(x0, 1, larg * self.progresso, 4), 2, 2)


def cartao(rotulo_txt: str, titulo: str, parent=None, etiquetas: tuple = (), forte: bool = False) -> Vidro:
    v = Vidro(rotulo_txt, parent, forte=forte)
    t = rotulo(titulo, TEXTO, 13 if forte else 11.5, QFont.Weight.Bold)
    linha = QHBoxLayout(); linha.addWidget(t, 1)
    for texto in etiquetas:
        linha.addWidget(Chip(texto, CIANO))
    v.corpo.addLayout(linha)
    v.titulo_label = t
    return v


class Resumo(QWidget):
    """Briefing: etapas no cartão central e depois os cartões do dia."""

    dados_prontos = pyqtSignal(dict)

    MIN_ETAPA = 1.7   # segundos mínimos em cada etapa

    def __init__(self, hud):
        super().__init__(hud)
        self.hud = hud
        self.dados_prontos.connect(self._chegou)
        self._fechar_timer = QTimer(self); self._fechar_timer.setSingleShot(True)
        self._fechar_timer.timeout.connect(self.fechar)
        self._passo_timer = QTimer(self); self._passo_timer.timeout.connect(self._passo)
        self._anims = []
        self._dados = None
        self._presenca = False
        self.etapas = CartaoEtapas(self)
        self.etapas.hide()
        self._cartoes = []
        self.hide()

    # ----- ciclo
    def carregar(self, presenca: bool):
        self._presenca = presenca
        self._dados = None
        self._limpar_cartoes()
        self._etapa = 0
        self._t_etapa = time.time()
        self._encaixar()
        self.etapas.show()
        self.etapas.progresso = 0.0
        self._mostrar_etapa()
        self.show(); self.raise_()
        self._passo_timer.start(60)
        threading.Thread(target=lambda: self.dados_prontos.emit(juntar_resumo()), daemon=True).start()

    def _chegou(self, d: dict):
        self._dados = d

    def _mostrar_etapa(self):
        nome, titulo, sub = ETAPAS[self._etapa]
        if nome == "CLIMA":
            sub = f"Previsão do dia para {os.environ.get('JARVIS_CIDADE', 'Campina Grande')}."
        self.etapas.mostrar(self._etapa, titulo, sub)

    def _passo(self):
        dur = time.time() - self._t_etapa
        total = len(ETAPAS)
        frac = min(1.0, dur / self.MIN_ETAPA)
        self.etapas.progresso = (self._etapa + frac) / (total + 1)
        self.etapas.barra.update()
        if frac < 1.0:
            return
        if self._etapa < total - 1:
            self._etapa += 1
            self._t_etapa = time.time()
            self._mostrar_etapa()
        elif self._dados is not None:
            self._passo_timer.stop()
            self._parecer()

    def _parecer(self):
        d = self._dados
        emails = d["emails"]
        acao = len(emails.get("itens", [])) if emails.get("conectado") else 0
        pend = len(d["lembretes"])
        if acao or pend:
            partes = []
            if acao:
                partes.append(f"{acao} e-mail(s)")
            if pend:
                partes.append(f"{pend} compromisso(s)")
            titulo, sub = "Pedem sua atenção", " e ".join(partes) + " para hoje."
        else:
            titulo, sub = "Sem desvios relevantes", "Nada urgente desde ontem."
        self.etapas.progresso = 1.0
        self.etapas.mostrar(-1, titulo, sub, "PARECER PRÉVIO")
        QTimer.singleShot(2200, self._cartoes_do_dia)

    # ----- cartões finais
    def _cartoes_do_dia(self):
        if not self.isVisible() or self._dados is None:
            return
        d = self._dados
        self.etapas.hide()
        self._limpar_cartoes()
        hoje = dt.date.today()
        nome = os.environ.get("JARVIS_NOME", "").strip()
        emails, clima = d["emails"], d["clima"]

        # Cartão grande: e-mails (ou notícias, se o Gmail não estiver conectado)
        if emails.get("conectado"):
            total = emails.get("total", 0)
            grande = cartao("Comunicações · e-mail", "Pedem sua atenção", self,
                            (f"{total} NÃO LIDOS", f"{len(emails['itens'])} PARA AGIR"), forte=True)
            for rem, assunto in emails["itens"] or []:
                grande.corpo.addWidget(rotulo(f'<b style="color:{CIANO}">{_escapar(rem.upper()[:28])}</b><br>'
                                              f'<span style="color:{TEXTO}">{_escapar(assunto)}</span>', TEXTO, 9))
            if not emails["itens"]:
                grande.corpo.addWidget(rotulo(emails.get("erro", "Caixa de entrada em dia."), TEXTO2, 9))
        else:
            grande = cartao("Radar · notícias", "Manchetes do dia", self, ("GOOGLE NOTÍCIAS",), forte=True)
            for n in d["noticias"] or ["Sem notícias agora. Confira a internet."]:
                grande.corpo.addWidget(rotulo("•  " + n, TEXTO, 9))
            grande.corpo.addWidget(rotulo('Gmail não conectado: diga "conectar o Gmail" para ver seus e-mails aqui.',
                                          APAGADO, 7.5))
        saud = rotulo(f"Bom dia{', ' + nome if nome else ''} · {DIAS[hoje.weekday()]}, {hoje.day} de "
                      f"{MESES[hoje.month - 1]}" + ("  ·  presença confirmada" if self._presenca else ""),
                      TEXTO2, 7.5, familia=MONO)
        grande.corpo.addWidget(saud)

        # Clima
        if clima.get("ok"):
            c1 = cartao("Previsão · clima", clima["cidade"], self)
            linha = QHBoxLayout()
            sol = rotulo("☀", AMBAR, 20, quebra=False)
            temp = rotulo(clima.get("temp") or "--", TEXTO, 22, QFont.Weight.Bold, MONO, False)
            linha.addWidget(sol); linha.addWidget(temp); linha.addStretch(1)
            c1.corpo.addLayout(linha)
            c1.corpo.addWidget(rotulo(clima.get("desc", ""), TEXTO2, 8.5))
            if clima.get("min"):
                c1.corpo.addWidget(rotulo(f"MÍN {clima['min']}   ·   MÁX {clima['max']}", TEXTO, 8, QFont.Weight.Bold, MONO))
        else:
            c1 = cartao("Previsão · clima", clima["cidade"], self)
            c1.corpo.addWidget(rotulo("Clima indisponível agora.", TEXTO2, 9))

        # Agenda
        if d["lembretes"]:
            c2 = cartao("Agenda · hoje", f"{len(d['lembretes'])} compromisso(s)", self)
            for l in d["lembretes"]:
                c2.corpo.addWidget(rotulo(l, TEXTO, 9))
        else:
            c2 = cartao("Agenda · hoje", "Agenda livre", self)
            c2.corpo.addWidget(rotulo("🗓", CIANO, 16, quebra=False))
            c2.corpo.addWidget(rotulo("Nenhum compromisso registrado.", TEXTO, 9))

        pequenos = [c1, c2]
        if emails.get("conectado") and d["noticias"]:
            c3 = cartao("Radar · notícias", "Manchetes", self)
            for n in d["noticias"][:3]:
                c3.corpo.addWidget(rotulo("•  " + n, TEXTO, 8.5))
            pequenos.append(c3)

        fechar = QPushButton("×", grande)
        fechar.setCursor(Qt.CursorShape.PointingHandCursor)
        fechar.setFixedSize(24, 24)
        fechar.setStyleSheet(f"QPushButton{{color:{TEXTO2}; background: rgba(4,20,56,160); border:1px solid #3a78d8;"
                             f"border-radius:12px; font: 11pt;}} QPushButton:hover{{color:{TEXTO}; border-color:{CIANO};}}")
        fechar.clicked.connect(self.fechar)
        self._fechar_btn = fechar
        self._grande, self._pequenos = grande, pequenos
        self._cartoes = [grande] + pequenos
        self._posicionar_cartoes()
        self._anims = []
        for i, w in enumerate(self._cartoes):
            w.show()
            ef = QGraphicsOpacityEffect(w); ef.setOpacity(0.0); w.setGraphicsEffect(ef)
            an = QPropertyAnimation(ef, b"opacity", self)
            an.setDuration(500); an.setStartValue(0.0); an.setEndValue(1.0)
            an.setEasingCurve(QEasingCurve.Type.OutExpo)
            QTimer.singleShot(220 * i, an.start)
            self._anims.append(an)
        self._fechar_timer.start(90_000)

    def _posicionar_cartoes(self):
        if not self._cartoes:
            return
        W, H = self.width(), self.height()
        g = self._grande
        g.setFixedWidth(W)
        g.adjustSize()
        hg = min(g.sizeHint().height(), int(H * 0.55))
        g.setGeometry(0, 0, W, hg)
        self._fechar_btn.move(W - 34, 8)
        n = len(self._pequenos)
        esp = 12
        larg = (W - esp * (n - 1)) / n if n else W
        y = hg + esp
        hp = 0
        for w in self._pequenos:
            w.setFixedWidth(int(larg)); w.adjustSize(); hp = max(hp, w.sizeHint().height())
        hp = min(hp, H - y)
        for i, w in enumerate(self._pequenos):
            w.setGeometry(int(i * (larg + esp)), y, int(larg), hp)

    def _limpar_cartoes(self):
        for w in self._cartoes:
            w.hide(); w.deleteLater()
        self._cartoes = []
        self._grande, self._pequenos = None, []

    def _encaixar(self):
        W, H = self.hud.width(), self.hud.height()
        lw = int(min(W * 0.46, 640)) if W >= 980 else int(W * 0.9)
        lh = int(min(H * 0.64, 520))
        self.setGeometry(int((W - lw) / 2), int((H - lh) / 2) + 6, lw, lh)
        ew = int(min(lw, 560))
        self.etapas.setGeometry(int((lw - ew) / 2), int(lh * 0.3), ew, 170)
        self._posicionar_cartoes()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._posicionar_cartoes()

    def fechar(self):
        self._fechar_timer.stop()
        self._passo_timer.stop()
        self.hide()
        self.etapas.hide()
        self._limpar_cartoes()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape:
            self.fechar()


def juntar_resumo() -> dict:
    """Busca tudo ao mesmo tempo (roda fora da tela)."""
    saida = {}
    tarefas = {"clima": _clima, "noticias": _noticias, "lembretes": _lembretes_hoje, "emails": _emails}
    fios = []
    for nome, fn in tarefas.items():
        th = threading.Thread(target=lambda n=nome, f=fn: saida.__setitem__(n, f()), daemon=True)
        th.start()
        fios.append(th)
    for th in fios:
        th.join(timeout=20)
    saida.setdefault("clima", {"cidade": os.environ.get("JARVIS_CIDADE", "Campina Grande"), "ok": False})
    saida.setdefault("noticias", [])
    saida.setdefault("lembretes", [])
    saida.setdefault("emails", {"conectado": False, "itens": []})
    return saida


# ---------------------------------------------------------------- controle

class ControleOrbe(QObject):
    """Liga o orbe ao HUD, monta a cena e dispara o ritual do "bom dia"."""

    _pedido = pyqtSignal()
    GATILHO = re.compile(r"\bbom\s+dia\b")

    def __init__(self, win):
        super().__init__(win)
        self.win = win
        self.hud = win.hud
        self.hud._orbe = Orbe()
        self.cena = None
        if cena_ligada() and hasattr(win, "centralWidget") and win.centralWidget() is not None:
            self.cena = Cena(win)
            atalho = QShortcut(QKeySequence("F2"), win)
            atalho.activated.connect(self.cena.alternar)
        self.biometria = Biometria(self.hud)
        self.resumo = Resumo(self.hud)
        self.biometria.concluida.connect(self.resumo.carregar)
        self._pedido.connect(self.bom_dia)
        self._rodando_desde = 0.0
        antigo = self.hud.resizeEvent

        def ao_redimensionar(ev, antigo=antigo):
            antigo(ev)
            self.reencaixar()
        self.hud.resizeEvent = ao_redimensionar

    def reencaixar(self):
        if getattr(self, "biometria", None) is not None and self.biometria.isVisible():
            self.biometria._encaixar()
        if getattr(self, "resumo", None) is not None and self.resumo.isVisible():
            self.resumo._encaixar()

    def ver_texto(self, texto: str) -> None:
        """Chamado a cada linha do log (de qualquer thread)."""
        if self.cena is not None:
            self.cena.registrar(texto)
        if not texto.startswith(("You:", "Você:")):
            return
        if self.GATILHO.search(_sem_acento(texto.split(":", 1)[1])):
            self._pedido.emit()

    def bom_dia(self) -> None:
        if time.time() - self._rodando_desde < 12 or self.biometria.isVisible():
            return
        self._rodando_desde = time.time()
        self.resumo.fechar()
        if os.environ.get("JARVIS_BIOMETRIA", "1").strip() not in ("0", "nao", "não", "off"):
            self.biometria.iniciar()
        else:
            self.resumo.carregar(False)


def instalar(win) -> ControleOrbe | None:
    if not ligado():
        return None
    return ControleOrbe(win)
