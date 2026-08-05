# AGENTS.md

Guía para agentes de IA y colaboradores que trabajan en este repositorio.

## Proyecto

Bot autónomo de opciones binarias en Exnova, en Python. Proyecto educativo/de portafolio — **no es fuente de ingresos**. Proyecto completo y decisiones de arquitectura en **`plan.md`** (fuente única de verdad; léelo antes de hacer cambios de alcance).

- Fase 1 (entorno, menú, BrokerClient/ExnovaAdapter) **completa**.
- Fase 2 (Machine Learning) **en curso**: historial ✅, features ✅, entrenamiento walk-forward pendiente.

## Entorno

- **Python 3.14 + uv** (usa `uv` para deps y ejecución, no pip).
- SO Windows; shell PowerShell 7 (`pwsh`). Evita heredocs bash — escribe un script temporal si necesitas bloques multi-línea.
- `plan.md` usa LF. Respeta el estilo de archivo existente.
- Clave del layout de imports: corre siempre desde la raíz del repo (`uv run python -m ...`), nunca desde `bot/`.

## Comandos

```bash
uv add <paquete>                 # añadir dependencia
uv run python -m bot.scripts.build_features --in data/5m/EURUSD.csv
uv run python -m bot.scripts.fetch_history --pair EURUSD --timeframe 5m --count 10000
uv run python main.py            # menú interactivo (requiere .env)
```

Verificar imports tras mover archivos: `uv run python -c "from <modulo> import ..."`.

## Arquitectura (reglas no negociables)

- **Nunca importes `exnovaapi` fuera de `bot/broker/exnova.py`.** El núcleo solo conoce `BrokerClient` (`bot/broker/base.py`). Cambiar de bróker = nuevo adaptador, nada más.
- `bot/vendor/exnovaapi/` es librería de terceros copiada — **no la modifiques**.
- La lógica pura (features, history, ML) no importa el bróker; recibe datos vía parámetros/callables.

## Estructura

```text
bot/
├── broker/       # BrokerClient (base.py) + ExnovaAdapter (exnova.py)
├── ml/           # features.py (16 columnas, lib ta); train.py/model.py futuros
├── scripts/      # fetch_history.py, build_features.py (CLIs con --in/--out)
├── vendor/       # exnovaapi (terceros, no tocar)
├── config.py     # lee .env, valida credenciales
├── history.py    # fetch_candle_history (paginación 1000/batch)
└── menu.py       # choose_market / choose_assets
data/5m/          # EURUSD.csv, EURUSD.features.csv
```

## Datos y ML

- Features: `build_features()` (bot/ml/features.py) → 16 columnas (`FEATURE_COLUMNS`). Las ~49 primeras filas tienen NaN de warm-up (EMA50/ATR14) — aplicar `dropna()` en entrenamiento.
- `ta` sustituye a `pandas-ta` (abandonado, no soporta py3.14). No intentes reintroducirlo.
- El target (dirección vela t+1) se construye en la tarea de entrenamiento, no en features.
- Validación: **walk-forward (TimeSeriesSplit), nunca split aleatorio** — evita data leakage.

## Credenciales

- Todo secreto vía `.env` (excluido de git). Plantilla: `.env.example`.
- Nunca muestres ni hardcodees credenciales, tokens o claves.

## Convenciones de código

- Responder al usuario en **español**; identificadores/código en inglés.
- **No añadir comentarios** al código salvo que se pidan.
- Modo ponytail: la solución más simple que funciona (YAGNI). Una carpeta solo se crea cuando hay 2-3+ archivos relacionados, no para 1 archivo.
- Al terminar una tarea, verificar con una ejecución real o `import` (no asumir).
