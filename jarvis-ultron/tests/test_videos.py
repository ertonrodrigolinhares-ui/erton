import importlib.util
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from core import aprovacao
from core.aprovacao import fechar_fala, mais_um_pedaco, nova_fala


def _modulo():
    spec = importlib.util.spec_from_file_location("auto_videos", RAIZ / "automacoes" / "videos.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class JarvisFalso:
    """Imita o JarvisLive: conta as falas do Erton (o "ok" só vale numa fala nova)."""

    def __init__(self, fala=""):
        self._fala_n, self._fala_texto = 0, ""
        self.avisos, self.logs = [], []
        self.ui = NS(write_log=self.logs.append)
        if fala:
            self.falar(fala)

    def falar(self, texto):
        nova_fala(self, texto)

    def _falar_aviso(self, texto):
        self.avisos.append(texto)


def _esperar_video():
    for t in threading.enumerate():
        if t.name == "VideoVeo":
            t.join(5)


class OkAntesDoVideoTests(unittest.TestCase):
    def setUp(self):
        self.m = _modulo()
        self.pedido = {"description": "a triathlete crossing the finish line in Hawaii at sunset", "seconds": 8}

    def test_primeiro_mostra_o_preco_e_nao_faz_nada(self):
        with patch.object(self.m, "gerar") as gerar:
            r = self.m.executar(dict(self.pedido), JarvisFalso())
        self.assertIn("US$ 0.96", r)  # 8 s x US$ 0,12 (rápido)
        self.assertIn("R$", r)
        gerar.assert_not_called()

    def test_confirmar_sem_ok_do_usuario_nao_faz(self):
        jarvis = JarvisFalso("faz um vídeo de um triatleta no Havaí")
        with patch.object(self.m, "gerar") as gerar:
            self.m.executar(dict(self.pedido), jarvis)
            jarvis.falar("hmm, quanto fica mesmo?")
            r = self.m.executar(dict(self.pedido, confirm=True), jarvis)
            _esperar_video()
        self.assertIn("Not confirmed", r)
        gerar.assert_not_called()

    def test_recusa_que_comeca_com_ok_nao_vale(self):
        jarvis = JarvisFalso("faz um vídeo de um triatleta no Havaí")
        with patch.object(self.m, "gerar") as gerar:
            self.m.executar(dict(self.pedido), jarvis)
            for recusa in ("Ok, pode cancelar, tá caro", "ok, deixa pra depois", "sim, mas muito caro",
                           "ok, quanto fica em euro?", "ok, entendi", "ok, pode fazer amanhã",
                           "ok, pode fazer daqui a pouco", "ok pode fazer peraí", "sim, pode fazer na semana que vem"):
                jarvis.falar(recusa)
                r = self.m.executar(dict(self.pedido, confirm=True), jarvis)
                self.assertIn("Not confirmed", r, recusa)
            _esperar_video()
        gerar.assert_not_called()

    def test_resto_da_fala_que_vira_recusa_nao_faz_e_o_preco_continua_valendo(self):
        # Gemini ao vivo: a ferramenta chegou com só o "Ok," transcrito; o resto chega depois
        jarvis = JarvisFalso("faz um vídeo de um triatleta no Havaí")
        with patch.object(aprovacao, "SILENCIO", 0.2), \
                patch.object(self.m, "gerar", return_value=Path("/tmp/video.mp4")) as gerar, \
                patch.object(self.m, "_abrir"):
            self.m.executar(dict(self.pedido), jarvis)
            numero = nova_fala(jarvis, "Ok,", em_pedacos=True)
            r = self.m.executar(dict(self.pedido, confirm=True), jarvis)
            self.assertIn("background", r)
            mais_um_pedaco(jarvis, numero, "Ok, pode cancelar, tá caro")
            fechar_fala(jarvis, numero)
            _esperar_video()
            gerar.assert_not_called()
            self.assertIn("Não fiz o vídeo", jarvis.avisos[-1])
            # um "ok" claro numa fala nova ainda vale para o mesmo preço
            jarvis.falar("ok, pode fazer")
            self.assertIn("background", self.m.executar(dict(self.pedido, confirm=True), jarvis))
            _esperar_video()
        gerar.assert_called_once()

    def test_ok_dito_antes_do_preco_nao_vale(self):
        jarvis = JarvisFalso("ok, pode fazer")
        with patch.object(self.m, "gerar") as gerar:
            self.m.executar(dict(self.pedido), jarvis)  # o preço vem depois do "ok"
            r = self.m.executar(dict(self.pedido, confirm=True), jarvis)
            _esperar_video()
        self.assertIn("Not confirmed", r)
        gerar.assert_not_called()

    def test_confirmar_sem_ter_mostrado_o_preco_nao_faz(self):
        with patch.object(self.m, "gerar") as gerar:
            r = self.m.executar(dict(self.pedido, confirm=True), JarvisFalso("ok, pode fazer"))
            _esperar_video()
        self.assertIn("Not confirmed", r)
        gerar.assert_not_called()

    def test_ok_para_outro_video_nao_vale(self):
        jarvis = JarvisFalso("faz um vídeo de um triatleta no Havaí")
        with patch.object(self.m, "gerar") as gerar:
            self.m.executar(dict(self.pedido), jarvis)
            jarvis.falar("ok, pode fazer")
            r = self.m.executar(dict(self.pedido, seconds=4, confirm=True), jarvis)
            _esperar_video()
        self.assertIn("Not confirmed", r)
        gerar.assert_not_called()

    def test_com_ok_faz_em_segundo_plano_abre_e_avisa(self):
        jarvis = JarvisFalso("faz um vídeo de um triatleta no Havaí")
        with patch.object(self.m, "gerar", return_value=Path("/tmp/video.mp4")) as gerar, \
                patch.object(self.m, "_abrir") as abrir:
            self.m.executar(dict(self.pedido), jarvis)
            jarvis.falar("ok, pode fazer")
            r = self.m.executar(dict(self.pedido, confirm=True), jarvis)
            _esperar_video()
        self.assertIn("background", r)
        gerar.assert_called_once()
        abrir.assert_called_once_with(Path("/tmp/video.mp4"))
        self.assertIn("pronto", jarvis.avisos[0])
        # o mesmo ok não serve para um segundo vídeo
        with patch.object(self.m, "gerar") as gerar2:
            r2 = self.m.executar(dict(self.pedido, confirm=True), jarvis)
        self.assertIn("Not confirmed", r2)
        gerar2.assert_not_called()

    def test_pode_fazer_dito_junto_com_o_pedido_nao_vale(self):
        """O ok tem que vir numa fala nova, depois de o Erton ouvir o preço."""
        jarvis = JarvisFalso("faz um vídeo de um triatleta no Havaí, pode fazer")
        with patch.object(self.m, "gerar") as gerar:
            self.m.executar(dict(self.pedido), jarvis)
            r = self.m.executar(dict(self.pedido, confirm=True), jarvis)
            _esperar_video()
        self.assertIn("Not confirmed", r)
        gerar.assert_not_called()

    def test_modo_privado_nunca_manda_a_descricao_para_o_google(self):
        import os

        pedido = dict(self.pedido, description="client Fulano from company X receiving a certificate")
        with patch.dict(os.environ, {"JARVIS_CEREBRO": "gemma"}), patch.object(self.m, "gerar") as gerar:
            r1 = self.m.executar(dict(pedido), JarvisFalso())
            r2 = self.m.executar(dict(pedido, confirm=True), JarvisFalso("ok, pode fazer"))
            _esperar_video()
        self.assertIn("modo privado", r1)
        self.assertNotIn("US$", r1)
        self.assertIn("modo privado", r2)
        gerar.assert_not_called()

    def test_modo_privado_ligado_entre_o_preco_e_o_ok(self):
        jarvis = JarvisFalso("ok, pode fazer")
        with patch.object(self.m, "gerar") as gerar:
            self.m.executar(dict(self.pedido), JarvisFalso())
            with patch.object(self.m, "_modo_privado", side_effect=[False, True]):
                self.m.executar(dict(self.pedido, confirm=True), jarvis)
                _esperar_video()
        gerar.assert_not_called()
        self.assertIn("modo privado", jarvis.avisos[0])

    def test_marcada_como_ia_na_nuvem(self):
        from core.automacoes import carregar_ferramentas

        self.assertTrue(carregar_ferramentas(RAIZ / "automacoes").ferramentas["generate_video"].usa_ia_nuvem)

    def test_erro_do_google_vira_aviso_em_portugues(self):
        jarvis = JarvisFalso("faz um vídeo de um triatleta no Havaí")
        with patch.object(self.m, "gerar", side_effect=RuntimeError("403 billing account not enabled")):
            self.m.executar(dict(self.pedido), jarvis)
            jarvis.falar("ok, pode fazer")
            self.m.executar(dict(self.pedido, confirm=True), jarvis)
            _esperar_video()
        self.assertIn("faturamento", jarvis.avisos[0])


def _pedaco(texto):
    """Um pedaço da transcrição da fala do Erton (Gemini ao vivo)."""
    return NS(server_content=NS(input_transcription=NS(text=texto), output_transcription=None, turn_complete=False),
              tool_call=None)


def _video(confirm):
    fc = NS(name="generate_video", id="v", args={"description": "my workout", "seconds": 8, "confirm": confirm})
    return NS(server_content=None, tool_call=NS(function_calls=[fc]))


def _fim_do_turno():
    return NS(server_content=NS(input_transcription=None, output_transcription=None, turn_complete=True),
              tool_call=None)


class OkNoGeminiAoVivoTests(unittest.TestCase):
    """No Gemini ao vivo a transcrição chega em pedaços e atrasada: o "pode fazer" dito junto com o
    pedido não pode aprovar o vídeo na segunda chamada do mesmo turno."""

    def setUp(self):
        from core import aprovacao

        self.m = _modulo()
        self.respostas, self.avisos = [], []
        silencio = patch.object(aprovacao, "SILENCIO", 0.4)  # o padrão (2 s) só deixaria o teste lento
        silencio.start()
        self.addCleanup(silencio.stop)

    def _rodar(self, mensagens):
        """mensagens: o que o Gemini manda, na ordem; um número é uma pausa (segundos) na conexão."""
        import asyncio

        import main

        jarvis = object.__new__(main.JarvisLive)
        jarvis.ui = NS(muted=False, write_log=lambda t: None, clear_subtitle=lambda: None,
                       show_subtitle=lambda t: None)
        jarvis._portao = NS(estender=lambda: None, estado="ouvindo")
        jarvis._turn_done_event = None
        jarvis._shutdown_requested = threading.Event()
        jarvis._fala_n, jarvis._fala_texto = 0, ""
        for nome in ("_checar_pedido_de_modo", "_pedido_de_cerebro", "_falar_com_voz_externa"):
            setattr(jarvis, nome, lambda t: None)
        jarvis._is_explicit_self_quit_transcript = lambda t: False
        jarvis.anunciar = lambda texto, *a, **k: self.avisos.append(texto) or "falado"
        m, respostas = self.m, self.respostas

        async def ferramentas(chamadas):
            respostas.extend(m.executar(dict(fc.args), jarvis) for fc in chamadas)
            return []

        jarvis._execute_tool_batch = ferramentas

        class Sessao:
            async def receive(self):
                for mensagem in mensagens:
                    if isinstance(mensagem, (int, float)):
                        await asyncio.sleep(mensagem)
                        continue
                    yield mensagem
                jarvis._shutdown_requested.set()

            async def send_tool_response(self, function_responses):
                pass

        jarvis.session = Sessao()
        with patch.object(self.m, "gerar", return_value=Path("/tmp/video.mp4")) as gerar, \
                patch.object(self.m, "_abrir"):
            asyncio.run(jarvis._receive_audio())
            _esperar_video()
        return gerar

    def test_pode_fazer_que_chega_depois_do_preco_no_mesmo_turno_nao_vale(self):
        gerar = self._rodar([_pedaco("Jarvis, faz um vídeo de 8 segundos do meu treino"), _video(False),
                             _pedaco(", pode fazer"), _video(True), _fim_do_turno()])
        gerar.assert_not_called()
        self.assertIn("Not confirmed", self.respostas[1])

    def test_pedido_inteiro_transcrito_atrasado_nao_vale(self):
        # o preço saiu antes de chegar qualquer pedaço da fala; o pedido (que soa como um "ok")
        # chega depois, no mesmo turno do modelo: não é uma fala nova depois do preço
        gerar = self._rodar([_video(False), _pedaco("Ok Jarvis, pode fazer um vídeo do meu treino"),
                             _video(True), _fim_do_turno()])
        gerar.assert_not_called()
        self.assertIn("Not confirmed", self.respostas[1])

    def test_ok_que_vira_recusa_quando_o_resto_da_fala_chega_nao_faz(self):
        # "Ok, pode cancelar, tá caro": a ferramenta chega quando só o "Ok," foi transcrito; o resto
        # chega depois. O vídeo pago não pode começar com o pedaço "Ok,".
        gerar = self._rodar([_pedaco("Jarvis, faz um vídeo de 8 segundos do meu treino"), _video(False),
                             _fim_do_turno(), _pedaco("Ok,"), _video(True), 0.2,
                             _pedaco("pode cancelar, tá caro"), _fim_do_turno()])
        gerar.assert_not_called()
        self.assertTrue(any("Não fiz o vídeo" in a for a in self.avisos), self.avisos)

    def test_resto_da_fala_que_chega_depois_do_fim_do_turno_tambem_conta(self):
        # o resto da fala chega só depois do fim do turno do modelo (vira uma fala nova): não faz
        gerar = self._rodar([_pedaco("Jarvis, faz um vídeo de 8 segundos do meu treino"), _video(False),
                             _fim_do_turno(), _pedaco("Ok,"), _video(True), _fim_do_turno(), 0.2,
                             _pedaco("pode cancelar, tá caro"), _fim_do_turno()])
        gerar.assert_not_called()

    def test_ok_numa_fala_nova_depois_do_preco_vale(self):
        gerar = self._rodar([_pedaco("Jarvis, faz um vídeo de 8 segundos do meu treino"), _video(False),
                             _fim_do_turno(), _pedaco("ok, pode fazer"), _video(True), _fim_do_turno()])
        gerar.assert_called_once()
        self.assertIn("background", self.respostas[1])


class Operacao:
    def __init__(self, voltas, video):
        self.voltas, self.video = voltas, video

    @property
    def done(self):
        return self.voltas <= 0

    @property
    def result(self):
        return NS(generated_videos=[NS(video=self.video)])

    error = None


class VideoFalso:
    uri = None
    video_bytes = b"mp4"

    def save(self, caminho):
        Path(caminho).write_bytes(self.video_bytes)


class ClienteVeo:
    def __init__(self, nomes, inexistentes=()):
        self.nomes, self.inexistentes, self.pedidos = nomes, set(inexistentes), []
        self.models = NS(list=lambda config=None: [NS(name=f"models/{n}") for n in self.nomes],
                         generate_videos=self._gerar)
        self.operations = NS(get=self._andar)

    def _gerar(self, model, source, config):
        self.pedidos.append((model, config))
        if model in self.inexistentes:
            raise Exception(f"404 NOT_FOUND {model}")
        return Operacao(2, VideoFalso())

    def _andar(self, operacao):
        operacao.voltas -= 1
        return operacao


class GerarTests(unittest.TestCase):
    def setUp(self):
        self.m = _modulo()
        self.casa = tempfile.mkdtemp()

    def test_escolhe_o_veo_rapido_mais_novo_e_salva(self):
        cliente = ClienteVeo(["veo-3.0-fast-generate-001", "veo-3.1-fast-generate-preview", "veo-3.1-generate-preview"])
        with patch.object(self.m, "pasta_videos", lambda: Path(self.casa)):
            arquivo = self.m.gerar("a runner", 8, "rapido", True, cliente=cliente, dormir=lambda s: None)
        self.assertTrue(arquivo.exists())
        modelo, config = cliente.pedidos[0]
        self.assertEqual(modelo, "veo-3.1-fast-generate-preview")
        self.assertEqual(config.aspect_ratio, "9:16")
        self.assertEqual(config.duration_seconds, 8)

    def test_modelo_que_nao_existe_tenta_o_proximo(self):
        cliente = ClienteVeo(["veo-3.1-generate-preview", "veo-3.1-generate-001"], inexistentes={"veo-3.1-generate-preview"})
        with patch.object(self.m, "pasta_videos", lambda: Path(self.casa)):
            arquivo = self.m.gerar("a runner", 4, "maximo", False, cliente=cliente, dormir=lambda s: None)
        self.assertTrue(arquivo.exists())
        self.assertEqual([p[0] for p in cliente.pedidos], ["veo-3.1-generate-preview", "veo-3.1-generate-001"])

    def test_carrega_como_ferramenta_do_jarvis(self):
        from core.automacoes import carregar_ferramentas

        carga = carregar_ferramentas(RAIZ / "automacoes")
        self.assertIn("generate_video", carga.ferramentas)
        self.assertNotIn("videos.py", carga.na_tela)


if __name__ == "__main__":
    unittest.main()
