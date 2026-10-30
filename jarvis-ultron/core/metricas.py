"""Leitura do computador (CPU, memória, disco, rede, placa de vídeo, temperatura) num lugar só.

Antes, três lugares liam o psutil por conta própria: a tela antiga, num fio que nascia só de importar o
ui.py e lia o sistema a cada 1,5 s mesmo com o painel escondido; a Cena (tela azul); e a tela Stark. E a
tela antiga abria programas de fora (nvidia-smi, powershell) a cada poucos segundos, com janela preta no
Windows. Aqui (Etapa 6 da reorganização):

- nada roda ao importar: a primeira leitura acontece quando alguém pede (ler());
- a leitura leve (CPU, memória, disco, rede) é feita na hora, no máximo uma vez a cada INTERVALO
  segundos; quem pedir de novo nesse meio tempo recebe o mesmo retrato. Assim a CPU dá o mesmo número em
  todas as telas (o psutil.cpu_percent(interval=None) mede desde a última chamada: chamadas espalhadas
  por vários lugares davam números diferentes);
- a leitura pesada (placa de vídeo e temperatura abrem programas de fora) só acontece se a ferramenta
  existe no PC, roda num fio curto para não prender a tela, só de vez em quando (INTERVALO_PESADO),
  sem janela preta no Windows (CREATE_NO_WINDOW), e para de tentar quando o PC não tem como responder;
- amostra_cpu() mede, numa janela só, a CPU do computador e a de cada programa do Jarvis (tela e
  cérebro), para o autodiagnóstico.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import threading
import time
from typing import Iterable

INTERVALO = 1.5         # segundos entre leituras leves (CPU, memória, disco, rede)
INTERVALO_PESADO = 12.0  # segundos entre leituras da placa de vídeo e da temperatura
TEMPO_LIMITE = 3         # segundos para um programa de fora responder

SEM_LEITURA = -1.0  # placa de vídeo ou temperatura: "não dá para ler neste PC"

_SEM_JANELA = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}


def _rodar(comando: list[str], tempo: float = TEMPO_LIMITE) -> str:
    """Saída de um programa de fora, sem janela preta no Windows; "" se ele falhar."""
    try:
        r = subprocess.run(comando, capture_output=True, text=True, timeout=tempo, **_SEM_JANELA)
    except (OSError, subprocess.SubprocessError):
        return ""
    return r.stdout if r.returncode == 0 else ""


def _ler_gpu() -> float:
    """Uso da placa de vídeo (0 a 100), ou SEM_LEITURA. Só chama programas que existem no PC."""
    if shutil.which("nvidia-smi"):
        saida = _rodar(["nvidia-smi", "--query-gpu=utilization.gpu", "--format=csv,noheader,nounits"])
        valores = []
        for linha in saida.splitlines():
            try:
                valores.append(float(linha.strip()))
            except ValueError:
                continue
        if valores:
            return sum(valores) / len(valores)
    if shutil.which("rocm-smi"):  # AMD
        for linha in _rodar(["rocm-smi", "--showuse", "--csv"]).splitlines():
            partes = linha.split(",")
            if len(partes) >= 2:
                try:
                    return float(partes[1].strip().replace("%", ""))
                except ValueError:
                    continue
    return SEM_LEITURA


def _ler_temperatura() -> float:
    """Temperatura do processador em °C, ou SEM_LEITURA."""
    import psutil

    leitor = getattr(psutil, "sensors_temperatures", None)
    if leitor is not None:
        try:
            sensores = leitor() or {}
        except Exception:
            sensores = {}
        for nome in ("coretemp", "k10temp", "cpu_thermal", "acpitz", "cpu-thermal", "zenpower", "it8688"):
            if sensores.get(nome):
                return float(sensores[nome][0].current)
        for entradas in sensores.values():
            if entradas:
                return float(entradas[0].current)
    if os.name == "nt":
        saida = _rodar(["powershell", "-NoProfile", "-Command",
                        "(Get-CimInstance MSAcpi_ThermalZoneTemperature -Namespace root/wmi).CurrentTemperature"])
        primeira = saida.strip().split("\n")[0].strip() if saida.strip() else ""
        try:
            return float(primeira) / 10.0 - 273.15
        except ValueError:
            pass
    return SEM_LEITURA


class _Leitor:
    def __init__(self):
        self._trava = threading.Lock()
        self._retrato = {"cpu": 0.0, "mem": 0.0, "disco": 0.0, "net": 0.0,
                         "gpu": SEM_LEITURA, "tmp": SEM_LEITURA}
        self._lido_em = 0.0
        self._pesado_em = 0.0
        self._pesado_rodando = False
        self._rede_antes = None  # (instante, bytes enviados, bytes recebidos)
        self._gpu_off = False    # o PC não tem como ler: não tenta mais
        self._tmp_off = False

    def ler(self) -> dict:
        agora = time.monotonic()
        with self._trava:
            if agora - self._lido_em >= INTERVALO:
                try:
                    self._leve(agora)
                except Exception:
                    pass  # uma leitura que falha não derruba a tela; fica o retrato anterior
                self._lido_em = agora
            pesado = (not self._pesado_rodando and not (self._gpu_off and self._tmp_off)
                      and agora - self._pesado_em >= INTERVALO_PESADO)
            if pesado:
                self._pesado_rodando = True
                self._pesado_em = agora
            retrato = dict(self._retrato)
        if pesado:
            threading.Thread(target=self._pesado, daemon=True, name="MetricasPesadas").start()
        return retrato

    def _leve(self, agora: float) -> None:
        import psutil

        r = self._retrato
        r["cpu"] = float(psutil.cpu_percent(interval=None))
        r["mem"] = float(psutil.virtual_memory().percent)
        try:
            r["disco"] = float(psutil.disk_usage(raiz_do_disco()).percent)
        except OSError:
            pass
        rede = psutil.net_io_counters()
        if self._rede_antes is not None:
            t0, env0, rec0 = self._rede_antes
            passou = agora - t0
            if passou > 0:
                r["net"] = ((rede.bytes_sent - env0) + (rede.bytes_recv - rec0)) / passou / (1024 * 1024)
        self._rede_antes = (agora, rede.bytes_sent, rede.bytes_recv)

    def _pesado(self) -> None:
        try:
            gpu = SEM_LEITURA if self._gpu_off else _ler_gpu()
            tmp = SEM_LEITURA if self._tmp_off else _ler_temperatura()
        except Exception:
            gpu = tmp = SEM_LEITURA
        with self._trava:
            if not self._gpu_off:
                self._retrato["gpu"] = gpu
                self._gpu_off = gpu < 0
            if not self._tmp_off:
                self._retrato["tmp"] = tmp
                self._tmp_off = tmp < 0
            self._pesado_rodando = False


_leitor = _Leitor()


def ler() -> dict:
    """Retrato do computador: cpu, mem e disco em %, net em MB/s, gpu em % e tmp em °C (ou SEM_LEITURA)."""
    return _leitor.ler()


def raiz_do_disco() -> str:
    return os.environ.get("SystemDrive", "C:") + "\\" if os.name == "nt" else "/"


def amostra_cpu(pids: Iterable[int], segundos: float = 0.5) -> tuple[float, dict[int, float], dict[int, int]]:
    """Numa janela só de `segundos`: CPU do computador (%), CPU de cada programa pedido (% do processador
    inteiro, já dividida pelos núcleos) e a memória de cada um (bytes). Programas que não existem mais
    ficam de fora."""
    import psutil

    processos = []
    for pid in pids:
        try:
            processos.append(psutil.Process(int(pid)))
        except (psutil.Error, ValueError):
            continue
    psutil.cpu_percent(interval=None)  # abre a janela de medição
    for p in processos:
        try:
            p.cpu_percent(interval=None)
        except psutil.Error:
            pass
    time.sleep(segundos)
    nucleos = psutil.cpu_count() or 1
    pc = float(psutil.cpu_percent(interval=None))
    por_programa: dict[int, float] = {}
    memoria: dict[int, int] = {}
    for p in processos:
        try:
            por_programa[p.pid] = float(p.cpu_percent(interval=None)) / nucleos
            memoria[p.pid] = int(p.memory_info().rss)
        except psutil.Error:
            continue
    return pc, por_programa, memoria


def bateria():
    """(porcentagem, na tomada) ou None quando o PC não tem bateria (computador de mesa)."""
    import psutil

    leitor = getattr(psutil, "sensors_battery", None)
    if leitor is None:
        return None
    try:
        b = leitor()
    except Exception:
        return None
    if b is None or b.percent is None:
        return None
    return float(b.percent), bool(b.power_plugged)
