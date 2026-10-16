"""O "ok" do Erton conferido no código (vídeo pago, mudança de código pelo Claude, publicar pelo Hermes).

Regra: o "ok" só vale numa fala do Erton DEPOIS de ele ouvir o que vai ser feito. O JarvisLive conta
as falas dele: _fala_n sobe 1 a cada fala nova (falada ou digitada) e _fala_texto é o texto dessa fala.
Quem propõe algo guarda marca(jarvis) no momento em que a proposta é contada; na confirmação,
aprovou_depois(jarvis, marca) só é True se veio uma fala nova depois da marca e ela é um "ok" claro
(core/hermes_ponte.usuario_aprovou).

Comparar o texto da fala (como antes) não servia: no Gemini ao vivo a transcrição chega em pedaços e
atrasada, e o próprio pedido ("faz o vídeo, pode fazer") parecia uma fala nova na segunda chamada.
"""

from __future__ import annotations


def marca(jarvis) -> int:
    """Número da fala atual do Erton. Guarde no momento em que a proposta é contada a ele."""
    try:
        return int(getattr(jarvis, "_fala_n", 0) or 0)
    except (TypeError, ValueError):
        return 0


def aprovou_depois(jarvis, marca: int) -> bool:
    """True só se o Erton falou de novo depois da marca e essa fala nova é um "ok" claro."""
    from core.hermes_ponte import usuario_aprovou

    # lê o número antes do texto (nova_fala grava o texto antes do número)
    numero = getattr(jarvis, "_fala_n", None)
    texto = str(getattr(jarvis, "_fala_texto", "") or "")
    try:
        return int(numero) > int(marca) and usuario_aprovou(texto)
    except (TypeError, ValueError):
        return False


def nova_fala(jarvis, texto: str) -> int:
    """Registra uma fala NOVA do Erton (o JarvisLive chama). Devolve o número dela."""
    jarvis._fala_texto = str(texto or "").strip()
    jarvis._fala_n = marca(jarvis) + 1
    return jarvis._fala_n
