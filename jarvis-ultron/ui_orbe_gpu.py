"""Anel do Jarvis Ultron desenhado pela placa de vídeo (OpenGL) — Jarvis Ultron.

O desenho normal (ui_orbe.Orbe) calcula cada fio no Python e desenha linha por linha: bonito, mas
pesado. Aqui o mesmo anel vira um pequeno programa que roda na placa de vídeo e calcula todos os
pontos da tela de uma vez — inclusive numa placa comum, como a Intel de notebook. Resultado:
60 quadros por segundo, os 18 fios completos com um brilho suave a mais, e quase nada de processador.

As contas (tamanho, agitação com a voz, brilho, cores do Ultron) são as mesmas do desenho normal
(Orbe.estado_quadro e a função cor), então os dois ficam iguais. O texto ("OUVINDO") continua sendo
desenhado por cima, do jeito normal.

Proteções (a tela nunca pode ficar preta nem fechar por causa disto):
  - antes de pôr a camada na janela, liga o OpenGL num teste: se não ligar, ou se for OpenGL feito
    pelo processador (sem driver de vídeo, área de trabalho remota, máquina virtual: llvmpipe e
    parecidos), usa o desenho normal nesta abertura (na próxima tenta de novo);
  - placa de vídeo sem OpenGL 2.0, programa que não compila, qualquer erro ao desenhar, ou a camada
    na tela e a placa sem desenhar nada por alguns segundos -> volta sozinho para o desenho normal;
  - se o Jarvis fechar sozinho na hora de ligar a placa de vídeo (driver com defeito), na próxima
    abertura ele percebe e não tenta mais (arquivo ~/.jarvis/orbe_gpu_falhou; apague para tentar de novo).
    Outro Jarvis abrindo ao mesmo tempo (dois cliques no iniciador) não conta como queda;
  - JARVIS_ORBE_GPU=0 no .env desliga; JARVIS_ORBE_GPU=forcar tenta sempre (até com OpenGL por software).
"""

from __future__ import annotations

import math
import os
import time
from pathlib import Path

PASTA = Path.home() / ".jarvis"
TESTANDO = PASTA / "orbe_gpu_testando"   # existe só enquanto a placa de vídeo é ligada pela 1ª vez
FALHOU = PASTA / "orbe_gpu_falhou"       # a placa de vídeo deu problema: usar o desenho normal

MAX_FIOS = 18
FAISCAS = 14

# OpenGL feito pelo processador (Mesa llvmpipe/softpipe, o opengl32sw.dll que vem com o Qt, SwiftShader,
# o OpenGL 1.1 do Windows sem driver): o anel rodaria a 60 quadros no processador e travaria o resto.
SOFTWARE = ("llvmpipe", "softpipe", "swiftshader", "software", "gdi generic", "basic render")
LIGANDO_MAX_S = 120   # marca de outro Jarvis vivo e mais nova que isso = ele está abrindo agora
VIGIA_MS = 2000       # de quanto em quanto tempo confere se a placa de vídeo já desenhou
VIGIA_VEZES = 3       # vezes seguidas com a camada na tela e nada desenhado = a placa não desenha

VERTICES = """
attribute vec2 pos;
void main() { gl_Position = vec4(pos, 0.0, 1.0); }
"""

# GLSL 1.10: roda em qualquer placa com OpenGL 2.0 (praticamente todas desde 2006).
FRAGMENTOS = """
#ifdef GL_ES
precision highp float;
#endif
uniform vec2 u_res;      // tamanho em pixels da placa
uniform vec2 u_c;        // centro do anel (pixels, origem no alto à esquerda)
uniform float u_R;       // raio do anel (pixels)
uniform float u_dpr;     // pixels por ponto (telas com zoom)
uniform int u_n;         // quantos fios
uniform vec4 u_fio[18];  // raio, achatamento, giro, largura
uniform vec4 u_k[18];    // as 3 ondas do fio (k) + pulso do brilho
uniform vec3 u_a[18];    // amplitude das 3 ondas (já com a agitação da voz)
uniform vec3 u_p[18];    // fase das 3 ondas (já com o tempo)
uniform vec2 u_fx[14];   // faíscas (pixels)
uniform float u_brilho;
uniform float u_largo;   // 1 = camada larga de brilho (qualidade alta)
uniform float u_bloom;   // brilho suave em volta dos fios
uniform vec3 u_ciano;
uniform vec3 u_azul;
uniform vec3 u_gelo;
uniform vec3 u_halo;
uniform vec3 u_branco;
uniform vec3 u_bg0;
uniform vec3 u_bg1;
uniform vec3 u_bg2;
uniform vec3 u_grade;
uniform vec3 u_vin;
uniform float u_passo;

// quanto de um traço de largura w (pixels) cobre um pixel a distância d do centro do traço
float cobre(float d, float w) {
    float ww = max(w, 1.0);
    return clamp(0.5 * ww + 0.5 - d, 0.0, 1.0) * min(w, 1.0);
}

void main() {
    vec2 px = vec2(gl_FragCoord.x, u_res.y - gl_FragCoord.y);
    float W = u_res.x;
    float H = u_res.y;
    float M = max(W, H);

    // fundo: azul da sala escura (degradê), grade e vinheta nas bordas
    float tb = length(px - vec2(u_c.x, u_c.y * 0.95)) / (M * 0.8);
    vec3 col = tb < 0.45 ? mix(u_bg0, u_bg1, tb / 0.45) : mix(u_bg1, u_bg2, clamp((tb - 0.45) / 0.55, 0.0, 1.0));
    float gx = abs(mod(px.x - u_c.x + 0.5 * u_passo, u_passo) - 0.5 * u_passo);
    float gy = abs(mod(px.y - u_c.y + 0.5 * u_passo, u_passo) - 0.5 * u_passo);
    float g = max(clamp(u_dpr - gx, 0.0, 1.0), clamp(u_dpr - gy, 0.0, 1.0)) * (55.0 / 255.0);
    col = mix(col, u_grade, g);
    float tv = length(px - u_c) / (M * 0.75);
    col = mix(col, u_vin, clamp((tv - 0.6) / 0.4, 0.0, 1.0) * (150.0 / 255.0));

    // luz difusa atrás do anel
    float th = length(px - u_c) / (u_R * 1.35);
    float ah = th < 0.75 ? mix(30.0, 55.0, th / 0.75) : mix(55.0, 0.0, clamp((th - 0.75) / 0.25, 0.0, 1.0));
    col = mix(col, u_halo, ah / 255.0 * u_brilho * step(th, 1.0));

    // fios de energia (somam luz, como o modo "Plus" do desenho normal)
    vec3 luz = vec3(0.0);
    vec2 q0 = (px - u_c) / u_R;
    float rq = length(q0);
    if (rq > 0.3 && rq < 2.0) {
        for (int i = 0; i < 18; i++) {
            if (i >= u_n) break;
            vec4 f = u_fio[i];
            float cg = cos(f.z);
            float sg = sin(f.z);
            vec2 q = vec2(q0.x * cg + q0.y * sg, -q0.x * sg + q0.y * cg);
            q.y = q.y / f.y;
            float ang = atan(q.y, q.x);
            vec4 k = u_k[i];
            vec3 a = u_a[i];
            vec3 p = u_p[i];
            float r = f.x + a.x * sin(k.x * ang + p.x) + a.y * sin(k.y * ang + p.y) + a.z * sin(k.z * ang + p.z);
            float d = abs(length(q) - r) * u_R;
            float pul = k.w * u_brilho;
            float w = f.w * u_dpr;
            luz += u_ciano * (10.0 / 255.0) * pul * cobre(d, 9.0 * w) * u_largo;
            luz += u_azul * (40.0 / 255.0) * pul * cobre(d, 3.5 * w);
            luz += u_ciano * (120.0 / 255.0) * pul * cobre(d, 1.6 * w);
            luz += u_gelo * (120.0 / 255.0) * pul * cobre(d, 0.7 * w);
            luz += u_ciano * u_bloom * pul * exp(-d * d / (72.0 * u_dpr * u_dpr));
        }
    }

    // faíscas correndo pelos fios
    for (int j = 0; j < 14; j++) {
        float ts = length(px - u_fx[j]) / (14.0 * u_dpr);
        if (ts < 1.0) {
            vec3 c = ts < 0.25 ? mix(u_branco, u_ciano, ts / 0.25) : u_ciano;
            float al = ts < 0.25 ? mix(190.0, 110.0, ts / 0.25) : mix(110.0, 0.0, (ts - 0.25) / 0.75);
            luz += c * (al / 255.0) * u_brilho;
        }
    }

    gl_FragColor = vec4(min(col + luz, vec3(1.0)), 1.0);
}
"""


def _escolha() -> str:
    return os.environ.get("JARVIS_ORBE_GPU", "1").strip().lower()


def _forcar() -> bool:
    return _escolha() in ("forcar", "forçar", "force")


def por_software(renderer: str) -> bool:
    """O OpenGL é feito pelo processador (e não pela placa de vídeo)? Vem do nome do GL_RENDERER."""
    nome = (renderer or "").lower()
    return any(s in nome for s in SOFTWARE)


def gpu_permitida() -> bool:
    """Pode tentar a placa de vídeo? (env, tela de teste, e se a última tentativa não derrubou o Jarvis)."""
    escolha = _escolha()
    if escolha in ("0", "nao", "não", "off", "false"):
        return False
    try:
        from PyQt6.QtGui import QGuiApplication

        if QGuiApplication.platformName() in ("offscreen", "minimal", "vnc"):
            return False  # sem placa de vídeo de verdade (testes)
    except Exception:
        return False
    if _forcar():
        return True
    if TESTANDO.exists():
        if _outro_jarvis_ligando():
            # outro Jarvis aberto agora mesmo está ligando a placa de vídeo: não é queda, só não usa desta vez
            print("[Orbe GPU] Outro Jarvis está abrindo agora; desta vez uso o desenho normal.")
            return False
        # a última abertura começou a ligar a placa de vídeo e não terminou: o Jarvis fechou ali.
        _marcar_falha("o Jarvis fechou ao ligar a placa de vídeo na última vez")
        return False
    return not FALHOU.exists()


def _ler_testando():
    """(número do processo, segundos desde que foi escrita) da marca de teste, ou None se não der."""
    try:
        pid, quando = TESTANDO.read_text(encoding="utf-8").split()[:2]
        return int(pid), time.time() - float(quando)
    except (OSError, ValueError):
        return None


def _outro_jarvis_ligando() -> bool:
    """A marca de teste é de OUTRO Jarvis que está vivo e abriu há pouco? Então não houve queda."""
    dono = _ler_testando()
    if dono is None:
        return False
    pid, idade = dono
    if pid == os.getpid() or abs(idade) >= LIGANDO_MAX_S:
        return False
    try:
        import psutil

        return psutil.pid_exists(pid)  # no Windows, nunca os.kill(pid, 0): lá ele FECHA o processo
    except Exception:
        return False


def _apagar_testando() -> None:
    """Apaga a marca de teste (menos a de outro Jarvis que está abrindo agora)."""
    if _outro_jarvis_ligando():
        return
    try:
        TESTANDO.unlink(missing_ok=True)
    except OSError:
        pass


def _marcar_falha(motivo: str, lembrar: bool = True) -> None:
    """Volta ao desenho normal. lembrar=False: só nesta abertura (na próxima tenta a placa de novo)."""
    print(f"[Orbe GPU] Usando o desenho normal: {motivo}.")
    if lembrar:
        try:
            PASTA.mkdir(parents=True, exist_ok=True)
            FALHOU.write_text(motivo + "\nApague este arquivo para tentar a placa de vídeo de novo.\n",
                              encoding="utf-8")
        except OSError:
            pass
    _apagar_testando()


def _testar_opengl() -> str:
    """Liga o OpenGL fora da janela e devolve o problema ("" = pode usar a placa de vídeo).

    Sem isto, uma camada que o Qt não consegue ligar deixa a tela preta (o Qt nem chama o desenho, então
    não há erro para voltar ao normal), e o OpenGL por software roda o anel inteiro no processador."""
    from PyQt6.QtGui import QOffscreenSurface, QOpenGLContext
    from PyQt6.QtOpenGL import QOpenGLVersionFunctionsFactory, QOpenGLVersionProfile

    superficie = QOffscreenSurface()
    superficie.create()
    ctx = QOpenGLContext()
    try:
        if not ctx.create() or not ctx.makeCurrent(superficie):
            return "não consegui ligar o OpenGL nesta placa de vídeo"
        try:
            perfil = QOpenGLVersionProfile()
            perfil.setVersion(2, 0)
            gl = QOpenGLVersionFunctionsFactory.get(perfil, ctx)
            if gl is None:
                return "placa de vídeo sem OpenGL 2.0"
            gl.initializeOpenGLFunctions()
            renderer = str(gl.glGetString(0x1F01) or "")  # GL_RENDERER: quem desenha de verdade
            if por_software(renderer) and not _forcar():
                return f"OpenGL feito pelo processador ({renderer}), sem placa de vídeo de verdade"
            return ""
        finally:
            ctx.doneCurrent()
    finally:
        superficie.destroy()


def criar(hud, orbe):
    """Põe a camada da placa de vídeo dentro do HUD. Devolve a camada, ou None (desenho normal)."""
    if not gpu_permitida():
        return None
    try:
        from PyQt6.QtCore import Qt, QTimer
        from PyQt6.QtGui import QPainter, QVector2D, QVector3D, QVector4D
        from PyQt6.QtOpenGL import (QOpenGLShader, QOpenGLShaderProgram, QOpenGLVersionFunctionsFactory,
                                    QOpenGLVersionProfile)
        from PyQt6.QtOpenGLWidgets import QOpenGLWidget
    except Exception as erro:
        _marcar_falha(f"OpenGL indisponível ({erro})")
        return None

    import ui_orbe as uo

    class OrbeGPU(QOpenGLWidget):
        def __init__(self):
            super().__init__(hud)
            self.ativo = True
            self._prog = None
            self._gl = None
            self._primeiro = True
            self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            self.setGeometry(hud.rect())
            self.lower()  # fica atrás da câmera e do briefing (filhos do HUD)
            # vigia: se o Qt não conseguir ligar a placa nesta janela, ele nunca chama o desenho
            # (e não dá erro nenhum); sem isto a tela ficaria preta em toda abertura
            self._sem_desenho = 0
            self._vigia = QTimer(self)
            self._vigia.timeout.connect(self._vigiar)
            self._vigia.start(VIGIA_MS)

        # ----- placa de vídeo
        def initializeGL(self):
            try:
                ctx = self.context()
                if ctx is None or not ctx.isValid():
                    raise RuntimeError("sem contexto OpenGL")
                perfil = QOpenGLVersionProfile()
                perfil.setVersion(2, 0)
                self._gl = QOpenGLVersionFunctionsFactory.get(perfil, ctx)
                if self._gl is None:
                    raise RuntimeError("placa de vídeo sem OpenGL 2.0")
                self._gl.initializeOpenGLFunctions()
                prog = QOpenGLShaderProgram(self)
                if not prog.addShaderFromSourceCode(QOpenGLShader.ShaderTypeBit.Vertex, VERTICES):
                    raise RuntimeError("vértices: " + prog.log()[:200])
                if not prog.addShaderFromSourceCode(QOpenGLShader.ShaderTypeBit.Fragment, FRAGMENTOS):
                    raise RuntimeError("fragmentos: " + prog.log()[:200])
                prog.bindAttributeLocation("pos", 0)
                if not prog.link():
                    raise RuntimeError("link: " + prog.log()[:200])
                self._prog = prog
            except Exception as erro:
                self._desistir(f"a placa de vídeo recusou o desenho ({erro})")

        def paintGL(self):
            if not self.ativo or self._prog is None:
                return
            try:
                # primeiro o anel (OpenGL puro), depois o texto com QPainter: um não mexe no do outro
                q = self._desenhar_anel()
                p = QPainter(self)
                p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
                orbe.pintar_letreiro(hud, p, q["cx"], q["cy"], q["R"], q["t"], q["H"])
                p.end()
            except Exception as erro:
                self._desistir(f"erro ao desenhar ({erro})")
                return
            if self._primeiro:
                self._primeiro = False
                self._vigia.stop()
                _apagar_testando()  # ligou e desenhou: a placa de vídeo é confiável

        def _vigiar(self):
            """A camada está à vista na tela e a placa de vídeo nunca desenhou: ela não funciona aqui."""
            if not self.ativo or not self._primeiro:
                self._vigia.stop()
                return
            janela = self.window()
            alca = janela.windowHandle()
            a_vista = (self.isVisible() and alca is not None and alca.isExposed() and not janela.isMinimized()
                       and not self.visibleRegion().isEmpty())
            self._sem_desenho = self._sem_desenho + 1 if a_vista else 0
            if self._sem_desenho >= VIGIA_VEZES:
                self._desistir("a placa de vídeo não começou a desenhar")

        def _desenhar_anel(self) -> dict:
            q = orbe.estado_quadro(hud)
            dpr = self.devicePixelRatioF()
            leve = q["leve"] and hud._graphics_quality == "low"
            fios = orbe.fios[:: 2 if leve else 1][:MAX_FIOS]
            tt, agito, t = q["tt"], q["agito"], q["t"]
            v_fio, v_k, v_a, v_p = [], [], [], []
            for fio in fios:
                (k0, a0, f0, w0), (k1, a1, f1, w1), (k2, a2, f2, w2) = fio["harm"]
                giro = fio["giro"] + tt * fio["vel_giro"] * 0.25
                pulso = 0.55 + 0.45 * math.sin(t * 1.1 + fio["fase_brilho"])
                v_fio.append(QVector4D(fio["raio"], fio["achat"], giro, fio["largura"]))
                v_k.append(QVector4D(k0, k1, k2, pulso))
                v_a.append(QVector3D(a0 * agito, a1 * agito, a2 * agito))
                v_p.append(QVector3D(f0 + tt * w0, f1 + tt * w1, f2 + tt * w2))
            faiscas = []
            for i, ang0, vel in orbe.faiscas[:FAISCAS]:
                pt = orbe._ponto(orbe.fios[i], ang0 + tt * vel, tt, q["R"], q["cx"], q["cy"], agito)
                faiscas.append(QVector2D(pt.x() * dpr, pt.y() * dpr))

            W, H = q["W"], q["H"]
            gl, prog = self._gl, self._prog
            gl.glViewport(0, 0, int(W * dpr), int(H * dpr))
            prog.bind()
            u = prog.setUniformValue
            u("u_res", float(W * dpr), float(H * dpr))
            u("u_c", float(q["cx"] * dpr), float(q["cy"] * dpr))
            u("u_R", float(q["R"] * dpr))
            u("u_dpr", float(dpr))
            u("u_n", len(fios))
            prog.setUniformValueArray("u_fio", v_fio)
            prog.setUniformValueArray("u_k", v_k)
            prog.setUniformValueArray("u_a", v_a)
            prog.setUniformValueArray("u_p", v_p)
            prog.setUniformValueArray("u_fx", faiscas)
            u("u_brilho", float(q["brilho"]))
            u("u_largo", 0.0 if leve else 1.0)
            u("u_bloom", 0.0 if leve else 0.05)
            for nome, hexa in (("u_ciano", uo.CIANO), ("u_azul", uo.AZUL), ("u_gelo", uo.GELO),
                               ("u_halo", "#1d6dff"), ("u_branco", "#ffffff"), ("u_bg0", "#0d3f99"),
                               ("u_bg1", "#082c74"), ("u_bg2", "#031444"), ("u_grade", "#3a78d8"),
                               ("u_vin", "#000814")):
                c = uo.cor(hexa)  # já vem laranja no modo Ultron
                u(nome, QVector3D(c.redF(), c.greenF(), c.blueF()))
            u("u_passo", float(max(34, int(min(W, H) / 13)) * dpr))
            prog.enableAttributeArray(0)
            prog.setAttributeArray(0, [(-1.0, -1.0), (1.0, -1.0), (-1.0, 1.0), (1.0, 1.0)])
            gl.glDrawArrays(0x0005, 0, 4)  # GL_TRIANGLE_STRIP: um retângulo do tamanho da tela
            prog.disableAttributeArray(0)
            prog.release()
            return q

        def _desistir(self, motivo: str) -> None:
            """Qualquer problema: volta ao desenho normal, sem fechar nada."""
            if not self.ativo:
                return
            self.ativo = False
            self._vigia.stop()
            _marcar_falha(motivo)
            hud._orbe_gpu = None
            self.hide()
            try:
                hud.set_graphics_quality(hud._graphics_quality)  # volta o ritmo de quadros normal
            except Exception:
                pass
            hud._quadro_novo = True
            hud.update()

    try:
        PASTA.mkdir(parents=True, exist_ok=True)
        # quem está ligando e quando: outro Jarvis abrindo ao mesmo tempo não confunde isto com uma queda
        TESTANDO.write_text(f"{os.getpid()} {time.time():.0f}\nligando a placa de vídeo\n", encoding="utf-8")
    except OSError:
        pass
    try:
        problema = _testar_opengl()
    except Exception as erro:
        problema = f"não consegui ligar o OpenGL ({erro})"
    if problema:
        # é desta máquina/sessão (ex.: área de trabalho remota, sem driver): na próxima abertura tenta de novo
        _marcar_falha(problema, lembrar=False)
        return None
    camada = OrbeGPU()
    camada.show()
    try:
        from PyQt6.QtWidgets import QApplication

        # fechou normalmente (mesmo sem ter chegado a desenhar): não foi a placa de vídeo que derrubou
        QApplication.instance().aboutToQuit.connect(_apagar_testando)
    except Exception:
        pass
    print("[Orbe GPU] Anel desenhado pela placa de vídeo.")
    return camada
