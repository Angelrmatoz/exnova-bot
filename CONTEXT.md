# CONTEXT.md — Contexto completo del proyecto

Documento de contexto: recoge lo investigado y decidido hasta el **3 de noviembre de 2026**.
`plan.md` sigue siendo la fuente de verdad de arquitectura; esto es el registro de hallazgos,
mediciones y estado operativo.

Zona horaria local del operador: **UTC−4**. Todas las horas del bróker se expresan en **UTC**.

---

## 1. Objetivo y estado

Bot autónomo de opciones binarias en Exnova (Python). El objetivo real es demostrar edge antes de
arriesgar capital. Estado actual: **no se opera con dinero real**, solo DEMO.

| Fase | Estado |
|---|---|
| 1. Entorno, menú, BrokerClient/ExnovaAdapter | completa |
| 2. Machine Learning (XGBoost, walk-forward, calibración, SHAP) | completa — **sin edge, no se usa** |
| 3.6 Segundo bróker (IQ Option, ssid de navegador) | completa, validada en DEMO |
| Estrategia de señal | regla 5m validada en 11 pares + ventana horaria |
| Estrategia de anclaje OTC | medida, **bloqueada por el bróker** en los pares fuertes |

---

## 2. Entorno

- Python 3.14 + `uv` (nunca pip). Windows, PowerShell 7. Raíz del repo: `C:\Dev\exnova-bot`.
- Ejecutar siempre desde la raíz: `uv run python -m ...` o `uv run python script.py`.
- Tests: `uv run pytest tests` → **134 passed**.
- Credenciales en `.env` (Exnova + IQ Option). Nunca imprimirlas.

---

## 3. Estrategia 1 — Reversión 5m en pares NORMAL

Regla: unión de **Double Reversal + Exhaustion**.

- Cierre fuera de Bollinger(20, 2) con RSI(14) < 25 → `call`; RSI > 75 → `put`.
- O vela de agotamiento: rango ≥ 2×ATR(14), cuerpo ≥ 60 %, cierre fuera de banda.

Condiciones de operación validadas:

| Parámetro | Valor |
|---|---|
| Timeframe | 5m (actuar sobre la vela recién cerrada) |
| Entrada | open de la vela siguiente |
| Expiración | 900 s (binaria, `option_type_id = 1`) |
| Payout mínimo | 0,86 (comisión 14) |
| Mercado | NORMAL (`-op`) únicamente; OTC excluido |
| Ventana horaria | **18:00–24:00 UTC** (14:00–20:00 local) |

### Pares validados (11)

`EURUSD GBPUSD USDJPY AUDUSD EURGBP EURJPY GBPJPY USDCAD NZDUSD EURAUD CADCHF`

Acierto por par, horiz. 3 velas, datos ene–nov 2026:

| Par | n | win | Par | n | win |
|---|---|---|---|---|---|
| EURGBP | 1096 | 56,57 % | GBPJPY | 1309 | 54,85 % |
| USDJPY | 1420 | 56,34 % | NZDUSD | 1286 | 54,67 % |
| EURAUD | 1271 | 56,18 % | EURJPY | 1387 | 54,29 % |
| EURUSD | 1383 | 55,60 % | AUDUSD | 1361 | 53,93 % |
| CADCHF | 1232 | 55,28 % | USDCAD | 1248 | 53,85 % |
| GBPUSD | 1344 | 55,06 % | | | |

### Por franja horaria (dato decisivo)

| Franja UTC | n | win | expectancy (0,86) |
|---|---|---|---|
| 00–06 | 3946 | 52,58 % | −2,2 % |
| 06–12 | 4186 | 54,85 % | +2,0 % |
| 12–18 | 3437 | 51,96 % | −3,4 % |
| **18–24** | **2779** | **62,94 %** | **+17,1 %** |

Pool completo: **55,10 %** (n = 14.348). Estabilidad 70/30 en la ventana: 61,77 % / 65,67 %.
Breakeven con payout 0,86: **53,76 %**.

Frecuencia: ~9,3 señales/día en la ventana entre los 11 pares. Escaneando todos por vela, la
probabilidad de ≥1 setup por vela es 21 % → espera media 4,7 velas ≈ 24 min.

`EURUSD-OTC` y demás OTC **no** se usan: feed sintético, 48–49 % con esta regla.

---

## 4. Modelo ML — descartado

XGBoost con validación walk-forward (nunca split aleatorio): ~50 % de accuracy y expectancy
negativa (−0,08 a −0,17 con payout 0,80). **No aporta edge en ningún horizonte ni par.**
No se opera con el modelo. El pipeline se mantiene por valor educativo/portafolio.

---

## 5. Estrategia 2 — Anclaje diario del OTC

### Mecanismo

El precio OTC es un **random walk** (variance ratio 1,00 en k = 2,3,5,10; autocorrelación ≈ 0;
sd 5m 0,001182 ≈ 5,2× la real) que se desvía del par real durante el día y **una vez al día salta
al precio real** en un minuto fijo por activo.

- Divergencia media: 7 pips justo después del ancla → 132 pips antes.
- `corr(salto, movimiento real) = 0,9984`; magnitud del salto ≈ magnitud del desvío previo.
- La dirección se conoce **antes** del salto: `side = sign(real − otc)`.

### Acierto medido (sin lookahead, 15m)

| Par | Ancla UTC | Ancla local | n | win | expectancy (0,87) |
|---|---|---|---|---|---|
| EURUSD-OTC | 08:10 | 04:10 | 209 | 100,00 % | +87,0 % |
| EURAUD-OTC | 08:10 | 04:10 | 214 | 99,53 % | +86,1 % |
| AUDUSD-OTC | 01:10 | 21:10 | 205 | 99,51 % | +86,1 % |
| USDCAD-OTC | 08:10 | 04:10 | 213 | 99,06 % | +85,2 % |
| CADCHF-OTC | 08:10 | 04:10 | 204 | 99,02 % | +85,2 % |
| EURGBP-OTC | 04:05 | 00:05 | 201 | 83,08 % | +55,4 % |
| EURJPY-OTC | 04:05 | 00:05 | 214 | 82,71 % | +54,5 % |
| NZDUSD-OTC | 04:05 | 00:05 | 211 | 73,46 % | +37,4 % |
| USDJPY-OTC | 04:05 | 00:05 | 214 | 71,03 % | +32,8 % |
| GBPJPY-OTC | 04:05 | 00:05 | 214 | 68,69 % | +28,5 % |
| GBPUSD-OTC | 04:05 | 00:05 | 209 | 67,46 % | +26,2 % |

Breakeven con payout 0,87: **53,48 %**.

### Bloqueo del bróker — hallazgo del 4-nov

**Los cinco pares con anclaje casi perfecto están cerrados en la hora del anclaje.** El bróker
deshabilita el activo (`enabled = false`) en una ventana de una hora alrededor del recalibrado:

| Par | Hueco de trading | Ancla | ¿Operable? |
|---|---|---|---|
| AUDUSD-OTC | 01:00–02:00 | 01:10 | **No** |
| EURUSD-OTC | 08:00–09:00 | 08:10 | **No** |
| EURAUD-OTC | 08:00–09:00 | 08:10 | **No** |
| USDCAD-OTC | 08:00–09:00 | 08:10 | **No** |
| CADCHF-OTC | 08:00–09:00 | 08:10 | **No** |
| EURGBP-OTC | 04:00–05:00 | 04:05 | **No** |
| EURJPY-OTC | 04:00–05:00 | 04:05 | **No** |
| GBPUSD-OTC | 00:00–24:00 | 04:05 | **Sí** |
| USDJPY-OTC | 00:00–24:00 | 04:05 | **Sí** |
| NZDUSD-OTC | 00:00–24:00 | 04:05 | **Sí** |
| GBPJPY-OTC | 00:00–24:00 | 04:05 | **Sí** |

El schedule se consulta en `initialization-data` → `binary.actives.*.schedule` (lista de pares
`[inicio, fin]` en epoch). `enabled` por activo confirma el estado.

Consecuencia: el edge de los pares fuertes **existe en los datos pero no es accesible**. Los
operables son los de corrección parcial (67–73 %), que aún superan al 62,94 % de la regla 5m.

---

## 6. Reverse engineering de la app Exnova

### Artefactos

| Qué | Ruta / valor |
|---|---|
| MSI original | `C:\Users\Angel\Downloads\Exnova_v4129_3E806E.msi` |
| SHA256 del MSI | `97B7D17436AA2359A81D4242EBA3E980C53336C2C1FF58DE1EC0047B59983E86` |
| Exe (byte-idéntico al instalado) | SHA256 `773A4E5E17BA65479C2723B4F3978603CB75991BB62FFFA5E555B740A0926894`, 109.279.360 bytes |
| Copia extraída | `…\Temp\opencode\rea-exnova\msi-extract\Exnova\Exnova.exe` |
| Proyecto Ghidra (2,59 GB) | `C:\Tools\ghidra-proj\Exnova.gpr` |
| Ghidra | `C:\Tools\ghidra_12.1.4_PUBLIC` (JDK 25, `rea doctor` healthy) |
| Scripts de análisis | `C:\Tools\ghidra-scripts\DumpRefs.java`, `DumpNames.java` |
| Descompilado (40 funciones) | `C:\Tools\exnova-refs2.txt` |
| Catálogo de mensajes | `C:\Tools\exnova-names.tsv` |
| Strings crudos (98.605) | `…\Temp\opencode\rea-exnova\exnova_strings.txt` |

La app está **desinstalada**; el proyecto Ghidra conserva el programa importado.

### Entorno de análisis

| Elemento | Valor |
|---|---|
| `JAVA_HOME` | `C:\Program Files\Java\jdk-25.0.5.0.3` |
| `GHIDRA_INSTALL_DIR` | `C:\Tools\ghidra_12.1.4_PUBLIC` |
| Versión de Ghidra | 12.1.4 (REA solo admite la línea 12.1.x) |
| REA MCP | `npx -y rea-agents@6.7.0 mcp` (caché en `%LOCALAPPDATA%\npm-cache\_npx\…`) |
| Diagnóstico | `rea doctor` → ghidra, headless, native_decompiler y java en `healthy` |

Importación usada (primera y única pasada larga):

```
analyzeHeadless C:\Tools\ghidra-proj Exnova ^
  -import "C:\Program Files\Exnova\Exnova.exe" ^
  -scriptPath C:\Tools\ghidra-scripts ^
  -postScript DumpRefs.java <salida> <patrones> 25 ^
  -max-cpu 12
```

con `MAXMEM=12G`. Tiempo: **80,1 min** (317.742 procedimientos). Después, sobre el proyecto ya
guardado:

```
analyzeHeadless C:\Tools\ghidra-proj Exnova -process Exnova.exe -noanalysis ^
  -scriptPath C:\Tools\ghidra-scripts -postScript DumpRefs.java <salida> <patrones> 3 40
```

→ **51 s**.

**Lección operativa:** REA reimporta y reanaliza en cada operación
(`import_mode: "ephemeral-source-immutable"`, proyecto temporal borrado al cerrar). Cada consulta
cuesta ~80 min, así que solo se usó para la primera exploración; el resto se hizo conduciendo
Ghidra directamente sobre el proyecto persistente.

Sondas WS y scripts de diagnóstico: `%TEMP%\opencode\rea-exnova\` (`probe_ws*.py`, `probe_mood.py`,
`dump_*.py`, `diag_*.py`, `check_windows*.py`, `anchor_probe.py`). **Están fuera del repo y son
efímeros**: no se versionan.

### Naturaleza del binario

C++ **nativo** (toolkit propio `F2::UIElement`, `F2::UIControl`, `F2::json::JsonValue`), sin
Electron, CEF, Qt ni ASAR. `webview.exe` (283 KB) solo cubre partes web (login/KYC).
Plataforma base: **Quadcode** (misma familia que IQ Option: `F2::IQOptionType`, `iqplot::IQClock`).

Análisis: 317.742 procedimientos, 52.999 strings, 11 segmentos, image base `0x140000000`.
Tiempo: 80 min la primera pasada (12 GB heap, `-max-cpu 12`); consultas posteriores 51 s.

### Enum de instrumentos (`FUN_141623740`)

| id | tipo | id | tipo |
|---|---|---|---|
| 1 | binary | 12 (0xc) | fx-option |
| 3 | turbo | 15 | marginal-forex |
| 7 | digital-option | 16 | marginal-cfd |
| 8 | cfd | 17 | marginal-crypto |
| 9 | forex | 18 (0x12) | exchange-option |
| 10 | crypto | **19 (0x13)** | **blitz-option** |
| 999 | trade-rush | | |

### `option_type_id` (`FUN_1416ca640`)

```c
if (iVar3 == 1)        uVar7 = 1;    // binary
else if (iVar3 == 3)   uVar7 = 3;    // turbo
else if (iVar3 == 0x13) uVar7 = 0xc; // blitz-option -> 12
else                   uVar7 = 0;
```

Campos del registro de posición: `user_balance_id`, `active_id`, `option_type_id`, `direction`,
`expired`, `refund_value`, `price`, `value`, `profit_percent`, `expiration_size`.

### Web del traderoom (verificada, sin generador)

`/traderoom/bundle.js` = 1,14 MB ofuscado. Contiene **0** `Math.random`, **0** `otc`, **0**
`generat`, **0** `seed`. Los 6 `synthetic` son de Sentry; el único `simulat` es
`ReactTestUtils.Simulate`. El cliente **no genera precios**: solo pinta lo que llega por WS.

---

## 7. Protocolo WebSocket — qué responde

Sondeado en PRACTICE, sin órdenes.

| Mensaje | Resultado |
|---|---|
| `get-candles` | velas; la última es la que se está formando |
| `get-traders-mood` | `{"instrument":"binary-option","asset_id":N}` → 0,18–0,36 EURUSD; 0,5 fijo en varios pares. Ruido, sin cobertura |
| `get-technical-indicators` | `{"id": <id IQ>}` → 456 entradas (57 indicadores × 8 timeframes). TA estándar |
| `get-active-exposure` | `{"call":10000,"put":10000}` constante. Inútil |
| `get-script-indicators` | `{"active_id":N,"locale":"en"}` → 8 scripts de comunidad (pseudo-Pine) |
| `get-triggers` | alertas propias del usuario |
| `get-orderbooks` | sin respuesta |
| `get-economic-calendar-events` | sin respuesta |
| `get-news-feed` | sin respuesta |
| `get-instruments` | sin respuesta |
| `change-demo-balance`, `custom-demo-balance`, `decrease-demo-balance`, `hidden-reset-demo-balance`, `training-balance-reset`, `change-balance` | `Invalid contract` (no se puede cambiar el balance DEMO por WS) |

Catálogo completo: **938** nombres kebab-case referenciados por código (`exnova-names.tsv`).

Los ids de `get-technical-indicators` son del espacio IQ Option (1 = EURUSD); los `-op` se
rechazan con `Active is not supported`.

---

## 8. Ejecución de órdenes

- `get_expiration_time(ts, 15)` usa el **timestamp del servidor** y devuelve una marca de 15 min
  con `idx >= 5` → `option_type_id = 1` (binaria). Restante típico 400–1350 s.
- `get_payout` lee la comisión binaria del `initialization-data` v3 cacheado.
- Comisión binaria en los 261 activos NORMAL: **14 → payout 0,86**. OTC: 13 → **0,87**.
  Blitz EURUSD: 13 → 0,87 (pero solo mejora ese par; descartado).
- `check_result` espera el cierre hasta 1500 s (`socket-option-closed` llega sin suscripción extra).
- Deadtime: binaria 300 s; turbo 30 s; blitz 0.
- Drift del reloj del servidor vs local: ≈ +3 s (variable).

Orden REAL verificada (DEMO, $1): `order_id=14412289652`, `expired=1793628000` (%900==0),
`option_type_id=1`, cerrada como `loose pnl=-1.00`, balance 457.441,26 → 457.440,26.

---

## 9. Base de datos y kill-switches

`bot_data.db` (SQLite), tabla `trade_logs` (pair, market_type, signal, result, pnl, gate_passed…).

| Estrategia | market_type | Muestra mínima | Umbral | Implementación |
|---|---|---|---|---|
| Reversión 5m | `NORMAL` | 60 resueltas | 53,8 % (breakeven 0,86) | `session.edge_alive` + guarda en `main.py` |
| Anclaje OTC | `ANCHOR` | 15 resueltas | 90 % | `anchor.anchor_alive` + `bot/scripts/anchor_session.py` |

`db.get_win_rate(market_type)` cuenta solo WIN/LOSS (SKIPPED y DRAW no contaminan).

Balance DEMO actual: **457.440,26** (no se puede fijar por WS).

---

## 10. Código y commits

| Commit | Contenido |
|---|---|
| `fe261d5` | 11 pares validados + escaneo de todos por vela cerrada (`_scan`) |
| `a0e1fa5` | kill-switch por win rate realizado (`get_win_rate`, `edge_alive`) |
| `e884435` | ventana de entrada 18–24 UTC (`TRADING_HOURS_UTC`, `entry_in_window`) |
| `65672a3` | módulo de anclaje OTC (`bot/anchor.py`, CLI, 7 tests) |

Archivos clave:

- `bot/session.py` — `run_session`, `_scan`, `reversion_signal`, `VALIDATED_BASES`,
  `MIN_PAYOUT=0.86`, `TRADING_HOURS_UTC`, `MIN_SAMPLE/MIN_WIN_RATE`.
- `bot/anchor.py` — `ANCHORS`, `LEAD_SECONDS=120`, `MIN_GAP_REL`, `decide`, `run_anchors`,
  `anchor_alive`.
- `bot/scripts/anchor_session.py` — CLI diaria con kill-switch.
- `bot/db.py` — `get_win_rate`, `get_loss_streak`, `get_today_pnl`.
- `main.py` — guarda de edge antes de operar.
- `bot/broker/exnova_ws.py` — cliente WS (expiración por reloj de servidor, payout v3).
- `tests/` — 134 tests.

---

## 11. Tareas programadas

| Tarea | Hora | Estado |
|---|---|---|
| `ExnovaAnchorAUDUSD` | 03-nov 21:07 local (01:07 UTC) | **ejecutada y rechazada** por el bróker (activo cerrado 01:00–02:00) |
| `ExnovaAnchorGBPUSD` | 04-nov 00:02 local (04:02 UTC) | lista; entra a las 04:03 UTC, ancla 04:05 |

Ambas usan `C:\Tools\anchor_run.py` (script suelto, verificado, con `SetThreadExecutionState`
para no dormir el equipo) y escriben en `C:\Tools\anchor_runs.jsonl` y `C:\Tools\anchor_out.log`.

Requisitos: PC encendida, sesión de Windows iniciada, internet. `WakeToRun` activo; suspensión en
AC desactivada; hibernación en AC desactivada.

---

## 12. Datos

`data/5m/` — 22 CSV, 219 MB, re-descargados el 3-nov-2026 (13:25–13:30 UTC):

- 11 pares `-op` × 65.000 velas (ene–nov 2026)
- 11 pares `-OTC` × 90.000 velas

Verificación de robustez: borrados y re-descargados desde cero → los dos patrones (anclaje 96,9–100 %;
ventana 18–24 UTC 62,94 %) se reprodujeron con ≤0,5 pp de variación. No eran artefacto de ficheros
locales.

---

## 13. Descartado con evidencia

| Hipótesis | Evidencia |
|---|---|
| Modelo XGBoost aporta edge | ~50 % accuracy, expectancy negativa |
| Indicadores técnicos del servidor | 57 indicadores × 8 TF, matemática estándar; pivotes probados sin diferencia |
| Pivotes diarios como filtro | cerca (≤5 pips) 54,89 % vs lejos 55,05 % (70 %), 55,38 % vs 56,12 % (30 %) — inconsistente |
| Traders-mood | 0,18–0,36 y 0,5 fijo; ruido |
| Active-exposure | 10.000/10.000 constante |
| Orderbooks / calendario / news | no responden por WS |
| Blitz | solo EURUSD mejora (0,87 vs 0,86) |
| Payout mejor | los 261 activos binarios NORMAL están a comisión 14 |
| Pinning en el cierre de vela | OTC: último pip uniforme (p=0,096 / 0,251), salto cierre→apertura simétrico. NORMAL: sesgo de 0,126 pips por bid/ask, 100× menor que el movimiento típico |
| Cliente con lógica de precios | 0 `Math.random`, 0 `otc`, 0 `generat` en bundle.js y en las 98.605 strings |

---

## 14. Riesgos

1. **El anclaje OTC es un artefacto del feed del bróker**, no un edge de mercado. Sus términos pueden
   permitir anular beneficios o cerrar la cuenta. En DEMO no hay riesgo económico.
2. Los cinco pares con anclaje casi perfecto están **cerrados** en la hora del anclaje: diseñado para
   que no se pueda operar.
3. Todas las probabilidades son **frecuencias históricas in-sample** de 2026, no garantías.
4. El equity de la regla 5m es fino: 62,94 % en ventana contra 53,76 % de breakeven.
5. Criterio de abandono: si la ventana 18–24 UTC no supera 58 % tras 60 operaciones DEMO, se revierte.

---

## 15. Próximos pasos

1. **04:03 UTC (00:03 local) del 4-nov** — `GBPUSD-OTC`, 1.000 DEMO, entrada 120 s antes del ancla
   de 04:05. Es el primer par con ancla *operable*. Revisar `C:\Tools\anchor_runs.jsonl`.
2. Si la orden entra y gana → extender a USDJPY, NZDUSD y GBPJPY (mismo horario) y automatizar como
   tarea diaria con `bot.scripts.anchor_session`.
3. Si el bróker también la rechaza → cerrar la vía OTC definitivamente y quedarse solo con la regla 5m
   en la ventana 18–24 UTC.
4. Semana DEMO de la regla 5m con el kill-switch activo: medir win rate realizado contra 62,94 %.
