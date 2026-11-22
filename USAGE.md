# Uso de Terminal Mp3 Player

Guía completa de funcionamiento. Todo se controla con **teclado** y **ratón**, dentro de la terminal.

---

## 1. Iniciar

```bash
terminal-mp3player
```

La ventana se ajusta sola a 120×30 y aparecen tres paneles:

- **TERMINAL MP3 PLAYER** (reproductor, arriba‑izquierda)
- **TERMINAL MP3 PLAYER - EQ** (ecualizador, abajo‑izquierda)
- **TERMINAL MP3 PLAYER - PLAYLIST** (playlist, derecha)

---

## 2. Controles de teclado

| Tecla | Acción |
|-------|--------|
| `↑` / `↓` | Elegir canción |
| `Enter` | Reproducir seleccionada |
| `Espacio` | Pausa / reanudar |
| `←` / `→` | Anterior / siguiente |
| `+` / `-` | Volumen |
| `s` | Activar/desactivar SHUFFLE |
| `e` | Minimizar/maximizar ecualizador |
| `l` | Minimizar/maximizar playlist |
| `p` | Menú de presets |
| `u` | Abrir diálogo para pegar URL de YouTube |
| `t` | Gestor de listas guardadas |
| `d` | Descargar la pista seleccionada |
| `c` | Créditos y licencia |
| `q` o `Esc` | Salir |

---

## 3. Controles con ratón

- Clic en una canción → la reproduce.
- Botones `|<`, `>`, `||`, `[]`, `>|`, `^`, `SHUFFLE`, `=`.
- Barra de volumen → clic o arrastre.
- Faders del ecualizador → clic o arrastre (el pulador gris sigue a la barra).
- Botones `ON`, `AUTO`, `PRESETS`, `[URL]`, `[LIST]`, `[CRED]`.
- Icono **`↓`** junto a una pista de YouTube → la descarga.
- Botones `[EQ]` y `[PL]` → minimizan/maximizan ventanas.

---

## 4. Escuchar música local

1. Copia tus canciones a `~/Music/terminal-mp3player/` (o `./music/`).
2. Abre el reproductor.
3. Selecciona con `↑/↓` y pulsa `Enter`.

---

## 5. Agregar música de YouTube / YouTube Music

1. Pulsa **`u`** o el botón **`[URL]`**.
2. Pega la URL (Ctrl+V funciona).
3. Pulsa **`Enter`**.

El reproductor consulta el título real con `yt-dlp` y lo añade a la playlist.  
Al reproducirlo, el audio se descarga a caché y suena como cualquier archivo local, con la **mejor calidad disponible** (MP3 VBR ~264 kbps, estéreo 48 kHz).

Ejemplo:

```
https://www.youtube.com/watch?v=dQw4w9WgXcQ
```

---

## 6. Descargar una canción de YouTube

Cada pista URL muestra un icono **`↓`** al final de la fila.

- **Clic en `↓`** (o tecla **`d`** sobre la pista seleccionada).
- El audio se guarda en la carpeta principal de música local:
  - Global: `~/Music/terminal-mp3player/`
  - Proyecto: `./music/`
- La entrada pasa a ser un archivo local y se guarda en la lista.

Si no pulsas el icono, la canción **solo se escucha** y se pasa a la siguiente automáticamente.

---

## 7. Crear y usar varias playlists

1. Pulsa **`t`** o el botón **`[LIST]`**.
2. Escribe un nombre:
   - Si la lista existe, **carga** esa lista.
   - Si no existe, **guarda** la lista actual con ese nombre.
3. `Supr` borra la lista seleccionada.
4. `Esc` cierra el gestor.

Las listas se guardan en:

```
~/.config/terminal-mp3player/playlists/
```

Como archivos JSON con título, ruta local o URL y duración.

---

## 8. Ecualizador

- 11 faders: `PRE` (volumen), 60, 170, 310, 600, 1K, 3K, 6K, 12K, 14K, 16K.
- El efecto es **real e instantáneo**: filtro FIR en tiempo real sobre el audio de SDL, sin reprocesar archivos ni cortar el sonido.
- **ON** enciende/apaga el ecualizador.
- **AUTO** cambia de preset cada 5 segundos mientras se reproduce.
- **PRESETS** abre: `ROCK`, `HIP-HOP`, `METAL`, `SALSA`, `CUMBIA`.

---

## 9. Minimizar ventanas

- Botones `[EQ]` y `[PL]` o teclas `e` y `l`.
- El reproductor **mantiene su tamaño**.
- La terminal se reduce:
  - Sin EQ → `120×16`
  - Sin playlist → `61×30`
  - Sin ambas → `61×16`
- Al restaurar vuelve a `120×30`.

---

## 10. Créditos

Pulsa **`c`** o el botón **`[CRED]`**:

```
Power By Agdala 2026
Mensaje: ¡Gracias por usar TERMINAL MP3 PLAYER!
agdala.sv@gmail.com
Licencia de uso GRATUITA. Prohibida su venta.
```

---

**Power by Agdala 2026** · Uso gratuito · Prohibida su venta.
