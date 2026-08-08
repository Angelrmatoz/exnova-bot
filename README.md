# Exnova Bot

Bot autónomo en **Python** para opciones binarias en **Exnova**, con modelo de Machine Learning de ultra baja latencia (**XGBoost**), filtrado macro con IA (**Gemini**), gestión estricta de riesgo y persistencia en **SQLite**.

> 🎓 **Propósito principal:** ejercicio de **aprendizaje aplicado** — ML sobre series temporales, Pandas, ingeniería de features y auditoría de modelos. Sirve como **proyecto de portafolio para transición hacia Analista de Datos**, no como fuente de ingresos.

> ⚠️ **Advertencia de Riesgo:** las opciones binarias son instrumentos de alto riesgo. Proyecto técnico/educativo. Opera siempre en **DEMO** primero y nunca inviertas capital que no puedas permitirte perder.

> 🔄 **Nota sobre el bróker:** Exnova **no tiene regulación reconocida** (CySEC, FCA, CNMV). Se trata como una **dependencia intercambiable**: el núcleo analítico funciona independientemente del bróker conectado.

## Estado del Proyecto

- **Fase 1 — Entorno y Menú:** ✅ completa (`BrokerClient` abstracto, `ExnovaAdapter`, menú interactivo Normal/OTC, conexión DEMO validada).
- **Fase 2 — Machine Learning:** ✅ completa (walk-forward, calibración, SHAP, export `.pkl`, features MTLF multi-timeframe).
- **Fases 3-6:** Base de datos/backtesting, integración DEMO, despliegue, dashboard.

> ⚠️ **Hallazgo Fase 2 (importante):** el backtest con features técnicos 5m da ~50% accuracy y **expectancy negativa** (−0.08 a −0.17 con payout 80%). **No hay edge confirmado con técnicos.** Ver `bot/ml/backtest.py` / `calibrate.py`. La literatura (random walk) respalda esto para forex real L-V. Posible vía con respaldo académico (Springer 2025): sentimiento con LLM + XGBoost.

Detalle completo: [plan.md](plan.md) (roadmap, arquitectura de 3 capas, reglas de riesgo, esquema de BD).

## Stack

| Componente | Tecnología |
| --- | --- |
| Lenguaje | Python 3.14 (uv) |
| Conexión Broker | `BrokerClient` + `ExnovaAdapter` (websocket-client) |
| Análisis Técnico | pandas + `ta` |
| IA de Señales | XGBoost (.pkl) |
| Validación | scikit-learn (TimeSeriesSplit / walk-forward) |
| Persistencia | SQLite3 (model_versions) |

## Pipeline ML (Fase 2)

```bash
# 1) Features técnicos (16 col)
uv run python -m bot.scripts.build_features --in data/5m/EURUSD.csv

# 2) Entrenamiento walk-forward (OOS)
uv run python -m bot.ml.train --in data/5m/EURUSD.features.csv

# 3) Curva de calibración + guarda predicciones OOS
uv run python -m bot.ml.calibrate --in data/5m/EURUSD.features.csv

# 4) Backtest real (expectancy, PnL, maxDD)
uv run python -m bot.ml.backtest --in data/5m/EURUSD.features.csv --payout 0.80

# 5) Importancia de features (SHAP)
uv run python -m bot.ml.shap_analysis --in data/5m/EURUSD.features.csv

# 6) Exportar modelo final .pkl (registra en SQLite)
uv run python -m bot.ml.export_model --in data/5m/EURUSD.features.csv --out models/eurusd_5m.pkl

# 7) Features multi-timeframe MTLF (15m/1h, anti-leakage)
uv run python -m bot.ml.multi_tf --in data/5m/EURUSD.csv --out data/5m/EURUSD.mtl.csv
```

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
├── broker/       # Interfaz abstracta BrokerClient + adaptadores (Exnova, Mock) + ExnovaWSClient
├── ml/           # ML: features, multi_tf, train, calibrate, backtest, shap, export
├── scripts/      # CLIs (fetch_history, build_features, backtest_mock)
├── db.py         # SQLite (model_versions; trade_logs)
├── config.py     # Credenciales desde .env
├── history.py    # Descarga de velas con paginación
└── menu.py       # Menú interactivo de inicio
data/             # Velas CSV descargadas y features generados
models/           # Modelos XGBoost exportados (.pkl)
main.py           # Entry point
plan.md           # Roadmap y decisiones de arquitectura
```

## Convenciones

- La conexión con Exnova se hace vía `ExnovaWSClient` (cliente WebSocket propio en `bot/broker/exnova_ws.py`); el vendor `exnovaapi` fue eliminado. El núcleo solo habla con `BrokerClient`. Cambiar de bróker = escribir un adaptador nuevo en `bot/broker/`.
- Credenciales **solo** vía variables de entorno / `.env` (excluido de git). Nunca hardcodeadas.
- `ta` sustituye a `pandas-ta` (abandonado, no soporta Python 3.14).
- Instrucciones para agentes de IA: ver [AGENTS.md](AGENTS.md).
