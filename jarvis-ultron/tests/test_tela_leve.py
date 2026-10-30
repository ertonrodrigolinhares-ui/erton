"""Etapa 6 da reorganização: tela mais leve.

(a) medir antes: core/metricas.py e os itens "CPU do Jarvis", "CPU" e "Bateria" do autodiagnóstico.
"""

import os
import subprocess
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


# ---------------------------------------------------------------- (d) parar o que trabalha escondido
class _CofreVazio:
    def get(self, _chave):
        return None


class _JanelaDeTeste:
    """Uma MainWindow sem a chave de verdade (como no tests/test_ui_orbe.py)."""

    def __enter__(self):
        import tempfile

        import ui

        self._pasta = tempfile.TemporaryDirectory()
        self._trocas = [
            patch.dict(os.environ),
            patch.object(ui, "API_FILE", Path(self._pasta.name) / "api_keys.json"),
            patch.object(ui, "BASE_DIR", Path(self._pasta.name)),
            patch.object(ui, "get_secret_store", return_value=_CofreVazio()),
        ]
        for t in self._trocas:
            t.start()
        os.environ.pop("GEMINI_API_KEY", None)
        for nome in ("JARVIS_VISUAL", "JARVIS_CENA", "JARVIS_TELA"):
            os.environ.pop(nome, None)
        from PyQt6.QtWidgets import QApplication

        self.app = QApplication.instance() or QApplication([])
        self.win = ui.MainWindow("face.png")
        for nome in ("_overlay", "_name_overlay"):
            w = getattr(self.win, nome, None)
            if w is not None:
                w.hide()
        return self.win

    def __exit__(self, *_):
        self.win.close()
        self.win.deleteLater()
        self.app.processEvents()
        for t in reversed(self._trocas):
            t.stop()
        self._pasta.cleanup()


class NadaTrabalhaEscondidoTests(unittest.TestCase):
    def test_importar_o_ui_nao_cria_nenhum_fio(self):
        # antes, o ui.py abria ao importar um fio que lia o sistema a cada 1,5 s (o _SysMetrics)
        codigo = ("import os, threading; os.environ['QT_QPA_PLATFORM'] = 'offscreen'\n"
                  "antes = threading.active_count(); import ui; print(threading.active_count() - antes)")
        r = subprocess.run([sys.executable, "-c", codigo], cwd=str(RAIZ), capture_output=True, text=True, timeout=120)
        self.assertEqual(r.returncode, 0, r.stderr[-800:])
        self.assertEqual(r.stdout.strip(), "0", r.stderr[-800:])

    def test_a_tela_antiga_le_do_medidor_unico(self):
        import ui

        with patch.object(metricas, "retrato", return_value=dict(metricas.VAZIO, cpu=33.0)):
            self.assertEqual(ui._get_metrics()["cpu"], 33.0)

    def test_com_a_cena_na_frente_o_relogio_e_as_barras_da_tela_antiga_ficam_parados(self):
        import ui

        with _JanelaDeTeste() as win:
            cena = win._orbe.cena
            self.assertTrue(cena.ativa)
            win._clock_lbl.setText("parado")
            win._tick_clock()
            self.assertEqual(win._clock_lbl.text(), "parado")
            with patch.object(ui, "_get_metrics", return_value=dict(metricas.VAZIO)) as leitura:
                win._update_metrics()
            leitura.assert_not_called()

            cena.alternar()  # F2: a tela antiga volta a aparecer e volta a trabalhar
            win._tick_clock()
            self.assertNotEqual(win._clock_lbl.text(), "parado")
            with patch.object(ui, "_get_metrics", return_value=dict(metricas.VAZIO)) as leitura:
                win._update_metrics()
            leitura.assert_called_once()

    def test_a_stark_nao_le_o_sistema_enquanto_o_anel_cobre(self):
        import tempfile

        from PyQt6.QtWidgets import QApplication, QWidget

        import ui_stark

        self.app = QApplication.instance() or QApplication([])  # a referência segura o app vivo
        with patch.object(ui_stark.TelaStark, "_buscar_da_internet", lambda self: None):
            tela = ui_stark.TelaStark(QWidget(), lambda c: None, pasta_dados=Path(tempfile.mkdtemp()))
        tela.show()
        cena = NS(ativa=True, isHidden=lambda: False)
        tela.window()._orbe = NS(cena=cena)
        with patch.object(tela.sistema, "atualizar", return_value={}) as leitura:
            tela._a_cada_segundo()
            tela._girar_botoes()
            leitura.assert_not_called()
            cena.ativa = False  # F2
            tela._a_cada_segundo()
            leitura.assert_called_once()
        tela.close()
        tela.deleteLater()

    def test_a_stark_le_cpu_memoria_e_rede_do_medidor_unico(self):
        import ui_stark

        retrato = dict(metricas.VAZIO, cpu=21.0, mem=55.0, swap=2.0, envio=10.0, recebido=20.0)
        with patch.object(metricas, "retrato", return_value=retrato):
            d = ui_stark.Sistema().atualizar()
        self.assertEqual((d["cpu"], d["ram"], d["swap"], d["envio"], d["recebido"]), (21.0, 55.0, 2.0, 10.0, 20.0))
        self.assertIn("ligado", d)

    def test_o_anel_continua_pulsando_com_a_voz_mas_a_esfera_antiga_para(self):
        from PyQt6.QtWidgets import QApplication, QWidget

        import ui
        import ui_orbe

        self.app = QApplication.instance() or QApplication([])  # a referência segura o app vivo
        janela = QWidget()
        hud = ui.HudCanvas("face.png", parent=janela)
        hud._orbe = ui_orbe.Orbe()
        giro, pulsos = hud._rotation_y, len(hud._pulses)
        hud.nivel_voz, hud.nivel_voz_em = 0.9, time.time()
        for _ in range(5):
            hud._step()
        self.assertGreater(hud._nivel_suave, 0.3)        # o anel segue o volume da voz
        self.assertEqual(hud._rotation_y, giro)           # a esfera antiga não gira mais
        self.assertEqual(len(hud._pulses), pulsos)
        self.assertEqual(hud._blink_tick, 0)

        hud._orbe = None  # esfera clássica (JARVIS_VISUAL=classico): continua animando
        hud._step()
        self.assertNotEqual(hud._rotation_y, giro)
