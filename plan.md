## 🎯 Objetivo del Proyecto

Desarrollar un bot autónomo en **Python** para opciones binarias en la plataforma **Exnova**, utilizando un modelo de Machine Learning de ultra baja latencia (**XGBoost**), filtrado macro con IA (**Gemini 2.0 Flash Lite**), gestión estricta de riesgo y persistencia en **SQLite**.

> 🎓 **Propósito principal:** Este proyecto es fundamentalmente un ejercicio de **aprendizaje aplicado** — ML sobre series temporales, Pandas, ingeniería de features y auditoría de modelos. Su objetivo secundario es servir como **proyecto de portafolio para una transición hacia Analista de Datos**, no como fuente de ingresos.
> 

> ⚠️ **Advertencia de Riesgo**: Las opciones binarias son instrumentos de alto riesgo. Este bot es un proyecto técnico/educativo. Opera siempre en DEMO primero y nunca inviertas capital que no puedas permitirte perder.
> 

> 🔄 **Nota sobre el bróker:** Exnova **no cuenta con regulación de organismos reconocidos** (CySEC, FCA, CNMV) y existen reportes públicos de problemas con retiros. Por tanto, el bróker se trata como una **dependencia intercambiable**, no como un componente fijo del sistema. El núcleo analítico debe funcionar independientemente del bróker conectado. Adicionalmente, en modo OTC los precios son generados por un algoritmo propietario del bróker (no representan mercado real), por lo que el rendimiento del modelo en OTC debe registrarse y evaluarse por separado del rendimiento en mercado Normal, y **no debe considerarse comparable ni extrapolable entre ambos**.
> 

---

## 1. 🚀 Módulo de Inicio y Selección de Mercado

Al ejecutar el bot, el programa mostrará un **menú interactivo en consola** antes de arrancar la monitorización:

- [x]  **Selección de Tipo de Mercado:**
    - **Mercado Real (Normal):** Operación de lunes a viernes. Activa automáticamente la Capa 1 (Gemini) para lectura de noticias.
    - **Mercado OTC:** Operación de fines de semana o activos simulados. Desactiva automáticamente la Capa 1 (las noticias reales no aplican a OTC).
- [x]  **Escaneo Dinámico de Divisas:** Consultar las divisas abiertas en el modo seleccionado vía `BrokerClient.get_available_assets()`, manteniendo el núcleo del bot desacoplado del bróker específico.
- [x]  **Selección de Activos a Monitorizar:** Permitir al usuario elegir una divisa específica, una lista de divisas o la opción "Analizar todas las divisas disponibles" simultáneamente.

---

## 2. 🛠️ Stack Técnico

| Componente | Tecnología | Función Principal |
| --- | --- | --- |
| Lenguaje | Python 3.10+ | Entorno principal del sistema |
| Conexión Broker | BrokerClient + ExnovaAdapter (websocket-client) | Gestión de sesión, recepción de velas y órdenes, desacoplada del bróker específico |
| Análisis Técnico | pandas + ta | Procesamiento de datos y cálculo de indicadores (RSI, EMA, MACD) |
| IA de Señales (Capa 2) | XGBoost (.pkl) | Inferencia local ultra rápida (< 50 ms) para predecir la dirección de la vela |
| IA Macro (Capa 1) | Gemini 2.0 Flash Lite API | Evaluación de noticias en tiempo real con Grounding Search (solo Mercado Real) |
| Base de Datos | SQLite3 | Persistencia de estado, logs de auditoría de gates y métricas de PnL |
| Notificaciones | Bot de Telegram | Envíos de alertas de operaciones, ganancias y errores críticos |
| Infraestructura | Docker + Oracle Cloud (VPS) | Despliegue en contenedor aislado corriendo 24/7 |
| Validación | scikit-learn (TimeSeriesSplit / walk-forward) | Validación temporal sin fuga de información (data leakage) |
| Visualización / Dashboard | Streamlit o Plotly Dash | Panel de análisis de resultados leyendo directamente de SQLite |

> 🔌 **Abstracción BrokerClient:** Definir una **interfaz abstracta** con métodos `get_candles()`, `place_order()` y `get_balance()` para desacoplar por completo el núcleo analítico del bróker específico. Esto permite cambiar de Exnova a cualquier otro bróker modificando únicamente el adaptador.
> 

---

## 3. 🏗️ Arquitectura de 3 Capas

```text
┌─────────────────────────────────────────────────────────────────┐
│ CAPA 1 — Contexto Macro (Async, cada 30 min)                    │
│ Gemini Flash Lite → Analiza noticias y genera sesgo:            │
│ BULLISH / BEARISH / NEUTRAL                                     │
│ (Desactivada automáticamente en Mercado OTC)                    │
└────────────────────────────────┬────────────────────────────────┘
                                 ↓
┌─────────────────────────────────────────────────────────────────┐
│ CAPA 2 — Señal en Tiempo Real (Cada vela, < 50ms)               │
│ ta calcula indicadores → XGBoost evalúa probabilidad            │
│ Solo genera señal si la probabilidad supera el umbral           │
│ ⚠ Umbral a calibrar empíricamente con curva de calibración,    │
│   no fijado arbitrariamente en 68% antes de tener datos reales │
└────────────────────────────────┬────────────────────────────────┘
                                 ↓
┌─────────────────────────────────────────────────────────────────┐
│ CAPA 3 — Gateways de Validación y Ejecución                     │
│ Gate 1: Payout del activo ≥ 75%                                 │
│ Gate 2: Confluencia (Señal local coincide con sesgo Capa 1)     │
│ ⚠ Validar si el sesgo macro cada 30 min aporta valor           │
│   predictivo real a decisiones de velas cortas (no asumido)    │
│ Gate 3: Sincronización al segundo 59.8 de la vela               │
│ Gate 4: Validación de límites en RiskManager                    │
│ → Envío de orden a Exnova                                       │
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
- **Gestión de credenciales:** Todas las credenciales (API keys de Gemini, token de Telegram, credenciales de Exnova) se gestionan vía variables de entorno / `.env` excluido de git, nunca hardcodeadas en el código.

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
- [ ]  Entrenamiento con **validación walk-forward** (no split aleatorio) para evitar data leakage.
- [ ]  Generar **curva de calibración de probabilidades** para determinar el umbral real de confianza.
- [ ]  **Análisis de feature importance con SHAP** para entender qué variables impulsan el modelo.
- [ ]  Exportación del modelo a archivo `.pkl` con registro en tabla `model_versions`.

### Fase 3: Base de Datos y Backtesting

- [ ]  Crear módulo de conexión y tablas en SQLite.
- [ ]  Construir script de backtesting considerando la curva histórica de Payouts.
- [x]  ~~Construir capa de abstracción BrokerClient~~ ✅ Movido a Fase 1.
- [ ]  Implementar un segundo adaptador de prueba (`MockBrokerAdapter`) para backtesting sin conexión real.

### Fase 4: Integración y Pruebas en DEMO

- [ ]  Integrar el módulo asíncrono de Gemini Flash Lite (Capa 1).
- [ ]  Unir las 3 capas en el bucle principal.
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