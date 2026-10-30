"""Medidas do computador e do próprio Jarvis (psutil), numa fonte só.

Quem lê daqui: a Cena (painel "Sistema"), a tela antiga (F2), a tela Stark e o autodiagnóstico.
Até a etapa 6 da reorganização, cada tela lia o psutil por conta própria e a tela antiga ainda
abria um fio ao importar o ui.py, que lia o sistema a cada 1,5 s para painéis que ninguém via.

Regras deste arquivo:
- nada nasce ao importar: o medidor só lê quando alguém pede um `retrato()`;
- CPU, memória e rede são leituras baratas e vêm na hora (no máximo uma por segundo);
- GPU e temperatura abrem programas externos (lentos): são lidos num fio à parte, só a cada
  12 s, sem abrir janela preta no Windows, e param de tentar quando não há ferramenta.
"""

from __future__ import annotations

import os
import platform
import re
import subprocess
import threading
import time

_OS = platform.system()
INTERVALO = 1.0          # segundos entre leituras de CPU, memória e rede
INTERVALO_EXTRA = 12.0   # GPU e temperatura mudam devagar

VAZIO = {"cpu": 0.0, "mem": 0.0, "swap": 0.0, "net": 0.0, "envio": 0.0, "recebido": 0.0,
         "gpu": -1.0, "tmp": -1.0}


def _sem_janela() -> dict:
    """No Windows, um programa de linha de comando aberto pela tela abriria uma janela preta."""
    return {"creationflags": subprocess.CREATE_NO_WINDOW} if _OS == "Windows" else {}


def _rodar(comando: list[str], tempo: float):
    return subprocess.run(comando, capture_output=True, text=True, timeout=tempo, **_sem_janela())


class Medidor:
    def __init__(self):
        self._lock = threading.Lock()
        self._valores = dict(VAZIO)
        self._lido_em = 0.0
        self._rede_antes = None
        self._extra_em = 0.0
        self._extra_fio: threading.Thread | None = None
        self._gpu_off = False
        self._temp_off = False

    # ----- o que as telas leem
    def retrato(self) -> dict:
        """CPU (%), memória (%), swap (%), rede (MB/s, 'envio' e 'recebido' em bytes/s), GPU (%) e
        temperatura (°C). GPU e temperatura valem -1 enquanto não há leitura."""
        agora = time.time()
        fio = None
        with self._lock:
            if agora - self._lido_em >= INTERVALO:
                try:
                    self._ler(agora)
                except Exception:
                    pass
                self._lido_em = agora
            if self._extras_vencidos(agora):
                self._extra_em = agora
                fio = self._extra_fio = threading.Thread(target=self._ler_extras, daemon=True, name="Metricas-extras")
            valores = dict(self._valores)
        if fio is not None:
            fio.start()  # fora da trava: o fio também a usa para gravar o que leu
        return valores

    def _extras_vencidos(self, agora: float) -> bool:
        if self._gpu_off and self._temp_off:
            return False
        if self._extra_fio is not None and self._extra_fio.is_alive():
            return False
        return agora - self._extra_em >= INTERVALO_EXTRA

    def _ler(self, agora: float) -> None:
        import psutil

        v = self._valores
        v["cpu"] = psutil.cpu_percent(interval=None)
        v["mem"] = psutil.virtual_memory().percent
        v["swap"] = psutil.swap_memory().percent
        rede = psutil.net_io_counters()
        if self._rede_antes is not None:
            t0, env0, rec0 = self._rede_antes
            passou = max(0.5, agora - t0)
            v["envio"] = (rede.bytes_sent - env0) / passou
            v["recebido"] = (rede.bytes_recv - rec0) / passou
            v["net"] = (v["envio"] + v["recebido"]) / (1024 * 1024)
        self._rede_antes = (agora, rede.bytes_sent, rede.bytes_recv)

    # ----- GPU e temperatura (fio à parte)
    def _ler_extras(self) -> None:
        if not self._gpu_off:
            gpu = _ler_gpu()
            with self._lock:
                self._valores["gpu"] = gpu
                if gpu < 0:
                    self._gpu_off = True  # nenhuma ferramenta de GPU: não tenta mais
        if not self._temp_off:
            tmp = _ler_temperatura()
            with self._lock:
                self._valores["tmp"] = tmp
                if tmp < 0:
                    self._temp_off = True


def _ler_gpu() -> float:
    # NVIDIA
    try:
        r = _rodar(["nvidia-smi", "--query-gpu=utilization.gpu", "--format=csv,noheader,nounits"], 2)
        if r.returncode == 0:
            vals = [float(v.strip()) for v in r.stdout.strip().split("\n") if v.strip()]
            if vals:
                return sum(vals) / len(vals)
    except Exception:
        pass
    if _OS == "Linux":
        # AMD
        try:
            r = _rodar(["rocm-smi", "--showuse", "--csv"], 2)
            if r.returncode == 0:
                for line in r.stdout.strip().split("\n"):
                    parts = line.split(",")
                    if len(parts) >= 2:
                        try:
                            return float(parts[1].strip().replace("%", ""))
                        except ValueError:
                            pass
        except Exception:
            pass
        # Intel — uma amostra rápida (sem prender 500 ms toda vez)
        try:
            r = _rodar(["intel_gpu_top", "-J", "-s", "100", "-n", "1"], 1)
            if r.returncode == 0 and "Render/3D" in r.stdout:
                m = re.search(r'"busy":\s*([\d.]+)', r.stdout)
                if m:
                    return float(m.group(1))
        except Exception:
            pass
    if _OS == "Darwin":
        try:
            r = _rodar(["sudo", "-n", "powermetrics", "-n", "1", "-i", "500", "--samplers", "gpu_power"], 2)
            if r.returncode == 0 and "GPU" in r.stdout:
                m = re.search(r'GPU\s+Active:\s+([\d.]+)%', r.stdout)
                if m:
                    return float(m.group(1))
        except Exception:
            pass
    return -1.0


def _ler_temperatura() -> float:
    import psutil

    try:
        temps = psutil.sensors_temperatures()
        for name in ("coretemp", "k10temp", "cpu_thermal", "acpitz", "cpu-thermal", "zenpower", "it8688"):
            if name in temps and temps[name]:
                return temps[name][0].current
        for entries in temps.values():
            if entries:
                return entries[0].current
    except Exception:
        pass
    if _OS == "Darwin":
        try:
            r = _rodar(["osx-cpu-temp"], 2)
            if r.returncode == 0:
                m = re.search(r"([\d.]+)", r.stdout)
                if m:
                    return float(m.group(1))
        except Exception:
            pass
        try:
            r = _rodar(["ioreg", "-l"], 3)
            if r.returncode == 0:
                valid = [float(t) / 1000.0 for t in re.findall(r'"temperature"\s*=\s*(\d+)', r.stdout)
                         if 10 < float(t) < 150000]
                if valid:
                    return min(valid)
        except Exception:
            pass
    if _OS == "Windows":
        try:
            r = _rodar(["powershell", "-NoProfile", "-Command",
                        "(Get-WmiObject MSAcpi_ThermalZoneTemperature -Namespace root/wmi).CurrentTemperature"], 3)
            if r.returncode == 0 and r.stdout.strip():
                raw = float(r.stdout.strip().split("\n")[0])
                return (raw / 10.0) - 273.15
        except Exception:
            pass
    return -1.0


_medidor: Medidor | None = None
_medidor_lock = threading.Lock()


def retrato() -> dict:
    """O retrato do medidor único (criado na primeira leitura, nunca ao importar)."""
    global _medidor
    with _medidor_lock:
        if _medidor is None:
            _medidor = Medidor()
    return _medidor.retrato()


# ---------------------------------------------------------------- o próprio Jarvis e a bateria
def cpu_do_jarvis(intervalo: float = 0.5) -> list[tuple[str, float]]:
    """[(programa, % do processador inteiro)] dos programas do Jarvis. Nos dois programas (padrão),
    este é o cérebro e o pai é a tela; num programa só, é o único. A porcentagem é do computador
    inteiro, como no Gerenciador de Tarefas do Windows (o psutil soma os núcleos: aqui divide)."""
    import psutil

    dois = bool(os.environ.get("JARVIS_PONTE_PORTA", "").strip())
    programas = [("cérebro" if dois else "Jarvis", psutil.Process())]
    if dois:
        try:
            pai = programas[0][1].parent()
            if pai is not None:
                programas.append(("tela", pai))
        except psutil.Error:
            pass
    for _, p in programas:
        try:
            p.cpu_percent(interval=None)  # a primeira chamada só marca o começo
        except psutil.Error:
            pass
    time.sleep(intervalo)
    nucleos = psutil.cpu_count() or 1
    resultado = []
    for nome, p in programas:
        try:
            resultado.append((nome, p.cpu_percent(interval=None) / nucleos))
        except psutil.Error:
            pass
    return resultado


def bateria() -> dict | None:
    """{'pct', 'na_tomada', 'minutos'} ou None quando não há bateria (PC de mesa) — o psutil
    devolve None nesse caso, e ler .percent dele quebrava."""
    import psutil

    try:
        b = psutil.sensors_battery()
    except Exception:
        return None
    if b is None:
        return None
    minutos = None
    if isinstance(b.secsleft, (int, float)) and b.secsleft > 0:
        minutos = int(b.secsleft // 60)
    return {"pct": float(b.percent), "na_tomada": bool(b.power_plugged), "minutos": minutos}
