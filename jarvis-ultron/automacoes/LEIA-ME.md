# Pasta de automações do Jarvis Ultron

Cada automação nova é **um arquivo só**. Para instalar:

1. Salve o arquivo **nesta pasta** (`jarvis-ultron/automacoes`).
2. Feche e abra o Jarvis de novo.
3. Pronto. A janela do Jarvis mostra "Automações: ..." com o nome dela.

Para **desligar** uma automação, apague o arquivo daqui (ou coloque `_` no começo do nome).
Se um arquivo tiver algum problema, o Jarvis abre normalmente, avisa na tela qual é o arquivo
e o autodiagnóstico (botão ✚) mostra o motivo.

## Tipos de arquivo

- **`.py`**: uma função nova que o Jarvis usa por voz (ex.: consultar algo, calcular algo).
- **`.md`**: um agente/rotina do Hermes (ex.: "todo dia às 7h, leia tal site e me avise").
  O Jarvis copia para o Hermes sozinho e, se tiver horário, cria a rotina.

Um `.py` também pode trabalhar sozinho (sem você pedir) ou acrescentar algo na tela: basta ter a
função `iniciar(jarvis)`, que roda quando o Jarvis abre.

Arquivos terminados em `.exemplo` são só modelos e não são carregados.

## Automações que já vêm na pasta

| Arquivo | O que faz | Como usar |
|---|---|---|
| `autoconserto.py` | Diagnostica e conserta sozinho o que é seguro | "Jarvis, conserte seus problemas" |
| `lembretes.py` | Lembretes falados (no modo chamada, esperam o "Hey Jarvis") | "Jarvis, me lembra às 15h de ligar para o contador" · "quais são meus lembretes?" · "cancela o lembrete 2" |
| `rotinas.py` | Rotinas salvas: seus agentes para tarefas repetidas | "Jarvis, rotina bom dia" · "salve a rotina treino: ..." · "quais rotinas eu tenho?" |
| `memoria_hd.py` | Salva tudo o que o Jarvis aprende no seu HD externo (a cada 30 min, com histórico de 30 dias; nunca copia chaves) | "Jarvis, use o HD E como memória" · "salve sua memória no HD agora" |
| `painel_stark.py` | Central de missões na tela Stark (lembrete, Geekie, agentes, botões das rotinas) | Aparece sozinha na coluna da direita |

Lembretes e rotinas ficam salvos em `Documentos/Jarvis Ultron` (`lembretes.json` e `rotinas.json`).
Para falar os avisos mesmo no modo chamada, coloque `JARVIS_AVISO_FALA_SEMPRE=1` no `.env`.
