"""Ponte entre o Jarvis Ultron (voz) e o Hermes Agent (orquestrador com sub-agentes).

- perguntar(): manda um pedido para o Hermes (API local em http://127.0.0.1:8642) e devolve a
  resposta pronta para ser falada.
- aprovar_e_executar(): em duas chamadas. A primeira guarda a proposta (o Jarvis conta ao Erton o
  que vai ser publicado); a segunda só passa com um "ok" claro numa fala NOVA dele depois disso
  (core/aprovacao.py). Aí registra o "ok" por alguns minutos (é o que libera a trava de aprovação
  do Hermes) e pede para o Hermes publicar/executar o que foi aprovado.

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

JANELA_APROVACAO = 10 * 60  # segundos em que o "ok" vale
VALIDADE_PROPOSTA = 10 * 60  # segundos que a proposta contada ao Erton espera o "ok" dele
TEMPO_MAXIMO = 15 * 60  # tarefas de agentes podem demorar

# O "ok" tem que ser curto e COMEÇAR com uma destas. "publica"/"posta" sozinhos não contam
# ("o que a gente posta hoje?"), nem um "ok" no meio da frase.
PALAVRAS_OK = (
    "ok", "okay", "okey", "sim", "aprovo", "aprovado", "aprovada", "autorizo", "autorizado", "confirmo",
    "confirmado", "pode sim", "pode fazer", "pode publicar", "pode postar", "pode mandar", "pode aplicar",
    "pode seguir", "manda ver", "manda bala",
)
# Depois de um "ok"/"sim", ou vem uma destas ações...
ACOES_OK = tuple(p for p in PALAVRAS_OK if p not in ("ok", "okay", "okey", "sim"))
# ...ou só palavras como estas ("ok, entendi" e "ok, o Claude terminou" não são aprovação).
COMPLEMENTOS_OK = {"ok", "okay", "okey", "sim", "pode", "isso", "mesmo", "claro", "certo", "beleza",
                   "perfeito", "faz", "faca", "manda", "vai", "agora", "ja", "por", "favor", "ai"}
# Palavras de chamar ou de enrolar antes do "ok" ("Jarvis, ok", "beleza, pode fazer")
VOCATIVOS = {"hey", "ei", "oi", "jarvis"}
ANTES_DO_OK = {"beleza", "certo", "claro", "entao", "bom", "ta", "fechado", "perfeito", "show", "otimo"}
# Negação, adiamento, dúvida ou preço: nada disso é "ok" ("ok, pode cancelar", "sim, mas tá caro")
PALAVRAS_NAO = ("nao", "cancel", "esquec", "deix", "desist", "depois", "pens", "aguard", "esper",
                "negativ", "jamais", "nunca", "duvid", "talvez")  # começos de palavra
PALAVRAS_NAO_EXATAS = {"n", "nem", "num", "para", "pare", "parar", "paro", "mas", "caro", "cara", "caros",
                       "caras", "calma", "segura", "nope"}
FRASES_NAO = ("mais tarde", "outro dia", "outra hora")
MAX_PALAVRAS_OK = 8

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
            return "O Hermes demorou demais para responder. A tarefa pode continuar rodando; pergunte de novo daqui a pouco."
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


def registrar_aprovacao(tipo: str, agora: float | None = None) -> None:
    """Libera a trava do Hermes para 'redes' (posts) ou 'anuncios' por JANELA_APROVACAO segundos."""
    agora = agora or time.time()
    arquivo = arquivo_aprovacao()
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    try:
        dados = json.loads(arquivo.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        dados = {}
    dados[tipo] = {"ate": agora + JANELA_APROVACAO, "em": datetime.fromtimestamp(agora).isoformat(timespec="seconds")}
    arquivo.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")


_proposta: dict = {}
_trava = threading.Lock()


def aprovar_e_executar(tipo: str, detalhes: str, jarvis, confirmar: bool = False) -> str:
    """confirmar=False: guarda a proposta (o Jarvis conta ao Erton o que vai ser feito e pede o ok).
    confirmar=True: só publica se for a mesma proposta, recente, e o Erton disse um "ok" claro numa
    fala NOVA depois de ouvi-la (a frase do pedido ou uma fala antiga não valem). O ok vale uma vez."""
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
        return ("Proposta registrada, nada foi publicado ainda. Diga ao Erton, em português, exatamente o que "
                "vai ser publicado ou mudado e pergunte se pode. Só depois de ele aprovar com as palavras dele "
                "(por exemplo 'ok, pode publicar'), chame de novo com confirm=true e o mesmo kind e details.")
    with _trava:
        proposta_ok = (_proposta.get("chave") == chave
                       and time.monotonic() - _proposta.get("em", 0) < VALIDADE_PROPOSTA)
        aprovado = proposta_ok and aprovacao.aprovou_depois(jarvis, _proposta.get("marca", 0))
        if aprovado:
            _proposta.clear()
    if not proposta_ok:
        return ("Não registrei aprovação: primeiro chame com confirm=false e exatamente o que vai ser "
                "publicado, conte isso ao Erton e espere o ok dele.")
    if not aprovado:
        return ("Não registrei aprovação: o Erton precisa dizer claramente, depois de ouvir a proposta, "
                "por exemplo 'ok, pode publicar'. Pergunte a ele antes.")
    registrar_aprovacao(tipo)
    skill = "publicar-aprovados" if tipo == "redes" else "anuncios-meta"
    return perguntar(f"O Erton aprovou agora ({tipo}): {detalhes}. Use a skill {skill} e execute "
                     "somente o que foi aprovado.")
