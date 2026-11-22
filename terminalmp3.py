#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
terminal-mp3player — clon visual de Winamp clásico corriendo 100% en terminal.

Diseño: dos ventanas (reproductor + ecualizador) a la izquierda y
playlist a la derecha, con LCD verde, faders amarillos y botones.

Controles:
    ↑ / ↓      elegir canción
    Enter      reproducir
    Espacio    pausa / reanudar
    ← / →      anterior / siguiente
    + / -      volumen
    s          shuffle on/off
    q / Esc    salir
"""

from __future__ import annotations

import curses
import ctypes
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np

try:
    import pygame
    import pygame.sndarray
except ImportError as exc:  # pragma: no cover
    print("Falta pygame: python3 -m pip install --user pygame", file=sys.stderr)
    raise SystemExit(1) from exc


AUDIO_EXTS = {".mp3", ".ogg", ".oga", ".wav", ".flac", ".aac", ".m4a", ".opus", ".wma"}
VOLUME_STEP = 0.1
BASE_DIR = Path(__file__).resolve().parent
APP_BIN = BASE_DIR / "bin"
LOCAL_MUSIC_DIR = BASE_DIR / "music"
USER_MUSIC_DIR = Path.home() / "Music" / "terminal-mp3player"
PLAYLISTS_DIR = Path.home() / ".config" / "terminal-mp3player" / "playlists"
URL_CACHE_DIR = Path("/tmp/opencode/terminal-mp3player-cache")


class Track:
    """Pista local o URL de YouTube Music."""

    def __init__(self, name: str, path=None, url=None, duration=None, cache_path=None):
        self.name = name
        self.path = Path(path) if path else None
        self.url = url
        self.duration = duration
        self.cache_path = Path(cache_path) if cache_path else None

    @property
    def is_url(self) -> bool:
        return bool(self.url) and self.path is None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "path": str(self.path) if self.path else None,
            "url": self.url,
            "duration": self.duration,
        }

    @staticmethod
    def from_dict(data: dict) -> "Track":
        return Track(
            data.get("name", "?"),
            data.get("path"),
            data.get("url"),
            data.get("duration"),
        )

EQ_LEVELS = [0.62, 0.48, 0.55, 0.70, 0.58, 0.42, 0.50, 0.65, 0.45, 0.38]
EQ_LABELS = ["60", "170", "310", "600", "1K", "3K", "6K", "12K", "14K", "16K"]

PRESETS = {
    "ROCK":   [0.80, 0.70, 0.55, 0.45, 0.45, 0.60, 0.72, 0.78, 0.72, 0.62],
    "HIP-HOP":[0.90, 0.82, 0.68, 0.48, 0.38, 0.50, 0.62, 0.68, 0.62, 0.52],
    "METAL":  [0.85, 0.75, 0.68, 0.58, 0.52, 0.72, 0.86, 0.90, 0.85, 0.75],
    "SALSA":  [0.70, 0.66, 0.62, 0.68, 0.76, 0.80, 0.72, 0.62, 0.56, 0.50],
    "CUMBIA": [0.76, 0.62, 0.56, 0.70, 0.80, 0.76, 0.66, 0.56, 0.50, 0.46],
}
PRESET_NAMES = list(PRESETS)

DIGITS = {
    "0": ["███", "█ █", "█ █", "█ █", "███"],
    "1": [" █ ", "██ ", " █ ", " █ ", "███"],
    "2": ["███", "  █", "███", "█  ", "███"],
    "3": ["███", "  █", "███", "  █", "███"],
    "4": ["█ █", "█ █", "███", "  █", "  █"],
    "5": ["███", "█  ", "███", "  █", "███"],
    "6": ["███", "█  ", "███", "█ █", "███"],
    "7": ["███", "  █", "  █", "  █", "  █"],
    "8": ["███", "█ █", "███", "█ █", "███"],
    "9": ["███", "█ █", "███", "  █", "███"],
    ":": ["   ", " █ ", "   ", " █ ", "   "],
}

state = {
    "playlist": [],
    "index": 0,
    "offset": 0,
    "playing": False,
    "paused": False,
    "shuffle": False,
    "volume": 0.5,
    "prev_volume": 0.5,
    "eq_on": True,
    "eq_auto": False,
    "eq_generation": 0,
    "eq_pending": None,
    "current_source": None,
    "pcm": None,
    "channel": None,
    "start_offset": 0.0,
    "play_started": 0.0,
    "paused_elapsed": 0.0,
    "preset_index": 0,
    "preset_menu": False,
    "last_auto": 0.0,
    "show_eq": True,
    "show_playlist": True,
    "base_cols": 120,
    "base_rows": 30,
    "resize_pending": None,
    "current_playlist": "Default",
    "ui_mode": None,
    "ui_input": "",
    "ui_message": "",
    "message_until": 0.0,
    "pending_download": None,
    "quit": False,
    "error": "",
    "started_at": 0.0,
}

# Geometría de la interfaz, se recalcula en cada dibujado.
LAYOUT = {
    "volume": None,
    "lcd": None,
    "player_buttons": [],
    "eq_sliders": [],
    "playlist_rows": [],
    "playlist_buttons": [],
    "transport": [],
    "eq_buttons": [],
    "preset_items": [],
    "download_icons": [],
}
DRAG = {"target": None}

AUDIO_INFO = {"rate": 44100, "sample": -16, "channels": 2}

# Ecualizador en tiempo real (effect de SDL_mixer).
EQ_EFFECT_CB = None
EQ_FIR = None
EQ_TAIL = {}
EQ_ACTIVE = True
EQ_CALL_COUNT = 0

DURATION_CACHE: dict[Path, float | None] = {}


# ----------------------------------------------------------------------
# Audio / playlist
# ----------------------------------------------------------------------
def default_music_dir() -> Path:
    if str(BASE_DIR).startswith("/opt/"):
        return USER_MUSIC_DIR
    return LOCAL_MUSIC_DIR


def music_dir() -> Path:
    raw = (
        os.environ.get("TERMINAL_MP3_DIR")
        or os.environ.get("WINAMP_MUSIC_DIR")
        or (sys.argv[1] if len(sys.argv) > 1 else str(default_music_dir()))
    )
    return Path(raw).expanduser().resolve()


def tracks_from_folder() -> list[Track]:
    folder = music_dir()
    folder.mkdir(parents=True, exist_ok=True)
    return [
        Track(p.stem.replace("_", " ").strip(), path=p)
        for p in sorted(folder.rglob("*"))
        if p.is_file() and p.suffix.lower() in AUDIO_EXTS
    ]


def load_playlist() -> None:
    tracks = tracks_from_folder()
    if not tracks:
        print(f"No hay archivos de audio en: {music_dir()}")
        print("Copia algunos MP3/OGG/WAV ahí y vuelve a ejecutar.")
        raise SystemExit(1)
    state["playlist"] = tracks


def design_eq_fir(rate: int, bands: list[float], taps: int = 256) -> np.ndarray:
    """FIR de fase lineal con la respuesta de los 10 faders."""
    n_fft = taps
    freqs = np.fft.rfftfreq(n_fft, 1.0 / rate)
    mag = np.ones_like(freqs, dtype=np.float64)
    for label, level in zip(EQ_LABELS, bands):
        f0 = float(label.lower().replace("k", "")) * (1000 if "k" in label.lower() else 1)
        db = (level - 0.5) * 24.0
        width = max(30.0, f0 * 0.7)
        bump = np.exp(-0.5 * ((freqs - f0) / width) ** 2)
        mag *= 10.0 ** ((db / 20.0) * bump)
    impulse = np.fft.irfft(mag, n=n_fft)
    fir = np.concatenate([impulse[n_fft // 2:], impulse[:n_fft // 2]])
    fir = fir * np.hanning(n_fft)
    return fir.astype(np.float32)


def update_eq_fir() -> None:
    """Actualiza el filtro en caliente: no detiene ni reinicia la música."""
    global EQ_FIR, EQ_TAIL, EQ_ACTIVE
    EQ_ACTIVE = state["eq_on"]
    if not EQ_ACTIVE:
        return
    EQ_FIR = design_eq_fir(AUDIO_INFO["rate"], EQ_LEVELS)
    EQ_TAIL = {
        ch: np.zeros(len(EQ_FIR) - 1, dtype=np.float32)
        for ch in range(AUDIO_INFO["channels"])
    }


POSTMIX_FUNC = None


def sdl_eq_effect(udata, stream, length: int) -> None:
    """Se llama desde el hilo de audio de SDL para cada bloque reproducido."""
    global EQ_CALL_COUNT
    EQ_CALL_COUNT += 1
    if not EQ_ACTIVE or EQ_FIR is None or length <= 0:
        return
    channels = max(1, AUDIO_INFO["channels"])
    try:
        raw = ctypes.string_at(stream, length)
        data = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
        frames = data.size // channels
        if frames == 0:
            return
        data = data[:frames * channels].reshape(frames, channels)
        out = np.empty_like(data)
        for ch in range(channels):
            x = data[:, ch]
            conv = np.convolve(x, EQ_FIR)
            y = conv[:frames] + EQ_TAIL.get(ch, np.zeros(len(EQ_FIR) - 1, dtype=np.float32))[:frames]
            EQ_TAIL[ch] = conv[frames:]
            out[:, ch] = np.clip(y, -1.0, 1.0)
        packed = (out * 32767.0).astype("<i2").tobytes()
        ctypes.memmove(stream, packed, min(length, len(packed)))
    except Exception:
        return


def setup_eq_effect() -> None:
    """Registra el efecto de SDL_mixer para procesar el audio en tiempo real."""
    global EQ_EFFECT_CB, POSTMIX_FUNC
    try:
        lib = ctypes.CDLL("libSDL2_mixer-2.0.so.0")
        POSTMIX_FUNC = ctypes.CFUNCTYPE(
            None, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int
        )
        EQ_EFFECT_CB = POSTMIX_FUNC(sdl_eq_effect)
        lib.Mix_SetPostMix.argtypes = [POSTMIX_FUNC, ctypes.c_void_p]
        lib.Mix_SetPostMix.restype = None
        lib.Mix_SetPostMix(EQ_EFFECT_CB, None)
        update_eq_fir()
    except Exception:
        pass


def init_audio() -> None:
    configured = os.environ.get("SDL_AUDIODRIVER")
    attempts = [configured] if configured else [None, "dummy"]
    errors = []
    for driver in attempts:
        if driver:
            os.environ["SDL_AUDIODRIVER"] = driver
        else:
            os.environ.pop("SDL_AUDIODRIVER", None)
        # Configuración preferida: 44.1 kHz, 16-bit estéreo, buffer amplio
        # (evita cortes sin resamplear innecesariamente).
        for config in (
            {"frequency": 48000, "size": -16, "channels": 2, "buffer": 2048},
            {"frequency": 44100, "size": -16, "channels": 2, "buffer": 2048},
            {"frequency": 44100, "size": -16, "channels": 2},
            {},
        ):
            try:
                pygame.mixer.init(**config)
                AUDIO_INFO.update({
                    "rate": pygame.mixer.get_init()[0],
                    "sample": pygame.mixer.get_init()[1],
                    "channels": pygame.mixer.get_init()[2],
                })
                setup_eq_effect()
                if driver == "dummy":
                    print("⚠ Sin dispositivo de audio: modo silencioso (dummy).", file=sys.stderr)
                return
            except pygame.error as exc:
                errors.append(f"  - {driver or 'por defecto'} {config or 'default'}: {exc}")
    print("No se pudo inicializar el audio:", file=sys.stderr)
    for err in errors:
        print(err, file=sys.stderr)
    raise SystemExit(1)


# ----------------------------------------------------------------------
# YouTube / descargas
# ----------------------------------------------------------------------
def ytdlp_bin() -> str | None:
    bundled = APP_BIN / "yt-dlp"
    if bundled.exists() and os.access(bundled, os.X_OK):
        return str(bundled)
    return shutil.which("yt-dlp")


def safe_name(text: str) -> str:
    return re.sub(r'[^\w\s\-_()áéíóúñÁÉÍÓÚÑ]', "", text).strip()[:90] or "track"


def fetch_url_info(url: str) -> tuple[str | None, float | None, str]:
    """Obtiene título y duración sin descargar el audio."""
    binary = ytdlp_bin()
    if binary:
        try:
            out = subprocess.check_output(
                [binary, "--no-warnings", "--skip-download",
                 "--print", "%(title)s|%(duration)s", url],
                stderr=subprocess.DEVNULL, timeout=8,
            ).decode("utf-8", "replace").strip().splitlines()
            if out:
                parts = out[0].split("|", 1)
                title = parts[0].strip() or "YouTube"
                dur = None
                if len(parts) > 1:
                    try:
                        dur = float(parts[1])
                    except ValueError:
                        dur = None
                return title, dur, ""
        except Exception as exc:
            last_error = str(exc)

    # Fallback ligero: oEmbed de YouTube (no necesita yt-dlp).
    try:
        api = "https://www.youtube.com/oembed?format=json&url=" + urllib.parse.quote(url, safe="")
        req = urllib.request.Request(api, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=6) as resp:
            data = json.loads(resp.read().decode("utf-8", "replace"))
        return data.get("title") or "YouTube", None, ""
    except Exception:
        # Último recurso: usar el propio ID/URL como nombre para no perder la pista.
        name = re.sub(r"^.*(?:v=|youtu\.be/|shorts/)", "", url).split("&")[0][:60] or "YouTube"
        return f"YouTube: {name}", None, "sin conexión (guardada igualmente)"


def download_audio(track: Track, dest_dir: Path, fixed_name: str | None = None) -> Path | None:
    """Descarga el audio a dest_dir y devuelve el archivo creado."""
    binary = ytdlp_bin()
    if not binary or not track.url:
        state["error"] = "yt-dlp no está instalado; no se puede descargar"
        return None
    dest_dir.mkdir(parents=True, exist_ok=True)
    base = fixed_name or safe_name(track.name)
    template = str(dest_dir / f"{base}.%(ext)s")
    try:
        subprocess.run(
            [binary, "--no-warnings", "--format", "bestaudio/best",
             "-x", "--audio-format", "mp3", "--audio-quality", "0",
             "--postprocessor-args", "ffmpeg:-hide_banner -loglevel error",
             "-o", template, track.url],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=300, check=True,
        )
    except Exception as exc:
        state["error"] = f"Error al descargar: {exc}"
        return None
    matches = sorted(dest_dir.glob(base + ".*"), key=lambda p: p.stat().st_mtime)
    return matches[-1] if matches else None


def cached_audio(track: Track) -> Path | None:
    if track.cache_path and track.cache_path.exists():
        return track.cache_path
    key = hashlib.md5(track.url.encode()).hexdigest()[:12]
    URL_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    found = download_audio(track, URL_CACHE_DIR, fixed_name=key)
    if found:
        track.cache_path = found
    return found


def eq_filter_string() -> str:
    """Cadena de filtros ffmpeg para los 10 bandas del ecualizador."""
    parts = []
    for label, level in zip(EQ_LABELS, EQ_LEVELS):
        db = (level - 0.5) * 24.0
        parts.append(f"equalizer=f={label.lower()}:t=q:w=1:g={db:.1f}")
    return ",".join(parts)


def eq_signature() -> str:
    raw = repr((state["eq_on"], [round(v, 3) for v in EQ_LEVELS]))
    return hashlib.md5(raw.encode()).hexdigest()[:10]


def eq_cache_file(source: Path) -> Path:
    cache = URL_CACHE_DIR / "eq"
    cache.mkdir(parents=True, exist_ok=True)
    return cache / f"{eq_signature()}.mp3"


def eq_cached_source(source: Path) -> Path | None:
    if not state["eq_on"] or not source:
        return None
    out = eq_cache_file(source)
    return out if out.exists() else None


def build_eq_file(source: Path) -> Path | None:
    """Genera el archivo con EQ (llamado desde un hilo, nunca desde la UI)."""
    out = eq_cache_file(source)
    if out.exists():
        return out
    ffmpeg = APP_BIN / "ffmpeg"
    binary = str(ffmpeg) if ffmpeg.exists() else "ffmpeg"
    try:
        subprocess.run(
            [binary, "-y", "-hide_banner", "-loglevel", "error", "-i", str(source),
             "-af", eq_filter_string(), "-c:a", "libmp3lame", "-q:a", "2",
             str(out)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=300, check=True,
        )
        return out if out.exists() else None
    except Exception:
        return None


def schedule_eq_processing(source: Path, index: int) -> None:
    """Procesa el EQ en segundo plano y cambia la pista sin congelar la UI."""
    if not state["eq_on"] or not source:
        return
    if eq_cache_file(source).exists():
        return
    state["eq_generation"] += 1
    generation = state["eq_generation"]
    set_message("Aplicando ecualizador…")

    def worker() -> None:
        result = build_eq_file(source)
        # Si cambiaron los faders o la canción, este resultado ya no sirve.
        if generation != state["eq_generation"] or state["index"] != index:
            return
        if result:
            # No tocar pygame desde el hilo: el bucle principal aplica el cambio.
            state["eq_pending"] = (generation, index, result)

    threading.Thread(target=worker, daemon=True).start()


def refresh_playback_eq() -> None:
    """Actualiza el filtro en caliente: es instantáneo y no toca la reproducción."""
    update_eq_fir()
    set_message("EQ: " + (PRESET_NAMES[state["preset_index"]] if state["eq_on"] else "OFF"))


def music_elapsed() -> float:
    if not state["playing"]:
        return 0.0
    if state["paused"]:
        return state["paused_elapsed"]
    return state["start_offset"] + (time.time() - state["play_started"])


def stop_sound() -> None:
    channel = state.get("channel")
    if channel:
        channel.stop()
    state["channel"] = None


def play_pcm(start: float = 0.0) -> None:
    """Reproduce el PCM cargado desde un punto dado (permite buscar)."""
    pcm = state.get("pcm")
    if pcm is None:
        return
    rate = max(1, AUDIO_INFO["rate"])
    frame = int(start * rate)
    frame = max(0, min(frame, len(pcm) - 1))
    sound = pygame.sndarray.make_sound(np.ascontiguousarray(pcm[frame:]))
    channel = state.get("channel") or pygame.mixer.find_channel()
    if channel is None:
        return
    channel.stop()
    channel.play(sound)
    channel.set_volume(state["volume"])
    state["channel"] = channel
    state["start_offset"] = start
    state["play_started"] = time.time()
    state["paused_elapsed"] = start


def play(index: int, start: float = 0.0) -> None:
    if not 0 <= index < len(state["playlist"]):
        return
    track = state["playlist"][index]
    source = track.path
    if track.is_url:
        set_message(f"Descargando audio: {track.name}")
        source = cached_audio(track)
        if source is None:
            return
    state["current_source"] = str(source)

    try:
        loaded = pygame.mixer.Sound(str(source))
        state["pcm"] = pygame.sndarray.array(loaded)
    except Exception as exc:
        state["error"] = f"No se pudo reproducir: {exc}"
        state["playing"] = False
        return
    state["index"] = index
    state["playing"] = True
    state["paused"] = False
    state["error"] = ""
    state["started_at"] = time.time()
    play_pcm(start)


def stop() -> None:
    stop_sound()
    state["playing"] = False
    state["paused"] = False


def toggle_pause() -> None:
    if not state["playing"]:
        return
    if state["paused"]:
        play_pcm(state["paused_elapsed"])
        state["paused"] = False
    else:
        state["paused_elapsed"] = music_elapsed()
        channel = state.get("channel")
        if channel:
            channel.pause()
        state["paused"] = True


def next_track() -> None:
    if state["shuffle"] and len(state["playlist"]) > 1:
        import random
        idx = state["index"]
        while idx == state["index"]:
            idx = random.randrange(len(state["playlist"]))
        play(idx)
    else:
        play((state["index"] + 1) % len(state["playlist"]))


def prev_track() -> None:
    play((state["index"] - 1) % len(state["playlist"]))


def set_volume(value: float) -> None:
    state["volume"] = max(0.0, min(1.0, value))
    channel = state.get("channel")
    if channel:
        channel.set_volume(state["volume"])


def change_volume(delta: float) -> None:
    set_volume(state["volume"] + delta)


def toggle_mute() -> None:
    if state["volume"] > 0:
        state["prev_volume"] = state["volume"]
        set_volume(0.0)
    else:
        set_volume(state["prev_volume"] or 0.5)


def reload_playlist() -> None:
    tracks = tracks_from_folder()
    if tracks:
        state["playlist"] = tracks
        state["index"] = min(state["index"], len(tracks) - 1)
        state["error"] = ""


def duration_of(track: Track) -> float | None:
    if track.duration is not None:
        return track.duration
    key = track.path or track.url
    if key in DURATION_CACHE:
        return DURATION_CACHE[key]
    dur = None
    if track.path and track.path.suffix.lower() == ".wav":
        try:
            import wave
            with wave.open(str(track.path)) as w:
                dur = w.getnframes() / float(w.getframerate())
        except Exception:
            pass
    if dur is None and track.path:
        try:
            from mutagen import File as MutagenFile
            tag = MutagenFile(str(track.path))
            if tag is not None:
                dur = float(tag.info.length)
        except Exception:
            pass
    if dur is None and track.path:
        try:
            out = subprocess.check_output(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=nw=1:nk=1", str(track.path)],
                stderr=subprocess.DEVNULL, timeout=2,
            )
            dur = float(out.decode().strip())
        except Exception:
            pass
    DURATION_CACHE[key] = dur
    track.duration = dur
    return dur


def fmt_time(seconds: float | None, force: bool = False) -> str:
    if seconds is None:
        return "--:--"
    seconds = max(0, int(seconds))
    return f"{seconds // 60}:{seconds % 60:02d}"


def track_title(track: Track) -> str:
    return track.name


# ----------------------------------------------------------------------
# Primitivas de dibujo
# ----------------------------------------------------------------------
def put(stdscr, y: int, x: int, text: str, attr: int = 0) -> None:
    max_y, max_x = stdscr.getmaxyx()
    if y < 0 or y >= max_y or x < 0 or x >= max_x:
        return
    try:
        stdscr.addstr(y, x, text[: max_x - x], attr)
    except curses.error:
        pass


def truncate(text: str, width: int) -> str:
    if width <= 0:
        return ""
    return text if len(text) <= width else text[: width - 1] + "…"


def frame(stdscr, y: int, x: int, h: int, w: int, attr: int) -> None:
    if h < 2 or w < 2:
        return
    put(stdscr, y, x, "╔" + "═" * (w - 2) + "╗", attr)
    for r in range(y + 1, y + h - 1):
        put(stdscr, r, x, "║", attr)
        put(stdscr, r, x + w - 1, "║", attr)
    put(stdscr, y + h - 1, x, "╚" + "═" * (w - 2) + "╝", attr)


def title_bar(stdscr, y: int, x: int, w: int, title: str, pair: int | None = None) -> None:
    if pair is None:
        pair = PAIR_TITLE1
    tag = f"╣ {title} ╠"
    left = max(0, (w - len(tag)) // 2)
    bar = "═" * left + tag + "═" * max(0, w - left - len(tag))
    put(stdscr, y, x, bar[:w], pair)
    if w >= 12:
        put(stdscr, y, x + w - 8, "[_][X]", pair)


def button(stdscr, y: int, x: int, label: str, active: bool = False,
           attr: int | None = None) -> int:
    text = f"[{label}]"
    if attr is None:
        attr = PAIR_BTN_ON if active else PAIR_BTN_OFF
    put(stdscr, y, x, text, attr)
    return len(text) + 1


def big_text(stdscr, y: int, x: int, text: str, attr: int) -> None:
    for i, ch in enumerate(text.upper()):
        glyph = DIGITS.get(ch, ["   "] * 5)
        for r, row in enumerate(glyph):
            put(stdscr, y + r, x + i * 4, row, attr)


def draw_scope(stdscr, y: int, x: int, w: int, level: float, now: float,
               attr: int | None = None) -> None:
    """Onda de barras con color sólido (verde / cian)."""
    if attr is None:
        attr = PAIR_GREEN
    chars = " ▂▃▄▅▆▇█"
    for i in range(w):
        v = level * (
            0.35 + 0.45 * abs(math.sin(now * 4.5 + i * 0.8))
            + 0.20 * abs(math.sin(now * 8.0 + i * 1.7))
        )
        put(stdscr, y, x + i, chars[min(len(chars) - 1, int(v * len(chars)))], attr)


PAIR_GREEN = 0
PAIR_YELLOW = 0
PAIR_WHITE = 0
PAIR_CYAN = 0
PAIR_MAGENTA = 0
PAIR_RED = 0
PAIR_BLUE = 0
PAIR_TITLE1 = 0
PAIR_TITLE2 = 0
PAIR_TITLE3 = 0
PAIR_BTN_ON = 0
PAIR_BTN_ON2 = 0
PAIR_BTN_OFF = 0
PAIR_FRAME1 = 0
PAIR_FRAME2 = 0
PAIR_FRAME3 = 0
PAIR_MODAL_BG = 0
EQ_COLORS = []


def init_colors() -> None:
    global PAIR_GREEN, PAIR_YELLOW, PAIR_WHITE, PAIR_CYAN, PAIR_MAGENTA
    global PAIR_RED, PAIR_BLUE, PAIR_TITLE1, PAIR_TITLE2, PAIR_TITLE3
    global PAIR_BTN_ON, PAIR_BTN_ON2, PAIR_BTN_OFF
    global PAIR_FRAME1, PAIR_FRAME2, PAIR_FRAME3, PAIR_MODAL_BG, EQ_COLORS
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(1, curses.COLOR_GREEN, curses.COLOR_BLACK)
    curses.init_pair(2, curses.COLOR_YELLOW, curses.COLOR_BLACK)
    curses.init_pair(3, curses.COLOR_WHITE, curses.COLOR_BLACK)
    curses.init_pair(4, curses.COLOR_CYAN, curses.COLOR_BLACK)
    curses.init_pair(5, curses.COLOR_MAGENTA, curses.COLOR_BLACK)
    curses.init_pair(6, curses.COLOR_RED, curses.COLOR_BLACK)
    curses.init_pair(7, curses.COLOR_BLUE, curses.COLOR_BLACK)
    curses.init_pair(8, curses.COLOR_WHITE, curses.COLOR_MAGENTA)
    curses.init_pair(9, curses.COLOR_WHITE, curses.COLOR_GREEN)
    curses.init_pair(10, curses.COLOR_WHITE, curses.COLOR_RED)
    curses.init_pair(11, curses.COLOR_BLACK, curses.COLOR_CYAN)
    curses.init_pair(12, curses.COLOR_BLACK, curses.COLOR_YELLOW)
    curses.init_pair(13, curses.COLOR_BLACK, curses.COLOR_GREEN)
    curses.init_pair(14, curses.COLOR_BLACK, curses.COLOR_MAGENTA)
    curses.init_pair(15, curses.COLOR_BLACK, curses.COLOR_WHITE)

    cp = curses.color_pair
    PAIR_GREEN = cp(1) | curses.A_BOLD
    PAIR_YELLOW = cp(2)
    PAIR_WHITE = cp(3)
    PAIR_CYAN = cp(4)
    PAIR_MAGENTA = cp(5)
    PAIR_RED = cp(6)
    PAIR_BLUE = cp(7)
    PAIR_TITLE1 = cp(8) | curses.A_BOLD
    PAIR_TITLE2 = cp(9) | curses.A_BOLD
    PAIR_TITLE3 = cp(10) | curses.A_BOLD
    PAIR_BTN_ON = cp(11)
    PAIR_BTN_ON2 = cp(12)
    PAIR_BTN_OFF = cp(3)
    PAIR_FRAME1 = cp(7) | curses.A_BOLD
    PAIR_FRAME2 = cp(4) | curses.A_BOLD
    PAIR_FRAME3 = cp(5) | curses.A_BOLD
    PAIR_MODAL_BG = cp(15)
    EQ_COLORS = [cp(2), cp(4), cp(5), cp(1), cp(6)]


# ----------------------------------------------------------------------
# Ventanas
# ----------------------------------------------------------------------
def draw_player(stdscr, y: int, x: int, h: int, w: int, now: float) -> None:
    title_bar(stdscr, y, x, w, "TERMINAL MP3 PLAYER", PAIR_TITLE1)
    frame(stdscr, y + 1, x, h - 1, w, PAIR_FRAME1)

    lcd_y, lcd_x = y + 2, x + 2
    lcd_h, lcd_w = 7, max(16, w - 4)
    LAYOUT["lcd"] = (lcd_y, lcd_x, lcd_h, lcd_w)
    frame(stdscr, lcd_y, lcd_x, lcd_h, lcd_w, PAIR_GREEN)

    elapsed = music_elapsed()
    if elapsed < 0:
        elapsed = 0.0
    big_text(stdscr, lcd_y + 1, lcd_x + 2, fmt_time(elapsed), PAIR_CYAN)

    idx = state["index"]
    path = state["playlist"][idx]
    right_x_lcd = lcd_x + 20
    right_w_lcd = max(0, lcd_w - 21)
    put(stdscr, lcd_y + 1, right_x_lcd,
        truncate(f"{idx + 1}. {track_title(path)}", right_w_lcd), PAIR_GREEN)
    rate_k = AUDIO_INFO["rate"] // 1000
    bits = abs(AUDIO_INFO["sample"])
    put(stdscr, lcd_y + 2, right_x_lcd,
        truncate(f"{rate_k} kHz   {bits} bit   stereo", right_w_lcd - 8), PAIR_WHITE)
    put(stdscr, lcd_y + 2, lcd_x + lcd_w - 9, "stereo", PAIR_GREEN)

    level = state["volume"] if state["playing"] and not state["paused"] else 0.0
    scope_w = max(0, right_w_lcd - 1)
    draw_scope(stdscr, lcd_y + 4, right_x_lcd, scope_w, level, now, PAIR_GREEN)
    draw_scope(stdscr, lcd_y + 5, right_x_lcd, scope_w, level * 0.8, now + 0.4, PAIR_CYAN)

    put(stdscr, y + h - 6, x + 1, "─" * max(0, w - 2), PAIR_MAGENTA)
    if state["ui_message"] and now < state["message_until"]:
        put(stdscr, y + h - 4, x + 2, truncate(state["ui_message"], w - 4), PAIR_YELLOW)
    else:
        put(stdscr, y + h - 4, x + w - 12, "MOUSE ON", PAIR_CYAN)

    # Barra de volumen / color
    bar_y = y + h - 5
    bar_x = x + 2
    bar_w = max(4, w - 6)
    LAYOUT["volume"] = (bar_y, bar_x, bar_w)
    filled = int(state["volume"] * bar_w)
    put(stdscr, bar_y, bar_x, "━" * filled, PAIR_YELLOW)
    put(stdscr, bar_y, bar_x + filled, "─" * (bar_w - filled), PAIR_BLUE)
    put(stdscr, bar_y, bar_x + min(bar_w - 1, filled), "▣", PAIR_RED)

    # Botones del transporte
    by = y + h - 3
    bx = x + 2
    btns = [
        ("|<", False, "prev"), (">", state["playing"] and not state["paused"], "play"),
        ("||", state["paused"], "pause"), ("[]", not state["playing"], "stop"),
        (">|", False, "next"), ("^", False, "reload"),
        ("SHUFFLE", state["shuffle"], "shuffle"), ("=", state["volume"] == 0, "mute"),
        ("EQ", state["show_eq"], "eq_window"),
        ("PL", state["show_playlist"], "playlist_window"),
    ]
    LAYOUT["player_buttons"] = []
    btn_colors = [PAIR_YELLOW, PAIR_CYAN, PAIR_MAGENTA, PAIR_GREEN,
                  PAIR_RED, PAIR_BLUE, PAIR_YELLOW, PAIR_CYAN,
                  PAIR_GREEN, PAIR_MAGENTA]
    for i, (label, active, action) in enumerate(btns):
        if bx + len(label) + 2 > x + w - 2:
            break
        width = button(stdscr, by, bx, label, active,
                       PAIR_BTN_ON2 if active else btn_colors[i % len(btn_colors)])
        LAYOUT["player_buttons"].append((bx, by, len(label) + 2, action))
        bx += width


def draw_equalizer(stdscr, y: int, x: int, h: int, w: int) -> None:
    title_bar(stdscr, y, x, w, "TERMINAL MP3 PLAYER - EQ", PAIR_TITLE2)
    frame(stdscr, y + 1, x, h - 1, w, PAIR_FRAME2)

    LAYOUT["eq_buttons"] = []
    LAYOUT["preset_items"] = []
    bx = x + 2
    for label, active, action, color in (
        ("ON", state["eq_on"], "eq", PAIR_BTN_ON2 if state["eq_on"] else PAIR_WHITE),
        ("AUTO", state["eq_auto"], "auto", PAIR_BTN_ON if state["eq_auto"] else PAIR_MAGENTA),
    ):
        width = button(stdscr, y + 2, bx, label, active, color)
        LAYOUT["eq_buttons"].append((bx, y + 2, len(label) + 2, action))
        bx += width

    px = x + w - 12
    button(stdscr, y + 2, px, "PRESETS", state["preset_menu"],
           PAIR_CYAN if state["preset_menu"] else PAIR_BTN_OFF)
    LAYOUT["eq_buttons"].append((px, y + 2, 10, "presets"))

    top = y + 5
    bottom = y + h - 5
    if bottom - top < 2:
        return
    sh = bottom - top + 1

    put(stdscr, top - 2, x + 1, "+12 dB", PAIR_CYAN)
    put(stdscr, top - 2, x + w - 8, "0 dB", PAIR_CYAN)
    put(stdscr, top - 1, x + 1, "-12 dB", PAIR_MAGENTA)
    put(stdscr, top - 1, x + 9, "─" * max(0, w - 12), PAIR_YELLOW)

    count = 11
    step = max(4, (w - 12) // count)
    x0 = x + 9
    labels = ["PRE"] + EQ_LABELS
    LAYOUT["eq_sliders"] = []
    for i in range(count):
        sx = x0 + i * step
        if sx >= x + w - 2:
            break
        LAYOUT["eq_sliders"].append((sx, top, sh, i))
        level = state["volume"] if i == 0 else EQ_LEVELS[i - 1]
        filled = max(1, int(level * sh))
        color = EQ_COLORS[i % len(EQ_COLORS)] if state["eq_on"] else PAIR_BLUE
        for r in range(sh):
            put(stdscr, top + r, sx, "█" if r >= sh - filled else "░", color)
        put(stdscr, top - 1, sx, "+", color)
        put(stdscr, bottom + 1, sx, "-", color)
        # El pulador gris sigue a la barra (parte superior del relleno).
        handle = max(top, min(top + sh - 1, top + sh - filled))
        put(stdscr, handle, sx, "▒", PAIR_WHITE)
        put(stdscr, bottom + 2, sx - 1, truncate(labels[i], step - 1), PAIR_CYAN)

    if state["preset_menu"]:
        mw = min(28, w - 16)
        mh = len(PRESET_NAMES) + 3
        mx = x + 12
        my = y + 4
        title_bar(stdscr, my, mx, mw, "PRESETS", PAIR_TITLE3)
        frame(stdscr, my + 1, mx, mh - 1, mw, PAIR_FRAME3)
        for i, name in enumerate(PRESET_NAMES):
            row = my + 2 + i
            text = f"{i + 1}. {name}"
            active = i == state["preset_index"]
            put(stdscr, row, mx + 2, text,
                PAIR_BTN_ON2 | curses.A_REVERSE if active else PAIR_GREEN)
            LAYOUT["preset_items"].append((mx + 2, row, len(text) + 1, i))


def draw_playlist(stdscr, y: int, x: int, h: int, w: int, now: float) -> None:
    title_bar(stdscr, y, x, w, "TERMINAL MP3 PLAYER - PLAYLIST", PAIR_TITLE3)
    frame(stdscr, y + 1, x, h - 1, w, PAIR_FRAME3)

    list_top = y + 2
    list_h = max(1, h - 6)
    inner_w = w - 5
    idx = state["index"]

    if idx < state["offset"]:
        state["offset"] = idx
    elif idx >= state["offset"] + list_h:
        state["offset"] = idx - list_h + 1

    LAYOUT["playlist_rows"] = []
    LAYOUT["download_icons"] = []
    for row in range(list_h):
        pos = state["offset"] + row
        if pos >= len(state["playlist"]):
            break
        LAYOUT["playlist_rows"].append((pos, list_top + row, x + 2, inner_w))
        path = state["playlist"][pos]
        dur = fmt_time(duration_of(path))
        text = f"{pos + 1:2d}. {track_title(path)}"
        row_colors = [PAIR_GREEN, PAIR_CYAN, PAIR_MAGENTA, PAIR_YELLOW, PAIR_WHITE]
        if pos == idx and state["playing"]:
            attr = PAIR_BTN_ON2 | curses.A_REVERSE
        else:
            attr = row_colors[pos % len(row_colors)]
        icon_col = x + w - len(dur) - 5
        text_w = inner_w - len(dur) - (4 if path.is_url else 2)
        put(stdscr, list_top + row, x + 2, truncate(text, text_w), attr)
        put(stdscr, list_top + row, x + w - len(dur) - 3, dur, PAIR_CYAN)
        if path.is_url:
            put(stdscr, list_top + row, icon_col, "↓", PAIR_YELLOW | curses.A_BOLD)
            LAYOUT["download_icons"].append((pos, list_top + row, icon_col))

    # Scrollbar
    sx = x + w - 2
    for r in range(list_h):
        put(stdscr, list_top + r, sx, "░", PAIR_BLUE)
    total = len(state["playlist"])
    if total > list_h:
        thumb = min(list_h, max(1, int(list_h * list_h / total)))
        pos = int((state["offset"] / max(1, total - list_h)) * max(0, list_h - thumb))
        for r in range(thumb):
            put(stdscr, list_top + pos + r, sx, "█", PAIR_YELLOW)

    # Parte inferior
    by = y + h - 3
    bx = x + 2
    LAYOUT["playlist_buttons"] = []
    pl_colors = [PAIR_GREEN, PAIR_RED, PAIR_CYAN, PAIR_MAGENTA,
                 PAIR_YELLOW, PAIR_BLUE, PAIR_WHITE]
    for i, (label, action) in enumerate((
        ("ADD", "reload"), ("REM", "remove"), ("SEL", "play"), ("MISC", "shuffle"),
        ("URL", "url"), ("LIST", "lists"), ("CRED", "credits"),
    )):
        width = button(stdscr, by, bx, label, False, pl_colors[i % len(pl_colors)])
        LAYOUT["playlist_buttons"].append((bx, by, len(label) + 2, action))
        bx += width

    elapsed = music_elapsed()
    total_time = sum(d or 0 for d in (duration_of(p) for p in state["playlist"]))
    clock = f"{fmt_time(elapsed)}/{fmt_time(total_time)}+"
    put(stdscr, by, x + w - len(clock) - 3, clock, PAIR_YELLOW)

    tx = x + 2
    ty = y + h - 2
    LAYOUT["transport"] = []
    move_colors = [PAIR_MAGENTA, PAIR_YELLOW, PAIR_CYAN, PAIR_GREEN]
    for i, (label, action) in enumerate((
        ("◄◄", "prev"), ("◄", "prev"), ("►", "next"), ("►►", "next"),
    )):
        width = button(stdscr, tx, ty, label, False, move_colors[i % len(move_colors)])
        LAYOUT["transport"].append((tx, ty, len(label) + 2, action))
        tx += width
    put(stdscr, ty, x + w - 12, fmt_time(elapsed), PAIR_YELLOW)


# ----------------------------------------------------------------------
# Ratón
# ----------------------------------------------------------------------
def remove_selected() -> None:
    if len(state["playlist"]) <= 1:
        return
    idx = state["index"]
    stop()
    del state["playlist"][idx]
    state["index"] = min(idx, len(state["playlist"]) - 1)


def set_message(text: str, seconds: float = 10.0) -> None:
    state["ui_message"] = text
    state["message_until"] = time.time() + seconds


def playlist_file(name: str) -> Path:
    PLAYLISTS_DIR.mkdir(parents=True, exist_ok=True)
    return PLAYLISTS_DIR / f"{safe_name(name)}.json"


def save_playlist(name: str) -> None:
    path = playlist_file(name)
    data = {
        "name": name,
        "tracks": [t.to_dict() for t in state["playlist"]],
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    state["current_playlist"] = name
    set_message(f"Lista guardada: {name}")


def load_saved_playlist(name: str) -> None:
    path = playlist_file(name)
    if not path.exists():
        save_playlist(name)
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        tracks = [Track.from_dict(d) for d in data.get("tracks", [])]
        if not tracks:
            return
        state["playlist"] = tracks
        state["index"] = 0
        state["current_playlist"] = data.get("name", name)
        set_message(f"Lista cargada: {state['current_playlist']}")
    except Exception as exc:
        set_message(f"Error al cargar: {exc}")


def saved_playlist_names() -> list[str]:
    PLAYLISTS_DIR.mkdir(parents=True, exist_ok=True)
    names = []
    for p in sorted(PLAYLISTS_DIR.glob("*.json")):
        try:
            names.append(json.loads(p.read_text(encoding="utf-8")).get("name", p.stem))
        except Exception:
            names.append(p.stem)
    return names


def add_youtube_url(url: str) -> None:
    url = url.strip()
    if not url:
        return
    if "youtube.com" not in url and "youtu.be" not in url:
        set_message("Solo se aceptan URLs de YouTube / YouTube Music")
        return
    set_message("Consultando título…")
    title, dur, err = fetch_url_info(url)
    if not title:
        set_message(f"Error: {err}")
        return
    track = Track(title, url=url, duration=dur)
    state["playlist"].append(track)
    state["index"] = len(state["playlist"]) - 1
    set_message(f"Añadida: {title}" + (" (sin conexión)" if err else ""))
    save_playlist(state["current_playlist"])


def download_from_icon(index: int) -> None:
    """Descarga en segundo plano la pista URL y la vuelve local."""
    if not 0 <= index < len(state["playlist"]):
        return
    track = state["playlist"][index]
    if not track.is_url:
        return
    set_message(f"Descargando: {track.name}")

    def worker() -> None:
        folder = default_music_dir()
        found = download_audio(track, folder)
        if found:
            track.path = found
            track.url = None
            track.cache_path = None
            track.name = found.stem.replace("_", " ").strip()
            save_playlist(state["current_playlist"])
            set_message(f"Descargada: {track.name}")
        else:
            set_message(state["error"] or "No se pudo descargar")

    threading.Thread(target=worker, daemon=True).start()


def prompt_download(track: Track) -> None:
    state["pending_download"] = track
    state["ui_mode"] = "download"
    state["ui_input"] = ""


def finish_download(accept: bool) -> None:
    track = state["pending_download"]
    state["pending_download"] = None
    state["ui_mode"] = None
    if accept and track:
        folder = default_music_dir()
        found = download_audio(track, folder)
        if found:
            track.path = found
            track.url = None
            track.name = found.stem.replace("_", " ").strip()
            set_message(f"Descargada en {folder}")
            save_playlist(state["current_playlist"])
        else:
            set_message(state["error"] or "No se pudo descargar")
    next_track()


def apply_preset(index: int) -> None:
    name = PRESET_NAMES[index % len(PRESET_NAMES)]
    EQ_LEVELS[:] = PRESETS[name][:]
    state["preset_index"] = index % len(PRESET_NAMES)
    state["preset_menu"] = False
    set_message(f"EQ: {name}")
    refresh_playback_eq()


def cycle_preset() -> None:
    apply_preset(state["preset_index"] + 1)


def toggle_eq() -> None:
    state["eq_on"] = not state["eq_on"]
    state["preset_menu"] = False
    set_message("EQ activado" if state["eq_on"] else "EQ desactivado")
    refresh_playback_eq()


def toggle_auto() -> None:
    state["eq_auto"] = not state["eq_auto"]
    state["last_auto"] = time.time()
    state["preset_menu"] = False


def toggle_preset_menu() -> None:
    state["preset_menu"] = not state["preset_menu"]


def toggle_eq_window() -> None:
    state["show_eq"] = not state["show_eq"]
    state["preset_menu"] = False
    request_resize()


def toggle_playlist_window() -> None:
    state["show_playlist"] = not state["show_playlist"]
    state["preset_menu"] = False
    request_resize()


ACTIONS = {
    "prev": prev_track,
    "next": next_track,
    "play": lambda: play(state["index"]),
    "pause": toggle_pause,
    "stop": stop,
    "reload": reload_playlist,
    "remove": remove_selected,
    "shuffle": lambda: state.__setitem__("shuffle", not state["shuffle"]),
    "mute": toggle_mute,
    "eq": toggle_eq,
    "auto": toggle_auto,
    "presets": toggle_preset_menu,
    "eq_window": toggle_eq_window,
    "playlist_window": toggle_playlist_window,
    "url": lambda: open_input("url"),
    "lists": lambda: open_input("lists"),
    "credits": lambda: open_input("credits"),
}


def open_input(mode: str) -> None:
    state["ui_mode"] = mode
    state["ui_input"] = ""
    state["ui_message"] = ""


def find_mouse_target(mx: int, my: int):
    """Devuelve (tipo, dato) para la celda bajo el cursor, o None."""
    vol = LAYOUT["volume"]
    if vol and my == vol[0] and vol[1] <= mx < vol[1] + vol[2]:
        return ("volume", vol)

    lcd = LAYOUT["lcd"]
    if lcd and lcd[0] <= my < lcd[0] + lcd[2] and lcd[1] <= mx < lcd[1] + lcd[3]:
        return ("action", "play")

    for bx, by, bw, action in LAYOUT["player_buttons"]:
        if by == my and bx <= mx < bx + bw:
            return ("action", action)

    if state["preset_menu"]:
        for bx, by, bw, idx in LAYOUT["preset_items"]:
            if by == my and bx <= mx < bx + bw:
                return ("preset", idx)
        return ("action", "presets")

    for bx, by, bw, action in LAYOUT["eq_buttons"]:
        if by == my and bx <= mx < bx + bw:
            return ("action", action)

    for sx, top, sh, i in LAYOUT["eq_sliders"]:
        if abs(mx - sx) <= 1 and top <= my < top + sh:
            return ("eq", (sx, top, sh, i))

    for idx, iy, ix in LAYOUT["download_icons"]:
        if iy == my and ix <= mx < ix + 1:
            return ("download", idx)

    for idx, ry, rx, rw in LAYOUT["playlist_rows"]:
        if ry == my and rx <= mx < rx + rw:
            return ("select", idx)

    for bx, by, bw, action in LAYOUT["playlist_buttons"] + LAYOUT["transport"]:
        if by == my and bx <= mx < bx + bw:
            return ("action", action)

    return None


def apply_mouse_target(target, mx: int, my: int) -> None:
    kind, data = target
    if kind == "volume":
        _, bar_x, bar_w = data
        set_volume((mx - bar_x + 0.5) / bar_w)
    elif kind == "eq":
        sx, top, sh, i = data
        value = 1.0 - (my - top) / max(1, sh - 1)
        if i == 0:
            set_volume(value)
        else:
            EQ_LEVELS[i - 1] = max(0.0, min(1.0, value))
            refresh_playback_eq()
    elif kind == "select":
        state["index"] = data
        play(data)
    elif kind == "preset":
        apply_preset(data)
    elif kind == "download":
        download_from_icon(data)
    elif kind == "action":
        ACTIONS.get(data, lambda: None)()


def handle_mouse(mx: int, my: int, bstate: int) -> None:
    pressed = bool(bstate & (curses.BUTTON1_PRESSED | curses.BUTTON1_CLICKED))
    released = bool(bstate & curses.BUTTON1_RELEASED)
    motion = bool(bstate & curses.REPORT_MOUSE_POSITION)

    if released:
        DRAG["target"] = None
        return
    target = find_mouse_target(mx, my)
    if pressed:
        if target is None:
            return
        DRAG["target"] = target if target[0] in ("volume", "eq") else None
    elif not (motion and DRAG["target"]):
        return
    else:
        target = DRAG["target"]
    apply_mouse_target(target, mx, my)


# ----------------------------------------------------------------------
# Diálogos (URL / listas / descarga)
# ----------------------------------------------------------------------
def draw_modal(stdscr, max_y: int, max_x: int) -> None:
    mode = state["ui_mode"]
    if not mode:
        return
    w = min(max_x - 6, 76)
    h = 11 if mode == "credits" else (9 if mode != "lists" else min(max_y - 4, 14))
    y = max(0, (max_y - h) // 2)
    x = max(0, (max_x - w) // 2)

    if mode == "url":
        title, hint = "AÑADIR URL DE YOUTUBE", "Pega la URL y pulsa Enter · Esc cancela"
    elif mode == "lists":
        title, hint = "LISTAS GUARDADAS", "Enter=cargar/guardar · Supr=borrar · Esc=cerrar"
    elif mode == "credits":
        title, hint = "CRÉDITOS Y LICENCIA", "Pulsa cualquier tecla para cerrar"
    else:
        title, hint = "DESCARGAR AL TERMINAR", "¿Guardar en la carpeta de música? [s/N]"

    # Fondo sólido gris para que el diálogo se distinga del resto.
    for r in range(h):
        put(stdscr, y + r, x, " " * w, PAIR_MODAL_BG)

    title_bar(stdscr, y, x, w, title, PAIR_TITLE3)
    frame(stdscr, y + 1, x, h - 1, w, PAIR_FRAME3)
    put(stdscr, y + 2, x + 2, hint, PAIR_WHITE)
    if state["ui_message"]:
        put(stdscr, y + 3, x + 2, truncate(state["ui_message"], w - 4), PAIR_YELLOW)

    if mode == "lists":
        names = saved_playlist_names()
        for i, name in enumerate(names[: h - 6]):
            mark = "▶" if name == state["current_playlist"] else " "
            put(stdscr, y + 4 + i, x + 2, f"{mark} {i + 1}. {name}", PAIR_GREEN)
    if mode == "credits":
        lines = [
            "Power By Agdala 2026",
            "",
            "Mensaje: ¡Gracias por usar TERMINAL MP3 PLAYER!",
            "Envíame un correo: agdala.sv@gmail.com",
            "",
            "Licencia de uso GRATUITA.",
            "Prohibida su venta.",
        ]
        for i, line in enumerate(lines):
            put(stdscr, y + 3 + i, x + 2, line,
                PAIR_MODAL_BG | curses.A_BOLD if i in (0, 5, 6) else PAIR_MODAL_BG)
    if mode in ("url", "lists"):
        put(stdscr, y + h - 2, x + 2, "> " + state["ui_input"] + "▌", PAIR_MODAL_BG)


def handle_modal_key(key: int) -> None:
    mode = state["ui_mode"]
    if mode == "credits":
        state["ui_mode"] = None
        return
    if mode == "download":
        if key in (ord("s"), ord("S")):
            finish_download(True)
        elif key in (10, 13, ord("n"), ord("N"), 27, ord("q"), ord("Q")):
            finish_download(False)
        return

    if key == 27:
        state["ui_mode"] = None
        return
    if key in (10, 13, getattr(curses, "KEY_ENTER", -1)):
        text = state["ui_input"].strip()
        if mode == "url" and text:
            add_youtube_url(text)
        elif mode == "lists" and text:
            load_saved_playlist(text)
        state["ui_mode"] = None
        return
    if key in (curses.KEY_BACKSPACE, 127, 8):
        state["ui_input"] = state["ui_input"][:-1]
    elif key == getattr(curses, "KEY_DC", -1):
        names = saved_playlist_names()
        target = state["ui_input"].strip() or (names[0] if names else "")
        if target:
            playlist_file(target).unlink(missing_ok=True)
            set_message(f"Lista borrada: {target}")
            state["ui_input"] = ""
    elif 32 <= key < 127:
        state["ui_input"] += chr(key)


# ----------------------------------------------------------------------
# Bucle principal
# ----------------------------------------------------------------------
def draw(stdscr) -> None:
    curses.curs_set(0)
    stdscr.nodelay(True)
    init_colors()
    try:
        curses.mousemask(curses.ALL_MOUSE_EVENTS | curses.REPORT_MOUSE_POSITION)
        curses.mouseinterval(0)
    except (curses.error, AttributeError):
        pass
    # Desactivar bracketed paste: así un URL pegado llega como texto normal.
    try:
        sys.stdout.write("\x1b[?2004l")
        sys.stdout.flush()
    except Exception:
        pass
    enter_keys = {10, 13, getattr(curses, "KEY_ENTER", -1)}

    while not state["quit"]:
        apply_pending_resize(stdscr)
        max_y, max_x = stdscr.getmaxyx()
        stdscr.erase()

        need_rows, need_cols = desired_terminal_size()
        if max_y < need_rows or max_x < need_cols:
            put(stdscr, 0, 0,
                f"Terminal demasiado pequeña: {max_x}x{max_y} (mínimo {need_cols}x{need_rows})")
            stdscr.refresh()
            time.sleep(0.2)
            continue

        # El reproductor mantiene siempre su tamaño y posición (según la base).
        left_w = max(46, state["base_cols"] // 2 - 1)
        right_x = left_w + 2
        right_w = max_x - right_x
        main_h = 15
        eq_h = max_y - main_h - 1 if state["show_eq"] else 0

        now = time.time()
        if state["eq_auto"] and state["playing"] and now - state["last_auto"] > 5:
            cycle_preset()
            state["last_auto"] = now

        draw_player(stdscr, 0, 0, main_h, left_w, now)
        if state["show_eq"]:
            draw_equalizer(stdscr, main_h + 1, 0, eq_h, left_w)
        else:
            LAYOUT["eq_sliders"] = []
            LAYOUT["eq_buttons"] = []
            LAYOUT["preset_items"] = []
        if state["show_playlist"]:
            draw_playlist(stdscr, 0, right_x, max_y, right_w, now)
        else:
            LAYOUT["playlist_rows"] = []
            LAYOUT["playlist_buttons"] = []
            LAYOUT["transport"] = []
            LAYOUT["download_icons"] = []
        draw_modal(stdscr, max_y, max_x)
        stdscr.refresh()

        if (
            state["playing"] and not state["paused"]
            and state["ui_mode"] is None
            and now - state["started_at"] > 0.5
            and not (state.get("channel") and state["channel"].get_busy())
        ):
            next_track()

        try:
            key = stdscr.getch()
        except curses.error:
            key = -1
        if key == -1:
            time.sleep(0.03)
            continue

        if state["ui_mode"]:
            # Los eventos de ratón NO deben cerrar el diálogo (el release
            # del clic llegaba como "cualquier tecla" y lo cerraba).
            if key == curses.KEY_MOUSE:
                try:
                    _, _, _, _, bstate = curses.getmouse()
                    if (
                        state["ui_mode"] == "credits"
                        and bstate & (curses.BUTTON1_PRESSED | curses.BUTTON1_CLICKED)
                    ):
                        state["ui_mode"] = None
                except curses.error:
                    pass
                continue
            handle_modal_key(key)
            continue

        if key == curses.KEY_MOUSE:
            try:
                _, mx, my, _, bstate = curses.getmouse()
                handle_mouse(mx, my, bstate)
            except curses.error:
                pass
            continue

        if key in (ord("q"), ord("Q"), 27):
            state["quit"] = True
            stop()
        elif key == curses.KEY_UP:
            state["index"] = (state["index"] - 1) % len(state["playlist"])
        elif key == curses.KEY_DOWN:
            state["index"] = (state["index"] + 1) % len(state["playlist"])
        elif key in enter_keys:
            play(state["index"])
        elif key == ord(" "):
            toggle_pause()
        elif key == curses.KEY_LEFT:
            prev_track()
        elif key == curses.KEY_RIGHT:
            next_track()
        elif key in (ord("+"), ord("=")):
            change_volume(VOLUME_STEP)
        elif key in (ord("-"), ord("_")):
            change_volume(-VOLUME_STEP)
        elif key in (ord("s"), ord("S")):
            state["shuffle"] = not state["shuffle"]
        elif key in (ord("e"), ord("E")):
            toggle_eq_window()
        elif key in (ord("l"), ord("L")):
            toggle_playlist_window()
        elif key in (ord("p"), ord("P")):
            toggle_preset_menu()
        elif key in (ord("u"), ord("U")):
            open_input("url")
        elif key in (ord("t"), ord("T")):
            open_input("lists")
        elif key in (ord("d"), ord("D")):
            download_from_icon(state["index"])
        elif key in (ord("c"), ord("C")):
            open_input("credits")


def base_terminal_size() -> tuple[int, int]:
    spec = os.environ.get("TERMINAL_MP3_SIZE", "120x30")
    try:
        parts = spec.lower().replace("*", "x").replace(",", "x").split("x")
        cols, rows = int(parts[0]), int(parts[1])
    except (ValueError, IndexError):
        cols, rows = 120, 30
    return max(96, min(240, cols)), max(30, min(80, rows))


def set_terminal_size(rows: int, cols: int) -> None:
    os.environ["COLUMNS"] = str(cols)
    os.environ["LINES"] = str(rows)
    if os.environ.get("TMUX"):
        subprocess.run(
            ["tmux", "resize-window", "-x", str(cols), "-y", str(rows)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    elif sys.stdout.isatty():
        # CSI 8;rows;cols t -> xterm, GNOME Terminal, Konsole, Kitty, etc.
        sys.stdout.write(f"\x1b[8;{rows};{cols}t")
        sys.stdout.flush()
        time.sleep(0.05)


def desired_terminal_size() -> tuple[int, int]:
    """Tamaño según qué ventanas estén visibles."""
    cols, rows = state["base_cols"], state["base_rows"]
    if not state["show_playlist"]:
        cols = max(46, cols // 2 - 1) + 2
    if not state["show_eq"]:
        rows = 16
    return rows, cols


def request_resize() -> None:
    state["resize_pending"] = desired_terminal_size()


def apply_pending_resize(stdscr) -> None:
    pending = state.get("resize_pending")
    if not pending:
        return
    state["resize_pending"] = None
    rows, cols = pending
    set_terminal_size(rows, cols)
    try:
        curses.resizeterm(rows, cols)
    except (curses.error, AttributeError):
        pass


def auto_resize_terminal() -> tuple[int, int]:
    cols, rows = base_terminal_size()
    state["base_cols"], state["base_rows"] = cols, rows
    set_terminal_size(rows, cols)
    return cols, rows


def main() -> None:
    # Los binarios incluidos tienen prioridad sobre los del sistema.
    if APP_BIN.is_dir():
        os.environ["PATH"] = str(APP_BIN) + os.pathsep + os.environ.get("PATH", "")

    auto_resize_terminal()
    load_playlist()
    init_audio()
    try:
        curses.wrapper(draw)
    finally:
        pygame.mixer.quit()
        try:
            sys.stdout.write("\x1b[?2004h")
            sys.stdout.flush()
        except Exception:
            pass
    print("Hasta luego 👋")


if __name__ == "__main__":
    main()
