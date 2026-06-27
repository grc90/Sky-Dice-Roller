# Inicio rápido para Windows PowerShell
# El token se lee desde el archivo .env — no lo pases como parámetro

# Crear entorno virtual si no existe
if (-not (Test-Path "venv")) {
    Write-Host "Creando entorno virtual..."
    python -m venv venv
}

# Activar e instalar dependencias
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt --quiet

Write-Host "Iniciando Super Dice Roll Bot..." -ForegroundColor Green
python bot.py
