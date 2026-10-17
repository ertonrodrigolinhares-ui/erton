"""O "ok" do Erton conferido no código (vídeo pago, mudança de código pelo Claude, publicar pelo Hermes).

Regra: o "ok" só vale numa fala do Erton DEPOIS de ele ouvir o que vai ser feito. O JarvisLive conta
as falas dele: _fala_n sobe 1 a cada fala nova (falada ou digitada) e _fala_texto é o texto dessa fala.
Quem propõe algo guarda marca(jarvis) no momento em que a proposta é contada; na confirmação,
aprovou_depois(jarvis, marca) só é True se veio uma fala nova depois da marca e ela é um "ok" claro
(core/hermes_ponte.usuario_aprovou).

Comparar o texto da fala (como antes) não servia: no Gemini ao vivo a transcrição chega em pedaços e
atrasada, e o próprio pedido ("faz o vídeo, pode fazer") parecia uma fala nova na segunda chamada.
Por isso, no Gemini ao vivo, um pedaço só abre uma fala nova se o microfone mandou áudio depois do
último turno do Jarvis (enquanto ele fala, o microfone fica fechado; com voz externa, depois de ela
terminar a resposta); o que chega antes disso é o resto atrasado da fala anterior e só faz o texto
dela crescer.

Pelo mesmo motivo, a ferramenta pode chegar quando só o começo da resposta foi transcrito: de
"Ok, pode cancelar, tá caro" pode ter chegado só o "Ok,". Por isso, antes do que é pago ou não tem
volta, quem confirma roda ainda_aprovado() em segundo plano: espera a fala terminar de chegar e
confere de novo, com o texto inteiro.
"""

from __future__ import annotations

import time

SILENCIO = 2.0        # Gemini ao vivo: segundos sem pedaço novo (depois do fim do turno) = a fala chegou inteira
ESPERA_MAXIMA = 15.0  # no máximo isso esperando a fala terminar de chegar; passou disso, não vale


def marca(jarvis) -> int:
    """Número da fala atual do Erton. Guarde no momento em que a proposta é contada a ele."""
    try:
        return int(getattr(jarvis, "_fala_n", 0) or 0)
    except (TypeError, ValueError):
        return 0


def fala_que_aprovou(jarvis, marca: int) -> int:
    """Número da fala nova (depois da marca) que é um "ok" claro; 0 se não houver. Guarde-o para
    ainda_aprovado()."""
    from core.hermes_ponte import usuario_aprovou

    # lê o número antes do texto (nova_fala grava o texto antes do número)
    numero = getattr(jarvis, "_fala_n", None)
    texto = str(getattr(jarvis, "_fala_texto", "") or "")
    try:
        numero = int(numero)
        return numero if numero > int(marca) and usuario_aprovou(texto) else 0
    except (TypeError, ValueError):
        return 0


def aprovou_depois(jarvis, marca: int) -> bool:
    """True só se o Erton falou de novo depois da marca e essa fala nova é um "ok" claro."""
    return fala_que_aprovou(jarvis, marca) > 0


def nova_fala(jarvis, texto: str, em_pedacos: bool = False) -> int:
    """Registra uma fala NOVA do Erton (o JarvisLive chama). Devolve o número dela.
    em_pedacos=True: fala do Gemini ao vivo, que ainda pode crescer (mais_um_pedaco) até o fim do
    turno (fechar_fala). Texto digitado e falas do modo reserva já chegam inteiros."""
    jarvis._fala_texto = str(texto or "").strip()
    jarvis._fala_em_pedacos = bool(em_pedacos)
    jarvis._fala_aberta = bool(em_pedacos)
    jarvis._fala_mudou_em = time.monotonic()
    jarvis._fala_n = marca(jarvis) + 1
    return jarvis._fala_n


def mais_um_pedaco(jarvis, numero, texto: str) -> None:
    """Gemini ao vivo: chegou mais um pedaço de transcrição. Se ele é da fala atual (numero), o
    texto dela cresce; de todo jeito, o Erton ainda está falando."""
    if numero is not None and numero == marca(jarvis):
        jarvis._fala_texto = str(texto or "").strip()
    jarvis._fala_mudou_em = time.monotonic()


def fechar_fala(jarvis, numero) -> None:
    """Gemini ao vivo: fim do turno. Pedaço que chegar depois disso já é outra fala."""
    if numero is not None and numero == marca(jarvis):
        jarvis._fala_aberta = False
        jarvis._fala_mudou_em = time.monotonic()


def ainda_aprovado(jarvis, numero: int, dormir=time.sleep, agora=time.monotonic) -> bool:
    """Confere de novo, já com a fala inteira, antes do que é pago ou não tem volta. Rode em segundo
    plano (nunca no laço que recebe a transcrição, senão o resto da fala não chega).

    No Gemini ao vivo espera o fim do turno e mais SILENCIO segundos sem pedaço novo (no máximo
    ESPERA_MAXIMA). Só vale se a fala que aprovou ainda é a atual (nenhum pedaço virou fala nova)
    e o texto inteiro dela continua sendo um "ok" claro. Na dúvida, não vale."""
    from core.hermes_ponte import usuario_aprovou

    if not numero:
        return False
    inicio = agora()
    while getattr(jarvis, "_fala_em_pedacos", False):
        if marca(jarvis) != numero:
            return False
        parou = agora() - float(getattr(jarvis, "_fala_mudou_em", 0) or 0) >= SILENCIO
        if parou and not getattr(jarvis, "_fala_aberta", False):
            break
        if agora() - inicio >= ESPERA_MAXIMA:
            return False
        dormir(0.1)
    texto = str(getattr(jarvis, "_fala_texto", "") or "")
    return marca(jarvis) == numero and usuario_aprovou(texto)
