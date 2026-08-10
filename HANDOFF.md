# Handoff — Bot de opciones binarias Exnova

Contexto de la sesión para continuar en otro chat. Leer **`plan.md`** (fuente única de verdad) antes de cambios de alcance.

## Proyecto

Bot autónomo de opciones binarias en Python. **Proyecto de operación seria — la señal debe demostrar edge (expectancy positiva) antes de operar capital real.**

**Nota (última sesión):** se **eliminó Gemini del plan** (filtrado macro con IA descartado — sin edge predictivo no aporta nada). Arquitectura reducida de 3 → **2 capas** (Señal + Ejecución). Las vars `GEMINI_*` quedan en `.env` como config inofensiva.

## Entorno

- Python 3.14 + **uv** (nunca pip). Windows + PowerShell 7 (`pwsh`).
- Ejecutar SIEMPRE desde la raíz del repo: `uv run python -m ...` (nunca desde `bot/`).
- Evitar heredocs bash; escribir un script temporal si se necesitan bloques multi-línea.
- `plan.md` usa LF. Respetar estilo de archivos existentes.
- Convenciones: hablar en español, identificadores/código en inglés, **sin comentarios** de código salvo pedido. Estilo "ponytail" (YAGNI, solución más simple).

## Reglas de arquitectura (no negociables)

1. **`exnovaapi` no se importa en el núcleo ni en `bot/broker/exnova.py`** (migrado a `ExnovaWSClient`). El núcleo solo conoce `BrokerClient` (`bot/broker/base.py`).
2. El vendor `exnovaapi` fue **eliminado** — no reintroducirlo.
3. La lógica pura (features, ML, history) no importa el bróker; recibe datos vía parámetros/callables.
4. Cambiar de bróker = nuevo adaptador, nada más.

## Estado de fases

- **Fase 1** ✅ — entorno, menú, `BrokerClient`, `ExnovaAdapter`.
- **Fase 2** ✅ — ML (walk-forward, calibración, SHAP, export .pkl). Historial y features listos.
- **Fase 3** ✅ — SQLite (`trade_logs`), `MockBrokerAdapter`, `backtest_mock.py`. Completada hoy (ver abajo).
- **Fase 3.5** ✅ — cliente WebSocket Exnova propio (`ExnovaWSClient`): SSID auth, saldo multi-cuenta por `account_type`, histórico paginado, stream de velas, buy/sell, confirmación y resultado, Ping/Pong, reconexión con exponential backoff (2s→30s). `ExnovaAdapter` migrado del vendor, sin imports de `exnovaapi`. Paridad cubierta por tests (45 tests, suite verde). **Requisito antes de operar 24/7 en demo** — no se opera continuo sobre el vendor de bajo nivel.
- **Fase 4** ⏳ — unir las 2 capas en el bucle principal, validar **150 operaciones en mercado Normal + 150 en OTC** (por separado). Solo validación preliminar, no garantía de cuenta real.
- **Fase 5** ⏳ — Dockerfile + docker-compose, despliegue en Oracle Cloud Free Tier.
- **Fase 6** ⏳ — dashboard (Streamlit/Plotly Dash) sobre `bot_data.db`: PnL acumulado, win rate por par, calibración confianza vs resultado, máximo drawdown.

## Estado de señal (crítico, ser honestos)

Backtest 5m + features técnicos da **~50% accuracy y expectativa negativa** (−0.08 a −0.17 con payout 0.80). **No hay edge confirmado.** No asumir que el modelo aporta valor sin verlo.

**Barridos completos (todos sin edge a día de hoy):**
- **27 configs ML** (5m/15m/1h × horizon 1/2/4 × EURUSD/GBPUSD/USDJPY): todo ~50%.
- **9 filtros RSI** (20/80, 30/70, 10/90): sin edge.
- **24 configs Fibonacci** con pivotes de swing (0.382–0.786 × CALL/PUT × 3 pares, 5m): sin edge. El "FIFO 61.8% funciona" solo con lookahead (pivote confirmado sin leakage = ~50%).
- **72 configs Fibonacci con anclas max/min absolutos** de ventana rodante (3 pares × W 50/100/288 × 4 niveles × CALL/PUT, 5m): mejor 54.2%, sin edge.
- **Fibonacci 1m en OTC real de IQ** (1000 velas EURUSD-OTC): sin confirmación ~50%. **Con vela de confirmación** (pin bar / engulfing) el winrate sube: pin bar 0.382 → 55.9% (34 trades, exp +0.006), 0.786 any → **61.3%** (31 trades, exp +0.103). ⚠️ **Muestra demasiado pequeña para declarar edge** (error estándar ±9%); probamos 12 combos, saldrán falsos positivos por azar.

**Lección clave de las fuentes:** el retroceso Fibonacci **nunca se opera solo** — hay que esperar **vela de confirmación** (pin bar, engulfing) al tocar el nivel. Ese es el filtro discrecional que el usuario aplica a ojo y que los tests mecánicos sin confirmación no capturan. Sigue siendo hipótesis no confirmada: se necesitan 300-500 trades confirmados (≈10k velas 1m OTC, ~7 días) para poder estadístico.

## Estructura

```text
bot/
├── broker/       # base.py (BrokerClient), factory.py (build_broker por operador),
│                 # exnova_ws.py (ExnovaWSClient propio), exnova.py (ExnovaAdapter vía ExnovaWSClient),
│                 # iqoption_ws.py (IqOptionWSClient propio), iqoption.py (IqOptionAdapter),
│                 # mock.py (MockBrokerAdapter)
├── ml/           # features.py (16 col, lib `ta`), multi_tf.py (MTLF 15m/1h, merge_asof solo velas cerradas),
│                 # train.py (walk-forward, feature_columns detecta base/MTLF), calibrate.py, backtest.py,
│                 # shap_analysis.py, export_model.py
├── scripts/      # fetch_history.py, build_features.py, backtest_mock.py
├── db.py         # SQLite: model_versions (register_model); trade_logs (log_trade, log_trades,
│                 #   get_today_pnl, get_loss_streak)
├── config.py     # lee .env; exnova_credentials, iqoption_credentials (solo ssid obligatorio),
│                 #   configured_brokers (lista operadores listos para el menú)
├── history.py    # fetch_candle_history (paginación 1000/batch)
└── menu.py       # choose_broker (operador desde configured_brokers) / choose_market / choose_assets
data/5m/          # EURUSD.csv, GBPUSD.csv, USDJPY.csv; .features.csv; .features.oos.csv; .mtl.csv
models/           # eurusd_5m.pkl
bot_data.db       # SQLite (model_versions; trade_logs)
```

## Comandos clave

```bash
uv add <paquete>
uv run python -m bot.scripts.fetch_history --pair EURUSD --timeframe 5m --count 10000
uv run python -m bot.ml.train --in data/5m/EURUSD.features.csv
uv run python -m bot.ml.calibrate --in data/5m/EURUSD.features.csv
uv run python -m bot.ml.backtest --in data/5m/EURUSD.features.csv --payout 0.80
uv run python -m bot.ml.shap_analysis --in data/5m/EURUSD.features.csv
uv run python -m bot.ml.export_model --in data/5m/EURUSD.features.csv --out models/eurusd_5m.pkl
uv run python -m bot.ml.multi_tf --in data/5m/EURUSD.csv --out data/5m/EURUSD.mtl.csv
uv run python -m bot.scripts.backtest_mock --pairs data/5m/EURUSD.csv,data/5m/GBPUSD.csv
uv run python -m bot.scripts.backtest_mock --pairs data/5m/EURUSD.csv --payouts payouts.csv
uv run python main.py   # menú interactivo (elige operador → mercado → divisas), requiere .env
```

## Última entrega (CLI multi-bróker + experimentos Fibonacci)

**CLI multi-bróker (Fase 1, `main.py`):**
- `bot/config.py` — `configured_brokers()` lista operadores con credenciales completas en `.env` (exnova si email+password, iqoption si ssid). `iqoption_credentials()` ahora **solo exige el ssid** (email/password opcionales; antes exigía los 4 y rompía si faltaba alguno).
- `bot/broker/factory.py` (nuevo) — `build_broker(name, market_type)` devuelve `ExnovaAdapter` o `IqOptionAdapter`; núcleo sigue sin conocerlos.
- `bot/menu.py` — `choose_broker()` lee `configured_brokers()` y deja elegir (1. Exnova, 2. IQ Option, ...) dinámicamente, no hardcodeado.
- `main.py` — flujo: `choose_broker() → choose_market() → build_broker() → connect() → choose_assets()`.
- 95 tests verdes. Añadir 3er bróker = adaptador + credenciales en `.env` + entrada en factory.

**Experimentos Fibonacci OTC (Temp/opencode/, fuera del repo):**
- `fetch_iq_1m.py` → bajó **1000 velas 1m EURUSD-OTC** reales de IQ (`otc_eurusd_1m_history.csv`) vía `IqOptionWSClient.get_candles("EURUSD-OTC","1m",1000)` (funciona, trae histórico de golpe, no 1/min).
- `fib_1m_otc.py`, `fib_1m_otc2.py` (sin confirmación, ~50%), `fib_1m_confirm.py` (**con** pin bar/engulfing → 55.9%/61.3% pero n=31-34, no significativo).
- `fib_abs_test.py` — anclas max/min absolutos, sin edge.
- Captura continua sigue corriendo: `capture_iq.py` (60s EURUSD-OTC, active 76) → `otc_live_76_60.csv`.

## Última entrega (Fase 3, hoy)

- **`bot/db.py`** — tabla `trade_logs` (timestamp, pair, market_type, signal, confidence, gate_passed, result, pnl, features_snapshot, model_version_id) y helpers `log_trade`, `log_trades` (batch), `get_today_pnl`, `get_loss_streak` (LOSS consecutivos; SKIPPED no rompe racha).
- **`bot/broker/mock.py`** — `MockBrokerAdapter(BrokerClient)`: resuelve órdenes sobre velas históricas (dict par→DataFrame OHLC), cursor simulado, duración→pasos, `check_result` devuelve `("WIN"/"LOSS", pnl)`, `get_payout`, `get_balance`.
- **`bot/scripts/backtest_mock.py`** — backtest offline: estrategia momentum 5m, escribe en SQLite en batch, reporte por par y curva de payouts.
- **Resultado**: 182,994 operaciones mock (3 pares × ~61k). Win rate ~48%, expectancy −1.3 con stake 10 (payout 0.80) → no hay edge. Coherente con el estado de señal.
- Docs actualizados: `plan.md` Fase 3 ✅, `AGENTS.md`, `README.md`.

## Última entrega (Fase 3.5, sesión de migración del vendor a WS propio)

**Contexto:** `ExnovaAdapter` dependía del vendor `exnovaapi` (port de bajo nivel, sin mantenimiento). Se migró por completo al cliente WebSocket propio `ExnovaWSClient` y se **eliminó** `bot/vendor/exnovaapi`.

Cambios en **`bot/broker/exnova_ws.py`**:
- Constante de módulo `BALANCE_TYPE_ID = {"REAL": 1, "PRACTICE": 4, "TOURNAMENT": 2}` (mapeo real del vendor, verificado). El handler `profile` en `_on_message` ahora elige `balance_id` según el `account_type` del cliente — antes estaba hardcodeado a `type == 4` (PRACTICE).
- Añadido `check_connect()` → `self._connected.is_set()` (devuelve bool, no bloquea).
- `_active_id(pair)` tolerante: 1) match exacto en `self._actives`; 2) fallback comparando `pair.replace(".", "").upper()` contra cada clave sin puntos; 3) `ValueError` si no se encuentra. Necesario porque `get_available_assets()` devuelve nombres públicos (ej. `"USD"`, `"USD-OTC"`) que difieren de claves internas p.  ej. `"EURUSD"`).
- `connect` con backoff exponencial 2s→30s ya existente (no usado en esta sesión, verificado por grep).

**`bot/broker/exnova.py`** reescrito completo: `ExnovaAdapter` envuelve `ExnovaWSClient` directamente; retirado el import de `exnovaapi` y el `sys.path`/vendor hack. API pública intacta (`BrokerClient`): `connect`, `connect_2fa`, `check_connect`, `disconnect`, `get_candles` (delega en el WS client, que ya normaliza a `{time, open, close, high, low}`), `get_available_assets` (filtra por `market_type`: OTC → `endswith("-OTC")`; NORMAL → sin sufijo), `place_order` (mapea `buy(...) -> (ok, order_id)` a order_id o None), `check_result`, `get_balance`, `get_payout`. `ExnovaAdapter` instancia `ExnovaWSClient(email, password, account_type)`; conserva `ssid`/`balance_id` como atributos necesarios para `place_order`.

**Tests (suite 45 passed, 0.35s):**
- `tests/conftest.py` — fixture `adapter`: `ExnovaAdapter("t@t.com", "pw", account_type="PRACTICE", market_type="OTC")`, fuerza `ssid="test"` y `balance_id=4`, teardown hace `ad.disconnect()`.
- `tests/test_exnova_adapter_integration.py` (nuevo, 7 tests): paridad adapter→WS client — `get_candles` normalizado, filtro OTC devuelve `["USD-OTC"]` / NORMAL `["USD"]`, `place_order`→`check_result` (`order_id` con prefijo `result-`, resultado `"loose"`, pnl −1.0), balance 10000.0, payout 0.8, `check_connect` False antes del start y True después.
- Se usa `monkeypatch.setattr(exnova_ws, "WSS_URL", mock_server.url)` para apuntar al mock server WS local.

**Docs actualizados:** `plan.md` (Fase 3.5 todos los checkboxes ✅, incl. "Eliminar vendor"), `AGENTS.md`, `README.md`, `HANDOFF.md` (este archivo).

## Gotchas aprendidos hoy (importantes)

1. `log_trade` individual abre conexión SQLite por operación → 60k+ operaciones = cuelgues y timeouts. **Usar el batch `log_trades`** (una transacción por par).
2. Si un comando se cuelga y el shell corta, quedan **procesos python zombie** sosteniendo locks. Matarlos: `Get-Process python | Stop-Process -Force`.
3. `bot_data.db` contiene ya 182,994 filas `MOCK` de prueba (dev). Si se quiere partir limpio: `DELETE FROM trade_logs`.
4. `check_result` (mock) resuelve con vela de expiración (cierre > apertura para CALL); misma semántica que `bot.ml.backtest.py`.

## Gotchas de la migración (Fase 3.5, sesión)

1. El mapping del vendor para `balance_type` es **1=REAL, 4=PRACTICE, 2=TOURNAMENT**. No asumir `4` siempre — el cliente selecciona por `account_type`.
2. Los nombres de activos del WS (ej. `"USD"`) NO son los del CLI (`"EURUSD"`). Fuente de verdad: `get_available_assets()` del adapter; luego se usa la resolución tolerante de `_active_id`.
3. `ExnovaAdapter` instancia `ExnovaWSClient` **siempre** — el adaptador ya no maneja conexión a "real" de forma separada; el `account_type` controla el saldo.
4. Para mockear conexión WS en tests: `monkeypatch.setattr(exnova_ws, "WSS_URL", mock_server.url)`.
5. Al eliminar el vendor, vigilar que ningún import siga refiriendo a `exnovaapi` (queda solo docstring histórico).

## Pendientes (candidatos a siguiente sesión)

- **Fase 4** básica: bucle principal Features → ML → gates → orden, iterable sobre `MockBrokerAdapter` sin riesgo (ya se puede operar con el adaptador real sobre `ExnovaWSClient` en demo).
- **Acumular datos 1m OTC**: dejar corriendo la captura en background varios días para llegar a ~10k velas 1m (~7 días OTC). Con eso re-ejecutar `fib_1m_confirm.py` — el filtro de confirmación dispara solo en 2-5% de velas, se necesitan 300-500 trades confirmados para significancia estadística real.
- **Modo registro manual** (propuesto, no construido): CLI donde el usuario apunta sus trades a ojo (entrada, dirección, resultado) guardándolos en `trade_logs` — medir su winrate real contra la versión mecánica.
- **Decisión**: si el Fibonacci 1m OTC + confirmación no se confirma con datos suficientes, documentar en `plan.md` y cerrar como no-edge (como el resto del barrido).
- **Lección de proyectos validados** (`binary-options-ml`, `ATLAS`): filtro de confianza (|prob−0.5| ≥ umbral, abstener = edge), expiry 15m > 1 vela, walk-forward + re-entrenar con datos IQ OTC. ⚠️ `ATLAS` midió OTC de IQ en **47.1%** (bajo moneda al aire) con modelo sin confirmación humana.