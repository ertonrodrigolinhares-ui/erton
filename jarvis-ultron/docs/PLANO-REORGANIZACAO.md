# Reorganização do Jarvis Ultron: primeiro o cinto de segurança, depois o que o Erton sente, e por último a arrumação por dentro

Plano feito em 18/10/2026 a partir de dois assistentes de referência (J.A.R.V.I.S-master e Jarvis-Desktop-Voice-Assistant) e de um mapa completo do Jarvis Ultron. Nada dos repositórios de referência foi copiado nem executado: só as ideias, reescritas no padrão do Ultron.

## Visão

COMO O PLANO FOI MONTADO
A espinha é a Proposta 1 (risco mínimo). A regra de ouro é “mover, não reescrever”: o código muda de arquivo letra por letra, os nomes continuam iguais, e o main.py e o ui.py continuam atendendo pelos nomes antigos. Assim, nada que dependa deles percebe a mudança.

Da Proposta 3 veio a ORDEM: primeiro o que o Erton sente (segurança, PC mais leve, tudo em português, novidades das referências) e só depois a arrumação por dentro, que ele não vê.

Da Proposta 2 vieram quatro proteções extras:
- o teste de invariantes;
- o core/SEGURANCA.md, um mapa das travas;
- o teste que confere se todo atributo nasce no __init__;
- os testes do “ok” escritos antes de mexer na conversa ao vivo.

O QUE OS DOIS REPOSITÓRIOS ENSINAM
Código para copiar, nenhum: o Ultron já faz tudo o que eles fazem, e melhor. A grande lição é de organização. A cadeia de if/elif do J.A.R.V.I.S-master apodreceu, e o Desktop-Voice promete um “mapa de comandos” que não entrega. O main.py do Ultron tem o mesmo problema: 33 “elif name ==” no _execute_tool, e cada ferramenta espalhada por até 8 lugares. Daí vêm:
- a tabela e a ficha única por ferramenta;
- as frases fixas num lugar só;
- um jeito só de comparar a fala, por palavra inteira.
Também vêm de 8 a 10 utilidades pequenas, reescritas do zero e sem IA na nuvem: clima falado, notícias, mapa, print salvo, música do PC, “você quis dizer…?”, CPU e bateria, e saudação conforme a hora.

REGRAS DE TODA ETAPA
(1) O trabalho é feito no ramo git “reorganizacao”, com uma etiqueta antes de cada etapa e um commit por passo. Reorganização e recurso novo nunca vão no mesmo commit.
(2) Nada entra sem quatro conferências:
- o dev/conferir_testes.py (nenhum teste que passava pode falhar);
- as fotos da Etapa 1 iguais, a não ser quando a mudança é de propósito;
- o pyflakes sem “nome indefinido” nos arquivos mexidos;
- o “git diff --color-moved”, quando é só mudança de lugar.
(3) As etapas de risco baixo chegam ao Erton juntas. As de risco médio ou alto chegam sozinhas, com alguns dias de uso antes da próxima.
(4) A cada versão, o Erton guarda a pasta da versão anterior, copia o .env para a nova e faz o roteiro de 5 minutos. Se algo estranhar, ele volta a abrir o Iniciar da pasta antiga e avisa; no código, basta um git revert.
(5) Enquanto a reorganização durar, o Claude chefe não mexe no código do próprio Jarvis.

AS FASES
- Etapas 0–2: rede de segurança. Nada muda para ele.
- Etapas 3–4: fechar as portas que agem sem o “ok”.
- Etapas 5–8: PC mais leve, nada escondido e tudo em português.
- Etapas 9–10: novidades das referências.
- Etapa 11: guardar a herança do JARVIS-OS (servidor, Mac, manuais).
- Etapas 12–14: fim do if/elif, com a ficha única por ferramenta.
- Etapas 15–17: dividir o main.py e o ui.py, com a conversa ao vivo por último.
- Etapas 18–21: decisões do Erton, enxugar componentes e opcionais.

RESULTADO ESPERADO
- main.py de 3.630 para cerca de 300 linhas, e ui.py de 9.510 para cerca de 3.000.
- Cerca de 12 mil linhas de herança fora do caminho.
- Zero “falhas conhecidas” nos testes, em vez de 71.
- Nenhuma ferramenta que envie, rode código ou desligue o PC sem o “ok” dele conferido no código.
- O PC mais leve com o Jarvis aberto, com um número para conferir.

Por fora, o Jarvis continua o mesmo: o mesmo “Iniciar Jarvis Ultron.bat”, a mesma voz, o Gemma, o Claude chefe, o painel Ultron, os agentes, o Hermes, os vídeos com “ok” e a tela limpa.

## Estrutura de pastas (alvo)

```
jarvis-ultron/   (alvo final, alcançado aos poucos; FICA = mesmo nome e mesmo lugar)
├── Iniciar Jarvis Ultron.bat ..... FICA (mesmo nome, mesma ordem)
├── outros 12 .bat ................ FICAM na raiz; só vão para instaladores/ se o Erton quiser (Etapa 20)
├── LEIA-ME.md  VERSAO.txt  LICENSE  .env.example  requirements.txt (enxuto)
├── README.md ..................... poucas linhas em português apontando para o LEIA-ME
├── main.py ....................... FICA. ~300 linhas: preparo do ambiente ao importar (igual a hoje),
│                                   JarvisLive montada com os pedaços de cerebro/, main(), cli_main
│                                   e reexportação dos nomes antigos (rodar_cerebro, carregar_automacoes...)
├── ui.py ......................... FICA. ~3.000 linhas: MainWindow + JarvisUI (os 29 nomes da ponte);
│                                   reexporta tudo o que foi para tela/
├── ui_orbe.py  ui_orbe_gpu.py  ui_stark.py ... FICAM onde estão (o anel na placa de vídeo não é tocado)
├── cerebro/ ...................... NOVO: os pedaços do main.py
│   ├── ferramentas/
│   │   ├── declaracoes.py ........ descrição das ferramentas para o Gemini (texto idêntico)
│   │   ├── politica.py ........... modo privado, lista de nuvem, fila (calculados das fichas)
│   │   ├── executores.py ......... tabela nome → função (no lugar dos 33 elif)
│   │   └── registro.py ........... ficha única por ferramenta + automações da pasta
│   ├── avisos.py  escuta.py  voz_saida.py  pontes.py  ultron.py
│   ├── entrada.py  desligar.py  reserva.py  modo_privado.py  inicio.py  ambiente.py
│   └── gemini_live/ .............. config.py  audio.py  conexao.py  recepcao.py (os últimos a mudar)
├── tela/ ......................... NOVO: os pedaços do ui.py
│   ├── base.py  estado_voz.py  compacto.py  visao.py
│   ├── janelinhas/ ............... chave, voz, nome, ajustes, atalhos
│   ├── avisos/ ................... toasts e andamento da pesquisa e da apresentação
│   └── antiga/ ................... Command Center / F2 (só enquanto o Erton quiser)
├── core/ ......................... FICA. Ganha: fontes_do_dia.py (clima e notícias), metricas.py,
│                                   status.py, frases.py, texto.py, SEGURANCA.md.
│                                   As travas (aprovacao, cerebro_gemma, secret_store...) NÃO mudam de lugar
├── actions/  automacoes/ (+ noticias.py, mapa.py, musica_local.py)  agent/task_queue.py
│   memory/  config/  claude/  hermes/  gemma/  assets/ ... FICAM no mesmo lugar
├── tests/ ........................ + test_contratos.py, test_invariantes.py, test_sentinela.py,
│                                   test_tela_contratos.py, test_registro.py, dados/
├── dev/ .......................... NOVO: conferir_testes.py, ROTEIRO_DE_5_MINUTOS.md
├── docs/original/ ................ NOVO: manuais em inglês do JARVIS-OS (com os créditos)
└── arquivo/ ...................... TEMPORÁRIO: servidor-web/, mac-linux/, ferramentas-herdadas/, pecas-sem-uso/.
                                    Nada aqui é importado (um teste confere). Apagado depois de alguns meses,
                                    com a etiqueta git “heranca-jarvis-os” guardando tudo.
```

## Etapas

### Etapa 0: Ponto de partida e alarme de testes (nada muda no Jarvis)  (risco: baixo)

Só preparação: o Jarvis que o Erton usa não muda.
(1) Criar o ramo git “reorganizacao” e a etiqueta “antes-da-reorganizacao”, que permite voltar tudo a qualquer momento.
(2) Rodar a suíte inteira 3 vezes, com pastas HOME/USERPROFILE temporárias, e guardar a lista exata das falhas de hoje em tests/dados/falhas_conhecidas.txt. Hoje são 71: as 70 do tests/test_ui_regressions.py e o tests/test_action_helpers.py::test_open_app_normalization_removes_polite_noise. Numa rodada anterior apareceu uma 72ª (test_jarvis_ultron, PainelUltronTests.test_botao_roda_automacao_direto_e_fecha). Se ela oscilar, fica anotada como “instável”, para investigar à parte.
(3) Criar o dev/conferir_testes.py: ele roda a suíte e responde só “nenhuma falha nova” ou a lista das novas.
(4) Criar a sentinela: um teste que falha se a suíte mexer em .env, config/api_keys.json, memory/*.json ou tmp/. Os testes que hoje gravam no memory/task_history.json e no tmp/jarvis_web.db de verdade passam a usar uma pasta temporária (a mudança é só nos testes).
(5) Escrever o dev/ROTEIRO_DE_5_MINUTOS.md:
- abrir pelo .bat;
- “Hey Jarvis, como está o tempo?”;
- “modo privado”: aparece o 🔒, e um pedido de pesquisa é recusado;
- “modo normal”;
- rodar um botão do painel Ultron;
- pedir um vídeo e dizer “não”: nada é gerado;
- F2 e voltar;
- fechar no X e sair pela bandeja.

- **Arquivos:** tests/dados/falhas_conhecidas.txt, tests/test_sentinela.py, dev/conferir_testes.py, dev/ROTEIRO_DE_5_MINUTOS.md (novos); ajustes só de teste em tests/test_core_resilience.py, tests/test_deep_research.py, tests/test_presentation_maker.py e tests/test_claude_chefe.py (pasta temporária)
- **Como testar:** - Rodar o dev/conferir_testes.py duas vezes seguidas: a lista de falhas é a mesma e não há nenhuma nova.
- Depois de rodar, o “git status” não mostra mudança em memory/, config/ nem tmp/.
- **Como desfazer:** git revert do commit. Ele só mexe em testes e na pasta dev/, então o Jarvis não é afetado.
- **Ganho para o Erton:** Nada muda no uso, mas passa a existir um alarme: se uma etapa seguinte estragar algo que funciona, um teste avisa antes de a versão chegar ao PC dele. E rodar os testes deixa de bagunçar o histórico real de tarefas dele.

### Etapa 1: Fotos do comportamento de hoje e mapa das travas  (risco: baixo)

Ainda sem mudar nada no Jarvis. Criar o tests/test_contratos.py e o tests/test_invariantes.py com “fotos” do que existe hoje:
- o texto e a ordem das declarações das ferramentas (TOOL_DECLARATIONS), em tests/dados/declaracoes_antes.json. O Gemini decide pelo texto, então ele não pode mudar sem querer;
- os conjuntos FERRAMENTAS_NUVEM_IA, CLOUD_SAFE_ACTIONS e RESERVA_FERRAMENTAS_ESSENCIAIS e o “mutating” do _execute_tool_batch, em tests/dados/politicas_antes.json;
- os métodos da JarvisLive, os nomes que outros arquivos usam (anunciar, _falar_aviso, _hermes_sem_travar, rodar_automacao_ultron, _ativar_modo_reserva, _definir_modo_escuta, rodar_cerebro, carregar_automacoes) e os 29 nomes de core/ponte.METODOS_TELA;
- a resposta padrão de cada ferramenta nativa (“Done.”, “Weather delivered.”...) quando a ação falsa não devolve nada;
- as regras que nunca podem quebrar: no modo privado, cada ferramenta de FERRAMENTAS_NUVEM_IA é recusada antes de chegar à ação; a lista de nuvem só cresce enquanto a ferramenta existir; um “ok” antigo não aprova publicação nem vídeo; a chave nunca vai para o config/api_keys.json.
Copiar para cá as conferências de segurança que hoje ficam em testes ligados ao servidor (por volta de tests/test_phase1_decoupling.py:89, test_cerebro_gemma.py:297 e test_qa_system.py:271), para elas não se perderem quando o servidor for guardado.
Escrever o core/SEGURANCA.md: uma página que diz onde fica cada trava (ok, modo privado, chaves, desligar) e qual teste protege cada uma.

- **Arquivos:** tests/test_contratos.py, tests/test_invariantes.py, tests/dados/declaracoes_antes.json, tests/dados/politicas_antes.json, core/SEGURANCA.md (novos)
- **Como testar:** - As fotos passam no código de hoje, sem nenhuma mudança.
- O dev/conferir_testes.py não mostra nenhuma falha nova.
- **Como desfazer:** git revert do commit. Ele só mexe em testes e num arquivo .md.
- **Ganho para o Erton:** Daqui em diante, nenhuma mudança consegue tirar uma trava de segurança ou mudar o que o Gemini lê sem que um teste avise. E fica uma página só que explica as proteções do Jarvis dele.

### Etapa 2: Consertar a rede de testes da tela  (risco: baixo)

Dos 77 testes do tests/test_ui_regressions.py, 70 falham porque cobram telas do JARVIS-OS que não existem mais: apresentação inicial, tour guiado, INTRO_*, save_auto_graphics_result e a voz padrão “charon”. Apagar esses 70 (ficam guardados na etiqueta do git) e manter os 7 que passam.
Criar o tests/test_tela_contratos.py, curto, com o que a tela de hoje precisa garantir:
- o campo da chave fica mascarado;
- a JarvisUI tem todos os nomes de METODOS_TELA;
- o _voice_combo existe e informa a voz atual;
- o _chat_bubble nasce antes do FocusDialogue;
- a Cena cobre a janela e o F2 alterna;
- com JARVIS_CEREBRO=gemma, aparece o selo 🔒.
Olhar a falha que sobra, a da normalização do open_app. Se for um defeito de verdade, consertar num commit próprio; se for teste velho, ajustar o teste.

- **Arquivos:** tests/test_ui_regressions.py; tests/test_tela_contratos.py (novo); tests/dados/falhas_conhecidas.txt; actions/open_app.py (só se a 71ª falha for defeito real, em commit separado)
- **Como testar:** - dev/conferir_testes.py: nenhum teste que passava falha.
- As falhas conhecidas caem de 71 para 0, ou para 1 anotada com o motivo.
- test_ui_orbe, test_ui_orbe_gpu e test_ui_submit continuam passando.
- **Como desfazer:** git revert do commit: os testes antigos voltam para o lugar.
- **Ganho para o Erton:** Com 71 falhas fixas, uma falha nova passava despercebida. Com zero, qualquer quebra na tela aparece na hora, e a tela fica protegida antes de alguém mexer nela.

### Etapa 3: Fechar as portas que agem sem o “ok” dele (muda de propósito, com o sim do Erton)  (risco: baixo)

Tirar da lista que o Gemini vê as ferramentas herdadas que podem agir sem o “ok” conferido no código. Os arquivos ficam no lugar por enquanto, para a volta ser imediata. Um commit por ferramenta:
- send_message, prepare_message_reply e check_messages: digitam e apertam Enter no WhatsApp, Telegram e Discord, e hoje o core/prompt.txt (linha 16) manda o Gemini enviar direto;
- agent_task: quando não reconhece uma ferramenta, escreve e RODA código Python gerado pela IA (agent/executor.py, _run_generated_code);
- code_helper e dev_agent: rodam código e pip install, e o Claude chefe já faz isso com plano e “ok”;
- computer_control: clica e digita em qualquer lugar;
- game_updater: pode desligar o PC.
Em cada commit, ajustar juntos:
- TOOL_DECLARATIONS e RESERVA_FERRAMENTAS_ESSENCIAIS;
- as linhas do core/prompt.txt que citam a ferramenta (16–22 e 42–50);
- core/qa_mode.py e core/qa_audit.py (EXPECTED_TOOLS);
- os rótulos do ui.py e a linha 39 do tests/test_documentacao.py.
Se a ferramenta for chamada mesmo assim, o ramo responde “ferramenta desligada” e não chama nada. A ORDEM das travas do _execute_tool e a lista FERRAMENTAS_NUVEM_IA não mudam. As fotos da Etapa 1 são atualizadas de propósito, só nesses nomes.

- **Arquivos:** main.py (declarações, RESERVA e ramos); core/prompt.txt; core/qa_mode.py; core/qa_audit.py; ui.py (só rótulos); tests/test_documentacao.py, tests/test_qa_system.py, tests/test_contratos.py; VERSAO.txt; LEIA-ME.md
- **Como testar:** - dev/conferir_testes.py.
- Testes novos: nenhuma ferramenta desligada aparece nas declarações; o prompt.txt não cita ferramenta que não existe; chamar uma delas responde “desligada” sem tocar na ação; a FERRAMENTAS_NUVEM_IA continua igual à foto.
- No PC: “Jarvis, manda oi no WhatsApp para a Ana”. Ele tem de dizer que não envia mensagens; nunca pode enviar.
- **Como desfazer:** git revert do commit da ferramenta: a declaração e o prompt voltam, e o arquivo nunca saiu do lugar. O Erton também pode reabrir a pasta da versão anterior.
- **Ganho para o Erton:** Uma frase mal entendida pelo microfone deixa de poder mandar mensagem, rodar código gerado pela IA, clicar em qualquer lugar ou desligar o PC. A regra “nada sai sem o meu ok” passa a valer de verdade, e com menos ferramentas na lista o Gemini escolhe mais rápido.

### Etapa 4: Desligar e reiniciar só com o “ok” dele conferido no código  (risco: medio)

Os dois projetos de referência desligam o PC à força com uma palavra solta. O Ultron já é cuidadoso: pede alvo explícito, espera 10 s, não usa /f e recusa “desligar o Jarvis”. Mas hoje basta confirmed=yes, um campo que o PRÓPRIO modelo preenche (actions/computer_settings.py, por volta das linhas 597–706).
A mudança é exigir também o core/aprovacao, como já acontece no approve_publication e nos vídeos:
- marca(jarvis) quando o Jarvis pergunta “posso reiniciar?”;
- aprovou_depois e ainda_aprovado na confirmação, para conferir que veio uma fala NOVA do Erton.
O core/aprovacao.py em si não muda; só passa a ser usado aqui. Se for preciso, o main.py passa o jarvis para a ação.

- **Arquivos:** actions/computer_settings.py; main.py (só a chamada da ação, se preciso); tests/test_computer_settings_aprovacao.py (novo); core/SEGURANCA.md
- **Como testar:** - Testes novos, com o subprocess falso: confirmed=yes sem fala nova não desliga; um “ok” dito ANTES da pergunta não vale; um “ok” depois da pergunta agenda; “não” cancela.
- Os testes do core/aprovacao, do hermes_ponte e dos vídeos sem falha nova.
- No PC: “Jarvis, reinicia o computador”, ele pergunta, o Erton responde “não”, e nada acontece.
- **Como desfazer:** git revert do commit.
- **Ganho para o Erton:** O PC só desliga ou reinicia quando ELE diz “ok” depois da pergunta, nunca porque o Gemini achou que ele disse.

### Etapa 5: Tirar o código morto do main.py e guardar peças que nada usa  (risco: baixo)

Apagar só o que tem prova de que nada usa, ou seja, o grep acha apenas a definição e os testes. Um commit por item, e antes de cada um procurar o nome no projeto inteiro, inclusive nos .bat, .ps1, .md e na pasta automacoes/:
- o porteiro de palmas (wait_for_startup_claps e STARTUP_CLAP_*, cerca de 170 linhas) e o tests/test_startup_clap.py. O LEIA-ME já diz “sem palmas”;
- os 3 ajudantes de reconexão sem chamador, com os testes deles;
- LOCAL_MACHINE_ONLY_ACTIONS e set_tour_active/_tour_active;
- as checagens do volume trancado do macOS (uma delas tem time.sleep dentro do laço);
- os atributos nunca lidos: _voice_changed, _interrupted_text, _ext_tts_voice_id e _ext_tts_api_key (este guarda a chave do ElevenLabs à toa).
Mover para arquivo/pecas-sem-uso/, com os testes deles: awareness/ (junto com memory/awareness-engine-enhanced.md e docs/MEMORY.md), memory/answer_cache.py e core/graphics_capability.py. O core/tenant.py e o core/jarvis_client.py FICAM.
Criar o teste “nada fora de arquivo/ importa de arquivo/” e tirar a pasta arquivo/ da compilação do scripts/qa.py.

- **Arquivos:** main.py; tests/test_startup_clap.py (sai); trechos de tests/test_qa_system.py, tests/test_phase1_decoupling.py, tests/test_core_resilience.py e tests/test_claude_chefe.py; awareness/, memory/answer_cache.py, core/graphics_capability.py → arquivo/pecas-sem-uso/; arquivo/LEIA-ME.md (novo); .env.example (JARVIS_LOCKED_VOLUME); scripts/qa.py
- **Como testar:** - dev/conferir_testes.py.
- pyflakes main.py sem “nome indefinido”.
- Fotos iguais, exceto os nomes apagados de propósito.
- Roteiro de 5 minutos.
- **Como desfazer:** git revert do commit do item. Os itens não dependem uns dos outros.
- **Ganho para o Erton:** Cerca de 220 linhas a menos no main.py e umas 650 a menos de peças soltas, sem mudar nada no uso. E sai da memória do programa uma cópia desnecessária da chave do ElevenLabs.

### Etapa 6: Tela mais leve: medir, tirar o morto e parar o que trabalha escondido  (risco: medio)

É a parte que ele sente no PC. Um commit por item:
(a) MEDIR ANTES. O core/autodiagnostico.py ganha três itens: “CPU do Jarvis” (os dois programas, tela e cérebro, via psutil.Process), “CPU” do PC e “Bateria”. A ideia vem do helpers.cpu() do J.A.R.V.I.S-master, mas tratando o PC de mesa sem bateria, em que o sensors_battery() devolve None (é justamente o erro do original). O Erton anota o número com o Jarvis parado e falando.
(b) APAGAR do ui.py o que é morto com prova:
- AIActivityCanvas, AIActivityConfig e _mode_sig (recebiam atualizações à toa);
- LogWidget;
- _show_voice_select, _on_voice_select_done e _close_voice_overlay;
- _feed_sparklines e o apelido VoicePresetOverlay;
- os 3 ganchos vazios, ajustando o scripts/qa_ui_probe.py;
- o carregamento do face.png, que nem existe;
- LAYOUT_SETTINGS_FILE.
(c) Só se o Erton disser sim: tirar os enfeites que fingem dados na tela antiga:
- o PresenceSystem, com frases inventadas em inglês;
- a barra COG, com um número sorteado;
- o AgentGrid, com agentes falsos e um relógio de 80 ms;
- as sparklines escondidas;
- os popups das teclas L e R.
(d) PARAR o que trabalha escondido:
- o fio _SysMetrics deixa de nascer quando o ui.py é carregado e vira o core/metricas.py: uma fonte só de CPU e memória para a Cena, a Stark e o autodiagnóstico, ligada só quando alguém olha e sem abrir janela preta (CREATE_NO_WINDOW);
- os relógios da tela antiga e da Stark param enquanto a Cena cobre a janela;
- o HudCanvas deixa de animar a esfera antiga quando o anel existe.
NÃO param o _nivel_suave (que faz o anel pulsar com a voz), o estado nem o ritmo do anel.

- **Arquivos:** core/autodiagnostico.py; core/metricas.py (novo); ui.py; ui_stark.py (relógios); scripts/qa_ui_probe.py; tests/test_ui_orbe.py, tests/test_graphics_quality.py, tests/test_tela_leve.py (novo)
- **Como testar:** - Continuam passando: test_ui_orbe, test_ui_orbe_gpu, test_graphics_quality, test_ui_submit, test_research_progress_ui e test_vision_preview.
- Testes novos: importar o ui não cria nenhum fio; com a Cena na frente, os relógios da tela antiga ficam parados; o anel continua pulsando com o volume; o autodiagnóstico funciona com bateria = None.
- No PC: comparar o “Jarvis, autodiagnóstico” e o Gerenciador de Tarefas antes e depois (2 minutos parado e 1 minuto conversando). O F2 e o Ctrl+Shift+C continuam abrindo.
- **Como desfazer:** git revert do commit do item. A pausa (d) fica separada da remoção (b), então dá para voltar só ela.
- **Ganho para o Erton:** O PC fica mais leve com o Jarvis aberto: a tela para de calcular a esfera antiga e de ler o sistema para painéis que ele nem vê. E ele ganha um número para conferir: “Jarvis, autodiagnóstico” diz quanto o Jarvis está gastando.

### Etapa 7: Nada some atrás do anel  (risco: medio)

Corrigir o que a sonda achou na tela virtual, um commit por item:
(a) Uma lista central de “janelas por cima”, que a Cena sempre traz de volta para a frente depois de mudar de tamanho: escolha de voz da 1ª abertura, Ajustes, Atalhos, janela da visão e avisos. Hoje só a tela da chave e a do nome voltam.
(b) O andamento da pesquisa profunda e da apresentação e o “executando…” viram um cartão de vidro na Cena. Hoje eles ficam escondidos atrás dela.
(c) Os avisos que hoje só vão para o registro antigo (“usando a reserva Groq”, chave salva, erro de voz) passam a aparecer também no Canal da Cena.
(d) show_toast, show_tool_progress e toggle_compact_mode passam a usar sinal do Qt. Assim ficam seguros de chamar de outro fio, como o resto da JarvisUI.
(e) A ferramenta jarvis_ui_control para de prometer “mudar o tema” e abrir/fechar o Command Center na tela azul; hoje o Jarvis diz que fez e nada muda. A ação sai, ou responde que a tela azul tem cor fixa. As descrições das outras ações não mudam nenhuma palavra.

- **Arquivos:** ui_orbe.py (Cena._trazer_janelas, cartão, Canal); ui.py (registro das janelinhas e JarvisUI); main.py (só as ações de tema e Command Center do jarvis_ui_control); tests/test_ui_orbe.py; tests/test_contratos.py (foto atualizada de propósito só nessa declaração)
- **Como testar:** - Testes novos na tela virtual: depois de mudar o tamanho, os Ajustes, a escolha de voz e os avisos ficam na frente; o show_research_progress deixa o cartão visível; uma linha “SYS: usando a reserva Groq” aparece no Canal.
- test_research_progress_ui e test_vision_preview passam.
- No PC: mudar o tamanho da janela com os Ajustes abertos; pedir uma pesquisa profunda e ver o andamento na tela azul.
- **Como desfazer:** git revert do commit do item.
- **Ganho para o Erton:** Ele passa a ver, na tela que usa de verdade, o que o Jarvis está fazendo, e o Jarvis para de dizer que fez algo que não aparece.

### Etapa 8: Tudo o que ele vê em português, com as frases fixas num lugar só  (risco: baixo)

Traduzir só textos, sem mexer na lógica, uma janela por commit:
- a tela da chave (INITIALISATION REQUIRED, VERIFYING WITH GEMINI…, Remember API key…);
- os avisos: “JARVIS is thinking...” e “Processing request...” saem, e “Tool error: X” vira “Erro na ferramenta X”;
- o título e o ícone perto do relógio: “J.A.R.V.I.S — MARK XXXIX” vira “Jarvis Ultron”, e o menu fica “Mostrar o Jarvis”, “Silenciar o microfone” e “Sair do Jarvis”;
- a 1ª abertura (VOICE SELECTION, ENTER YOUR NAME): o padrão “Sir” vira o nome dele;
- Ajustes, Atalhos (que passam a mostrar o F2 e o Ctrl+Shift+C), visão e área de soltar arquivo.
O “Quit JARVIS” muda num commit único, em TODOS os lugares que o citam: ui.py, main.py, core/claude_chefe.py, os .ps1 de gemma, claude e hermes, o .bat da voz local, o LEIA-ME e os testes test_documentacao, test_claude_chefe e test_qa_system. Os .ps1 continuam só em ASCII.
Criar o core/frases.py, a versão útil do STRINGS do Desktop-Voice, só em português: FRASES = {chave: texto} e frase(chave, **valores), que nunca dá erro (se a chave faltar, devolve a própria chave). Para lá vão os avisos repetidos:
- os dois avisos do modo privado (main.py:1282 e automacoes/videos.py:37), que hoje têm textos diferentes;
- AVISO_SEM_WHISPER, AVISO_WHISPER_FALHOU, DEMOROU e SEM_HERMES;
- “não consegui ligar o Gemma”.
As constantes antigas ficam como apelidos.
NÃO traduzir nem mover: os prefixos “You:”, “Jarvis:”, “SYS:” e “ERR:” (o código lê esses textos), os resultados que voltam para o Gemini (“Done.”), o pedido [FILE_UPLOADED], o texto das declarações e as listas PALAVRAS_OK/PALAVRAS_NAO.

- **Arquivos:** ui.py (só textos); main.py e core/claude_chefe.py (“Quit JARVIS”); gemma/*.ps1, claude/instalar_claude.ps1, hermes/instalar_hermes.ps1, “Instalar voz local.bat”; core/frases.py (novo); automacoes/videos.py, core/cerebro_gemma.py e core/hermes_ponte.py (só os textos dos avisos); LEIA-ME.md; tests/test_documentacao.py, test_claude_chefe.py, test_qa_system.py; tests/test_textos_em_portugues.py (novo)
- **Como testar:** - dev/conferir_testes.py.
- Teste novo: uma lista de textos em inglês proibidos (Quit JARVIS, Toggle Mute, INITIALISATION REQUIRED, VOICE SELECTION, VISION LINK, EXECUTING, is thinking) não aparece no ui.py, nos .ps1 nem nos .bat; e frase() com chave inexistente devolve a própria chave.
- O test_gemini_acesso continua passando, o que garante que a chave segue o mesmo caminho.
- No PC: abrir e ver a tela da chave; clicar com o botão direito no ícone do relógio; abrir Ajustes e Atalhos; no modo privado, o aviso falado continua o mesmo.
- **Como desfazer:** git revert do commit da janela. Só textos mudam, então a volta é imediata.
- **Ganho para o Erton:** Nenhuma tela, aviso ou menu em inglês, e o manual chama o botão pelo mesmo nome que ele vê. Para mudar um aviso, basta editar um arquivo só, e nenhum aviso fica com duas versões.

### Etapa 9: Novidades das referências, parte 1: clima falado, notícias, mapa e saudação  (risco: baixo)

Ideias do J.A.R.V.I.S-master e do Desktop-Voice reescritas do zero no padrão do Ultron: nenhuma linha copiada e nada executado dos repositórios. Um commit por item:
(a) core/fontes_do_dia.py, sem PyQt: o buscar_clima e o buscar_noticias saem do ui_stark.py sem mudar uma linha do miolo. O ui_stark continua reexportando, e o ui_orbe passa a importar do core. Assim, o cérebro não precisa carregar código de tela.
(b) O actions/weather_report.py passa a FALAR o clima de verdade, em português: wttr.in e a cidade de JARVIS_CIDADE, sem nunca localizar pelo IP nem dizer latitude e longitude. Hoje ele só abre uma busca em inglês e diz “Showing the weather… sir”. Como já está em RESERVA_FERRAMENTAS_ESSENCIAIS e não usa IA, a melhora vale também no Groq e no modo privado. Só abre o navegador se ele pedir.
(c) automacoes/noticias.py (FERRAMENTA news_headlines, USA_IA_NUVEM=False): lê de 3 a 5 manchetes do RSS do Google Notícias, que não precisa de chave, e só abre a matéria depois do “sim”.
(d) automacoes/mapa.py: abre https://www.google.com/maps/search/?api=1&query=<lugar codificado>, sem os erros do original (google.nl, texto sem codificar e “&amp;”).
(e) O cartão do bom dia diz “bom dia”, “boa tarde” ou “boa noite” conforme a hora (ui_orbe.py, por volta da linha 1499). Opcional: o gatilho também aceita “boa tarde” e “boa noite”.

- **Arquivos:** core/fontes_do_dia.py (novo); ui_stark.py; ui_orbe.py; actions/weather_report.py; automacoes/noticias.py e automacoes/mapa.py (novos); tests/test_fontes_do_dia.py (novo); LEIA-ME.md (uma linha por novidade); VERSAO.txt
- **Como testar:** - Testes com a internet trocada por respostas prontas (os testes não usam a rede): o clima sai em português, com a cidade do .env e sem chamar geolocalização; as notícias não abrem o navegador sem “sim”; o mapa codifica acentos e espaços; importar o core.fontes_do_dia não carrega o PyQt6; com JARVIS_CEREBRO=gemma, as três aparecem e nenhuma está em FERRAMENTAS_NUVEM_IA.
- test_ui_orbe (resumo do bom dia) e TelaStarkTests passam.
- No PC: “como está o tempo?” no modo normal e no modo privado; “quais as notícias?”, responder “não”, e nada abre; “mostra no mapa a praia de Tambaú”.
- **Como desfazer:** git revert do commit. Cada automação nova também pode ser só apagada, porque é um arquivo.
- **Ganho para o Erton:** “Jarvis, como está o tempo?” passa a responder falando, em português, até no modo privado. Notícias e mapa por voz passam a existir, sem gastar IA na nuvem.

### Etapa 10: Novidades das referências, parte 2: print salvo, música do PC e “você quis dizer…?”  (risco: baixo)

Um commit por item:
(a) Print salvo de verdade: nova ação save_screenshot no actions/computer_settings.py, usando o mss (que já está no requirements). O arquivo vai para Documentos/Jarvis Ultron/Capturas/AAAA-MM-DD_HH-MM-SS.png, fica só no PC e nunca é enviado. O memoria_hd NÃO copia essa pasta sem o Erton decidir. A ação de hoje, que abre o recorte do Windows, continua existindo. Se a declaração do computer_settings listar as ações, a foto é atualizada de propósito.
(b) core/texto.py com normalizar(fala) e tem_palavra(texto, palavra), que compara a palavra inteira: “time” não pode bater em “sometimes”. Nesta etapa ele é usado SÓ pelo código novo.
(c) automacoes/musica_local.py (USA_IA_NUVEM=False): toca um arquivo da pasta Música, sem internet, comparando com tem_palavra(). Se achar várias músicas, diz quantas achou em vez de sortear uma.
(d) “Você quis dizer a rotina X?”, com difflib, no automacoes/rotinas.py (_achar) e no cancelamento pelo texto do automacoes/lembretes.py.

- **Arquivos:** actions/computer_settings.py (nova ação); core/texto.py e automacoes/musica_local.py (novos); automacoes/rotinas.py; automacoes/lembretes.py; automacoes/memoria_hd.py (só para garantir que não copia Capturas); main.py (só o texto da declaração do computer_settings, se ela listar as ações); testes novos; LEIA-ME.md
- **Como testar:** - Testes novos: o nome do print tem data e hora e o arquivo fica na pasta certa (mss simulado); a música compara palavra inteira e, com 3 resultados, diz “achei 3”; “rotina trein0” pergunta “Você quis dizer a rotina treino?”; o memoria_hd não copia a pasta Capturas.
- Todos continuam disponíveis no modo privado.
- No PC: “Jarvis, tira um print” e “toca <música> do meu PC”.
- **Como desfazer:** git revert do commit do item, ou apagar o arquivo da automação.
- **Ganho para o Erton:** Passam a funcionar coisas que ele pede e hoje não dão certo: o print que não salvava, a música que está no próprio PC e o nome de rotina que o microfone entende errado. Tudo sem nuvem.

### Etapa 11: Guardar a herança que não serve ao PC dele: servidor web, Mac/Linux e manuais antigos (com o sim do Erton)  (risco: medio)

Vários commits pequenos, nesta ordem:
(1) Mover o api/status.py para core/status.py e trocar o import da linha 15 do main.py. O api/status.py fica só reexportando por enquanto. SEM este passo, o Jarvis não abre.
(2) Se o Erton confirmar que não usa a versão web, mover para arquivo/servidor-web/: api/, web/, alembic/, alembic.ini, Dockerfile, docker-compose.yml, .dockerignore, fly.toml, render.yaml, .github/workflows/deploy.yml, scripts/start_web_api.sh e tests/test_hosted_api.py. O test_phase1_decoupling só sai agora, porque as conferências de segurança dele já foram copiadas na Etapa 1. Os ramos cloud_safe/external_audio do cérebro ficam para a Etapa 14, porque estão misturados com as travas.
(3) Trocar o .github/workflows/ci.yml por um que rode os testes do PC (QT_QPA_PLATFORM=offscreen), ou desligá-lo. Se ele ficar como está, todo PR fica vermelho.
(4) Mover para arquivo/mac-linux/: os scripts de Mac/Linux (start_jarvis.*, setup_jarvis.*, install_jarvis_cli.sh, scripts/jarvis), o create_locked_dmg.sh, o JARVIS.spec e o JARVIS-Debug.spec. O pyproject.toml é reescrito curto ou apagado.
(5) Manuais:
- o README, PRODUCT, DESIGN, CONTRIBUTING, docs/USAGE.md e docs/TUTORIAL.md do JARVIS-OS vão para docs/original/, com os créditos;
- o que vale do USAGE (Gmail e Spotify) passa para o LEIA-ME;
- o README da raiz vira poucas linhas em português apontando para o LEIA-ME;
- sai do LEIA-ME a frase da “apresentação em inglês”, que não existe mais;
- o LICENSE fica na raiz.
(6) Limpar do .env.example as variáveis do servidor e do Mac: DATABASE_URL, REDIS_URL, JWT_SECRET, JARVIS_ENCRYPTION_KEY e JARVIS_LOCKED_VOLUME. O modo de teste com prazo (JARVIS_TRIAL_KEYWORD) só sai se o Erton confirmar, e em commit separado, porque mexe na ponte (SAIDA_FIM_DO_TESTE).
O core/tenant.py e o core/jarvis_client.py FICAM. O requirements.txt NÃO muda aqui: fica para a Etapa 18, para o .bat reinstalar os componentes uma vez só.

- **Arquivos:** api/status.py → core/status.py; main.py (linha 15); api/, web/, alembic/, alembic.ini, Dockerfile, docker-compose.yml, .dockerignore, fly.toml, render.yaml, deploy.yml, scripts/start_web_api.sh → arquivo/servidor-web/; .github/workflows/ci.yml; scripts antigos, JARVIS*.spec, create_locked_dmg.sh → arquivo/mac-linux/; pyproject.toml; README.md, PRODUCT.md, DESIGN.md, CONTRIBUTING.md, docs/USAGE.md, docs/TUTORIAL.md → docs/original/; LEIA-ME.md; .env.example; tests/test_hosted_api.py e tests/test_phase1_decoupling.py → arquivo/
- **Como testar:** - Depois de cada commit: dev/conferir_testes.py (a linha de base perde só os testes guardados).
- O comando python -I -c "import main" funciona sem erro.
- O teste “nada importa arquivo/” passa, e o grep confirma que nada fora de arquivo/ importa api, web ou alembic.
- No PC: o Iniciar abre, ele conversa por voz e o painel Ultron roda uma automação.
- **Como desfazer:** Tudo é movido com git mv. Basta um git revert do commit, ou trazer a pasta de volta de arquivo/.
- **Ganho para o Erton:** Uns 40% do projeto (cerca de 12 mil linhas, mais o site) saem do caminho. A pasta passa a mostrar só o que é do Jarvis dele, e nenhum manual em inglês manda mais rodar script de Mac ou instalar servidor.

### Etapa 12: Arrumação por dentro, parte 1: descrições e regras das ferramentas em arquivos próprios  (risco: baixo)

Aqui começa a aplicação da lição principal das duas referências: a cadeia if/elif que apodrece. Nesta etapa é só MOVER, letra por letra:
(a) As cerca de 835 linhas de TOOL_DECLARATIONS saem do main.py para cerebro/ferramentas/declaracoes.py, sem mudar nenhuma palavra. Na MESMA mudança, o core/qa_audit.declared_tools deixa de ler o texto do main.py e passa a importar a lista, porque o scripts/qa.py e os testes test_qa_system, test_deep_research e test_presentation_maker dependem disso.
(b) Em commit separado, FERRAMENTAS_NUVEM_IA, AVISO_MODO_PRIVADO (como apelido de core/frases), CLOUD_SAFE_ACTIONS e o conjunto “mutating” (que vira a constante MUDAM_ALGO) vão para cerebro/ferramentas/politica.py. A função bloqueio_do_modo_privado FICA no main.py por enquanto: ela usa o carregar_automacoes, que os testes trocam.
O main.py reexporta todos os nomes, porque o core/cerebro_gemma e os testes usam main.FERRAMENTAS_NUVEM_IA.

- **Arquivos:** cerebro/__init__.py, cerebro/ferramentas/__init__.py, cerebro/ferramentas/declaracoes.py, cerebro/ferramentas/politica.py (novos); main.py; core/qa_audit.py
- **Como testar:** - test_invariantes: o texto e a ordem das declarações são IGUAIS à foto da Etapa 1, e os conjuntos de política também.
- test_cerebro_gemma, test_qa_system, test_deep_research e test_presentation_maker passam.
- O “git diff --color-moved” mostra que o bloco só mudou de lugar, e o pyflakes não acusa nome indefinido.
- No PC: roteiro + modo privado, “pesquise X”, e o Jarvis recusa.
- **Como desfazer:** git revert do commit.
- **Ganho para o Erton:** O main.py encolhe quase um quarto de uma vez, e as regras sobre o que pode ir para a nuvem ficam numa página só, fácil de conferir.

### Etapa 13: Arrumação por dentro, parte 2: trocar os 33 “elif name ==” por uma tabela  (risco: medio)

Primeiro, criar um teste que confere POR IMPORTAÇÃO, e não pelo texto, três coisas: toda ferramenta declarada tem executor, todo executor tem declaração, e nenhum nome se repete entre as nativas e as automações. Também ajustar o core/qa_audit.repository_findings, que hoje procura “name == "x"” no texto.
Depois, ainda DENTRO do main.py, criar o dicionário EXECUTORES = {nome: função} e passar as ferramentas para ele em grupos, um commit por grupo:
(1) weather_report, web_search, browser_control, media_control e youtube_video;
(2) sistema: open_app, computer_settings, desktop_control, file_controller, graphics_quality e jarvis_ui_control;
(3) e-mail e lembrete: email_control e reminder;
(4) o Jarvis por dentro: listening_mode, suspend_listening, self_diagnosis, school_tasks, hermes_agent, approve_publication e generate_image. Neste grupo, rodar também os testes de aprovação, dos vídeos e do hermes_ponte;
(5) visão, arquivos e tarefas: screen_process, file_processor, create_presentation, deep_research e task_status;
(6) as herdadas que ainda existirem.
Cada função faz exatamente o que o ramo fazia, inclusive o texto padrão. O save_memory fica onde está, porque tem uma regra própria do modo privado. As travas do começo do _execute_tool não são tocadas, nem na ordem: cloud_safe → modo privado → operational_ready → modo QA → interceptar desligar → save_memory. Como as funções continuam no main.py, os testes que trocam main.web_search_action e main.youtube_video continuam valendo.

- **Arquivos:** main.py (_execute_tool); core/qa_audit.py; tests/test_registro.py (novo); tests/test_contratos.py
- **Como testar:** - A cada grupo: dev/conferir_testes.py; as respostas padrão iguais à foto; o test_cerebro_gemma (o modo privado recusa web_search antes de chegar à ação); pyflakes.
- No PC, depois do grupo 1: clima, uma pesquisa e tocar música.
- Depois do último grupo: roteiro completo, mais um botão do painel Ultron (que usa o mesmo executor pelo LoopReserva) e uma pergunta no modo Gemma.
- **Como desfazer:** git revert do commit do grupo: aquele grupo volta ao if/elif. A etiqueta da etapa volta tudo de uma vez.
- **Ganho para o Erton:** O coração do cérebro fica fácil de testar, e o _execute_tool cai de cerca de 320 para cerca de 80 linhas. Acrescentar ou tirar uma ferramenta passa a ser mexer em uma linha da tabela.

### Etapa 14: Arrumação por dentro, parte 3: ficha única por ferramenta e fila segura  (risco: medio)

(a) Mover a tabela para cerebro/ferramentas/executores.py, o carregar_automacoes (com o cache _AUTOMACOES) para cerebro/ferramentas/registro.py e o bloqueio_do_modo_privado para o politica.py. O main.py reexporta o carregar_automacoes, porque o automacoes/painel_ultron.py faz “from main import carregar_automacoes”. No MESMO commit, os testes trocam o alvo dos patches (por exemplo, main.web_search_action vira cerebro.ferramentas.executores.web_search_action). Um grep por “patch("main.” confere que nenhum ficou para trás, e cada teste confere que a ação falsa foi mesmo chamada, para nenhum passar por engano.
(b) Em commit separado, criar a ficha de cada ferramenta, no mesmo padrão do core/automacoes.py. A ficha tem:
- nome, declaração, executar e resposta padrão;
- usa_ia_nuvem: sim, não, ou uma regra por argumento, como a do resumo do youtube_video;
- muda_algo, precisa_ok, nuvem_ok e essencial_na_reserva.
FERRAMENTAS_NUVEM_IA, CLOUD_SAFE_ACTIONS, MUDAM_ALGO e RESERVA_FERRAMENTAS_ESSENCIAIS passam a ser CALCULADOS a partir das fichas, com os mesmos nomes, e a foto prova que dão exatamente as listas de hoje.
(c) Em commit separado, uma mudança de propósito: muda_algo=True vira o padrão seguro. Hoje, num lote do Gemini, approve_publication, hermes_agent, generate_image, open_app, browser_control, media_control, suspend_listening, listening_mode e as automações (claude_task, generate_video) podem rodar AO MESMO TEMPO, porque ficaram fora do “mutating”. Passam a rodar em fila. Só uma lista curta de leitura (web_search, weather_report, task_status, self_diagnosis…) continua em paralelo, e as automações só de leitura podem declarar MUDA_ALGO = False. A ficha do computer_settings ganha precisa_ok=True, o que liga a trava da Etapa 4.
(d) Se o servidor saiu na Etapa 11, um commit separado tira os ramos cloud_safe/external_audio, inclusive a primeira trava do _execute_tool, que nunca age no PC. Os testes do modo privado rodam junto.

- **Arquivos:** cerebro/ferramentas/executores.py e registro.py (novos); cerebro/ferramentas/politica.py e declaracoes.py; core/automacoes.py (só ler MUDA_ALGO, opcional); main.py; testes (alvos de patch); tests/dados/politicas_antes.json
- **Como testar:** - (a) e (b): conjuntos idênticos à foto; test_cerebro_gemma, test_jarvis_ultron e test_ponte; pyflakes em cerebro/.
- (c): teste novo em que um lote com approve_publication + generate_video roda em ordem, e um lote só de leitura continua em paralelo; o “mutating” só pode crescer.
- (d): no modo privado, cada ferramenta de nuvem continua recusada pelo executor.
- No PC: roteiro completo, com o modo privado.
- **Como desfazer:** git revert de (d), (c), (b) ou (a), cada um separado.
- **Ganho para o Erton:** Cada ferramenta fica escrita num lugar só, e acaba o risco de criar uma ferramenta nova e esquecer de pô-la na lista do modo privado, o que vazaria dados para a nuvem. E duas ações que mudam algo, como publicar e gerar um vídeo pago, nunca mais disputam o mesmo “ok” ao mesmo tempo.

### Etapa 15: Cérebro em pedaços, parte 1 (os blocos mais soltos)  (risco: medio)

A JarvisLive continua sendo UMA classe, no main.py e com o __init__ no mesmo lugar, mas passa a ser montada com pedaços (mixins) que ficam em outros arquivos, com os MESMOS nomes de função e de atributo.
Antes, duas preparações:
(1) Todo atributo que hoje nasce no meio do caminho passa a ser criado no __init__: _resposta_digitada_ate, _leituras_sem_registro, _loop_reserva, _reserva_ferramentas, _suspensao, _ja_cumprimentou, _idioma_recusado, _erro_ouvido_avisado, _ultima_fala_em e _abrir_ultron. Um teste lê o código, acha cada getattr(self, 'nome', ...) e confere que o nome existe no __init__. Isso pega erro de digitação que hoje mudaria o comportamento sem dar erro.
(2) O teste de contrato confere os nomes que outros arquivos usam (anunciar, _falar_aviso, _hermes_sem_travar, _ativar_modo_reserva, _reserva, _modo_reserva, _cerebro_nome, rodar_automacao_ultron, _definir_modo_escuta, _shutdown_requested, _loop, _abrir_ultron, os _fala_* do core/aprovacao e session) e os nomes dos fios (VideoVeo, ClaudeTarefa, ClaudePlano e HermesPublicar).
Depois, um commit por pedaço, com alguns dias de uso entre os mais delicados:
- cerebro/avisos.py, com anunciar, _falar_aviso e _falar_no_pc (o aviso sigiloso continua indo só pela voz do Windows);
- escuta.py;
- pontes.py (Hermes, Geekie e autodiagnóstico);
- ultron.py, voz_saida.py, entrada.py, desligar.py e reserva.py;
- por último nesta etapa, modo_privado.py, com o _trocando_cerebro ligado ANTES de abrir o fio TrocarCerebro.
Regras: recortar o texto exato; nenhum módulo novo lê os.environ nem cria cliente do Gemini ao ser importado; o alvo dos patches dos testes muda no mesmo commit.

- **Arquivos:** cerebro/avisos.py, escuta.py, pontes.py, ultron.py, voz_saida.py, entrada.py, desligar.py, reserva.py, modo_privado.py (novos); main.py; tests/test_contratos.py; testes que fazem patch em main.X usado dentro dos métodos movidos
- **Como testar:** - Depois de CADA pedaço: dev/conferir_testes.py; a lista de métodos da JarvisLive idêntica; pyflakes em cada arquivo novo (um nome esquecido só daria erro quando o Erton pedisse aquela função); “git diff --color-moved”.
- Testes de lembretes, vídeos, claude_tarefas, painel Ultron, Hermes, test_cerebro_gemma e test_reserva_outra.
- No PC: roteiro, mais um lembrete falado, um botão do Ultron, “modo chamada”, “suspender por 5 minutos”, modo privado e volta por voz e por texto, abrir sem internet e ver se cai para a reserva, e “desliga o Jarvis” respondendo “não”.
- **Como desfazer:** git revert do commit do pedaço; o Erton pode reabrir a pasta da versão anterior.
- **Ganho para o Erton:** O main.py perde cerca de 1.150 linhas, e cada assunto do cérebro ganha um arquivo com nome em português. Quando algo falhar, dá para dizer “olha o cerebro/reserva.py” em vez de procurar em 3.600 linhas.

### Etapa 16: Cérebro em pedaços, parte 2: a conversa ao vivo, por último  (risco: alto)

Só depois de algumas semanas de uso tranquilo da etapa anterior.
ANTES de mover qualquer coisa, escrever testes de regressão com uma sessão falsa, que passem no código ANTIGO:
- um “ok” que chega atrasado, do turno anterior, NÃO aprova publicação nem vídeo;
- uma fala nova aprova;
- “desliga o Jarvis” só desliga depois da despedida;
- o resultado do botão Ultron aparece uma vez só no Canal.
Depois, um commit por arquivo:
- cerebro/gemini_live/config.py: _announce_startup, _build_config, _idioma_voz e _pensamento_da_voz;
- audio.py: _send_realtime, _listen_audio, _play_audio e _esquecer_sessao_ao_sair;
- conexao.py: run, reconexão, cair para a reserva, _erro_da_api, _modelo_indisponivel e _live_response_audio_bytes;
- por último, sozinho, recepcao.py, com o _receive_audio;
- cerebro/inicio.py, com o rodar_cerebro.
O main.py reexporta o rodar_cerebro, porque o core/processo_cerebro.py chama main.rodar_cerebro. O preparo feito ao importar o main (.env, Studio/Vertex e central de modelos) vira a função preparar_ambiente() em cerebro/ambiente.py. Mesmo assim, o main.py continua chamando essa função ao ser importado, igual e na mesma ordem. Os write_status (tmp/jarvis_status.json, que ninguém lê) só saem se o Erton concordar.

- **Arquivos:** cerebro/gemini_live/config.py, audio.py, conexao.py, recepcao.py, cerebro/inicio.py, cerebro/ambiente.py (novos); main.py (fica com cerca de 300 linhas); tests/test_recepcao.py (novo)
- **Como testar:** - Os testes novos passam antes e depois da mudança.
- dev/conferir_testes.py.
- No PC, duas vezes, em dias diferentes:
  - roteiro completo;
  - pedir uma publicação e dizer “ok” só depois que ele perguntar: tem que funcionar;
  - repetir dizendo “ok” ANTES de ele terminar de perguntar: não pode aprovar;
  - desligar o Wi-Fi por 1 minuto: ele cai para a reserva e volta.
- **Como desfazer:** git revert do commit do pedaço. Se algo estranho acontecer com o “ok”, reverter o recepcao.py primeiro. O Erton reabre a pasta da versão anterior.
- **Ganho para o Erton:** O main.py fica com cerca de 300 linhas (eram 3.630). E a parte mais delicada, o “ok”, ganha testes próprios que antes não existiam: o Jarvis fica mais seguro do que estava.

### Etapa 17: Tela em pastas (o ui.py vira porta de entrada)  (risco: medio)

A regra é a mesma do cérebro: mover sem mudar, com o ui.py reexportando tudo e a JarvisUI mantendo os mesmos 29 nomes da ponte. O ui_orbe.py, o ui_orbe_gpu.py e o ui_stark.py FICAM onde estão, e o anel na placa de vídeo não é tocado.
Um commit por bloco:
(1) tela/base.py, com os caminhos e as constantes: API_FILE, UI_SETTINGS_FILE, GRAPHICS_PROFILES, a paleta e as fontes.
(2) As janelinhas vão para tela/janelinhas/: atalhos, ajustes, nome e voz. Por último e sozinha, a tela da chave (SetupOverlay → chave.py).
(3) Os avisos e o andamento vão para tela/avisos/, o CompactModeWidget para tela/compacto.py e a VisionPreviewWindow para tela/visao.py.
(4) O _voice_combo sai do painel direito para tela/estado_voz.py, sem desenho, porque é a fonte da voz atual.
(5) A tela antiga do Command Center/F2 vai para tela/antiga/. A ordem de montagem continua a mesma (o _chat_bubble antes do FocusDialogue), e o núcleo do HudCanvas que o anel usa (_step, _nivel_suave) fica.
CUIDADO: os testes fazem patch em ui.API_FILE e ui.UI_SETTINGS_FILE. Se o código passar a ler tela.base.API_FILE, o patch tem que mudar no MESMO commit, senão os testes mexeriam no config/api_keys.json de verdade. A sentinela da Etapa 0 avisa se isso acontecer.
O scripts/qa.py passa a compilar tela/ e cerebro/.

- **Arquivos:** tela/__init__.py, tela/base.py, tela/janelinhas/*.py, tela/avisos/*.py, tela/compacto.py, tela/visao.py, tela/estado_voz.py, tela/antiga/*.py (novos); ui.py (fica com cerca de 3.000 linhas); scripts/qa.py; testes (alvos de patch)
- **Como testar:** - dev/conferir_testes.py, e o “git status” limpo em config/ depois dos testes.
- test_gemini_acesso: a chave vai para o cofre só se ele marcar, para o .env só se for aceita, e nunca para o api_keys.json.
- test_cerebro_gemma: a tela da chave fecha sozinha no modo Gemma.
- test_tela_contratos, test_ui_orbe, test_ui_orbe_gpu e test_ponte.
- No PC: roteiro, mais abrir os Ajustes por voz e trocar a voz, Ctrl+M, F2, Ctrl+Shift+C e soltar um arquivo. Testar também com JARVIS_ORBE_GPU=0 (o anel sem a placa de vídeo).
- **Como desfazer:** git revert do commit do bloco. A fachada ui.py garante que o main.py, o core/ponte.py e as automações não percebem a mudança.
- **Ganho para o Erton:** O ui.py cai de 9.510 para cerca de 3.000 linhas. As telas que pedem a chave ficam isoladas e fáceis de revisar, e fica claro o que é a tela azul e o que é a tela antiga. É a base para ele decidir se a tela antiga continua.

### Etapa 18: Ferramentas herdadas restantes e componentes enxutos (com o sim do Erton)  (risco: medio)

Depois de umas duas semanas sem sentir falta das ferramentas desligadas na Etapa 3:
(1) Mover os arquivos delas para arquivo/ferramentas-herdadas/: agent/executor.py, planner.py e error_handler.py; actions/code_helper.py, dev_agent.py, computer_control.py e game_updater.py; e, se as mensagens não voltaram, send_message.py, message_monitor.py, instagram_browser.py e safe_text_entry.py. O agent/task_queue.py FICA, porque a pesquisa e as apresentações usam.
(2) Uma ferramenta por commit, mexendo junto na ficha, no prompt.txt, no qa_audit, no qa_mode, nos rótulos do ui.py e nos testes:
- flight_finder: o agente “viagens” do Claude já faz;
- reminder: o automacoes/lembretes.py faz o mesmo e ainda fala o aviso (perguntar se ele usa o Agendador do Windows);
- desktop_control: só se ele não usa o papel de parede nem a limpeza da área de trabalho.
(3) O requirements.txt muda num commit ÚNICO, porque o Iniciar reinstala tudo quando ele muda. Sai:
- fastapi, uvicorn, SQLAlchemy, alembic, psycopg, redis e email-validator, se o servidor saiu;
- pywinauto e pygetwindow, se o game_updater saiu.
O xlrd fica enquanto as apresentações aceitarem o .xls antigo.
(4) Depois, em commits próprios: migrar o computer_settings, o desktop e o youtube_video para o google-genai e só então tirar o google-generativeai; trocar o duckduckgo-search pelo ddgs, com teste da busca.
Avisar o Erton: a próxima abertura demora alguns minutos, uma vez só.

- **Arquivos:** cerebro/ferramentas/*; core/prompt.txt; core/qa_audit.py; core/qa_mode.py; ui.py (rótulos); agent/executor.py, planner.py, error_handler.py; actions/code_helper.py, dev_agent.py, computer_control.py, game_updater.py, flight_finder.py, reminder.py, desktop.py, send_message.py, message_monitor.py, instagram_browser.py, safe_text_entry.py → arquivo/ferramentas-herdadas/; requirements.txt; actions/computer_settings.py, desktop.py, youtube_video.py, web_search.py (migrações); VERSAO.txt; LEIA-ME.md; tests/test_action_helpers.py, test_core_resilience.py, test_qa_system.py
- **Como testar:** - dev/conferir_testes.py, com as fotos atualizadas de propósito.
- Teste novo que importa todos os módulos que ficaram (actions/, automacoes/, core/, cerebro/, tela/): pega um pacote faltando antes de o Erton pedir aquela função.
- Teste de que cada pacote do requirements é importado por algum arquivo.
- Num venv limpo no Windows: pip install -r requirements.txt e pip check.
- No PC, depois da reinstalação: resumir um vídeo do YouTube, mudar o volume, criar uma apresentação pequena e “me lembra de beber água em 2 minutos”.
- **Como desfazer:** git revert do commit. O Iniciar reinstala sozinho a lista antiga na abertura seguinte.
- **Ganho para o Erton:** A instalação fica mais rápida e menor, e há menos pacotes com falha de segurança para manter. O Gemini fica sem nenhuma ferramenta que rode código, desligue o PC ou clique em qualquer lugar sem “ok”.

### Etapa 19: Decisões sobre a tela antiga (F2 e Command Center), só com o sim dele  (risco: medio)

Com a tela já separada, fazer só o que ele aprovar, um commit por item:
(a) A esfera clássica (JARVIS_VISUAL=classico, cerca de 900 linhas): guardar em arquivo/ ou manter.
(b) A tela antiga inteira (F2/Ctrl+Shift+C) só pode sair depois de duas coisas:
- levar para a tela azul, ou para comandos de voz, o que só ela tem: soltar arquivo, trocar a voz externa, trocar o nome, o bloco de notas da Stark, as legendas e a Central de missões;
- tirar o painel Ultron da dependência da Stark. Hoje o automacoes/painel_ultron.py (linha 52) desiste cedo se não houver _tela_stark, e com JARVIS_TEMA_STARK=0 o painel some.
(c) Se ele quiser manter o F2, a tela antiga passa a ser montada só na primeira vez que o F2 ou o Command Center for usado.

- **Arquivos:** ui.py; tela/antiga/*; ui_stark.py; ui_orbe.py; automacoes/painel_ultron.py; automacoes/painel_stark.py
- **Como testar:** - test_ui_orbe e os testes do painel Ultron.
- Teste novo: com JARVIS_TEMA_STARK=0, o painel Ultron continua abrindo.
- No PC: roteiro completo, mais cada coisa que foi levada para a tela azul.
- **Como desfazer:** git revert do commit. O que saiu fica guardado em arquivo/.
- **Ganho para o Erton:** A tela azul passa a ter tudo o que ele usa, o painel Ultron deixa de depender da tela Stark, e o que ele não usa para de pesar no PC.

### Etapa 20: Dois botões na pasta em vez de treze (opcional, com o sim dele)  (risco: medio)

Na raiz ficam só dois .bat:
- “Iniciar Jarvis Ultron.bat”, igual ao de hoje: mesmo nome e mesma ordem (desfaz a mudança interrompida do Claude antes de instalar);
- um novo “Instalar e Configurar.bat”: um menu numerado em português, escrito só em ASCII.
O menu tem 4 grupos:
1) Instalar: Claude, Gemma 4 e Hermes;
2) Ligar: Gmail, Telegram, Hermes e Agentes;
3) Consertar e testar: chave do Gemini, Telegram, voz local e voltar para o Gemini;
4) Desinstalar Hermes, que pede para digitar SIM.
Os 12 .bat de hoje vão para a pasta instaladores, com os MESMOS nomes. Dentro deles, a linha cd /d "%~dp0" vira cd /d "%~dp0..".
As mensagens que dizem “rode o X na pasta do Jarvis” passam a dizer “no Instalar e Configurar”. Elas estão no main.py, no core/hermes_ponte.py (SEM_HERMES), no automacoes/painel_ultron.py, no claude_tarefas.py, nos hermes/*.ps1, gemma/*.ps1, claude/instalar_claude.ps1 e nos SKILL.md do email-triagem.
O VERSAO.txt avisa que os atalhos antigos na Área de Trabalho para os instaladores precisam ser refeitos.

- **Arquivos:** Instalar e Configurar.bat (novo); instaladores/*.bat (movidos); textos em main.py, core/hermes_ponte.py, automacoes/painel_ultron.py, automacoes/claude_tarefas.py, hermes/*.ps1, gemma/*.ps1, claude/instalar_claude.ps1, claude/skills/email-triagem/SKILL.md, hermes/agentes-futuros/email-triagem/SKILL.md; LEIA-ME.md; VERSAO.txt; tests/test_cerebro_gemma.py, test_jarvis_ultron.py, test_claude_chefe.py, test_documentacao.py
- **Como testar:** - Testes novos: todo .bat e .ps1 é ASCII; todo .bat da pasta instaladores começa com a linha nova e todo arquivo que ele chama existe; o menu oferece todos os .bat da pasta; nenhum texto diz mais “na pasta do Jarvis”.
- No PC: abrir o menu e rodar por ele o “Testar chave do Gemini” e o “Testar Telegram”.
- **Como desfazer:** git revert do commit: os .bat voltam para a raiz com o conteúdo antigo.
- **Ganho para o Erton:** Na pasta, ele vê dois botões em vez de treze: um abre o Jarvis, e o outro é um menu em português para todo o resto.

### Etapa 21: Opcionais e limpeza final  (risco: baixo)

Cada item só com o sim dele, um commit por item:
(a) automacoes/wikipedia_rapida.py: resumo de 2 ou 3 frases pela API REST da pt.wikipedia, com urllib (sem o pacote “wikipedia”, que está abandonado), e USA_IA_NUVEM=False. O LEIA-ME avisa que o termo pesquisado sai do PC. Assim o modo privado ganha uma fonte de fatos.
(b) Ler texto da tela sem nuvem, com o OCR que já vem no Windows (Windows.Media.Ocr): uma foto por pedido, nunca em laço, para o modo privado.
(c) Trocar a voz do Gemini falando: só nomes de SUPPORTED_VOICE_NAMES, e a troca vale na próxima conexão.
(d) Alerta de preço que só AVISA (lista local + lembretes): nunca compra e nunca raspa a Amazon. Baixa prioridade.
(e) Trocar as cerca de 10 cópias da limpeza de texto pelo core/texto.py, uma por commit, só onde uma tabela grande de frases de prova der resultado IDÊNTICO. A tabela inclui acentos, pontuação, negações como “não publica” e frases longas. NUNCA nas travas: o core/hermes_ponte.py, o core/aprovacao.py, o core/cerebro_gemma.py e o core/palavra_ativacao.py ficam como estão.
(f) Depois de alguns meses sem nada fazer falta, criar a etiqueta git “heranca-jarvis-os” e apagar a pasta arquivo/.

- **Arquivos:** automacoes/wikipedia_rapida.py e automacoes/ler_texto_local.py (novos); cerebro/ (troca de voz); automacoes/ (alerta de preço); arquivos com cópias da limpeza de texto (só os que passarem na prova); arquivo/ (apagado no fim)
- **Como testar:** - Um teste por item, com a rede simulada.
- No item (e), a tabela de frases dá resultado idêntico antes e depois.
- No PC: o roteiro do item, também no modo privado.
- **Como desfazer:** git revert do commit do item. A pasta arquivo/ volta pela etiqueta.
- **Ganho para o Erton:** Mais respostas sem nuvem no modo privado, cada uma só se ele quiser, e no fim a pasta fica só com o que é dele.

## O que trazer das referências

- REGRA GERAL: dos dois repositórios só vêm IDEIAS, reescritas do zero no padrão do Ultron (automação com FERRAMENTA + executar, e USA_IA_NUVEM=False quando não usa IA). Nenhuma linha de código, nenhum arquivo, nada executado ou instalado, e nada deles dentro de automacoes/, que carrega qualquer .py ao abrir.
- J.A.R.V.I.S-master → a lição de organização: a cadeia if/elif do jarvis.py apodreceu, com ramos repetidos que nunca rodam, um “if” solto que quebra a cadeia e uma condição sempre verdadeira. No Ultron, ela vira a tabela e a ficha única por ferramenta (Etapas 12–14).
- J.A.R.V.I.S-master → clima FALADO com dados reais, mas com o wttr.in, em português, e a cidade do .env, nunca localizando pelo IP (Etapa 9).
- J.A.R.V.I.S-master → notícias lidas em voz alta, que só abrem a matéria depois do “sim”, usando o RSS do Google Notícias, sem chave (Etapa 9).
- J.A.R.V.I.S-master → mapa por voz, com a URL do Google Maps codificada direito (Etapa 9).
- J.A.R.V.I.S-master → CPU e bateria no autodiagnóstico, tratando o PC de mesa sem bateria, que é o erro do original (Etapa 6).
- J.A.R.V.I.S-master → “Você quis dizer…?” com difflib, nas rotinas e nos lembretes (Etapa 10).
- J.A.R.V.I.S-master, opcional → a ideia do OCR local, feita com o OCR do próprio Windows, uma foto por pedido; trocar a voz falando; alerta de preço que só avisa (Etapa 21).
- Desktop-Voice-Assistant → o “mapa de comandos” que o README promete e o código não entrega. No Ultron, vira o registro de ferramentas (Etapas 13–14).
- Desktop-Voice-Assistant → o dicionário STRINGS, só em português e sem a parte de dois idiomas. Vira o core/frases.py (Etapa 8).
- Desktop-Voice-Assistant, pelo contraexemplo (“time” bate em “sometimes”) → uma função só para comparar por palavra inteira: o core/texto.py, usado primeiro só no código novo (Etapas 10 e 21).
- Desktop-Voice-Assistant → tocar música da pasta Música, sem internet (Etapa 10).
- Desktop-Voice-Assistant, pelo contraexemplo do README que promete o que não existe → o LEIA-ME e o VERSAO.txt descrevem só o que existe, e o que for retirado sai também dos textos.
- Os dois → print salvo com data e hora no nome, só no PC (Etapa 10), e saudação conforme a hora no cartão do bom dia (Etapa 9).
- Os dois, pelo contraexemplo (desligam à força com uma palavra solta) → desligar e reiniciar só com o “ok” conferido no código pelo core/aprovacao (Etapa 4).
- Os dois, opcional → resumo da Wikipedia pela API REST da pt.wikipedia, sem o pacote “wikipedia” abandonado e avisando que o termo pesquisado sai do PC (Etapa 21).

## O que NÃO trazer

- Nenhuma linha de código, nenhum arquivo e nada executado ou instalado dos dois repositórios. Nada deles dentro de automacoes/, que carrega qualquer .py ao abrir.
- SpeechRecognition com recognize_google: manda a voz para um serviço não oficial do Google, às vezes duas vezes, e quebra a regra do modo privado. O Ultron já tem o openWakeWord e o Whisper locais.
- O PyAudio-0.2.11-cp38-cp38-win_amd64.whl: binário de origem não verificável, feito só para Python 3.8, que não tem mais suporte. Não instalar de jeito nenhum.
- O pyttsx3 no lugar da voz atual: trava a tela com runAndWait() e não aceita ser chamado de vários fios.
- Reconhecimento de rosto como “senha” (LBPH + Haar): uma foto engana, e ele aceita qualquer pessoa treinada. Também o trainer.yml (rostos de duas pessoas de terceiros) e o gerador de fotos de rosto. A Biometria do Ultron continua só como detecção local e enfeite.
- O baixador de vídeos do YouTube (pytube 11, exec(open(...))): vai contra os Termos de Serviço do YouTube e trava o assistente.
- A raspagem da Amazon com User-Agent falso: vai contra as Condições de Uso, roda só de importar o arquivo e manda o e-mail “Price fell down!” sem comparar preço nenhum.
- Senhas e chaves no código (server.login com usuário e senha, apiKey da NewsAPI na URL por http) e e-mail por smtplib sem confirmação. O Ultron usa o cofre do Windows e o Gmail com OAuth e aprovação.
- Abrir no navegador a URL da própria NewsAPI, que expõe a chave e mostra JSON cru. O plano grátis dela é só para desenvolvimento.
- Localizar pela internet usando o IP (geocoder.ip ao importar) e falar latitude e longitude em voz alta. Nem a API de clima do Glitch, que não existe mais.
- Desligar ou reiniciar à força sem confirmação (shutdown /p /f ou /s /f /t 1) e “sleep” fechando o programa.
- Achar comandos por pedaço de texto (“palavra in frase”), detectar o idioma por uma lista de palavras e as respostas fixas de personalidade em inglês.
- except: sem tipo (engole até o Ctrl+C), código que roda ao importar e caminhos fixos do PC do autor (D:\RoiNa.mp3, C:\Users\gs935\..., Tesseract em C:\Program Files).
- O dicionário data.json em inglês (4,9 MB, sem origem nem licença), o data.txt com anotações pessoais dos autores e o pacote “wikipedia” 1.4.0, abandonado desde 2014.
- O OCR em laço contínuo pela webcam (OCR.py), que não sai nunca, deixa a câmera presa e roda o Tesseract em todo quadro.
- Os requirements.txt deles: versões de 2021 com falhas de segurança conhecidas (Pillow 8.3.2, requests 2.26.0, urllib3 1.26.7) e pacotes estranhos (loc, jsonlib-python3). Nunca misturar com o do Ultron nem rodar pip install deles.
- Ramos novos para Mac e Linux: o Ultron só roda no Windows.
- As imagens de terceiros (logo do YouTube, arte do J.A.R.V.I.S. da Marvel, imagens de artigos), que têm direitos incertos.

## O que sai ou vai para o arquivo

- Código morto do main.py (Etapa 5): o porteiro de palmas (wait_for_startup_claps, STARTUP_CLAP_* e tests/test_startup_clap.py), os 3 ajudantes de reconexão sem chamador, LOCAL_MACHINE_ONLY_ACTIONS, set_tour_active/_tour_active, as checagens do volume trancado do macOS e os atributos nunca lidos (_voice_changed, _interrupted_text, _ext_tts_voice_id e _ext_tts_api_key).
- Código morto do ui.py (Etapa 6): AIActivityCanvas, AIActivityConfig e _mode_sig; LogWidget; _show_voice_select, _on_voice_select_done e _close_voice_overlay; _feed_sparklines; o apelido VoicePresetOverlay; os 3 ganchos vazios; o carregamento do face.png; e LAYOUT_SETTINGS_FILE. O fio _SysMetrics deixa de nascer ao carregar o ui.py.
- Enfeites que fingem dados na tela antiga, só com o sim do Erton (Etapa 6): PresenceSystem, barra COG sorteada, AgentGrid com agentes falsos, sparklines escondidas e popups das teclas L e R.
- Peças que nada usa, para arquivo/pecas-sem-uso/ (Etapa 5): awareness/ (com memory/awareness-engine-enhanced.md e docs/MEMORY.md), memory/answer_cache.py e core/graphics_capability.py.
- Os 70 testes do tests/test_ui_regressions.py que cobram telas que não existem mais (Etapa 2).
- Da lista do Gemini, já na Etapa 3, e depois os arquivos, na Etapa 18: send_message, prepare_message_reply, check_messages (com message_monitor, instagram_browser e safe_text_entry, se as mensagens não voltarem), agent_task (agent/executor.py, planner.py e error_handler.py; o agent/task_queue.py FICA), code_helper, dev_agent, computer_control e game_updater.
- Com o sim do Erton (Etapa 18): flight_finder, reminder (repete o lembretes.py) e desktop_control (decidir com ele).
- Servidor web, se ele confirmar que não usa, para arquivo/servidor-web/ (Etapa 11): api/ (depois de mover o status.py para core/), web/, alembic/, alembic.ini, Dockerfile, docker-compose.yml, .dockerignore, fly.toml, render.yaml, deploy.yml, scripts/start_web_api.sh, test_hosted_api.py e test_phase1_decoupling.py (com as conferências de segurança já copiadas na Etapa 1). Os ramos cloud_safe/external_audio saem na Etapa 14.
- Mac/Linux, para arquivo/mac-linux/ (Etapa 11): os scripts start_jarvis.*, setup_jarvis.*, install_jarvis_cli.sh, scripts/jarvis e create_locked_dmg.sh, e os arquivos JARVIS.spec e JARVIS-Debug.spec. O pyproject.toml é reescrito curto ou apagado.
- Manuais herdados em inglês, para docs/original/ (Etapa 11): o README original, PRODUCT.md, DESIGN.md, CONTRIBUTING.md, docs/USAGE.md e docs/TUTORIAL.md. O LICENSE fica na raiz.
- Do .env.example (Etapa 11): DATABASE_URL, REDIS_URL, JWT_SECRET, JARVIS_ENCRYPTION_KEY e JARVIS_LOCKED_VOLUME. O JARVIS_TRIAL_KEYWORD só sai se o Erton confirmar.
- Do requirements.txt, num commit único (Etapa 18): fastapi, uvicorn, SQLAlchemy, alembic, psycopg, redis, email-validator, pywinauto e pygetwindow. O google-generativeai só sai depois de migrar as 3 actions que ficam, e o duckduckgo-search vira ddgs.
- Da ferramenta jarvis_ui_control (Etapa 7): as ações de mudar o tema e de abrir/fechar o Command Center, enquanto não fizerem efeito na tela azul.
- Os avisos “JARVIS is thinking...” e “Processing request...” (Etapa 8).
- Os write_status do tmp/jarvis_status.json, que ninguém lê, só se ele concordar (Etapa 16).
- A esfera clássica e a tela antiga inteira, só por decisão dele e só depois de levar para a tela azul o que ela tem de único (Etapa 19).
- No fim, depois de alguns meses: a pasta arquivo/, com a etiqueta git “heranca-jarvis-os” guardando tudo (Etapa 21).
- Fora do Jarvis: as pastas descompactadas dos dois repositórios de referência, no rascunho, podem ser apagadas depois da análise.

## Não mexer (travas e contratos)

- A trava do “ok”: core/aprovacao.py (marca, aprovou_depois, ainda_aprovado), core/hermes_ponte.py (PALAVRAS_OK/PALAVRAS_NAO, usuario_aprovou, aprovar_e_executar), hermes/hooks/aprovacao_jarvis.py (fail_closed) e o preço e o “ok” dos vídeos. A reorganização pode USAR essas funções em mais lugares, mas nunca mudar a lógica delas. Só os textos dos avisos podem ir para o core/frases.py, deixando apelidos no lugar.
- O modo privado: core/cerebro_gemma.py, a lista FERRAMENTAS_NUVEM_IA (que só cresce enquanto a ferramenta existir), o bloqueio_do_modo_privado com as regras por argumento, o USA_IA_NUVEM das automações, o selo 🔒, que lê JARVIS_CEREBRO no programa da tela, o _trocando_cerebro ligado ANTES do fio TrocarCerebro e o save_memory, que não grava no modo privado. Essas peças podem mudar de arquivo, com a foto provando que ficaram idênticas.
- A ORDEM das travas no começo do _execute_tool: cloud_safe → modo privado → operational_ready → modo QA → interceptar desligar → save_memory. Ela pode mudar de arquivo, mas nunca de ordem.
- As chaves: core/secret_store.py, core/api_key_validator.py e o caminho da chave na tela (SetupOverlay, _on_setup_done, KeyTutorialOverlay). A chave vai para o cofre só se ele marcar, para o .env só se for aceita, e nunca para o config/api_keys.json; o campo fica mascarado. Traduzir os textos é permitido; mudar o caminho da chave, não.
- O aviso sigiloso, que só sai pela voz do Windows (_falar_no_pc), nunca pelo Gemini, e a conferência de “fala nova” contra “resto atrasado” no _receive_audio.
- O contrato entre a tela e o cérebro: core/ponte.py (METODOS_TELA, CHAMADAS_DO_CEREBRO), core/processo_cerebro.py chamando main.rodar_cerebro, core/na_tela.py e a JarvisUI, com os mesmos 29 nomes.
- Os nomes que outros arquivos usam dentro da JarvisLive (anunciar, _falar_aviso, _hermes_sem_travar, _ativar_modo_reserva, _reserva, _modo_reserva, _cerebro_nome, rodar_automacao_ultron, _definir_modo_escuta, _shutdown_requested, _loop, _abrir_ultron, os _fala_* e session) e os nomes dos fios VideoVeo, ClaudeTarefa, ClaudePlano e HermesPublicar.
- O main.py, com o mesmo nome e no mesmo lugar, e os efeitos que ele tem ao ser importado (carregar o .env, a via Studio/Vertex e instalar a central de modelos), iguais e na mesma ordem. Os módulos novos não podem ler os.environ nem criar cliente do Gemini ao serem importados.
- O “Iniciar Jarvis Ultron.bat”, com o mesmo nome e a mesma ordem (desfazer a mudança interrompida do Claude antes de instalar), e os caminhos que os .bat usam (%~dp0, hermes\*.ps1, gemma\*.ps1, claude\*.ps1).
- O ui_orbe_gpu.py inteiro (teste antes de ligar, vigia de “nunca desenhou”, orbe_gpu_falhou, OpenGL por software), o desenho do anel no ui_orbe.py e o _nivel_suave do HudCanvas, que faz o anel pulsar com a voz.
- A cadeia de reserva (Gemma → Groq → outra empresa), o LoopReserva e o tempo-limite HERMES_ESPERA. O RESERVA_FERRAMENTAS_ESSENCIAIS só perde as ferramentas desligadas de propósito.
- A voz e a escuta: core/palavra_ativacao.py (“Hey Jarvis”), o Whisper local do modo privado e o actions/tts_engine.py.
- O Claude chefe (core/claude_chefe.py), com a foto do código e o desfazer.
- O texto das descrições das ferramentas (o Gemini decide por ele), os resultados em inglês que voltam para o modelo (“Done.”), o pedido [FILE_UPLOADED] e os prefixos “You:”, “Jarvis:”, “SYS:” e “ERR:”. Isso só muda de arquivo, palavra por palavra, salvo uma mudança de propósito numa etapa marcada, com a foto atualizada no mesmo commit.
- O core/prompt.txt, que só muda quando uma ferramenta sai ou volta, e no mesmo commit.
- Os dados locais do Erton: .env, config/api_keys.json, memory/long_term.json, memory/task_history.json, tmp/ e Documentos/Jarvis Ultron/. Nunca versionar, apagar nem deixar os testes escreverem neles.
- Pastas e caminhos fixos: memory/ (o memoria_hd copia por caminho fixo), claude/skills (fonte dos agentes), hermes/agentes-futuros (até o Erton decidir), automacoes/ e o carregador core/automacoes.py.
- O core/tenant.py e o core/jarvis_client.py: a memória, o Gmail e a fila dependem deles, mesmo depois de o servidor ser guardado.
- O LICENSE (MIT do JARVIS-OS), com o aviso de autoria, e as licenças das fontes em assets/fonts.

## Decisões do Erton

- **Como você prefere receber as versões novas do Jarvis durante a reorganização? (antes da Etapa 3)**
  - Opções: Uma por vez, com alguns dias de uso entre elas | As de risco baixo juntas; as de risco médio ou alto sozinhas, com alguns dias de uso | Tudo de uma vez no fim
  - Recomendação: As de risco baixo juntas e as de risco médio ou alto sozinhas. A cada versão, você guarda a pasta da versão anterior, copia o .env para a nova e faz o roteiro de 5 minutos. Se algo estranhar, volta a abrir o Iniciar da pasta antiga e avisa.
- **Você manda mensagens pelo Jarvis (WhatsApp, Telegram, Discord, Instagram) ou pede para ele ler as suas mensagens? Hoje ele pode enviar direto, sem o seu “ok” conferido no código. (antes da Etapa 3)**
  - Opções: Não uso: pode desligar | Uso só o WhatsApp: refazer com rascunho, leitura em voz alta e “ok” antes de enviar | Uso e quero como está
  - Recomendação: Desligar agora. Se fizer falta, refazer só o WhatsApp com o “ok” conferido no código, como já acontece na publicação e nos vídeos. Manter como está vai contra a sua regra de “ok” antes de enviar.
- **Você usa alguma destas ferramentas herdadas: “faça tal tarefa no PC” (agent_task), o programador antigo (code_helper/dev_agent), controle de mouse e teclado (computer_control), atualizar jogos (game_updater), buscar voos (flight_finder), lembrete pelo Agendador do Windows (reminder), papel de parede ou limpar a área de trabalho (desktop_control)? (antes das Etapas 3 e 18)**
  - Opções: Não uso nenhuma: pode desligar todas | Uso algumas (dizer quais) | Não sei: desligar e ver se faz falta em duas semanas
  - Recomendação: Desligar já na Etapa 3 as que agem sem “ok”: agent_task, code_helper, dev_agent, computer_control e game_updater. O Claude chefe faz o trabalho delas com plano e “ok”. Voos, reminder e papel de parede esperam a sua resposta e só saem na Etapa 18.
- **O que fazer com o que sai (servidor, scripts de Mac, ferramentas herdadas)? (antes da Etapa 5)**
  - Opções: Guardar numa pasta “arquivo” por algumas semanas e depois apagar (o git guarda tudo para sempre) | Apagar já (o git guarda tudo para sempre) | Deixar tudo onde está
  - Recomendação: Guardar na pasta “arquivo” por algumas semanas: fica fácil ver o que saiu e trazer de volta. Depois, apagar, com uma etiqueta no git que guarda tudo.
- **Na tela antiga há enfeites que fingem dados: frases inventadas em inglês, “agentes” de mentira, um número COG sorteado, gráficos escondidos e os popups das teclas L e R. Podem sair? (antes da Etapa 6)**
  - Opções: Sim, tirar | Não, manter
  - Recomendação: Tirar: eles mostram coisas que não são verdade e gastam processador.
- **Hoje existem dois avisos diferentes do modo privado: um geral e outro para os vídeos. Como devem ficar? (antes da Etapa 8)**
  - Opções: Manter os dois textos, cada um no seu caso | Um texto só para tudo (dizer qual)
  - Recomendação: Manter os dois, guardados juntos no core/frases.py. Assim você muda qualquer um deles editando um arquivo só.
- **Os prints salvos pelo Jarvis devem ser copiados para o HD externo junto com a memória? (antes da Etapa 10)**
  - Opções: Não: ficam só no PC | Sim: copiar também
  - Recomendação: Ficar só no PC: um print pode ter dado sensível, como senha, conversa ou banco.
- **Você usa o Jarvis por algum site ou servidor na internet (a “versão web” herdada do JARVIS-OS)? (antes da Etapa 11)**
  - Opções: Não uso: pode guardar o servidor | Uso: manter como está | Não sei
  - Recomendação: Guardar. O LEIA-ME não cita nenhum site, os testes automáticos do GitHub só testam o servidor, e ele traz 7 componentes que você instala à toa. Se a resposta for “não sei”, o Claude confere antes se há algum serviço ligado.
- **Você usa o “modo de teste com prazo” herdado (JARVIS_TRIAL_KEYWORD)? (antes da Etapa 11)**
  - Opções: Não uso: pode sair | Uso: manter
  - Recomendação: Tirar, num commit separado, se você não usa.
- **Você ainda usa a tela antiga (F2) ou o Command Center (Ctrl+Shift+C)? O que usa nela: soltar arquivo, trocar a voz externa, trocar o nome, o bloco de notas da Stark, as legendas? (antes da Etapa 19)**
  - Opções: Uso: manter, mas parada enquanto escondida | Uso pouco: manter, mas montando só quando eu apertar F2 | Não uso: aposentar depois de levar para a tela azul o que só ela tem
  - Recomendação: Manter por enquanto, parada enquanto escondida (Etapa 6). Decidir aposentar só depois que a tela azul tiver tudo o que você usa nela.
- **Você usa a esfera clássica (JARVIS_VISUAL=classico) em vez do anel azul? (antes da Etapa 19)**
  - Opções: Não uso: guardar | Uso: manter
  - Recomendação: Guardar: o padrão é o anel, e a esfera clássica tem cerca de 900 linhas que só pesam.
- **Prefere a pasta com só dois botões (“Iniciar Jarvis Ultron” e um menu “Instalar e Configurar”) em vez dos 13 .bat de hoje? Os atalhos antigos dos instaladores na Área de Trabalho teriam de ser refeitos. (antes da Etapa 20)**
  - Opções: Sim, dois botões | Não, deixar os 13 como estão
  - Recomendação: Sim, mas só no fim, quando todo o resto estiver estável.
- **Quer o resumo rápido da Wikipedia, também no modo privado, sabendo que o termo pesquisado sai do PC (para a Wikipedia, não para uma IA)? (antes da Etapa 21)**
  - Opções: Sim, com o aviso | Não
  - Recomendação: Sim: dá ao modo privado uma fonte de fatos sem IA na nuvem, e só o termo pesquisado sai do PC.
- **Durante a reorganização (algumas semanas), tudo bem não pedir ao Claude chefe mudanças no código do próprio Jarvis?**
  - Opções: Sim | Não, preciso dele para isso
  - Recomendação: Sim. Se os dois mexerem no mesmo código ao mesmo tempo, um pode desfazer o trabalho do outro. O Claude chefe continua livre para todo o resto.

## Notas das três propostas

- **Proposta 1 — Reorganização em passos pequenos e seguros (risco mínimo)** — 8.5: Segurança 10/10. A regra é “mover, não reescrever”: os nomes antigos continuam valendo (reexportação), há fotos do comportamento de hoje, uma sentinela impede os testes de mexer nos arquivos reais, e cada passo passa por pyflakes e por “git diff --color-moved”. O Erton guarda a pasta da versão anterior. As duas portas abertas (mensagem sem ok e código gerado pela IA) são fechadas logo na Etapa 3, só tirando as ferramentas da lista.

Benefício 7/10. O que ele sente chega tarde: o desligar com ok só na Etapa 25, o clima falado e as novidades das referências só nas 26–28, e o servidor só é guardado na 22.

Esforço 6/10. São 29 etapas, um caminho longo, mas cada uma é pequena.

Fidelidade 8/10. Aproveita bem a lição do if/elif e do “mapa de comandos”, mas deixa as ideias das referências para o fim.

Foi a ESPINHA do plano final.
- **Proposta 2 — Um cômodo para cada coisa, sem perder nenhuma fechadura (estrutura limpa)** — 7.5: Segurança 8/10. Traz boas ideias próprias: teste de invariantes, core/SEGURANCA.md, um teste que confere se todo atributo nasce no __init__ e testes do “ok” antes de mover o _receive_audio. Também põe cedo o desligar com ok. Por outro lado, tira enfeites visíveis no F2 sem perguntar e mexe cedo (Etapa 6) nas funções de comparar a fala, que fazem parte das travas. Na Etapa 13, de risco alto, muda de lugar o ui_orbe e o ui_orbe_gpu (o anel na placa de vídeo, que deu trabalho para estabilizar) por pouco ganho.

Benefício 8/10. É a estrutura final mais completa e bonita.

Esforço 6/10. Tem duas etapas enormes de risco alto (8 e 13).

Fidelidade 8/10. As ideias das referências só chegam na última etapa, todas de uma vez.
- **Proposta 3 — Mais leve, mais simples e todo em português (leveza para o usuário)** — 8: Benefício 9,5/10. É a que mais pensa no que o Erton sente: mede a CPU antes e depois, deixa o PC mais leve, põe tudo em português, mostra na tela azul o que estava escondido, traz cedo o clima falado e as outras novidades e reduz a pasta a dois botões.

Fidelidade 8,5/10. Traz cedo as ideias das referências e tem a lista mais clara do que NÃO trazer.

Segurança 7,5/10:
- apaga o test_phase1_decoupling, que guarda conferências do modo privado;
- apaga as coisas em vez de guardá-las;
- tira os enfeites da tela antiga sem perguntar;
- move cedo os 12 .bat e o core/qa_audit, o que mexe em muitos caminhos;
- o desligar com ok só vem na Etapa 10.

Esforço 7/10. Tem menos etapas, mas a divisão do main.py e do ui.py, que é a parte mais arriscada, fica como uma única etapa final “opcional”, vaga demais.
