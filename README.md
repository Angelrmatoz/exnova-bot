# Binary Options Bot — IQ Option

Sistema autónomo de opciones binarias en **IQ Option** (el adaptador Exnova queda como fallback). Ejecuta la estrategia **NORMAL 5m exhaustion** en un host Linux con Docker, imagen en GHCR, SQLite y control estricto de riesgo. Cuenta **DEMO / PRACTICE**.

> **Estado de señal:** el backtest in-sample es positivo, pero la muestra forward todavía es insuficiente. El edge **no está confirmado**. Se opera solo en **DEMO**; no usar capital real hasta completar la validación.

> **Riesgo:** las opciones binarias son instrumentos de alto riesgo. El bróker se trata como una dependencia intercambiable; el núcleo analítico no depende de él.

## Estado actual

| Tema | Estado |
|---|---|
| Bróker | **IQ Option DEMO** (Exnova como fallback) |
| Estrategia | **NORMAL 5m exhaustion**, 30m |
| Pares | `EURUSD-op`, `NZDUSD-op`, `EURGBP-op` |
| Ventanas | 08:00–10:59 y 13:00–13:59 UTC |
| Payout IQ | EURUSD 90%, NZDUSD 87%, EURGBP 87% (snapshot 09-nov) |
| Riesgo | Stake **1.000 DEMO**, máx 3/sesión, corte 2W/2L |
| Producción | Oracle Cloud + Docker + `systemd` timer 07:55 UTC |
| Imagen | GHCR (`exnova-bot-runner`), ENTRYPOINT `--broker iqoption` |
| OTC | Suspendido: 0/11 con historia pasa el screener |
| ML | Descartado: ~50 % accuracy, expectancy negativa |
| Tests | **152 verdes** en GitHub Actions |

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
              ├── IqOptionWSClient (WebSocket, ssid)
              ├── estrategia 5m
              └── SQLite /app/db/bot_data.db
```

| Componente | Tecnología |
|---|---|
| Lenguaje | Python 3.14 + uv |
| Bróker producción | `BrokerClient` + `IqOptionAdapter` + `IqOptionWSClient` |
| Fallback | `ExnovaAdapter` + `ExnovaWSClient` |
| Análisis | pandas + `ta` |
| Persistencia | SQLite (`model_versions`, `trade_logs`) |
| Ejecución | Docker + Docker Compose |
| Distribución | GitHub Container Registry (GHCR) |
| CI/CD | GitHub Actions |

## Estrategia

| Parámetro | Valor |
|---|---|
| Timeframe | 5m |
| Expiración | 30m binaria (grilla 15m de IQ) |
| Payout IQ | 0,87–0,90 |
| `MIN_PAYOUT` | 0,86 |
| Stake | **1.000** |
| Máximo por sesión | 3 |
| Corte | 2W o 2L |
| Kill-switch | 30 resueltas con winrate <56 % |
| Pares | EURUSD-op, NZDUSD-op, EURGBP-op |
| Horas UTC | 8, 9, 10, 13 |

## Producción

La imagen se construye y publica desde GitHub Actions. El host no recibe pushes: **hace pull antes de cada sesión**.

```bash
docker compose -f compose.runner.yml pull
docker compose -f compose.runner.yml run --rm -T runner --stake 1000 --dry-run
```

El ENTRYPOINT de la imagen ejecuta `normal_five --broker iqoption`; `compose.runner.yml` fija `--stake 1000`. El timer diario arranca el runner antes de la ventana. El servicio hace `docker compose pull` y luego ejecuta el contenedor; si el `pull` falla, usa la imagen cacheada.

**IQ Option usa `ssid` de navegador.** Si caduca, el runner falla con `ssid inválido o sesión expirada`; hay que sacar la cookie nueva y actualizar `IQ_OPTION_SSID` en `/opt/exnova-bot/.env`.

### Operación

```bash
systemctl list-timers
systemctl is-active docker
journalctl -u <servicio> -n 100 --no-pager
```

## Desarrollo local

Requiere Python 3.14, [uv](https://docs.astral.sh/uv/) y Docker opcional.

```bash
uv sync
cp .env.example .env   # credenciales DEMO; nunca commitear
uv run pytest tests
uv run python -m bot.scripts.normal_five --broker iqoption --dry-run
uv run python -m bot.scripts.asset_hours EURUSD-op NZDUSD-op EURGBP-op --hours 14
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
├── scripts/      # normal_five, fetch_history, build_features, asset_hours, backtest_mock
├── db.py         # SQLite: model_versions + trade_logs
├── config.py     # .env: Exnova + IQ Option
├── history.py    # paginación de velas
├── schedule.py   # ventanas de apertura del bróker
└── session.py    # sesión interactiva de 3 operaciones

Dockerfile.runner              # imagen slim del runner (multi-stage, non-root)
requirements-runner.txt        # dependencias mínimas del runner
compose.runner.yml             # servicio: env, DB, logs
deploy/                        # unidad de servicio y timer
.github/workflows/             # CI + build/push GHCR
data/5m/                       # 22 CSV de investigación (11 NORMAL + 11 OTC)
bot_data.db                    # SQLite local (ignorado)
main.py                        # menú interactivo
```

## Datos y validación

- 22 CSV 5m (11 `-op` + 11 `-OTC`) hasta 03-nov-2026.
- IQ expone **273 binarias + 255 turbo**; Exnova **262 + 242**. Solo 22 activos tienen historia local.
- OTC: 0/11 pasa el screener; mejor slot 55–57 %, insuficiente.
- Replay IQ 30m: **222 señales, 65,6 % win, max DD 6,46 unidades, +51,77 unidades** con payouts 0,87–0,90.
- Forward: muestra todavía insuficiente (3 NORMAL resueltas al 09-nov).
- `backtest-expert`: `VALIDATION_REQUIRED`; no confundir backtest con edge confirmado.

No se cambian pares, horas, stake ni payout sin backtest, PR y validación forward. Un winrate de 30 días es ruido, no edge.

## Seguridad

- `.env` y credenciales fuera de git.
- No se publican IPs, llaves SSH, rutas internas ni tokens.
- El host usa un token de solo lectura para GHCR; el paquete puede ser privado.
- Nunca ejecutar dos runners a la vez.
- No commitear archivos locales, `db/`, `.env` ni llaves.

## Roadmap

1. Completar 30 operaciones resueltas y revisar el forward.
2. Añadir modo sombra para `GBPUSD-op`, `CADCHF-op` y otros FX antes de operarlos.
3. Evaluar un filtro de eventos macro (NFP/CPI/FOMC).
4. Endurecer `place_order` y `check_result` ante caídas de WebSocket.
5. Re-screener trimestral con datos nuevos y validación out-of-sample.
6. Dashboard de PnL, winrate y drawdown.

## Licencia

GPL-3.0. Cualquier derivado debe ser de código abierto y público bajo la misma licencia. Ver [`LICENSE`](LICENSE).
