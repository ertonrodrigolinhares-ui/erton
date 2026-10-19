# Travas de segurança do Jarvis Ultron

Uma página só: onde fica cada trava, o que ela garante e qual teste avisa se alguém a quebrar.
Feita na Etapa 1 do `docs/PLANO-REORGANIZACAO.md`. Quem mudar uma trava de lugar atualiza esta página no
mesmo commit.

Dois arquivos de teste guardam o conjunto:

- `tests/test_invariantes.py`: as regras que **nunca** mudam, nem de propósito. Se uma etapa fizer um deles
  falhar, a etapa está errada. A base dessas regras (as ferramentas de nuvem, as automações com
  `USA_IA_NUVEM` e o `mutating` de hoje) fica escrita à mão nele (`NUVEM_MINIMA`, `AUTOMACOES_NUVEM_MINIMA`,
  `MUTATING_MINIMO`), e não só na foto, porque o `--gravar-fotos` regrava a foto com o código do momento.
- `tests/test_contratos.py`: as "fotos" de hoje (texto das ferramentas que o Gemini lê, listas de política,
  nomes que outros arquivos usam, respostas padrão). Só mudam de propósito, no mesmo commit da mudança
  (`python tests/test_contratos.py --gravar-fotos` regrava os .json de `tests/dados/`).

## 1. O "ok" do Erton

O "ok" só vale numa fala do Erton **depois** de ele ouvir o que vai ser feito. Quem preenche o
`confirm=true` é o modelo; quem confere o "ok" é o código.

| Onde | O que garante |
|---|---|
| `core/aprovacao.py` (`marca`, `fala_que_aprovou`, `aprovou_depois`, `ainda_aprovado`) | Conta as falas do Erton; um "ok" dito antes da proposta, ou o resto atrasado da fala anterior, não vale. Antes do que é pago ou não tem volta, confere de novo com a fala inteira. |
| `core/hermes_ponte.py` (`PALAVRAS_OK`, `PALAVRAS_NAO`, `usuario_aprovou`, `aprovar_e_executar`, `_publicar`) | Publicar e mexer em anúncios (`approve_publication`): proposta primeiro, "ok" claro numa fala nova, vale uma vez só e só para aquela proposta. |
| `hermes/hooks/aprovacao_jarvis.py` (`decidir`, `aprovado`) | Gancho do Hermes: escrita no Metricool ou no Meta só passa com o "ok" registrado nos últimos minutos; se não conseguir ler o arquivo do "ok", bloqueia. |
| `automacoes/videos.py` (`executar`) | Vídeo pago: primeiro o preço, depois o "ok" numa fala nova; confere de novo no fio `VideoVeo` antes de gastar. |
| `automacoes/claude_tarefas.py` e `core/claude_chefe.py` | Mudança de código pelo Claude chefe: plano, "ok", backup e desfaz sozinho se os testes quebrarem. O Claude só escreve na pasta dele e nunca lê `.env`, chaves nem memória (`PROTEGIDOS`). |
| `main.py`, `JarvisLive._nova_fala`, `_microfone_mandou_audio` e `_receive_audio` | No Gemini ao vivo, um pedaço de transcrição só abre fala nova se o microfone mandou áudio depois do último turno do Jarvis. |

Testes: `test_invariantes.py` (`OkAntigoTests`), `test_videos.py` (`OkAntesDoVideoTests`,
`OkNoGeminiAoVivoTests`), `test_jarvis_ultron.py` (`TravaDeAprovacaoTests`, `OkClaroTests`,
`PonteHermesTests`), `test_claude_chefe.py` (`FerramentaClaudeTests`, `MudarCodigoTests`,
`DesfazerSoOQueEDoClaudeTests`, `MudancaInterrompidaTests`).

**Portas que agiam sem o "ok" (Etapa 3, decisão do Erton: desligar todas).** Nenhuma delas passava pelo
`core/aprovacao.py`. Desligadas, saem da lista do Gemini (`TOOL_DECLARATIONS`), da reserva
(`RESERVA_FERRAMENTAS_ESSENCIAIS`) e do `core/prompt.txt`; chamadas mesmo assim (um nome antigo, o modelo
inventando), o `_execute_tool` responde que estão desligadas (`main.FERRAMENTAS_DESLIGADAS`,
`resposta_de_desligada`) e não chama nada. Os arquivos ficam no lugar até a Etapa 18, e as regras delas no
`core/qa_mode.py` ficam como trava a mais até lá. Teste: `test_contratos.py` (`DesligadasTests`, com a
lista escrita à mão).

- `send_message` e `prepare_message_reply` (digitavam e podiam enviar no WhatsApp, Telegram e Discord) e
  `check_messages` (lia as mensagens; sai junto porque o Erton não usa mensagens): **desligadas**.
- `agent_task` (escrevia e rodava código gerado pela IA, em `agent/executor.py`): **desligada**.
- `code_helper` e `dev_agent` (rodam código e `pip install`): ainda abertas.
- `computer_control` (clica e digita em qualquer lugar): ainda aberta.
- `game_updater` (pode desligar o PC): ainda aberta.

## 2. Modo privado (nada vai para IA na nuvem)

Ligado por `JARVIS_CEREBRO=gemma` (`core/cerebro_gemma.py`, `cerebro_gemma()`).

| Onde | O que garante |
|---|---|
| `main.py`, `FERRAMENTAS_NUVEM_IA` | Lista das ferramentas que mandam o pedido (ou a tela) para uma IA na nuvem. Só cresce enquanto a ferramenta existir. |
| `main.py`, `bloqueio_do_modo_privado` | A recusa em português. Vale para a lista acima, para as regras por argumento (`youtube_video` com `summarize`, `school_tasks` com `refresh`) e para as automações com `USA_IA_NUVEM = True` (`claude_task`, `generate_video`). |
| `main.py`, `JarvisLive._execute_tool` (2ª trava) | A recusa acontece no código, antes de qualquer ação: vale para o Gemini, para o Gemma e o Groq da reserva (`_executar_ferramenta_reserva`) e para os botões do painel Ultron (`rodar_automacao_ultron`). |
| `main.py`, `JarvisLive._ferramentas_da_reserva` | No modo privado, a reserva nem recebe as ferramentas de nuvem nem o `save_memory`. |
| `main.py`, ramo do `save_memory` | No modo privado, a memória de longo prazo não é gravada. |
| `main.py`, `_trocando_cerebro` | Ligado **antes** de abrir o fio `TrocarCerebro`: durante a troca, nada do microfone ou do texto vai para a nuvem. |
| `automacoes/videos.py` e `core/claude_chefe.py` (`no_modo_privado`) | Conferem o modo de novo antes de mandar algo para fora. |
| Tela: selo "🔒 MODO PRIVADO" no alto da tela azul (`ui_orbe.py`, que lê `JARVIS_CEREBRO` no programa da tela) | O Erton vê que está no modo privado. |
| `main.py`, `JarvisLive._falar_no_pc` | Aviso sigiloso (ex.: resultado do Claude com dados de clientes) sai só pela voz do Windows, nunca pelo Gemini. |

Testes: `test_invariantes.py` (`ModoPrivadoTests`, `ListaDeNuvemTests`, `BaseEscritaAMaoTests`,
`OrdemDasTravasTests.test_save_memory_nao_grava_no_modo_privado`), `test_contratos.py` (foto da
`FERRAMENTAS_NUVEM_IA`), `test_cerebro_gemma.py` (`GemmaNoJarvisTests`, `ModoPrivadoPorVozTests`),
`test_videos.py` (`TrocaDeModoComVideoTests` e os testes de modo privado), `test_jarvis_ultron.py`
(`VozDoPcFechaOMicrofoneTests`). O selo 🔒 ganha teste próprio na Etapa 2 (`tests/test_tela_contratos.py`).

## 3. Chaves

| Onde | O que garante |
|---|---|
| `core/api_key_validator.py` | A chave do Gemini só é aceita depois de verificada no Google. |
| `core/secret_store.py` (`get_secret_store`) | O cofre do Windows. A chave só vai para lá se o Erton marcar "lembrar". |
| `ui.py`, `SetupOverlay` e `KeyTutorialOverlay` | O campo da chave fica mascarado. |
| `ui.py`, `MainWindow._on_setup_done` | Chave não verificada não vai a lugar nenhum; aceita, vai para o `.env` (e não vai se a tela abriu pela reserva); **nunca** para o `config/api_keys.json`, e uma chave antiga que estivesse lá é apagada (também em `_check_config` e `_on_voice_changed`). A chave da voz externa também vai só para o cofre. |
| `core/claude_chefe.py` (`PROTEGIDOS`, `SEGREDOS`) | O Claude chefe não lê `.env`, `config/api_keys.json` nem `memory/`, e não recebe as variáveis com chaves. |

Testes: `test_invariantes.py` (`ChaveTests`: não vai para o `api_keys.json` nem aparece no registro da
tela), `test_gemini_acesso.py`, `test_api_key_validation.py`, `test_claude_chefe.py`
(`RodarClaudeTests.test_tarefa_usa_a_assinatura_e_as_travas`, `TravasDeLeituraEConectoresTests`). O campo mascarado ganha teste na Etapa 2. A sentinela
(`tests/test_sentinela.py`) falha se algum teste mexer no `.env`, no `config/*.json`, na `memory/` ou no
`tmp/` de verdade.

## 4. Desligar

| Onde | O que garante |
|---|---|
| `main.py`, `JarvisLive._intercept_ui_tool_call` e `_is_explicit_self_quit_transcript` | "Desliga o Jarvis" só com pedido claro na fala atual do Erton; senão responde "Ignored an unverified shutdown request". |
| `main.py`, `_queue_self_quit_after_farewell` e `_complete_self_quit_after_audio` | O Jarvis só fecha depois de terminar a despedida (`SELF_QUIT_GOODBYE`). O `quit_jarvis` não é oferecido ao Gemini. |
| `actions/computer_settings.py`, `computer_settings` | Desligar ou reiniciar o PC: exige alvo explícito ("meu computador"), recusa "desligar o Jarvis", espera 10 s e não usa `/f`. **Ponto fraco de hoje:** basta `confirmed=yes`, que o próprio modelo preenche. A Etapa 4 passa a exigir o "ok" do `core/aprovacao.py`. |
| `actions/game_updater.py` | Pode desligar o PC ao fim de um download. Sai da lista do Gemini na Etapa 3. |
| `core/qa_mode.py` | No modo de teste (QA), desligar, reiniciar e travar a tela ficam sempre bloqueados. |

Testes: `test_qa_system.py` (`test_live_quit_tool_requires_explicit_current_user_transcript`,
`test_self_quit_waits_for_farewell_audio_to_finish`, `test_shutdown_is_not_exposed_as_a_gemini_tool_action`,
`test_power_actions_remain_blocked_even_with_desktop_opt_in`), `test_jarvis_ultron.py` (`IdiomaTests`,
frases de "desliga o Jarvis"), `test_core_resilience.py` (alvo explícito), `test_invariantes.py`
(`OrdemDasTravasTests.test_desligar_o_jarvis_so_com_pedido_claro_antes_de_qualquer_ferramenta`). A
Etapa 4 cria o `tests/test_computer_settings_aprovacao.py`.

## 5. A ordem das travas no começo do `_execute_tool`

Toda chamada de ferramenta (Gemini, reserva, painel Ultron) passa por elas, **nesta ordem**:

1. servidor (`cloud_safe`): fora da lista `CLOUD_SAFE_ACTIONS`, recusa sem tocar na tela;
2. modo privado (`bloqueio_do_modo_privado`);
3. Jarvis pronto (`operational_ready`);
4. modo QA (`core/qa_mode.guard_tool_call`);
5. desligar o Jarvis (`_intercept_ui_tool_call`);
6. `save_memory` (não grava no modo privado);
7. só então a ferramenta (uma ferramenta desligada na Etapa 3 responde que está desligada e não chama nada).

A ordem pode mudar de arquivo, nunca de ordem. Teste: `test_invariantes.py` (`OrdemDasTravasTests`).

## 6. Lote de ferramentas do Gemini

Num lote, as ferramentas que mudam algo (o `mutating` do `JarvisLive._execute_tool_batch`) rodam em fila e
na ordem; as só de leitura rodam juntas. A lista só pode crescer. Testes: `test_invariantes.py`
(`LoteDoGeminiTests`, `BaseEscritaAMaoTests`) e `test_contratos.py` (foto do `mutating`).

## 7. Modo servidor (herdado do JARVIS-OS)

`main.CLOUD_SAFE_ACTIONS` e o `cloud_safe` da `JarvisLive`: no servidor, só a lista liberada é oferecida, e
nenhuma ferramenta que age no PC. Testes: `test_invariantes.py` (`ServidorTests`, cópia do
`test_phase1_decoupling.py`, que sai com o servidor na Etapa 11). Os ramos `cloud_safe` saem na Etapa 14.

## 8. O que outros arquivos usam (não é trava, mas quebra o Jarvis se mudar)

O texto e a ordem das declarações das ferramentas, as listas de política, os métodos da `JarvisLive`, os
nomes usados por automações e pela ponte (`core/ponte.py`, `METODOS_TELA` e `CHAMADAS_DO_CEREBRO`) e a
resposta padrão de cada ferramenta. Teste: `test_contratos.py`.
