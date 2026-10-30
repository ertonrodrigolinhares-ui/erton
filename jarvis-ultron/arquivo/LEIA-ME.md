# Arquivo: peças que saíram do Jarvis

Esta pasta guarda, por algumas semanas, o que saiu do Jarvis Ultron na reorganização (veja
`docs/PLANO-REORGANIZACAO.md`). **Nada aqui é usado:** o Jarvis não importa nada desta pasta (o
`tests/test_arquivo.py` confere) e os testes guardados aqui não rodam (o `conftest.py` desta pasta
impede).

Depois de alguns meses, a pasta é apagada (Etapa 21). O git guarda tudo para sempre.

## Como trazer uma peça de volta

O jeito mais simples é `git revert` do commit que a guardou (o nome do commit está abaixo): o arquivo
volta para o lugar, junto com os testes e as linhas que saíram de outros arquivos. À mão:

1. `git mv` do arquivo de volta para o lugar de onde veio (abaixo).
2. Tire o nome dele da lista `GUARDADOS` do `tests/test_arquivo.py`.
3. Traga de volta os testes e as linhas de scripts que saíram junto (`git show` do commit).

## O que está aqui

<!-- awareness (Etapa 5) -->
- **`pecas-sem-uso/awareness/`** (commit "Reorganização etapa 5: guarda o awareness"): o motor de
  "consciência" herdado do JARVIS-OS. Vinha de `awareness/engine.py`; as anotações vinham de
  `memory/awareness-engine-enhanced.md` e `docs/MEMORY.md`. Nada criava o motor. O teste que saiu
  está em `teste-que-saiu.md`.

<!-- memory/answer_cache.py (Etapa 5) -->
- **`pecas-sem-uso/answer_cache/`** (commit "Reorganização etapa 5: guarda o answer_cache"): um
  cache de respostas herdado do JARVIS-OS. Vinha de `memory/answer_cache.py`. Nada o usava: o
  arquivo de respostas nunca era criado. Os testes que saíram estão em `teste-que-saiu.md`.

<!-- core/graphics_capability.py (Etapa 5) -->
- **`pecas-sem-uso/graphics_capability/`** (commit "Reorganização etapa 5: guarda o
  graphics_capability"): a detecção da placa de vídeo para o modo gráfico "Auto", herdada do
  JARVIS-OS. Vinha de `core/graphics_capability.py`, e o teste de `tests/test_graphics_capability.py`
  (aqui ele não roda). Nada a chamava: o gancho do ui.py ficou vazio.

<!-- servidor web (Etapa 11) -->
- **`servidor-web/`** (commit "Reorganização etapa 11: guarda o servidor web"): a "versão web" herdada
  do JARVIS-OS, que o Erton confirmou não usar: a API em FastAPI (`api/`, menos o `status.py`, que virou
  `core/status.py`), o site em Next.js (`web/`), o banco (`alembic/`, `alembic.ini`), o Docker
  (`Dockerfile`, `docker-compose.yml`, `.dockerignore`), os modelos de hospedagem (`fly.toml`,
  `render.yaml`, `.github/workflows/deploy.yml`), o `scripts/start_web_api.sh` e os testes
  `tests/test_hosted_api.py` e `tests/test_phase1_decoupling.py` (aqui eles não rodam; as conferências de
  segurança deles já foram copiadas para o `tests/test_invariantes.py` na Etapa 1). Os caminhos "por
  usuário" do cofre e da memória que gravavam no banco do servidor saíram no commit anterior.

<!-- Mac/Linux (Etapa 11) -->
- **`mac-linux/`** (commit "Reorganização etapa 11: guarda os scripts de Mac/Linux"): os iniciadores e
  instaladores herdados do JARVIS-OS para Mac e Linux (`scripts/start_jarvis.sh`, `.command`, o
  `start_jarvis.bat` e `setup_jarvis.*` antigos, `install_jarvis_cli.sh`, `scripts/jarvis`,
  `create_locked_dmg.sh`) e os `JARVIS.spec`/`JARVIS-Debug.spec` do PyInstaller. O Jarvis Ultron só roda
  no Windows, pelo "Iniciar Jarvis Ultron.bat". O `pyproject.toml` foi reescrito curto.

