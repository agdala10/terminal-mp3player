#!/usr/bin/env bash
# Instalación global de terminal-mp3player para TODOS los usuarios del sistema.
# Ejecutar con:  sudo bash install-system.sh
set -euo pipefail

SRC="$(cd "$(dirname "$0")" && pwd)"
PREFIX="/opt/terminal-mp3player"
BIN="/usr/local/bin"

echo "==> Instalando terminal-mp3player para todos los usuarios..."

# ------------------------------------------------------------------
# 1) pygame disponible para el Python del sistema
# ------------------------------------------------------------------
if python3 -c 'import pygame' >/dev/null 2>&1; then
    echo "==> pygame ya está instalado en el sistema"
else
    echo "==> Instalando pygame en el Python del sistema..."
    if apt-get install -y python3-pygame >/dev/null 2>&1; then
        echo "==> pygame instalado vía apt"
    elif apt-get update -qq && apt-get install -y python3-pygame >/dev/null 2>&1; then
        echo "==> pygame instalado vía apt (tras apt-get update)"
    elif python3 -m pip install --break-system-packages pygame >/dev/null 2>&1; then
        echo "==> pygame instalado vía pip"
    else
        echo "ERROR: no se pudo instalar pygame" >&2
        exit 1
    fi
fi

# ------------------------------------------------------------------
# 2) Copiar el proyecto a /opt
# ------------------------------------------------------------------
echo "==> Copiando archivos a $PREFIX ..."
install -d -m 755 "$PREFIX" "$PREFIX/music"
install -m 755 "$SRC/terminalmp3.py" "$PREFIX/terminalmp3.py"
install -m 644 "$SRC/README.md"      "$PREFIX/README.md"
install -m 644 "$SRC/requirements.txt" "$PREFIX/requirements.txt"
install -m 644 "$SRC/music/README.txt" "$PREFIX/music/README.txt"

# Herramientas empaquetadas: yt-dlp + módulo + ffmpeg + ffprobe.
rm -rf "$PREFIX/bin"
cp -a "$SRC/bin" "$PREFIX/bin"
chmod -R a+rX "$PREFIX/bin"
chmod 755 "$PREFIX/bin/yt-dlp" "$PREFIX/bin/ffmpeg" "$PREFIX/bin/ffprobe"
chmod 755 "$PREFIX" "$PREFIX/music"

# ------------------------------------------------------------------
# 3) Comando global en /usr/local/bin
# ------------------------------------------------------------------
echo "==> Creando lanzadores en $BIN ..."
rm -f "$BIN/term-winamp" "$BIN/winamp" "$BIN/tmp3" \
      "$BIN/terminal-mp3-player" "$BIN/terminal-mp3player"

cat > "$BIN/terminal-mp3player" <<'EOF'
#!/usr/bin/env bash
# Lanzador global de terminal-mp3player (usa el Python del sistema).
exec /usr/bin/python3 /opt/terminal-mp3player/terminalmp3.py "$@"
EOF
chmod 755 "$BIN/terminal-mp3player"

for alias_name in terminal-mp3-player tmp3 winamp term-winamp; do
    ln -sf terminal-mp3player "$BIN/$alias_name"
done

# Limpieza de la instalación anterior.
if [ -d /opt/term-winamp ]; then
    rm -rf /opt/term-winamp
fi

# ------------------------------------------------------------------
# 4) Verificación
# ------------------------------------------------------------------
python3 -c 'import pygame; print("==> pygame OK:", pygame.version.ver)'
command -v terminal-mp3player
echo
echo "✅ INSTALACIÓN COMPLETADA"
echo "   Cualquier usuario puede ejecutar:  terminal-mp3player"
echo "   (alias: terminal-mp3-player / tmp3 / winamp / term-winamp)"
echo "   Su música se busca en: ~/Music/terminal-mp3player  (se crea sola)"
echo "   También se puede indicar:  terminal-mp3player /ruta/a/musica"
