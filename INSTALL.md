# Instalación de Terminal Mp3 Player

Guía paso a paso para Linux. El proyecto incluye **`yt-dlp`, `ffmpeg` y `ffprobe`**, así que no necesitas instalarlos por separado.

---

## Opción A — Instalación global (recomendada, para todos los usuarios)

El script instala el reproductor en `/opt/terminal-mp3player` y crea los comandos en `/usr/local/bin`.

```bash
# 1) Descargar el proyecto
git clone https://github.com/agdala10/terminal-mp3player.git
cd terminal-mp3player

# 2) Instalar para todos los usuarios
sudo bash install-system.sh

# 3) Ejecutar desde cualquier terminal
terminal-mp3player
```

**Alias disponibles:** `terminal-mp3player`, `terminal-mp3-player`, `tmp3`, `winamp`, `term-winamp`.

Cada usuario guarda su música en:

```
~/Music/terminal-mp3player/
```

La carpeta se crea automáticamente la primera vez que abres el reproductor.

---

## Opción B — Ejecutar desde el proyecto (sin instalar globalmente)

```bash
cd terminal-mp3player

# 1) Crear entorno virtual
python3 -m venv .venv

# 2) Instalar dependencias (pygame + numpy)
.venv/bin/python -m pip install -r requirements.txt

# 3) Ejecutar
./run.sh
```

También puedes usar directamente:

```bash
.venv/bin/python terminalmp3.py
```

La música local se lee de `./music/`.

---

## Requisitos

| Requisito | Estado |
|-----------|--------|
| Linux con terminal UTF‑8 | Necesario |
| Python 3.10+ | Necesario |
| `pygame` y `numpy` | Se instalan con `pip` |
| `yt-dlp`, `ffmpeg`, `ffprobe` | **Incluidos en `bin/`** |
| Terminal de 120×30 | La app la ajusta sola |

En sistemas minimalistas puede hacer falta la librería de audio:

```bash
sudo apt-get install -y libasound2 libasound2-plugins
```

---

## Tamaño de la terminal

Al iniciar, la ventana se ajusta automáticamente a **120×30** con el escape ANSI `CSI 8;30;120t`. En **tmux** usa `tmux resize-window`.

Para otro tamaño:

```bash
TERMINAL_MP3_SIZE=140x40 terminal-mp3player
```

Límites: mínimo `96×30`, máximo `240×80`.

---

## Carpeta de música

```bash
# Global
cp ~/Descargas/*.mp3 ~/Music/terminal-mp3player/

# Proyecto local
cp ~/Descargas/*.mp3 ~/term.../terminal-mp3player/music/
```

O pasa una carpeta al abrir:

```bash
terminal-mp3player /ruta/a/mi/musica
```

Variable de entorno:

```bash
TERMINAL_MP3_DIR=/ruta/a/mi/musica terminal-mp3player
```

---

## Solución de problemas

**No se inicializa el audio**
```bash
export SDL_AUDIODRIVER=alsa      # o pulse / pipewire
terminal-mp3player
```

**Sin sonido en entorno de prueba**
```bash
export SDL_AUDIODRIVER=dummy     # interfaz sin audio
```

**El ratón no responde en tmux**
```bash
set -g mouse on
```

**No hay archivos de audio**
Copia MP3/OGG/WAV/FLAC a la carpeta de música indicada arriba.

---

## Créditos y licencia

**Power by Agdala 2026** · agdala.sv@gmail.com  
Licencia de uso **gratuita**. **Prohibida su venta.**
