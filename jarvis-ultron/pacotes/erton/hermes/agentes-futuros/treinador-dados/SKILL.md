---
name: treinador-dados
description: "Treinador de dados: lê os treinos do Strava/Garmin e faz o resumo da semana (volume, ritmo, frequência cardíaca, sinais de cansaço)."
version: 1.0.0
metadata:
  hermes:
    tags: [jarvis, futuro]
    category: jarvis
---
# Treinador de dados

Treinador de dados: lê os treinos do Strava/Garmin e faz o resumo da semana (volume, ritmo, frequência cardíaca, sinais de cansaço).

## Requisitos
- Conectar o Strava ou o Garmin (MCP ou exportação de arquivos).
- Sem conector, o agente pode ler arquivos .fit/.gpx/.csv exportados para a pasta Documentos\Jarvis Ultron\Treinos.

## Procedimento
1. Leia os treinos dos últimos 7 dias (e os 28 dias anteriores para comparar).
2. Calcule por modalidade (natação, bike, corrida): distância, tempo, ritmo/velocidade médios e FC média.
3. Compare com as 4 semanas anteriores: subiu ou caiu o volume? Mais de 10% de aumento em uma semana é alerta.
4. Aponte sinais de cansaço: FC em repouso subindo, ritmo piorando com a mesma FC, poucos dias de descanso.
5. Responda em até 5 frases faladas: resumo, destaque positivo, um ponto de atenção e uma sugestão para a próxima semana.

## Regras
- Não dê diagnóstico médico. Diante de dor, lesão ou sintoma, recomende procurar um profissional.
- Não publique dados de treino sem o ok do Erton.
