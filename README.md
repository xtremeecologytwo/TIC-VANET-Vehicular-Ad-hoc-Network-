# SmartCityNet — Consola de simulación y optimización VANET

**Trabajo de Integración Curricular — Redes Vehiculares Ad-hoc (VANETs) · Escuela Politécnica Nacional**

Plataforma web que, a partir de un **área real dibujada en un mapa**, genera un
escenario de tráfico con **SUMO**, calcula la **conectividad V2V/V2I con línea de
vista (LoS)** considerando los edificios como obstáculos, la extiende a **varios
saltos**, y resuelve el **despliegue óptimo de RSU** (*Road Side Units*) con
**CPLEX**. Todo el flujo ocurre en una sola consola:

```
área en el mapa → escenario SUMO → RSU candidatas → conectividad V2V/V2I
              → multisalto → dataset CVR → optimización → despliegue de RSU
```

La aplicación es un **frontend React** que consume una **API FastAPI**; la API
reutiliza el **backend Python** (la ciencia del proyecto) sin reimplementar nada.

---

## 🧭 Arquitectura

```
┌──────────────────────────┐     HTTP /api      ┌──────────────────────────────┐
│  web/  (React + Vite)     │  ───────────────►  │  api/  (FastAPI)             │
│  SPA: mapa, controles,    │                    │  Traduce peticiones HTTP en  │
│  animación, tablas        │  ◄───────────────  │  llamadas al backend y       │
│                           │   JSON (lat/lon)   │  devuelve JSON en lat/lon    │
└──────────────────────────┘                    └───────────────┬──────────────┘
                                                                 │  (import directo)
                                       ┌─────────────────────────┴─────────────────────────┐
                                       │  backend/            +   optimizacion/             │
                                       │  SUMO · LoS · V2V/V2I ·  modelo docplex/CPLEX       │
                                       │  multisalto · export     (despliegue de RSU)        │
                                       └────────────────────────────────────────────────────┘
```

**Por qué así:** el backend ya estaba bien factorizado en funciones puras que
devuelven `dict`/`list`. La API sólo las envuelve y **convierte las coordenadas
SUMO (metros) a lat/lon** para que el mapa del navegador las dibuje directo. Toda
la matemática (LoS, matrices de conectividad, multisalto, optimización) vive en
`backend/` y `optimizacion/` y es idéntica a la del documento del TIC.

---

## 📂 Estructura del proyecto

```
TIC-VANET/
├── api/                     # 🌐 API REST (FastAPI) — capa HTTP sobre el backend
│   └── main.py              #    endpoints + estado del escenario + conversión lat/lon
│
├── web/                     # 🖥️ Frontend React (Vite + TypeScript)
│   ├── src/
│   │   ├── App.tsx          #    consola: estado, flujo M1→M2→M3, línea de tiempo
│   │   ├── App.css          #    estilos de la consola + marco "plotter"
│   │   ├── api/client.ts    #    cliente HTTP tipado de la API
│   │   ├── design/tokens.css#    sistema de diseño (paleta, tipografía)
│   │   └── components/
│   │       ├── ScenarioMap.tsx  # mapa (react-leaflet): dibujo del área + capas
│   │       └── ResultsTabs.tsx  # tablas de tuplas, matrices A/B, multisalto
│   └── README.md            #    detalle del frontend
│
├── backend/                 # ⚙️ Lógica VANET (Python puro, sin dependencia de UI)
│   ├── descargar_osm.py     #    descarga el área desde OpenStreetMap
│   ├── sumo_pipeline.py     #    netconvert → polyconvert → randomTrips
│   ├── parsear_xml.py       #    junctions/edificios, proyección, filtrado de RSU
│   ├── simulacion_sumo.py   #    corre SUMO y parsea el FCD (posiciones por instante)
│   ├── visibilidad.py       #    línea de vista (LoS) + tuplas V2I y V2V (Matriz A)
│   ├── multisalto.py        #    matrices Ã, R_h, S_h, D_H, vector d
│   └── exportar_dat.py      #    construye el dataset CVR ⟨s,h,v,r⟩ para el solver
│
├── optimizacion/            # 🧮 Optimización del despliegue de RSU
│   ├── optimizar_rsu.py     #    modela y resuelve con docplex/CPLEX
│   ├── rsu_model.mod        #    modelo OPL de referencia (misma matemática)
│   └── rsu_micro.dat / rsu_backend.dat  # datos de ejemplo / generado del backend
│
├── output/                  # 📤 Artefactos de una corrida (SUMO, JSON de tuplas…)
├── requirements.txt         # 📦 dependencias Python (backend + API)
├── DESPLIEGUE.md            # 🚀 dónde y cómo desplegar (pendiente)
└── mini_proyecto_vanet.py   # 📚 demo didáctica del flujo completo (backend)
    ejemplo_multisalto.py    #    (scripts educativos, independientes de la app)
    explicar_multisalto.py
```

---

## 🚀 Instalación y ejecución

**Requisitos:** **Python 3.10** (única versión que corre el motor completo de
CPLEX), **Node 18+**, y **SUMO** con `netconvert`/`polyconvert` en el `PATH` y
`SUMO_HOME` configurado.

La app son **dos procesos**: la API (Python) y el frontend (React).

```bash
# 1) API — desde la raíz del repo
python -m venv .venv
.venv\Scripts\activate                 # Windows  (Linux/Mac: source .venv/bin/activate)
pip install -r requirements.txt
uvicorn api.main:app --reload --port 8000

# 2) Frontend — desde web/
cd web
npm install                            # sólo la primera vez
npm run dev                            # abre http://localhost:5173
```

En desarrollo, Vite **proxya** `/api` → `http://localhost:8000` (ver
`web/vite.config.ts`), así que no hay problemas de CORS y el cliente usa rutas
relativas. Si ya existe un escenario en `output/`, la API lo **carga al arrancar**
y el frontend lo rehidrata (muestra edificios/RSU y permite optimizar directo).

---

## 🕹️ Flujo de uso (en la interfaz)

El pipeline es una secuencia real, reflejada en el *stepper* **M1 → M2 → M3**:

1. **Seleccionar área** — botón *"◱ Seleccionar área"* y **dos clics** en el mapa
   para dibujar el rectángulo.
2. **M1 · Generar escenario** — descarga OSM y corre SUMO (red vial + edificios).
3. **Filtrar RSU** — reduce las intersecciones a RSU candidatas (grado + clúster).
4. **M2 · Simular conectividad** — corre el tráfico, calcula LoS y genera las
   tuplas V2I/V2V y las matrices; aparece la **línea de tiempo** para animar
   vehículos y enlaces por instante.
5. **M3 · Optimizar despliegue** — construye el dataset CVR y resuelve con CPLEX;
   las **RSU desplegadas** se resaltan en verde sobre el mapa.

Debajo, la sección **Análisis** muestra las **tuplas** V2I/V2V, las **matrices
A/B** del instante activo y el **resumen multisalto**.

---

## 🌐 La API (`api/main.py`)

Cada endpoint traduce una petición HTTP en llamadas al backend y devuelve JSON.
El servidor mantiene **un escenario en memoria** (herramienta de un solo usuario)
y lo persiste en `output/`. Las geometrías salen en **[lat, lon]** listas para el
mapa.

| Método y ruta | Qué hace | Funciones del backend que usa |
|---|---|---|
| `GET /api/health` | Sonda de vida | — |
| `GET /api/state` | Qué hay cargado (escenario/RSU/simulación, conteos, *bounds*) | — |
| `GET /api/scenario/buildings` | Edificios del escenario en lat/lon | `convertir_xy_a_lonlat` |
| `POST /api/scenario/generate` | **M1**: descarga OSM + SUMO + parseo | `descargar_mapa_osm`, `ejecutar_pipeline_sumo`, `parsear_junctions`, `parsear_edificios`, `obtener_proyeccion` |
| `POST /api/rsu/filter` | Filtra junctions → RSU candidatas | `filtrar_junctions_rsu` |
| `POST /api/simulate` | **M2**: FCD + LoS + tuplas V2I/V2V + matrices | `ejecutar_simulacion_sumo`, `parsear_fcd`, `generar_tuplas_visibilidad`, `generar_tuplas_v2v` |
| `GET /api/timesteps` | Instantes disponibles para la animación | — |
| `GET /api/connectivity?t=` | Vehículos + enlaces V2I/V2V de un instante | `convertir_xy_a_lonlat` |
| `POST /api/optimize` | **M3**: construye CVR y resuelve | `exportar_dat_desde_memoria`, `optimizar` |
| `GET /api/tuples/v2i` · `/v2v` | Tuplas de conectividad (paginadas) | — |
| `GET /api/multihop?t=&H=` | A, B, R_h, S_h, D_H, d y resumen de un instante | `analizar_timestep` |

**Convención de coordenadas.** SUMO trabaja en **metros** (x, y). La API las
convierte a **lat/lon** con `convertir_xy_a_lonlat`, que usa la **proyección real
de SUMO** (UTM, vía `pyproj`) leída del `.net.xml` (`projParameter` + `netOffset`).
Esto es clave: la interpolación lineal entre *bounding boxes* fallaba porque
`netconvert` **recorta** la red (su `convBoundary` ya no coincide con el
`origBoundary` de la descarga), lo que desplazaba edificios y RSU ~178 m.

Documentación interactiva de la API: con el servidor arriba, abre
`http://localhost:8000/docs` (Swagger generado por FastAPI).

---

## ⚙️ El backend (la ciencia)

### 1. Escenario — `descargar_osm.py` + `sumo_pipeline.py` + `parsear_xml.py`
- `descargar_mapa_osm(bbox…)` baja el `.osm` del área desde la API de OSM.
- `ejecutar_pipeline_sumo(...)` corre **netconvert** (red vial), **polyconvert**
  (edificios) y **randomTrips** (rutas de N vehículos).
- `parsear_junctions` / `parsear_edificios` extraen intersecciones y polígonos.
- `filtrar_junctions_rsu(min_grado, radio_cluster)` elige las RSU candidatas en
  dos pasos: **grado** (nº de vecinos únicos en el grafo no dirigido, así una
  intersección en cruz tiene grado 4) y **clustering espacial** *greedy* (si dos
  candidatas están a < `radio_cluster` m, se conserva la de mayor grado; empate
  por id, determinista).

### 2. Conectividad — `visibilidad.py`
- **Línea de vista (LoS):** un vehículo ve a un RSU (o a otro vehículo) si están
  dentro del radio del OBU **y** ningún edificio corta el segmento. La
  intersección segmento–edificio usa el test de **orientación CCW** (O(1) por
  arista) más el chequeo de extremos dentro del polígono (*ray casting*).
- **Rendimiento:** el cálculo escala a **1000 vehículos** gracias a un **índice
  espacial (grid)** de RSU y de vehículos (cada uno sólo se compara con su
  vecindario 3×3), un **grid de edificios por segmento** (cada par sólo prueba
  los edificios de su trayecto) y **bounding boxes precalculados**. Son
  optimizaciones **exactas**: dan el mismo resultado que la fuerza bruta.
- Salidas: tuplas **V2I** ⟨t, V, RSU⟩ (Matriz B) y **V2V** ⟨t, Vi, Vj⟩ con las
  **matrices A** (vehículo×vehículo) por instante.

### 3. Multisalto — `multisalto.py`
Para cada instante, a partir de A (V2V) y B (V2I):

```
Ã  = A ∨ I           (identidad para conservar conexiones al subir de salto)
R₁ = B ,  Rₕ = β(Ã · Rₕ₋₁)      (β = binarización: importa si hay ≥1 camino)
Sₕ = Rₕ − Rₕ₋₁       (mínimo nº de saltos EXACTAMENTE h)
D_H = J − R_H        (1 = el vehículo NO alcanza ese RSU con ≤ H saltos)
dᵢ = 1 si la fila i de R_H es toda ceros (vehículo aislado)
```

`analizar_timestep(...)` devuelve A, B, todas las Rₕ/Sₕ, D_H, d y un resumen por
salto. Es lo que alimenta el visor de matrices y de multisalto del frontend.

### 4. Dataset CVR — `exportar_dat.py`
Convierte cada instante en un **escenario** *s* y cada `1` de las Sₕ en una tupla
**⟨s, h, v, r⟩** (vehículo *v* alcanza el RSU *r* en mínimo *h* saltos, en el
escenario *s*). Añade el RSU artificial `r_∞` (desconexión, salto H+1) para que el
modelo siempre sea factible. Construye también los conjuntos y parámetros del
modelo (costos, capacidades, penalización por saltos, carga).

### 5. Optimización — `optimizacion/optimizar_rsu.py`
Traducción 1:1 del modelo OPL (`rsu_model.mod`, Urquiza-Aguiar et al.) a **docplex**:

```
minimizar  Σ Sel[r]·Cost[r]  +  Σ Rts[t]·P[t.h]·L[t.s][t.v]
sujeto a   toda la carga de cada vehículo se sirve; sólo se usa un RSU si se
           despliega; capacidad por RSU; nº máximo de RSU (MaxR); Sel[r_∞]=1.
```

`optimizar(datos)` devuelve el valor objetivo, el estado del solver y los **ids de
RSU a desplegar**. El motor **community** de CPLEX se limita a 1000 variables; el
problema real necesita el motor **completo** (licencia académica gratuita de IBM),
que sólo soporta **Python 3.7–3.10** — por eso el proyecto fija **Python 3.10**.

---

## 🖥️ El frontend (`web/`)

React + TypeScript + Vite. **react-leaflet** para el mapa. El diseño es una
**consola científica/ingeniería** (fondo claro, un acento azul acero, verde
semántico para "óptimo", datos en monoespaciada, marco tipo *plotter*).

| Archivo | Rol |
|---|---|
| `src/api/client.ts` | Cliente HTTP **tipado**: una función por endpoint (`generate`, `filterRsu`, `simulate`, `connectivity`, `optimize`, `timesteps`, `tuplesV2i/v2v`, `multihop`) y las interfaces de sus respuestas. |
| `src/App.tsx` | **Orquestador**: mantiene el estado (parámetros, escenario, RSU, KPIs, instante activo), define las acciones `generar / filtrar / simular / optimizar` (cada una llama a `client.ts` y actualiza el mapa y los KPIs), y controla la **reproducción** de la línea de tiempo. |
| `src/components/ScenarioMap.tsx` | El mapa. `DrawRectangle` implementa la **selección del área por 2 clics** (sin leaflet-draw); `FitBounds` encuadra el escenario e invalida el tamaño para que no haya desalineo; las capas dibujan edificios (GeoJSON), RSU candidatas/desplegadas y, por instante, vehículos y enlaces V2I/V2V. |
| `src/components/ResultsTabs.tsx` | Sección **Análisis**: tablas de tuplas V2I/V2V, rejillas binarias de las **matrices A/B** del instante y el **resumen multisalto** (pares alcanzables por salto + vehículos desconectados). |
| `src/design/tokens.css` · `src/App.css` | Sistema de diseño y estilos de la consola. |

Más detalle y estado de la migración: [`web/README.md`](web/README.md).

---

## 📝 Notas importantes

- **Datos precargados.** El `output/` incluido es una demo. Sus edificios/RSU se
  alinean bien (proyección real), pero el `fcd.xml` puede ser de otra corrida, así
  que la **animación** de vehículos sólo es fiel tras **generar un escenario
  nuevo** (Generar → Filtrar → Simular).
- **CPLEX / Python 3.10.** Ver arriba: el motor completo exige Python ≤ 3.10 y el
  backend exige ≥ 3.10 → **3.10** es la única versión que corre ambas cosas.
- **Despliegue.** Pendiente. La app necesita un **servidor real** (SUMO + CPLEX en
  el backend), no un hosting estático. Ver [`DESPLIEGUE.md`](DESPLIEGUE.md).

---

## 📄 Licencia

Trabajo de Integración Curricular — Escuela Politécnica Nacional.
