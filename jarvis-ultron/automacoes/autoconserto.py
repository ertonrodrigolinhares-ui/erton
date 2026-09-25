"""Autoconserto do Jarvis Ultron (automação: salve na pasta 'automacoes' e reabra o Jarvis).

Diga: "Jarvis, conserte seus problemas" (ou "faça o autoconserto").
Ele roda o autodiagnóstico, conserta sozinho o que é seguro consertar, confere de novo e diz o que
consertou e o que ainda depende de você. Nunca mexe em chaves, senhas ou arquivos seus.

O que ele conserta sozinho:
  - Hermes desligado → liga o serviço do Hermes e espera ele responder;
  - chave do Gemini recusada → liga a reserva Groq (se houver chave do Groq);
  - memória do computador cheia → baixa a qualidade gráfica da tela;
  - navegador automático faltando → instala o Chromium das automações;
  - "Hey Jarvis" sem detector → passa para o modo mãos livres;
  - automação com defeito na pasta 'automacoes' → desliga só ela (põe "_" no nome).
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

FERRAMENTA = {
    "name": "self_repair",
    "description": (
        "Runs JARVIS's self-repair: diagnoses the system and automatically fixes what is safe to fix "
        "(restarts Hermes, switches to the Groq backup, lowers graphics quality, installs the automation "
        "browser, enables hands-free if the wake word failed, disables a broken automation file). Use when "
        "the user asks JARVIS to fix/repair itself or its problems. Then tell the user in Portuguese what "
        "was fixed and what still needs them."
    ),
    "parameters": {"type": "OBJECT", "properties": {}},
}


def _consertar_hermes() -> str:
    from core import autodiagnostico
    from core.automacoes import _hermes

    hermes = _hermes()
    if not hermes:
        return ""
    resultado = subprocess.run([hermes, "gateway", "restart"], capture_output=True, text=True, timeout=120)
    if resultado.returncode != 0:
        subprocess.run([hermes, "gateway", "start"], capture_output=True, text=True, timeout=120)
    for _ in range(12):
        time.sleep(5)
        if autodiagnostico.verificar_hermes().estado == "ok":
            return "liguei o Hermes"
    return ""


def _consertar_navegador() -> str:
    resultado = subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"],
                               capture_output=True, text=True, timeout=900)
    return "instalei o navegador das automações" if resultado.returncode == 0 else ""


def _desligar_automacao_com_defeito() -> str:
    from core.automacoes import carregar_ferramentas, pasta_padrao

    desligadas = []
    for arquivo, _motivo in carregar_ferramentas().erros:
        caminho = pasta_padrao() / arquivo
        if caminho.exists() and caminho.name != Path(__file__).name:
            caminho.rename(caminho.with_name("_" + caminho.name))
            desligadas.append(arquivo)
    return f"desliguei a automação com defeito {', '.join(desligadas)}" if desligadas else ""


def consertar(itens, jarvis) -> list[str]:
    """Aplica os consertos seguros para os itens com problema. Devolve o que foi feito."""
    feitos = []
    for item in itens:
        if item.estado == "ok":
            continue
        feito = ""
        try:
            if item.nome == "Hermes (agentes)" and "desligado" in item.detalhe:
                feito = _consertar_hermes()
            elif item.nome == "Chave do Gemini" and item.estado == "defeito":
                reserva = getattr(jarvis, "_reserva", None)
                if reserva is not None and not getattr(jarvis, "_modo_reserva", False):
                    jarvis._ativar_modo_reserva()
                    feito = "liguei a reserva Groq enquanto a chave do Gemini não funciona"
            elif item.nome == "Computador" and "memória" in item.detalhe:
                ui = getattr(jarvis, "ui", None)
                if ui is not None and hasattr(ui, "set_graphics_quality"):
                    ui.set_graphics_quality("low")
                    feito = "baixei a qualidade gráfica para aliviar a memória"
            elif item.nome == "Navegador automático":
                feito = _consertar_navegador()
            elif item.nome == "Escuta" and "detector" in item.detalhe:
                jarvis._definir_modo_escuta("maos_livres")
                feito = "passei para o modo mãos livres, porque o 'Hey Jarvis' não carregou"
            elif item.nome == "Automações" and item.estado == "defeito":
                feito = _desligar_automacao_com_defeito()
        except Exception as erro:
            print(f"[Autoconserto] {item.nome}: {erro}")
        if feito:
            feitos.append(feito)
    return feitos


def executar(args: dict, jarvis) -> str:
    from core import autodiagnostico

    antes = autodiagnostico.diagnosticar(getattr(jarvis, "_portao", None))
    feitos = consertar(antes, jarvis)
    depois = autodiagnostico.diagnosticar(getattr(jarvis, "_portao", None)) if feitos else antes
    relatorio = autodiagnostico.relatorio(depois)
    try:
        autodiagnostico.salvar(relatorio)
    except OSError:
        pass
    pendentes = [f"{i.nome}: {i.detalhe}. {i.dica}".strip() for i in depois if i.estado != "ok"]
    partes = []
    partes.append("Consertei: " + "; ".join(feitos) + "." if feitos else "Não havia nada que eu pudesse consertar sozinho.")
    if pendentes:
        partes.append("Ainda precisa de você: " + " | ".join(pendentes))
    else:
        partes.append("Agora está tudo funcionando.")
    return " ".join(partes) + "\nTell the user this in Portuguese, briefly."
