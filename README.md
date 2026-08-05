# Exnova Bot

Bot autónomo en **Python** para opciones binarias en **Exnova**, con modelo de Machine Learning de ultra baja latencia (**XGBoost**), filtrado macro con IA (**Gemini**), gestión estricta de riesgo y persistencia en **SQLite**.

> 🎓 **Propósito principal:** ejercicio de **aprendizaje aplicado** — ML sobre series temporales, Pandas, ingeniería de features y auditoría de modelos. Sirve como **proyecto de portafolio para transición hacia Analista de Datos**, no como fuente de ingresos.

> ⚠️ **Advertencia de Riesgo:** las opciones binarias son instrumentos de alto riesgo. Proyecto técnico/educativo. Opera siempre en **DEMO** primero y nunca inviertas capital que no puedas permitirte perder.

> 🔄 **Nota sobre el bróker:** Exnova **no tiene regulación reconocida** (CySEC, FCA, CNMV). Se trata como una **dependencia intercambiable**: el núcleo analítico funciona independientemente del bróker conectado.

## Estado del Proyecto

- **Fase 1 — Entorno y Menú:** ✅ completa (`BrokerClient` abstracto, `ExnovaAdapter`, menú interactivo Normal/OTC, conexión DEMO validada).
- **Fase 2 — Machine Learning:** 🔄 en curso (descarga de historial ✅, features técnicos ✅, entrenamiento walk-forward pendiente).
- **Fases 3-6:** Base de datos/backtesting, integración DEMO, despliegue, dashboard.

Detalle completo: [plan.md](plan.md) (roadmap, arquitectura de 3 capas, reglas de riesgo, esquema de BD).

## Stack

| Componente | Tecnología |
| --- | --- |
| Lenguaje | Python 3.14 (uv) |
| Conexión Broker | `BrokerClient` + `ExnovaAdapter` (websocket-client) |
| Análisis Técnico | pandas + `ta` |
| IA de Señales | XGBoost (.pkl) |
| IA Macro | Gemini 2.0 Flash Lite |
| BD | SQLite3 |
| Notificaciones | Bot de Telegram |
| Validación | scikit-learn (TimeSeriesSplit / walk-forward) |

## Instalación

Requiere [uv](https://docs.astral.sh/uv/).

```bash
uv sync
cp .env.example .env   # rellena con tus credenciales DEMO
```

## Uso

### Menú interactivo (Fase 1)

```bash
uv run python main.py
```

### Descargar historial de velas (10,000+)

```bash
uv run python -m bot.scripts.fetch_history --pair EURUSD --timeframe 5m --count 10000
```

### Generar features técnicos

```bash
uv run python -m bot.scripts.build_features --in data/5m/EURUSD.csv --out data/5m/EURUSD.features.csv
```

## Estructura

```text
bot/
├── broker/       # Interfaz abstracta BrokerClient + adaptadores (Exnova)
├── ml/           # Machine Learning: features (train.py, model.py futuros)
├── scripts/      # CLIs (fetch_history, build_features)
├── vendor/       # Librería exnovaapi de terceros (no tocar)
├── config.py     # Credenciales desde .env
├── history.py    # Descarga de velas con paginación
└── menu.py       # Menú interactivo de inicio
data/             # Velas CSV descargadas y features generados
main.py           # Entry point
plan.md           # Roadmap y decisiones de arquitectura
```

## Convenciones

- El núcleo del bot **nunca importa `exnovaapi` directamente** — solo habla con `BrokerClient`. Cambiar de bróker = escribir un adaptador nuevo en `bot/broker/`.
- Credenciales **solo** vía variables de entorno / `.env` (excluido de git). Nunca hardcodeadas.
- `ta` sustituye a `pandas-ta` (abandonado, no soporta Python 3.14).
- Instrucciones para agentes de IA: ver [AGENTS.md](AGENTS.md).
