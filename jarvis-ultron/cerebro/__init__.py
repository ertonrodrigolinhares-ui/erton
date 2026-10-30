"""O cérebro do Jarvis Ultron em pedaços (Etapas 12 a 16 da reorganização).

A JarvisLive (main.py) é UMA classe, montada com os pedaços daqui, cada um com um assunto e o nome em
português (tests/test_cerebro_em_pedacos.py diz o que mora em cada um):
  ambiente.py      a pasta do Jarvis e os caminhos fixos
  avisos.py        lembretes e avisos falados (anunciar, _falar_aviso, _falar_no_pc)
  escuta.py        modo chamada / mãos livres ("Hey Jarvis")
  pontes.py        Hermes, Geekie One e autodiagnóstico
  voz_saida.py     a voz dele (vozes, voz externa, o que vai para a fala)
  ultron.py        o painel Ultron pela voz e pelos botões
  desligar.py      desligar só depois da despedida; suspender por alguns minutos
  entrada.py       o que o Erton digita e o áudio do microfone
  reserva.py       Groq / outra empresa / Gemma 4 quando o Gemini cai
  modo_privado.py  a troca de cérebro (Gemma no PC ou Gemini)
  ferramentas/     declarações, fichas, regras, executores e o registro das automações
O main.py continua sendo a porta de entrada (e a conversa ao vivo com o Gemini) e reexporta os nomes antigos."""
