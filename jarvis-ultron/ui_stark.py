"""Tela Stark do Jarvis Ultron: painéis no estilo do HUD do Homem de Ferro em volta da esfera.

- Topo: régua com os dias do mês (hoje aceso) e o título.
- Esquerda: relógio em anel, disco, energia, tempo ligado, internet e atalhos.
- Direita: STARK INDUSTRIES, clima, sistema (CPU/memória/swap), bloco de notas e notícias.
- Embaixo: botões redondos que mandam comandos ao Jarvis.

Ligada por padrão. Para voltar à tela original: JARVIS_TEMA_STARK=0 no .env.
Configurações: JARVIS_CIDADE (clima, padrão "Campina Grande").
"""

from __future__ import annotations

import calendar
import datetime as dt
import math
import os
import threading
import time
import webbrowser
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import quote

from PyQt6.QtCore import QPointF, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QRadialGradient
from PyQt6.QtWidgets import (QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QSizePolicy,
                             QVBoxLayout, QWidget)

AZUL = "#00c8ff"
AZUL_FORTE = "#00e5ff"
AZUL_ESCURO = "#006a88"
LINHA = "#0d3a55"
FUNDO = "#000306"
TEXTO = "#a8e8ff"
AMBAR = "#ffb300"

MESES = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto",
         "Setembro", "Outubro", "Novembro", "Dezembro"]
DIAS = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]

ATALHOS = [
    ("YouTube", "https://www.youtube.com"), ("Google", "https://www.google.com"),
    ("Gmail", "https://mail.google.com"), ("Instagram", "https://www.instagram.com"),
    ("Strava", "https://www.strava.com/dashboard"), ("Garmin", "https://connect.garmin.com"),
    ("Metricool", "https://app.metricool.com"), ("WhatsApp", "https://web.whatsapp.com"),
]

# (símbolo, dica, comando enviado ao Jarvis ou ação especial)
BOTOES = [
    ("◉", "Posts de hoje", "quais são os posts de hoje?"),
    ("☀", "Clima", "como está o tempo hoje?"),
    ("✉", "E-mails", "tenho e-mails não lidos?"),
    ("♫", "Música", "toque uma música no Spotify"),
    ("⛭", "Mãos livres", "modo mãos livres"),
    ("☏", "Modo chamada", "modo chamada"),
    ("⏸", "Suspender 10 min", "fique suspenso por 10 minutos"),
    ("⌂", "Pasta do Jarvis", "@pasta"),
    ("⚡", "Resumo do dia", "me dê um resumo do meu dia"),
]


def _cor(hexa: str, alfa: int = 255) -> QColor:
    cor = QColor(hexa)
    cor.setAlpha(alfa)
    return cor


def _caneta(hexa: str, largura: float = 1.0, alfa: int = 255) -> QPen:
    caneta = QPen(_cor(hexa, alfa))
    caneta.setWidthF(largura)
    caneta.setCapStyle(Qt.PenCapStyle.RoundCap)
    return caneta


class Fontes:
    ui = "Space Grotesk"
    tech = "JetBrains Mono"

    @classmethod
    def de(cls, tamanho: float, negrito: bool = False, tech: bool = False) -> QFont:
        fonte = QFont(cls.tech if tech else cls.ui)
        fonte.setPointSizeF(tamanho)
        fonte.setBold(negrito)
        return fonte


# ---------------------------------------------------------------- dados do computador

class Sistema:
    """Lê CPU, memória, disco, rede, bateria e tempo ligado (psutil)."""

    def __init__(self):
        try:
            import psutil
        except ImportError:  # pragma: no cover
            psutil = None
        self.ps = psutil
        self._rede_antes = None
        self.dados: dict = {}

    def atualizar(self) -> dict:
        ps = self.ps
        if ps is None:
            return self.dados
        d = {}
        d["cpu"] = ps.cpu_percent(interval=None)
        memoria = ps.virtual_memory()
        d["ram"] = memoria.percent
        d["swap"] = ps.swap_memory().percent
        raiz = os.environ.get("SystemDrive", "C:") + "\\" if os.name == "nt" else "/"
        try:
            disco = ps.disk_usage(raiz)
            d["disco_total"], d["disco_livre"] = disco.total, disco.free
            d["disco_pct"] = 100.0 * (disco.total - disco.free) / disco.total if disco.total else 0.0
        except OSError:
            d["disco_total"] = d["disco_livre"] = d["disco_pct"] = 0
        agora = time.time()
        rede = ps.net_io_counters()
        if self._rede_antes:
            t0, env0, rec0 = self._rede_antes
            passou = max(0.5, agora - t0)
            d["envio"] = (rede.bytes_sent - env0) / passou
            d["recebido"] = (rede.bytes_recv - rec0) / passou
        else:
            d["envio"] = d["recebido"] = 0.0
        self._rede_antes = (agora, rede.bytes_sent, rede.bytes_recv)
        bateria = ps.sensors_battery() if hasattr(ps, "sensors_battery") else None
        d["energia"] = bateria.percent if bateria else 100.0
        d["na_tomada"] = bool(bateria.power_plugged) if bateria else True
        d["ligado"] = agora - ps.boot_time()
        self.dados = d
        return d


def _tamanho(bytes_: float) -> str:
    for unidade in ("B", "KB", "MB", "GB", "TB"):
        if bytes_ < 1024 or unidade == "TB":
            return f"{bytes_:.0f} {unidade}" if unidade in ("B", "KB") else f"{bytes_:.1f} {unidade}"
        bytes_ /= 1024
    return "0 B"


def _duracao(segundos: float) -> str:
    horas, resto = divmod(int(segundos), 3600)
    dias, horas = divmod(horas, 24)
    return f"{dias}d {horas}h {resto // 60}min" if dias else f"{horas}h {resto // 60}min"


def buscar_clima(cidade: str) -> str:
    import requests

    r = requests.get(f"https://wttr.in/{quote(cidade)}?format=j1&lang=pt", timeout=15,
                     headers={"User-Agent": "JarvisUltron"})
    r.raise_for_status()
    dados = r.json()
    atual = dados["current_condition"][0]
    descricao = (atual.get("lang_pt") or atual.get("weatherDesc") or [{"value": ""}])[0]["value"]
    linhas = [f"{atual['temp_C']}°C  {descricao}", f"Sensação {atual['FeelsLikeC']}°C · Umidade {atual['humidity']}%"]
    for dia in dados.get("weather", [])[:3]:
        data = dt.date.fromisoformat(dia["date"])
        linhas.append(f"{DIAS[data.weekday()][:3]}  {dia['mintempC']}° / {dia['maxtempC']}°")
    return "\n".join(linhas)


def buscar_noticias(limite: int = 5) -> list[tuple[str, str]]:
    import requests

    r = requests.get("https://news.google.com/rss?hl=pt-BR&gl=BR&ceid=BR:pt-419", timeout=15,
                     headers={"User-Agent": "JarvisUltron"})
    r.raise_for_status()
    itens = []
    for item in ET.fromstring(r.content).iter("item"):
        titulo = (item.findtext("title") or "").rsplit(" - ", 1)[0].strip()
        if titulo:
            itens.append((titulo, item.findtext("link") or ""))
        if len(itens) >= limite:
            break
    return itens


# ---------------------------------------------------------------- peças visuais

class Moldura(QWidget):
    """Painel com cantos cortados e título, no estilo HUD."""

    def __init__(self, titulo: str = "", parent=None):
        super().__init__(parent)
        self.titulo = titulo
        self.corpo = QVBoxLayout(self)
        self.corpo.setContentsMargins(14, 26 if titulo else 12, 14, 12)
        self.corpo.setSpacing(4)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        c = 10
        caminho = QPainterPath()
        caminho.moveTo(r.left() + c, r.top())
        caminho.lineTo(r.right() - c, r.top())
        caminho.lineTo(r.right(), r.top() + c)
        caminho.lineTo(r.right(), r.bottom() - c)
        caminho.lineTo(r.right() - c, r.bottom())
        caminho.lineTo(r.left() + c, r.bottom())
        caminho.lineTo(r.left(), r.bottom() - c)
        caminho.lineTo(r.left(), r.top() + c)
        caminho.closeSubpath()
        p.fillPath(caminho, _cor(AZUL, 10))
        p.setPen(_caneta(LINHA, 1.2))
        p.drawPath(caminho)
        p.setPen(_caneta(AZUL, 2.0))
        p.drawLine(QPointF(r.left() + c, r.top()), QPointF(r.left() + c + 40, r.top()))
        p.drawLine(QPointF(r.right() - c - 40, r.bottom()), QPointF(r.right() - c, r.bottom()))
        if self.titulo:
            p.setFont(Fontes.de(8.5, True, tech=True))
            p.setPen(_cor(AZUL))
            p.drawText(QRectF(r.left() + 14, r.top() + 5, r.width() - 28, 16),
                       Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self.titulo.upper())


class AnelRelogio(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(190, 190)

    def paintEvent(self, _):
        agora = dt.datetime.now()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        lado = min(self.width(), self.height()) - 12
        r = QRectF((self.width() - lado) / 2, (self.height() - lado) / 2, lado, lado)
        centro = r.center()
        brilho = QRadialGradient(centro, lado / 2)
        brilho.setColorAt(0.0, _cor(AZUL, 40))
        brilho.setColorAt(1.0, _cor(AZUL, 0))
        p.setBrush(brilho)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(r)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(_caneta(LINHA, 6))
        p.drawEllipse(r.adjusted(6, 6, -6, -6))
        segundos = agora.second + agora.microsecond / 1e6
        p.setPen(_caneta(AZUL, 6))
        p.drawArc(r.adjusted(6, 6, -6, -6), 90 * 16, int(-segundos / 60 * 360 * 16))
        p.setPen(_caneta(AZUL_ESCURO, 1.5))
        for i in range(60):
            ang = math.radians(i * 6)
            dentro = lado / 2 - (20 if i % 5 == 0 else 16)
            fora = lado / 2 - 12
            p.drawLine(QPointF(centro.x() + dentro * math.sin(ang), centro.y() - dentro * math.cos(ang)),
                       QPointF(centro.x() + fora * math.sin(ang), centro.y() - fora * math.cos(ang)))
        p.setPen(_cor(TEXTO))
        p.setFont(Fontes.de(11))
        p.drawText(QRectF(r.left(), centro.y() - lado * 0.30, r.width(), 22),
                   Qt.AlignmentFlag.AlignHCenter, MESES[agora.month - 1])
        p.setPen(_cor(AZUL_FORTE))
        p.setFont(Fontes.de(lado * 0.18, True))
        p.drawText(QRectF(r.left(), centro.y() - lado * 0.17, r.width(), lado * 0.28),
                   Qt.AlignmentFlag.AlignCenter, f"{agora.day:02d}")
        p.setPen(_cor(TEXTO))
        p.setFont(Fontes.de(10, tech=True))
        p.drawText(QRectF(r.left(), centro.y() + lado * 0.12, r.width(), 20),
                   Qt.AlignmentFlag.AlignHCenter, DIAS[agora.weekday()])
        p.setFont(Fontes.de(12, True, tech=True))
        p.setPen(_cor(AZUL))
        p.drawText(QRectF(r.left(), centro.y() + lado * 0.21, r.width(), 22),
                   Qt.AlignmentFlag.AlignHCenter, agora.strftime("%H:%M:%S"))


class AnelMedidor(QWidget):
    def __init__(self, titulo: str, alerta_quando_baixo: bool = False, parent=None):
        super().__init__(parent)
        self.titulo, self.valor, self.fracao, self.detalhe = titulo, "--", 0.0, ""
        self.alerta_quando_baixo = alerta_quando_baixo  # bateria: alerta quando está acabando
        self.setMinimumSize(110, 110)

    def definir(self, valor: str, fracao: float, detalhe: str = "") -> None:
        self.valor, self.fracao, self.detalhe = valor, max(0.0, min(1.0, fracao)), detalhe
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        lado = min(self.width(), self.height()) - 10
        r = QRectF((self.width() - lado) / 2, (self.height() - lado) / 2, lado, lado)
        p.setPen(_caneta(LINHA, 5))
        p.drawArc(r, 225 * 16, -270 * 16)
        alerta = self.fracao < 0.2 if self.alerta_quando_baixo else self.fracao > 0.9
        p.setPen(_caneta(AMBAR if alerta else AZUL, 5))
        p.drawArc(r, 225 * 16, int(-270 * self.fracao * 16))
        p.setPen(_cor(TEXTO))
        p.setFont(Fontes.de(8, tech=True))
        p.drawText(QRectF(r.left(), r.top() + lado * 0.22, r.width(), 14), Qt.AlignmentFlag.AlignHCenter, self.titulo)
        p.setPen(_cor(AZUL_FORTE))
        p.setFont(Fontes.de(max(9.0, lado * 0.12), True))
        p.drawText(QRectF(r.left(), r.top() + lado * 0.36, r.width(), lado * 0.3), Qt.AlignmentFlag.AlignCenter, self.valor)
        if self.detalhe:
            p.setPen(_cor(TEXTO, 200))
            p.setFont(Fontes.de(7.5, tech=True))
            p.drawText(QRectF(r.left(), r.top() + lado * 0.66, r.width(), 28),
                       Qt.AlignmentFlag.AlignHCenter, self.detalhe)


class BarraMedidor(QWidget):
    def __init__(self, titulo: str, parent=None):
        super().__init__(parent)
        self.titulo, self.fracao, self.texto = titulo, 0.0, "--"
        self.setFixedHeight(28)

    def definir(self, fracao: float, texto: str) -> None:
        self.fracao, self.texto = max(0.0, min(1.0, fracao)), texto
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = self.width()
        p.setFont(Fontes.de(8.5, tech=True))
        p.setPen(_cor(TEXTO))
        p.drawText(QRectF(0, 0, w * 0.6, 14), Qt.AlignmentFlag.AlignLeft, self.titulo)
        p.setPen(_cor(AZUL_FORTE))
        p.drawText(QRectF(w * 0.4, 0, w * 0.6, 14), Qt.AlignmentFlag.AlignRight, self.texto)
        base = QRectF(0, 17, w, 6)
        p.fillRect(base, _cor(LINHA))
        p.fillRect(QRectF(0, 17, w * self.fracao, 6), _cor(AMBAR if self.fracao > 0.9 else AZUL))
        p.setPen(_caneta(FUNDO, 1))
        for x in range(0, w, 6):
            p.drawLine(QPointF(x, 17), QPointF(x, 23))


class ReguaDias(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(30)

    def paintEvent(self, _):
        hoje = dt.date.today()
        total = calendar.monthrange(hoje.year, hoje.month)[1]
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        passo = self.width() / total
        p.setPen(_caneta(LINHA, 1))
        p.drawLine(QPointF(0, self.height() - 2), QPointF(self.width(), self.height() - 2))
        for dia in range(1, total + 1):
            x = (dia - 0.5) * passo
            destaque = dia == hoje.day
            p.setFont(Fontes.de(12 if destaque else 10, destaque, tech=True))
            p.setPen(_cor(AZUL_FORTE if destaque else AZUL_ESCURO))
            p.drawText(QRectF(x - passo / 2, 0, passo, self.height() - 6), Qt.AlignmentFlag.AlignCenter, f"{dia:02d}")
            if destaque:
                p.setPen(_caneta(AZUL_FORTE, 3))
                p.drawLine(QPointF(x - passo * 0.3, self.height() - 2), QPointF(x + passo * 0.3, self.height() - 2))


class Titulo(QWidget):
    def __init__(self, texto: str, tamanho: float = 22, parent=None):
        super().__init__(parent)
        self.texto, self.tamanho = texto, tamanho
        self.setFixedHeight(int(tamanho * 2))

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        fonte = Fontes.de(self.tamanho, True)
        fonte.setItalic(True)
        fonte.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 108)
        p.setFont(fonte)
        area = QRectF(self.rect())
        for deslocamento, alfa in ((3, 40), (1.5, 90)):
            p.setPen(_cor(AZUL, alfa))
            p.drawText(area.adjusted(-deslocamento, 0, -deslocamento, 0), Qt.AlignmentFlag.AlignCenter, self.texto)
        p.setPen(_cor(AZUL_FORTE))
        p.drawText(area, Qt.AlignmentFlag.AlignCenter, self.texto)


class BotaoRedondo(QPushButton):
    def __init__(self, simbolo: str, dica: str, parent=None):
        super().__init__(parent)
        self.simbolo = simbolo
        self.setToolTip(dica)
        self.setAccessibleName(dica)
        self.setFixedSize(64, 64)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._giro = 0.0

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(4, 4, -4, -4)
        ativo = self.underMouse() or self.isDown()
        p.setBrush(_cor(AZUL, 45 if ativo else 18))
        p.setPen(_caneta(AZUL if ativo else AZUL_ESCURO, 2.5))
        p.drawEllipse(r)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(_caneta(AZUL_FORTE, 3))
        p.drawArc(r.adjusted(5, 5, -5, -5), int((self._giro + 30) * 16), 70 * 16)
        p.drawArc(r.adjusted(5, 5, -5, -5), int((self._giro + 210) * 16), 70 * 16)
        p.setPen(_cor(AZUL_FORTE if ativo else AZUL))
        p.setFont(Fontes.de(17, True))
        p.drawText(r, Qt.AlignmentFlag.AlignCenter, self.simbolo)

    def girar(self, graus: float) -> None:
        self._giro = (self._giro + graus) % 360
        self.update()


def _lista_links(itens, ao_clicar) -> QWidget:
    caixa = QWidget()
    lay = QVBoxLayout(caixa)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(1)
    for nome, destino in itens:
        botao = QPushButton(f"▸  {nome}")
        botao.setCursor(Qt.CursorShape.PointingHandCursor)
        botao.setFont(Fontes.de(9.5))
        botao.setStyleSheet(
            f"QPushButton {{ color: {TEXTO}; background: transparent; border: none; text-align: left;"
            f" padding: 3px 2px; }} QPushButton:hover {{ color: {AZUL_FORTE}; }}")
        botao.clicked.connect(lambda _=False, d=destino: ao_clicar(d))
        lay.addWidget(botao)
    return caixa


def _rotulo(texto: str = "", tamanho: float = 9.5, cor: str = TEXTO, tech: bool = False) -> QLabel:
    rotulo = QLabel(texto)
    rotulo.setFont(Fontes.de(tamanho, tech=tech))
    rotulo.setStyleSheet(f"color: {cor}; background: transparent;")
    rotulo.setWordWrap(True)
    return rotulo


# ---------------------------------------------------------------- tela montada

class TelaStark(QWidget):
    """Envolve a área central original (esfera, legendas...) com os painéis Stark."""

    _clima_pronto = pyqtSignal(str)
    _noticias_prontas = pyqtSignal(list)

    def __init__(self, centro: QWidget, enviar_comando, pasta_dados: Path | None = None, parent=None):
        super().__init__(parent)
        self.enviar_comando = enviar_comando
        self.pasta = Path(pasta_dados or Path.home() / "Documents" / "Jarvis Ultron")
        self.sistema = Sistema()
        self.setStyleSheet("background: transparent;")

        geral = QVBoxLayout(self)
        geral.setContentsMargins(10, 4, 10, 4)
        geral.setSpacing(4)
        geral.addWidget(ReguaDias())

        meio = QHBoxLayout()
        meio.setSpacing(10)
        self.esquerda = self._montar_esquerda()
        self.direita = self._montar_direita()
        meio.addWidget(self.esquerda)
        centro_coluna = QVBoxLayout()
        centro_coluna.setSpacing(0)
        centro_coluna.addWidget(Titulo("JARVIS  ULTRON", 24))
        centro_coluna.addWidget(centro, stretch=1)
        meio.addLayout(centro_coluna, stretch=1)
        meio.addWidget(self.direita)
        geral.addLayout(meio, stretch=1)

        linha_botoes = QHBoxLayout()
        linha_botoes.setSpacing(14)
        linha_botoes.addStretch(1)
        self.botoes = []
        for simbolo, dica, comando in BOTOES:
            botao = BotaoRedondo(simbolo, dica)
            botao.clicked.connect(lambda _=False, c=comando: self._acionar(c))
            linha_botoes.addWidget(botao)
            self.botoes.append(botao)
        linha_botoes.addStretch(1)
        geral.addLayout(linha_botoes)

        self._clima_pronto.connect(self.clima.setText)
        self._noticias_prontas.connect(self._mostrar_noticias)

        self._relogio = QTimer(self)
        self._relogio.timeout.connect(self._a_cada_segundo)
        self._relogio.start(1000)
        self._animacao = QTimer(self)
        self._animacao.timeout.connect(self._girar_botoes)
        self._animacao.start(100)
        self._a_cada_segundo()
        self._buscar_da_internet()
        self._internet = QTimer(self)
        self._internet.timeout.connect(self._buscar_da_internet)
        self._internet.start(30 * 60 * 1000)

    def _girar_botoes(self):
        if self.isVisible() and not self.window().isMinimized():
            for b in self.botoes:
                b.girar(6)

    # ---- colunas
    def _montar_esquerda(self) -> QWidget:
        coluna = QWidget()
        coluna.setFixedWidth(270)
        lay = QVBoxLayout(coluna)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        self.relogio = AnelRelogio()
        lay.addWidget(self.relogio)

        info = Moldura("Sistema de arquivos")
        self.disco = BarraMedidor("Disco")
        info.corpo.addWidget(self.disco)
        self.disco_total = _rotulo("", 9, tech=True)
        info.corpo.addWidget(self.disco_total)
        self.ligado = _rotulo("", 9, tech=True)
        info.corpo.addWidget(self.ligado)
        lay.addWidget(info)

        aneis = QHBoxLayout()
        self.energia = AnelMedidor("ENERGIA", alerta_quando_baixo=True)
        self.rede = AnelMedidor("INTERNET")
        aneis.addWidget(self.energia)
        aneis.addWidget(self.rede)
        lay.addLayout(aneis)

        atalhos = Moldura("Atalhos")
        atalhos.corpo.addWidget(_lista_links(ATALHOS, webbrowser.open))
        lay.addWidget(atalhos, stretch=1)
        return coluna

    def _montar_direita(self) -> QWidget:
        coluna = QWidget()
        coluna.setFixedWidth(290)
        lay = QVBoxLayout(coluna)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        lay.addWidget(Titulo("STARK INDUSTRIES", 16))

        clima = Moldura(f"Clima · {os.environ.get('JARVIS_CIDADE', 'Campina Grande')}")
        self.clima = _rotulo("Carregando...", 10)
        clima.corpo.addWidget(self.clima)
        lay.addWidget(clima)

        sistema = Moldura("Sistema")
        self.cpu, self.ram, self.swap = BarraMedidor("CPU"), BarraMedidor("Memória"), BarraMedidor("Swap")
        for barra in (self.cpu, self.ram, self.swap):
            sistema.corpo.addWidget(barra)
        lay.addWidget(sistema)

        notas = Moldura("Bloco de notas")
        self.notas = QPlainTextEdit()
        self.notas.setFont(Fontes.de(9.5))
        self.notas.setStyleSheet(f"QPlainTextEdit {{ color: {TEXTO}; background: transparent; border: none; }}")
        self.notas.setPlaceholderText("Escreva aqui. Fica salvo sozinho.")
        self.notas.setPlainText(self._ler_notas())
        self._salvar_notas = QTimer(self)
        self._salvar_notas.setSingleShot(True)
        self._salvar_notas.timeout.connect(self._gravar_notas)
        self.notas.textChanged.connect(lambda: self._salvar_notas.start(800))
        notas.corpo.addWidget(self.notas)
        lay.addWidget(notas, stretch=1)

        noticias = Moldura("Notícias")
        self.noticias = QVBoxLayout()
        self.noticias.setSpacing(2)
        self.noticias.addWidget(_rotulo("Carregando...", 9))
        noticias.corpo.addLayout(self.noticias)
        lay.addWidget(noticias, stretch=1)
        return coluna

    # ---- ações
    def _acionar(self, comando: str) -> None:
        if comando == "@pasta":
            self.pasta.mkdir(parents=True, exist_ok=True)
            webbrowser.open(self.pasta.as_uri())
            return
        self.enviar_comando(comando)

    def _a_cada_segundo(self) -> None:
        self.relogio.update()
        d = self.sistema.atualizar()
        if not d:
            return
        total, livre = d.get("disco_total", 0), d.get("disco_livre", 0)
        self.disco.definir(d.get("disco_pct", 0) / 100, f"{d.get('disco_pct', 0):.0f}% usado")
        self.disco_total.setText(f"Livre: {_tamanho(livre)} de {_tamanho(total)}")
        self.ligado.setText(f"Tempo ligado: {_duracao(d.get('ligado', 0))}")
        self.energia.definir(f"{d['energia']:.0f}%", d["energia"] / 100, "na tomada" if d["na_tomada"] else "bateria")
        self.rede.definir(_tamanho(d["recebido"]) + "/s", min(1.0, d["recebido"] / (5 * 1024 * 1024)),
                          f"↑ {_tamanho(d['envio'])}/s")
        self.cpu.definir(d["cpu"] / 100, f"{d['cpu']:.0f}%")
        self.ram.definir(d["ram"] / 100, f"{d['ram']:.0f}%")
        self.swap.definir(d["swap"] / 100, f"{d['swap']:.0f}%")

    def _buscar_da_internet(self) -> None:
        cidade = os.environ.get("JARVIS_CIDADE", "Campina Grande")

        def trabalhar():
            try:
                self._clima_pronto.emit(buscar_clima(cidade))
            except Exception:
                self._clima_pronto.emit("Sem conexão com o serviço de clima.")
            try:
                self._noticias_prontas.emit(buscar_noticias())
            except Exception:
                self._noticias_prontas.emit([])

        threading.Thread(target=trabalhar, daemon=True).start()

    def _mostrar_noticias(self, itens: list) -> None:
        while self.noticias.count():
            widget = self.noticias.takeAt(0).widget()
            if widget:
                widget.deleteLater()
        if not itens:
            self.noticias.addWidget(_rotulo("Sem conexão com as notícias.", 9))
            return
        self.noticias.addWidget(_lista_links(itens, webbrowser.open))

    # ---- notas
    def _arquivo_notas(self) -> Path:
        return self.pasta / "notas.txt"

    def _ler_notas(self) -> str:
        try:
            return self._arquivo_notas().read_text(encoding="utf-8")
        except OSError:
            return ""

    def _gravar_notas(self) -> None:
        self.pasta.mkdir(parents=True, exist_ok=True)
        self._arquivo_notas().write_text(self.notas.toPlainText(), encoding="utf-8")


def ligada() -> bool:
    return os.environ.get("JARVIS_TEMA_STARK", "1").strip().lower() not in {"0", "false", "no", "off", "nao", "não"}


def montar_tela_stark(janela, centro: QWidget, fonte_ui: str, fonte_tech: str) -> QWidget:
    """Chamada pela janela principal: devolve a área central envolvida pelos painéis Stark."""
    Fontes.ui, Fontes.tech = fonte_ui, fonte_tech
    return TelaStark(centro, enviar_comando=janela._send)
