"""Por qual caminho o Jarvis Ultron fala com o Gemini, e o testador de chave (Jarvis Ultron).

Há dois caminhos para a mesma IA do Google:
  - "studio": o normal, do Google AI Studio (generativelanguage.googleapis.com);
  - "vertex": o Vertex AI do Google Cloud (aiplatform.googleapis.com), usando a chave no "modo
    expresso".

Por que isso importa: desde 2026 o AI Studio só cria chaves que começam com "AQ.", e para muitas
contas o caminho normal recusa essas chaves (erro 401 ACCESS_TOKEN_TYPE_UNSUPPORTED). As chaves
"AQ." são do tipo que o Vertex AI usa; por isso o Jarvis tenta os dois caminhos e fica com o que
funcionar. A escolha fica no .env (JARVIS_GEMINI_VIA=vertex) e vale para as partes do Jarvis de
uma vez: a biblioteca nova do Google lê GOOGLE_GENAI_USE_VERTEXAI, e os pedidos das partes que ainda
usam a biblioteca antiga (que só conhece o caminho normal) vão pela nova (core/modelos.py). O que só
existe no caminho normal (a File API, para mandar arquivos grandes) não funciona pelo Vertex AI.

Testador (para o Erton, no Windows): dê dois cliques em "Testar chave do Gemini". Ele testa a chave
do .env (ou uma nova, digitada escondida) nos dois caminhos e na conversa ao vivo, explica em
português o que deu certo e grava no .env o caminho e o modelo de voz que funcionaram.
A chave nunca aparece na tela.
"""

from __future__ import annotations

import asyncio
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

VIAS = ("studio", "vertex")

# Modelos de conversa ao vivo do Vertex AI, do mais novo para o mais antigo (o testador confere
# quais a conta pode usar; dá para forçar um com GEMINI_LIVE_MODEL no .env).
VIVO_VERTEX = (
    "gemini-live-2.5-flash-native-audio",
    "gemini-live-2.5-flash",
    "gemini-2.0-flash-live-preview-04-09",
)
VIVO_STUDIO = (
    "gemini-2.5-flash-native-audio-preview-12-2025",
    "gemini-live-2.5-flash-preview",
)
TEXTO_TESTE = ("gemini-2.5-flash", "gemini-flash-latest", "gemini-2.0-flash")


def via() -> str:
    return "vertex" if os.environ.get("JARVIS_GEMINI_VIA", "").strip().lower() == "vertex" else "studio"


def aplicar_via(escolha: str | None = None) -> str:
    """Faz as conexões do Gemini usarem o caminho escolhido (as da biblioteca nova direto; as da
    antiga pela central de modelos, core/modelos.py)."""
    escolha = (escolha or via()).strip().lower()
    if escolha == "vertex":
        os.environ["JARVIS_GEMINI_VIA"] = "vertex"
        os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "true"
    else:
        os.environ.pop("GOOGLE_GENAI_USE_VERTEXAI", None)
        if os.environ.get("JARVIS_GEMINI_VIA", "").strip().lower() == "vertex":
            os.environ["JARVIS_GEMINI_VIA"] = "studio"
        # o modelo de voz do Vertex AI (gravado pelo testador) não abre pelo caminho normal; sem ele
        # a voz escolhe um do caminho normal (senão o do Vertex seria tentado primeiro a cada religada)
        if voz_so_do_vertex(os.environ.get("GEMINI_LIVE_MODEL", "")):
            os.environ.pop("GEMINI_LIVE_MODEL", None)
    return escolha


def voz_so_do_vertex(nome: str) -> bool:
    """True para um modelo de voz que só existe no Vertex AI (ex.: "gemini-live-2.5-flash-native-audio")."""
    return nome_curto(nome) in VIVO_VERTEX


def esquecer_voz_do_vertex(env: Path | str) -> bool:
    """No caminho normal: tira um GEMINI_LIVE_MODEL do Vertex AI do processo e do .env.
    True se tirou do .env."""
    if voz_so_do_vertex(os.environ.get("GEMINI_LIVE_MODEL", "")):
        os.environ.pop("GEMINI_LIVE_MODEL", None)
    from core.env_arquivo import remover_env

    return remover_env(env, "GEMINI_LIVE_MODEL", se=voz_so_do_vertex)


def versao_api() -> str | None:
    """Versão da API para o caminho atual ("v1beta" no studio; o Vertex escolhe a dele)."""
    return None if via() == "vertex" else "v1beta"


def opcoes_http(**extra) -> dict:
    opcoes = dict(extra)
    versao = versao_api()
    if versao:
        opcoes["api_version"] = versao
    return opcoes


def nome_curto(nome: str) -> str:
    """'models/x', 'publishers/google/models/x' -> 'x'."""
    return str(nome or "").strip().split("/")[-1]


# ---------------------------------------------------------------- diagnóstico

@dataclass
class Resultado:
    via: str
    ok: bool = False
    motivo: str = ""
    codigo: str = ""
    modelo_texto: str = ""
    vivos: list = field(default_factory=list)  # modelos de conversa ao vivo que a lista mostrou


def explicar_erro(erro: Exception, via_: str) -> tuple[str, str]:
    """(código curto, explicação em português) para um erro do Google."""
    texto = str(erro)
    baixo = texto.lower()
    if "access_token_type_unsupported" in baixo:
        return ("TIPO_DE_CHAVE", "o Google não aceita este tipo de chave (\"AQ.\") por este caminho")
    if "api_key_invalid" in baixo or "api key not valid" in baixo or "invalid api key" in baixo:
        return ("CHAVE_INVALIDA", "a chave não é válida (copiada pela metade, apagada ou de outro serviço)")
    if "service_disabled" in baixo or "has not been used in project" in baixo or "is disabled" in baixo:
        api = "Vertex AI API" if via_ == "vertex" else "Generative Language API"
        return ("API_DESLIGADA", f"a \"{api}\" está desligada no projeto da chave")
    if "billing" in baixo:
        return ("FATURAMENTO", "o projeto precisa de faturamento ativado no Google Cloud")
    if "resource_exhausted" in baixo or "429" in baixo or "quota" in baixo:
        return ("COTA", "a cota acabou por agora (limite gratuito); a chave em si funciona")
    if "permission_denied" in baixo or "403" in baixo:
        return ("SEM_PERMISSAO", "a chave não tem permissão para este caminho")
    if "not found" in baixo or "404" in baixo:
        return ("MODELO", "este modelo não existe para a sua conta")
    if "unauthenticated" in baixo or "401" in baixo:
        return ("RECUSADA", "o Google recusou a chave")
    if "timed out" in baixo or "timeout" in baixo or "connect" in baixo:
        return ("REDE", "não consegui falar com o Google (internet ou firewall)")
    return ("OUTRO", texto[:160])


def cliente(chave: str, via_: str, timeout_ms: int = 15000):
    from google import genai
    from google.genai import types

    opcoes = {"timeout": timeout_ms}
    if via_ == "studio":
        opcoes["api_version"] = "v1beta"
    return genai.Client(api_key=chave, vertexai=(via_ == "vertex"), http_options=types.HttpOptions(**opcoes))


def testar_via(chave: str, via_: str, timeout_ms: int = 15000) -> Resultado:
    """A chave funciona por este caminho? Lista os modelos e faz um pedido mínimo de texto."""
    r = Resultado(via=via_)
    try:
        c = cliente(chave, via_, timeout_ms=timeout_ms)
        nomes = []
        try:
            for m in c.models.list(config={"page_size": 200}):
                nome = nome_curto(getattr(m, "name", ""))
                acoes = {str(a).lower() for a in (getattr(m, "supported_actions", None) or [])}
                nomes.append(nome)
                if "bidigeneratecontent" in acoes or "live" in nome or "native-audio" in nome:
                    r.vivos.append(nome)
        except Exception as erro_lista:
            if via_ == "studio":
                raise  # no caminho normal, listar é o teste da chave
            del erro_lista  # no Vertex, listar pode não ser permitido: o pedido de texto decide
        ultimo = None
        for modelo in TEXTO_TESTE:
            try:
                c.models.generate_content(model=modelo, contents="Responda apenas: ok",
                                          config={"max_output_tokens": 8})
                r.ok, r.modelo_texto = True, modelo
                return r
            except Exception as erro:
                ultimo = erro
                codigo, _ = explicar_erro(erro, via_)
                if codigo not in ("MODELO",):
                    break  # não é o modelo: é a chave/projeto; não adianta tentar outro modelo
        raise ultimo
    except Exception as erro:
        r.codigo, r.motivo = explicar_erro(erro, via_)
        return r


async def _abrir_ao_vivo(c, modelo: str, espera: float) -> None:
    async def tentar():
        async with c.aio.live.connect(model=modelo, config={"response_modalities": ["AUDIO"]}):
            return
    await asyncio.wait_for(tentar(), timeout=espera)


def testar_ao_vivo(chave: str, via_: str, sugeridos=(), espera: float = 20.0) -> tuple[str, list]:
    """Qual modelo abre a conversa ao vivo nesta conta? (modelo ou "", [(modelo, motivo)])."""
    base = VIVO_VERTEX if via_ == "vertex" else VIVO_STUDIO
    candidatos = list(dict.fromkeys([m for m in (os.environ.get("GEMINI_LIVE_MODEL", "").strip(),) if m]
                                    + [nome_curto(m) for m in sugeridos] + list(base)))
    falhas = []
    for modelo in candidatos[:8]:
        try:
            # um cliente por tentativa: cada asyncio.run tem o seu próprio laço de eventos
            asyncio.run(_abrir_ao_vivo(cliente(chave, via_, timeout_ms=int(espera * 1000)), modelo, espera))
            return modelo, falhas
        except Exception as erro:
            falhas.append((modelo, explicar_erro(erro, via_)[1]))
    return "", falhas


def escolher_caminho(chave: str) -> tuple[Resultado | None, list]:
    """Tenta o caminho normal; se não der, o Vertex AI. (resultado que funcionou ou None, todos)."""
    todos = []
    for via_ in VIAS:
        r = testar_via(chave, via_)
        todos.append(r)
        if r.ok:
            return r, todos
    return None, todos


# ---------------------------------------------------------------- testador (janela preta)

def _arquivo_env() -> Path:
    return Path(__file__).resolve().parent.parent / ".env"


def _descrever(chave: str) -> str:
    tipo = "começa com AQ." if chave.startswith("AQ.") else ("começa com AIza" if chave.startswith("AIza") else "outro formato")
    return f"{tipo}, {len(chave)} caracteres"


def _proximos_passos(resultados: list) -> list[str]:
    codigos = {r.codigo for r in resultados}
    passos = []
    if "CHAVE_INVALIDA" in codigos:
        passos.append("Crie uma chave nova e cole de novo (ela pode ter sido copiada pela metade).")
    if "API_DESLIGADA" in codigos:
        passos.append("Ligue a \"Vertex AI API\" no projeto da chave: https://console.cloud.google.com/apis/library/aiplatform.googleapis.com "
                      "(escolha o mesmo projeto da chave e clique em ATIVAR). Depois rode este teste de novo.")
    if "FATURAMENTO" in codigos:
        passos.append("Ative o faturamento do projeto no Google Cloud: https://console.cloud.google.com/billing "
                      "(a conversa ao vivo gasta pouco; os vídeos são cobrados).")
    if "COTA" in codigos:
        passos.append("A chave funciona, mas a cota grátis acabou por agora: espere algumas horas ou ative o faturamento.")
    if "REDE" in codigos:
        passos.append("Confira a internet (e se algum antivírus ou firewall está bloqueando o Python).")
    if not passos:
        passos.append("Mande um print desta janela para o suporte (a chave não aparece nela).")
    return passos


def principal() -> int:
    import getpass

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from core.env_arquivo import atualizar_env, ler_texto_env

    try:
        import io

        from dotenv import load_dotenv

        # o .env pode estar na página de código do console (cidade com acento gravada pelo iniciador)
        load_dotenv(stream=io.StringIO(ler_texto_env(_arquivo_env())))
    except Exception:
        pass

    print("=" * 62)
    print(" Testar a chave do Gemini (a chave nunca aparece na tela)")
    print("=" * 62)
    atual = os.environ.get("GEMINI_API_KEY", "").strip()
    print("Chave no .env:", _descrever(atual) if atual else "nenhuma")
    print()
    print("Se você criou uma chave NOVA, cole aqui (clique com o botão direito; ela fica escondida)")
    nova = getpass.getpass("e aperte Enter. Para testar a do .env, só aperte Enter: ").strip()
    chave = nova or atual
    if not chave:
        print("\nNenhuma chave para testar. Crie uma em https://aistudio.google.com/apikey")
        return 1
    if nova:
        print("Chave nova:", _descrever(nova))

    print("\n[1/3] Caminho normal (Google AI Studio)...")
    estudio = testar_via(chave, "studio")
    print("      FUNCIONA" if estudio.ok else f"      NÃO: {estudio.motivo}")
    resultados = [estudio]
    vencedor = estudio if estudio.ok else None
    if not estudio.ok:
        print("[2/3] Caminho Vertex AI (Google Cloud)...")
        vertex = testar_via(chave, "vertex")
        print("      FUNCIONA" if vertex.ok else f"      NÃO: {vertex.motivo}")
        resultados.append(vertex)
        vencedor = vertex if vertex.ok else None
    else:
        print("[2/3] Caminho Vertex AI: não precisa (o normal funcionou).")

    if vencedor is None:
        print("\nA chave não funcionou por nenhum caminho. O que fazer:")
        for passo in _proximos_passos(resultados):
            print(" -", passo)
        return 1

    print(f"[3/3] Conversa ao vivo (voz natural) pelo caminho {'Vertex AI' if vencedor.via == 'vertex' else 'normal'}...")
    modelo_vivo, falhas = testar_ao_vivo(chave, vencedor.via, vencedor.vivos)
    if modelo_vivo:
        print(f"      FUNCIONA (modelo de voz: {modelo_vivo})")
    else:
        print("      NÃO consegui abrir a conversa ao vivo:")
        for modelo, motivo in falhas[:4]:
            print(f"        {modelo}: {motivo}")

    env = _arquivo_env()
    try:
        if nova:
            atualizar_env(env, "GEMINI_API_KEY", nova)
        atualizar_env(env, "JARVIS_GEMINI_VIA", vencedor.via)
        if modelo_vivo and (vencedor.via == "vertex" or os.environ.get("GEMINI_LIVE_MODEL")):
            atualizar_env(env, "GEMINI_LIVE_MODEL", modelo_vivo)
    except OSError as erro:
        print(f"\nNÃO consegui gravar no arquivo .env ({type(erro).__name__}). Ele pode estar somente leitura")
        print("ou aberto em outro programa. Feche o Jarvis e o Bloco de Notas e rode este teste de novo.")
        return 1
    print("\nGravei no .env:", ", ".join(
        (["a chave nova"] if nova else []) + [f"o caminho ({vencedor.via})"]
        + ([f"o modelo de voz ({modelo_vivo})"] if modelo_vivo and (vencedor.via == "vertex" or os.environ.get("GEMINI_LIVE_MODEL")) else [])))
    if modelo_vivo:
        print("\nPronto! Abra o 'Iniciar Jarvis Ultron': a conversa natural deve funcionar.")
        return 0
    print("\nO texto funciona, mas a voz ao vivo não abriu. O Jarvis vai usar a reserva para falar.")
    for passo in _proximos_passos(resultados):
        print(" -", passo)
    return 2


def rodar_no_console() -> int:
    """O testador na janela preta: nunca fecha sozinho, nem quando algo dá errado."""
    try:
        codigo = principal()
    except KeyboardInterrupt:
        codigo = 1
    except Exception as erro:
        # só o tipo do erro: a mensagem pode trazer pedaços da chave, que nunca vai para a tela
        print(f"\nDeu um erro inesperado ({type(erro).__name__}). Tire um print desta janela e mande para o suporte.")
        codigo = 1
    try:
        input("\nAperte Enter para fechar.")
    except EOFError:
        pass
    return codigo


if __name__ == "__main__":
    sys.exit(rodar_no_console())
