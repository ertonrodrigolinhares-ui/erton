"""Central de modelos do Gemini (Jarvis Ultron).

O projeto original tinha nomes de modelos fixos espalhados pelo código (quase sempre
"gemini-2.5-flash"). Quando o Google aposenta ou limita um modelo, essas partes param.
Esta central:

- pergunta ao Google quais modelos a sua chave pode usar e escolhe sempre o mais novo
  de cada tipo (texto, leve, pro, imagem/Nano Banana, voz ao vivo);
- se um modelo não existir mais (404) ou acabar a cota gratuita (429), tenta o próximo
  (cada modelo tem a sua própria cota grátis);
- vale para a biblioteca nova (google-genai) e para a antiga (google-generativeai).

Padrão: rapidez (modelos estáveis). Para preferir uma versão (ex.: Gemini 3.5, mesmo em preview),
coloque no .env: JARVIS_PRIORIDADE=versao e JARVIS_GEMINI_VERSAO=3.5

Para forçar um modelo, coloque no .env:
  JARVIS_MODELO_TEXTO, JARVIS_MODELO_LEVE, JARVIS_MODELO_PRO, JARVIS_MODELO_IMAGEM, GEMINI_LIVE_MODEL
"""

from __future__ import annotations

import functools
import os
import re
import threading
import time

_EXCLUIR_TEXTO = ("lite", "image", "audio", "tts", "live", "embedding", "veo", "imagen",
                  "gemma", "robotics", "computer-use", "learnlm", "aqa", "nano")
_cache: list[tuple[str, set[str]]] | None = None
_cache_momento = 0.0
_trava = threading.Lock()
_instalado = False


# ---------- lista de modelos da chave ----------

def listar(forcar: bool = False) -> list[tuple[str, set[str]]]:
    """[(nome, {ações suportadas})] dos modelos disponíveis para a chave. [] se não conseguir."""
    global _cache, _cache_momento
    with _trava:
        # Lista boa vale a sessão toda; lista vazia (falha) é tentada de novo a cada 5 minutos.
        if _cache and not forcar or (_cache == [] and time.time() - _cache_momento < 300 and not forcar):
            return _cache
        chave = _chave()
        if not chave:
            return []
        try:
            from google import genai

            cliente = genai.Client(api_key=chave, http_options={"api_version": "v1beta"})
            modelos = []
            for modelo in _metodo_original(cliente.models, "list")():
                nome = str(getattr(modelo, "name", "") or "").removeprefix("models/")
                acoes = {str(a).lower() for a in (getattr(modelo, "supported_actions", None) or [])}
                if nome:
                    modelos.append((nome, acoes))
            _cache = modelos
        except Exception as erro:
            print(f"[Modelos] Não consegui listar os modelos da chave: {erro}")
            _cache = []
        _cache_momento = time.time()
        return _cache


def _chave() -> str:
    chave = os.environ.get("GEMINI_API_KEY", "").strip()
    if chave:
        return chave
    try:  # a chave também pode estar guardada no cofre do Windows pela tela de configuração
        from memory.config_manager import get_gemini_key

        return (get_gemini_key() or "").strip()
    except Exception:
        return ""


def _versao(nome: str) -> float:
    achado = re.search(r"gemini-(\d+(?:\.\d+)?)", nome)
    return float(achado.group(1)) if achado else 0.0


# Modelos mais antigos que isso ficam só como última reserva. O Gemini 2.5 está sendo aposentado
# pelo Google; JARVIS_VERSAO_MINIMA no .env muda esse limite.
try:
    VERSAO_MINIMA = float(os.environ.get("JARVIS_VERSAO_MINIMA", "3.0").replace(",", "."))
except ValueError:
    VERSAO_MINIMA = 3.0


def _grupo(nome: str) -> int:
    """0 = estável e atual, 1 = apelido "latest", 2 = preview/experimental (o Google desliga
    mais rápido), 3 = versão antiga (perto de ser aposentada)."""
    if "latest" in nome:
        return 1
    if _versao(nome) < VERSAO_MINIMA:
        return 3
    if "preview" in nome or "exp" in nome:
        return 2
    return 0


def prioridade() -> str:
    """JARVIS_PRIORIDADE: 'rapidez' (padrão: modelos estáveis, que respondem mais rápido e travam
    menos) ou 'versao' (usa JARVIS_GEMINI_VERSAO, mesmo que seja preview)."""
    valor = os.environ.get("JARVIS_PRIORIDADE", "rapidez").strip().lower()
    return "versao" if valor in {"versao", "versão", "novidade"} else "rapidez"


def versao_preferida() -> float | None:
    """JARVIS_GEMINI_VERSAO=3.5 + JARVIS_PRIORIDADE=versao no .env: usa primeiro os modelos dessa
    versão (mesmo em preview). Se a chave não tiver essa versão, segue a escolha normal."""
    if prioridade() != "versao":
        return None
    try:
        return float(os.environ.get("JARVIS_GEMINI_VERSAO", "").strip().replace(",", "."))
    except ValueError:
        return None


def _fora_da_preferida(nome: str) -> int:
    pref = versao_preferida()
    return 0 if pref is None or abs(_versao(nome) - pref) < 1e-6 else 1


def _ordenar(nomes: list[str]) -> list[str]:
    """Versão escolhida no .env primeiro; depois estáveis mais novos; preview e antigos na reserva."""
    return sorted(nomes, key=lambda n: (_fora_da_preferida(n), _grupo(n), -_versao(n), len(n), n))


def categoria(pedido: str) -> str:
    n = (pedido or "").lower().removeprefix("models/")
    if "native-audio" in n or "live" in n:
        return "ao_vivo"
    if "image" in n:
        return "imagem"
    if "lite" in n:
        return "leve"
    if "pro" in n:
        return "pro"
    return "texto"


def _da_categoria(cat: str, modelos: list[tuple[str, set[str]]]) -> list[str]:
    gerar = [n for n, acoes in modelos if "generatecontent" in acoes and n.startswith("gemini")]
    if cat == "ao_vivo":
        vivos = [n for n, acoes in modelos if "bidigeneratecontent" in acoes]
        # Voz: 3.x sempre antes do 2.5 (aposentando), mesmo que o 2.5 seja de áudio nativo; depois a
        # versão escolhida no .env, estável antes de preview, a mais nova (3.5 antes de 3.1) e, na
        # mesma versão, o áudio nativo (mais rápido).
        return sorted(vivos, key=lambda n: (_versao(n) < VERSAO_MINIMA, _fora_da_preferida(n),
                                            _grupo(n) == 2 and prioridade() == "rapidez", -_versao(n),
                                            "native-audio" not in n, n))
    if cat == "imagem":
        return _ordenar([n for n in gerar if "image" in n and "imagen" not in n])
    if cat == "leve":
        return _ordenar([n for n in gerar if "lite" in n and not any(x in n for x in _EXCLUIR_TEXTO if x != "lite")])
    texto = [n for n in gerar if not any(x in n for x in _EXCLUIR_TEXTO)]
    if cat == "pro":
        return _ordenar([n for n in texto if "pro" in n])
    return _ordenar([n for n in texto if "flash" in n])


_VARIAVEL = {"texto": "JARVIS_MODELO_TEXTO", "leve": "JARVIS_MODELO_LEVE", "pro": "JARVIS_MODELO_PRO",
             "imagem": "JARVIS_MODELO_IMAGEM", "ao_vivo": "GEMINI_LIVE_MODEL"}
_ALIAS = {"texto": "gemini-flash-latest", "leve": "gemini-flash-lite-latest", "pro": "gemini-pro-latest"}


def candidatos(pedido: str) -> list[str]:
    """Modelos a tentar, em ordem, para o modelo que o código pediu."""
    pedido = (pedido or "").removeprefix("models/")
    cat = categoria(pedido)
    escolhido = os.environ.get(_VARIAVEL[cat], "").strip().removeprefix("models/")
    if cat == "imagem" and not escolhido:  # variável que o projeto original já usava
        escolhido = os.environ.get("GEMINI_IMAGE_MODEL", "").strip().removeprefix("models/")
    modelos = listar()
    lista: list[str] = []
    if escolhido:
        lista.append(escolhido)
    if modelos:
        disponiveis = {n for n, _ in modelos}
        lista += _da_categoria(cat, modelos)
        if cat in ("leve", "pro"):  # reserva: modelos de texto normais
            lista += _da_categoria("texto", modelos)
        if cat in ("texto", "leve", "pro") and _ALIAS[cat] in disponiveis:
            lista.append(_ALIAS[cat])
        if pedido in disponiveis:  # o modelo escrito no código original, como última opção
            lista.append(pedido)
    else:  # sem lista (sem internet ou chave): tenta o pedido e o apelido "mais recente"
        lista += [pedido] + ([_ALIAS[cat]] if cat in _ALIAS else [])
        if cat == "imagem":
            lista += ["gemini-3.1-flash-image", "gemini-2.5-flash-image"]
    return _sem_os_que_falharam(list(dict.fromkeys(m for m in lista if m)) or [pedido])


# ---------- modelos que acabaram de falhar ----------

PULAR_POR = 10 * 60  # segundos que um modelo que falhou fica de lado antes de ser tentado de novo
_falharam: dict[str, float] = {}


def pular(modelo: str) -> None:
    """Deixa este modelo de lado por um tempo (ex.: a voz não conectou nele): usa o próximo."""
    _falharam[str(modelo or "").removeprefix("models/")] = time.time()


def _sem_os_que_falharam(lista: list[str]) -> list[str]:
    agora = time.time()
    ativos = [m for m in lista if agora - _falharam.get(m, 0) > PULAR_POR]
    if ativos:
        return ativos + [m for m in lista if m not in ativos]  # os que falharam vão para o fim
    for m in lista:  # todos falharam: começa a volta de novo
        _falharam.pop(m, None)
    return lista


def resolver(pedido: str) -> str:
    return candidatos(pedido)[0]


def resumo() -> str:
    """Quais modelos o Jarvis vai usar agora (aparece na janela preta ao abrir)."""
    partes = [("Voz", "gemini-live-native-audio"), ("Texto", "gemini-flash"), ("Pro", "gemini-pro"),
              ("Imagem", "gemini-flash-image")]
    return " | ".join(f"{rotulo}: {resolver(pedido)}" for rotulo, pedido in partes)


def _deve_tentar_outro(erro: Exception) -> bool:
    codigo = getattr(erro, "code", None) or getattr(erro, "status_code", None)
    texto = f"{type(erro).__name__} {erro}".lower()
    return codigo in (404, 429) or any(p in texto for p in (
        "not found", "notfound", "resource_exhausted", "resourceexhausted", "quota", "is not supported"))


# ---------- ligação com as bibliotecas do Google ----------

def _metodo_original(objeto, nome):
    metodo = getattr(objeto, nome)
    return getattr(metodo, "__jarvis_original__", metodo)


def _com_reserva(chamar, pedido, **kwargs):
    ultimo = None
    for modelo in candidatos(pedido):
        try:
            return chamar(model=modelo, **kwargs)
        except Exception as erro:
            if not _deve_tentar_outro(erro):
                raise
            print(f"[Modelos] {modelo} indisponível ({str(erro)[:80]}). Tentando o próximo...")
            ultimo = erro
    raise ultimo


def instalar() -> None:
    """Faz todas as chamadas ao Gemini passarem pela central de modelos."""
    global _instalado
    if _instalado:
        return
    _instalado = True
    if _chave():
        def mostrar():
            try:
                print(f"[Modelos] {resumo()}")
            except Exception as erro:
                print(f"[Modelos] Não consegui montar o resumo: {erro}")
        threading.Thread(target=mostrar, daemon=True, name="ResumoModelos").start()

    from google.genai import chats, live, models

    original = models.Models.generate_content

    @functools.wraps(original)
    def generate_content(self, *, model, **kwargs):
        return _com_reserva(lambda **kw: original(self, **kw), model, **kwargs)

    original_async = models.AsyncModels.generate_content

    @functools.wraps(original_async)
    async def generate_content_async(self, *, model, **kwargs):
        ultimo = None
        for modelo in candidatos(model):
            try:
                return await original_async(self, model=modelo, **kwargs)
            except Exception as erro:
                if not _deve_tentar_outro(erro):
                    raise
                ultimo = erro
        raise ultimo

    for classe, nome in ((models.Models, "generate_content_stream"),
                         (models.AsyncModels, "generate_content_stream"),
                         (chats.Chats, "create"), (chats.AsyncChats, "create"),
                         (live.AsyncLive, "connect")):
        _trocar_modelo(classe, nome)

    generate_content.__jarvis_original__ = original
    generate_content_async.__jarvis_original__ = original_async
    models.Models.generate_content = generate_content
    models.AsyncModels.generate_content = generate_content_async

    try:  # biblioteca antiga (descontinuada pelo Google, ainda usada em partes do projeto)
        import google.generativeai as antiga

        original_init = antiga.GenerativeModel.__init__

        @functools.wraps(original_init)
        def init(self, model_name: str = "gemini-flash-latest", *args, **kwargs):
            original_init(self, resolver(model_name), *args, **kwargs)
            self.__jarvis_pedido__ = model_name

        original_gerar = antiga.GenerativeModel.generate_content

        @functools.wraps(original_gerar)
        def gerar(self, *args, **kwargs):
            ultimo = None
            for modelo in candidatos(getattr(self, "__jarvis_pedido__", self._model_name)):
                self._model_name = "models/" + modelo
                try:
                    return original_gerar(self, *args, **kwargs)
                except Exception as erro:
                    if not _deve_tentar_outro(erro):
                        raise
                    ultimo = erro
            raise ultimo

        antiga.GenerativeModel.__init__ = init
        antiga.GenerativeModel.generate_content = gerar
    except ImportError:
        pass


def _trocar_modelo(classe, nome: str) -> None:
    original = getattr(classe, nome)

    @functools.wraps(original)
    def envolvido(self, *args, model, **kwargs):
        return original(self, *args, model=resolver(model), **kwargs)

    envolvido.__jarvis_original__ = original
    setattr(classe, nome, envolvido)


# ---------- Nano Banana: gerar imagens ----------

def gerar_imagem(descricao: str, pasta=None) -> str:
    """Gera uma imagem com o modelo de imagem do Gemini (Nano Banana), salva e abre."""
    from datetime import datetime
    from pathlib import Path

    from google import genai
    from google.genai import types

    pasta = Path(pasta or Path.home() / "Documents" / "Jarvis Ultron" / "Imagens")
    pasta.mkdir(parents=True, exist_ok=True)
    cliente = genai.Client(api_key=_chave() or None)
    try:
        resposta = cliente.models.generate_content(
            model="gemini-flash-image", contents=descricao,
            config=types.GenerateContentConfig(response_modalities=["IMAGE", "TEXT"]))
    except Exception as erro:
        texto = str(erro).lower()
        if "limit: 0" in texto or "quota" in texto or "billing" in texto:
            return ("A sua chave não tem cota gratuita para gerar imagens (Nano Banana) agora. "
                    "O Google pode exigir faturamento ativado para esse modelo.")
        return f"Não consegui gerar a imagem: {str(erro)[:200]}"

    for parte in (resposta.candidates[0].content.parts if resposta.candidates else []) or []:
        dados = getattr(getattr(parte, "inline_data", None), "data", None)
        if dados:
            arquivo = pasta / f"imagem-{datetime.now():%Y%m%d-%H%M%S}.png"
            arquivo.write_bytes(dados)
            try:
                if os.name == "nt":
                    os.startfile(arquivo)  # noqa: S606 - abre a imagem que o próprio Jarvis criou
            except OSError:
                pass
            return f"Imagem criada e salva em {arquivo}."
    return "O modelo não devolveu nenhuma imagem. Tente descrever de outro jeito."
