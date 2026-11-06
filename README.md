# Exnova Bot

Sistema autónomo de opciones binarias en **Exnova**. Ejecuta la estrategia **NORMAL 5m exhaustion** en una instancia **Oracle Cloud**, con Docker, imagen GHCR, SQLite y control estricto de riesgo. Cuenta **DEMO / PRACTICE**.

[![CI](https://github.com/Angelrmatoz/exnova-bot/actions/workflows/ci.yml/badge.svg)](https://github.com/Angelrmatoz/exnova-bot/actions/workflows/ci.yml)
[![Docker runner](https://github.com/Angelrmatoz/exnova-bot/actions/workflows/docker-runner.yml/badge.svg)](https://github.com/Angelrmatoz/exnova-bot/actions/workflows/docker-runner.yml)

> **Estado de señal:** el edge **no está confirmado**. El backtest in-sample da 67,8 % en 230 señales, pero el forward real es **1W/0L**. Se opera solo en **DEMO**. No usar capital real hasta validar 30 operaciones resueltas y un tramo out-of-sample.

> **Riesgo:** las opciones binarias son instrumentos de alto riesgo. Exnova no tiene regulación reconocida (CySEC, FCA, CNMV). El bróker se trata como una dependencia intercambiable; el núcleo analítico no depende de él.

## Estado actual

| Tema | Estado |
|---|---|
| Estrategia | **NORMAL 5m exhaustion**, 30m, payout 0,86 |
| Pares | `EURUSD-op`, `NZDUSD-op`, `EURGBP-op` |
| Ventanas | 08:00–10:59 y 13:00–13:59 UTC (04:00–06:59 y 09:00–09:59 RD) |
| Stake | 10.000 DEMO por orden; máx 3/sesión; corte 2W/2L |
| Producción | Oracle Cloud Ubuntu, Docker 29.1.3, Compose 2.40.3 |
| Imagen | `ghcr.io/angelrmatoz/exnova-bot-runner:latest` |
| Timer | `exnova-runner.timer`, diario 07:55 UTC |
| Tarea Windows | `ExnovaNormal0813` deshabilitada |
| OTC | Suspendido: 0/11 con historia pasa el screener |
| ML | Descartado: ~50 % accuracy, expectancy negativa |
| Tests | 142 verdes en GitHub Actions |

## Qué hace

1. En cada vela de 5 minutos cerrada, dentro de las ventanas, revisa los 3 pares.
2. Exige cuatro condiciones:
   - rango de la vela ≥ 2× ATR14;
   - cuerpo ≥ 60 % del rango;
   - cierre fuera de Bollinger(20,2);
   - RSI no extremo.
3. Si la vela cerró **debajo** de la banda inferior, entra **CALL**; si cerró **arriba**, entra **PUT**.
4. Entra al open de la vela siguiente, con expiración **30 minutos** y stake fijo.
5. Registra el resultado en SQLite y aplica los límites de sesión.

### Lo que no hace

- No opera OTC.
- No usa Machine Learning en vivo; el modelo fue descartado.
- No promete ganar ni predice el mercado.
- No filtra noticias ni eventos macro (NFP, CPI, FOMC).
- No comprueba el schedule antes de ordenar; si el par está cerrado, la orden se rechaza.
- No usa las skills de trader en runtime; son herramientas de análisis externas.

## Arquitectura

```text
GitHub Actions
  ├── tests (pytest)
  └── build/push imagen → GHCR

Oracle Cloud
  └── systemd timer 07:55 UTC
        └── docker compose run runner
              ├── pull :latest
              ├── ExnovaWSClient (WebSocket)
              ├── estrategia 5m
              └── SQLite /app/db/bot_data.db
```

| Componente | Tecnología |
|---|---|
| Lenguaje | Python 3.14 + uv |
| Bróker | `BrokerClient` + `ExnovaAdapter` + `ExnovaWSClient` |
| Análisis | pandas + `ta` |
| Persistencia | SQLite (`model_versions`, `trade_logs`) |
| Ejecución | Docker + Docker Compose |
| Producción | Oracle Cloud + systemd |
| Distribución | GitHub Container Registry (GHCR) |
| CI/CD | GitHub Actions |

## Estrategia

| Parámetro | Valor |
|---|---|
| Timeframe | 5m |
| Expiración | 30m |
| Payout de referencia | 0,86 |
| Breakeven | 53,76 % |
| Stake | 10.000 |
| Máximo por sesión | 3 |
| Corte | 2W o 2L |
| Kill-switch | 30 resueltas con winrate <56 % |
| Pares | EURUSD-op, NZDUSD-op, EURGBP-op |
| Horas UTC | 8, 9, 10, 13 |

El detalle de la selección y del análisis está en `Context.md` (handoff local, no versionado) y en [`AGENTS.md`](AGENTS.md) (reglas del repo y runbook).

## Producción

La imagen se construye y publica desde GitHub Actions. Oracle no recibe pushes: **hace pull antes de cada sesión**.

```bash
# En Oracle
cd /opt/exnova-bot
sudo -H -u ubuntu -g docker docker compose -f compose.runner.yml pull
sudo -H -u ubuntu -g docker docker compose -f compose.runner.yml run --rm -T runner --dry-run
```

El servicio `exnova-runner.service` ejecuta:

```ini
ExecStartPre=-/usr/bin/docker compose -f compose.runner.yml pull
ExecStart=/usr/bin/docker compose -f compose.runner.yml run --rm -T runner
```

El timer dispara a las **07:55 UTC**. La tarea de Windows debe permanecer deshabilitada para no duplicar órdenes.

### Operación

```bash
systemctl list-timers exnova-runner.timer
systemctl is-active exnova-runner.service
journalctl -u exnova-runner.service -n 100 --no-pager
```

## Desarrollo local

Requiere Python 3.14, [uv](https://docs.astral.sh/uv/) y Docker opcional.

```bash
uv sync
cp .env.example .env   # credenciales DEMO; nunca commitear
uv run pytest tests
uv run python -m bot.scripts.normal_five --dry-run
uv run python -m bot.scripts.asset_hours EURUSD-op NZDUSD-op EURGBP-op --hours 14
```

### Construir la imagen del runner

```bash
docker build -f Dockerfile.runner -t ghcr.io/angelrmatoz/exnova-bot-runner:local .
```

## Estructura

```text
bot/
├── broker/       # BrokerClient, ExnovaAdapter/WS, IqOptionAdapter/WS, Mock
├── ml/           # features, multi_tf, train, calibrate, backtest, shap, export
├── scripts/      # normal_five, fetch_history, build_features, asset_hours, backtest_mock
├── db.py         # SQLite: model_versions + trade_logs
├── config.py     # .env: Exnova + IQ Option
├── history.py    # paginación de velas
├── schedule.py   # ventanas de apertura del bróker
└── session.py    # sesión interactiva de 3 operaciones

Dockerfile.runner              # imagen slim del runner (multi-stage, non-root)
requirements-runner.txt        # dependencias mínimas del runner
compose.runner.yml             # servicio Oracle: env, DB, logs
deploy/                        # exnova-runner.service / .timer
.github/workflows/             # CI + build/push GHCR
data/5m/                       # 22 CSV de investigación (11 NORMAL + 11 OTC)
bot_data.db                    # SQLite local (ignorado)
main.py                        # menú interactivo
```

## Datos y validación

- 22 CSV 5m (11 `-op` + 11 `-OTC`) hasta 03-nov-2026.
- El bróker expone 262 binarias; 190 activas; 85 son FX. Solo 22 tienen historia local.
- OTC: 0/11 pasa el screener; mejor slot 55–57 %, insuficiente.
- In-sample: 230 señales, 67,8 % win, DD 3,18 %, IC95 61,5–73,5 %.
- Sep–nov: 63,4 % n41, IC95 48,1–76,4 % (cruza breakeven).
- Forward: 1W/0L.
- `backtest-expert`: 60/100, `VALIDATION_REQUIRED`.

No se cambian pares, horas, stake ni payout sin backtest, PR y validación forward. Un winrate de 30 días es ruido, no edge.

## Seguridad

- `.env` y credenciales fuera de git.
- La llave SSH y el PAT de GHCR (`read:packages`) viven fuera del repo.
- El paquete GHCR puede ser privado; Oracle usa un PAT de solo lectura.
- Nunca ejecutar dos runners a la vez.
- No commitear `Context.md`, `trader/`, `db/`, `.env` ni llaves.

## Roadmap

1. Completar 30 operaciones resueltas en Oracle y revisar el forward.
2. Añadir modo sombra para `GBPUSD-op`, `CADCHF-op` y otros FX antes de operarlos.
3. Evaluar un filtro de eventos macro (NFP/CPI/FOMC).
4. Endurecer `place_order` y `check_result` ante caídas de WebSocket.
5. Re-screener trimestral con datos nuevos y validación out-of-sample.
6. Dashboard de PnL, winrate y drawdown.

## Licencia

GPL-3.0. Cualquier derivado debe ser de código abierto y público bajo la misma licencia. Ver [`LICENSE`](LICENSE).
