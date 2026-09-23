# Jarvis — assistente pessoal em Python

Assistente pessoal que escuta, fala e conversa usando a inteligência artificial do Claude (Anthropic).

## Como funciona

```
Você fala/digita ──► comandos locais (hora, data, sites, pesquisa, contas, piadas)
                        │ não reconheceu?
                        ▼
                     Claude (IA) ──► resposta falada/escrita
```

| Arquivo | Função |
|---|---|
| `jarvis/main.py` | Loop principal: ouvir → entender → responder |
| `jarvis/voz.py` | Fala (pyttsx3) e reconhecimento de voz (SpeechRecognition), com modo texto automático |
| `jarvis/comandos.py` | Comandos rápidos que não precisam de IA |
| `jarvis/cerebro.py` | Conversa com o Claude, mantendo o histórico |
| `jarvis/config.py` | Configurações via `.env` |

## Instalação

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # e coloque sua ANTHROPIC_API_KEY
```

A chave da API é criada em https://console.anthropic.com. No Windows, se o `pyaudio` falhar, use `pip install pipwin && pipwin install pyaudio`; no Linux, `sudo apt install portaudio19-dev espeak` antes.

## Uso

```bash
python -m jarvis            # modo voz: diga "Jarvis, que horas são?"
python -m jarvis --texto    # conversa digitando no terminal
python -m jarvis --sem-ia   # só comandos locais, sem usar a API
```

Exemplos: "que horas são", "que dia é hoje", "abra o YouTube", "pesquise holding familiar",
"pesquisar no youtube ironman havaí", "calcule 1500 vezes 12", "conte uma piada".
Qualquer outra pergunta vai para o Claude. Diga "nova conversa" para limpar o histórico e "sair" para encerrar.

## Adicionando um comando

Em `jarvis/comandos.py`, crie uma função que recebe o texto (minúsculo, sem acentos) e retorna a resposta ou `None`, e inclua-a na lista `COMANDOS`:

```python
def cmd_bom_dia(texto: str) -> str | None:
    if "bom dia" not in texto:
        return None
    return "Bom dia! Pronto para mais um dia de alta performance."
```

## Testes

```bash
pip install pytest
python -m pytest
```
