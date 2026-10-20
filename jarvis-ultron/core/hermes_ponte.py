"""Ponte entre o Jarvis Ultron (voz) e o Hermes Agent (orquestrador com sub-agentes).

- perguntar(): manda um pedido para o Hermes (API local em http://127.0.0.1:8642) e devolve a
  resposta pronta para ser falada.
- aprovar_e_executar(): em duas chamadas. A primeira guarda a proposta (o Jarvis conta ao Erton o
  que vai ser publicado); a segunda só passa com um "ok" claro numa fala NOVA dele depois disso
  (core/aprovacao.py). Aí, em segundo plano, confere o "ok" de novo com a fala inteira, abre a trava
  de aprovação do Hermes, pede para ele publicar/executar só o que foi aprovado e fecha a trava
  assim que ele termina.

O "Instalar Hermes.bat" preenche no .env: HERMES_API_URL, HERMES_API_KEY e HERMES_JARVIS_HOME.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
import unicodedata
from datetime import datetime
from pathlib import Path

JANELA_APROVACAO = 10 * 60  # no máximo isso com a trava aberta (ela fecha quando o Hermes termina)
VALIDADE_PROPOSTA = 10 * 60  # segundos que a proposta contada ao Erton espera o "ok" dele
TEMPO_MAXIMO = 15 * 60  # tarefas de agentes podem demorar

# O "ok" tem que ser curto e COMEÇAR com uma destas. "publica"/"posta" sozinhos não contam
# ("o que a gente posta hoje?"), nem um "ok" no meio da frase.
PALAVRAS_OK = (
    "ok", "okay", "okey", "sim", "aprovo", "aprovado", "aprovada", "autorizo", "autorizado", "confirmo",
    "confirmado", "pode sim", "pode fazer", "pode publicar", "pode postar", "pode mandar", "pode aplicar",
    "pode seguir", "pode agendar", "manda ver", "manda bala",
)
# Depois de um "ok"/"sim", ou vem uma destas ações...
ACOES_OK = tuple(p for p in PALAVRAS_OK if p not in ("ok", "okay", "okey", "sim"))
# ...ou só palavras como estas ("ok, entendi" e "ok, o Claude terminou" não são aprovação).
COMPLEMENTOS_OK = {"ok", "okay", "okey", "sim", "pode", "isso", "mesmo", "claro", "certo", "beleza",
                   "perfeito", "faz", "faca", "manda", "vai", "agora", "ja", "por", "favor", "ai"}
# Palavras de chamar ou de enrolar antes do "ok" ("Jarvis, ok", "beleza, pode fazer")
VOCATIVOS = {"hey", "ei", "oi", "jarvis"}
ANTES_DO_OK = {"beleza", "certo", "claro", "entao", "bom", "ta", "fechado", "perfeito", "show", "otimo"}
# Negação, adiamento, espera, condição, dúvida ou preço: nada disso é "ok" ("ok, pode cancelar",
# "sim, mas tá caro", "ok, pode fazer amanhã", "ok pode fazer, peraí"). Na dúvida o Jarvis pergunta de novo.
PALAVRAS_NAO = ("nao", "cancel", "esquec", "deix", "desist", "depois", "pens", "aguard", "aguent", "esper",
                "negativ", "jamais", "nunca", "duvid", "talvez", "amanh", "seman", "daqui", "tard", "noit",
                "madrugad", "minut", "instant", "moment", "sabad", "doming")  # começos de palavra
PALAVRAS_NAO_EXATAS = {"n", "nem", "num", "para", "pare", "parar", "paro", "mas", "caro", "cara", "caros",
                       "caras", "calma", "segura", "nope", "pera", "perai", "mes", "meses", "hora", "horas",
                       "dia", "dias", "segunda", "terca", "quarta", "quinta", "sexta", "feira", "antes", "se",
                       "quando"}
FRASES_NAO = ("mais tarde", "outro dia", "outra hora", "logo mais")
MAX_PALAVRAS_OK = 8

DEMOROU = "O Hermes demorou demais para responder. A tarefa pode continuar rodando; pergunte de novo daqui a pouco."
SEM_HERMES = ("O Hermes ainda não está configurado. Dê dois cliques em 'Instalar Hermes' na pasta "
              "do Jarvis Ultron e depois abra o Jarvis de novo.")


def _normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", (texto or "").lower())
    return " ".join("".join(c for c in texto if not unicodedata.combining(c)).split())


def usuario_aprovou(fala: str) -> bool:
    """True só se a fala do Erton for um "ok" claro: curta, começando com uma aprovação, sem
    pergunta e sem negação, adiamento ou dúvida. Na dúvida, não é aprovação (o Jarvis pergunta de
    novo). Exemplos que NÃO valem: "ok, pode cancelar", "ok, deixa pra depois", "sim, mas tá caro",
    "ok, entendi", "ok, quanto fica em euro?", "o que a gente posta hoje?"."""
    bruto = str(fala or "")
    if "?" in bruto:
        return False
    palavras = [p for p in re.sub(r"[^a-z0-9 ]", " ", _normalizar(bruto)).split() if p != "jarvis"]
    while palavras and (palavras[0] in VOCATIVOS or palavras[0] in ANTES_DO_OK):
        palavras.pop(0)
    if not palavras or len(palavras) > MAX_PALAVRAS_OK:
        return False
    texto = f" {' '.join(palavras)} "
    if any(p in PALAVRAS_NAO_EXATAS or p.startswith(PALAVRAS_NAO) for p in palavras):
        return False
    if any(f" {f} " in texto for f in FRASES_NAO):
        return False
    if not any(texto.startswith(f" {p} ") for p in PALAVRAS_OK):
        return False
    return any(f" {p} " in texto for p in ACOES_OK) or all(p in COMPLEMENTOS_OK for p in palavras)


def configurado() -> bool:
    return bool(os.environ.get("HERMES_API_KEY", "").strip())


def enderecos() -> list[str]:
    """Onde procurar o perfil jarvis. O Hermes novo atende todos os perfis num serviço só, e o do
    Jarvis fica em .../p/jarvis; o Hermes antigo (ou perfil separado) atende direto na porta."""
    base = os.environ.get("HERMES_API_URL", "http://127.0.0.1:8642").strip().rstrip("/")
    raiz = base.split("/p/")[0]
    return list(dict.fromkeys([base, raiz + "/p/jarvis", raiz]))


def perguntar(pedido: str, tempo_maximo: float = TEMPO_MAXIMO) -> str:
    if not configurado():
        return SEM_HERMES
    import requests

    resposta = None
    desligado = True
    for endereco in enderecos():
        try:
            tentativa = requests.post(
                endereco + "/v1/chat/completions",
                headers={"Authorization": f"Bearer {os.environ['HERMES_API_KEY'].strip()}"},
                json={"model": "hermes-agent", "messages": [{"role": "user", "content": pedido}]},
                timeout=(5, tempo_maximo),  # 5s para conectar (falha rápido e tenta o próximo endereço)
            )
        except requests.exceptions.ConnectionError:
            continue
        except requests.exceptions.Timeout:
            return DEMOROU
        desligado = False
        resposta = tentativa
        if tentativa.status_code not in (401, 404):  # 401/404: endereço errado para este perfil
            break
    if desligado:
        return ("O Hermes está desligado. Ele liga sozinho com o Windows; se não ligou, abra o "
                "'Instalar Hermes' de novo ou reinicie o computador.")
    if resposta.status_code in (401, 404):
        return "O Hermes não reconheceu o Jarvis (chave ou endereço). Rode o 'Instalar Hermes' de novo."
    if resposta.status_code >= 400:
        return f"O Hermes respondeu com erro {resposta.status_code}: {resposta.text[:200]}"
    try:
        return resposta.json()["choices"][0]["message"]["content"].strip() or "Pronto."
    except (ValueError, KeyError, IndexError):
        return "O Hermes respondeu num formato inesperado."


def arquivo_aprovacao() -> Path:
    pasta = os.environ.get("HERMES_JARVIS_HOME", "").strip()
    return Path(pasta) / "jarvis" / "aprovacao.json"


_trava_arquivo = threading.Lock()


def registrar_aprovacao(tipo: str, agora: float | None = None) -> float:
    """Libera a trava do Hermes para 'redes' (posts) ou 'anuncios' por no máximo JANELA_APROVACAO
    segundos. Devolve até quando (para fechar_aprovacao)."""
    agora = agora or time.time()
    arquivo = arquivo_aprovacao()
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    with _trava_arquivo:
        try:
            dados = json.loads(arquivo.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            dados = {}
        dados[tipo] = {"ate": agora + JANELA_APROVACAO, "em": datetime.fromtimestamp(agora).isoformat(timespec="seconds")}
        arquivo.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
    return dados[tipo]["ate"]


def fechar_aprovacao(tipo: str, ate: float) -> None:
    """Fecha a trava de novo assim que o Hermes terminou o que foi aprovado: o "ok" vale para aquela
    tarefa, não para qualquer publicação nos minutos seguintes. Não mexe se outro "ok" foi registrado
    depois (outro 'ate')."""
    arquivo = arquivo_aprovacao()
    with _trava_arquivo:
        try:
            dados = json.loads(arquivo.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if not isinstance(dados.get(tipo), dict) or dados[tipo].get("ate") != ate:
            return
        dados[tipo]["ate"] = 0
        arquivo.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")


def _avisar(jarvis, texto: str) -> None:
    """Conta o resultado ao Erton (respeita o modo chamada) ou, sem isso, só mostra na tela."""
    anunciar = getattr(jarvis, "anunciar", None)
    if callable(anunciar):
        anunciar(texto, "Hermes")
        return
    ui = getattr(jarvis, "ui", None)
    if ui is not None:
        ui.write_log(f"Hermes: {texto[:500]}")


_proposta: dict = {}
_trava = threading.Lock()


def aprovar_e_executar(tipo: str, detalhes: str, jarvis, confirmar: bool = False) -> str:
    """confirmar=False: guarda a proposta (o Jarvis conta ao Erton o que vai ser feito e pede o ok).
    confirmar=True: só publica se for a mesma proposta, recente, e o Erton disse um "ok" claro numa
    fala NOVA depois de ouvi-la (a frase do pedido ou uma fala antiga não valem). O ok vale uma vez.
    A publicação roda em segundo plano (_publicar) e o resultado é contado ao Erton quando sair."""
    from core import aprovacao

    if tipo not in ("redes", "anuncios"):
        return "Tipo de aprovação inválido. Use 'redes' (posts) ou 'anuncios'."
    if not configurado():
        return SEM_HERMES
    chave = (tipo, _normalizar(detalhes))
    if not confirmar:
        with _trava:
            _proposta.clear()
            _proposta.update(chave=chave, em=time.monotonic(), marca=aprovacao.marca(jarvis))
        return ("Proposta registrada, nada foi publicado ainda. Diga ao usuário, em português, exatamente o que "
                "vai ser publicado ou mudado e pergunte se pode. Só depois de ele aprovar com as palavras dele "
                "(por exemplo 'ok, pode publicar'), chame de novo com confirm=true e o mesmo kind e details.")
    with _trava:
        proposta_ok = (_proposta.get("chave") == chave
                       and time.monotonic() - _proposta.get("em", 0) < VALIDADE_PROPOSTA)
        fala_do_ok = aprovacao.fala_que_aprovou(jarvis, _proposta.get("marca", 0)) if proposta_ok else 0
        proposta = dict(_proposta)
        if fala_do_ok:
            _proposta.clear()
    if not proposta_ok:
        return ("Não registrei aprovação: primeiro chame com confirm=false e exatamente o que vai ser "
                "publicado, conte isso ao usuário e espere o ok dele.")
    if not fala_do_ok:
        return ("Não registrei aprovação: o usuário precisa dizer claramente, depois de ouvir a proposta, "
                "por exemplo 'ok, pode publicar'. Pergunte a ele antes.")
    # em segundo plano: no Gemini ao vivo o resto da fala do "ok" só chega depois que a ferramenta
    # responde (o laço que recebe a transcrição fica parado enquanto ela roda)
    threading.Thread(target=_publicar, args=(tipo, detalhes, jarvis, fala_do_ok, proposta),
                     daemon=True, name="HermesPublicar").start()
    return ("Aprovado. O Hermes está publicando em segundo plano só o que foi aprovado. Diga ao usuário, em uma "
            "frase curta em português, que você avisa quando terminar. Não chame ferramentas de novo para isso.")


def _publicar(tipo: str, detalhes: str, jarvis, fala_do_ok: int, proposta: dict) -> None:
    from core import aprovacao

    # A ferramenta pode ter chegado com só o começo da resposta transcrito ("Ok," ... "pode
    # cancelar"): antes de abrir a trava do Hermes, confere de novo com a fala inteira.
    if not aprovacao.ainda_aprovado(jarvis, fala_do_ok):
        with _trava:
            if not _proposta:  # a proposta continua valendo para um "ok" claro numa fala nova
                _proposta.update(proposta, marca=aprovacao.marca(jarvis))
        _avisar(jarvis, "Não publiquei nada: a sua resposta não foi um 'ok' claro. Se quiser publicar, "
                        "diga 'ok, pode publicar'.")
        return
    ate = registrar_aprovacao(tipo)
    skill = "publicar-aprovados" if tipo == "redes" else "anuncios-meta"
    try:
        resposta = perguntar(f"O usuário aprovou agora ({tipo}): {detalhes}. Use a skill {skill} e execute "
                             "somente o que foi aprovado.")
    except Exception as erro:  # nunca deixa o fio morrer calado
        resposta = f"O Hermes falhou: {str(erro)[:160]}"
    if resposta != DEMOROU:  # demorou: a tarefa pode seguir rodando (a trava fecha sozinha no prazo)
        fechar_aprovacao(tipo, ate)
    _avisar(jarvis, resposta)
