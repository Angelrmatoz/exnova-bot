# Binary Options Bot — Exnova

Sistema autónomo de opciones binarias en **Exnova** (el adaptador IQ Option queda como fallback). Ejecuta la estrategia **NORMAL 5m exhaustion** en un host Linux con Docker, imagen en GHCR, SQLite y control estricto de riesgo. Cuenta **DEMO / PRACTICE**.

> **Estado de señal:** in-sample positivo (357 señales, 67,2 %) y forward en curso (9 resueltas, 6W/3L al 19-nov). Muestra forward **insuficiente**: el edge **no está confirmado**. Se opera solo en **DEMO**; no usar capital real hasta completar la validación.

> **Riesgo:** las opciones binarias son instrumentos de alto riesgo. El bróker se trata como una dependencia intercambiable; el núcleo analítico no depende de él.

## Estado actual

| Tema | Estado |
|---|---|
| Bróker | **Exnova DEMO** (IQ Option como fallback, ssid vencido) |
| Estrategia | **NORMAL 5m exhaustion**, 30m + side-logging 5/10/15/30m |
| Pares | `EURUSD-op`, `NZDUSD-op`, `EURGBP-op`, `GBPUSD-op`, `CADCHF-op` |
| Ventanas | 08:00–10:59 y 13:00–13:59 UTC |
| Payout Exnova | 0,86 en los 5 pares (turbo 0,84 en 3; NZDUSD turbo 0,30 inoperable; CADCHF sin turbo) |
| Riesgo | Stake **10.000 DEMO**, máx 3/sesión, corte 2W/2L |
| Producción | Oracle Cloud + Docker + `systemd` timer 07:55 UTC (Mon–Vie) |
| Resumen diario | `exnova-check.timer` 15:30 UTC → webhook de Discord (trades, acumulado, kill-switch, journal) |
| Imagen | GHCR (`exnova-bot-runner`); compose de Oracle fuerza `--broker exnova` |
| OTC | **Cerrado definitivamente**: feed generado por el bróker, iid en 5m/1m/1s |
| ML | Descartado: ~50 % accuracy, expectancy negativa |
| Tests | **168 verdes** en GitHub Actions |

## Qué hace

1. En cada vela de 5 minutos cerrada, dentro de las ventanas, revisa los 5 pares.
2. Exige cuatro condiciones:
   - rango de la vela ≥ 2× ATR14;
   - cuerpo ≥ 60 % del rango;
   - cierre fuera de Bollinger(20,2);
   - RSI no extremo.
3. Si la vela cerró **debajo** de la banda inferior, entra **CALL**; si cerró **arriba**, entra **PUT**.
4. Entra al open de la vela siguiente, con expiración **30 minutos** y stake fijo.
5. Registra el resultado en SQLite (con el z de la señal y el resultado papel a 5/10/15/30m) y aplica los límites de sesión.

### Lo que no hace

- No opera OTC (cerrado con evidencia estadística).
- No usa Machine Learning en vivo; el modelo fue descartado.
- No promete ganar ni predice el mercado.
- No filtra noticias ni eventos macro (NFP, CPI, FOMC).
- No usa las skills de trader en runtime; son herramientas de análisis externas.

## Arquitectura

```text
GitHub Actions
  ├── tests (pytest)
  └── build/push imagen → GHCR

Oracle Cloud
  ├── systemd timer 07:55 UTC (Mon–Vie)
  │     └── docker compose run runner
  │           ├── pull :latest
  │           ├── ExnovaWSClient (WebSocket, email/password)
  │           ├── estrategia 5m
  │           └── SQLite /app/db/bot_data.db
  └── systemd timer 15:30 UTC
        └── resumen del día → Discord webhook
```

| Componente | Tecnología |
|---|---|
| Lenguaje | Python 3.14 + uv |
| Bróker producción | `BrokerClient` + `ExnovaAdapter` + `ExnovaWSClient` |
| Fallback | `IqOptionAdapter` + `IqOptionWSClient` |
| Análisis | pandas + `ta` |
| Persistencia | SQLite (`model_versions`, `trade_logs`) |
| Ejecución | Docker + Docker Compose |
| Distribución | GitHub Container Registry (GHCR) |
| CI/CD | GitHub Actions |
| Notificaciones | Webhook de Discord |

## Estrategia

| Parámetro | Valor |
|---|---|
| Timeframe | 5m |
| Expiración | 30m binaria |
| Payout Exnova | 0,86 |
| `MIN_PAYOUT` | 0,86 |
| Stake | **10.000** |
| Máximo por sesión | 3 |
| Corte | 2W o 2L |
| Kill-switch | 30 resueltas con winrate <56 % |
| Pares | EURUSD-op, NZDUSD-op, EURGBP-op, GBPUSD-op, CADCHF-op |
| Horas UTC | 8, 9, 10, 13 |

## Producción

La imagen se construye y publica desde GitHub Actions. El host no recibe pushes: **hace pull antes de cada sesión**.

```bash
docker compose -f compose.runner.yml pull
docker compose -f compose.runner.yml run --rm -T runner --dry-run
```

El compose de Oracle fija `entrypoint` en `normal_five --broker exnova` y `--stake 10000`. El timer diario arranca el runner antes de la ventana. El servicio hace `docker compose pull` y luego ejecuta el contenedor; si el `pull` falla, usa la imagen cacheada.

**Autenticación: Exnova usa email/password** (sin cookie de sesión que caduque). IQ Option, como fallback, usa `ssid` de navegador que caduca; el actual está vencido — refrescar solo si se vuelve a usar IQ.

### Operación

```bash
systemctl list-timers
systemctl is-active docker
journalctl -u exnova-runner.service -n 100 --no-pager
journalctl -u exnova-check.service --since today --no-pager
```

## Desarrollo local

Requiere Python 3.14, [uv](https://docs.astral.sh/uv/) y Docker opcional.

```bash
uv sync
cp .env.example .env   # credenciales DEMO; nunca commitear
uv run pytest tests
uv run python -m bot.scripts.normal_five --broker exnova --dry-run
uv run python -m bot.scripts.asset_hours EURUSD-op NZDUSD-op EURGBP-op GBPUSD-op CADCHF-op --hours 14
uv run python -m bot.scripts.signal_report          # base, horas, buckets z, robustez mensual
```

### Construir la imagen del runner

```bash
docker build -f Dockerfile.runner -t ghcr.io/<owner>/exnova-bot-runner:local .
```

## Estructura

```text
bot/
├── broker/       # BrokerClient, ExnovaAdapter/WS, IqOptionAdapter/WS, Mock
├── ml/           # features, multi_tf, train, calibrate, backtest, shap, export
├── scripts/      # normal_five, session_report, signal_report, fetch_history,
│                 # build_features, asset_hours, backtest_mock
├── db.py         # SQLite: model_versions + trade_logs
├── config.py     # .env: Exnova + IQ Option
├── history.py    # paginación de velas
├── schedule.py   # ventanas de apertura del bróker
└── session.py    # sesión interactiva de 3 operaciones

Dockerfile.runner              # imagen slim del runner (multi-stage, non-root)
requirements-runner.txt        # dependencias mínimas del runner
compose.runner.yml             # servicio: env, DB, logs
deploy/                        # unidades de servicio y timers (runner + resumen)
.github/workflows/             # CI + build/push GHCR
data/5m/, data/1m/             # CSV de investigación (no versionados)
reports/                       # artefactos de análisis (no versionados)
main.py                        # menú interactivo
```

## Datos y validación

- 22 CSV 5m (11 `-op` + 11 `-OTC`) ene–nov 2026; 1m de 6 pares (21–63 días). `data/` no se versiona.
- IQ expone **273 binarias + 255 turbo**; Exnova **262 + 242**. Solo 22 activos tienen historia local.
- In-sample (5 pares, horas de producción): **357 señales, 67,2 %**, Wilson 62,2–71,9 %; racha perdedora máx 4.
- Forward real: **9 resueltas, 6W/3L (66,7 %)**; kill-switch 9/30.
- Side-logging: cada trade real guarda su resultado papel a **5/10/15/30m** para decidir la expiración por par con OOS.
- Expiración: zona buena 5–30m; ≥60m descartado en los 5 pares. Turbo: 0,84 en 3 pares; NZDUSD sin turbo viable.
- OTC: cerrado; iid puro (autocorrelación ≈0, sin clustering de volatilidad, rachas consistentes con azar).
- `backtest-expert`: 58/100, `VALIDATION_REQUIRED`; no confundir backtest con edge confirmado.

No se cambian pares, horas, stake, payout ni expiración sin backtest, PR y validación forward. Un winrate de 30 días es ruido, no edge.

## Seguridad

- `.env` y credenciales fuera de git.
- No se publican IPs, llaves SSH, rutas internas ni tokens.
- El host usa un token de solo lectura para GHCR; el paquete puede ser privado.
- Nunca ejecutar dos runners a la vez.
- No commitear archivos locales, `db/`, `.env` ni llaves.

## Roadmap

1. Completar 30 operaciones resueltas y decidir con `signal_report` + side-logging: cutoff z, confluencia, guarda de régimen y expiración por par.
2. Endurecer `place_order` y `check_result` ante caídas de WebSocket.
3. Re-screener trimestral con datos nuevos y validación out-of-sample.
4. Dashboard de PnL, winrate y drawdown.

## Licencia

GPL-3.0. Cualquier derivado debe ser de código abierto y público bajo la misma licencia. Ver [`LICENSE`](LICENSE).
