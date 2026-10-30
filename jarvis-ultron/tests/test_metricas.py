"""Etapa 6 da reorganização, item (a): medir antes de aliviar a tela.

core/metricas.py é a fonte única de CPU/memória da tela (antiga, Cena e Stark) e do autodiagnóstico.
Promessas: nada roda ao importar; a leitura leve é compartilhada (uma por intervalo); programas de fora
(nvidia-smi, powershell) só rodam se existem no PC, sem janela preta; e o autodiagnóstico diz quanto o
Jarvis gasta e lida com o PC de mesa sem bateria (sensors_battery() devolve None)."""

import os
import subprocess
import sys
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from core import autodiagnostico as ad  # noqa: E402
from core import metricas  # noqa: E402


class ImportarNaoTrabalhaTests(unittest.TestCase):
    def test_importar_metricas_nao_cria_fio_nem_le_o_sistema(self):
        codigo = ("import threading, sys; sys.path.insert(0, %r); antes = threading.active_count(); "
                  "import core.metricas; print(threading.active_count() - antes)" % str(RAIZ))
        saida = subprocess.run([sys.executable, "-I", "-c", codigo], capture_output=True, text=True, timeout=60)
        self.assertEqual(saida.returncode, 0, saida.stderr)
        self.assertEqual(saida.stdout.strip(), "0")


class LeituraLeveTests(unittest.TestCase):
    def setUp(self):
        self.leitor = metricas._Leitor()
        self.leitor._gpu_off = self.leitor._tmp_off = True  # só a leitura leve nestes testes

    def test_retrato_tem_as_chaves_da_tela_e_valores_numericos(self):
        r = self.leitor.ler()
        self.assertEqual(set(r), {"cpu", "mem", "disco", "net", "gpu", "tmp"})
        self.assertTrue(0 <= r["cpu"] <= 100 and 0 < r["mem"] <= 100 and 0 <= r["disco"] <= 100)
        self.assertEqual((r["gpu"], r["tmp"]), (metricas.SEM_LEITURA, metricas.SEM_LEITURA))

    def test_duas_leituras_seguidas_sao_a_mesma_e_nao_releem_o_sistema(self):
        primeira = self.leitor.ler()
        with patch("psutil.cpu_percent", side_effect=AssertionError("releu o sistema")):
            segunda = self.leitor.ler()
        self.assertEqual(primeira, segunda)

    def test_depois_do_intervalo_le_de_novo(self):
        self.leitor.ler()
        self.leitor._lido_em -= metricas.INTERVALO + 1
        with patch("psutil.cpu_percent", return_value=42.0):
            self.assertEqual(self.leitor.ler()["cpu"], 42.0)

    def test_falha_na_leitura_nao_derruba_e_mantem_o_retrato_anterior(self):
        antes = self.leitor.ler()
        self.leitor._lido_em -= metricas.INTERVALO + 1
        with patch("psutil.cpu_percent", side_effect=RuntimeError("psutil quebrou")):
            depois = self.leitor.ler()
        self.assertEqual(antes, depois)


class LeituraPesadaTests(unittest.TestCase):
    def test_sem_ferramenta_de_gpu_nenhum_programa_de_fora_roda(self):
        with patch.object(metricas.shutil, "which", return_value=None), \
                patch.object(metricas.subprocess, "run", side_effect=AssertionError("abriu um programa")):
            self.assertEqual(metricas._ler_gpu(), metricas.SEM_LEITURA)

    def test_nvidia_smi_e_lido_sem_janela_preta(self):
        chamadas = []

        def rodar(cmd, **kw):
            chamadas.append((cmd, kw))
            return SimpleNamespace(returncode=0, stdout="37\n41\n")

        with patch.object(metricas.shutil, "which", side_effect=lambda n: "/x/" + n if n == "nvidia-smi" else None), \
                patch.object(metricas.subprocess, "run", side_effect=rodar), \
                patch.object(metricas, "_SEM_JANELA", {"creationflags": 0x08000000}):
            self.assertEqual(metricas._ler_gpu(), 39.0)
        self.assertEqual(chamadas[0][0][0], "nvidia-smi")
        self.assertTrue(chamadas[0][1]["capture_output"])
        self.assertEqual(chamadas[0][1]["creationflags"], 0x08000000)  # CREATE_NO_WINDOW do Windows

    def test_no_windows_a_leitura_sem_janela_esta_ligada(self):
        self.assertEqual(bool(metricas._SEM_JANELA), os.name == "nt")
        if os.name == "nt":
            self.assertEqual(metricas._SEM_JANELA["creationflags"], subprocess.CREATE_NO_WINDOW)

    def test_pc_sem_gpu_nem_sensor_para_de_tentar(self):
        leitor = metricas._Leitor()
        with patch.object(metricas, "_ler_gpu", return_value=metricas.SEM_LEITURA) as gpu, \
                patch.object(metricas, "_ler_temperatura", return_value=metricas.SEM_LEITURA) as tmp:
            leitor.ler()
            fio = next((f for f in threading.enumerate() if f.name == "MetricasPesadas"), None)
            if fio is not None:
                fio.join(5)
            self.assertTrue(leitor._gpu_off and leitor._tmp_off)
            leitor._pesado_em -= metricas.INTERVALO_PESADO + 1
            leitor.ler()  # agora não abre fio nenhum
            self.assertEqual((gpu.call_count, tmp.call_count), (1, 1))
        self.assertNotIn("MetricasPesadas", [f.name for f in threading.enumerate()])

    def test_programa_de_fora_que_falha_vira_vazio(self):
        with patch.object(metricas.subprocess, "run", side_effect=OSError("não existe")):
            self.assertEqual(metricas._rodar(["nada"]), "")
        with patch.object(metricas.subprocess, "run", return_value=SimpleNamespace(returncode=1, stdout="erro")):
            self.assertEqual(metricas._rodar(["nada"]), "")


class AmostraCpuTests(unittest.TestCase):
    def test_mede_o_pc_e_o_proprio_programa_numa_janela_so(self):
        pc, por_programa, memoria = metricas.amostra_cpu([os.getpid(), 2 ** 22 + 12345], segundos=0.05)
        self.assertTrue(0 <= pc <= 100)
        self.assertEqual(set(por_programa), {os.getpid()})  # o pid inexistente fica de fora
        self.assertGreater(memoria[os.getpid()], 1024 * 1024)

    def test_bateria_ausente_e_none(self):
        with patch("psutil.sensors_battery", return_value=None, create=True):
            self.assertIsNone(metricas.bateria())
        with patch("psutil.sensors_battery", return_value=SimpleNamespace(percent=64, power_plugged=False), create=True):
            self.assertEqual(metricas.bateria(), (64.0, False))


class AutodiagnosticoTests(unittest.TestCase):
    def test_pc_de_mesa_sem_bateria_e_ok(self):
        with patch.object(metricas, "bateria", return_value=None):
            item = ad.verificar_bateria()
        self.assertEqual((item.nome, item.estado), ("Bateria", "ok"))
        self.assertIn("sem bateria", item.detalhe)

    def test_bateria_acabando_fora_da_tomada_e_defeito(self):
        with patch.object(metricas, "bateria", return_value=(8.0, False)):
            self.assertEqual(ad.verificar_bateria().estado, "defeito")
        with patch.object(metricas, "bateria", return_value=(20.0, False)):
            self.assertEqual(ad.verificar_bateria().estado, "atencao")
        with patch.object(metricas, "bateria", return_value=(8.0, True)):
            self.assertEqual(ad.verificar_bateria().estado, "ok")

    def test_cpu_do_jarvis_conta_a_tela_e_o_cerebro(self):
        with patch.dict(os.environ, {"JARVIS_PROCESSO": "cerebro", "JARVIS_PID_TELA": "4242"}), \
                patch.object(metricas, "amostra_cpu",
                             return_value=(31.0, {4242: 2.4, os.getpid(): 1.2},
                                           {4242: 300 * 1024 * 1024, os.getpid(): 410 * 1024 * 1024})):
            itens = ad.verificar_processador()
        self.assertEqual([i.nome for i in itens], ["CPU", "CPU do Jarvis"])
        self.assertEqual(itens[0].estado, "ok")
        self.assertIn("31%", itens[0].detalhe)
        self.assertEqual(itens[1].estado, "ok")
        self.assertIn("tela 2% (300 MB de memória)", itens[1].detalhe)
        self.assertIn("cérebro 1% (410 MB de memória)", itens[1].detalhe)

    def test_um_programa_so_quando_nao_ha_ponte(self):
        with patch.dict(os.environ, {"JARVIS_PROCESSO": "", "JARVIS_PID_TELA": ""}):
            self.assertEqual(ad.programas_do_jarvis(), {"Jarvis": os.getpid()})

    def test_jarvis_pesado_e_pc_cheio_viram_atencao(self):
        with patch.dict(os.environ, {"JARVIS_PROCESSO": "", "JARVIS_PID_TELA": ""}), \
                patch.object(metricas, "amostra_cpu", return_value=(88.0, {os.getpid(): 45.0}, {os.getpid(): 0})):
            cpu, jarvis = ad.verificar_processador()
        self.assertEqual((cpu.estado, jarvis.estado), ("atencao", "atencao"))
        self.assertIn("qualidade gráfica baixa", jarvis.dica)

    def test_tela_que_sumiu_nao_quebra_a_medicao(self):
        with patch.dict(os.environ, {"JARVIS_PROCESSO": "cerebro", "JARVIS_PID_TELA": "4242"}), \
                patch.object(metricas, "amostra_cpu", return_value=(10.0, {}, {})):
            cpu, jarvis = ad.verificar_processador()
        self.assertEqual(jarvis.estado, "atencao")
        self.assertIn("não consegui medir", jarvis.detalhe)

    def test_diagnostico_completo_traz_os_itens_novos(self):
        with patch.object(ad, "verificar_internet", return_value=ad.Item("Internet", "ok", "x")), \
                patch.object(ad, "verificar_gemini", return_value=ad.Item("Chave do Gemini", "ok", "x")), \
                patch.object(ad, "verificar_groq", return_value=ad.Item("Reserva Groq", "ok", "x")), \
                patch.object(ad, "verificar_hermes", return_value=ad.Item("Hermes (agentes)", "ok", "x")), \
                patch.object(ad, "verificar_modelos", return_value=ad.Item("Modelos do Gemini", "ok", "x")), \
                patch.object(metricas, "amostra_cpu", return_value=(10.0, {os.getpid(): 1.0}, {os.getpid(): 0})), \
                patch.object(metricas, "bateria", return_value=None):
            nomes = [i.nome for i in ad.diagnosticar(None)]
        i = nomes.index("Computador")
        self.assertEqual(nomes[i:i + 4], ["Computador", "CPU", "CPU do Jarvis", "Bateria"])


class PonteTests(unittest.TestCase):
    def test_a_tela_passa_o_proprio_pid_ao_cerebro(self):
        from core import ponte

        aberto = {}

        class Processo:
            pid = 1

        def popen(comando, cwd, env):
            aberto.update(env)
            return Processo()

        p = ponte.PonteTela.__new__(ponte.PonteTela)
        p._comando, p._pasta, p._processo, p._ouvinte = ["x"], RAIZ, None, None
        with patch.object(ponte.subprocess, "Popen", side_effect=popen), \
                patch.object(ponte.threading.Thread, "start", lambda self: None):
            p.iniciar()
        self.assertEqual(aberto.get("JARVIS_PID_TELA"), str(os.getpid()))
        self.assertEqual(aberto.get("JARVIS_PROCESSO"), "cerebro")
        p._ouvinte.close()


if __name__ == "__main__":
    unittest.main()
