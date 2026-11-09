# AGENTS.md

Guía para agentes de IA y colaboradores que trabajan en este repositorio.

## Proyecto

Bot autónomo de opciones binarias en **IQ Option**, en Python (el adaptador Exnova queda como fallback). Proyecto de operación seria — la señal debe demostrar edge antes de operar capital real. Proyecto completo y decisiones de arquitectura en **`plan.md`** (fuente única de verdad; léelo antes de hacer cambios de alcance).

- Fase 1 (entorno, menú, BrokerClient/ExnovaAdapter) **completa**.
- Fase 2 (Machine Learning) **completa**: entrenamiento walk-forward, calibración, SHAP, export `.pkl`. Historial ✅, features ✅.
- Fase 3.6 (segundo bróker) **completa**: IQ Option con `IqOptionAdapter` + `IqOptionWSClient` (misma familia Quadcode, auth por ssid de navegador). Validado end-to-end en DEMO real: 1m turbo, 15m y 30m binaria. El bróker no aporta precisión al modelo — solo transporte de datos y ejecución.
- **Estado de señal (importante):** el backtest ML con 5m + features técnicos da ~50% accuracy y **expectancy negativa** (−0.08 a −0.17 con payout 80%). **ML descartado.** La única línea activa es **NORMAL 5m exhaustion** (ver `Context.md` §2): 3 pares `EURUSD-op, NZDUSD-op, EURGBP-op`, expiración **30m**, ventana operable **08:00–10:59 + 13:00–13:59 UTC**, payout IQ actual **0,87–0,90** con `MIN_PAYOUT=0.86`. **OTC suspendido**: en días operables da ~53,6 % a 15m = breakeven; el 67–100 % viejo incluía días con el activo cerrado y no era operable.
- **Producción (09-nov):** el runner corre en **Oracle Cloud**, no en la laptop. Imagen `ghcr.io/angelrmatoz/exnova-bot-runner:latest` (Docker/GHCR) con ENTRYPOINT `normal_five --broker iqoption`; `systemd` timer `exnova-runner.timer` a las **07:55 UTC**. `compose.runner.yml` fija `--stake 1000`. La tarea Windows `ExnovaNormal0813` está **deshabilitada** para evitar órdenes duplicadas. IQ usa `ssid` de navegador: **caduca** y hay que refrescarlo en Oracle. Detalle en `Context.md` §1 y §15.

## Entorno

- **Python 3.14 + uv** (usa `uv` para deps y ejecución, no pip).
- SO Windows; shell PowerShell 7 (`pwsh`). Evita heredocs bash — escribe un script temporal si necesitas bloques multi-línea.
- **Desarrollo local:** laptop Windows con Python 3.14 + `uv`; sirve para tests, backtests y `--dry-run`. **La laptop ya no ejecuta el bot en producción.**
- **Producción:** Oracle Cloud Ubuntu, Docker 29.1.3 + Compose 2.40.3, 1 GB RAM + 2 GB swap, 48 GB disco. Runner en `/opt/exnova-bot`; host y llave SSH fuera del repo.
- `plan.md` usa LF. Respeta el estilo de archivo existente.
- Clave del layout de imports: corre siempre desde la raíz del repo (`uv run python -m ...`), nunca desde `bot/`.
- Tests: `uv run pytest tests` (152 tests verdes; `pythonpath=["."]` ya configurado en pyproject.toml).
- Cuenta DEMO / PRACTICE. Zona operador UTC−4 (RD), bróker habla UTC. Estado vivo del proyecto en **`Context.md`** (handoff entre sesiones; actualizarlo al cerrar el día).

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

# Sesión NORMAL activa en IQ (exhaustion 5m, 30m, 1k, máx 3/sesión)
uv run python -m bot.scripts.normal_five --broker iqoption --dry-run   # no opera: chequea conexión, balance y señal
uv run python -m bot.scripts.normal_five --broker exnova --dry-run     # fallback Exnova
uv run python -m bot.scripts.asset_hours EURUSD-op NZDUSD-op EURGBP-op --hours 14  # schedule en vivo
uv run python -m bot.scripts.anchor_scan --fx        # horarios OTC (referencia; OTC suspendido)

# Producción Oracle (SSH; host/llave fuera del repo)
ssh ubuntu@<oracle-host> 'systemctl list-timers exnova-runner.timer'
ssh ubuntu@<oracle-host> 'journalctl -u exnova-runner.service -n 100 --no-pager'
ssh ubuntu@<oracle-host> 'cd /opt/exnova-bot && sudo -H -u ubuntu -g docker docker compose -f compose.runner.yml pull'
```

Verificar imports tras mover archivos: `uv run python -c "from <modulo> import ..."`.

## Arquitectura (reglas no negociables)

- La conexión con el bróker es vía cliente WebSocket propio: `ExnovaWSClient` (`bot/broker/exnova_ws.py`) e `IqOptionWSClient` (`bot/broker/iqoption_ws.py`, auth por **ssid** de navegador — el login HTTP de IQ responde 403). El vendor `exnovaapi` fue **eliminado** — no reintroducirlo. El núcleo solo conoce `BrokerClient` (`bot/broker/base.py`). Cambiar de bróker = nuevo adaptador, nada más.
- `IqOptionAdapter.place_order` es el único que debe llamar `IqOptionWSClient.buy()`: `buy` devuelve tupla `(ok, order_id)`. No usar `buy()` directo como order_id (el id va dentro de la tupla).
- La lógica pura (features, history, ML) no importa el bróker; recibe datos vía parámetros/callables.
- `main.py` corre `run_session` en bucle: tras cada sesión (`choose_after_session`) elige esperar 1h (`time.sleep(3600)`), re-analizar ya (espera vela nueva dentro de `run_session`) o salir.
- Runner activo `bot/scripts/normal_five.py`: `PAIRS=(EURUSD-op,NZDUSD-op,EURGBP-op)`, `HOURS={8,9,10,13}`, stake 1.000, expiración `30m`, `check_result(timeout=2400)`. Kill-switch: 30 resueltas, parar si win < 56 %. **Producción:** `exnova-runner.timer` en Oracle a las 07:55 UTC; `ExecStartPre` hace `docker compose pull` de `:latest`. El ENTRYPOINT de la imagen usa `--broker iqoption`; `compose.runner.yml` fija `--stake 1000`. La tarea Windows `ExnovaNormal0813` está deshabilitada. **IQ depende de `IQ_OPTION_SSID`; si caduca, el runner falla con `ssid inválido o sesión expirada`.**
- Imagen: `Dockerfile.runner` (multi-stage, non-root, solo deps del runner), `requirements-runner.txt`, `compose.runner.yml`; GHCR `ghcr.io/angelrmatoz/exnova-bot-runner`. El workflow `docker-runner.yml` corre tests y publica `:dev`/`:latest` con actions Node 24.
- **Nunca dos runners:** si Oracle está activo, Windows debe estar deshabilitado. Dos runners duplican órdenes.
- Exhaustion sobre vela 5m cerrada: rango ≥2×ATR14, cuerpo ≥60 %, cierre fuera Bollinger(20,2), excluye velas con RSI extremo. Entrada al open siguiente.
- Schedule manda: los `-op` cierran 18:00–19:30 UTC (verificado en vivo 04-nov; 19–22 UTC queda CLOSED aunque el backtest tenga velas). `normal_five` filtra por schedule: `broker.is_open()` lee las ventanas de initialization-data y omite pares cerrados (y sale con 0 ops si ninguno abre). El timer de Oracle corre solo Mon-Fri. Revisar con `asset_hours.py` antes de cada sesión.
- WS frágil: un corte (`WebSocketConnectionClosedException`) mata el runner salvo que el tramo tenga reintento (hoy solo la lectura de velas del loop lo tiene; visto 05-nov 10:40 UTC). Si tocas el loop, conserva el reintento y no lo conviertas en `break` silencioso.
- `trade_logs.market_type`: `NORMAL` (sesión activa) vs `ANCHOR` (OTC suspendido, referencia en `C:\Tools\anchor_*.py`).

## Operación Oracle y despliegue

- **Timer:** `exnova-runner.timer` dispara `exnova-runner.service` a las **07:55 UTC**. El servicio hace `docker compose pull` de `:latest` y luego `docker compose run --rm -T runner`; el ENTRYPOINT de la imagen ya pasa `--broker iqoption` y compose fija `--stake 1000`.
- **Pre-sesión (03:45 RD):** `systemctl list-timers exnova-runner.timer`, `systemctl is-active exnova-runner.service`, `docker compose ps`, `free -h`, `df -h`, `asset_hours.py` de los 3 pares, payout y evento macro del día.
- **Post-sesión:** `journalctl -u exnova-runner.service --since today`, revisar `trade_logs` de `NORMAL`, PnL y winrate. No cambiar la estrategia por una racha.
- **Pull manual:** `cd /opt/exnova-bot && sudo -H -u ubuntu -g docker docker compose -f compose.runner.yml pull`.
- **Rollback:** fijar en `compose.runner.yml` el tag `sha-<commit>` anterior, `pull`, `run --dry-run` y dejar el timer. No reactivar Windows sin desactivar antes el timer.
- **Incidentes:** WS caído → revisar el reintento de velas; `pull` falla → usa la imagen cacheada; timer perdido → `systemctl start exnova-runner.service` solo si la ventana sigue abierta; DB → backup antes de tocar. **IQ ssid vencido** → `connect` devuelve `ssid inválido o sesión expirada`; sacar cookie nueva del navegador y actualizar `IQ_OPTION_SSID` en `/opt/exnova-bot/.env`.
- **Nunca dos runners:** Oracle activo ⇒ Windows `ExnovaNormal0813` deshabilitado.
- **Despliegue:** commit en `dev` → CI → PR `dev`→`main` → merge → `:latest` → Oracle hace `pull` en la siguiente sesión. No cambiar `PAIRS`, `HOURS`, `MIN_PAYOUT`, stake ni máx 3 sin backtest + PR.
- **Payout:** `MIN_PAYOUT=0.86` no es decorativo: payout 0,86 ⇒ breakeven 53,76 %. IQ paga 0,87–0,90 en los 3 pares, pero el filtro se mantiene. Bajarlo sin backtest cambia la expectancy. No quitar el filtro por preferencia.
- **Handoff:** `Context.md` es local/untracked; `AGENTS.md` sí se commitea. No commitear `.env`, `db/`, `trader/` ni llaves.

## Estructura

```text
bot/
├── broker/       # BrokerClient (base.py), MockBrokerAdapter (mock.py),
│                 # ExnovaAdapter (exnova.py), ExnovaWSClient (exnova_ws.py),
│                 # IqOptionAdapter (iqoption.py), IqOptionWSClient (iqoption_ws.py)
├── ml/           # features.py (16 col, lib ta); multi_tf.py (MTLF 15m/1h);
│                 # train.py, calibrate.py, backtest.py, shap_analysis.py, export_model.py
├── scripts/      # fetch_history.py, build_features.py (CLIs con --in/--out); backtest_mock.py
│                 # normal_five.py (runner activo: 3 pares, HOURS={8,9,10,13}, 30m)
│                 # anchor_scan.py (mapa 172 anclas OTC, referencia); asset_hours.py (schedule en vivo)
Dockerfile.runner  # imagen slim del runner (multi-stage, non-root)
requirements-runner.txt
compose.runner.yml # servicio runner, env_file, volumen db, log rotation
deploy/            # exnova-runner.service / exnova-runner.timer (Oracle systemd)
.github/workflows/docker-runner.yml  # tests + build/push GHCR
├── schedule.py   # ventanas [inicio, fin] epoch UTC de initialization-data; is_open/next_close/next_open
├── db.py         # SQLite: model_versions (register_model); trade_logs (log_trade/log_trades) + get_today_pnl/get_loss_streak
├── config.py     # lee .env, valida credenciales (Exnova + IQ Option)
├── history.py    # fetch_candle_history (paginación 1000/batch)
├── menu.py       # choose_broker / choose_market / choose_account_type / choose_timeframe /
│                 # choose_stake / choose_assets / choose_after_session
└── session.py    # run_session: regla de 3 operaciones; con wait=True espera vela NUEVA
                  # antes de cada operación (análisis fresco, sin depender del reloj local)
data/5m/          # 22 CSV: 11 `-op` + 11 `-OTC` ene–nov 2026; 1m solo ~30–42 días
models/           # eurusd_5m.pkl (modelo exportado)
tests/            # pytest: wsutil.py (helpers WS), iq_mock.py (mock server IQ), conftest.py
                  # test_exnova_ws_*.py, test_iqoption_ws_*.py, test_iqoption_adapter_integration.py
                  # test_anchor_scan.py, test_schedule.py
bot_data.db       # SQLite (model_versions; trade_logs)
```

## Datos y ML

- Universo binario: IQ **273 binarias + 255 turbo**; Exnova **262 + 242**. Solo 22 tienen CSV 5m local; el resto solo se revisa en vivo. El bot opera 3 pares FX NORMAL.
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
- Oracle: `.env` en `/opt/exnova-bot/.env` (600); `db/` en 700 y `bot_data.db` en 600, propiedad UID 10001. GHCR usa un PAT clásico `read:packages` guardado en `/home/ubuntu/.docker/config.json` (600). Ni el PAT ni la llave SSH van al repo.
- `Context.md`, `trader/`, `db/` y `.env` son locales; no commitearlos.

## Convenciones de código

- Responder al usuario en **español**; identificadores/código en inglés.
- **No añadir comentarios** al código salvo que se pidan.
- Modo ponytail: la solución más simple que funciona (YAGNI). Una carpeta solo se crea cuando hay 2-3+ archivos relacionados, no para 1 archivo.
- Al terminar una tarea, verificar con una ejecución real o `import` (no asumir).
