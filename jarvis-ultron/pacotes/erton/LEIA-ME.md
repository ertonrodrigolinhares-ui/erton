# Pacote do dono: erton

Agentes e habilidades que são do criador do Jarvis (perfil de atleta, família, escola dos filhos e
contabilidade). **Não fazem parte do produto**: o cliente não os recebe.

Para usá-los no seu PC, ponha no `.env` do Jarvis:

```
JARVIS_PACOTE=erton
```

Com isso:
- `claude/skills` daqui entra no `Ativar Agentes`, no painel Ultron e no Claude (o Jarvis copia junto
  com os agentes do produto na próxima tarefa);
- `hermes/skills/jarvis` entra no perfil do Hermes quando você roda o `Instalar Hermes`, que também
  cria as rotinas (posts das 8h e Geekie) porque elas existem;
- `hermes/agentes-futuros` são as cópias para o Hermes que o `Ativar Agentes` usa.

Para um pacote de outra pessoa: copie esta pasta com outro nome (`pacotes/<nome>`) e troque a linha
do `.env`. O nome só aceita letras minúsculas, números e `-`.
