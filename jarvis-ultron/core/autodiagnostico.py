"""Autodiagnóstico do Jarvis Ultron: confere as próprias peças e diz o que está com defeito.

Cada verificação é rápida (poucos segundos no máximo), não mostra chave nenhuma e devolve:
  - nome: o que foi verificado;
  - estado: "ok", "atencao" ou "defeito";
  - detalhe: o que foi encontrado;
  - dica: como resolver (vazio quando está tudo certo).

Funciona mesmo com o Gemini fora do ar: pode ser pedido por texto/botão ("diagnóstico") e
o resultado vai para a tela, para a voz e para Documentos/Jarvis Ultron/diagnostico.txt.
"""

from __future__ import annotations

import os
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable


@dataclass
class Item:
    nome: str
    estado: str  # "ok" | "atencao" | "defeito"
    detalhe: str
    dica: str = ""


def _seguro(nome: str, verificar: Callable[[], Item]) -> Item:
    try:
        return verificar()
    except Exception as erro:  # uma verificação quebrada nunca derruba as outras
        return Item(nome, "atencao", f"não consegui verificar ({str(erro)[:80]})")


# ---------------------------------------------------------------- verificações

def verificar_internet() -> Item:
    import socket

    try:
        socket.create_connection(("8.8.8.8", 53), timeout=3).close()
        return Item("Internet", "ok", "conectado")
    except OSError:
        return Item("Internet", "defeito", "sem conexão com a internet",
                    "Confira o Wi-Fi ou o cabo. Sem internet o Gemini, o Hermes e o clima não funcionam.")


def verificar_gemini() -> Item:
    from core import modelos

    chave = modelos._chave()
    if not chave:
        return Item("Chave do Gemini", "defeito", "nenhuma chave configurada",
                    "Abra o Jarvis e cole a chave na tela, ou coloque GEMINI_API_KEY no arquivo .env.")
    try:
        from google import genai

        cliente = genai.Client(api_key=chave, http_options={"api_version": "v1beta", "timeout": 8000})
        modelos_da_chave = list(cliente.models.list())
    except Exception as erro:
        texto = str(erro)
        if "ACCESS_TOKEN_TYPE_UNSUPPORTED" in texto:
            return Item("Chave do Gemini", "defeito",
                        "o Google recusou a chave (defeito do Google nas chaves 'AQ.')",
                        "Crie a chave com outro Gmail de adulto, ou use o botão 'Continuar com a reserva (Groq)'.")
        if "401" in texto or "API_KEY_INVALID" in texto or "not valid" in texto.lower():
            return Item("Chave do Gemini", "defeito", "chave recusada (inválida, apagada ou antiga)",
                        "Crie uma chave nova em aistudio.google.com/apikey e cole na tela do Jarvis.")
        if "429" in texto or "quota" in texto.lower():
            return Item("Chave do Gemini", "atencao", "limite grátis do dia atingido",
                        "Espere algumas horas; enquanto isso o Jarvis usa a reserva Groq.")
        return Item("Chave do Gemini", "atencao", f"não consegui falar com o Google ({texto[:80]})",
                    "Confira a internet e tente de novo em alguns minutos.")
    vivos = [m for m in modelos_da_chave
             if "bidigeneratecontent" in {str(a).lower() for a in (getattr(m, "supported_actions", None) or [])}]
    if not vivos:
        return Item("Chave do Gemini", "defeito", "a chave funciona, mas não tem modelo de voz ao vivo",
                    "Crie a chave num projeto novo do AI Studio.")
    return Item("Chave do Gemini", "ok", f"aceita pelo Google ({len(modelos_da_chave)} modelos disponíveis)")


def verificar_modelos() -> Item:
    from core import modelos

    if not modelos.listar():
        return Item("Modelos do Gemini", "atencao", "não deu para ver os modelos (a chave não respondeu)",
                    "Resolva primeiro a chave do Gemini.")
    voz = modelos.resolver("gemini-live-native-audio")
    texto = modelos.resolver("gemini-flash")
    detalhe = f"voz: {voz} | texto: {texto}"
    if modelos._versao(voz) and modelos._versao(voz) < modelos.VERSAO_MINIMA:
        return Item("Modelos do Gemini", "atencao", detalhe + " (a voz ainda é 2.5, que o Google está aposentando)",
                    "Normal se o Google ainda não liberou voz 3.x para a sua chave; o Jarvis troca sozinho quando liberar.")
    return Item("Modelos do Gemini", "ok", detalhe)


def verificar_groq() -> Item:
    chave = os.environ.get("GROQ_API_KEY", "").strip()
    if not chave:
        return Item("Reserva Groq", "atencao", "sem chave do Groq",
                    "Opcional: sem ela não há reserva quando o Gemini cai. Crie em console.groq.com/keys.")
    import requests

    try:
        resposta = requests.get("https://api.groq.com/openai/v1/models",
                                headers={"Authorization": f"Bearer {chave}"}, timeout=6)
    except requests.RequestException:
        return Item("Reserva Groq", "atencao", "não consegui falar com o Groq agora")
    if resposta.status_code == 401:
        return Item("Reserva Groq", "defeito", "chave do Groq recusada (apagada ou errada)",
                    "Crie uma chave nova em console.groq.com/keys e troque GROQ_API_KEY no .env.")
    if resposta.status_code >= 400:
        return Item("Reserva Groq", "atencao", f"o Groq respondeu com erro {resposta.status_code}")
    return Item("Reserva Groq", "ok", "chave aceita")


def verificar_hermes() -> Item:
    from core import hermes_ponte

    if not hermes_ponte.configurado():
        return Item("Hermes (agentes)", "atencao", "não instalado ou não ligado ao Jarvis",
                    "Dê dois cliques em 'Instalar Hermes' na pasta do Jarvis.")
    import requests

    chave = os.environ.get("HERMES_API_KEY", "").strip()
    desligado = True
    for endereco in hermes_ponte.enderecos():
        try:
            resposta = requests.get(endereco + "/v1/models", headers={"Authorization": f"Bearer {chave}"},
                                    timeout=3)
        except requests.RequestException:
            continue
        desligado = False
        if resposta.status_code == 200:
            return Item("Hermes (agentes)", "ok", "ligado e respondendo")
    if desligado:
        return Item("Hermes (agentes)", "defeito", "o Hermes está desligado",
                    "Dê dois cliques em 'Ligar Hermes' na pasta do Jarvis.")
    return Item("Hermes (agentes)", "defeito", "o Hermes não reconheceu o Jarvis (chave ou endereço)",
                "Rode o 'Instalar Hermes' de novo e depois o 'Ligar Hermes'.")


def verificar_audio() -> list[Item]:
    import sounddevice as sd

    itens = []
    try:
        entrada = sd.query_devices(kind="input")
        itens.append(Item("Microfone", "ok", str(entrada.get("name", "encontrado"))))
    except Exception:
        itens.append(Item("Microfone", "defeito", "nenhum microfone encontrado",
                          "Conecte um microfone ou libere o acesso em Configurações do Windows > Privacidade > Microfone."))
    try:
        saida = sd.query_devices(kind="output")
        itens.append(Item("Alto-falante", "ok", str(saida.get("name", "encontrado"))))
    except Exception:
        itens.append(Item("Alto-falante", "defeito", "nenhuma saída de som encontrada",
                          "Confira se o som do computador está ligado e com um alto-falante ou fone escolhido."))
    return itens


def verificar_computador() -> Item:
    import psutil

    ram = psutil.virtual_memory().percent
    raiz = os.environ.get("SystemDrive", "C:") + "\\" if os.name == "nt" else "/"
    disco = psutil.disk_usage(raiz).percent
    detalhe = f"memória {ram:.0f}%, disco {disco:.0f}%"
    if ram >= 92 or disco >= 95:
        return Item("Computador", "defeito", detalhe + " (muito cheio)",
                    "Feche programas e abas que não está usando; se o disco estiver cheio, apague arquivos grandes.")
    if ram >= 85 or disco >= 90:
        return Item("Computador", "atencao", detalhe,
                    "Está apertado: fechar abas do navegador e dizer 'qualidade gráfica baixa' ajuda.")
    return Item("Computador", "ok", detalhe)


def verificar_navegador() -> Item:
    try:
        import playwright  # noqa: F401
    except ImportError:
        return Item("Navegador automático", "defeito", "componente do navegador não instalado",
                    "Apague a pasta .venv do Jarvis e abra o 'Iniciar Jarvis Ultron' de novo para reinstalar.")
    pastas = []
    if os.environ.get("PLAYWRIGHT_BROWSERS_PATH"):
        pastas.append(Path(os.environ["PLAYWRIGHT_BROWSERS_PATH"]))
    if os.name == "nt":
        pastas.append(Path(os.environ.get("LOCALAPPDATA", "")) / "ms-playwright")
    pastas.append(Path.home() / ".cache" / "ms-playwright")
    if any(p.exists() and any(p.glob("chromium*")) for p in pastas):
        return Item("Navegador automático", "ok", "instalado")
    return Item("Navegador automático", "atencao", "o Chromium das automações não foi encontrado",
                "Os sites ainda abrem no navegador normal; para o Jarvis clicar sozinho, reinstale os componentes.")


def verificar_escuta(portao) -> Item:
    if portao is None:
        return Item("Escuta", "atencao", "não iniciada")
    if portao.detector is None and portao.modo == "chamada":
        return Item("Escuta", "defeito", "o detector do 'Hey Jarvis' não carregou",
                    "Use o botão MÃOS LIVRES; para consertar, reinstale os componentes (apague a pasta .venv).")
    modo = "mãos livres" if portao.modo == "maos_livres" else "modo chamada (diga 'Hey Jarvis')"
    return Item("Escuta", "ok", modo)


def verificar_automacoes() -> Item:
    from core.automacoes import carregar_ferramentas, pasta_padrao

    carga = carregar_ferramentas()
    pasta = pasta_padrao()
    extras = [p.name for p in pasta.glob("*.md") if p.name.lower() not in {"leia-me.md", "readme.md"}] \
        if pasta.is_dir() else []
    total = len(carga.ferramentas) + len(extras)
    if carga.erros:
        arquivo, motivo = carga.erros[0]
        return Item("Automações", "defeito", f"{arquivo}: {motivo}",
                    "Confira esse arquivo na pasta 'automacoes' ou tire ele de lá.")
    return Item("Automações", "ok", f"{total} na pasta 'automacoes'" if total else "nenhuma instalada")


# ---------------------------------------------------------------- relatório

def diagnosticar(portao=None, conferir_internet: bool = True) -> list[Item]:
    itens = [_seguro("Internet", verificar_internet)] if conferir_internet else []
    itens += [
        _seguro("Chave do Gemini", verificar_gemini),
        _seguro("Modelos do Gemini", verificar_modelos),
        _seguro("Reserva Groq", verificar_groq),
        _seguro("Hermes (agentes)", verificar_hermes),
    ]
    try:
        itens += verificar_audio()
    except Exception as erro:
        itens.append(Item("Som", "atencao", f"não consegui verificar ({str(erro)[:60]})"))
    itens += [
        _seguro("Computador", verificar_computador),
        _seguro("Navegador automático", verificar_navegador),
        _seguro("Escuta", lambda: verificar_escuta(portao)),
        _seguro("Automações", verificar_automacoes),
    ]
    return itens


_ICONE = {"ok": "OK", "atencao": "ATENÇÃO", "defeito": "DEFEITO"}


def relatorio(itens: list[Item]) -> str:
    linhas = [f"Autodiagnóstico do Jarvis Ultron — {datetime.now():%d/%m/%Y %H:%M}", ""]
    for item in itens:
        linhas.append(f"[{_ICONE[item.estado]}] {item.nome}: {item.detalhe}")
        if item.dica:
            linhas.append(f"    → {item.dica}")
    return "\n".join(linhas)


def resumo_falado(itens: list[Item]) -> str:
    """Frase curta para a voz: só o que precisa de atenção."""
    problemas = [i for i in itens if i.estado == "defeito"] + [i for i in itens if i.estado == "atencao"]
    if not problemas:
        return "Fiz o autodiagnóstico: está tudo funcionando, senhor."
    partes = []
    for item in problemas[:4]:
        partes.append(f"{item.nome}: {item.detalhe}." + (f" {item.dica}" if item.dica else ""))
    total = len(problemas)
    inicio = f"Fiz o autodiagnóstico e encontrei {total} ponto{'s' if total > 1 else ''} para ver. "
    return inicio + " ".join(partes)


def salvar(texto: str, pasta: Path | None = None) -> Path:
    pasta = Path(pasta or Path.home() / "Documents" / "Jarvis Ultron")
    pasta.mkdir(parents=True, exist_ok=True)
    arquivo = pasta / "diagnostico.txt"
    arquivo.write_text(texto + "\n", encoding="utf-8")
    return arquivo


def pediu_diagnostico(fala: str) -> bool:
    texto = unicodedata.normalize("NFKD", (fala or "").lower())
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return bool(re.search(r"\b(auto ?diagnostico|diagnostico|diagnostique|verifique (o )?(seu )?sistema|"
                          r"o que (esta|tem) (com )?defeito|checar? (o )?sistema)\b", texto))
