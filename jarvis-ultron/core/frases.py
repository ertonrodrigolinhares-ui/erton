"""Frases fixas do Jarvis Ultron, só em português e num lugar só (Etapa 8 da reorganização).

Para mudar um aviso, edite aqui: nenhum aviso fica com duas versões espalhadas pelo código. As
constantes antigas (main.AVISO_MODO_PRIVADO, cerebro_gemma.AVISO_SEM_WHISPER, hermes_ponte.DEMOROU...)
continuam existindo como apelidos destas frases.

Uso:
    from core.frases import frase
    frase("sem_hermes")                       -> o texto
    frase("gemma_nao_ligou", acao="Instalar") -> o texto com {acao} preenchido
frase() nunca dá erro: chave que não existe devolve a própria chave, e um {campo} que faltou fica como
está no texto.

NÃO ficam aqui: os prefixos "You:", "Jarvis:", "SYS:" e "ERR:" (o código lê esses textos), os resultados
que voltam para o Gemini ("Done."), o pedido [FILE_UPLOADED], o texto das declarações das ferramentas e
as listas PALAVRAS_OK/PALAVRAS_NAO (travas do "ok").
"""

from __future__ import annotations

import string

# O nome da janela do Jarvis. É também o que o computer_settings confere para NUNCA digitar nem apertar
# teclas na janela do próprio Jarvis (actions/computer_settings.py, TITULO_DO_JARVIS): mudar aqui muda nos
# dois lugares ao mesmo tempo.
TITULO_DA_JANELA = "Jarvis Ultron"

FRASES: dict[str, str] = {
    # a janela e o ícone perto do relógio
    "titulo_janela": TITULO_DA_JANELA,
    "menu_mostrar": "Mostrar o Jarvis",
    "menu_silenciar": "Silenciar o microfone",
    "menu_sair": "Sair do Jarvis",
    "x_so_esconde_titulo": "Jarvis continua ligado",
    "x_so_esconde": ("Ele continua ouvindo, no ícone perto do relógio. Clique no ícone para voltar; para "
                     "fechar de verdade: botão direito no ícone → Sair do Jarvis."),
    # modo privado (dois avisos de propósito: o geral e o dos vídeos, decisão do Erton)
    "modo_privado_nuvem": ("No modo privado isso não é usado, porque mandaria o pedido para uma IA na nuvem. "
                           "Para usar, diga 'modo normal'."),
    "modo_privado_video": ("No modo privado não faço vídeos, porque a descrição iria para a IA de vídeo do "
                           "Google, na nuvem. Para fazer, diga 'modo normal'."),
    "gemma_nao_ligou": ("Modo privado: não consegui ligar o Gemma 4, e não vou usar a nuvem. Rode o Instalar "
                        "Gemma 4 na pasta do Jarvis, ou digite 'modo normal' para voltar ao Gemini."),
    "sem_whisper": ("No modo privado não consigo ouvir sua voz: a transcrição local (Whisper) não está "
                    "instalada, e a voz não vai para a internet. Dê dois cliques em 'Instalar voz local' "
                    "na pasta do Jarvis. "
                    "Enquanto isso, digite."),
    "whisper_falhou": ("Não consegui carregar a transcrição local da voz (Whisper). Na primeira vez ela precisa "
                       "da internet para baixar o modelo; tento de novo em 1 minuto. Enquanto isso, digite."),
    # Hermes
    "hermes_demorou": ("O Hermes demorou demais para responder. A tarefa pode continuar rodando; pergunte de "
                       "novo daqui a pouco."),
    "sem_hermes": ("O Hermes ainda não está configurado. Dê dois cliques em 'Instalar Hermes' na pasta "
                   "do Jarvis Ultron e depois abra o Jarvis de novo."),
    # ferramentas
    "erro_na_ferramenta": "Erro na ferramenta {ferramenta}",
    "erro_na_ferramenta_falado": "Senhor, a ferramenta {ferramenta} deu erro. {detalhe}",
}


class _SemErro(dict):
    """Um {campo} que faltou fica escrito como está, em vez de dar erro."""

    def __missing__(self, chave):
        return "{" + chave + "}"


def frase(chave: str, **valores) -> str:
    """O texto da chave, com os {campos} preenchidos. Chave desconhecida devolve a própria chave."""
    texto = FRASES.get(chave)
    if texto is None:
        return chave
    if not valores:
        return texto
    return string.Formatter().vformat(texto, (), _SemErro(valores))
