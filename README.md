# 🎲 Super Dice Roll Bot

Bot de Telegram para lanzar dados de cualquier tipo, con soporte para D&D y otros juegos de rol. Funciona en chats privados y grupos (el modo inline está desactivado por seguridad, ver [Modo inline](#modo-inline)).

---

## Características

- Lanzamiento de dados con la sintaxis estándar de rol: `NdM`, `NdM±X`, `NdMkhK`, etc.
- Selectores **keep/drop**: `kh`, `kl`, `dh`, `dl`
- Generación de estadísticas D&D con múltiples variantes
- Historial de tiradas por usuario (en memoria)
- Validación de entrada con mensajes de error claros
- Tiradas críticas y pifias detectadas automáticamente (🎯 / 💀)

---

## Instalación

### Requisitos

- Python 3.11 o superior
- Token de Telegram (obtenido desde [@BotFather](https://t.me/BotFather))

### 1. Clonar o descargar el proyecto

```
super-dice-roll-bot/
├── bot.py
├── requirements.txt
├── .env              ← créalo tú (ver paso 3)
├── .env.example      ← plantilla
├── start.ps1         ← inicio rápido Windows
├── start.sh          ← inicio rápido Linux/Mac
└── tests/
    └── test_core.py
```

### 2. Crear el entorno virtual e instalar dependencias

**Windows (PowerShell):**
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

**Linux / Mac:**
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Configurar el token

Copia `.env.example` como `.env` y pon tu token real:

```
BOT_TOKEN=123456:ABC-tu-token-aqui
```

> **Importante:** nunca subas `.env` a git. Ya está en `.gitignore`.

### 4. Iniciar el bot

**Windows:**
```powershell
.\start.ps1
```

**Linux / Mac:**
```bash
chmod +x start.sh
./start.sh
```

**Manual (cualquier sistema):**
```bash
python bot.py
```

---

## Configurar en BotFather

### Comandos visibles en Telegram

Telegram permite separar la lista de comandos según el contexto: grupos vs. chats privados.

#### Scope: grupos (recomendado)

En [@BotFather](https://t.me/BotFather) → `/setcommands` → seleccioná el bot → elegí **"Edit commands for groups"**:

```
roll - Lanza dados. Ej: /roll 3d6 · /roll 4d6dl1 · /roll 2d20kh1+3
stats - Genera 6 estadísticas D&D. Ej: /stats · /stats heroic · /stats 3d6
history - Tus últimos 10 lanzamientos
help - Cómo usar el bot y el modo inline
```

> `/admin` y `/start` se omiten en grupos deliberadamente: `/admin` es solo para privado; `/start` no aporta valor en un grupo activo.

#### Scope: chats privados

En BotFather → `/setcommands` → **"Edit commands for private chats"**:

```
roll - Lanza dados. Ej: /roll 3d6 · /roll 4d6dl1 · /roll 2d20kh1+3
stats - Genera 6 estadísticas D&D. Ej: /stats · /stats heroic · /stats 3d6
history - Tus últimos 10 lanzamientos
help - Cómo usar el bot y el modo inline
start - Inicia el bot y muestra los controles rápidos
```

> Si BotFather no muestra la opción de scope, podés definir los mismos comandos para todos los contextos con `/setcommands` → **"For all chats"** y luego refinarlo.

### Modo inline

No es necesario activarlo: el modo inline está desactivado a nivel de código por seguridad (ver [Modo inline](#modo-inline) más abajo). Si `/setinline` ya está configurado en BotFather, no hay problema en dejarlo así — el bot solo responderá con un mensaje informativo, sin tiradas reales.

---

## Uso

### Comandos

#### `/roll NdM[selector][±modificador]`

Lanza dados. Todos los componentes excepto `M` son opcionales.

| Componente | Descripción | Ejemplo |
|---|---|---|
| `N` | Número de dados (defecto: 1) | `3d6` |
| `M` | Caras del dado | `d20` |
| `khK` | Keep highest — conserva los K más altos | `4d6kh3` |
| `klK` | Keep lowest — conserva los K más bajos | `5d10kl2` |
| `dhK` | Drop highest — descarta los K más altos | `6d8dh2` |
| `dlK` | Drop lowest — descarta los K más bajos | `4d6dl1` |
| `±X` | Modificador sumado al total | `2d20+5` |

**Ejemplos:**

```
/roll 3d6          → 3 dados de 6 caras
/roll d20+5        → 1d20 con +5
/roll 4d6dl1       → 4d6, descarta el más bajo (estadística D&D)
/roll 4d6kh3+2     → 4d6, guarda los 3 más altos, +2
/roll 2d20kh1      → ventaja en D&D
/roll 2d20kl1      → desventaja en D&D
/roll 6d8dh2       → 6d8, descarta los 2 más altos
```

**Respuesta ejemplo (`/roll 4d6dl1`):**
```
🎲 4d6dl1
┌ Todos:      [ 2 · 5 · 3 · 6 ]
├ ❌ dl1 (descarta los 1 más bajos): [ 2 ]
├ ✅ Mantiene: [ 6 + 5 + 3 ] = 14
└ Total: 14
```

**Crítico / Pifia (solo en 1d sin modificador):**
```
🎲 1d20
└ Resultado: 20 🎯 ¡Crítico!

🎲 1d20
└ Resultado: 1 💀 ¡Pifia!
```

---

#### `/stats [variante]`

Genera 6 valores de estadísticas de habilidad para D&D.

**Regla estándar:** tira 4d6, descarta el más bajo, suma los 3 mayores. Repite 6 veces.

| Variante | Expresión | Descripción |
|---|---|---|
| `standard` / `dnd` | `4d6dl1` | Estándar D&D 5e *(por defecto)* |
| `classic` / `3d6` | `3d6` | Clásico, sin descartar |
| `heroic` | `5d6dl2` | 5d6, descarta los 2 más bajos |
| `grim` | `3d6kl2` | 3d6, conserva los 2 más bajos |
| Expresión libre | cualquiera | `/stats 4d6kh3` |

**Respuesta ejemplo (`/stats`):**
```
⚔️ Estadísticas de D&D
Variante: 4d6dl1 — estándar D&D — 4d6, descarta el más bajo, suma los 3 mayores

Tirada 1: [ 6 · 4 · 3 · 2 ] ❌ [2] → 13
Tirada 2: [ 5 · 5 · 4 · 1 ] ❌ [1] → 14
Tirada 3: [ 6 · 6 · 2 · 3 ] ❌ [2] → 15
Tirada 4: [ 4 · 3 · 2 · 1 ] ❌ [1] → 9
Tirada 5: [ 6 · 5 · 4 · 2 ] ❌ [2] → 15
Tirada 6: [ 3 · 3 · 3 · 1 ] ❌ [1] → 9

📊 Resultados: 13, 14, 15, 9, 15, 9
Suma: 75 | Promedio: 12.5
```

---

#### `/history`

Muestra tus últimos 10 lanzamientos. El historial persiste entre reinicios gracias a `roll_history.json`.

```
📋 Tus últimos lanzamientos:

1. stats(4d6dl1) → [13, 14, 15, 9, 15, 9]
2. 4d6dl1 → 14
3. 2d20kh1 → 17
4. 1d20 → 8
```

---

#### `/admin`

Panel de administración de solo lectura. Requiere que tu ID de Telegram esté en `ADMIN_USER_IDS` (ver Variables de entorno).

Muestra:
- Uptime del bot desde el último arranque
- Usuarios activos en memoria vs. límite configurado
- Parámetros de configuración actuales (historial, límites)

Si `ADMIN_USER_IDS` no está configurado, el comando avisa que no hay admins definidos (no produce error).

#### `/help`

Muestra la referencia completa de comandos y sintaxis.

#### `/start`

Mensaje de bienvenida con un resumen de comandos. Ideal para usuarios nuevos.

---

### Modo inline

**Desactivado por seguridad.** Telegram permite convertir cualquier resultado inline en un mensaje *programado*, pero no expone ninguna señal fiable para distinguir ese caso de un envío inmediato. Como el contenido de un resultado inline se fija en el momento de la consulta y se entrega tal cual cuando el cliente decide enviarlo, un resultado inline con una tirada real permitiría precomputar un resultado favorable y programarlo para más tarde como si fuera legítimo.

Por eso `@NombreDelBot` en cualquier chat solo devuelve un mensaje informativo (sin números aleatorios reales) que indica usar `/roll` o `/stats` en el chat.

---

## Tests

```bash
python -m pytest tests/ -v
```

Los tests cubren parsing, lógica de dados, selectores, format de mensajes, límites de longitud, historial LRU, detección de chat privado y persistencia de historial. No requieren conexión a Telegram. (98 casos)

---

## Variables de entorno

| Variable | Requerida | Descripción |
|---|---|---|
| `BOT_TOKEN` | ✅ | Token del bot obtenido desde @BotFather |
| `ADMIN_USER_IDS` | ❌ | IDs de Telegram de admins, separados por coma. Ej: `123456,789012` |
| `HISTORY_FILE` | ❌ | Ruta del archivo JSON de historial persistente. Defecto: `roll_history.json` |
| `MAX_HISTORY_USERS` | ❌ | Máximo de usuarios en memoria (LRU). Defecto: `1000` |
| `LOG_FILE` | ❌ | Ruta del archivo de log rotante. Sin valor: solo consola |
| `LOG_MAX_BYTES` | ❌ | Tamaño máximo por archivo de log. Defecto: `5242880` (5 MB) |
| `LOG_BACKUP_COUNT` | ❌ | Número de archivos de respaldo del log. Defecto: `3` |

### Configuración de administradores

Para activar `/admin`, añade al `.env`:

```
ADMIN_USER_IDS=123456789
```

Tu ID de Telegram se puede obtener enviando `/start` a [@userinfobot](https://t.me/userinfobot).

### Log rotante (opcional)

Para guardar logs a archivo con rotación automática:

```
LOG_FILE=bot.log
LOG_MAX_BYTES=5242880
LOG_BACKUP_COUNT=3
```

Con esta configuración, al llegar a 5 MB se crea `bot.log.1`, `bot.log.2`, etc. Sin `LOG_FILE`, el bot solo escribe en consola (comportamiento por defecto).

---

## Límites técnicos

| Parámetro | Límite |
|---|---|
| Dados por tirada | 1 – 100 |
| Caras por dado | 2 – 10.000 |
| Historial por usuario | últimas 10 tiradas |
| Longitud de respuesta | máx. ~3.800 caracteres (dados en exceso se resumen) |

---

## Estructura del proyecto

```
bot.py              ← lógica principal y handlers
requirements.txt    ← dependencias Python
.env                ← token (no subir a git)
.env.example        ← plantilla para colaboradores
.gitignore
start.ps1           ← inicio rápido Windows
start.sh            ← inicio rápido Linux/Mac
tests/
└── test_core.py    ← suite de tests (98 casos)
```

---

## Pendientes / ideas futuras

- [x] Persistencia del historial entre reinicios (archivo JSON)
- [ ] Imagen de perfil y descripción del bot configuradas en BotFather
