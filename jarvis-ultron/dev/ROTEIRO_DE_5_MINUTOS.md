# Roteiro de 5 minutos (conferir cada versão nova do Jarvis)

Durante a reorganização (docs/PLANO-REORGANIZACAO.md), cada versão nova chega com este roteiro. Ele
confere, no seu PC, o que os testes automáticos não veem: a voz, a tela e as travas do "ok".

## Antes de começar

1. Feche o Jarvis de verdade: botão direito no ícone perto do relógio → **Quit JARVIS** (depois
   da tradução da tela, o nome passa a ser **Sair do Jarvis**). O X só esconde.
2. **Guarde a pasta da versão anterior** (não apague): é a sua volta segura.
3. Extraia a versão nova numa pasta nova e **copie o seu `.env`** da pasta antiga para a nova.

## O roteiro

Para cada passo, o que fazer e o que tem de acontecer.

1. **Abrir:** dois cliques em **"Iniciar Jarvis Ultron"**.
   - Abre a tela azul com o anel, sem erro na janela preta (ela mostra `[Ponte] Cérebro conectado`).
2. **Conversa:** diga **"Hey Jarvis, como está o tempo?"**.
   - Ele acorda com o "Hey Jarvis" e responde sobre o tempo.
3. **Modo privado** (só se o Gemma 4 estiver instalado; se não, pule para o passo 5): diga
   **"Jarvis, modo privado"**.
   - Aparece o selo **🔒 MODO PRIVADO** no alto da tela, e ele diz que está rodando no Gemma 4.
   - Peça **"Jarvis, pesquise na internet o preço do ouro hoje"**: ele tem de **recusar**, dizendo
     que no modo privado isso não é usado (iria para uma IA na nuvem).
4. **Modo normal:** diga **"Jarvis, modo normal"**.
   - O selo 🔒 some, e ele volta para o Gemini.
5. **Painel Ultron:** diga **"Jarvis, modo Ultron"** (ou clique no botão **⚙ ULTRON**) e, no painel,
   clique em **⏰ Meus lembretes**.
   - O painel fecha, e o resultado aparece na tela uma vez só e é falado.
6. **Vídeo com "não":** diga **"Jarvis, faz um vídeo de 8 segundos de um triatleta cruzando a linha
   de chegada"**. Ele diz o preço e pergunta se pode fazer: responda **"não"**.
   - Nada é gerado: nenhum vídeo novo em `Documentos\Jarvis Ultron\Videos` e nenhum aviso de vídeo
     pronto depois.
7. **F2:** aperte **F2** (vai para a tela antiga) e **F2** de novo.
   - Volta para a tela azul com o anel, sem travar.
8. **Fechar:** clique no **X** da janela.
   - A janela some, mas o ícone continua perto do relógio (o Jarvis continua ouvindo).
   - Botão direito no ícone → **Quit JARVIS** (ou **Sair do Jarvis**): o Jarvis fecha de verdade,
     e a janela preta fecha junto.

## Se algo estranhar

Feche o Jarvis, abra o **"Iniciar Jarvis Ultron"** da **pasta antiga** (que você guardou) e avise,
dizendo em qual passo foi. No código, a volta é um `git revert` do commit da etapa.
