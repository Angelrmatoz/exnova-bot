## 🎯 Objetivo del Proyecto

Desarrollar un bot autónomo en **Python** para opciones binarias en la plataforma **Exnova**, utilizando un modelo de Machine Learning de ultra baja latencia (**XGBoost**), gestión estricta de riesgo y persistencia en **SQLite**.

> 🎯 **Propósito:** Sistema autónomo de trading de opciones binarias en Exnova e IQ Option, con modelo de Machine Learning (XGBoost), gestión estricta de riesgo y auditoría en SQLite. Proyecto de operación seria — no demo/académico. La señal debe demostrar edge (expectancy positiva) antes de operar capital real.
> 

> ⚠️ **Advertencia de Riesgo**: Las opciones binarias son instrumentos de alto riesgo. Opera siempre en DEMO primero, con montos pequeños, y nunca inviertas capital que no puedas permitirte perder.
> 

> 🔄 **Nota sobre el bróker:** Exnova **no cuenta con regulación de organismos reconocidos** (CySEC, FCA, CNMV) y existen reportes públicos de problemas con retiros. Por tanto, el bróker se trata como una **dependencia intercambiable**, no como un componente fijo del sistema. El núcleo analítico debe funcionar independientemente del bróker conectado. Adicionalmente, en modo OTC los precios son generados por un algoritmo propietario del bróker (no representan mercado real), por lo que el rendimiento del modelo en OTC debe registrarse y evaluarse por separado del rendimiento en mercado Normal, y **no debe considerarse comparable ni extrapolable entre ambos**.
>
> ⚠️ **Segundo bróker integrado — IQ Option:** se añadió un segundo adaptador (`IqOptionAdapter` + `IqOptionWSClient`, Fase 3.6) que implementa el mismo contrato `BrokerClient`. **Precisión de señales:** el bróker solo transporta datos y ejecuta órdenes — **no añade precisión predictiva**. El modelo ML sigue entrenado con velas 5m de Exnova (~50% accuracy, sin edge confirmado). Para que IQ Option aporte algo al modelo habría que **capturar sus datos y re-entrenar** (precios OTC propietarios, distintos a Exnova). Lo que sí mejora es la **fiabilidad de conexión/ejecución** (efecto en PnL, no en accuracy).
>
> 🪙 **Tercer bróker previsto — Binance (futuro, Fase 7):** Binance **no es opciones binarias** — es un exchange de cripto con órdenes spot/futures (margen, stop-loss, take-profit). No implementa `place_order(duration)` con vencimiento como Exnova/IQ; el adaptador deberá mapear el ciclo a órdenes de mercado + cierre manual o usar futuros con TP/SL. Esto cambia la semántica de `check_result` (resultado ya no viene por push del bróker, se calcula del PnL de la posición). El core desacoplado (`BrokerClient`) ya lo soporta; se añadirá como adaptador nuevo cuando el modelo muestre edge confirmado (hoy no lo hay). **Nota:** los límites de monto ($1–$20k) aplican a Exnova/IQ; Binance tendrá sus propios mínimos por símbolo.
>
> ⚠️ **Sobre el vendor `exnovaapi`:** era un **port de bajo nivel** (linaje `iqoptionapi`), sin tipos, sin tests, estado global mutable (`global_value`), ~55 handlers por mensaje, `dict_queue_add` O(n), crash en el stream all-size de velas y `ACTIVES` hardcodeado. Fue **eliminado** y reemplazado por el cliente WS propio `ExnovaWSClient` (Fase 3.5). La resolución del feed (1 mensaje/seg) es límite del servidor, no de la librería.
> 

---

## 1. 🚀 Módulo de Inicio y Selección de Mercado

Al ejecutar el bot, el programa mostrará un **menú interactivo en consola** antes de arrancar la monitorización:

- [x]  **Selección de Tipo de Mercado:**
    - **Mercado Real (Normal):** Operación de lunes a viernes.
    - **Mercado OTC:** Operación de fines de semana o activos simulados.
- [x]  **Selección de Operador (multi-bróker):** primer paso del CLI — lee los operadores con credenciales completas en `.env` vía `configured_brokers()` y deja elegir (1. Exnova, 2. IQ Option, ...). El adaptador correcto lo construye `bot/broker/factory.build_broker()`; añadir un bróker nuevo = nuevo adaptador + sus credenciales en `.env` + entrada en el factory, sin tocar el núcleo.
- [x]  **Escaneo Dinámico de Divisas:** Consultar las divisas abiertas en el modo seleccionado vía `BrokerClient.get_available_assets()`, manteniendo el núcleo del bot desacoplado del bróker específico.
- [x]  **Selección de Activos a Monitorizar:** Permitir al usuario elegir una divisa específica, una lista de divisas o la opción "Analizar todas las divisas disponibles" simultáneamente.

---

## 2. 🛠️ Stack Técnico

| Componente | Tecnología | Función Principal |
| --- | --- | --- |
| Lenguaje | Python 3.10+ | Entorno principal del sistema |
| Conexión Broker | BrokerClient + ExnovaAdapter / IqOptionAdapter (websocket-client) → `ExnovaWSClient` / `IqOptionWSClient` propios | Gestión de sesión, recepción de velas 1s y órdenes, desacoplada del bróker específico |
| Análisis Técnico | pandas + ta | Procesamiento de datos y cálculo de indicadores (RSI, EMA, MACD) |
| IA de Señales (Capa 1) | XGBoost (.pkl) | Inferencia local ultra rápida (< 50 ms) para predecir la dirección de la vela |
| Base de Datos | SQLite3 | Persistencia de estado, logs de auditoría de gates y métricas de PnL |
| Notificaciones | Bot de Telegram | Envíos de alertas de operaciones, ganancias y errores críticos |
| Infraestructura | Docker + Oracle Cloud (VPS) | Despliegue en contenedor aislado corriendo 24/7 |
| Validación | scikit-learn (TimeSeriesSplit / walk-forward) | Validación temporal sin fuga de información (data leakage) |
| Visualización / Dashboard | Streamlit o Plotly Dash | Panel de análisis de resultados leyendo directamente de SQLite |

> 🔌 **Abstracción BrokerClient:** Definir una **interfaz abstracta** con métodos `get_candles()`, `place_order()` y `get_balance()` para desacoplar por completo el núcleo analítico del bróker específico. Esto permite cambiar de Exnova a cualquier otro bróker modificando únicamente el adaptador.
> 

---

## 3. 🏗️ Arquitectura de 2 Capas

```text
┌─────────────────────────────────────────────────────────────────┐
│ CAPA 1 — Señal en Tiempo Real (Cada vela, < 50ms)               │
│ ta calcula indicadores → XGBoost evalúa probabilidad            │
│ Solo genera señal si la probabilidad supera el umbral           │
│ ⚠ Umbral a calibrar empíricamente con curva de calibración,    │
│   no fijado arbitrariamente en 68% antes de tener datos reales │
└────────────────────────────────┬────────────────────────────────┘
                                 ↓
┌─────────────────────────────────────────────────────────────────┐
│ CAPA 2 — Gateways de Validación y Ejecución                     │
│ Gate 1: Payout del activo ≥ 75%                                 │
│ Gate 2: Sincronización al segundo 59.8 de la vela               │
│ Gate 3: Validación de límites en RiskManager                    │
│ → Envío de orden al bróker seleccionado                         │
└─────────────────────────────────────────────────────────────────┘
```

---

## 4. 🛡️ Reglas de Gestión de Riesgo (RiskManager)

| Regla | Valor |
| --- | --- |
| Monto por Operación | 1% al 2% del balance total |
| Payout Mínimo | ≥ 75% (descarta entradas menores) |
| Stop-Loss Diario | Apagado automático si el balance del día cae un 6% |
| Take-Profit Diario | Pausa de operaciones al alcanzar +10% en el día |
| Circuit Breaker | Pausa si la racha de pérdidas excede la distribución esperada según el win rate histórico (significancia estadística), no un conteo fijo arbitrario |
| Expectancy mínima | Calcular `(winrate × payout) − (1 − winrate)` antes de operar en real. Debe ser positiva para que el sistema sea viable a largo plazo |

> 🔴 **Circuit Breaker — Implementación concreta:**
> 

> 1. Calcular el win rate histórico del modelo (ej. `winrate = 0.55`).

> 2. Para una racha de N pérdidas consecutivas, calcular `P(N pérdidas) = (1 − winrate)^N`.

> 3. Ejemplo: si `winrate = 55%`, entonces `P(5 pérdidas seguidas) = 0.45⁵ ≈ 1.8%`.

> 4. **Umbral de activación:** si la probabilidad de la racha actual cae por debajo del **2%**, activar el freno automático.

> 5. Fórmula en código: `if (1 - winrate) ** racha_actual < 0.02: activar_circuit_breaker()`

> 6. **Definición de racha:** solo los resultados `WIN` / `LOSS` cuentan para el cálculo. Las operaciones con resultado `SKIPPED` (descartadas por algún gate) **no interrumpen ni extienden la racha** de pérdidas consecutivas.


> ⚠️ **Supuesto de independencia:** la fórmula `(1-winrate)^N` asume que cada operación es independiente de la anterior. En la práctica los mercados tienen regímenes (rachas de volatilidad, tendencias) donde las pérdidas pueden estar correlacionadas, por lo que el umbral calculado es una aproximación consciente, no una probabilidad exacta.
> 

---

## 5. 🗄️ Auditoría y Base de Datos (SQLite)

El archivo `bot_data.db` almacenará el historial completo para auditoría y recuperación tras caídas.

**Esquema de la Tabla `trade_logs`:**

| Columna | Tipo | Descripción |
| --- | --- | --- |
| id | INTEGER PRIMARY KEY | Identificador único |
| timestamp | DATETIME | Fecha y hora de la operación |
| pair | TEXT | Par de divisas operado |
| market_type | TEXT (NORMAL / OTC) | Tipo de mercado activo |
| signal | TEXT (CALL / PUT / NONE) | Señal generada |
| confidence | FLOAT | Probabilidad del modelo XGBoost |
| gate_passed | TEXT | Gate aprobada o motivo de rechazo |
| result | TEXT (WIN / LOSS / SKIPPED) | Resultado de la operación |
| pnl | FLOAT | Profit & Loss de la operación |
| features_snapshot | JSON | Snapshot de los features que alimentaron la predicción (permite auditoría posterior y análisis de drift). ⚠️ Evaluar rotación o compresión si el volumen de operaciones crece significativamente (riesgo de inflación del SQLite en uso 24/7). |
| model_version_id | INTEGER (FK → model_versions) | Versión del modelo XGBoost que generó la señal |

**Tabla adicional `model_versions`:**

| Columna | Tipo | Descripción |
| --- | --- | --- |
| id | INTEGER PRIMARY KEY | Identificador de versión |
| trained_at | DATETIME | Fecha y hora de entrenamiento |
| deployed_at | DATETIME (nullable) | Fecha y hora en que este modelo empezó a usarse en producción (distinto de trained_at si se evalúan varios modelos antes de elegir cuál desplegar) |
| is_active | BOOLEAN | Indica si es el modelo actualmente en uso para generar señales |
| val_accuracy | FLOAT | Accuracy en validación walk-forward |
| val_logloss | FLOAT | Log-loss en validación |
| feature_list | JSON | Lista de features usadas |
| notes | TEXT | Observaciones del entrenamiento |

---

## 6. 🔄 Estrategia de Resiliencia

- **Heartbeat:** Envío continuo de tramas Ping/Pong en el WebSocket para evitar desconexiones por inactividad.
- **Exponential Backoff:** En caso de corte de red, aplicar reintentos automáticos a los 2 s, 4 s, 8 s, 16 s... hasta restablecer la conexión sin cerrar el programa.
- **Persistencia de Estado:** Al reiniciar el bot, este lee la base de datos SQLite para restaurar el contador de pérdidas y el PnL del día actual.
- **Gestión de credenciales:** Todas las credenciales (token de Telegram, credenciales de Exnova) se gestionan vía variables de entorno / `.env` excluido de git, nunca hardcodeadas en el código.

---

## 7. 🗺️ Roadmap de Desarrollo (Checklist)

### Fase 1: Entorno y Menú de Inicio

- [x]  Crear estructura de carpetas modular en Python.
- [x]  **Diseñar e implementar la interfaz abstracta `BrokerClient`** con métodos `get_candles()`, `place_order()` y `get_balance()`.
- [x]  Implementar `ExnovaAdapter` como primera implementación concreta de `BrokerClient`.
- [x]  Desarrollar menú interactivo (Normal vs. OTC + selección de divisas).
- [x]  Validar conexión WebSocket a través de `ExnovaAdapter` en cuenta DEMO.

> 💡 **Nota de arquitectura:** Construir `BrokerClient` antes del acoplamiento directo evita una refactorización costosa en fases posteriores. Exnova es solo el primer adaptador — el núcleo del bot nunca debe importar Exnova directamente.
> 

### Fase 2: Machine Learning (XGBoost)

- [x]  Script para descargar historial de 10,000+ velas.
- [x]  Generación de features técnicos con [ta](https://github.com/bukosabino/ta) (sustituto de pandas-ta, abandonado).
- [x]  Entrenamiento con **validación walk-forward** (no split aleatorio) para evitar data leakage.
- [x]  Generar **curva de calibración de probabilidades** para determinar el umbral real de confianza.
- [x]  **Análisis de feature importance con SHAP** para entender qué variables impulsan el modelo.
- [x]  Exportación del modelo a archivo `.pkl` con registro en tabla `model_versions`.

### Fase 3: Base de Datos y Backtesting

- [x]  Crear módulo de conexión y tablas en SQLite.
- [x]  Construir script de backtesting considerando la curva histórica de Payouts.
- [x]  ~~Construir capa de abstracción BrokerClient~~ ✅ Movido a Fase 1.
- [x]  Implementar un segundo adaptador de prueba (`MockBrokerAdapter`) para backtesting sin conexión real.

### Fase 3.5: API Exnova propia (desacoplar del vendor)

> 🔧 **Motivación:** `bot/vendor/exnovaapi` es un port de bajo nivel sin mantenimiento (ver nota de arquitectura). No se puede confiar en él para operación continua 24/7 (reconexión, heartbeat, stream de velas). Se sustituye por un cliente WebSocket mínimo, propio, tipado y testeado que implemente **solo** lo que el bot usa. El núcleo sigue desacoplado: `ExnovaAdapter` no cambia su contrato `BrokerClient`.

- [x] Auditar qué superficie real de `exnovaapi` usa `ExnovaAdapter` (auth, `get_balance`, histórico de velas, stream de velas, compra/venta, resultado) — hecho.
- [x] Implementar `bot/broker/exnova_ws.py` (`ExnovaWSClient`): auth por SSID, saldo multi-cuenta (`account_type`), histórico de velas con paginación, stream de velas, compra/venta, confirmación de orden y resultado, heartbeat Ping/Pong.
- [x] Reconexión con **exponential backoff** (2s→4s→8s→… hasta 30s) (Resiliencia, §6).
- [x] Migrar `ExnovaAdapter` de `exnovaapi` a `ExnovaWSClient` manteniendo el mismo contrato (sin import de vendor; balance por `account_type`; `check_connect`; resolución tolerante de activos).
- [x] **Eliminar** `bot/vendor/exnovaapi` — hecho (sin imports activos desde el núcleo).
- [x] Validar paridad: `tests/test_exnova_adapter_integration.py` + `tests/test_exnova_ws_*.py`.

### Fase 3.6: Segundo bróker — IQ Option (misma familia Quadcode)

> 🔧 **Motivación:** el núcleo está desacoplado vía `BrokerClient`; añadir IQ Option demuestra la intercambiabilidad del bróker. IQ Option comparte protocolo WS Quadcode con Exnova pero autentica con **ssid** (cookie de sesión del navegador; el login HTTP responde 403). OTC disponible 24/7.

- [x] Auditar protocolo IQ Option con RE en vivo (wss://ws.iqoption.com/echo/websocket): auth por ssid, `get-first-candles`, velas `candle-generated`, órdenes `binary-options.open-option` v2.0 (vencimiento = timestamp absoluto), resultado vía suscripción `portfolio.position-changed`.
- [x] Implementar `bot/broker/iqoption_ws.py` (`IqOptionWSClient`): auth ssid, saldo por `account_type`, histórico/stream de velas, compra con vencimiento alineado (margen ≥30s), resultado por push `position-changed`, reconexión con exponential backoff.
- [x] Implementar `bot/broker/iqoption.py` (`IqOptionAdapter`): mismo contrato `BrokerClient` (`get_candles`, `get_available_assets`, `place_order`, `check_result`, `get_balance`, `get_payout`). **Nota:** `buy()` devuelve tupla `(ok, id)`; `place_order` extrae el id — no usar `buy()` directo como order_id.
- [x] Credenciales en `.env`: `IQ_OPTION_SSID` (cookie ssid) + `IQ_OPTION_ACCOUNT_TYPE` (PRACTICE|REAL); carga en `bot/config.py`.
- [x] Validar end-to-end en cuenta DEMO real: ciclo completo connect → balance → assets → payout → candles → place_order → check_result (win/loose) → balance final consistente. ✅
- [x] Tests: `tests/test_iqoption_ws_parsing.py` (unitarios sin red), `tests/test_iqoption_ws_integration.py` + `tests/test_iqoption_adapter_integration.py` (contra mock server local `tests/iq_mock.py`; helpers compartidas en `tests/wsutil.py`).
- [x] Fix infra: `[tool.pytest.ini_options] pythonpath = ["."]` en `pyproject.toml` — los tests Exnova existentes **no corrían** (`ModuleNotFoundError: bot`); ahora sí.
- [x] Captura de datos OTC en curso (script en `Temp/opencode/capture_iq.py`, fuera del repo): velas 60s de EURUSD-OTC (active_id 76), ~1 vela/min, a `Temp/opencode/otc_live_76_60.csv`. **Pendiente:** repetir captura a 5m (`SIZE=300`) para alimentar el pipeline ML estándar (build_features → train → backtest) con datos IQ.
- [ ] Evaluar si re-entrenar el modelo con datos IQ Option cambia el accuracy/expectancy (recordar: no hay edge confirmado con datos Exnova; esto es experimentación, no mejora garantizada).

### Fase 4: Integración y Pruebas en DEMO

> ⚠️ La **Fase 3.5** (cliente Exnova propio) debe completarse **antes** de operación continua en demo: no se hace 24/7 sobre el vendor de bajo nivel.

- [ ]  Unir las 2 capas en el bucle principal.
- [ ]  Ejecutar un mínimo de **150 operaciones en mercado Normal y 150 en OTC**, evaluadas y reportadas por separado.

> ⚠️ **Importante:** Las 150 operaciones en DEMO **no garantizan comportamiento en cuenta real**, especialmente en brokers no regulados. Tratar esta fase como **validación preliminar**, no definitiva. El deslizamiento, las condiciones de mercado real y las políticas del bróker pueden diferir significativamente.
> 

### Fase 5: Despliegue en Producción

- [ ]  Crear `Dockerfile` y `docker-compose.yml`.
- [ ]  Configurar e instalar el contenedor en Oracle Cloud Free Tier.

### Fase 6: Análisis y Dashboard

- [ ]  Construir dashboard en **Streamlit o Plotly Dash** conectado directamente a `bot_data.db`.
- [ ]  Visualizar **PnL acumulado** a lo largo del tiempo.
- [ ]  Gráfica de **win rate por par de divisas**.
- [ ]  Distribución **confianza del modelo vs. resultado** (calibración visual).
- [ ]  Cálculo y visualización del **drawdown máximo**.

### Fase 7: Tercer bróker — Binance (futuro)

> 🪙 **Advertencia:** Binance **no es opciones binarias** — es un exchange de cripto (spot/futures). El contrato `BrokerClient` (velas, orden, resultado) aplica conceptualmente, pero `place_order` con vencimiento no existe; el adaptador mapeará a órdenes de mercado + cierre manual / futuros con TP/SL. **Se pospone hasta tener edge predictivo confirmado** (no tiene sentido construir otro transporte para una señal sin ventaja). Distinto del resto del stack: modelo de expiración binaria no aplica.

- [ ] Implementar `bot/broker/binance.py` (`BinanceAdapter` + cliente REST/WS propio, API keys en `.env`) si la señal demuestra edge.
- [ ] Definir semántica de `check_result` para posiciones abiertas (PnL calculado, no push del bróker).
- [ ] Límites de monto propios por símbolo (distintos a $1–$20k de Exnova/IQ).