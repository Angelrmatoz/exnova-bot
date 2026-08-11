# AGENTS.md

Guía para agentes de IA y colaboradores que trabajan en este repositorio.

## Proyecto

Bot autónomo de opciones binarias en Exnova, en Python. Proyecto de operación seria — la señal debe demostrar edge antes de operar capital real. Proyecto completo y decisiones de arquitectura en **`plan.md`** (fuente única de verdad; léelo antes de hacer cambios de alcance).

- Fase 1 (entorno, menú, BrokerClient/ExnovaAdapter) **completa**.
- Fase 2 (Machine Learning) **completa**: entrenamiento walk-forward, calibración, SHAP, export `.pkl`. Historial ✅, features ✅.
- Fase 3.6 (segundo bróker) **completa**: IQ Option con `IqOptionAdapter` + `IqOptionWSClient` (misma familia Quadcode, auth por ssid de navegador). Validado end-to-end en DEMO real. El bróker no aporta precisión al modelo — solo transporte de datos y ejecución.
- **Estado de señal (importante):** el backtest con 5m + features técnicos da ~50% accuracy y **expectancy negativa** (−0.08 a −0.17 con payout 80%). **No hay edge confirmado** a día de hoy. Ver resultados en `calibrate.py`/`backtest.py` antes de asumir que el modelo aporta valor.

## Entorno

- **Python 3.14 + uv** (usa `uv` para deps y ejecución, no pip).
- SO Windows; shell PowerShell 7 (`pwsh`). Evita heredocs bash — escribe un script temporal si necesitas bloques multi-línea.
- `plan.md` usa LF. Respeta el estilo de archivo existente.
- Clave del layout de imports: corre siempre desde la raíz del repo (`uv run python -m ...`), nunca desde `bot/`.
- Tests: `uv run pytest tests` (105 tests verdes; `pythonpath=["."]` ya configurado en pyproject.toml).

## Comandos

```bash
uv add <paquete>                 # añadir dependencia
uv run python -m bot.scripts.build_features --in data/5m/EURUSD.csv
uv run python -m bot.scripts.fetch_history --pair EURUSD --timeframe 5m --count 10000
uv run python main.py            # menú interactivo (requiere .env)

# Pipeline ML (Fase 2)
uv run python -m bot.ml.train --in data/5m/EURUSD.features.csv        # walk-forward
uv run python -m bot.ml.calibrate --in data/5m/EURUSD.features.csv   # curva calibración + guarda OOS
uv run python -m bot.ml.backtest --in data/5m/EURUSD.features.csv --payout 0.80
uv run python -m bot.ml.shap_analysis --in data/5m/EURUSD.features.csv
uv run python -m bot.ml.export_model --in data/5m/EURUSD.features.csv --out models/eurusd_5m.pkl
uv run python -m bot.ml.multi_tf --in data/5m/EURUSD.csv --out data/5m/EURUSD.mtl.csv  # features MTLF

# Backtest sin conexión (Fase 3)
uv run python -m bot.scripts.backtest_mock --pairs data/5m/EURUSD.csv,data/5m/GBPUSD.csv   # mock broker + trade_logs
uv run python -m bot.scripts.backtest_mock --pairs data/5m/EURUSD.csv --payouts payouts.csv  # curva de payouts por par

# Dashboard (Fase 6)
uv run streamlit run bot/scripts/dashboard.py   # panel sobre bot_data.db: PnL acumulado, win rate por par, calibración, drawdown
```

Verificar imports tras mover archivos: `uv run python -c "from <modulo> import ..."`.

## Arquitectura (reglas no negociables)

- La conexión con el bróker es vía cliente WebSocket propio: `ExnovaWSClient` (`bot/broker/exnova_ws.py`) e `IqOptionWSClient` (`bot/broker/iqoption_ws.py`, auth por **ssid** de navegador — el login HTTP de IQ responde 403). El vendor `exnovaapi` fue **eliminado** — no reintroducirlo. El núcleo solo conoce `BrokerClient` (`bot/broker/base.py`). Cambiar de bróker = nuevo adaptador, nada más.
- `IqOptionAdapter.place_order` es el único que debe llamar `IqOptionWSClient.buy()`: `buy` devuelve tupla `(ok, order_id)`. No usar `buy()` directo como order_id (el id va dentro de la tupla).
- La lógica pura (features, history, ML) no importa el bróker; recibe datos vía parámetros/callables.
- `main.py` corre `run_session` en bucle: tras cada sesión (`choose_after_session`) elige esperar 1h (`time.sleep(3600)`), re-analizar ya (espera vela nueva dentro de `run_session`) o salir.

## Estructura

```text
bot/
├── broker/       # BrokerClient (base.py), MockBrokerAdapter (mock.py),
│                 # ExnovaAdapter (exnova.py), ExnovaWSClient (exnova_ws.py),
│                 # IqOptionAdapter (iqoption.py), IqOptionWSClient (iqoption_ws.py)
├── ml/           # features.py (16 col, lib ta); multi_tf.py (MTLF 15m/1h);
│                 # train.py, calibrate.py, backtest.py, shap_analysis.py, export_model.py
├── scripts/      # fetch_history.py, build_features.py (CLIs con --in/--out); backtest_mock.py
├── db.py         # SQLite: model_versions (register_model); trade_logs (log_trade/log_trades) + get_today_pnl/get_loss_streak
├── config.py     # lee .env, valida credenciales (Exnova + IQ Option)
├── history.py    # fetch_candle_history (paginación 1000/batch)
├── menu.py       # choose_broker / choose_market / choose_account_type / choose_timeframe /
│                 # choose_stake / choose_assets / choose_after_session
└── session.py    # run_session: regla de 3 operaciones; con wait=True espera vela NUEVA
                  # antes de cada operación (análisis fresco, sin depender del reloj local)
data/5m/          # EURUSD.csv, EURUSD.features.csv, EURUSD.features.oos.csv, EURUSD.mtl.csv
models/           # eurusd_5m.pkl (modelo exportado)
tests/            # pytest: wsutil.py (helpers WS), iq_mock.py (mock server IQ), conftest.py
                  # test_exnova_ws_*.py, test_iqoption_ws_*.py, test_iqoption_adapter_integration.py
bot_data.db       # SQLite (model_versions; trade_logs)
```

## Datos y ML

- Features: `build_features()` (bot/ml/features.py) → 16 columnas (`FEATURE_COLUMNS`). Las ~49 primeras filas tienen NaN de warm-up (EMA50/ATR14) — aplicar `dropna()` en entrenamiento.
- Features MTLF: `multi_tf.py` resamplea 5m→15m/1h con `merge_asof` **solo velas superiores cerradas** (anti-leakage). `MTL_COLUMNS` = `FEATURE_COLUMNS` + 8 de tendencia.
- `train.feature_columns(df)` detecta las columnas presentes (base o MTLF) — no hardcodear.
- `ta` sustituye a `pandas-ta` (abandonado, no soporta py3.14). No intentes reintroducirlo.
- El target (dirección vela t+1) se construye en la tarea de entrenamiento (`train.build_target`), no en features.
- Validación: **walk-forward (TimeSeriesSplit), nunca split aleatorio** — evita data leakage. `walk_forward` además devuelve predicciones OOS concatenadas (usa `backtest`/`calibrate`).
- Backtest (`backtest.py`) simula cuenta: CALL si proba>=0.5, resuelve con vela t+1, pnl con `--payout`. Espera: expectancy = win×payout − (1−win). Con payout 0.80 se necesita win > 55.6% para no perder.
- OOS de un run se guarda en `EURUSD.features.oos.csv` (y_true + y_prob) — reutilizable sin re-entrenar.

## Credenciales

- Todo secreto vía `.env` (excluido de git). Plantilla: `.env.example`.
- Nunca muestres ni hardcodees credenciales, tokens o claves.

## Convenciones de código

- Responder al usuario en **español**; identificadores/código en inglés.
- **No añadir comentarios** al código salvo que se pidan.
- Modo ponytail: la solución más simple que funciona (YAGNI). Una carpeta solo se crea cuando hay 2-3+ archivos relacionados, no para 1 archivo.
- Al terminar una tarea, verificar con una ejecución real o `import` (no asumir).
