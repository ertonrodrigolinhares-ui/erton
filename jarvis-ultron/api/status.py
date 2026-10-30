"""O status.py mora no core/ (Etapa 11); este nome fica só reexportando até o api/ ir para arquivo/."""

from core.status import *  # noqa: F401,F403
from core.status import STATUS_PATH, clear_status, read_status, write_status  # noqa: F401
