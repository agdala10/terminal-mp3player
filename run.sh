#!/usr/bin/env bash
# Lanzador de terminal-mp3player usando el entorno virtual del proyecto.
cd "$(dirname "$0")" || exit 1
exec .venv/bin/python terminalmp3.py "$@"
