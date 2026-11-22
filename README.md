# 🎵 TERMINAL MP3 PLAYER

Reproductor de música **multicolor** que corre **completamente en la terminal** de Linux, con interfaz inspirada en los reproductores clásicos. No abre ninguna ventana gráfica: usa `curses` para dibujar y `pygame` para reproducir el audio. **El ratón se activa automáticamente al iniciar.**

🌐 **Sitio web (GitHub Pages):** `https://agdala10.github.io/terminal-mp3player/`

📘 Guías: [INSTALACIÓN](INSTALL.md) · [USO](USAGE.md) · [Demo en video](docs/assets/media/demo.mp4)

## Características

- **Tres ventanas de colores distintos**: reproductor (título magenta), ecualizador (título verde) y playlist (título rojo).
- LCD verde con reloj cian, osciloscopo verde/cian, barra de volumen amarilla con cursor rojo.
- Ecualizador con 11 faders en cinco colores (amarillo, cian, magenta, verde, rojo).
- Playlist con filas en cinco colores, duraciones cian, selección resaltada y scrollbar azul.
- Botones de transporte multicolor, reloj total `elapsed/total+`.
- Control por **teclado y ratón**, shuffle y avance automático a la siguiente pista.
- Sin interfaz gráfica, sin X11, sin servidor web. Requiere terminal de al menos **96x30**.
- **Layout compacto (120x30)**: se quitaron los espacios negros sobrantes del reproductor y del ecualizador. La playlist muestra solo las canciones.

## Instalación ✅ (ya realizada)

El proyecto usa un **entorno virtual** (`.venv/`) porque el sistema bloquea las instalaciones globales de pip (PEP 668). `pygame 2.6.1` ya está instalado ahí.

Para reinstalarlo desde cero:

```bash
cd ~/terminal-mp3player
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

> En sistemas minimalistas puede hacer falta la librería de audio del sistema:
> ```bash
> sudo apt-get install -y libasound2 libasound2-plugins
> ```

## Instalación global (todos los usuarios) ✅ (ya realizada)

Se instaló en `/opt/terminal-mp3player`, con `pygame` en el Python del sistema y lanzadores en `/usr/local/bin`. Cualquier usuario puede abrir una terminal nueva y escribir:

```bash
terminal-mp3player   # o:  terminal-mp3-player / tmp3 / winamp / term-winamp
```

Cada usuario guarda su música en `~/Music/terminal-mp3player` (la carpeta se crea automáticamente). Para reinstalar:

```bash
sudo bash /home/master/terminal-mp3player/install-system.sh
```

## Uso (proyecto local de `master`)

```bash
# 1) Pon música en la carpeta music/
cp ~/Descargas/*.mp3 music/

# 2) Ejecuta con el lanzador (recomendado)
./run.sh

# O directamente con el intérprete del venv
.venv/bin/python terminalmp3.py

# O apunta a otra carpeta
./run.sh /ruta/a/mi/musica

# O mediante variable de entorno
TERMINAL_MP3_DIR=/ruta/a/mi/musica ./run.sh
```

## Tamaño automático de la terminal 📐

Al iniciar, el reproductor **redimensiona solo la ventana** a `120x30` (el tamaño justo, sin espacios negros sobrantes), usando el escape ANSI `CSI 8;30;120t`. Funciona en xterm, GNOME Terminal, Konsole, Kitty, etc. En **tmux** usa `tmux resize-window`.

Si quieres otro tamaño:

```bash
TERMINAL_MP3_SIZE=140x40 terminal-mp3player
```

El valor se limita a un mínimo de `96x30` y un máximo de `240x80`.

## Controles

| Tecla | Acción |
|-------|--------|
| `↑` / `↓` | Elegir canción |
| `Enter` | Reproducir seleccionada |
| `Espacio` | Pausa / reanudar |
| `←` / `→` | Anterior / siguiente |
| `+` / `-` | Subir / bajar volumen |
| `s` | Activar/desactivar SHUFFLE |
| `e` | Minimizar/maximizar ecualizador |
| `l` | Minimizar/maximizar playlist |
| `p` | Abrir/cerrar menú de PRESETS |
| `c` | Ver créditos y licencia |
| `q` o `Esc` | Salir |

### Créditos
El botón **`[CRED]`** de la playlist (o tecla **`c`**) abre una ventana con:

- **Power By Agdala 2026**
- Mensaje y correo: **agdala.sv@gmail.com**
- **Licencia de uso gratuita — prohibida su venta.**

### Ecualizador y presets
- El **pulador gris `▒`** se desplaza con la barra de cada canal.
- El ecualizador es **real e instantáneo**: se aplica como efecto `Mix_SetPostMix` de SDL sobre el audio en vivo (FIR de 256 taps con numpy), sin reprocesar archivos, sin esperas, sin congelar la interfaz, sin bajar el volumen y sin cortar el sonido.
- Mover un fader, aplicar un preset o pulsar **ON/AUTO** cambia el filtro **al instante**. La reproducción usa canales de `pygame.mixer.Sound` (necesario para que SDL aplique el post‑mix).
- **ON** enciende/apaga el ecualizador; **AUTO** cambia de preset automáticamente cada 5 s mientras se reproduce.
- **PRESETS** abre un menú con: `ROCK`, `HIP-HOP`, `METAL`, `SALSA`, `CUMBIA`.
- Los botones **`[EQ]`** y **`[PL]`** del reproductor minimizan/maximizan el ecualizador y la playlist. El reproductor **mantiene siempre su ancho y alto**; solo se oculta la ventana elegida, sin deformarse.
- La **terminal también se redimensiona**: al ocultar el EQ baja a `120x16`, al ocultar la playlist baja a `61x30` (o `61x16` si ambas están ocultas), y al restaurar vuelve a `120x30`.

### YouTube Music, listas y descargas 🌐

- Pulsa **`u`** o el botón **`[URL]`** de la playlist y pega una URL de YouTube / YouTube Music. El reproductor consulta el título con `yt-dlp` (o `oEmbed` como respaldo) y lo añade a la lista.
- Las pistas URL **sí se escuchan**: al darles `Enter` se descarga el audio a una caché temporal y suena como cualquier archivo local.
- Cada pista URL muestra un icono **`↓`** al final de la fila: **clic en `↓`** (o tecla **`d`**) la descarga en segundo plano a la carpeta principal de música y la convierte en pista local. Si no se pulsa, la canción simplemente se escucha y se pasa a la siguiente.
- El diálogo tiene **fondo gris sólido** para que se distinga, acepta **pegar con Ctrl+V** y muestra el resultado (o el error) en una línea de estado del reproductor. Si no hay conexión, guarda igualmente la pista con un nombre basado en el ID del vídeo.
- Pulsa **`t`** o **`[LIST]`** para abrir el gestor de listas: escribe un nombre y `Enter` carga esa lista (o la crea guardando la actual); `Supr` borra la lista seleccionada. Las listas se guardan en `~/.config/terminal-mp3player/playlists/`.
- Al terminar la pista, el reproductor sigue con la siguiente automáticamente (**solo la escuchas**). Para guardarla, pulsas el icono `↓` cuando quieras.
- **`yt-dlp`, su módulo Python, `ffmpeg` y `ffprobe` van INCLUIDOS en `bin/`**. El usuario no tiene que instalar nada: la app los pone primero en el `PATH` y los usa automáticamente (si faltaran, hay respaldo con `oEmbed`).

### Calidad de audio 🔊
- Descarga siempre el **mejor formato de audio disponible** (`bestaudio/best`) y extrae MP3 con `--audio-quality 0` (VBR máximo; en la prueba dio **264 kbps, estéreo 48 kHz**), evitando una segunda codificación de baja calidad.
- El mezclador se inicializa preferentemente a **48 kHz / 16 bit / estéreo** con buffer de 2048 (sin resampleo en las pistas de YouTube y menos cortes). Si el dispositivo no lo acepta, baja a 44,1 kHz y luego a la configuración por defecto.
- El LCD muestra la configuración real (`48 kHz   16 bit   stereo`).

### Ratón 🖱️

También se puede usar el mouse (curses habilita el reporte de eventos):

- **Playlist:** clic en una canción la selecciona y la reproduce.
- **Botones:** `|<`, `>`, `||`, `[]`, `>|`, `SHUFFLE`, `=`, `[EQ]`, `[PL]`, `ADD`, `REM`, `SEL`, `MISC`, `ON`, `AUTO`, `PRESETS`, `[URL]`, `[LIST]`, `[CRED]` y los transportes `◄◄ ◄ ► ►►`.
- **Barra de volumen:** clic o arrastre para ajustar el nivel.
- **Ecualizador:** clic o arrastre sobre cualquier fader (el primero controla el volumen); su pulador gris sigue a la barra.
- **Menú de presets:** clic en `PRESETS` y luego en `ROCK`, `HIP-HOP`, `METAL`, `SALSA` o `CUMBIA`.
- **LCD:** clic para reproducir la pista seleccionada.

> Si tu terminal no propaga eventos de ratón, activa el modo mouse de tu emulador (en GNOME Terminal, Xterm, Konsole y Kitty funciona por defecto; en tmux usa `set -g mouse on`).

## Solución de problemas

**"No se pudo inicializar el audio"** — Prueba elegir un backend de SDL:

```bash
export SDL_AUDIODRIVER=alsa      # o pulse / pipewire
python3 terminalmp3.py
```

En un entorno sin tarjeta de sonido puedes usar `SDL_AUDIODRIVER=dummy` para probar la interfaz (no se escuchará nada).

**"No hay archivos de audio"** — La carpeta `music/` existe pero está vacía. Copia tus canciones ahí.

**La terminal se ve rara** — La app ajusta la ventana sola; si la acortas manualmente, vuelve a `120x30`.

## Estructura

```
terminal-mp3player/
├── terminalmp3.py      # código principal
├── requirements.txt    # dependencias (pygame)
├── music/              #_coloca_tu_música_aquí_
└── README.md           # este archivo
```

Licencia: MIT. TERMINAL MP3 PLAYER — música en tu terminal. 🖥️🎶
