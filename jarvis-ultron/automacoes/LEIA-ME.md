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

Arquivos terminados em `.exemplo` são só modelos e não são carregados.
