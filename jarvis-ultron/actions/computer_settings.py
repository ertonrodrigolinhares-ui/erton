import os
#computer_settings.py
import json
import re
import sys
import time
import threading
import subprocess
import unicodedata
import platform
from pathlib import Path

from core import marca

try:
    import pyautogui
    pyautogui.FAILSAFE = True
    pyautogui.PAUSE    = 0.05
    _PYAUTOGUI = True
except ImportError:
    _PYAUTOGUI = False

try:
    import pyperclip
    _PYPERCLIP = True
except ImportError:
    _PYPERCLIP = False

_OS = platform.system()  # "Windows" | "Darwin" | "Linux"


def _get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent

def _get_api_key() -> str:
    # Prefer env var; fall back to config file only if present.
    env_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if env_key:
        return env_key

    path = _get_base_dir() / "config" / "api_keys.json"
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f).get("gemini_api_key", "")

    raise RuntimeError("GEMINI_API_KEY not set (set GEMINI_API_KEY env var).")

def _get_macos_wifi_interface() -> str:
    try:
        result = subprocess.run(
            ["networksetup", "-listallhardwareports"],
            capture_output=True, text=True, timeout=5
        )
        lines = result.stdout.splitlines()
        for i, line in enumerate(lines):
            if "Wi-Fi" in line or "AirPort" in line:
                for j in range(i, min(i + 4, len(lines))):
                    if lines[j].startswith("Device:"):
                        return lines[j].split(":", 1)[1].strip()
    except Exception:
        pass
    return "en0" 

def volume_up():
    if _OS == "Windows":
        for _ in range(5): pyautogui.press("volumeup")
    elif _OS == "Darwin":
        subprocess.run(["osascript", "-e",
            "set volume output volume (output volume of (get volume settings) + 10)"],
            capture_output=True)
    else:
        subprocess.run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", "+10%"],
            capture_output=True)

def volume_down():
    if _OS == "Windows":
        for _ in range(5): pyautogui.press("volumedown")
    elif _OS == "Darwin":
        subprocess.run(["osascript", "-e",
            "set volume output volume (output volume of (get volume settings) - 10)"],
            capture_output=True)
    else:
        subprocess.run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", "-10%"],
            capture_output=True)

def volume_mute():
    if _OS == "Windows":
        pyautogui.press("volumemute")
    elif _OS == "Darwin":
        subprocess.run(["osascript", "-e", "set volume with output muted"],
            capture_output=True)
    else:
        subprocess.run(["pactl", "set-sink-mute", "@DEFAULT_SINK@", "toggle"],
            capture_output=True)

def volume_set(value: int):
    value = max(0, min(100, int(value)))
    if _OS == "Windows":
        try:
            import math
            from ctypes import cast, POINTER
            from comtypes import CLSCTX_ALL
            from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
            devices   = AudioUtilities.GetSpeakers()
            interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            vol       = cast(interface, POINTER(IAudioEndpointVolume))
            vol_db    = -65.25 if value == 0 else max(-65.25, 20 * math.log10(value / 100))
            vol.SetMasterVolumeLevel(vol_db, None)
            return
        except Exception as e:
            print(f"[Settings] pycaw failed, using keypress fallback: {e}")
            pyautogui.press("volumemute")
            pyautogui.press("volumemute")
    elif _OS == "Darwin":
        subprocess.run(["osascript", "-e", f"set volume output volume {value}"],
            capture_output=True)
        return
    else:
        subprocess.run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{value}%"],
            capture_output=True)
        return

def brightness_up():
    if _OS == "Darwin":
        subprocess.run(["osascript", "-e",
            'tell application "System Events" to key code 144'],
            capture_output=True)
    elif _OS == "Linux":
        if subprocess.run(["which", "brightnessctl"],
                capture_output=True).returncode == 0:
            subprocess.run(["brightnessctl", "set", "+10%"], capture_output=True)
        else:
            subprocess.run(
                'xrandr --output $(xrandr | grep " connected" | head -1 | cut -d " " -f1)'
                ' --brightness $(python3 -c "import subprocess; '
                'b=float(subprocess.check_output([\"xrandr\",\"--verbose\"]).decode()'
                '.split(\"Brightness:\")[1].split()[0]); print(min(1.0,b+0.1))")',
                shell=True, capture_output=True
            )
    else:
        try:
            subprocess.run(
                ["powershell", "-Command",
                 "(Get-WmiObject -Namespace root/wmi -Class WmiMonitorBrightnessMethods)"
                 ".WmiSetBrightness(1, [math]::Min(100, "
                 "(Get-WmiObject -Namespace root/wmi -Class WmiMonitorBrightness).CurrentBrightness + 10))"],
                capture_output=True, timeout=5
            )
        except Exception as e:
            print(f"[Settings] Brightness up failed on Windows: {e}")

def brightness_down():
    if _OS == "Darwin":
        subprocess.run(["osascript", "-e",
            'tell application "System Events" to key code 145'],
            capture_output=True)
    elif _OS == "Linux":
        if subprocess.run(["which", "brightnessctl"],
                capture_output=True).returncode == 0:
            subprocess.run(["brightnessctl", "set", "10%-"], capture_output=True)
        else:
            subprocess.run(
                'xrandr --output $(xrandr | grep " connected" | head -1 | cut -d " " -f1)'
                ' --brightness $(python3 -c "import subprocess; '
                'b=float(subprocess.check_output([\"xrandr\",\"--verbose\"]).decode()'
                '.split(\"Brightness:\")[1].split()[0]); print(max(0.1,b-0.1))")',
                shell=True, capture_output=True
            )
    else:
        try:
            subprocess.run(
                ["powershell", "-Command",
                 "(Get-WmiObject -Namespace root/wmi -Class WmiMonitorBrightnessMethods)"
                 ".WmiSetBrightness(1, [math]::Max(0, "
                 "(Get-WmiObject -Namespace root/wmi -Class WmiMonitorBrightness).CurrentBrightness - 10))"],
                capture_output=True, timeout=5
            )
        except Exception as e:
            print(f"[Settings] Brightness down failed on Windows: {e}")

def close_app():
    if _OS == "Darwin":
        pyautogui.hotkey("command", "q")
    else:
        pyautogui.hotkey("alt", "f4")

def close_window():
    if _OS == "Darwin":
        pyautogui.hotkey("command", "w")
    else:
        pyautogui.hotkey("ctrl", "w")

def quit_app(app_name: str | None = None):
    """
    Quit a specific app on macOS when an app name is provided.
    Falls back to closing the frontmost app/window if no app name is provided.
    """
    app_name = (app_name or "").strip()

    if _OS == "Darwin":
        if app_name:
            script = f'tell application "{app_name}" to quit'
            subprocess.run(["osascript", "-e", script], capture_output=True)
        else:
            pyautogui.hotkey("command", "q")
    else:
        pyautogui.hotkey("alt", "f4")

def full_screen():
    if _OS == "Darwin": pyautogui.hotkey("ctrl", "command", "f")
    else:               pyautogui.press("f11")

def minimize_window():
    if _OS == "Darwin": pyautogui.hotkey("command", "m")
    else:               pyautogui.hotkey("win", "down")

def maximize_window():
    if _OS == "Darwin":
        subprocess.run(["osascript", "-e",
            'tell application "System Events" to keystroke "f" '
            'using {control down, command down}'],
            capture_output=True)
    elif _OS == "Windows":
        pyautogui.hotkey("win", "up")
    else:
        try:
            subprocess.run(["wmctrl", "-r", ":ACTIVE:", "-b", "add,maximized_vert,maximized_horz"],
                capture_output=True)
        except Exception:
            pyautogui.hotkey("super", "up")

def snap_left():
    if _OS == "Windows":
        pyautogui.hotkey("win", "left")
    elif _OS == "Linux":
        try:
            subprocess.run(["wmctrl", "-r", ":ACTIVE:", "-e", "0,0,0,960,1080"],
                capture_output=True)
        except Exception:
            pass

def snap_right():
    if _OS == "Windows":
        pyautogui.hotkey("win", "right")
    elif _OS == "Linux":
        try:
            subprocess.run(["wmctrl", "-r", ":ACTIVE:", "-e", "0,960,0,960,1080"],
                capture_output=True)
        except Exception:
            pass

def switch_window():
    if _OS == "Darwin": pyautogui.hotkey("command", "tab")
    else:               pyautogui.hotkey("alt", "tab")

def show_desktop():
    if _OS == "Darwin":   pyautogui.hotkey("fn", "f11")
    elif _OS == "Windows": pyautogui.hotkey("win", "d")
    else:                  pyautogui.hotkey("super", "d")

def open_task_manager():
    if _OS == "Windows":
        pyautogui.hotkey("ctrl", "shift", "esc")
    elif _OS == "Darwin":
        subprocess.Popen(["open", "-a", "Activity Monitor"])
    else:
        for cmd in [["gnome-system-monitor"], ["xfce4-taskmanager"], ["htop"]]:
            if subprocess.run(["which", cmd[0]], capture_output=True).returncode == 0:
                subprocess.Popen(cmd)
                break


def focus_search():
    if _OS == "Darwin": pyautogui.hotkey("command", "l")
    else:               pyautogui.hotkey("ctrl", "l")

def pause_video():      pyautogui.press("space")

def refresh_page():
    if _OS == "Darwin": pyautogui.hotkey("command", "r")
    else:               pyautogui.press("f5")

def close_tab():
    if _OS == "Darwin": pyautogui.hotkey("command", "w")
    else:               pyautogui.hotkey("ctrl", "w")

def new_tab():
    if _OS == "Darwin": pyautogui.hotkey("command", "t")
    else:               pyautogui.hotkey("ctrl", "t")

def next_tab():
    if _OS == "Darwin": pyautogui.hotkey("command", "shift", "bracketright")
    else:               pyautogui.hotkey("ctrl", "tab")

def prev_tab():
    if _OS == "Darwin": pyautogui.hotkey("command", "shift", "bracketleft")
    else:               pyautogui.hotkey("ctrl", "shift", "tab")

def go_back():
    if _OS == "Darwin": pyautogui.hotkey("command", "left")
    else:               pyautogui.hotkey("alt", "left")

def go_forward():
    if _OS == "Darwin": pyautogui.hotkey("command", "right")
    else:               pyautogui.hotkey("alt", "right")

def zoom_in():
    if _OS == "Darwin": pyautogui.hotkey("command", "equal")
    else:               pyautogui.hotkey("ctrl", "equal")

def zoom_out():
    if _OS == "Darwin": pyautogui.hotkey("command", "minus")
    else:               pyautogui.hotkey("ctrl", "minus")

def zoom_reset():
    if _OS == "Darwin": pyautogui.hotkey("command", "0")
    else:               pyautogui.hotkey("ctrl", "0")

def find_on_page():
    if _OS == "Darwin": pyautogui.hotkey("command", "f")
    else:               pyautogui.hotkey("ctrl", "f")

def reload_page_n(n: int, janela=None):
    """Jarvis Ultron: com a janela (a que apareceu na pergunta), confere antes de cada F5 se ela ainda é a da
    frente; se mudou, para e lança o erro (o _depois_do_ok avisa o Erton): o ok vale só para aquela janela."""
    for vez in range(max(1, n)):
        if janela is not None and _a_mesma(_janela_da_frente()) != _a_mesma(janela):
            raise RuntimeError(f"a janela da frente mudou depois de {vez} de {n}, e parei para não apertar F5 "
                               "em outra janela")
        refresh_page()
        time.sleep(0.8)


def scroll_up(amount: int = 500):    pyautogui.scroll(amount)
def scroll_down(amount: int = 500):  pyautogui.scroll(-amount)

def scroll_top():
    if _OS == "Darwin": pyautogui.hotkey("command", "up")
    else:               pyautogui.hotkey("ctrl", "home")

def scroll_bottom():
    if _OS == "Darwin": pyautogui.hotkey("command", "down")
    else:               pyautogui.hotkey("ctrl", "end")

def page_up():   pyautogui.press("pageup")
def page_down(): pyautogui.press("pagedown")


def copy():
    if _OS == "Darwin": pyautogui.hotkey("command", "c")
    else:               pyautogui.hotkey("ctrl", "c")

def paste():
    if _OS == "Darwin": pyautogui.hotkey("command", "v")
    else:               pyautogui.hotkey("ctrl", "v")

def cut():
    if _OS == "Darwin": pyautogui.hotkey("command", "x")
    else:               pyautogui.hotkey("ctrl", "x")

def undo():
    if _OS == "Darwin": pyautogui.hotkey("command", "z")
    else:               pyautogui.hotkey("ctrl", "z")

def redo():
    if _OS == "Darwin": pyautogui.hotkey("command", "shift", "z")
    else:               pyautogui.hotkey("ctrl", "y")

def select_all():
    if _OS == "Darwin": pyautogui.hotkey("command", "a")
    else:               pyautogui.hotkey("ctrl", "a")

def save_file():
    if _OS == "Darwin": pyautogui.hotkey("command", "s")
    else:               pyautogui.hotkey("ctrl", "s")

def press_enter():   pyautogui.press("enter")
def press_escape():  pyautogui.press("escape")
def press_key(key: str): pyautogui.press(key)

def type_text(text: str, press_enter_after: bool = False):
    if not text:
        return
    if _PYPERCLIP:
        pyperclip.copy(str(text))
        time.sleep(0.15)
        paste()
    else:
        pyautogui.write(str(text), interval=0.03)
    if press_enter_after:
        time.sleep(0.1)
        pyautogui.press("enter")

def take_screenshot():
    if _OS == "Windows":
        pyautogui.hotkey("win", "shift", "s")
    elif _OS == "Darwin":
        pyautogui.hotkey("command", "shift", "3")
    else:
        for cmd in [["scrot"], ["gnome-screenshot"], ["import", "-window", "root", "screenshot.png"]]:
            if subprocess.run(["which", cmd[0]], capture_output=True).returncode == 0:
                subprocess.Popen(cmd)
                return
        pyautogui.hotkey("ctrl", "print_screen")

def lock_screen():
    if _OS == "Windows":
        pyautogui.hotkey("win", "l")
    elif _OS == "Darwin":
        subprocess.run(["pmset", "displaysleepnow"], capture_output=True)
    else:
        for cmd in [
            ["gnome-screensaver-command", "-l"],
            ["xdg-screensaver", "lock"],
            ["loginctl", "lock-session"],
        ]:
            if subprocess.run(["which", cmd[0]], capture_output=True).returncode == 0:
                subprocess.run(cmd, capture_output=True)
                return

def open_system_settings():
    if _OS == "Windows":
        pyautogui.hotkey("win", "i")
    elif _OS == "Darwin":
        subprocess.Popen(["open", "-a", "System Preferences"])
    else:
        for cmd in [["gnome-control-center"], ["xfce4-settings-manager"], ["kcmshell5"]]:
            if subprocess.run(["which", cmd[0]], capture_output=True).returncode == 0:
                subprocess.Popen(cmd)
                return

def open_file_explorer():
    if _OS == "Windows":
        pyautogui.hotkey("win", "e")
    elif _OS == "Darwin":
        subprocess.Popen(["open", str(Path.home())])
    else:
        for cmd in [["nautilus"], ["thunar"], ["dolphin"], ["nemo"]]:
            if subprocess.run(["which", cmd[0]], capture_output=True).returncode == 0:
                subprocess.Popen(cmd)
                return
        subprocess.Popen(["xdg-open", str(Path.home())])

def sleep_display():
    if _OS == "Windows":
        try:
            import ctypes
            ctypes.windll.user32.SendMessageW(0xFFFF, 0x0112, 0xF170, 2)
        except Exception as e:
            print(f"[Settings] sleep_display failed: {e}")
    elif _OS == "Darwin":
        subprocess.run(["pmset", "displaysleepnow"], capture_output=True)
    else:
        subprocess.run(["xset", "dpms", "force", "off"], capture_output=True)

def open_run():
    if _OS == "Windows":
        pyautogui.hotkey("win", "r")

def dark_mode():
    if _OS == "Darwin":
        subprocess.run(["osascript", "-e",
            'tell app "System Events" to tell appearance preferences '
            'to set dark mode to not dark mode'],
            capture_output=True)
    elif _OS == "Windows":
        try:
            import winreg
            key_path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Themes\Personalize"
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_ALL_ACCESS)
            current, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            winreg.SetValueEx(key, "AppsUseLightTheme", 0, winreg.REG_DWORD, 1 - current)
            winreg.SetValueEx(key, "SystemUsesLightTheme", 0, winreg.REG_DWORD, 1 - current)
            winreg.CloseKey(key)
        except Exception as e:
            print(f"[Settings] dark_mode registry failed: {e}")
    else:
        try:
            result = subprocess.run(
                ["gsettings", "get", "org.gnome.desktop.interface", "color-scheme"],
                capture_output=True, text=True
            )
            current = result.stdout.strip()
            new_scheme = "'default'" if "dark" in current else "'prefer-dark'"
            subprocess.run(
                ["gsettings", "set", "org.gnome.desktop.interface", "color-scheme", new_scheme],
                capture_output=True
            )
        except Exception as e:
            print(f"[Settings] dark_mode Linux failed: {e}")

def toggle_wifi():
    if _OS == "Darwin":
        iface = _get_macos_wifi_interface()
        result = subprocess.run(
            ["networksetup", "-getairportpower", iface],
            capture_output=True, text=True
        )
        state = "off" if "On" in result.stdout else "on"
        subprocess.run(["networksetup", "-setairportpower", iface, state],
            capture_output=True)
    elif _OS == "Windows":
        try:
            subprocess.run(
                ["powershell", "-Command",
                 "$adapter = Get-NetAdapter | Where-Object {$_.PhysicalMediaType -eq 'Native 802.11'};"
                 "if ($adapter.Status -eq 'Up') { Disable-NetAdapter -Name $adapter.Name -Confirm:$false }"
                 "else { Enable-NetAdapter -Name $adapter.Name -Confirm:$false }"],
                capture_output=True, timeout=10
            )
        except Exception as e:
            print(f"[Settings] toggle_wifi Windows failed: {e}")
    else:
        try:
            result = subprocess.run(["nmcli", "radio", "wifi"], capture_output=True, text=True)
            state  = "off" if "enabled" in result.stdout else "on"
            subprocess.run(["nmcli", "radio", "wifi", state], capture_output=True)
        except Exception as e:
            print(f"[Settings] toggle_wifi Linux failed: {e}")

def _energia(comando: list) -> None:
    """Jarvis Ultron: roda o comando de desligar ou reiniciar e, se o sistema recusar (o Windows devolve 1190
    quando já há um desligamento agendado), lança o erro: o _depois_do_ok avisa "Não consegui ..." em vez de
    escrever "Feito"."""
    resultado = subprocess.run(comando, capture_output=True)
    if resultado.returncode:
        saida = resultado.stderr or resultado.stdout or b""
        if isinstance(saida, bytes):
            # a saída dos comandos do Windows vem na página OEM (no Brasil, o cp850): o codec "oem" e, onde
            # ele não existe (fora do Windows de verdade, como nos testes), o cp850; no Linux e no Mac, utf-8
            for codigo in ("oem", "cp850") if _OS == "Windows" else ("utf-8",):
                try:
                    saida = saida.decode(codigo)
                    break
                except (LookupError, UnicodeDecodeError):
                    continue
            else:
                saida = saida.decode("utf-8", "replace")
        raise RuntimeError(" ".join(str(saida).split()) or f"o sistema recusou (código {resultado.returncode})")

def restart_computer():
    if _OS == "Windows":
        _energia(["shutdown", "/r", "/t", "10"])
    elif _OS == "Darwin":
        _energia(["osascript", "-e",
            'tell application "System Events" to restart'])
    else:
        _energia(["systemctl", "reboot"])

def shutdown_computer():
    if _OS == "Windows":
        _energia(["shutdown", "/s", "/t", "10"])
    elif _OS == "Darwin":
        _energia(["osascript", "-e",
            'tell application "System Events" to shut down'])
    else:
        _energia(["systemctl", "poweroff"])

ACTION_MAP: dict[str, callable] = {
    "volume_up":           volume_up,
    "volume_down":         volume_down,
    "mute":                volume_mute,
    "unmute":              volume_mute,
    "toggle_mute":         volume_mute,
    "brightness_up":       brightness_up,
    "brightness_down":     brightness_down,
    "sleep_display":       sleep_display,
    "screen_off":          sleep_display,
    "pause_video":         pause_video,
    "play_pause":          pause_video,
    "close_app":           close_app,
    "close_window":        close_window,
    "quit_app":            quit_app,
    "full_screen":         full_screen,
    "fullscreen":          full_screen,
    "minimize":            minimize_window,
    "maximize":            maximize_window,
    "snap_left":           snap_left,
    "snap_right":          snap_right,
    "switch_window":       switch_window,
    "show_desktop":        show_desktop,
    "task_manager":        open_task_manager,
    "focus_search":        focus_search,
    "refresh_page":        refresh_page,
    "reload":              refresh_page,
    "close_tab":           close_tab,
    "new_tab":             new_tab,
    "next_tab":            next_tab,
    "prev_tab":            prev_tab,
    "go_back":             go_back,
    "go_forward":          go_forward,
    "zoom_in":             zoom_in,
    "zoom_out":            zoom_out,
    "zoom_reset":          zoom_reset,
    "find_on_page":        find_on_page,
    "scroll_up":           scroll_up,
    "scroll_down":         scroll_down,
    "scroll_top":          scroll_top,
    "scroll_bottom":       scroll_bottom,
    "page_up":             page_up,
    "page_down":           page_down,
    "copy":                copy,
    "paste":               paste,
    "cut":                 cut,
    "undo":                undo,
    "redo":                redo,
    "select_all":          select_all,
    "save":                save_file,
    "enter":               press_enter,
    "escape":              press_escape,
    "screenshot":          take_screenshot,
    "lock_screen":         lock_screen,
    "open_settings":       open_system_settings,
    "file_explorer":       open_file_explorer,
    "open_run":            open_run,
    "dark_mode":           dark_mode,
    "toggle_wifi":         toggle_wifi,
    "restart":             restart_computer,
    "shutdown":            shutdown_computer,
}

_DANGEROUS_ACTIONS = {"restart", "shutdown"}

# Jarvis Ultron (Etapa 4): além de desligar e reiniciar, pede o "ok" do Erton (_pedir_ok) tudo o que
# escreve ou aperta teclas no PROGRAMA da janela da frente: o efeito depende de qual programa está na
# frente, e nada confere qual é (o Enter envia no WhatsApp, o Ctrl+V cola no chat, o F5 roda o programa no
# VS Code, o Alt+F4 fecha o que estiver na frente, o Espaço escreve num campo de texto). Fora do ACTION_MAP
# pedem também type_text (e write_on_screen, type, write), press_key e reload_n. Ação -> (teclas no
# Windows, para quê), para a pergunta.
TECLAS_PEDEM_OK = {
    "pause_video":   ("Espaço", "pausar ou continuar o vídeo"),
    "play_pause":    ("Espaço", "pausar ou continuar o vídeo"),
    "close_app":     ("Alt+F4", "fechar o programa da frente"),
    "close_window":  ("Ctrl+W", "fechar a janela ou a aba da frente"),
    "quit_app":      ("Alt+F4", "fechar o programa da frente"),
    "full_screen":   ("F11", "tela cheia"),
    "fullscreen":    ("F11", "tela cheia"),
    "focus_search":  ("Ctrl+L", "ir para a barra de endereço"),
    "refresh_page":  ("F5", "recarregar a página"),
    "reload":        ("F5", "recarregar a página"),
    "close_tab":     ("Ctrl+W", "fechar a aba"),
    "new_tab":       ("Ctrl+T", "abrir uma aba nova"),
    "next_tab":      ("Ctrl+Tab", "ir para a próxima aba"),
    "prev_tab":      ("Ctrl+Shift+Tab", "voltar para a aba anterior"),
    "go_back":       ("Alt+Seta para a esquerda", "voltar uma página"),
    "go_forward":    ("Alt+Seta para a direita", "avançar uma página"),
    "zoom_in":       ("Ctrl+=", "aumentar o zoom"),
    "zoom_out":      ("Ctrl+-", "diminuir o zoom"),
    "zoom_reset":    ("Ctrl+0", "voltar o zoom ao normal"),
    "find_on_page":  ("Ctrl+F", "procurar na página"),
    "scroll_top":    ("Ctrl+Home", "ir para o começo"),
    "scroll_bottom": ("Ctrl+End", "ir para o fim"),
    "page_up":       ("Page Up", "subir uma tela"),
    "page_down":     ("Page Down", "descer uma tela"),
    "copy":          ("Ctrl+C", "copiar"),
    "paste":         ("Ctrl+V", "colar o que está copiado"),
    "cut":           ("Ctrl+X", "recortar"),
    "undo":          ("Ctrl+Z", "desfazer"),
    "redo":          ("Ctrl+Y", "refazer"),
    "select_all":    ("Ctrl+A", "selecionar tudo"),
    "save":          ("Ctrl+S", "salvar"),
    "enter":         ("Enter", "confirmar ou enviar"),
    "escape":        ("Esc", "cancelar ou fechar"),
}
# Não pedem: o que não chega ao programa da frente. As teclas de volume, os atalhos com a tecla Windows, o
# Alt+Tab e o Ctrl+Shift+Esc são atendidos pelo próprio Windows; brilho, Wi-Fi, tema escuro e apagar a tela
# não usam teclas; rolar usa a rodinha do mouse. Ação -> por quê.
NAO_PEDEM_OK = {
    "volume_up":       "tecla de volume, atendida pelo Windows",
    "volume_down":     "tecla de volume, atendida pelo Windows",
    "mute":            "tecla de volume, atendida pelo Windows",
    "unmute":          "tecla de volume, atendida pelo Windows",
    "toggle_mute":     "tecla de volume, atendida pelo Windows",
    "brightness_up":   "brilho pelo Windows, sem teclas",
    "brightness_down": "brilho pelo Windows, sem teclas",
    "sleep_display":   "só apaga a tela, sem teclas (o PC continua ligado)",
    "screen_off":      "só apaga a tela, sem teclas (o PC continua ligado)",
    "minimize":        "Windows+Seta para baixo: o Windows mexe na janela, não no que está nela",
    "maximize":        "Windows+Seta para cima: o Windows mexe na janela, não no que está nela",
    "snap_left":       "Windows+Seta para a esquerda: o Windows mexe na janela, não no que está nela",
    "snap_right":      "Windows+Seta para a direita: o Windows mexe na janela, não no que está nela",
    "show_desktop":    "Windows+D: o Windows mostra a área de trabalho",
    "switch_window":   "Alt+Tab: o Windows troca de janela",
    "task_manager":    "Ctrl+Shift+Esc: o Windows abre o Gerenciador de Tarefas",
    "screenshot":      "Windows+Shift+S: o Windows abre a captura de tela",
    "lock_screen":     "Windows+L: o Windows bloqueia a tela (não desliga nem sai da conta)",
    "open_settings":   "Windows+I: o Windows abre as Configurações",
    "file_explorer":   "Windows+E: o Windows abre o Explorador de Arquivos",
    "open_run":        "Windows+R: o Windows abre o Executar (digitar nele pede o ok)",
    "dark_mode":       "tema escuro pelo registro do Windows, sem teclas",
    "toggle_wifi":     "Wi-Fi pelo Windows, sem teclas",
    "scroll_up":       "rodinha do mouse, sem teclas",
    "scroll_down":     "rodinha do mouse, sem teclas",
}
# Teclas do press_key que vão para o Windows, e não para a janela da frente: a pergunta diz o que acontece com
# o PC, sem janela, como desligar e reiniciar. Tecla (como o pyautogui a lê, em minúsculas) -> o que faz.
TECLAS_DE_ENERGIA = {"sleep": "suspender o computador"}


def _power_target_text(params: dict, description: str, value) -> str:
    return " ".join(
        str(part or "")
        for part in (
            description,
            value,
            params.get("app_name", ""),
            params.get("target", ""),
            params.get("text", ""),
        )
    ).lower()


def _is_jarvis_self_shutdown_request(params: dict, action: str, description: str, value) -> bool:
    text = f"{action} {_power_target_text(params, description, value)}"
    if not any(nome in text for nome in marca.nomes_falados()):  # "jarvis" e os nomes de core/marca.py
        return False
    return any(word in text for word in ("shutdown", "shut down", "restart", "reboot", "close", "quit", "exit", "stop"))


def _has_explicit_computer_power_target(params: dict, description: str, value) -> bool:
    text = _power_target_text(params, description, value)
    return any(word in text for word in ("computer", "system", "mac", "macbook", "pc", "machine"))


# ----- Jarvis Ultron: o "ok" do Erton conferido no código (Etapa 4 do docs/PLANO-REORGANIZACAO.md)
#
# Desligar ou reiniciar o PC, e escrever ou apertar teclas no programa da frente (TECLAS_PEDEM_OK), só
# acontece com o "ok" dele conferido pelo core/aprovacao.py, como no approve_publication e nos vídeos. A
# primeira chamada não faz nada: guarda o pedido, com a marca da fala atual dele, e devolve a pergunta com
# o texto ou as teclas e a janela da frente (que também aparece num aviso do Windows, perto do relógio, e no
# alto da tela do Jarvis). Numa chamada seguinte com o MESMO
# pedido (mesmo texto, mesma tecla, mesma janela, pelo número e pelo título), só faz se a PRIMEIRA fala nova
# dele depois da pergunta for um "ok" claro; um "não", ou qualquer outra resposta, cancela. O confirmed=yes
# que o modelo preenche não conta. O ok vale uma vez só e só para aquele pedido. Uma pergunta por vez:
# enquanto uma espera a resposta, outro pedido na mesma fala não é guardado (senão o ok dado à pergunta
# falada faria a outra, guardada calada). Como nos vídeos, a ação roda num fio depois de
# ainda_aprovado (no Gemini ao vivo o resto da fala só chega depois que a ferramenta responde): se o resto
# da resposta desfizer o "ok", ou se a janela da frente não for mais a que apareceu na pergunta, nada é
# feito e ele é avisado. Na janela do próprio Jarvis nada é digitado nem apertado, nem com o ok: o campo de
# texto dela manda o que recebe como fala nova do Erton, que responderia a outra pergunta. Chamada sem o
# jarvis (fora da conversa) não faz nada.

VALIDADE_PEDIDO = 2 * 60  # segundos que a pergunta espera a resposta dele
RECARREGAR_NO_MAXIMO = 20  # vezes do reload_n por ok (o número vem do modelo; cada F5 leva 0,8 s)
TITULO_DO_JARVIS = marca.TITULO_DA_JANELA  # o da janela da tela (ui.py, setWindowTitle): os dois leem de core/marca.py

_pendente: dict = {}
_trava = threading.Lock()


def _janela_da_frente() -> tuple[int, str]:
    """(número, título) da janela da frente, no Windows; (0, "") quando não dá para saber."""
    if _OS != "Windows":
        return 0, ""
    try:
        import ctypes

        user32 = ctypes.windll.user32
        janela = user32.GetForegroundWindow() or 0
        tamanho = int(user32.GetWindowTextLengthW(janela) or 0)
        titulo = ctypes.create_unicode_buffer(tamanho + 1)
        user32.GetWindowTextW(janela, titulo, tamanho + 1)
        return int(janela), " ".join(titulo.value.split())
    except Exception:
        return 0, ""


def _a_mesma(janela) -> tuple:
    """O que identifica a janela na chave e na conferência antes de agir: o número e o título (trocar de aba
    no navegador muda só o título), sem a marca de "não salvo" que os editores põem no começo do título ao
    receber texto ("*Sem título - Bloco de Notas", "● app.py - Visual Studio Code")."""
    return janela[0], janela[1].lstrip("*●• ")


def _programas_do_jarvis() -> set:
    """Os números (pid) dos programas do Jarvis: este (o cérebro, ou o programa único) e os de Python acima
    dele, entre eles o da tela, que abriu o cérebro (às vezes por um python.exe do ambiente virtual)."""
    numeros = {os.getpid()}
    try:
        import psutil

        for pai in psutil.Process().parents():
            if pai.name().lower().startswith("python"):
                numeros.add(pai.pid)
    except Exception:
        pass
    return numeros


def _janela_do_jarvis(janela) -> bool:
    """A janela da frente é do próprio Jarvis (a tela, o painel Ultron...)? Pelo título da tela e, no Windows,
    pelo programa dono da janela."""
    if _a_mesma(janela)[1] == TITULO_DO_JARVIS:
        return True
    if _OS != "Windows" or not janela[0]:
        return False
    try:
        import ctypes

        dono = ctypes.c_ulong(0)
        ctypes.windll.user32.GetWindowThreadProcessId(janela[0], ctypes.byref(dono))
        return bool(dono.value) and dono.value in _programas_do_jarvis()
    except Exception:
        return False


def _log(jarvis, texto: str) -> None:
    ui = getattr(jarvis, "ui", None)
    if ui is not None:
        ui.write_log(texto)


def _mostrar_pergunta(jarvis, pergunta: str) -> None:
    """A pergunta num aviso do Windows, perto do relógio, e no alto da tela do Jarvis (ui.notificar): o registro
    (write_log) só aparece na tela antiga, embaixo do anel, e ao digitar o programa da frente cobre o Jarvis."""
    notificar = getattr(getattr(jarvis, "ui", None), "notificar", None)
    if callable(notificar):
        try:
            notificar("Pergunta", pergunta)
        except Exception as erro:  # a pergunta falada continua valendo
            print(f"[Settings] Could not show the question: {erro}")


def _avisar(jarvis, aviso: str) -> None:
    anunciar = getattr(jarvis, "anunciar", None)
    if callable(anunciar):  # respeita o modo chamada: guarda o aviso até o "Hey Jarvis"
        anunciar(aviso, "Computador")
        return
    _log(jarvis, f"SYS: ✋ {aviso}")
    falar = getattr(jarvis, "_falar_aviso", None)
    if callable(falar):
        falar(aviso)


def _pedir_ok(jarvis, chave: tuple, o_que: str, janela, fazer) -> str:
    """Pergunta antes de agir ou, se a pergunta já foi feita, confere a resposta do Erton e, com o "ok",
    faz (num fio). Devolve o texto para o modelo. o_que: o que vai ser feito, em português ("reiniciar o
    computador"). janela: (número, título) da janela da frente quando a ação vai para ela, que entra na
    chave (pelo _a_mesma) e, a que apareceu na pergunta, é conferida de novo antes de agir; None quando a
    janela não importa (desligar, reiniciar, suspender). Na janela do próprio Jarvis, recusa sem perguntar."""
    from core import marca as _marca  # aqui embaixo, "marca" é a marca da fala

    if jarvis is None:  # sem a conversa não há como conferir o "ok" dele
        return (f"Not done: this needs the user's ok, which {_marca.NOME} checks in the conversation, and this call "
                "did not come from the conversation.")
    if janela is not None and _janela_do_jarvis(janela):
        # o texto e o Enter iriam para o campo do Jarvis e virariam uma fala nova do Erton, que responderia a
        # outra pergunta (reiniciar, um vídeo pago, uma publicação); as teclas apertariam os botões dele
        return (f"Not done: the window in front is {_marca.NOME} itself, and text or keys sent there would count as "
                f"the user speaking (or press {_marca.NOME}'s own buttons). {_marca.NOME} never types or presses keys in its "
                "own window. Tell the user, in one short Portuguese sentence, to bring the right program to "
                "the front and ask again.")
    from core import aprovacao

    agora = time.monotonic()
    with _trava:
        valido = bool(_pendente) and agora - _pendente.get("em", 0) < VALIDADE_PEDIDO
        pedido = valido and _pendente.get("chave") == chave
        marca = _pendente.get("marca", 0)
        fala = aprovacao.marca(jarvis)
        if pedido and fala == marca:
            return ("Not done: the user has not answered the question yet. Wait for the answer; only a clear "
                    "ok in the user's own words, said after the question, counts.")
        if valido and fala == marca:  # outra pergunta, da mesma fala, ainda espera a resposta: uma por vez
            return ("Not done: another action is already waiting for the user's ok. Ask only that question, "
                    "wait for the answer, and call this one again only after that one is done or cancelled; "
                    "then it asks its own question.")
        if pedido and fala == marca + 1:
            janela = _pendente.get("janela")  # a que apareceu na pergunta, e não a desta chamada
            _pendente.clear()  # a primeira resposta decide, uma vez só: o "ok" faz, qualquer outra cancela
            fala_do_ok = aprovacao.fala_que_aprovou(jarvis, marca)
        else:  # pedido novo (ou outro pedido, ou a pergunta venceu, ou já houve outras falas): pergunta
            pedido = False
            _pendente.clear()
            _pendente.update(chave=chave, em=agora, marca=fala, janela=janela)

    if not pedido:
        if janela is None:
            pergunta = f"Posso {o_que} agora? Salve antes o que estiver aberto."
        else:
            titulo = janela[1] if len(janela[1]) <= 80 else janela[1][:79] + "…"
            onde = f'na janela "{titulo}"' if titulo else "na janela da frente (não consegui ver qual é)"
            pergunta = f"Posso {o_que} {onde}?"
        pergunta += ' Para confirmar, diga "ok, pode fazer".'
        _log(jarvis, f"SYS: ✋ Antes de agir, pergunto: {pergunta}")
        _mostrar_pergunta(jarvis, pergunta)
        return (f"Not done yet: {_marca.NOME} needs the user's ok first. Ask the user now, in Portuguese, exactly this "
                f"question: {pergunta} Then stop and wait for the answer. Only if the user's next answer is a "
                "clear ok in their own words (for example 'ok, pode fazer'), call computer_settings again with "
                "exactly the same parameters. If the user says no or anything else, do not call it again; just "
                "say you did not do it. Never call it again without the user's answer.")
    if fala_do_ok != marca + 1:
        _log(jarvis, f'SYS: ✋ Cancelado ({o_que}): a resposta não foi um "ok" claro.')
        return ("Cancelled: the user's answer to the question was not a clear ok, so nothing was done. Tell the "
                "user, in one short Portuguese sentence, that you did not do it. Call computer_settings again "
                "only if the user asks for it again.")
    threading.Thread(target=_depois_do_ok, args=(jarvis, fala_do_ok, o_que, janela, fazer),
                     daemon=True, name="ComputadorOk").start()
    return (f"Approved by the user. {_marca.NOME} checks the user's whole answer once more and then does it. Tell the "
            "user, in one short Portuguese sentence, that you are doing it. Do not call computer_settings "
            "again for this.")


def _depois_do_ok(jarvis, fala_do_ok: int, o_que: str, janela, fazer) -> None:
    """Fio: confere o "ok" de novo, com a fala inteira, e se a janela da frente ainda é a da pergunta; só
    então faz."""
    from core import aprovacao

    # A ferramenta pode ter chegado com só o começo da resposta transcrito ("Ok," ... "não, espera"):
    # antes do que não tem volta, confere de novo com a fala inteira.
    if not aprovacao.ainda_aprovado(jarvis, fala_do_ok):
        _avisar(jarvis, f'Não vou {o_que}: a sua resposta não foi um "ok" claro. Se quiser, peça de novo.')
        return
    if janela is not None and _a_mesma(_janela_da_frente()) != _a_mesma(janela):
        _avisar(jarvis, f"Não vou {o_que}: a janela da frente mudou depois da pergunta. Se quiser, peça de novo.")
        return
    try:
        fazer()
    except Exception as erro:
        print(f"[Settings] Action failed after the ok ({o_que}): {erro}")
        _avisar(jarvis, f"Não consegui {o_que}: {str(erro)[:150]}")
        return
    _log(jarvis, f"SYS: ✅ Feito com o seu ok: {o_que}.")



def _detect_action(description: str) -> dict:

    import google.generativeai as genai
    genai.configure(api_key=_get_api_key())
    model = genai.GenerativeModel("gemini-2.5-flash-lite")

    available = ", ".join(sorted(ACTION_MAP.keys())) + \
                ", volume_set, type_text, press_key, reload_n"

    prompt = f"""You are an intent detector for a computer control assistant.

The user issued a command (possibly in any language): "{description}"

Available actions: {available}

Return ONLY a valid JSON object:
{{"action": "action_name", "value": null_or_value}}

Rules:
- Pick the single best matching action from the available list.
- If the user says to shut down, restart, reboot, close, quit, exit, or stop {marca.NOME}, do not choose shutdown or restart.
- Choose shutdown/restart only when the user clearly asks to power off or restart the computer/system/Mac/PC.
- For volume_set: value is an integer 0-100.
- For type_text: value is the exact text to type.
- For press_key: value is the key name (e.g. "f5", "tab", "enter").
- For reload_n: value is an integer (number of times to reload).
- If no clear match, pick the closest action.
- Return ONLY the JSON, no explanation, no markdown."""

    try:
        resp = model.generate_content(prompt)
        text = re.sub(r"```(?:json)?", "", resp.text).strip().rstrip("`").strip()
        return json.loads(text)
    except Exception as e:
        print(f"[Settings] Intent detection failed: {e}")
        return {"action": description.lower().replace(" ", "_"), "value": None}

def computer_settings(
    parameters: dict = None,
    response=None,
    player=None,
    session_memory=None,
    jarvis=None,
) -> str:
    """jarvis: a conversa (o main.py passa no _execute_tool), onde o "ok" do Erton é conferido. Sem ela,
    desligar, reiniciar, digitar e apertar teclas no programa da frente não acontecem."""
    if not _PYAUTOGUI:
        return "pyautogui is not installed. Run: pip install pyautogui"

    params      = parameters or {}
    raw_action  = params.get("action", "").strip()
    description = params.get("description", "").strip()
    value       = params.get("value", None)

    if not raw_action and description:
        detected   = _detect_action(description)
        raw_action = detected.get("action", "")
        if value is None:
            value = detected.get("value")

    action = raw_action.lower().strip().replace(" ", "_").replace("-", "_")

    if not action:
        return "No action could be determined."

    if _is_jarvis_self_shutdown_request(params, action, description, value):
        return f"{marca.NOME} self-shutdown is disabled. No computer shutdown was performed."

    print(f"[Settings] Action: {action}  Value: {value}  OS: {_OS}")
    if player:
        player.write_log(f"[Settings] {action}")

    if action in _DANGEROUS_ACTIONS:
        if not _has_explicit_computer_power_target(params, description, value):
            return (
                f"Refusing to {action} the computer because the target was not explicit. "
                f"Say '{action} my computer' if you intend to power-control the machine."
            )
        # o confirmed=yes do modelo não basta: só com o "ok" do Erton conferido no código
        o_que = "reiniciar o computador" if action == "restart" else "desligar o computador"
        return _pedir_ok(jarvis, (action,), o_que, None, ACTION_MAP[action])

    if action == "volume_set":
        try:
            volume_set(int(value or 50))
            return f"Volume set to {value}%."
        except Exception as e:
            return f"Could not set volume: {e}"

    if action in ("type_text", "write_on_screen", "type", "write"):
        text = str(value or params.get("text", "")).strip()
        if not text:
            return "No text provided to type."
        if any(unicodedata.category(letra) in ("Cc", "Cf") for letra in text):
            # quebra de linha e tab viram Enter e Tab de verdade (e, colados num console, cada linha roda), e os
            # invisíveis (como o U+202E, que inverte o texto na tela) fazem a pergunta mostrar outra coisa
            return ("Not done: the text has line breaks, tabs or invisible characters, which would press keys "
                    f"or make the question show something different from what is typed. {marca.NOME} types only one "
                    "line of visible text per ok (Enter only with press_enter, which the question shows). Tell "
                    "the user, in one short Portuguese sentence.")
        enter_after = str(params.get("press_enter", "false")).lower() in ("true", "1", "yes")
        # escreve na janela da frente, seja ela qual for: só com o "ok" do Erton (Etapa 4)
        janela = _janela_da_frente()
        o_que = f'digitar "{text}"' + (" e apertar Enter" if enter_after else "")
        return _pedir_ok(jarvis, ("type_text", text, enter_after, _a_mesma(janela)), o_que, janela,
                         lambda: type_text(text, press_enter_after=enter_after))

    if action == "press_key":
        key = str(value or params.get("key", "")).strip()
        if not key:
            return "No key specified."
        if key.lower() in TECLAS_DE_ENERGIA:  # suspende o PC: pergunta como desligar e reiniciar, sem janela
            return _pedir_ok(jarvis, ("press_key", key.lower()), TECLAS_DE_ENERGIA[key.lower()], None,
                             lambda: press_key(key))
        janela = _janela_da_frente()
        return _pedir_ok(jarvis, ("press_key", key, _a_mesma(janela)), f'apertar a tecla "{key}"', janela,
                         lambda: press_key(key))

    if action in ("reload_n", "refresh_n", "reload_page_n"):
        try:
            vezes = max(1, int(value or 1))
        except (TypeError, ValueError) as e:
            return f"Reload failed: {e}"
        if vezes > RECARREGAR_NO_MAXIMO:
            return (f"Not done: {marca.NOME} reloads at most {RECARREGAR_NO_MAXIMO} times per ok, and {vezes} were "
                    "asked. Tell the user, in one short Portuguese sentence, and ask for a smaller number.")
        janela = _janela_da_frente()
        o_que = f"apertar F5 (recarregar a página) {vezes} {'vez' if vezes == 1 else 'vezes'}"
        # a cada F5 confere de novo a janela: se o Erton trocar de janela no meio, para
        return _pedir_ok(jarvis, ("reload_n", vezes, _a_mesma(janela)), o_que, janela,
                         lambda: reload_page_n(vezes, janela))

    if action == "scroll_up":
        scroll_up(int(value or 500))
        return "Scrolled up."

    if action == "scroll_down":
        scroll_down(int(value or 500))
        return "Scrolled down."

    func = ACTION_MAP.get(action)
    if not func:
        return f"Unknown action: '{raw_action}'."

    app_name = ""
    if action in ("quit_app", "close_app", "close_window"):
        app_name = str(
            params.get("app_name")
            or value
            or description
            or ""
        ).strip()

    def fazer() -> str:
        # If user named an app on macOS, target that app directly.
        if _OS == "Darwin" and app_name:
            quit_app(app_name)
            return f"Closed app: {app_name}."
        func()
        return f"Done: {action}."

    if action in TECLAS_PEDEM_OK:
        # tecla para o programa da frente: só com o "ok" do Erton (Etapa 4)
        teclas, para_que = TECLAS_PEDEM_OK[action]
        do_mac = app_name if _OS == "Darwin" else ""
        o_que = f'fechar o programa "{do_mac}"' if do_mac else f"apertar {teclas} ({para_que})"
        janela = _janela_da_frente()
        return _pedir_ok(jarvis, (action, do_mac, _a_mesma(janela)), o_que, janela, fazer)

    try:
        return fazer()
    except Exception as e:
        print(f"[Settings] Action failed ({action}): {e}")
        return f"Action failed ({action}): {e}"
