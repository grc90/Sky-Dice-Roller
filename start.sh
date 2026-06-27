#!/usr/bin/env bash
# Inicio rápido para Linux/Mac
# Uso: ./start.sh
# El token se lee desde el archivo .env

set -e

if [ ! -d "venv" ]; then
    echo "Creando entorno virtual..."
    python3 -m venv venv
fi

# shellcheck disable=SC1091
source venv/bin/activate
pip install -r requirements.txt --quiet

echo "Iniciando Super Dice Roll Bot..."
python3 bot.py
