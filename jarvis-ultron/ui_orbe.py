"""Jarvis Ultron: visual "Orbe".

Três peças por cima da tela do Jarvis:
- Orbe: anel de energia feito de fios de luz entrelaçados, no lugar da esfera
  antiga. Reage à voz (cresce e brilha quando o Jarvis fala) e mostra no topo
  o estado em português (FALANDO, OUVINDO, PENSANDO...).
- Biometria: quando o usuário diz "bom dia", a câmera abre dentro do anel,
  procura um rosto e mostra "PRESENÇA CONFIRMADA". Tudo local: nenhuma imagem
  é gravada nem enviada.
- Resumo do dia: cartões flutuantes com clima, lembretes, notícias e e-mails.

Configurações (.env):
- JARVIS_VISUAL=classico  volta para a esfera antiga.
- JARVIS_BIOMETRIA=0      pula a câmera no "bom dia".
- JARVIS_NOME=Erton       nome usado na saudação dos cartões.
"""

from __future__ import annotations

import datetime as dt
import json
import math
import os
import random
import re
import threading
import time
import unicodedata
from pathlib import Path

from PyQt6.QtCore import QEasingCurve, QObject, QPointF, QPropertyAnimation, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QFont, QImage, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap, QRadialGradient
from PyQt6.QtWidgets import QGraphicsOpacityEffect, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

AZUL = "#1f7bff"        # fio principal
CIANO = "#00c8ff"       # brilho
GELO = "#cfefff"        # destaque dos fios
FUNDO = "#010812"
GRADE = "#0b2a4a"
TEXTO = "#e8f8ff"
TEXTO2 = "#7fb8d6"
VERDE = "#00ff9c"

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


def cor(h: str, a: int = 255) -> QColor:
    c = QColor(h)
    c.setAlpha(max(0, min(255, int(a))))
    return c


def _sem_acento(texto: str) -> str:
    return unicodedata.normalize("NFD", texto).encode("ascii", "ignore").decode().lower()


# ---------------------------------------------------------------- orbe

class Orbe:
    """Desenha o anel de fios de energia dentro do HudCanvas."""

    FIOS = 22
    PONTOS = 150

    def __init__(self):
        rnd = random.Random(7)
        self.fios = []
        for i in range(self.FIOS):
            harm = []
            for _ in range(3):
                harm.append((rnd.randint(2, 5), rnd.uniform(0.012, 0.04), rnd.uniform(0, math.tau), rnd.uniform(-0.9, 0.9)))
            self.fios.append({
                "harm": harm,
                "raio": rnd.uniform(0.9, 1.06),
                "achat": rnd.uniform(0.78, 1.0),       # achatamento: dá a sensação de volume
                "giro": rnd.uniform(0, math.pi),
                "vel_giro": rnd.uniform(-0.25, 0.25),
                "largura": rnd.uniform(0.7, 1.3),
                "fase_brilho": rnd.uniform(0, math.tau),
            })
        # Faíscas que correm pelos fios
        self.faiscas = [(rnd.randrange(self.FIOS), rnd.uniform(0, math.tau), rnd.uniform(0.25, 0.7)) for _ in range(18)]
        self._inicio = time.time()

    def _ponto(self, fio: dict, ang: float, t: float, R: float, cx: float, cy: float, agito: float) -> QPointF:
        r = fio["raio"]
        for k, amp, fase, vel in fio["harm"]:
            r += amp * agito * math.sin(k * ang + fase + t * vel)
        x = math.cos(ang) * r
        y = math.sin(ang) * r * fio["achat"]
        g = fio["giro"] + t * fio["vel_giro"] * 0.2
        xr = x * math.cos(g) - y * math.sin(g)
        yr = x * math.sin(g) + y * math.cos(g)
        return QPointF(cx + xr * R, cy + yr * R)

    def pintar(self, hud, p: QPainter) -> None:
        W, H = hud.width(), hud.height()
        cx, cy = W / 2, H / 2
        fw = min(W, H)
        t = time.time() - self._inicio
        voz = getattr(hud, "_nivel_suave", 0.0)
        falando = bool(hud.speaking) and not hud.muted
        pensando = hud.state in ("THINKING", "PROCESSING")
        estilo_leve = getattr(hud, "_render_stride", 1) > 1

        # Fundo: azul profundo com grade, como numa sala escura
        fundo = QRadialGradient(QPointF(cx, cy), max(W, H) * 0.75)
        fundo.setColorAt(0.0, cor("#062048"))
        fundo.setColorAt(0.55, cor("#03112a"))
        fundo.setColorAt(1.0, cor(FUNDO))
        p.fillRect(hud.rect(), fundo)
        passo = max(28, int(fw / 16))
        p.setPen(QPen(cor(GRADE, 70), 1))
        x = cx % passo
        while x < W:
            p.drawLine(QPointF(x, 0), QPointF(x, H)); x += passo
        y = cy % passo
        while y < H:
            p.drawLine(QPointF(0, y), QPointF(W, y)); y += passo

        # Tamanho e agitação seguem o estado e o volume da voz
        R = fw * 0.27 * (1.0 + 0.10 * voz) * getattr(hud, "_scale", 1.0) ** 0.5
        agito = 1.0 + (1.4 * voz if falando else 0.0) + (0.4 if pensando else 0.0)
        velocidade = 1.0 + (1.2 if pensando else 0.0) + (0.8 * voz if falando else 0.0)
        tt = t * velocidade
        brilho = 0.65 + 0.35 * (voz if falando else 0.0) + (0.15 if pensando else 0.0)
        if hud.muted:
            brilho *= 0.45

        # Halo central
        halo = QRadialGradient(QPointF(cx, cy), R * 1.5)
        halo.setColorAt(0.0, cor(AZUL, 40 * brilho))
        halo.setColorAt(0.6, cor(AZUL, 22 * brilho))
        halo.setColorAt(1.0, cor(AZUL, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(halo))
        p.drawEllipse(QPointF(cx, cy), R * 1.5, R * 1.5)

        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
        passo_ang = math.tau / (self.PONTOS // (2 if estilo_leve else 1))
        fios = self.fios[:: 2 if estilo_leve else 1]
        caminhos = []
        for fio in fios:
            cam = QPainterPath()
            ang = 0.0
            cam.moveTo(self._ponto(fio, ang, tt, R, cx, cy, agito))
            while ang < math.tau:
                ang += passo_ang
                cam.lineTo(self._ponto(fio, ang, tt, R, cx, cy, agito))
            cam.closeSubpath()
            pulso = 0.6 + 0.4 * math.sin(t * 1.3 + fio["fase_brilho"])
            caminhos.append((cam, fio, pulso))

        p.setBrush(Qt.BrushStyle.NoBrush)
        if not estilo_leve:
            for cam, fio, pulso in caminhos:  # brilho largo
                p.setPen(QPen(cor(CIANO, 18 * brilho * pulso), fio["largura"] * 7))
                p.drawPath(cam)
        for cam, fio, pulso in caminhos:      # fio azul
            p.setPen(QPen(cor(AZUL, 150 * brilho * pulso), fio["largura"] * 1.8))
            p.drawPath(cam)
        for cam, fio, pulso in caminhos:      # miolo claro
            p.setPen(QPen(cor(GELO, 110 * brilho * pulso), max(0.6, fio["largura"] * 0.6)))
            p.drawPath(cam)

        # Faíscas correndo pelos fios
        for i, ang0, vel in self.faiscas:
            fio = self.fios[i]
            ang = ang0 + tt * vel
            pt = self._ponto(fio, ang, tt, R, cx, cy, agito)
            g = QRadialGradient(pt, 9)
            g.setColorAt(0.0, cor("#ffffff", 200 * brilho))
            g.setColorAt(0.3, cor(CIANO, 120 * brilho))
            g.setColorAt(1.0, cor(CIANO, 0))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(g))
            p.drawEllipse(pt, 9, 9)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

        # Estado no topo, em português
        estado = "MUDO" if hud.muted else ("FALANDO" if hud.speaking else ESTADOS_PT.get(hud.state, hud.state))
        f = QFont("Consolas", 10, QFont.Weight.Bold)
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 5)
        p.setFont(f)
        topo = max(18.0, cy - R * 1.55)
        cor_estado = cor(VERDE if hud.speaking else CIANO, 230)
        p.setPen(QPen(cor_estado, 1))
        p.drawText(QRectF(0, topo, W, 20), Qt.AlignmentFlag.AlignCenter, estado)
        linha = QLinearGradient(QPointF(cx - 90, 0), QPointF(cx + 90, 0))
        linha.setColorAt(0.0, cor(CIANO, 0)); linha.setColorAt(0.5, cor(CIANO, 160)); linha.setColorAt(1.0, cor(CIANO, 0))
        p.setPen(QPen(QBrush(linha), 1))
        p.drawLine(QPointF(cx - 90, topo + 24), QPointF(cx + 90, topo + 24))

        # Botão-núcleo embaixo, como no vídeo
        by = min(H - 26.0, cy + R * 1.45)
        p.setPen(QPen(cor(CIANO, 150), 1.4))
        p.setBrush(QBrush(cor("#06244a", 220)))
        p.drawEllipse(QPointF(cx, by), 13, 13)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(cor(CIANO, 140 + 100 * (0.5 + 0.5 * math.sin(t * 2.2)))))
        p.drawEllipse(QPointF(cx, by), 4.5, 4.5)


# ---------------------------------------------------------------- câmera

def _indice_camera() -> int:
    try:
        from ui import API_FILE
        dados = json.loads(API_FILE.read_text(encoding="utf-8")) if API_FILE.exists() else {}
        return int(dados.get("camera_index", 0))
    except Exception:
        return 0


def _detector_rosto(cv2):
    nomes = ["haarcascade_frontalface_default.xml"]
    pastas = []
    dados = getattr(cv2, "data", None)
    if dados is not None and getattr(dados, "haarcascades", None):
        pastas.append(Path(dados.haarcascades))
    pastas.append(Path(cv2.__file__).parent / "data")
    for pasta in pastas:
        for nome in nomes:
            arq = pasta / nome
            if arq.exists():
                det = cv2.CascadeClassifier(str(arq))
                if not det.empty():
                    return det
    return None


class _LeitorCamera(threading.Thread):
    """Lê a câmera fora da tela, para a janela não travar enquanto ela liga."""

    def __init__(self):
        super().__init__(daemon=True)
        self.quadro = None          # último quadro (BGR)
        self.rostos = 0             # quantos quadros seguidos tiveram rosto
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

    concluida = pyqtSignal(bool)   # True = rosto encontrado

    PRAZO = 9.0

    def __init__(self, hud):
        super().__init__(hud)
        self.hud = hud
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._leitor = None
        self._px = None
        self._fase = "busca"      # busca | ok | falhou
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
                self._terminar(False); return
            if lt.quadro is not None:
                self._px = self._para_pixmap(lt.quadro)
            confirmou = lt.rostos >= 4 or (lt.pronta and not lt.tem_detector and agora - self._t0 > 2.5 and lt.quadro is not None)
            if confirmou:
                self._fase, self._t_fim = "ok", agora
            elif agora - self._t0 > self.PRAZO:
                self._fase, self._t_fim = "falhou", agora
        elif agora - self._t_fim > 1.4:
            self._terminar(self._fase == "ok"); return
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
        r = min(W, H) * 0.15
        agora = time.time()

        f = QFont("Consolas", 8, QFont.Weight.Bold)
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 3)
        p.setFont(f)
        self._legenda(p, c.y() - r - 44, "◦ IDENTIFICAÇÃO BIOMÉTRICA — LOCAL", CIANO)

        # Foto recortada em círculo
        cam = QPainterPath(); cam.addEllipse(c, r, r)
        p.save(); p.setClipPath(cam)
        if self._px is not None:
            p.drawPixmap(QRectF(c.x() - r, c.y() - r, 2 * r, 2 * r), self._px, QRectF(self._px.rect()))
        else:
            p.fillRect(QRectF(c.x() - r, c.y() - r, 2 * r, 2 * r), cor("#031a38", 230))
            p.setPen(QPen(cor(TEXTO2, 200), 1))
            p.drawText(QRectF(c.x() - r, c.y() - 8, 2 * r, 16), Qt.AlignmentFlag.AlignCenter, "LIGANDO CÂMERA")
        if self._fase == "busca":  # linha de varredura
            yv = c.y() - r + (2 * r) * (0.5 + 0.5 * math.sin((agora - self._t0) * 2.4))
            g = QLinearGradient(QPointF(0, yv - 14), QPointF(0, yv + 2))
            g.setColorAt(0.0, cor(CIANO, 0)); g.setColorAt(1.0, cor(CIANO, 150))
            p.fillRect(QRectF(c.x() - r, yv - 14, 2 * r, 16), QBrush(g))
        p.restore()

        ok = self._fase == "ok"
        tom = VERDE if ok else ("#ff5566" if self._fase == "falhou" else CIANO)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(cor(tom, 230), 3))
        p.drawEllipse(c, r + 6, r + 6)
        p.setPen(QPen(cor(tom, 90), 1.2))
        giro = (agora - self._t0) * 90
        p.drawArc(QRectF(c.x() - r - 16, c.y() - r - 16, 2 * r + 32, 2 * r + 32), int(giro * 16), 100 * 16)
        p.drawArc(QRectF(c.x() - r - 16, c.y() - r - 16, 2 * r + 32, 2 * r + 32), int((giro + 180) * 16), 100 * 16)

        texto = {"busca": "PROCURANDO ROSTO", "ok": "PRESENÇA CONFIRMADA", "falhou": "ROSTO NÃO ENCONTRADO"}[self._fase]
        self._legenda(p, c.y() + r + 30, texto, tom)

    def _legenda(self, p: QPainter, y: float, texto: str, tom: str) -> None:
        """Texto com fundo escuro, para ler bem por cima dos fios de luz."""
        largura = p.fontMetrics().horizontalAdvance(texto) + 24
        caixa = QRectF((self.width() - largura) / 2, y - 3, largura, 22)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(cor("#020c1c", 200)))
        p.drawRoundedRect(caixa, 4, 4)
        p.setPen(QPen(cor(tom, 235), 1))
        p.drawText(caixa, Qt.AlignmentFlag.AlignCenter, texto)


# ---------------------------------------------------------------- resumo do dia

def _clima() -> dict:
    cidade = os.environ.get("JARVIS_CIDADE", "Campina Grande")
    try:
        from ui_stark import buscar_clima
        linhas = buscar_clima(cidade).splitlines()
        return {"cidade": cidade, "linhas": linhas}
    except Exception:
        return {"cidade": cidade, "linhas": [], "erro": "Clima indisponível agora."}


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
            itens.append(f"{remetente}: {cab.get('subject', '(sem assunto)')}")
        return {"conectado": True, "total": total, "itens": itens}
    except Exception:
        return {"conectado": True, "total": 0, "itens": [], "erro": "Não consegui ler a caixa agora."}


def juntar_resumo() -> dict:
    """Busca tudo ao mesmo tempo (roda fora da tela)."""
    saida = {}
    tarefas = {"clima": _clima, "noticias": _noticias, "lembretes": _lembretes_hoje, "emails": _emails}
    fios = []
    for nome, fn in tarefas.items():
        th = threading.Thread(target=lambda n=nome, f=fn: saida.__setitem__(n, f()), daemon=True)
        th.start(); fios.append(th)
    for th in fios:
        th.join(timeout=20)
    saida.setdefault("clima", {"cidade": os.environ.get("JARVIS_CIDADE", "Campina Grande"), "linhas": []})
    saida.setdefault("noticias", []); saida.setdefault("lembretes", []); saida.setdefault("emails", {"conectado": False, "itens": []})
    return saida


DIAS = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"]
MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"]


class Cartao(QWidget):
    """Cartão de vidro escuro com borda ciano."""

    def __init__(self, rotulo: str, titulo: str, parent=None, destaque: bool = False):
        super().__init__(parent)
        self.destaque = destaque
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 14)
        lay.setSpacing(4)
        r = QLabel(rotulo.upper())
        r.setStyleSheet(f"color:{TEXTO2}; font: 600 8pt 'Consolas'; letter-spacing: 2px; background: transparent;")
        t = QLabel(titulo)
        t.setWordWrap(True)
        t.setStyleSheet(f"color:{TEXTO}; font: 600 {'15' if destaque else '12'}pt 'Segoe UI'; background: transparent;")
        lay.addWidget(r); lay.addWidget(t)
        self.corpo = lay

    def linha(self, texto: str, cor_txt: str = TEXTO2, tamanho: int = 9, negrito: bool = False) -> QLabel:
        l = QLabel(texto)
        l.setWordWrap(True)
        l.setStyleSheet(f"color:{cor_txt}; font: {'600' if negrito else '400'} {tamanho}pt 'Segoe UI'; background: transparent;")
        self.corpo.addWidget(l)
        return l

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        g = QLinearGradient(r.topLeft(), r.bottomLeft())
        g.setColorAt(0.0, cor("#0a2446", 235)); g.setColorAt(1.0, cor("#051430", 235))
        p.setBrush(QBrush(g))
        p.setPen(QPen(cor(CIANO, 150 if self.destaque else 90), 1.2))
        p.drawRoundedRect(r, 8, 8)
        p.setPen(QPen(cor(CIANO, 220), 2))
        p.drawLine(QPointF(r.left() + 12, r.top()), QPointF(r.left() + 52, r.top()))


class Resumo(QWidget):
    """Painel do resumo do dia, flutuando sobre o anel."""

    dados_prontos = pyqtSignal(dict)

    def __init__(self, hud):
        super().__init__(hud)
        self.hud = hud
        self.dados_prontos.connect(self._montar)
        self._fechar_timer = QTimer(self)
        self._fechar_timer.setSingleShot(True)
        self._fechar_timer.timeout.connect(self.fechar)
        self._anims = []
        self.hide()

    def carregar(self, presenca: bool):
        self._presenca = presenca
        self._limpar()
        self._carregando = QLabel("Preparando seu resumo do dia...", self)
        self._carregando.setStyleSheet(f"color:{CIANO}; font: 600 11pt 'Consolas'; background: transparent;")
        self._carregando.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay = QVBoxLayout(self) if self.layout() is None else self.layout()
        lay.addWidget(self._carregando)
        self._encaixar(); self.show(); self.raise_()
        threading.Thread(target=lambda: self.dados_prontos.emit(juntar_resumo()), daemon=True).start()

    def _limpar(self):
        lay = self.layout()
        if lay is None:
            return
        while lay.count():
            item = lay.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
            elif item.layout() is not None:
                sub = item.layout()
                while sub.count():
                    s = sub.takeAt(0)
                    if s.widget() is not None:
                        s.widget().deleteLater()

    def _encaixar(self):
        W, H = self.hud.width(), self.hud.height()
        lw = int(min(W * 0.86, 760))
        lh = int(min(H * 0.82, 560))
        topo = max(int(H * 0.14), int((H - lh) / 2))
        self.setGeometry(int((W - lw) / 2), topo, lw, min(lh, H - topo - 8))

    def _montar(self, d: dict):
        self._limpar()
        lay = self.layout()
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)

        hoje = dt.date.today()
        nome = os.environ.get("JARVIS_NOME", "").strip()
        saud = "Bom dia" + (f", {nome}" if nome else "")
        emails = d["emails"]
        partes = []
        if d["lembretes"]:
            partes.append(f"{len(d['lembretes'])} lembrete(s) hoje")
        if emails.get("conectado") and "total" in emails:
            partes.append(f"{emails['total']} e-mail(s) não lido(s)")
        resumo_txt = " · ".join(partes) if partes else "Nada urgente pedindo sua atenção."

        topo = Cartao(f"Parecer do dia · {DIAS[hoje.weekday()]}, {hoje.day} de {MESES[hoje.month - 1]}", saud, self, destaque=True)
        topo.linha(resumo_txt, TEXTO, 10)
        if self._presenca:
            topo.linha("Presença confirmada pela câmera.", VERDE, 8)
        fechar = QPushButton("×", topo)
        fechar.setCursor(Qt.CursorShape.PointingHandCursor)
        fechar.setFixedSize(26, 26)
        fechar.setStyleSheet(f"QPushButton{{color:{TEXTO2}; background:transparent; border:1px solid #1a5c7a; border-radius:13px; font:12pt;}}"
                             f"QPushButton:hover{{color:{TEXTO}; border-color:{CIANO};}}")
        fechar.clicked.connect(self.fechar)
        fechar.move(1, 1)
        topo.resizeEvent = lambda e, b=fechar, c=topo: b.move(c.width() - 36, 10)

        clima = d["clima"]
        c1 = Cartao(f"Clima · {clima['cidade']}", (clima["linhas"][0] if clima["linhas"] else "Sem dados"), self)
        for l in clima["linhas"][1:4]:
            c1.linha(l)
        if clima.get("erro"):
            c1.linha(clima["erro"])

        c2 = Cartao("Agenda de hoje", f"{len(d['lembretes'])} lembrete(s)" if d["lembretes"] else "Dia livre", self)
        for l in d["lembretes"] or ["Nenhum lembrete marcado para hoje."]:
            c2.linha(l)

        c3 = Cartao("Pedem sua atenção · e-mail", "", self)
        if not emails.get("conectado"):
            c3.corpo.itemAt(1).widget().setText("Gmail não conectado")
            c3.linha('Diga: "conectar o Gmail" para ver seus e-mails aqui.')
        else:
            c3.corpo.itemAt(1).widget().setText(f"{emails.get('total', 0)} não lido(s)")
            for l in emails["itens"] or [emails.get("erro", "Caixa de entrada em dia.")]:
                c3.linha("• " + l)

        c4 = Cartao("Radar de notícias", "Manchetes agora", self)
        for n in d["noticias"] or ["Sem notícias no momento."]:
            c4.linha("• " + n)

        lay.addWidget(topo)
        linha1 = QHBoxLayout(); linha1.setSpacing(10); linha1.addWidget(c1, 1); linha1.addWidget(c2, 1)
        linha2 = QHBoxLayout(); linha2.setSpacing(10); linha2.addWidget(c3, 1); linha2.addWidget(c4, 1)
        lay.addLayout(linha1); lay.addLayout(linha2); lay.addStretch(1)

        # Os cartões aparecem um de cada vez
        self._anims = []
        for i, w in enumerate([topo, c1, c2, c3, c4]):
            ef = QGraphicsOpacityEffect(w); ef.setOpacity(0.0); w.setGraphicsEffect(ef)
            an = QPropertyAnimation(ef, b"opacity", self)
            an.setDuration(450); an.setStartValue(0.0); an.setEndValue(1.0)
            an.setEasingCurve(QEasingCurve.Type.OutExpo)
            QTimer.singleShot(180 * i, an.start)
            self._anims.append(an)
        self._fechar_timer.start(90_000)

    def fechar(self):
        self._fechar_timer.stop()
        self.hide()
        self._limpar()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape:
            self.fechar()


# ---------------------------------------------------------------- controle

class ControleOrbe(QObject):
    """Liga o orbe ao HUD e dispara o ritual do "bom dia"."""

    _pedido = pyqtSignal()
    GATILHO = re.compile(r"\bbom\s+dia\b")

    def __init__(self, win):
        super().__init__(win)
        self.win = win
        self.hud = win.hud
        self.hud._orbe = Orbe()
        self.biometria = Biometria(self.hud)
        self.resumo = Resumo(self.hud)
        self.biometria.concluida.connect(self.resumo.carregar)
        self._pedido.connect(self.bom_dia)
        self._rodando_desde = 0.0
        antigo = self.hud.resizeEvent

        def ao_redimensionar(ev, antigo=antigo):
            antigo(ev)
            if self.biometria.isVisible():
                self.biometria._encaixar()
            if self.resumo.isVisible():
                self.resumo._encaixar()
        self.hud.resizeEvent = ao_redimensionar

    def ver_texto(self, texto: str) -> None:
        """Chamado a cada linha do log (de qualquer thread)."""
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
