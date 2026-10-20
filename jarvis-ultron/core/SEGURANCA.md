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
| `actions/computer_settings.py` (`_pedir_ok`, `_depois_do_ok`, `TECLAS_PEDEM_OK`, `TECLAS_DE_ENERGIA`, `_janela_do_jarvis`) | Desligar e reiniciar o PC (e suspender, pela tecla Sleep do `press_key`, cuja pergunta diz "suspender o computador", sem janela), digitar e apertar teclas no programa da janela da frente (Etapa 4): a primeira chamada só pergunta, com o texto ou as teclas e o nome da janela (a pergunta aparece também num aviso do Windows, perto do relógio, pelo `ui.notificar`, porque o registro da tela fica embaixo do anel); só age se a **primeira** fala nova do Erton depois da pergunta for um "ok" claro. O `confirmed=yes` que o modelo preenche não conta; "não" (ou qualquer outra resposta) cancela; o ok vale uma vez e só para aquele pedido (outro texto, outra tecla, outro número de vezes ou outra janela, pelo número e pelo título, pedem de novo; `_a_mesma` só ignora a marca de "não salvo" do editor); uma pergunta por vez: enquanto uma espera a resposta, outro pedido na mesma fala não é guardado; texto com quebra de linha, tab ou caractere invisível é recusado (viraria Enter ou Tab, ou a pergunta mostraria outra coisa); antes de agir, confere de novo com a fala inteira (`ainda_aprovado`) e se a janela da frente ainda é a que apareceu na pergunta (guardada no pedido, não a da chamada que confirmou). Na janela do próprio Jarvis (`_janela_do_jarvis`: o título da tela ou, no Windows, o programa dono da janela, que é o do cérebro ou um de Python acima dele, como a tela) não digita nem aperta teclas, nem pergunta: o campo de texto dela manda o que recebe como fala nova do Erton (`on_text_command`), e um "sim" digitado ali responderia a outra pergunta. Sem o `jarvis` (chamada fora da conversa), não age. A trava fica dentro da ação, que o `_execute_tool` chama com o `jarvis`: vale para o Gemini, a reserva e o painel Ultron. |
| `main.py`, `JarvisLive._nova_fala`, `_microfone_mandou_audio` e `_receive_audio` | No Gemini ao vivo, um pedaço de transcrição só abre fala nova se o microfone mandou áudio depois do último turno do Jarvis. |

Testes: `test_invariantes.py` (`OkAntigoTests`), `test_videos.py` (`OkAntesDoVideoTests`,
`OkNoGeminiAoVivoTests`), `test_jarvis_ultron.py` (`TravaDeAprovacaoTests`, `OkClaroTests`,
`PonteHermesTests`), `test_claude_chefe.py` (`FerramentaClaudeTests`, `MudarCodigoTests`,
`DesfazerSoOQueEDoClaudeTests`, `MudancaInterrompidaTests`), `test_computer_settings_aprovacao.py`
(`DesligarEReiniciarTests`, `TecladoTests`, `JanelaDoJarvisTests`, `PeloExecuteToolTests`).

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
- `code_helper` e `dev_agent` (rodavam código e `pip install`): **desligadas**. O `code_helper` saiu
  também da `CLOUD_SAFE_ACTIONS` (modo servidor): lá só é oferecido o que está declarado.
- `computer_control` (clicava e digitava em qualquer lugar): **desligada**. Digitar e apertar teclas
  continua pelo `computer_settings`, só com o "ok" do Erton desde a Etapa 4 (veja a porta fechada abaixo).
- `game_updater` (podia desligar o PC): **desligada**.
- `desktop_control` com `action='task'` (ou qualquer ação fora da lista dele): pedia um código à IA e o rodava
  com o teclado e o mouse (`pyautogui`) e, no Windows, com o `ctypes`. Digitava e apertava Enter na janela da
  frente, até um "ok" no campo do próprio Jarvis (que contaria como fala nova do Erton), e podia desligar o PC.
  **Desligado** no reparo da Etapa 4, dentro da ação (`actions/desktop.py`, `TAREFA_DESLIGADA`: não pede o
  código nem roda nada), e o "task" saiu da declaração. Papel de parede, organizar, limpar, listar e as
  estatísticas continuam até a Etapa 18. Teste: `test_outras_portas.py` (`DesktopControlTests`).

Os nomes das desligadas continuam reservados: uma automação em `automacoes/` com um deles não carrega
(`main.carregar_automacoes`; teste `test_automacao_com_nome_de_desligada_nao_carrega`). A reserva (Groq e
outra empresa, `core/reserva_groq.py`, `INSTRUCOES`) também diz que o Jarvis não envia nem lê mensagens,
nem pelo navegador (teste `test_reserva_nao_manda_mensagem`).

**Pendência (Etapa 14, ou antes com o sim do Erton):** o `INSTRUCOES_GEMMA` do `core/cerebro_gemma.py`
(lista "Não mexer" do plano) ainda diz "Nunca publique, envie mensagens ... sem o 'ok' do Erton". Nenhuma
ferramenta de mensagem é oferecida ao Gemma, mas ele tem o `browser_control`, que digita e aperta Enter.
Falta a mesma frase da reserva.

**Porta fechada (Etapa 4): digitar e apertar teclas pelo `computer_settings` só com o "ok" do Erton.** O
`computer_settings` continua oferecido ao Gemini (a declaração diz "typing text on screen"), e nada confere se
a janela da frente é um campo de texto (o `actions/safe_text_entry.py` só era usado pelo `computer_control` e
pelas mensagens). Até a Etapa 4, o `type_text` (e `write_on_screen`, `type`, `write`) escrevia qualquer texto
na janela da frente e, com `press_enter`, apertava Enter; o `press_key` e as ações de atalho apertavam teclas,
sem o "ok". Agora passam pelo `_pedir_ok` com o `core/aprovacao.py` (a mesma trava de desligar e reiniciar,
na tabela acima): o `type_text` e os sinônimos, o `press_key`, o `reload_n` e todas as ações do `ACTION_MAP`
que mandam teclas para o programa da frente (`TECLAS_PEDEM_OK`: Enter, Esc, colar, copiar, recortar, desfazer,
refazer, salvar, selecionar tudo, fechar programa, janela ou aba, abrir aba nova, trocar de aba, voltar e
avançar, ir para a barra de endereço, recarregar, zoom, procurar, tela cheia, Page Up/Down, começo e fim, e o
Espaço do `pause_video`). A pergunta mostra o texto ou as teclas e o nome da janela da frente; o ok vale para
aquele texto, naquela janela (o número e o título: trocar de aba no navegador muda o título), uma vez, e só um
pedido espera a resposta de cada vez. O `reload_n` aperta o F5 no máximo 20 vezes por ok (`RECARREGAR_NO_MAXIMO`) e confere a janela antes de cada F5: se ela mudar no meio, para e avisa. Nada é digitado nem apertado na janela do próprio Jarvis (o texto
viraria uma fala do Erton). A tecla Sleep do `press_key` suspende o PC: pergunta como desligar e reiniciar. O texto vai numa linha só, sem caracteres invisíveis. Não pedem (`NAO_PEDEM_OK`,
cada uma com o motivo): volume, brilho, Wi-Fi, tema escuro, apagar a tela, rolar com o mouse e os atalhos que o
próprio Windows atende (tecla Windows, Alt+Tab, Ctrl+Shift+Esc). Toda ação nova do `ACTION_MAP` tem de entrar
numa das duas listas (teste). As linhas "Messaging" e "Typing safety" do `core/prompt.txt` continuam (nunca
digitar num aplicativo de mensagem) e agora mandam perguntar e esperar o ok. O modo privado recusa o
`computer_settings` inteiro, e o modo QA (`core/qa_mode.py`) recusa digitar e apertar teclas sem
`JARVIS_QA_ALLOW_DESKTOP=1`. Continua sem o "ok": o `browser_control`, que digita e aperta Enter no navegador
que o Jarvis controla. Testes: `test_computer_settings_aprovacao.py` (`TecladoTests`, `JanelaDoJarvisTests`, `PeloExecuteToolTests`),
`test_contratos.py` (`DesligadasTests.test_digitar_pelo_computer_settings_so_com_o_ok_e_esta_no_mapa` e
`test_prompt_nao_promete_conferir_o_campo_de_texto`).

**Como desfazer uma só (para quem programa):** os commits da Etapa 3 mexem nas mesmas linhas (a
`FERRAMENTAS_DESLIGADAS`, as declarações, o LEIA-ME, o VERSAO.txt, este arquivo, os testes e as fotos), então
o `git revert` de um só dá conflito. Ou se resolve o conflito à mão (devolver a declaração, o ramo do
`_execute_tool` e o nome nas listas, e tirar o nome da `FERRAMENTAS_DESLIGADAS` e do `DESLIGADAS` do
`test_contratos.py`), ou se revertem todos os commits da Etapa 3, reparos inclusive, do mais novo para o mais
antigo. No meio do caminho, os commits do `code_helper`, do `computer_control` e do `game_updater` só passam
no `test_phase1_decoupling` depois do reparo que tira o `code_helper` da `CLOUD_SAFE_ACTIONS`. Para o Erton
continua valendo reabrir a pasta da versão anterior.

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
| `core/claude_chefe.py` (`_proibidas_na`, `ambiente`, `_copiar_agency`, `_dentro`) | Nas tarefas, o Claude só lê a pasta `Agency` (especialistas) e os `CLAUDE.md`; em todo pedido, a memória do Claude Code fica desligada (`CLAUDE_CODE_DISABLE_AUTO_MEMORY`) e `~/.claude` não pode ser escrito. Assim, instrução escondida numa página não vira regra permanente. A cópia de `Agency` volta ao original a cada tarefa, e a limpeza não entra em atalhos de pasta. |

Testes: `test_invariantes.py` (`ChaveTests`: não vai para o `api_keys.json` nem aparece no registro da
tela), `test_gemini_acesso.py`, `test_api_key_validation.py`, `test_claude_chefe.py`
(`RodarClaudeTests.test_tarefa_usa_a_assinatura_e_as_travas`, `TravasDeLeituraEConectoresTests`,
`EspecialistasAgencyTests`, `ClaudeMdInstaladoTests`). O campo mascarado ganha teste na Etapa 2. A sentinela
(`tests/test_sentinela.py`) falha se algum teste mexer no `.env`, no `config/*.json`, na `memory/` ou no
`tmp/` de verdade.

## 4. Desligar

| Onde | O que garante |
|---|---|
| `main.py`, `JarvisLive._intercept_ui_tool_call` e `_is_explicit_self_quit_transcript` | "Desliga o Jarvis" só com pedido claro na fala atual do Erton; senão responde "Ignored an unverified shutdown request". |
| `main.py`, `_queue_self_quit_after_farewell` e `_complete_self_quit_after_audio` | O Jarvis só fecha depois de terminar a despedida (`SELF_QUIT_GOODBYE`). O `quit_jarvis` não é oferecido ao Gemini. |
| `actions/computer_settings.py`, `computer_settings` | Desligar ou reiniciar o PC: exige alvo explícito ("meu computador"), recusa "desligar o Jarvis", espera 10 s (com `/t` maior que 0, o Windows fecha os programas à força mesmo sem o `/f`, e o que não foi salvo se perde: por isso a pergunta pede para salvar antes) e só acontece com o "ok" do Erton conferido no código (`_pedir_ok` com o `core/aprovacao.py`, Etapa 4; veja a seção 1). A tecla Sleep do `press_key` (suspender) também (`TECLAS_DE_ENERGIA`). O `confirmed=yes` que o próprio modelo preenche não basta mais. |
| `actions/open_app.py` (`_recusa`, `_launch_windows`) | O nome do programa vem do modelo e nunca vira comando (reparo da Etapa 4; antes, "shutdown.exe /s /t 0" desligava na hora, em qualquer cérebro): nada passa pelo shell; nome com argumento (inclusive uma palavra depois de um programa que o `which` acha, que a busca do menu Iniciar rodaria), caminho ou sinais do cmd é recusado (o "&" entre espaços, de "Movies & TV", vale: nada passa pelo shell, e "cmd & ..." cai na regra do comando); e os programas que desligam, reiniciam ou saem da conta (`shutdown`, `logoff`, `rundll32`...) não abrem por aqui, nem sem argumento. Um nome conhecido (`_APP_ALIASES`, como "git bash", e `_NOMES_INTEIROS`, que só valem inteiros: "control panel" e "painel de controle" vão para o `control.exe`) é conferido e aberto pelo apelido, que é fixo: as palavras ditas não vão para a busca, e a volta pelo nome dito passa de novo pelo `_recusa`. Um nome que começa com um comando só abre pelo atalho do menu Iniciar com esse nome exato (`_atalho_do_menu_iniciar`, como o "Docker Desktop.lnk", aberto pelo `os.startfile`, sem argumento), nunca pela busca; sem o atalho, é recusado. O "claude" abre o aplicativo pelo atalho ou pela busca, nunca pelo PATH (`_SO_PELO_MENU`: o `claude.exe` do PATH é o Claude Code de terminal). Um nome que não é achado ainda vai para a busca do menu Iniciar, que abre o que o Windows achar primeiro. |
| `actions/file_controller.py` (`_e_programa`) | Não abre programa, script nem atalho (.exe, .bat, .ps1, .py, .lnk... e o que o `PATHEXT` rodar: abrir os rodaria) e não cria um (escrever, renomear, copiar ou mover para um nome assim), para não deixar nenhum pronto para rodar depois, como na pasta Inicializar do Windows (reparo da Etapa 4; antes, escrever um .bat com "shutdown /s /t 0" e abri-lo desligava o PC). |
| `actions/desktop.py` (`TAREFA_DESLIGADA`) | O modo 'task', que rodava código da IA com o teclado, o mouse e o `ctypes`, está desligado (reparo da Etapa 4; veja a seção 1). |
| `actions/game_updater.py` | Podia desligar o PC ao fim de um download. Desligado na Etapa 3: fora da lista do Gemini e, chamado mesmo assim, responde que está desligado. |
| `core/qa_mode.py` | No modo de teste (QA), desligar, reiniciar e travar a tela ficam sempre bloqueados. |

Testes: `test_qa_system.py` (`test_live_quit_tool_requires_explicit_current_user_transcript`,
`test_self_quit_waits_for_farewell_audio_to_finish`, `test_shutdown_is_not_exposed_as_a_gemini_tool_action`,
`test_power_actions_remain_blocked_even_with_desktop_opt_in`), `test_jarvis_ultron.py` (`IdiomaTests`,
frases de "desliga o Jarvis"), `test_core_resilience.py` (alvo explícito), `test_invariantes.py`
(`OrdemDasTravasTests.test_desligar_o_jarvis_so_com_pedido_claro_antes_de_qualquer_ferramenta`),
`test_computer_settings_aprovacao.py` (`DesligarEReiniciarTests`, `PeloExecuteToolTests`),
`test_outras_portas.py` (`OpenAppTests`, `FileControllerTests`, `DesktopControlTests`, pelo `_execute_tool`; o
`open_app` e o `file_controller` também no Gemma).

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
