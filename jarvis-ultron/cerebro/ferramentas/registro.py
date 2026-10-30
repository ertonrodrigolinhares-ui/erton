"""O registro das automações da pasta `automacoes` (Etapa 14 da reorganização).

carregar_automacoes() importa cada automacoes/*.py uma vez (cache _AUTOMACOES) e reserva os nomes das
ferramentas nativas e das desligadas, para que uma automação não os tome. O main.py reexporta a função
(automacoes/painel_ultron.py faz "from main import carregar_automacoes"); os testes que a trocam fazem patch
em cerebro.ferramentas.registro.carregar_automacoes (ou _AUTOMACOES).
"""

from __future__ import annotations

from cerebro.ferramentas.declaracoes import TOOL_DECLARATIONS
from cerebro.ferramentas.politica import FERRAMENTAS_DESLIGADAS

_AUTOMACOES = None


def carregar_automacoes(recarregar: bool = False):
    """Jarvis Ultron: ferramentas da pasta 'automacoes' (um arquivo .py por automação)."""
    global _AUTOMACOES
    if _AUTOMACOES is None or recarregar:
        from core.automacoes import carregar_ferramentas

        # as desligadas também ficam reservadas: uma automação com o nome delas não carrega
        _AUTOMACOES = carregar_ferramentas(reservados={d.get("name") for d in TOOL_DECLARATIONS}
                                           | set(FERRAMENTAS_DESLIGADAS))
    return _AUTOMACOES
