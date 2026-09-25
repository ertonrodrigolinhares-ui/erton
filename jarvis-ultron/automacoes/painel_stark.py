"""Central de missões na tela Stark (automação: salve na pasta 'automacoes' e reabra o Jarvis).

Acrescenta um painel na coluna da direita da tela Stark com:
  - o próximo lembrete (e o painel pisca em âmbar quando um lembrete toca);
  - as atividades pendentes do Geekie (quantas e quantas vencem logo);
  - o estado dos agentes: voz (Gemini ou reserva Groq) e Hermes (ligado ou desligado);
  - um botão para cada rotina salva (clique para o Jarvis fazer a rotina).

Não fala nada e quase não gasta computador: atualiza a cada 5 segundos, e o Hermes a cada 1 minuto.
Para tirar o painel, apague este arquivo (ou coloque "_" no começo do nome).
Funciona junto com os arquivos lembretes.py e rotinas.py (sem eles, mostra só o resto).
"""

from __future__ import annotations

import json
import threading
import time
from datetime import date, datetime, timedelta
from pathlib import Path

ATUALIZAR_MS = 5000
HERMES_A_CADA = 60  # segundos
ALERTA_POR = 90  # segundos que o painel fica âmbar depois de um lembrete

_montado = threading.Event()


# ---------------------------------------------------------------- dados (sem tela; fáceis de testar)

def pasta_dados() -> Path:
    return Path.home() / "Documents" / "Jarvis Ultron"


def _json(nome: str) -> dict:
    try:
        dados = json.loads((pasta_dados() / nome).read_text(encoding="utf-8"))
        return dados if isinstance(dados, dict) else {}
    except (OSError, ValueError):
        return {}


def texto_lembrete(agora: datetime | None = None) -> tuple[str, bool]:
    """(linha do próximo lembrete, se um lembrete acabou de tocar)."""
    agora = agora or datetime.now()
    dados = _json("lembretes.json")
    alerta = False
    ultimo = dados.get("ultimo_aviso") or {}
    try:
        alerta = (agora - datetime.fromisoformat(ultimo.get("em", ""))).total_seconds() <= ALERTA_POR
    except (TypeError, ValueError):
        pass
    if alerta:
        return "⚠ " + str(ultimo.get("texto", ""))[:70], True
    itens = sorted(dados.get("lembretes") or [], key=lambda l: l.get("quando", ""))
    if not itens:
        return "Nenhum lembrete marcado", False
    proximo = itens[0]
    try:
        quando = datetime.fromisoformat(proximo["quando"])
    except (KeyError, ValueError):
        return "Nenhum lembrete marcado", False
    if quando.date() == agora.date():
        dia = "hoje"
    elif quando.date() == agora.date() + timedelta(days=1):
        dia = "amanhã"
    else:
        dia = f"{quando:%d/%m}"
    extra = f"  (+{len(itens) - 1})" if len(itens) > 1 else ""
    return f"{dia} {quando:%H:%M} · {str(proximo.get('texto', ''))[:48]}{extra}", False


def texto_geekie(hoje: date | None = None) -> str:
    try:
        from core import geekie

        atividades, atualizado = geekie.ler()
    except Exception:
        return "Geekie: indisponível"
    if atualizado is None and not atividades:
        return "Geekie: sem lista ainda"
    hoje = hoje or date.today()
    abertas = geekie.abertas(atividades)
    if not abertas:
        return "Geekie: nada pendente ✓"
    logo = [a for a in abertas if a.prazo is not None and (a.prazo - hoje).days <= geekie.DIAS_AVISO]
    return f"Geekie: {len(abertas)} pendente{'s' if len(abertas) > 1 else ''}" + (
        f" · {len(logo)} vence{'m' if len(logo) > 1 else ''} logo" if logo else "")


def texto_voz(jarvis) -> tuple[str, bool]:
    if getattr(jarvis, "_modo_reserva", False):
        return "Voz: reserva (Groq)", False
    if getattr(jarvis, "session", None) is None:
        return "Voz: conectando...", False
    return "Voz: Gemini ao vivo", True


def nomes_rotinas() -> list[str]:
    rotinas = _json("rotinas.json").get("rotinas")
    if isinstance(rotinas, dict):
        return sorted(rotinas)[:6]
    if not (pasta_dados() / "rotinas.json").exists():
        return ["bom dia", "fim do dia"]  # as prontas do rotinas.py
    return []


# ---------------------------------------------------------------- painel

def _montar(jarvis) -> None:
    janela = getattr(getattr(jarvis, "ui", None), "_win", None)
    tela = getattr(janela, "_tela_stark", None)
    if tela is None:
        print("[Painel Stark] A tela Stark está desligada; painel não mostrado.")
        return
    import ui_stark as us
    from PyQt6.QtCore import QRectF, QTimer
    from PyQt6.QtGui import QPainter
    from PyQt6.QtWidgets import QHBoxLayout, QPushButton, QWidget

    class MolduraAlerta(us.Moldura):
        alerta = False

        def paintEvent(self, evento):
            super().paintEvent(evento)
            if self.alerta:
                p = QPainter(self)
                p.setRenderHint(QPainter.RenderHint.Antialiasing)
                p.setPen(us._caneta(us.AMBAR, 2.2))
                p.drawRoundedRect(QRectF(self.rect()).adjusted(2, 2, -2, -2), 6, 6)

    painel = MolduraAlerta("Central de missões")
    lembrete = us._rotulo("", 9.5)
    geekie_ = us._rotulo("", 9, tech=True)
    linha_agentes = QHBoxLayout()
    voz = us._rotulo("", 8.5, tech=True)
    hermes = us._rotulo("Hermes: ...", 8.5, tech=True)
    linha_agentes.addWidget(voz)
    linha_agentes.addWidget(hermes)
    botoes = QWidget()
    linha_botoes = QHBoxLayout(botoes)
    linha_botoes.setContentsMargins(0, 2, 0, 0)
    linha_botoes.setSpacing(4)
    painel.corpo.addWidget(lembrete)
    painel.corpo.addWidget(geekie_)
    painel.corpo.addLayout(linha_agentes)
    painel.corpo.addWidget(botoes)

    estado = {"hermes": None, "hermes_em": 0.0, "rotinas": None, "buscando": False}

    def ver_hermes():
        try:
            from core import autodiagnostico

            item = autodiagnostico.verificar_hermes()
            estado["hermes"] = (item.estado == "ok", "ligado" if item.estado == "ok" else
                                ("não instalado" if "instalado" in item.detalhe else "desligado"))
        except Exception:
            estado["hermes"] = (False, "sem resposta")
        finally:
            estado["buscando"] = False

    def pintar(rotulo, texto, cor):
        us_cor = {"ok": us.VERDE, "ruim": us.AMBAR, "normal": us.TEXTO}[cor]
        if rotulo.text() != texto:
            rotulo.setText(texto)
        rotulo.setStyleSheet(f"color: {us_cor}; background: transparent;")

    def refazer_botoes(nomes):
        while linha_botoes.count():
            widget = linha_botoes.takeAt(0).widget()
            if widget:
                widget.deleteLater()
        for nome in nomes:
            botao = QPushButton(f"▸ {nome}")
            botao.setToolTip(f"Rodar a rotina '{nome}'")
            botao.setFont(us.Fontes.de(8.5, tech=True))
            botao.setStyleSheet(
                f"QPushButton {{ color: {us.TEXTO}; background: transparent; border: 1px solid {us.AZUL_ESCURO};"
                f" border-radius: 9px; padding: 1px 7px; }} QPushButton:hover {{ color: {us.AZUL_FORTE};"
                f" border-color: {us.AZUL_FORTE}; }}")
            botao.clicked.connect(lambda _=False, n=nome: tela.enviar_comando(f"rotina {n}"))
            linha_botoes.addWidget(botao)
        linha_botoes.addStretch(1)

    def atualizar():
        if not painel.isVisible() or painel.window().isMinimized():
            return
        texto, alerta = texto_lembrete()
        pintar(lembrete, "◷ " + texto, "ruim" if alerta else "normal")
        if painel.alerta != alerta:
            painel.alerta = alerta
            painel.update()
        texto_g = texto_geekie()
        pintar(geekie_, "✎ " + texto_g, "ruim" if "logo" in texto_g else "normal")
        texto_v, ok_v = texto_voz(jarvis)
        pintar(voz, texto_v, "ok" if ok_v else "ruim")
        if estado["hermes"] is not None:
            ok_h, detalhe = estado["hermes"]
            pintar(hermes, f"Hermes: {detalhe}", "ok" if ok_h else "ruim")
        if time.monotonic() - estado["hermes_em"] > HERMES_A_CADA and not estado["buscando"]:
            estado["hermes_em"], estado["buscando"] = time.monotonic(), True
            threading.Thread(target=ver_hermes, daemon=True, name="PainelHermes").start()
        nomes = nomes_rotinas()
        if nomes != estado["rotinas"]:
            estado["rotinas"] = nomes
            refazer_botoes(nomes)

    coluna = tela.direita.layout()
    coluna.insertWidget(min(3, coluna.count()), painel)  # depois de "Sistema", antes do bloco de notas
    relogio = QTimer(painel)
    relogio.timeout.connect(atualizar)
    relogio.start(ATUALIZAR_MS)
    QTimer.singleShot(300, atualizar)
    tela._central_de_missoes = painel


def iniciar(jarvis) -> None:
    if _montado.is_set():
        return
    _montado.set()
    from core.na_tela import executar

    executar(lambda: _montar(jarvis))
