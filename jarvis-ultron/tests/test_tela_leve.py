"""Etapa 6 da reorganização: tela mais leve.

(a) medir antes: core/metricas.py e os itens "CPU do Jarvis", "CPU" e "Bateria" do autodiagnóstico.
"""

import os
import sys
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from core import autodiagnostico as ad
from core import metricas


class _ProcessoFalso:
    def __init__(self, cpu: float, pai=None):
        self._cpu, self._pai, self.chamadas = cpu, pai, 0

    def cpu_percent(self, interval=None):
        self.chamadas += 1
        return 0.0 if self.chamadas == 1 else self._cpu  # a 1ª chamada só marca o começo

    def parent(self):
        return self._pai


def _psutil_falso(**extra):
    base = dict(
        cpu_percent=lambda interval=None: 12.0,
        virtual_memory=lambda: NS(percent=40.0),
        swap_memory=lambda: NS(percent=3.0),
        net_io_counters=lambda: NS(bytes_sent=1000, bytes_recv=2000),
        sensors_battery=lambda: None,
        cpu_count=lambda: 4,
        Error=Exception,
    )
    base.update(extra)
    return NS(**base)


class MedidorTests(unittest.TestCase):
    def test_importar_o_medidor_nao_le_nada_nem_abre_fio(self):
        fios = threading.active_count()
        with patch.dict(sys.modules, {"psutil": None}):  # sem psutil: só a leitura precisaria dele
            m = metricas.Medidor()
        self.assertEqual(m._valores, metricas.VAZIO)
        self.assertEqual(threading.active_count(), fios)

    def test_retrato_le_cpu_memoria_e_rede_no_maximo_uma_vez_por_segundo(self):
        ps = _psutil_falso()
        m = metricas.Medidor()
        m._gpu_off = m._temp_off = True  # sem o fio dos extras neste teste
        relogio = iter([10.0, 10.3, 11.5])
        with patch.dict(sys.modules, {"psutil": ps}), patch.object(metricas, "time", NS(time=lambda: next(relogio))):
            r1 = m.retrato()
            r2 = m.retrato()  # 0,3 s depois: a mesma leitura
            ps.net_io_counters = lambda: NS(bytes_sent=1000 + 1024 * 1024, bytes_recv=2000)
            r3 = m.retrato()  # 1,5 s depois: lê de novo e calcula a rede
        self.assertEqual((r1["cpu"], r1["mem"], r1["swap"]), (12.0, 40.0, 3.0))
        self.assertEqual(r2, r1)
        self.assertAlmostEqual(r3["net"], 1 / 1.5, places=3)
        self.assertAlmostEqual(r3["envio"], 1024 * 1024 / 1.5, places=1)
        self.assertEqual((r3["gpu"], r3["tmp"]), (-1.0, -1.0))

    def test_gpu_e_temperatura_vao_num_fio_a_parte_e_param_quando_nao_ha_ferramenta(self):
        m = metricas.Medidor()
        fios = []
        with patch.dict(sys.modules, {"psutil": _psutil_falso()}), \
                patch.object(metricas, "_ler_gpu", return_value=-1.0) as gpu, \
                patch.object(metricas, "_ler_temperatura", return_value=-1.0) as tmp, \
                patch.object(metricas.threading, "Thread", side_effect=lambda **kw: fios.append(kw) or NS(start=lambda: kw["target"](), is_alive=lambda: False)):
            m.retrato()
            m.retrato()
        self.assertEqual(len(fios), 1)  # uma leitura dos extras, e nunca de novo: não há ferramenta
        self.assertTrue(fios[0]["daemon"])
        gpu.assert_called_once()
        tmp.assert_called_once()
        self.assertTrue(m._gpu_off and m._temp_off)

    def test_programas_externos_nao_abrem_janela_preta_no_windows(self):
        chamadas = []

        def run(cmd, **kw):
            chamadas.append(kw)
            return NS(returncode=1, stdout="")

        with patch.object(metricas, "_OS", "Windows"), patch.object(metricas.subprocess, "run", run), \
                patch.object(metricas.subprocess, "CREATE_NO_WINDOW", 0x08000000, create=True), \
                patch.dict(sys.modules, {"psutil": _psutil_falso(sensors_temperatures=lambda: {})}):
            metricas._ler_gpu()
            metricas._ler_temperatura()
        self.assertGreaterEqual(len(chamadas), 2)
        for kw in chamadas:
            self.assertEqual(kw.get("creationflags"), 0x08000000)

    def test_retrato_global_cria_o_medidor_so_na_primeira_leitura(self):
        with patch.object(metricas, "_medidor", None), patch.dict(sys.modules, {"psutil": _psutil_falso()}):
            self.assertIsNone(metricas._medidor)
            r = metricas.retrato()
            self.assertIsNotNone(metricas._medidor)
        self.assertEqual(r["cpu"], 12.0)


class CpuDoJarvisEBateriaTests(unittest.TestCase):
    def test_nos_dois_programas_mede_o_cerebro_e_a_tela(self):
        tela = _ProcessoFalso(80.0)
        cerebro = _ProcessoFalso(40.0, pai=tela)
        ps = _psutil_falso(Process=lambda: cerebro)
        with patch.dict(sys.modules, {"psutil": ps}), patch.dict(os.environ, {"JARVIS_PONTE_PORTA": "5000"}), \
                patch.object(metricas, "time", NS(time=time.time, sleep=lambda s: None)):
            partes = metricas.cpu_do_jarvis()
        # o psutil soma os núcleos (4 aqui): a porcentagem é do computador inteiro
        self.assertEqual(partes, [("cérebro", 10.0), ("tela", 20.0)])

    def test_num_programa_so_mede_so_ele(self):
        ps = _psutil_falso(Process=lambda: _ProcessoFalso(8.0, pai=_ProcessoFalso(99.0)))
        with patch.dict(sys.modules, {"psutil": ps}), patch.dict(os.environ, {"JARVIS_PONTE_PORTA": ""}), \
                patch.object(metricas, "time", NS(time=time.time, sleep=lambda s: None)):
            partes = metricas.cpu_do_jarvis()
        self.assertEqual(partes, [("Jarvis", 2.0)])  # o pai (o .bat ou o Explorer) não é o Jarvis

    def test_bateria_none_e_pc_de_mesa(self):
        with patch.dict(sys.modules, {"psutil": _psutil_falso()}):
            self.assertIsNone(metricas.bateria())
            item = ad.verificar_bateria()
        self.assertEqual(item.estado, "ok")
        self.assertIn("sem bateria", item.detalhe)

    def test_bateria_acabando_fora_da_tomada_avisa(self):
        ps = _psutil_falso(sensors_battery=lambda: NS(percent=12, power_plugged=False, secsleft=600))
        with patch.dict(sys.modules, {"psutil": ps}):
            item = ad.verificar_bateria()
        self.assertEqual(item.estado, "defeito")
        self.assertIn("12%", item.detalhe)
        self.assertIn("10 min", item.detalhe)
        self.assertIn("carregador", item.dica)


class AutodiagnosticoTests(unittest.TestCase):
    def test_cpu_do_jarvis_junta_tela_e_cerebro_e_avisa_quando_pesa(self):
        with patch.object(metricas, "cpu_do_jarvis", return_value=[("cérebro", 3.0), ("tela", 4.0)]):
            leve = ad.verificar_cpu_jarvis()
        with patch.object(metricas, "cpu_do_jarvis", return_value=[("cérebro", 10.0), ("tela", 45.0)]):
            pesado = ad.verificar_cpu_jarvis()
        with patch.object(metricas, "cpu_do_jarvis", return_value=[]):
            vazio = ad.verificar_cpu_jarvis()
        self.assertEqual(leve.estado, "ok")
        self.assertEqual(leve.detalhe, "7% (cérebro 3% + tela 4%) do processador")
        self.assertEqual(pesado.estado, "defeito")
        self.assertIn("qualidade gráfica baixa", pesado.dica)
        self.assertEqual(vazio.estado, "atencao")

    def test_cpu_do_pc(self):
        with patch.dict(sys.modules, {"psutil": _psutil_falso(cpu_percent=lambda interval=None: 95.0)}):
            self.assertEqual(ad.verificar_cpu().estado, "defeito")
        with patch.dict(sys.modules, {"psutil": _psutil_falso(cpu_percent=lambda interval=None: 20.0)}):
            item = ad.verificar_cpu()
        self.assertEqual((item.estado, item.detalhe), ("ok", "20% em uso"))

    def test_diagnostico_tem_os_tres_itens_novos_e_funciona_sem_bateria(self):
        ok = lambda nome: (lambda: ad.Item(nome, "ok", "x"))  # noqa: E731
        ps = _psutil_falso(Process=lambda: _ProcessoFalso(4.0), disk_usage=lambda _: NS(percent=50.0))
        with patch.dict(sys.modules, {"psutil": ps}), patch.object(metricas, "time", NS(time=time.time, sleep=lambda s: None)), \
                patch.dict(os.environ, {"JARVIS_PONTE_PORTA": ""}), \
                patch.object(ad, "verificar_internet", ok("Internet")), \
                patch.object(ad, "verificar_gemini", ok("Chave do Gemini")), \
                patch.object(ad, "verificar_modelos", ok("Modelos do Gemini")), \
                patch.object(ad, "verificar_groq", ok("Reserva Groq")), \
                patch.object(ad, "verificar_hermes", ok("Hermes (agentes)")), \
                patch.object(ad, "verificar_audio", lambda: []), \
                patch.object(ad, "verificar_navegador", ok("Navegador automático")), \
                patch.object(ad, "verificar_automacoes", ok("Automações")):
            itens = ad.diagnosticar(None)
        por_nome = {i.nome: i for i in itens}
        self.assertEqual([i.nome for i in itens][5:9], ["Computador", "CPU do Jarvis", "CPU", "Bateria"])
        self.assertEqual(por_nome["CPU do Jarvis"].estado, "ok")
        self.assertEqual(por_nome["CPU"].estado, "ok")
        self.assertEqual(por_nome["Bateria"].detalhe, "sem bateria (computador de mesa)")
        self.assertIn("CPU do Jarvis: Jarvis 1% do processador", ad.relatorio(itens))


if __name__ == "__main__":
    unittest.main()
