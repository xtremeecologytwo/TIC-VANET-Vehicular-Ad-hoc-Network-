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
│   ├── main.py              #    endpoints + estado del escenario + conversión lat/lon
│   └── cronometro.py        #    mide y imprime en consola el tiempo de cada etapa
│
├── web/                     # 🖥️ Frontend React (Vite + TypeScript)
│   ├── src/
│   │   ├── App.tsx          #    consola: estado, flujo M1→M2→M3, línea de tiempo
│   │   ├── App.css          #    estilos de la consola + marco "plotter"
│   │   ├── api/client.ts    #    cliente HTTP tipado de la API
│   │   ├── design/tokens.css#    sistema de diseño (paleta, tipografía)
│   ├── .env.example         #    plantilla: copiar a .env.local y poner VITE_CARTO_KEY
│   │   └── components/
│   │       ├── ScenarioMap.tsx  # mapa (react-leaflet): dibujo del área + capas
│   │       ├── ResultsTabs.tsx  # tablas de tuplas, matrices A/B, multisalto
│   │       └── CapaFisica.tsx   # panel 802.11p: curva de recepción, r80/r90, Γ_H, α·C₀
│   └── README.md            #    detalle del frontend
│
├── backend/                 # ⚙️ Lógica VANET (Python puro, sin dependencia de UI)
│   ├── flujo.py             #    el flujo M1→M2 como funciones puras (lo usan la API y el CLI)
│   ├── catalogo.py          #    registro SQLite de corridas + manifest.json de cada carpeta
│   ├── almacen.py           #    reutilización de etapas ya calculadas (datos/cache/)
│   ├── capa_fisica.py       #    radio, Γ_H y capacidad de 802.11p desde las notas del tutor
│   ├── descargar_osm.py     #    descarga el área desde OpenStreetMap
│   ├── procesos.py          #    registro de subprocesos, para poder cancelarlos
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
│   └── rsu_micro.dat        #    micro-ejemplo de validación (rsu_backend.dat es generado)
│
├── scn.py                   # 🧪 CLI de campañas: corridas por lotes con semilla y catálogo
├── consultas.sql            #    consultas listas para DB Browser sobre datos/catalogo.sqlite
├── pruebas/determinismo.py  #    prueba de reproducibilidad (misma semilla → mismo escenario)
├── pruebas/capa_fisica.py   #    C₀/C₁ contra las tablas del tutor + su ejemplo de radios y Γ
├── Luis Urquiza/            # 📡 material del tutor: channel_functions.py, run_experiments.py, notas PDF
├── herramientas/            # 🔧 osmconvert / osmfilter (binarios, no versionados; ver su README)
├── requirements.txt         # 📦 dependencias Python (backend + API)
└── mini_proyecto_vanet.py   # 📚 demo didáctica del flujo completo (backend)
    ejemplo_multisalto.py    #    (scripts educativos, independientes de la app)
    explicar_multisalto.py
```

**Carpetas que existen en local pero NO se versionan** (ver [`.gitignore`](.gitignore)):

| Carpeta | Qué es | Por qué no sube |
|---|---|---|
| `datos/` | **Todas las corridas** (`corridas/`), el catálogo (`catalogo.sqlite`) y el almacén de etapas (`cache/`) — ver [Campañas, catálogo y almacén](#campanas) | Se **regenera** desde la semilla. Una corrida de ciudad deja cientos de MB |
| `.osm_cache/` | Mapas ya recortados o descargados, por bbox | Ídem; con 11 áreas ocupaba 822 MB |
| `datos/osm/` | El extracto de Ecuador de Geofabrik (125 MB) y su `.meta.json` | Se baja con `scn.py extracto` — ver [Mapas sin red](#extracto) |
| `herramientas/*.exe` | `osmconvert` y `osmfilter` | Binarios de terceros; `herramientas/README.md` dice de dónde |
| `output/` | Carpeta única de la web en versiones anteriores | Solo se lee si existe; la web guarda ahora en `datos/corridas/` |
| `web/node_modules/` | Dependencias del frontend | Se reinstalan con `npm install` desde `package-lock.json` |
| `explicaciones/` | Documentos de estudio (PDF + LaTeX) | Documentación de trabajo, no es el programa |
| `Jornadas SmartCityNet/` | Artículo científico y sus figuras | Ídem |

---

## 🚀 Instalación y ejecución

**Requisitos:** **Python 3.10** (única versión que corre el motor completo de
CPLEX), **Node 18+**, y **SUMO** con `netconvert`/`polyconvert` en el `PATH` y
`SUMO_HOME` configurado.

La app son **dos procesos** que deben estar encendidos a la vez: la **API**
(Python/FastAPI, hace la ciencia) y el **frontend** (React, la interfaz). El
frontend habla con la API; por eso necesitas ambos.

**Primera vez (instalar dependencias):**
```bash
python -m venv .venv
.venv\Scripts\activate                 # Windows  (Linux/Mac: source .venv/bin/activate)
pip install -r requirements.txt        # dependencias del backend/API
cd web && npm install && cd ..         # dependencias del frontend
```

**Cada vez que quieras usar la app** — abre **dos terminales**:
```bash
# Terminal 1 — backend (API en http://localhost:8000)
uvicorn api.main:app --reload --port 8000 --timeout-graceful-shutdown 5

# Terminal 2 — frontend (app en http://localhost:5173)
cd web
npm run dev
```
Luego abre **http://localhost:5173** en el navegador.

> **Mapa base con marca de agua.** CARTO exige una API key para sus teselas
> raster. Sin ella la app funciona igual, pero el mapa sale con *"API KEY
> REQUIRED"* estampado. Para quitarla: copia `web/.env.example` a
> `web/.env.local` y pon tu clave en `VITE_CARTO_KEY` (gratis en
> [carto.com/basemaps/apikey](https://carto.com/basemaps/apikey)). El archivo
> `.env.local` **no se versiona**. (`uvicorn api.main:app`
significa: correr el objeto `app` definido en `api/main.py`.)

**Atajo (Windows):** en vez de las dos terminales, ejecuta **`.\dev.ps1`** en la
raíz del repo (clic derecho → *Ejecutar con PowerShell*). Abre las dos ventanas
solo (la API y el frontend) y te indica las URLs.

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
   las **RSU desplegadas** se resaltan en verde sobre el mapa. El panel trae dos
   casillas: **"Limitar nº de RSU (MaxR)"** (ver *[MaxR desde la interfaz](#maxr)*)
   y **"Limitar el tiempo del solver"** (ver *[El límite de tiempo](#solver)*),
   ambas apagadas equivalen a "sin límite".

Debajo, la sección **Análisis** muestra las **tuplas** V2I/V2V, las **matrices
A/B** del instante activo y el **resumen multisalto**.

**Cada clic queda cronometrado en la consola del backend** (la terminal donde
corre `uvicorn`): ver *[Medición de tiempos](#tiempos)*.

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
| `POST /api/scenario/generate` | **M1**: corta lo que hubiera en marcha, descarga OSM + SUMO + parseo | `descargar_mapa_osm`, `ejecutar_pipeline_sumo`, `parsear_junctions`, `parsear_edificios`, `obtener_proyeccion` |
| `POST /api/rsu/filter` | Filtra junctions → RSU candidatas | `filtrar_junctions_rsu` |
| `POST /api/simulate` | **M2**: FCD + LoS + tuplas V2I/V2V + matrices | `ejecutar_simulacion_sumo`, `parsear_fcd`, `generar_tuplas_visibilidad`, `generar_tuplas_v2v` |
| `GET /api/timesteps` | Instantes disponibles para la animación | — |
| `GET /api/connectivity?t=` | Vehículos + enlaces V2I/V2V de un instante | `convertir_xy_a_lonlat` |
| `POST /api/optimize` | **M3**: construye CVR, resuelve (`H`, `max_rsu`, `limite_tiempo`, `lexicografico`) y **registra la corrida en el catálogo**; responde su `corrida` (uuid) y `carpeta` | `exportar_dat_desde_memoria`, `optimizar`, `registrar_corrida_completa` |
| `GET /api/tuples/v2i` · `/v2v` | Tuplas de conectividad (paginadas) | — |
| `GET /api/multihop?t=&H=` | A, B, R_h, S_h, D_H, d y resumen de un instante | `analizar_timestep` |
| `GET /api/fisica/opciones` | Tasas PHY, tamaños, criterios, α recomendados y si están los CSV del tutor | `capa_fisica.opciones` |
| `GET /api/fisica/resumen?rate=&packet_bytes=&escenario=&criterio=&alfa=&carga_kbps=&semilla=&n=` | Curva de recepción, r80/r90, Γ_H, C₀ y los parámetros ya traducidos para M2/M3 — ver [Capa física](#fisica) | `capa_fisica.resumen` |

**Convención de coordenadas.** SUMO trabaja en **metros** (x, y). La API las
convierte a **lat/lon** con `convertir_xy_a_lonlat`, que usa la **proyección real
de SUMO** (UTM, vía `pyproj`) leída del `.net.xml` (`projParameter` + `netOffset`).
Esto es clave: la interpolación lineal entre *bounding boxes* fallaba porque
`netconvert` **recorta** la red (su `convBoundary` ya no coincide con el
`origBoundary` de la descarga), lo que desplazaba edificios y RSU ~178 m.

Documentación interactiva de la API: con el servidor arriba, abre
`http://localhost:8000/docs` (Swagger generado por FastAPI).

---

<a id="tiempos"></a>

## ⏱️ Medición de tiempos por consola (`api/cronometro.py`)

Cada acción del usuario se **cronometra y se imprime en la terminal donde corre
`uvicorn`**. No aparece nada en la interfaz: es una herramienta de medición para
experimentar (por ejemplo, comparar el mismo mapa **con y sin** la restricción
`MaxR`, o ver cuánto pesa el solver frente al resto del pipeline).

**Dos niveles de medida:**

| Nivel | Qué mide | ¿Suma al total? |
|---|---|---|
| **Etapa** | Una acción del usuario = **un clic** (Generar, Filtrar, Simular, Optimizar) | ✅ sí |
| **Subetapa** | Una fase interna de esa acción (descarga OSM, SUMO, LoS, solver…) | ❌ no: su tiempo ya está dentro de la etapa |

**Cuándo empieza y termina una sesión de medición:**

- **Generar escenario** abre una **sesión nueva** (reinicia los contadores) y
  escribe la cabecera con los parámetros de la corrida.
- Cada etapa posterior imprime su tiempo y el **acumulado** de la sesión.
- **Optimizar despliegue** cierra el flujo e imprime la **tabla resumen con la
  suma total** y el peso relativo (%) de cada etapa.
- Si se empieza por la mitad (retomando el escenario guardado en `output/`), la
  sesión se abre sola y lo indica: *"sesion iniciada sobre escenario existente"*.

**Ejemplo real de salida** (escenario retomado + una optimización con `MaxR = 20`):

```
================================================================================
  SmartCityNet - CRONOMETRO DE ETAPAS   (sesion iniciada sobre escenario existente)
================================================================================

[1] Filtrar RSU candidatas (grado>=4, cluster=20 m)
      - Grado + clustering espacial .........................     3.255 s
    > etapa     3.292 s  |  acumulado     3.292 s

[2] M3 - Optimizar despliegue (H=2, MaxR=20)
      - Multisalto + construccion del CVR (.dat) ............     4.671 s
      - Solver CPLEX (branch & bound) .......................    21.873 s
    > etapa    26.558 s  |  acumulado    29.850 s

================================================================================
  RESUMEN DE TIEMPOS
================================================================================
   1. Filtrar RSU candidatas (grado>=4, cluster=20 m) .........     3.292 s   ( 11.0 %)
   2. M3 - Optimizar despliegue (H=2, MaxR=20) ................    26.558 s   ( 89.0 %)
  ----------------------------------------------------------------------------
      TOTAL ...................................................    29.850 s
================================================================================
```

**Qué se mide en cada etapa:**

| Etapa (clic) | Subetapas |
|---|---|
| `M1 - Generar escenario` | Descarga OSM · SUMO (netconvert/polyconvert/trips) · Parseo junctions + edificios · Conversión a lat/lon |
| `Filtrar RSU candidatas` | Grado + clustering espacial |
| `M2 - Simular conectividad` | Simulación SUMO (tráfico + FCD) · Parseo del FCD · LoS V2I · LoS V2V |
| `M3 - Optimizar despliegue` | Multisalto + construcción del CVR (`.dat`) · Solver CPLEX (con una nota debajo: `status` de CPLEX, tiempo del motor y límite usado) |

El nombre de cada etapa incluye **los parámetros con los que se midió** (grado,
radio, `H`, `MaxR`…), de modo que la consola queda como bitácora de la corrida.
Las peticiones de la línea de tiempo (`/api/connectivity`, `/api/multihop`) **no**
se cronometran: se disparan solas al animar y ensuciarían la medición.

**API del módulo** (por si se quiere instrumentar algo más):

| Función | Qué hace |
|---|---|
| `nueva_sesion(titulo)` | Reinicia contadores e imprime la cabecera |
| `etapa(nombre)` | *Context manager*: mide una acción del usuario y la suma al total |
| `subetapa(nombre)` | *Context manager*: mide una fase interna (informativa) |
| `resumen()` | Imprime la tabla final con la suma y devuelve `{pasos, total}` |
| `nota(texto)` | Imprime una línea informativa bajo la subetapa recién medida |

`subetapa` cede además un objeto `Medicion`: al salir del `with`, `m.segundos`
guarda lo que tardó, por si hay que devolvérselo al frontend.

> El marco de la tabla es **ASCII puro** a propósito: la consola de Windows no
> siempre puede imprimir caracteres de dibujo o emojis, y `_emitir()` degrada con
> elegancia si algún acento no cabe en la página de códigos activa.

---

<a id="maxr"></a>

## 🎚️ MaxR desde la interfaz — limitar el nº de RSU

`MaxR` es la restricción del modelo que acota **cuántas RSU se pueden desplegar**
(Ec. 5 del modelo: `Σ_{r∈R\{r_inf}} y_r ≤ MaxR`). Antes solo se podía tocar desde
la línea de comandos (`--max-rsu`); ahora está en el panel **M3 · Optimización**:

| Control | Estado | Qué se envía a la API | Efecto en el modelo |
|---|---|---|---|
| ☐ *Limitar nº de RSU (MaxR)* | **apagado (por defecto)** | `max_rsu: null` | `exportar_dat` fija `MaxR` = nº de RSU candidatas ⇒ la restricción **existe pero nunca ata**: es el comportamiento de siempre |
| ☑ *Limitar nº de RSU (MaxR)* | encendido | `max_rsu: <número>` | El solver no puede desplegar más de ese número; si hace falta, deja vehículos desconectados (cayendo en `r_inf`, con su penalización) |

El campo numérico se acota automáticamente a `[1, nº de RSU candidatas]`. Tras
optimizar, el KPI **MaxR** muestra el valor usado — `sin límite (N)` cuando la
casilla está apagada, siendo `N` el número de candidatas.

**Para qué sirve:** permite medir, **sobre el mismo mapa y la misma simulación**,
cuánto cambia el tiempo de resolución y la calidad de la solución al restringir el
presupuesto de infraestructura. Con la restricción floja el problema es "fácil"
(el solver despliega todo lo que reduce penalización); al apretarla se vuelve una
elección combinatoria real y el *branch & bound* trabaja mucho más.

---

<a id="solver"></a>

## 🚦 El límite de tiempo del solver y el KPI *Solver*

**El programa no tiene límite de tiempo.** M1 (OSM + SUMO), el filtrado y M2
(simulación + LoS) tardan lo que tengan que tardar: no hay *timeout* en el
navegador, ni en el proxy de Vite, ni en `uvicorn`. Lo único acotado es la
búsqueda de CPLEX en M3, con `limite_tiempo` — y es **configurable desde la
interfaz**:

| Casilla *"Limitar el tiempo del solver"* | Se envía | Efecto |
|---|---|---|
| ☑ encendida (por defecto, 60 s) | `limite_tiempo: <segundos>` | Al agotarlo, CPLEX devuelve la mejor solución encontrada. Rango 5–3600 s |
| ☐ apagada | `limite_tiempo: null` | **Sin límite**: busca hasta demostrar el óptimo. Puede tardar mucho y la petición queda esperando |

**Por qué existe ese límite.** El *branch & bound* hace dos trabajos: **encontrar**
una buena combinación de RSU (rápido) y **demostrar** que ninguna otra es mejor
(lento). Lo caro es lo segundo. Sin límite, un problema grande (grado bajo + 1000
vehículos + `H` alto) puede quedarse minutos demostrando algo que ya encontró, y
desde la interfaz solo se ve el ⏳. Con límite, CPLEX **para de buscar y entrega la
mejor solución que tenía**: nunca se pierde el resultado, solo el certificado de
optimalidad. Además el modelo es **siempre factible** por diseño (el RSU artificial
`r_inf` permite desconectar a cualquier vehículo pagando `P[hmax]`), así que el
caso "no encontró nada" prácticamente no ocurre.

**Cómo saberlo desde la interfaz.** Tras optimizar aparecen dos KPIs nuevos:

| KPI | Qué muestra |
|---|---|
| **Cobertura** | **La métrica del proyecto**: % de pares (instante, vehículo) que quedan comunicados, con el conteo debajo |
| **Desconectados** | Pares que caen en el RSU artificial `r_inf` |
| **Multisalto** | Pares conectados a 2–H saltos (puenteados por V2V) y cuántos van directos a una RSU |
| **RSU desplegadas** | Cuántas antenas usa la solución |
| **Solver** | *Óptimo demostrado* (verde) o *Cortado por tiempo* (ámbar), con una frase debajo explicando qué significa |
| **Tiempo solver** | Segundos que consumió el **motor** CPLEX y contra qué límite (`de un límite de 60 s` / `topó el límite de 60 s`) |

El bloque `cobertura` de la respuesta trae `n_pares`, `conectados`,
`desconectados`, `cobertura_pct`, `directos`, `multisalto` y `por_salto`
(carga servida en cada nivel de salto). Se calcula en
`optimizar()` a partir de las variables `Rts` de la solución, y también se
imprime en la consola del backend bajo la subetapa del solver.

La API los devuelve en el bloque `solver` de `POST /api/optimize`:

| Campo | Qué es |
|---|---|
| `status` | Frase cruda de CPLEX (`integer optimal solution`, `time limit exceeded`…) |
| `etiqueta` / `detalle` | La traducción legible que pinta el KPI |
| `optimo` | `true` si CPLEX terminó por su cuenta (incluye *integer optimal, tolerance*) |
| `corto_por_tiempo` | `true` si agotó el presupuesto y devolvió la mejor solución hallada |
| `segundos` | Tiempo del **motor** (`solve_details.time`): es el que se compara con el límite |
| `segundos_total` | Armado del modelo **+** motor. Siempre mayor; por eso `segundos_total` puede pasar del límite sin que el solver lo haya topado |
| `limite_tiempo` | El tope que se usó en esa corrida (`null` = sin límite) |

> **Por qué se separan `segundos` y `segundos_total`.** Construir el modelo
> docplex (decenas de miles de tuplas `CVR`) toma varios segundos y **no** cuenta
> para el límite: `set_time_limit` solo gobierna la resolución. Medido con el
> reloj, una corrida con tope de 5 s dio `segundos_total = 5.64 s` pero
> `segundos = 1.97 s` de motor, con `status = integer optimal, tolerance`: no
> topó nada. Comparar el total contra el límite habría dado un falso positivo.

**Al comparar tiempos entre configuraciones**, revisa el KPI *Solver* en cada
corrida: si sale **Cortado por tiempo**, el número medido es el tope que pusiste
tú, no la dificultad del problema — sube el tope (o quítalo) y repite esa fila.

### ¿Cortar por tiempo cuesta conectividad?

Es la pregunta que importa, porque el objetivo del proyecto es **conectar al mayor
número de vehículos**. Medido con los pesos actuales sobre `output/`, con MaxR
libre y `H = 3`:

| Tope | Motor | Z | **Pares desconectados** | Cobertura | RSU | Estado |
|---|---|---|---|---|---|---|
| 30 s | 16,4 s | 177 330 | **139** | 96,23 % | 249 | cerró |
| 60 s | 16,6 s | 177 330 | **139** | 96,23 % | 249 | cerró |
| 300 s | 16,8 s | 177 330 | **139** | 96,23 % | 249 | cerró |

**Con esta configuración el tope ni siquiera llega a actuar**: el solver cierra
solo en ~17 s, muy por debajo del límite más corto. Las tres filas dan la solución
idéntica porque las tres son la misma solución óptima.

Eso no quiere decir que el tope sobre. Sirve de red de seguridad para
configuraciones más duras: subir `H`, meter 1000 vehículos o apretar `MaxR` a un
valor intermedio hace crecer el árbol de búsqueda, y ahí sí puede cortar. Cuando
corta, lo que se pierde es **precisión en el nº de RSU, no cobertura** — el peso
de una desconexión es tan alto frente al de una antena que la parte de
conectividad se resuelve mucho antes que la de recuento.

> **Matiz importante sobre lo que está *demostrado*.** Que el gap sea pequeño no
> certifica por sí solo el número de desconexiones: el modelo podría, en teoría,
> conectar un par más a cambio de desplegar muchas antenas extra, y el balance
> quedar dentro del gap. Cuánta holgura hay para eso lo decide la relación entre
> `penal_desconexion` y `Cost[r]` — ver [Los pesos del modelo](#pesos).

---


## ⚙️ Backend — Documentación Detallada

<a id="cancelar"></a>

### 📁 `backend/procesos.py` — cortar lo que esté corriendo

Las herramientas de SUMO tardan **minutos**, y los endpoints de la API son
síncronos: FastAPI los ejecuta en un hilo del *threadpool*… y **un hilo de Python
no se puede interrumpir desde fuera**. Consecuencia real, vista en consola:

```
INFO: Waiting for background tasks to complete. (CTRL+C to force quit)
INFO: Finished server process [15332]
```

Decía "Finished", pero el proceso seguía vivo **una hora después con 2,2 GB**.
Ctrl+C no servía, y pulsar "Generar escenario" otra vez dejaba dos corridas
peleándose por la CPU y la RAM.

La salida es no depender del hilo: lo que consume la máquina es el
**subproceso**, y a un subproceso **sí** se le puede matar. `procesos.py` lleva
la cuenta de los que están vivos:

- `correr(cmd, timeout, cwd, etiqueta)` sustituye a `subprocess.run` y registra
  el proceso. Se comporta igual —devuelve `CompletedProcess`, lanza
  `CalledProcessError` y `TimeoutExpired`— así que el manejo de errores existente
  no cambia.
- `cancelar_todo()` mata lo registrado y devuelve **qué** cortó, para que quede
  dicho en el log en vez de parecer magia.

`POST /api/scenario/generate` lo llama antes de empezar. Verificado con un
`netconvert` real: el hilo bloqueado se libera **al instante**.

> **En Windows hay que matar el ÁRBOL, no el proceso.** `randomTrips.py` es un
> Python que lanza `duarouter.exe` como hijo; matar solo al padre dejaba a
> `duarouter` huérfano consumiendo **5 GB**. Por eso se usa `taskkill /F /T`.

<a id="extracto"></a>

### 🗺️ Mapas sin red: el extracto local (y por qué Overpass es el respaldo)

Hasta ahora el mapa de cada área **venía de Overpass**, un servicio público y
gratuito que ejecuta consultas sobre la base de datos mundial de OSM. Toda la
maquinaria de abajo —carrera entre espejos, rondas, troceo, caché— existe para
sobrevivir a un servicio que se satura. El 25 de septiembre de 2026 se cayó del
todo: los cuatro espejos devolvieron `504` durante horas **hasta para una
manzana**, y un M1 se quedó dos horas reintentando. Además OSM cambia a diario,
así que el mapa de hoy no es el de hace tres meses: para una tesis, eso es un
problema de reproducibilidad.

**Ahora el orden es: caché → extracto local → Overpass.**

| Fuente | Cuándo | Coste |
|---|---|---|
| `.osm_cache/` | el mismo bbox ya se pidió | 0 s |
| **extracto local** (`datos/osm/*.osm.pbf`) | el bbox cae dentro de un extracto registrado | **~2 s** para un km², sin red |
| Overpass | no hay extracto que cubra el área (otro país) | 30–150 s si va bien; nada si está caído |

El extracto es el país entero tal como lo publica [Geofabrik](https://download.geofabrik.de/south-america/ecuador.html)
cada día (Ecuador: **125 MB**), descargado **una vez** y congelado con su fecha:

```powershell
.\.venv\Scripts\python.exe scn.py extracto            # baja Ecuador, comprueba el MD5, registra bbox y fecha
.\.venv\Scripts\python.exe scn.py extracto --listar   # qué extractos hay
.\.venv\Scripts\python.exe scn.py extracto --url https://download.geofabrik.de/south-america/colombia-latest.osm.pbf
```

Necesita dos binarios en `herramientas/` (ver [`herramientas/README.md`](herramientas/README.md)):
`osmconvert` recorta el rectángulo y `osmfilter` se queda con lo mismo que se
pedía a Overpass (`highway`, `building`, `type=restriction`). Cada corrida anota
en su `manifest.json` de dónde salió el mapa (`origen_osm`: archivo, **fecha
de los datos**, URL, MD5), que es lo que se cita.

**Dos detalles que conviene saber:**

* `--complete-ways` de osmconvert —la opción que devuelve enteras las vías que
  cruzan el borde— **no funciona en la build de Windows** (salida vacía con
  `.pbf` y con `.o5m`). Se compensa recortando con un **margen** de 0,003°
  (~330 m, `OSM_MARGEN_GRADOS`) y **podando después en `netconvert`** al
  rectángulo pedido con `--keep-edges.in-geo-boundary`, que conserva enteras
  las aristas que lo tocan: la misma semántica que la consulta bbox de
  Overpass. `polyconvert` poda los edificios al mismo rectángulo
  (`--prune.boundary`, en coordenadas de la red). Medido en el área de prueba:
  sin poda 557 junctions y 893 edificios; **con poda 251 junctions y 281
  edificios**, frente a **258 y 281** de Overpass con datos de una semana
  antes. La poda solo se aplica
  a mapas del extracto, para no alterar las corridas basadas en Overpass ni la
  reproducción del artículo.
* Desde la web, dibujar a mano el mismo rectángulo nunca coincide al
  micrómetro con la caché: con el extracto ya no importa, porque recortar es
  casi gratis.

### ⏹️ Ctrl+C para la API de verdad

Los endpoints son síncronos y corren en hilos de anyio, que **no son daemon**.
Al recibir Ctrl+C, uvicorn deja de aceptar conexiones y espera a que terminen
las peticiones en curso; si una está bloqueada en una descarga o en
`netconvert`, el hilo no vuelve y el proceso se queda vivo con *"Waiting for
background tasks"* —visto en consola, más de una vez, y una de ellas durante dos
horas—.

Ahora, al arrancar, la API envuelve los manejadores de señal de uvicorn
(`api/main.py: _ctrl_c_que_pare`): antes de cederle la señal **mata los
subprocesos registrados** (`procesos.cancelar_todo`) y **aborta las descargas**
(`descargar_osm.abortar`, un contador de generación que cada espera de la
descarga comprueba cada segundo). Las peticiones bloqueadas fallan en ~1 s y el
cierre termina. Medido con una petición colgada en Overpass: **uvicorn terminó
en 0,5 s**. Lo mismo hace *Generar escenario*: un escenario nuevo corta la
descarga y los subprocesos del anterior.

`--timeout-graceful-shutdown 5` en la línea de arranque (ya en `dev.ps1`) es
la red de seguridad: si algo se resiste, uvicorn cancela a los 5 s.

### 📁 `backend/descargar_osm.py`

Este módulo gestiona la comunicación con la API REST de OpenStreetMap para descargar los datos geográficos crudos.

**Librerías utilizadas:** `os`, `requests`

#### `validar_coordenadas(min_lon, min_lat, max_lon, max_lat) → (bool, str)`

Valida que las coordenadas del Bounding Box estén dentro de rangos geográficos reales antes de enviar la solicitud a la API.

**Validaciones implementadas:**
1. **Rango de longitud:** Verifica que ambas longitudes estén en `[-180°, 180°]`
2. **Rango de latitud:** Verifica que ambas latitudes estén en `[-90°, 90°]`
3. **Orden lógico:** Verifica que `min < max` para ambos ejes
4. **Tamaño del área:** Calcula `(max_lon - min_lon) × (max_lat - min_lat)` y rechaza áreas mayores a `MAX_AREA_DEG2` (**1.5°²**). No es un límite de Overpass sino un tope de sensatez: por encima de eso el `.net.xml` supera el medio GB y la optimización deja de ser tratable.

**Parámetros:**
- `min_lon` (float): Longitud mínima del Bounding Box
- `min_lat` (float): Latitud mínima del Bounding Box
- `max_lon` (float): Longitud máxima del Bounding Box
- `max_lat` (float): Latitud máxima del Bounding Box

**Retorna:** Tupla `(True, "")` si es válido, o `(False, "mensaje de error descriptivo")` si no lo es.

---

#### `descargar_mapa_osm(min_lon, min_lat, max_lon, max_lat, output_dir) → (str|None, str|None)`

Descarga los archivos `.osm` del área usando la **Overpass API**, con una
estrategia pensada para que funcionen áreas del tamaño de una ciudad.

**1. Pide solo lo que el proyecto usa.** Antes la consulta traía *todo* el
contenido del rectángulo (`node`/`way`/`relation` sin filtro): árboles,
comercios, límites administrativos, ríos… que SUMO descartaba igualmente. Ahora
pide únicamente:

| Etiqueta | Para qué |
|---|---|
| `way["highway"]` | la red vial que consume `netconvert` |
| `way["building"]` + `relation["building"]` | los obstáculos de la línea de vista (`polyconvert`) |
| `relation["type"="restriction"]` | giros prohibidos: mejoran la red y pesan casi nada |

**2. Separa calles y edificios en dos descargas, y las lanza EN PARALELO.**
Medido sobre el área Quito–Sangolquí (0,34° × 0,20°): las calles solas son
**61 MB y bajan en 8 s**, mientras que pedir los edificios de golpe devuelve
**504**. Los edificios son la parte pesada, y separarlos evita que arrastren a
las calles.

Son dos consultas independientes, así que van en un `ThreadPoolExecutor` de dos
hilos en vez de una detrás de otra. Medido sobre un área de Quito: **114 s las
calles y 37 s los edificios, 151 s en serie**; en paralelo el coste es el de la
más lenta. No se paraleliza más porque Overpass admite dos peticiones
simultáneas por IP y pasarse provoca `429`.

**2 pre. Antes de todo esto, mira si hay un extracto local** (ver
[Mapas sin red](#extracto)): si lo hay, recorta de él y no toca Overpass.

**2 bis. Cachea lo descargado, indexado por bbox.** Overpass era el **74 % del
tiempo de M1** y devuelve lo mismo cada vez para un área dada. Repetir el mismo
escenario cambiando vehículos o duración —lo que se hace constantemente al
calibrar— ya no descarga nada: los `.osm` se copian de `.osm_cache/`. Verificado
sobre un área real del centro de Quito, con los ficheros comparados por SHA-256:

| | tiempo | resultado |
|---|---|---|
| 1ª vez (descarga real, en paralelo) | 52,4 s | `map.osm` + `map_edificios.osm` |
| 2ª vez, mismo bbox | **0,0 s** | **bytes idénticos** |

La clave es el bbox redondeado a 1e-6° (~0,1 m), así que dos clics iguales dan
la misma entrada y un rectángulo distinto se descarga igual que siempre. El
`meta.json` se escribe **al final**: si el proceso muere a medias, la entrada
queda sin meta y se ignora en vez de servir datos incompletos. Se controla con
`OSM_CACHE_DIAS` (30 por defecto; **0 la desactiva**) y `OSM_CACHE_DIR`.

**3. Trocea los edificios de forma recursiva.** Si un cuadrante falla, se parte
en cuatro y se reintenta cada uno (hasta 3 niveles = 64 trozos). El troceado se
adapta a la densidad: el campo baja de una vez y solo el núcleo urbano se
subdivide.

**4. Corre una carrera entre instancias de Overpass.** Las públicas se saturan a
menudo y de forma **transitoria**: medido, la misma consulta que devolvió 504 en
los cuatro servidores funcionó sin problema medio minuto después.

Antes se recorrían **en un orden fijo**, escrito a mano tras una medición. Ese
orden caduca: días después, los dos primeros de la lista estaban caídos y el
tercero respondía en 22 s. Ahora la misma consulta se manda a `OVERPASS_CARRERA`
instancias **a la vez** y se usa **la primera que conteste con datos**; las demás
se abandonan (corren en hilos `daemon`, así que no retrasan nada). Si el grupo
entero falla, se pasa al siguiente, y todo se repite `OVERPASS_REINTENTOS` rondas.

Se limita a **2 en carrera** a propósito: son servidores públicos y gratuitos, y
mandar la misma consulta pesada a los cuatro sería abusar.

**El otro cambio es el tiempo de espera.** Estaba en 300 s por servidor, y
medido, **todas** las peticiones que funcionan tardan entre **23 y 41 s** — ninguna
se acerca a 300. Bajarlo a **120 s** deja un margen de 3× sobre la más lenta que
triunfó y abandona a un servidor colgado en la quinta parte de tiempo.

Las dos cosas juntas, sobre la misma área del centro de Quito:

| | Descarga |
|---|---|
| Orden fijo, timeout 300 s | 52,4 s |
| **Carrera de 2, timeout 120 s** | **6,8 s** (7,7×) |

Y el peor caso —cuando de verdad no hay nada que hacer— baja de **60,7 minutos**
colgado (4 servidores × 300 s × 3 rondas) a **12,7**.

Además, toda descarga tiene un **presupuesto total** (`OVERPASS_PRESUPUESTO_S`,
15 min): al agotarse paran las rondas y el troceo de edificios, que antes
podía multiplicar los reintentos (4 → 16 → 64 cuadrantes) durante horas con los
servidores caídos. Y **cada intento se escribe en la consola** del backend
(`[overpass] mail.ru: 504 (45 s)`, `ronda 2/3 en 20 s`…): antes esperaba en
silencio y la interfaz solo mostraba el reloj de arena.

> **Lo que NO funciona: trocear el área.** Se probó, porque parece lo natural, y
> los datos lo desmienten: el coste de Overpass es **por petición, no por
> tamaño**. Peticiones de 0,0028°² y de 0,0051°² tardan lo mismo (23–41 s), y
> hasta un trozo diminuto —el 2 % del lado— tarda 22 s. Esos segundos son **cola
> de espera**, no cálculo. Así que más trozos = más colas: 9 trozos secuenciales
> tardaron 300 s y 16 trozos, 476 s. En paralelo es aún peor, porque dispara
> `429` (límite de ritmo) y `504`. El troceado recursivo que queda en el código
> se usa **solo como reacción a un fallo**, no de entrada.

> ⚠️ **No añadir instancias regionales.** `overpass.osm.ch` solo tiene datos de
> Suiza: responde `200` con un documento vacío, que parece éxito y no lo es. Por
> eso se comprueba que la respuesta contenga vías antes de aceptarla.

**Retorna:** `(rutas, None)` en éxito, donde `rutas` es una **cadena con varios
archivos separados por comas** (`map.osm,map_edificios.osm,…`), que es
exactamente el formato que aceptan `netconvert` y `polyconvert` en `--osm-files`.
No se fusionan los XML: las herramientas de SUMO ya admiten listas.

Si se descargan las calles pero **ningún** edificio, la función **falla a
propósito**: sin obstáculos, la línea de vista daría conectividad perfecta en
todas partes — un resultado falso que parecería correcto.

---

### 📁 `backend/sumo_pipeline.py`

Este módulo automatiza la ejecución secuencial de las tres herramientas CLI de SUMO como subprocesos del sistema.

**Librerías utilizadas:** `os`, `sys`, `subprocess`

#### `_buscar_random_trips() → str`

Función privada que localiza el script `randomTrips.py` en el sistema.

**Estrategia de búsqueda:**
1. Lee la variable de entorno `SUMO_HOME`
2. Si existe, construye la ruta `SUMO_HOME/tools/randomTrips.py`
3. Verifica con `os.path.isfile()` que el archivo exista
4. Si no se encuentra, retorna `"randomTrips.py"` como fallback (asume que está en PATH)

---

#### `ejecutar_pipeline_sumo(osm_path, output_dir) → list[dict]`

Ejecuta los tres pasos del pipeline SUMO de forma secuencial. Si un paso falla, los siguientes **no se ejecutan** (fail-fast).

<a id="vclass"></a>

**Filtrado de la red por tipo de vía: probado y DESACTIVADO.**

La consulta a Overpass pide `highway=*`, y en OSM eso incluye **aceras, sendas
peatonales, escaleras y ciclovías**, por las que ningún coche circula. Filtrarlas
aligera las cuatro etapas… pero **cambia el escenario**: las junctions de la red
son las candidatas a RSU, así que quitar vías quita candidatas.

Medido sobre un área de Quito (`map.osm` de 56 MB):

| | Red | Junctions (candidatas) | `service` | `residential` |
|---|---|---|---|---|
| **sin filtro (por defecto)** | **520,0 MB** | **92 993** | **33 934** | **126 994** |
| `remove pedestrian,bicycle` | 458,9 MB | 77 963 (−16 %) | 30 973 | 115 067 |
| `keep passenger` | 366,8 MB | 55 354 (−40 %) | **0** | 105 713 |

> ⚠️ **`--keep-edges.by-vclass passenger` es una trampa.** SUMO asigna por
> defecto a `highway.service` un `vclass` que **no incluye `passenger`**, así que
> borra **33 934 aristas** de callejones, accesos y vías de parking —calles por
> las que los coches sí circulan— y con ellas el **40 % de las candidatas a RSU**.
> Se llegó a activar y hubo que revertirlo. No usarlo.

`--remove-edges.by-vclass pedestrian,bicycle` sí es correcto —quita solo lo que
admite **únicamente** peatones o bicis, dejando en cero `footway`, `steps`,
`cycleway` y `path`— pero aun así recorta un 16 % de las junctions a cambio de
un ahorro modesto (12 % de la red). **Ante la duda, red completa**: que el
escenario sea fiel importa más que ahorrar unos segundos.

Queda disponible por si se quiere medir el compromiso:

```powershell
$env:SUMO_FILTRO_VIAS = "pedestrian,bicycle"   # vacío o sin definir = sin filtro
```

> **Los edificios no dependen de esto.** `polyconvert` los saca de
> `map_edificios.osm` —una descarga aparte— y solo usa la red para proyectar
> coordenadas. Comprobado: los `.poly.xml` generados con una red y con la otra
> tienen los **mismos 132 678 polígonos**, y las únicas 3 líneas distintas son la
> marca de tiempo y los nombres de archivo del encabezado.

**Paso 1 — netconvert:**

```bash
netconvert --ramps.guess --remove-edges.isolated --edges.join --geometry.remove \
           --osm-files output/map.osm -o output/mapa.net.xml
```

- `--ramps.guess`: Detecta automáticamente rampas de acceso/salida
- `--remove-edges.isolated`: Elimina segmentos viales aislados sin conexión
- `--edges.join`: Fusiona aristas adyacentes con misma geometría
- `--geometry.remove`: Simplifica la geometría eliminando nodos intermedios redundantes
- `-o`: Define el archivo de salida

**Paso 2 — polyconvert:**

```bash
polyconvert --net-file output/mapa.net.xml --osm-files output/map.osm \
            -o output/mapa.poly.xml
```

- `--net-file`: Red vial como referencia para la proyección de coordenadas
- `--osm-files`: Fuente de datos de polígonos (edificios, parques, etc.)

**Paso 3 — randomTrips:**

```bash
python randomTrips.py -n output/mapa.net.xml -r output/mapa.rou.xml \
    -e <end_time> -p <periodo_s> --seed <semilla> \
    --duarouter-routing-threads <N> --duarouter-routing-algorithm CH \
    --no-validate
```

- `-n`: Archivo de red vial de entrada
- `-r`: Archivo de rutas de salida
- `-e <end_time>`: Tiempo final de generación de vehículos. Se calcula como `end_time = num_vehiculos × periodo_salida` (en segundos), que equivale a la duración total
- `-p <periodo_s>`: Periodo de salida en **segundos** entre vehículos
- `--seed <semilla>`: **semilla del generador aleatorio** — ver [Reproducibilidad](#semilla)
- Se ejecuta con `sys.executable` para usar el mismo intérprete Python del entorno virtual
- **Parámetros configurables (UI):** `num_vehiculos` (5–1 000 000, **default 100**) y `tiempo_simulacion` en **minutos** (1–240, **default 120 min** = 2 h). El `periodo_salida` ya **no se elige a mano**: se calcula automáticamente como `tiempo_simulacion / num_vehiculos` para repartir todos los autos a lo largo de la simulación (tráfico continuo)

<a id="semilla"></a>

**Reproducibilidad: la semilla.** `randomTrips` y `sumo` usan generadores
pseudoaleatorios. Sin fijar la semilla, **dos corridas con los mismos parámetros
producen escenarios distintos**: no se puede repetir un resultado, ni comparar
dos configuraciones de filtrado sobre la misma movilidad, ni publicar un
suplemento que otra persona pueda rehacer.

La semilla se pasa **a las dos etapas** —`randomTrips --seed` y `sumo --seed`—
porque cada una tiene su propio generador: la primera decide los pares
origen-destino, la segunda las inserciones y el comportamiento de los
conductores. Se resuelve **una sola vez por escenario** y queda guardada junto a
sus parámetros.

| Dónde | Valor |
|---|---|
| Petición de la API | `semilla` (`null` = usa la de por defecto) |
| Constante | `SEMILLA_POR_DEFECTO` en `backend/sumo_pipeline.py` |
| Variable de entorno | `SUMO_SEMILLA` |
| Por defecto | **42** — la que usó la campaña del artículo V5 |

**Comprobado, no supuesto.** `pruebas/determinismo.py` verifica las tres cosas
que hacen falta, **con el paralelismo activado**:

```
  corrida                rutas              traza (FCD)
  semilla 42 (a)         85cbbd5f63e1f923   f9e467149822ac87
  semilla 42 (b)         85cbbd5f63e1f923   f9e467149822ac87
  semilla 7              afa9fb9e0574e9f2   9ada370476ceb480
  semilla 42, 1 hilo     85cbbd5f63e1f923   f9e467149822ac87

  1. misma semilla -> mismo escenario   : True
  2. otra semilla  -> otro escenario    : True
  3. los hilos no alteran el resultado  : True
```

La tercera comprobación importa especialmente: el proyecto usa `duarouter` con
varios hilos y **CH**. Queda verificado que **el paralelismo no introduce
variación** entre corridas.

> **No comparar los archivos byte a byte.** SUMO escribe en la cabecera la marca
> de tiempo de generación y un bloque `<configuration>` con las **rutas** de los
> archivos; ambas cambian entre dos corridas en carpetas distintas sin que el
> escenario sea distinto. La prueba compara el **contenido** (los `<vehicle>` del
> `.rou.xml` y los `<timestep>` del FCD), descartando esa cabecera.

```bash
python pruebas/determinismo.py                    # usa output/map.osm
python pruebas/determinismo.py --osm otro.osm --vehiculos 500
```

<a id="paralelismo"></a>

**Las dos últimas opciones son las que evitan que M1 se eternice.** `randomTrips`
no calcula las rutas: delega en **`duarouter`**, que resuelve *un camino mínimo
por vehículo* sobre toda la red. Y `duarouter` por defecto va **monohilo y con
dijkstra**. Medido sobre un escenario real de 50 000 vehículos y una red de
379 MB: **101 % de CPU —un solo núcleo de 16— durante más de una hora**.

`randomTrips` reenvía a `duarouter` cualquier opción con el prefijo
`--duarouter-` (mecanismo `allowed_programs` de `sumolib`), así que se le pasan
dos cosas distintas:

| Opción | Qué cambia |
|---|---|
| `--routing-threads N` | Reparte las consultas de ruta entre N hilos |
| `--routing-algorithm CH` | Jerarquías de contracción: **preprocesa la red una vez** y luego cada camino mínimo sale casi gratis |
| `--no-validate` | Quita la **segunda pasada completa** de `duarouter` (ver abajo) |

> **CH no cambia ni un resultado.** Igual que A\*, es un algoritmo **exacto**:
> devuelve los mismos caminos mínimos que dijkstra, solo que precalculando.
> Comprobado: A\* y CH escribieron **exactamente las mismas 9 884 rutas**.

**A\* frente a CH**, sobre una red real de 442 MB con 16 hilos:

| Viajes | `astar` | `CH` | |
|---|---|---|---|
| 500 | 93,5 s | 90,0 s | 1,04× |
| 2 000 | 115,8 s | 98,3 s | 1,18× |
| 10 000 | 198,1 s | **101,4 s** | **1,95×** |

Ajustando `T(n) = fijo + n · coste_por_viaje`:

| | Coste fijo | Por viaje |
|---|---|---|
| `astar` | 95,2 s | 0,0103 s |
| **`CH`** | 97,5 s | **0,00039 s** (26× más barato) |

El preproceso de CH cuesta ~2 s y a partir de ahí cada ruta es casi gratis.
Extrapolado a **50 000 viajes: 610 s → 117 s (5,2×)**. Gana en todos los
tamaños medidos, así que —a diferencia de los hilos— no necesita umbral. Los
~95 s fijos son **cargar la red**, no el algoritmo.

**La segunda pasada de `duarouter`.** `randomTrips` trae `validate=True` por
defecto, y eso ejecuta `duarouter` **dos veces** sobre los mismos viajes: una
para producir las rutas y otra con `--write-trips` para comprobar cuáles son
válidas. Confirmado viendo ambos procesos vivos a la vez. En una corrida real
de 50 000 vehículos esa segunda pasada costó **~800 s** y **no cambió el
resultado**: el rutado va antes que la validación, así que el `.rou.xml` ya
estaba escrito. Se desactiva con `--no-validate`; a cambio salen algunos
vehículos menos de los pedidos (los irrutables), y el pipeline **reporta el
número real** en vez de repetir el pedido.

> ⚠️ **Cuidado con `--` en las rutas de archivo.** `randomTrips` escribe la
> línea de comandos dentro de un **comentario XML**, y XML prohíbe `--` ahí.
> Si alguna ruta lleva doble guion, el `trips.trips.xml` sale inválido y
> `duarouter` falla con `'--' sequence is illegal in comment` —devolviendo
> `rc=0` y un archivo vacío, que parece éxito—. Costó varias mediciones dadas
> por buenas antes de descubrirlo.

**Medido sobre la red real del escenario** (`mapa.net.xml` de 397 MB, 2 000
vehículos en 180 min, máquina de 16 núcleos), comprobando que ambas
configuraciones escriben las **2 000 rutas**:

| | Tiempo | Rutas escritas |
|---|---|---|
| `dijkstra`, 1 hilo (antes) | 540,2 s | 2 000 / 2 000 |
| **`astar`, 16 hilos (ahora)** | **352,1 s** | 2 000 / 2 000 |
| | **1,53×** | |

**Repartir tiene un coste fijo**, y no es pequeño: cada hilo monta su propia
estructura de rutado sobre la red entera. Ajustando `T(n) = fijo + n · coste_por_viaje`
con dos puntos medidos (n = 200 y n = 2 000):

| | Coste fijo | Por viaje |
|---|---|---|
| `dijkstra`, 1 hilo | 125 s | 0,2074 s |
| `astar`, 16 hilos | **220 s** | **0,0659 s** |

Los 16 hilos cuestan **95 s extra de arranque** pero rutan **3,15× más rápido
por viaje**. El punto de equilibrio está en `95 / (0,2074 − 0,0659) ≈ 670
viajes`, y se comprobó midiendo: **con 200 vehículos paralelizar sale peor**
(166,8 s → 233,5 s). Extrapolado a 50 000 vehículos, en cambio: **175 min →
59 min (3,0×)**.

Por eso `_hilos()` recibe el número de viajes y devuelve **1 por debajo de
`UMBRAL_HILOS`** (700 por defecto, configurable con `SUMO_UMBRAL_HILOS`). El
umbral no es un número redondo elegido a ojo: es el corte de esas dos rectas. A*
se deja siempre, porque explora menos arcos también con un solo hilo.

> ⚠️ **La memoria sí escala con los hilos.** Cada hilo mantiene su propio estado
> de rutado sobre la red: medido, `duarouter` pasó de ~1 GB con 1 hilo a
> **6,8 GB con 16** sobre esta red de 397 MB. En una máquina con poca RAM hay
> que bajar `SUMO_HILOS`.

**M2 no se paraleliza.** Se probó `sumo --threads N` y no reparte el bucle de
la simulación: medido con 50 000 vehículos, el hilo principal consumió
25 480 s de CPU y los 16 auxiliares **22 s cada uno**. Se quitó la opción. El
tiempo de M2 con decenas de miles de vehículos es el de un núcleo, y la única
palanca real es el tamaño del escenario (o pasar a la simulación mesoscópica
de SUMO, `--mesosim`, que es una decisión de método).

> ⚠️ **Lo que sí mata a M2 es la memoria.** `sumo` con 50 000 vehículos sobre
> la red de Quito llegó a **3,3 GB**. Con 0,9 GB libres —VS Code, navegador y
> demás ocupaban 12 GB de 13,7— Windows lo paginó a disco y estuvo **8 horas
> sin avanzar 600 s simulados** (working set de 7 MB, 100 % de CPU: pura
> paginación). Por eso M2 **avisa antes de lanzar** cuánto necesita
> (66 KB por vehículo, medido) y cuánto hay libre. No se recorta nada; si el
> aviso sale, cierra programas o reduce los vehículos.

El número de hilos de `duarouter` sale de `_hilos()` en
[`sumo_pipeline.py`](backend/sumo_pipeline.py): usa **todos los núcleos** salvo
que se fije `SUMO_HILOS`.

**Ejecución con `subprocess.run()`:**
- `check=True`: Lanza `CalledProcessError` si el código de retorno no es 0
- `capture_output=True`: Captura stdout y stderr para diagnóstico
- `text=True`: Decodifica la salida como texto (no bytes)
- `timeout`: Red de seguridad para que la petición HTTP no se cuelgue si una herramienta se atasca. Lo fija `_timeout()` a partir de `SUMO_TIMEOUT_S`; **por defecto no hay límite** (`TIMEOUT_POR_DEFECTO = 0.0`), porque con una ciudad entera cualquier tope fijo se queda corto y corta corridas legítimas

**Manejo de excepciones por paso:**
- `FileNotFoundError`: El ejecutable no está en el PATH
- `CalledProcessError`: El comando retornó un código de error (se muestra `stderr[:500]`)
- `TimeoutExpired`: El proceso excedió `SUMO_TIMEOUT_S`, si se definió

**Retorna:** Lista de diccionarios `[{"paso": str, "exito": bool, "mensaje": str}, ...]`

---

### 📁 `backend/parsear_xml.py`

Este módulo implementa el proceso **ETL (Extract-Transform-Load)** que convierte los archivos XML de SUMO en datos JSON limpios y manejables.

**Librerías utilizadas:** `os`, `json`, `xml.etree.ElementTree`

#### `parsear_junctions(net_xml_path, output_dir) → (dict|None, str|None)`

Extrae las intersecciones viales útiles del archivo `mapa.net.xml`.

**Proceso ETL:**
1. **Extract:** Parsea el XML con `ET.parse()` y busca todos los elementos `<junction>` con `root.findall("junction")`
2. **Transform:** Filtra las junctions por tipo, excluyendo:
   - `type="internal"` (junctions internas de SUMO, no representan intersecciones reales)
   - `type="dead_end"` (callejones sin salida, no útiles para simulación VANET)
3. **Load:** Extrae los atributos `id`, `x`, `y` de cada junction válida y los guarda como JSON

**Estructura del JSON de salida (`junctions_limpias.json`):**
```json
{
    "267037289": {
        "x": 128.6,
        "y": 206.25
    },
    "268160930": {
        "x": 348.37,
        "y": 212.89
    }
}
```

> **Nota:** Las coordenadas `x`, `y` están en el **sistema proyectado de SUMO** (metros UTM con offset), no en lat/lon. Para visualizarlas en un mapa se necesita la función `convertir_xy_a_lonlat()`.

> ⚡ **Lectura en streaming.** El recorrido usa `_iter_elementos()`, un envoltorio
> sobre `ET.iterparse()` que va descartando cada elemento tras leerlo. Con
> `ET.parse()` el árbol completo del `.net.xml` de una ciudad (565 MB medidos en
> Quito) ocupa varios GB de objetos Python. Ahora la memoria es constante sea cual
> sea el tamaño del archivo.

---

#### `parsear_edificios(poly_xml_path, output_dir) → (dict|None, str|None)`

Extrae los polígonos de edificios del archivo `mapa.poly.xml`.

**Proceso ETL:**
1. **Extract:** Busca todos los elementos `<poly>` en el XML
2. **Transform:**
   - Filtra solo los polígonos cuyo `type` contiene la palabra `"building"` (case insensitive)
   - Convierte el atributo `shape` del formato string `"x1,y1 x2,y2 x3,y3"` a una lista de pares `[[x1, y1], [x2, y2], [x3, y3]]`
   - Descarta polígonos con menos de 3 vértices (no forman un polígono válido)
3. **Load:** Guarda el resultado en `edificios_limpios.json`

**Estructura del JSON de salida (`edificios_limpios.json`):**
```json
{
    "425185241": [
        [145.169137, 237.09657],
        [137.103598, 227.306636],
        [131.123261, 232.164513],
        [139.1888, 241.954447],
        [145.169137, 237.09657]
    ]
}
```

---

#### `obtener_proyeccion(net_xml_path) → dict|None`

Lee los parámetros de proyección cartográfica del elemento `<location>` dentro de `mapa.net.xml`.

**¿Por qué es necesario?**

SUMO usa internamente una proyección UTM (Universal Transverse Mercator) para convertir coordenadas geográficas (lon, lat en grados) a un sistema plano (x, y en metros). El elemento `<location>` almacena los boundaries necesarios para revertir esta conversión.

**Datos que extrae del XML:**
```xml
<location netOffset="-777496.49,23956.17"
          convBoundary="0.00,0.00,348.37,271.52"
          origBoundary="-78.506984,-0.216532,-78.503856,-0.214078"
          projParameter="+proj=utm +zone=17 +ellps=WGS84 +datum=WGS84 +units=m +no_defs"/>
```

- **`convBoundary`** → `[x_min, y_min, x_max, y_max]` — Límites en coordenadas SUMO (metros)
- **`origBoundary`** → `[lon_min, lat_min, lon_max, lat_max]` — Límites en coordenadas geográficas originales

**Retorna:** `{"orig": [4 floats], "conv": [4 floats]}` o `None` si hubo error.

> ⚡ **Se corta en cuanto encuentra `<location>`.** Ese elemento está en las
> primeras líneas del `.net.xml`, pero antes se parseaba el archivo **entero**
> para leer sus cuatro atributos: **17,3 s** con la red de Quito. Con `iterparse`
> y un `break`, **0,0 s**.

---

#### `convertir_xy_a_lonlat(x, y, proy) → (lat, lon)`

Convierte una coordenada SUMO `(x, y)` en metros a coordenadas geográficas `(lat, lon)` en grados decimales.

**Método: proyección real de SUMO (UTM vía `pyproj`)**

SUMO genera sus coordenadas con `xy_sumo = proj(lon,lat) + netOffset`, donde `proj`
es la proyección (UTM) indicada en el `.net.xml` (`projParameter`). La inversa es exacta:

```
lon, lat = proj⁻¹(x − netOffset_x, y − netOffset_y)      # con pyproj
```

`obtener_proyeccion()` lee `projParameter` y `netOffset` del `.net.xml`, y
`convertir_xy_a_lonlat()` reconstruye el lat/lon exacto (transformador `pyproj`
cacheado). Si faltara `pyproj`, cae a una interpolación lineal entre `convBoundary`
y `origBoundary` (aproximada). **Por qué importa:** `netconvert` recorta la red, así
que `convBoundary ≠ origBoundary` y la interpolación lineal desplazaba edificios/RSU
~178 m; la proyección real lo corrige.

**Ejemplo real:**
- Entrada: `x=128.6, y=206.25` (coordenadas SUMO)
- Salida: `lat=-0.214668, lon=-78.505829` (coordenadas geográficas en Quito, Ecuador)

---

## 📡 Filtrado Inteligente para RSU Placement

Esta sección documenta el sistema de filtrado que reduce las junctions (intersecciones) crudas de SUMO a un conjunto optimizado de **puntos candidatos para la colocación de RSU (Road Side Units)** en redes vehiculares.

### ¿Por qué es necesario el filtrado?

Cuando SUMO procesa un archivo OSM con `netconvert`, genera un gran número de junctions que incluyen:

- **Nodos intermedios** dentro de una misma calle (puntos donde la geometría cambia de dirección)
- **Bifurcaciones menores** de senderos peatonales o ciclovías
- **Dead ends** (callejones sin salida, ya excluidos en el parseo inicial)
- **Junctions internas** de SUMO (ya excluidas en el parseo inicial)

Para la colocación de RSU en VANETs, solo interesa un subconjunto específico: **las intersecciones reales donde múltiples calles vehiculares se cruzan**, ya que es en esos puntos donde los vehículos se detienen, cambian de dirección y necesitan comunicación V2I (Vehicle-to-Infrastructure).

**Ejemplo real:** Para la zona del Centro Histórico de Quito incluida en `output/`, SUMO generó **1211 junctions** tras el parseo inicial. Con la configuración de referencia (grado mínimo **4**, radio **20 m**), el filtrado RSU las redujo a **278 candidatos** (reducción del **77%**) conservando solo las intersecciones significativas.

---

### Dataset de entrada: `mapa.net.xml`

El filtrado RSU opera sobre **dos fuentes de datos** del mismo archivo XML generado por SUMO:

#### 1. Datos de junctions (ya parseados en el paso previo)

Del JSON `junctions_limpias.json`, que contiene las junctions con `type ≠ internal` y `type ≠ dead_end`:

```json
{
    "267037289": { "x": 128.6, "y": 206.25 },
    "268160930": { "x": 348.37, "y": 212.89 }
}
```

#### 2. Datos de aristas (edges) del `mapa.net.xml`

Para calcular el grado de cada junction, se leen los elementos `<edge>` del archivo `mapa.net.xml`. Cada edge tiene atributos `from` y `to` que referencian IDs de junctions:

```xml
<!-- Edge vehicular (se cuenta para el grado) -->
<edge id="24559989#0" from="4995666329" to="9727960118" priority="3" type="highway.residential">
    <lane id="24559989#0_0" speed="13.89" length="37.57" .../>
</edge>

<!-- Edge interna (se IGNORA en el cálculo de grado) -->
<edge id=":267037289_0" function="internal">
    <lane id=":267037289_0_0" speed="7.09" length="3.05" .../>
</edge>
```

Las edges con `function="internal"` son aristas que SUMO crea **dentro** de las intersecciones para modelar los movimientos de giro. Estas se ignoran en el cálculo de grado porque no representan calles reales.

---

### Algoritmo de filtrado: dos etapas

El filtrado se implementa en la función `filtrar_junctions_rsu()` y consta de dos etapas secuenciales:

#### Etapa 1: Filtrado por grado de conectividad

**¿Qué es el grado?** El grado de una junction es el número de **vecinos únicos** que tiene en el grafo **no dirigido** de la red. Las aristas dirigidas y paralelas de SUMO (una calle bidireccional genera 2 edges, uno por sentido) se reducen a un par no ordenado `{from, to}`, de modo que dos junctions vecinas cuentan **una sola vez**. Así el grado equivale al número de calles distintas que confluyen en la intersección:

| Grado | Significado real | ¿Se conserva? (default min_grado=4) |
|-------|-----------------|--------------------------------------|
| **1** | Final de una calle de un solo sentido | ❌ No — nodo terminal |
| **2** | Nodo intermedio en una calle bidireccional, o punto donde pasa una única calle | ❌ No — no es intersección |
| **3** | Intersección T de una calle bidireccional + una de un solo sentido | ❌ No (con default=4) |
| **4** | Cruce de 2 calles bidireccionales en cruz (+) o T | ✅ Sí — intersección estándar |
| **5** | Cruce de 2 calles bidireccionales + 1 de un solo sentido | ✅ Sí — intersección compleja |
| **6** | Cruce de 3 calles bidireccionales (intersección en Y/estrella) | ✅ Sí — intersección principal |
| **7-8** | Rotondas o intersecciones de muchas vías | ✅ Sí — nodo crítico |

**Implementación** (`calcular_grado_junctions()`):

```python
vecinos = {}
for edge in _iter_elementos(net_xml_path, "edge"):   # streaming, no ET.parse
    if edge.get("function") == "internal":
        continue  # Ignorar edges internas de SUMO
    a, b = edge.get("from"), edge.get("to")
    if not a or not b or a == b:
        continue  # descartar aristas incompletas o lazos
    vecinos.setdefault(a, set()).add(b)   # pares no ordenados
    vecinos.setdefault(b, set()).add(a)
grados = {j: len(vs) for j, vs in vecinos.items()}  # nº de vecinos únicos
```

> ⚡ **El resultado se cachea.** Los grados dependen solo de la red, no de los
> parámetros del filtro, pero antes se recalculaban en **cada** clic de *Filtrar
> RSU*: **18,6 s por clic** con la red de Quito. Ahora se guardan con clave
> `(ruta, tamaño, fecha)`, así que probar varias combinaciones de grado y radio
> es instantáneo, y la caché se invalida sola al regenerar el escenario.
> Medido: `grado=4, radio=20` seguido de `grado=5, radio=50` pasó de
> **66 s + 66 s** a **66 s + 0,0 s**.

Se recorre cada `<edge>` no interna, se descartan lazos, y cada extremo se agrega al conjunto de vecinos del otro; el grado final es el **número de vecinos únicos**. De este modo una calle bidireccional (2 edges) cuenta como **un solo vecino**, alineando el grado con la tabla de arriba (grado 4 = cruce de 2 calles = 4 vecinos). El `clustering` greedy ordena por grado descendente y, ante empate, por id de junction ascendente, para que corridas repetidas den el **mismo** conjunto de RSU (resultado determinista).

#### Etapa 2: Clustering espacial greedy

Después del filtrado por grado, pueden quedar **junctions muy cercanas entre sí** que en la realidad representan la misma intersección física (SUMO a veces genera múltiples nodos para una sola intersección).

El algoritmo agrupa las junctions que están a menos de `radio_cluster` metros y conserva solo la de **mayor grado** como representante del grupo:

```
Algoritmo Greedy de Clustering:

1. Ordenar candidatos por grado DESCENDENTE
2. Para cada junction (de mayor a menor grado):
   a. Calcular distancia euclidiana a todos los centros existentes
   b. Si la distancia mínima es > radio_cluster:
      → Esta junction se convierte en un nuevo CENTRO
   c. Si la distancia mínima es ≤ radio_cluster:
      → Se DESCARTA (ya hay un centro cercano con mayor grado)
```

**¿Por qué greedy y no K-means?** Porque el algoritmo greedy garantiza que la junction con mayor grado siempre sea la representante del cluster, lo cual es preferible para RSU placement (colocar el RSU en la intersección más conectada de cada zona).

**Fórmula de distancia** (euclidiana en coordenadas SUMO, que ya están en metros):

```
distancia = √((x₁ - x₂)² + (y₁ - y₂)²)
```

Dado que las coordenadas SUMO están en metros UTM, la distancia euclidiana es directamente la distancia real en metros.

---

### Parámetros configurables (UI)

La interfaz incluye controles para diferenciar entre el **preprocesamiento espacial** (cuántos RSU poner) y la **visualización de alcance** (hasta dónde llegan). Es fundamental entender la diferencia:

#### 1. Radio de Agrupación (Clustering) — `radio_cluster`
- **Propósito:** Eliminar puntos redundantes durante el preprocesamiento.
- **Qué hace:** Si varias intersecciones generadas por SUMO están a menos de esta distancia (ej. a 5m por ser múltiples carriles del mismo cruce), las agrupa conservando solo la de mayor grado. Esto **reduce la cantidad real de RSU**.
- **Escala típica:** 10–50 metros. (Invisible en el mapa, afecta el conteo total).

#### 2. Radio de Cobertura RSU — `radio_cobertura` (Checkbox)
- **Propósito:** Visualizar el alcance de comunicación inalámbrica (tecnologías DSRC/802.11p o C-V2X).
- **Qué hace:** Dibuja un círculo verde semi-transparente alrededor de cada candidato a RSU. Sirve para evaluar visualmente si hay "puntos ciegos" (zonas de la ciudad sin cobertura). Es de **solo visualización**, no elimina puntos.
- **Escala típica:** 150–300 metros. (Visible en el mapa como áreas verdes).

Estos parámetros se controlan desde el **panel de parámetros del frontend** (sección
*"RSU candidatas"*) y viajan al backend en la petición `POST /api/rsu/filter`:

| Parámetro | Control UI | Default | Rango | Función |
|-----------|-----------|---------|-------|---------|
| `min_grado` | Slider: 🔗 Grado mínimo | **4** | 2 – 8 | Filtro topológico |
| `radio_cluster` | Slider: 📏 Radio de agrupación | **20m** | 0 – 100m | Filtro espacial |
| `mostrar_cobertura` | Checkbox: 📶 Mostrar radio | **Falso** | On / Off | Visualización |
| `radio_cobertura` | Slider: 📡 Radio de cobertura | **200m** | 50 – 500m | Alcance visual |

**¿Dónde cambiar los defaults?**

Los valores por defecto de los *sliders* viven en el frontend, en la constante
`DEF` de [`web/src/App.tsx`](web/src/App.tsx) (`min_grado`, `radio_cluster`, …), y
los **rangos/validación** en los *schemas* de la API (`RsuReq`, etc.) en
[`api/main.py`](api/main.py). El backend recibe estos parámetros vía
`POST /api/rsu/filter`.

Si se desea **llamar al filtrado directamente desde código** (sin UI ni API):

```python
from backend.parsear_xml import filtrar_junctions_rsu
import json

# Cargar junctions
junctions = json.load(open("output/junctions_limpias.json"))

# Aplicar filtrado con parámetros personalizados
rsu_candidatos = filtrar_junctions_rsu(
    junctions,
    net_xml_path="output/mapa.net.xml",
    min_grado=6,        # Solo intersecciones de 3+ calles
    radio_cluster=30.0  # 30 metros de separación mínima
)

print(f"Originales: {len(junctions)} → RSU: {len(rsu_candidatos)}")
```

---

### Visualización en el mapa

Los RSU candidatos se renderizan en el mapa de resultados con estilo diferenciado:

| Elemento | Estilo | Color | Radio | Info en tooltip |
|----------|--------|-------|-------|-----------------|
| **RSU Candidato** | CircleMarker sólido | Rojo `#ef4444` / `#f87171` | 9px | ID, grado, lat, lon |
| **Edificio** | Polygon relleno | Naranja `#f97316` / `#fb923c` | — | ID, nº vértices |

La leyenda sobre el mapa muestra en tiempo real:
- Número de junctions originales
- Número de RSU candidatos resultantes
- Porcentaje de reducción

Los controles `LayerControl` permiten activar/desactivar cada grupo (RSU, edificios) independientemente.

---

## 📡 Módulo 2 — Simulación V2I y Tuplas de Visibilidad

Esta sección documenta el **Módulo 2** del proyecto, que extiende el escenario generado en el Módulo 1 con una **simulación de tráfico real** ejecutada en SUMO, y genera las **tuplas de visibilidad `<t, V, RSU>`** que representan los momentos en que un vehículo tiene línea de vista directa (LoS) con un RSU.

### ¿Qué son las tuplas de visibilidad?

Una tupla `<t, V, RSU>` indica que en el instante de tiempo `t` (en segundos), el vehículo `V` tiene **comunicación directa** con el RSU `RSU`. Para que la tupla exista, deben cumplirse **dos condiciones simultáneamente**:

1. **Distancia ≤ Radio OBU**: La distancia euclidiana entre el vehículo y el RSU debe ser menor o igual al radio de cobertura del OBU del vehículo.
2. **Línea de vista directa (LoS)**: No debe haber ningún edificio que bloquee la línea recta entre el vehículo y el RSU.

Si alguna de las dos condiciones no se cumple, la tupla **no existe** (NLoS — Non Line of Sight).

---

### Radio de cobertura OBU

Las conexiones V2I se generan considerando **únicamente la cobertura del OBU (On Board Unit)** del vehículo. Es decir, un vehículo se conecta a un RSU solo si este se encuentra dentro del radio de cobertura de su OBU.

| Dispositivo | Descripción | Radio típico | Tecnología |
|-------------|-------------|--------------|------------|
| **OBU** (On Board Unit) | Dispositivo embarcado en el vehículo | 150–300m | DSRC/802.11p, C-V2X |

En la interfaz hay un slider para configurar el radio del OBU.

---

### Pipeline del Módulo 2

```
┌────────────────────┐     ┌────────────────────┐     ┌────────────────────┐
│  1. GENERAR CONFIG │     │  2. SIMULAR SUMO   │     │  3. PARSEAR FCD    │
│  mapa.sumocfg      │────▶│  sumo -c .sumocfg  │────▶│  fcd.xml → dict    │
│  (simulacion_sumo) │     │  (subprocess)      │     │  (simulacion_sumo) │
└────────────────────┘     └────────────────────┘     └────────┬───────────┘
                                                               │
┌────────────────────┐     ┌────────────────────┐     ┌────────▼───────────┐
│  8. VISUALIZAR     │     │  5. EXPORTAR JSON  │     │  4. TUPLAS V2I     │
│  Tabla + Matrices  │     │  tuplas_visib.json │◀────│  Matriz B (LoS)    │
│  + 4 Mapas V2I/V2V │     │  tuplas_v2v.json   │     │  (visibilidad)     │
└────────────────────┘     └─────────┬──────────┘     └────────────────────┘
                                     │
                           ┌─────────▼──────────┐
                           │  6. TUPLAS V2V      │
                           │  Matriz A (LoS)     │
                           │  (visibilidad)      │
                           └────────────────────┘
```

---

### 📁 `backend/simulacion_sumo.py`

Este módulo ejecuta el simulador SUMO para obtener la posición exacta de cada vehículo en cada instante de tiempo.

#### `generar_sumocfg(output_dir, tiempo_simulacion, periodo_fcd) → str`

Genera el archivo de configuración SUMO (`.sumocfg`) que le indica al simulador:
- Qué red vial usar (`mapa.net.xml`)
- Qué rutas vehiculares cargar (`mapa.rou.xml`)
- Cuánto tiempo simular (`tiempo_simulacion`, en segundos)
- Qué salida generar (FCD — Floating Car Data)
- **Cada cuánto escribir el FCD** (`periodo_fcd`, en segundos) mediante `device.fcd.period`

**Archivo generado (`mapa.sumocfg`):**

```xml
<configuration>
    <input>
        <net-file value="mapa.net.xml"/>
        <route-files value="mapa.rou.xml"/>
    </input>
    <time>
        <begin value="0"/>
        <end value="7200"/>            <!-- Duración (s). 7200 = 2 h. Configurable -->
    </time>
    <output>
        <fcd-output value="fcd.xml"/>
    </output>
    <processing>
        <device.fcd.period value="120"/> <!-- Escribe cada 120 s = 2 min. Configurable -->
    </processing>
    <report>
        <no-warnings value="true"/>
        <no-step-log value="true"/>
    </report>
</configuration>
```

> **Clave del muestreo por minutos:** `device.fcd.period` hace que SUMO registre la posición solo en `t = 0, periodo, 2·periodo, …` (alineado al reloj global). Así, con muestreo cada 2 min, el `fcd.xml` es pequeño y **todos los vehículos quedan registrados en los mismos instantes** (necesario para construir las matrices A y B).

---

#### `ejecutar_simulacion_sumo(output_dir, tiempo_simulacion, periodo_fcd) → (ruta_fcd, error)`

Ejecuta el simulador `sumo` (sin GUI) como subproceso, con `timeout=600` s (10 min) para soportar simulaciones largas (2–3 h). Usa `sumo` en lugar de `sumo-gui` porque es más rápido y compatible con ejecución headless.

El archivo FCD resultante contiene la posición de **todos los vehículos activos** en cada instante de muestreo. SUMO escribe el FCD según `device.fcd.period` (alineado al reloj global: `t = 0, periodo, 2·periodo, …`), de modo que con un muestreo de 2 minutos el archivo es pequeño y todos los autos quedan en los **mismos instantes**:

```xml
<fcd-export>
    <timestep time="5.00">
        <vehicle id="0" x="145.23" y="189.67" angle="270" speed="8.33"/>
        <vehicle id="1" x="302.11" y="156.89" angle="90" speed="12.50"/>
    </timestep>
    <timestep time="6.00">
        <vehicle id="0" x="137.56" y="189.67" angle="270" speed="7.78"/>
        <vehicle id="1" x="315.61" y="156.89" angle="90" speed="13.50"/>
        <vehicle id="2" x="421.05" y="234.12" angle="180" speed="3.00"/>
    </timestep>
</fcd-export>
```

> **Nota:** Las coordenadas `x, y` están en el sistema SUMO (metros UTM con offset), que es el **mismo sistema** que usan los edificios y los RSU. Esto elimina la necesidad de conversiones durante el cálculo de distancias y LoS.

---

#### `parsear_fcd(fcd_path, step_intervalo) → (dict_fcd, error)`

Parsea el archivo FCD y extrae un diccionario organizado por timestep:

```python
{
    0.0: [
        {"id": "0", "x": 128.6, "y": 206.25, "speed": 0.0, "angle": 90.0},
        ...
    ],
    1.0: [
        {"id": "0", "x": 130.5, "y": 206.25, "speed": 5.0, "angle": 90.0},
        {"id": "1", "x": 348.37, "y": 212.89, "speed": 3.0, "angle": 180.0},
        ...
    ],
}
```

El parámetro `step_intervalo` (en segundos; la UI lo expone en minutos) permite muestrear cada N segundos para reducir el volumen de datos. Se pasa también a SUMO como `device.fcd.period` para que el propio simulador escriba solo esas muestras.

---

### 📁 `backend/visibilidad.py`

Este módulo implementa el **algoritmo de detección de línea de vista directa (LoS)** y la **generación de tuplas de visibilidad** tanto V2I como V2V.

#### Algoritmo de Line of Sight (LoS)

Para determinar si un vehículo en `(Vx, Vy)` tiene línea de vista directa con un RSU en `(Rx, Ry)`, se traza un **segmento recto** entre ambos puntos y se verifica si algún **polígono de edificio** lo intersecta.

**Operación geométrica fundamental — Test de intersección de dos segmentos:**

Se usa el **test de orientación CCW (Counter-Clockwise)** para determinar si dos segmentos se cruzan. Dados tres puntos A, B, C, la función CCW calcula:

```
CCW(A, B, C) = (Bx - Ax) × (Cy - Ay) - (By - Ay) × (Cx - Ax)
```

- Si `CCW > 0`: A→B→C gira en sentido antihorario
- Si `CCW < 0`: A→B→C gira en sentido horario
- Si `CCW = 0`: A, B, C son colineales

Dos segmentos P1P2 y P3P4 se intersectan si y solo si:
- P1 y P2 están en **lados opuestos** de la línea P3P4 (CCW da signos distintos), Y
- P3 y P4 están en **lados opuestos** de la línea P1P2

**Verificación de LoS para un par (vehículo, RSU):**

```python
def tiene_linea_de_vista(vx, vy, rx, ry, edificios_cercanos):
    segmento_VR = [(vx, vy), (rx, ry)]
    
    for edificio in edificios_cercanos:
        # Pre-filtro: bounding box del edificio vs del segmento
        if no_se_solapan(bbox_segmento, bbox_edificio):
            continue  # Skip rápido — O(1)
        
        # Test completo: probar cada arista del polígono
        for arista in aristas(edificio):
            if segmentos_intersectan(segmento_VR, arista):
                return False  # NLoS — edificio bloquea
    
    return True  # LoS confirmado
```

#### Optimizaciones de rendimiento

Sin optimizar, el cálculo requeriría del orden de `130 vehículos × 31 instantes × 280 RSU × 3248 edificios ≈ 3.7×10⁹` tests de intersección. Las optimizaciones implementadas reducen esto drásticamente:

| Optimización | Descripción | Reducción estimada |
|----------|-----------|----------|
| **Índice espacial (grid) de RSU** | Cada vehículo solo compara contra las RSU de su celda 3×3 (celda = radio), no contra las N | de O(V·R) a ≈O(V·k) |
| **Índice espacial (grid) de vehículos** | En V2V cada vehículo solo se empareja con los de su celda 3×3 | de O(n²) a ≈O(n·k) por instante |
| **Grid de edificios por segmento** | Cada segmento V→V/V→RSU solo prueba los edificios que toca su trayecto, no los miles del mapa | ~99% de edificios eliminados por par |
| **Bounding boxes precalculados 1 sola vez** | El bbox de cada edificio se calcula una vez y se reutiliza (antes se recomputaba en cada test) | evita millones de recomputaciones |
| **Pre-filtro por distancia²** | Descartar pares fuera de radio sin calcular la raíz cuadrada | el `sqrt` solo se hace en los pares reales |

Con estas optimizaciones el motor de conectividad **escala hasta 1000 vehículos**. Medido en el equipo de referencia (Ryzen 7 7735HS), el **peor caso extremo** de 10 instantes × **1000 vehículos activos** cada uno (≈5000 edificios, ≈440 RSU) toma **≈4.5 s** en total (V2I ≈3.6 s + V2V ≈0.9 s). En tráfico real solo hay una fracción de vehículos activos por instante, así que es aún más rápido. Todas las optimizaciones son **exactas**: producen exactamente el mismo conjunto de tuplas que la versión sin optimizar (verificado por comparación de conjuntos).

> ⚠️ **Ese número corresponde a ese escenario.** El coste crece con el nº de
> edificios y de RSU candidatas, que son los dos factores que más cambian al
> ampliar el área: un área metropolitana llega a ~190 000 edificios y >12 000
> candidatas, dos órdenes de magnitud por encima del caso medido. Los índices
> espaciales evitan que sea cuadrático, pero M2 se nota. Si M2 tarda demasiado,
> el mando efectivo es el mismo que para M3: **reducir el área o filtrar más
> candidatas**.

---

#### `generar_tuplas_visibilidad(datos_fcd, rsus, edificios, radio_obu) → (tuplas, estadísticas)`

Algoritmo principal que genera la Matriz B de tuplas V2I. Las conexiones se generan considerando únicamente la cobertura del OBU:

```
Para cada timestep t en FCD:
  Para cada vehículo V activo en t:
    Para cada RSU:
      1. distancia = √((Vx - Rx)² + (Vy - Ry)²)
      2. Si distancia > radio_obu → SKIP
      3. Si distancia ≤ radio_obu:
         Si tiene_linea_de_vista(V, RSU, edificios) → AÑADIR <t, V, RSU>
```

**Solo se incluyen tuplas con LoS confirmado** (distancia OK + sin edificios bloqueando). Las condiciones NLoS no se guardan en la matriz.

**Estructura de salida (JSON):**

```json
{
    "parametros": {
        "radio_obu": 300,
        "total_tuplas": 1847,
        "total_timesteps": 100
    },
    "rsus": {
        "RSU_267037289": {"x": 128.6, "y": 206.25, "grado": 6}
    },
    "tuplas": [
        {"t": 0.0, "vehiculo": "V0", "rsu": "RSU_267037289", "distancia": 45.3},
        {"t": 1.0, "vehiculo": "V0", "rsu": "RSU_267037289", "distancia": 38.7}
    ]
}
```

---

## 🚗 Módulo V2V — Conectividad Vehículo-Vehículo

Esta sección documenta la generación de la **Matriz A** (conectividad vehículo-vehículo) y las tuplas V2V `<t, Vi, Vj>`.

### Datos de Entrada

Para cada instante de tiempo `t`, se parte de **dos tipos de tuplas**:

| Tipo | Tupla | Significado |
|------|-------|-------------|
| **Vehículo–RCU** | `(t, v_i, r_k)` | El vehículo `v_i` tiene conectividad directa con la RCU `r_k` en el instante `t` |
| **Vehículo–Vehículo** | `(t, v_i, v_j)` | El vehículo `v_i` tiene conectividad directa con el vehículo `v_j` en el instante `t` |

### Definición Matemática de la Matriz A

Sea `V = {v_1, v_2, ..., v_n}` el conjunto de vehículos activos en el instante `t`.

La **Matriz A** de conectividad vehículo-vehículo es:

```
A ∈ {0, 1}^{n×n}
```

Su entrada `(i, j)` se define como:

```
A_ij = 1,  si el vehículo v_i ve directamente al vehículo v_j
A_ij = 0,  en caso contrario
```

Inicialmente la diagonal de A puede ser cero, porque A representa enlaces físicos directos entre vehículos distintos.

### Bidireccionalidad

Si la conectividad V2V se modela como **bidireccional** (por defecto), la existencia de la tupla `(t, v_i, v_j)` implica también `(t, v_j, v_i)`. En ese caso, la Matriz A es **simétrica**.

Si la conectividad se modela como **dirigida**, no se fuerza dicha simetría.

En la interfaz hay un **checkbox** para configurar esto. Por defecto está activada la bidireccionalidad.

### Algoritmo de Generación

La función `generar_tuplas_v2v()` implementa el siguiente algoritmo:

```
Para cada timestep t en FCD:
  n = número de vehículos activos en t
  Inicializar A como matriz n×n de ceros
  
  Para cada par (i, j) con i < j:
    1. distancia = √((Vi_x - Vj_x)² + (Vi_y - Vj_y)²)
    2. Si distancia > radio_obu → SKIP
    3. Si distancia ≤ radio_obu:
       a. Si tiene_linea_de_vista(Vi, Vj, edificios) → LoS confirmado
       b. A[i][j] = 1
       c. Si bidireccional: A[j][i] = 1
       d. Añadir tupla <t, Vi, Vj>
       e. Si bidireccional: añadir tupla <t, Vj, Vi>
```

**Optimizaciones:**
- Solo evaluar pares con `i < j` (evita duplicados)
- Pre-filtrar edificios por zona (bbox de todos los vehículos + margen del radio OBU)
- Reutiliza la misma función `tiene_linea_de_vista()` de V2I

### Parámetros Configurables (UI)

| Parámetro | Control UI | Default | Rango | Descripción |
|-----------|-----------|---------|-------|-------------|
| `radio_obu_sim` | Slider: 📱 Radio OBU | **300m** | 50 – 500m | Radio de cobertura del OBU (aplica a V2I y V2V) |
| `v2v_bidireccional` | Checkbox: 🔄 Bidireccional | **True** | On / Off | Si la Matriz A es simétrica |
| `step_intervalo` | Slider: ⏱️ Intervalo de muestreo | **2 min** | 1 – 30 min | Cada cuántos minutos se toma una muestra del tráfico |

### Estructura del JSON de Salida (`tuplas_v2v.json`)

```json
{
    "parametros": {
        "radio_obu": 300,
        "bidireccional": true,
        "total_tuplas_v2v": 523,
        "total_timesteps": 100,
        "total_pares_evaluados": 15000,
        "total_pares_en_rango": 890,
        "resumen_por_vehiculo": {
            "V0": {"total_conexiones": 45, "vecinos_unicos": 8},
            "V1": {"total_conexiones": 38, "vecinos_unicos": 6}
        }
    },
    "tuplas_v2v": [
        {"t": 0.0, "vehiculo_i": "V0", "vehiculo_j": "V1", "distancia": 45.3},
        {"t": 0.0, "vehiculo_i": "V1", "vehiculo_j": "V0", "distancia": 45.3}
    ],
    "matrices": {
        "0.0": {
            "vehiculos": ["V0", "V1", "V2"],
            "A": [[0, 1, 0], [1, 0, 1], [0, 1, 0]]
        },
        "1.0": {
            "vehiculos": ["V0", "V1", "V2", "V3"],
            "A": [[0, 1, 0, 0], [1, 0, 1, 0], [0, 1, 0, 1], [0, 0, 1, 0]]
        }
    }
}
```

---

## 🔢 Matrices de Conectividad

Para cada instante de tiempo `t`, se construyen **dos matrices binarias**:

### Matriz A — Vehículo×Vehículo

```
A ∈ {0, 1}^{n×n}

A_ij = 1 si v_i ve directamente a v_j (con LoS + dentro del radio OBU)
A_ij = 0 en caso contrario
```

- La diagonal es cero (un vehículo no se conecta consigo mismo)
- Si la conectividad es bidireccional, A es simétrica: `A_ij = A_ji`
- `n` varía en cada timestep (vehículos activos)

### Matriz B — Vehículo×RSU

```
B ∈ {0, 1}^{n×m}

B_ik = 1 si v_i ve directamente a la RCU r_k (con LoS + dentro del radio OBU)
B_ik = 0 en caso contrario
```

- `n` = número de vehículos activos en el timestep
- `m` = número de RSU candidatos (fijo)
- Representa la conectividad a un salto: `v_i → r_k`

### Visualización en la UI

La pestaña **"🔢 Matrices A y B"** permite seleccionar un instante de tiempo con un slider y ver ambas matrices renderizadas como DataFrames interactivos. Se muestran:

- El tamaño de cada matriz
- El número de conexiones activas (número de 1s)
- Los IDs de vehículos y RSU como etiquetas de filas/columnas

---

### Parámetros configurables (UI del Módulo 2)

| Parámetro | Control UI | Default | Rango | Descripción |
|-----------|-----------|---------|-------|---------| 
| `num_vehiculos` | Slider: 🚗 Número de vehículos | **100** | 5 – 1000 | Vehículos totales a generar con rutas aleatorias (el motor de conectividad usa índice espacial, así que escala a 1000) |
| `tiempo_simulacion` | Slider: 🕐 Duración de simulación | **120 min** | 1 – 180 min | Tiempo total de la simulación SUMO en minutos (hasta 3 horas; 120 = 2 h) |
| `periodo_salida` | **Automático** (no es slider) | — | — | Se calcula como `duración / Nº autos`: reparte los autos a lo largo de la simulación |
| `radio_obu_sim` | Slider: 📱 Radio OBU | **300m** | 50 – 500m | Radio de cobertura del OBU del vehículo (aplica a V2I y V2V) |
| `step_intervalo` | Slider: ⏱️ Intervalo de muestreo | **2 min** | 1 – 30 min | Cada cuántos **minutos** se toma una muestra (foto) del tráfico |
| `v2v_bidireccional` | Checkbox: 🔄 Bidireccional | **True** | On / Off | Si la Matriz A V2V es simétrica |

**¿Dónde cambiar los defaults?**

En la constante `DEF` de [`web/src/App.tsx`](web/src/App.tsx) (frontend) y en los
*schemas* de la API ([`api/main.py`](api/main.py): `ScenarioReq`, `SimReq`).

---

### Visualización del Módulo 2

La interfaz de visualización tiene **5 tabs**:

#### Tab 1: Tabla de Tuplas V2I
- Tabla interactiva con todas las tuplas `<t, V, RSU>` (Matriz B)
- Filtros por RSU, vehículo, y rango de tiempo
- Columnas: Tiempo (s), Vehículo, RSU, Distancia (m)

#### Tab 2: Tabla de Tuplas V2V
- Tabla interactiva con todas las tuplas `<t, Vi, Vj>` (Matriz A)
- Filtros por Vehículo i, Vehículo j, y rango de tiempo
- Columnas: Tiempo (s), Vehículo i, Vehículo j, Distancia (m)

#### Tab 3: Matrices A y B
- Selector de timestep con slider
- **Matriz A** (n×n): DataFrame con vehículos como filas/columnas, valores 0/1
- **Matriz B** (n×m): DataFrame con vehículos como filas y RSU como columnas, valores 0/1
- Estadísticas de cada matriz (dimensiones, conexiones activas)

#### Tab 4: Multisalto
- Selector de máximo de saltos `H` (1–6) y de instante de tiempo
- Checkbox **"Forzar A simétrica"**
- Tabla resumen por salto (pares alcanzables, vehículos conectados, pares nuevos)
- Visor de cualquier matriz `R_h`, `S_h` o `D_H`, y el vector `d` de vehículos aislados
- Ver la sección [**Módulo Multisalto**](#-módulo-multisalto--conectividad-de-varios-saltos) para el detalle matemático

#### Tab 5: Mapas de Conectividad (instantes exactos)
Se generan **4 mapas simultáneos**, cada uno mostrando una **captura instantánea** (snapshot) de la conectividad V2I y V2V en un momento exacto de la simulación:
- **Mapa al 25%**: Instante exacto al 25% de la duración total
- **Mapa al 50%**: Instante exacto al 50% de la duración total
- **Mapa al 75%**: Instante exacto al 75% de la duración total
- **Mapa al 100%**: Último instante de la simulación

Cada mapa Folium tiene 5 capas toggleables:
- **🏢 Edificios**: Polígonos naranjas (obstrucciones LoS)
- **🚗 Vehículos**: Posiciones exactas de los vehículos activos en ese instante
- **📡 Conexiones V2I**: Líneas verdes punteadas entre vehículos y RSU cuando hay LoS
- **🚗 Conexiones V2V**: Líneas amarillas punteadas entre vehículos conectados
- **📡 RSU Candidatos**: Marcadores rojos en las posiciones de los RSU

Los mapas se muestran en una grilla 2×2 para una comparación visual directa entre momentos clave de la simulación.

---

## 🧪 Guía de Experimentación

### Escenarios de prueba recomendados

Para la tesis, se recomienda ejecutar el pipeline con diferentes combinaciones de parámetros y documentar los resultados:

#### Escenario 1: Máxima cobertura (más RSU)

```
Grado mínimo:     3
Radio agrupación: 10 metros
```
- Incluye intersecciones T de una sola calle
- Más puntos RSU = mayor cobertura pero mayor costo
- Útil para zonas con calles estrechas

#### Escenario 2: Cobertura estándar (recomendado)

```
Grado mínimo:     4
Radio agrupación: 20 metros
```
- Solo cruces de 2+ calles bidireccionales
- Balance entre cobertura y costo
- **Es el escenario por defecto de la aplicación**

#### Escenario 3: Solo intersecciones principales

```
Grado mínimo:     6
Radio agrupación: 30 metros
```
- Solo cruces donde convergen 3+ calles
- Mínimo número de RSU = menor costo
- Útil para redes de malla urbana regular

#### Escenario 4: Sin clustering (análisis de densidad)

```
Grado mínimo:     4
Radio agrupación: 0 metros
```
- Desactiva el clustering espacial
- Muestra TODAS las junctions con grado ≥ 4, sin importar la proximidad
- Útil para analizar la densidad de intersecciones en una zona

### Matriz de resultados para documentar

Se sugiere crear una tabla comparativa para la tesis:

| Zona geográfica | Área (km²) | Junctions orig. | min_grado | radio (m) | RSU candidatos | Reducción (%) |
|-----------------|------------|-----------------|-----------|-----------|----------------|---------------|
| Centro Histórico (A) | ~0.5 | 1211 | 3 | 15 | 393 | 67.5% |
| Centro Histórico (B) | ~0.5 | 1211 | 3 | 20 | 366 | 69.8% |
| Centro Histórico (C, ref.) | ~0.5 | 1211 | 4 | 20 | 278 | 77.0% |
| Centro Histórico (D) | ~0.5 | 1211 | 5 | 25 | 14 | 98.8% |
| Zona Norte | ~0.8 | — | 4 | 20 | — | — |
| Zona Industrial | ~1.0 | — | 4 | 20 | — | — |

> Nota: el **grado** es el número de **vecinos únicos** (grafo no dirigido). Con grado 5 (config D) muy pocas junctions del centro histórico califican (la mayoría son cruces de 4 vecinos), por eso D es tan selectivo. Valores reproducibles con `filtrar_junctions_rsu()` sobre `output/`.

### Experimento: cobertura frente a presupuesto de RSU

Con la casilla *"Limitar nº de RSU (MaxR)"* se puede trazar la **curva de diseño**
del escenario: cuánta cobertura compra cada antena, **sobre el mismo mapa y la
misma simulación**. Protocolo:

1. Genera el escenario y simula **una sola vez** (M1 → M2). Así todas las medidas
   comparten `.dat`, vehículos e instantes: solo cambia `MaxR`.
2. Pulsa **Optimizar** con la casilla **apagada** → anota el tiempo de la subetapa
   *"Solver CPLEX"*, el `Objetivo` y las `RSU desplegadas`.
3. Repite pulsando **Optimizar** con la casilla **encendida** y distintos valores.
   Cada corrida se añade a la misma sesión del cronómetro, así que el resumen final
   las lista todas con su nombre (`MaxR=…`) y su porcentaje del total.

Resultado medido con los **pesos actuales** sobre un `output/` de 3691 pares
(instante, vehículo), 1649 RSU candidatas, `H = 3` y tope de 120 s por punto:

| MaxR | RSU usadas | Conectados | **Cobertura** | Multisalto | +pares por RSU extra |
|---|---|---|---|---|---|
| 10 | 10 | 1282 | 34,73 % | 235 | — |
| 25 | 25 | 1977 | 53,56 % | 220 | **46,33** |
| 50 | 50 | 2604 | 70,55 % | 203 | 25,08 |
| 100 | 100 | 3201 | 86,72 % | 95 | 11,94 |
| 150 | 150 | 3412 | 92,44 % | 61 | 4,22 |
| 200 | 200 | 3509 | 95,07 % | 41 | 1,94 |
| 300 | **248** | 3552 | 96,23 % | 29 | 0,90 |
| 400 | **249** | 3552 | 96,23 % | 28 | 0,00 |
| sin límite | **249** | 3552 | 96,23 % | 28 | — |

**Ninguna fila se cortó por tiempo**: las nueve cerraron con `integer optimal`, así
que todas las coberturas son exactas, no cotas inferiores.

Cuatro lecturas:

1. **La cobertura satura, no hace campana.** Subir `MaxR` nunca puede reducirla:
   toda solución válida con `MaxR = k` lo sigue siendo con `k+1`. El techo aquí es
   **96,23 %** — quedan **139 pares irreducibles** que ninguna infraestructura
   alcanza (no ven ninguna candidata, ni directamente ni por multisalto).
2. **`MaxR` deja de atar en ~249.** Con `MaxR = 300` el modelo usó 248 RSU y con
   `400` usó 249: le sobraba presupuesto en ambos casos. Por eso poner un tope por
   encima de ~250 **no cambia nada** en este escenario.
3. **El codo está entre 100 y 150 RSU:** con 150 antenas (el 60 % de las 249 que
   usaría sin límite) ya se consigue el 92 % de cobertura. De 200 en adelante cada
   antena nueva conecta menos de 2 pares, y de 300 en adelante menos de 1.
4. **El multisalto crece según escasea la infraestructura** (28 → 235 al bajar
   `MaxR`). Es el argumento de por qué el V2V importa: su aporte es máximo
   justamente en el régimen de presupuesto limitado, que es el realista.

> Sobre el multisalto: en un escenario anterior con muchas más candidatas (5325)
> la curva hacía un **pico interior** en `MaxR ≈ 50` y caía a ambos lados, porque
> con muy pocas antenas ni siquiera hay adónde puentear. Aquí, con 1649
> candidatas, esa zona queda por debajo de `MaxR = 10` y solo se ve el tramo
> decreciente. **La forma exacta depende del escenario; lo robusto es la
> tendencia**: más infraestructura, menos multisalto.

<a id="lex"></a>

### Cómo se resuelve: multi-objetivo lexicográfico

El modelo tiene **tres criterios que compiten**: dejar al menor número de
vehículos sin cobertura, usar pocas antenas y que el tráfico servido dé los menos
saltos posibles. La Ec. 1 original los suma en un único objetivo, pero eso trae
un problema práctico: **la tolerancia de CPLEX se aplica al total**. Como el total está dominado por las penalizaciones de desconexión,
el 0,01 % de tolerancia equivale a un margen enorme *medido en antenas* —con una
configuración anterior llegó a ser de **1 390 RSU**—, así que el solver paraba
dentro de ese margen y devolvía muchas más de las necesarias. Además, cuál de
los dos criterios pesaba más dependía de la relación `L · P[hmax] / Cost`.

La solución es **no sumarlos**, sino dárselos a CPLEX con prioridades. En
`docplex` es una sola llamada ([optimizar\_rsu.py](optimizacion/optimizar_rsu.py)):

```python
coste_instalacion  = mdl.sum(Sel[r] * Cost[r] for r in R)
carga_desconectada = mdl.sum(L[t[0]][t[2]] * Rts[t] for t in CVR if t[1] == hmax)
coste_trafico      = mdl.sum(Rts[t] * Ph(t[1]) * L[t[0]][t[2]]
                             for t in CVR if t[1] != hmax)

mdl.minimize_static_lex(
    [carga_desconectada, coste_instalacion, coste_trafico],   # orden de prioridad
    abstols=[0.0, 0.0, 0.0], reltols=[0.0, 0.0, 0.0],         # lexicográfico ESTRICTO
)
```

CPLEX minimiza **1º** la carga que se queda sin cobertura; **entre todas las
soluciones que alcanzan ese óptimo**, la que despliega **2º** menos RSU; y entre
esas, la de **3º** menos saltos.

Partir el tráfico en dos es exacto porque en este modelo `h == hmax` ocurre **si
y solo si** `r == r_inf`: la única tupla con salto `hmax` es la que va al RSU
artificial ([exportar\_dat.py](backend/exportar_dat.py)). No hay solape.

> **Por qué las tolerancias van en cero.** Con los valores por defecto, CPLEX se
> permite degradar un poco el primer objetivo al optimizar el segundo. En este
> modelo "un poco" del primer objetivo puede ser **un vehículo desconectado**.

**Lo que se gana (1): el número de RSU sale de la escala del total.** Pasa a
optimizarse en la suya propia —unos miles de puntos en vez de millones—, así que
el 0,01 % equivale a menos de una décima de antena.

**Lo que se gana (2): `penal_desconexion` desaparece del modelo.** Con la
desconexión en su propio nivel de prioridad, `P[hmax]` ya no aparece en ningún
objetivo, y en la Ec. 4 tampoco porque esa restricción excluye a `r_inf`.
Comprobado construyendo el modelo con `P[hmax] = 1000` y con `P[hmax] = 5` y
comparando el SHA-256 del LP exportado:

| | `penal = 1000` | `penal = 5` | |
|---|---|---|---|
| 2 niveles | `78f8371c22cbedcd` | `da71d300a6b36d9f` | distintos: **influye** |
| **3 niveles** | `d52750d7cb4d2ce2` | `d52750d7cb4d2ce2` | idénticos: **inerte** |

Deja de ser un parámetro que calibrar —"¿8, 100 o 1 000?"— y pasa a ser una
decisión de prioridad, que sí se puede justificar. Por la misma razón, la
**cobertura máxima queda garantizada por construcción**, no "mientras la
penalización sea suficientemente grande".

**Lo que cambia: la preferencia entre antenas y saltos se invierte.** Con dos
niveles los saltos vivían *dentro* del primer objetivo, así que la calidad
multisalto le ganaba al número de antenas. Con tres, entre dos despliegues de
igual cobertura se prefiere el de menos antenas aunque obligue a más vehículos a
conectarse por 2 o 3 saltos. Es una decisión de diseño deliberada —la
infraestructura es dinero; los saltos son calidad de servicio— y se refleja en
las cifras: igual cobertura, menos RSU, más multisalto.

Medido sobre el mismo escenario (99 865 tuplas CVR, 7 108 RSU candidatas,
`H = 3`, sin límite de MaxR), contra la suma ponderada y contra la versión
intermedia de dos niveles:

| | Suma ponderada | 2 niveles | **3 niveles** |
|---|---|---|---|
| **RSU desplegadas** | 792 | 779 | **767** |
| Cobertura | 93,79 % | 93,79 % | **93,79 %** |
| Pares desconectados | 556 | 556 | **556** |
| Pares en multisalto | 66 | 63 | **82** |
| Valor de la Ec. 1 | 5 652 540 | 5 652 380 | 5 652 450 |
| Motor CPLEX | 8,2 s | 97,9 s | **203,7 s** |
| Estado | `integer optimal, tolerance` | `multi-objective optimal` | `multi-objective optimal` |

**Misma cobertura exacta —los mismos 556 pares desconectados en los tres— con 25
antenas menos que la suma ponderada.** El precio son 16 pares más en multisalto
(el nivel 3 es el último en optimizarse) y un motor 25× más lento, porque CPLEX
resuelve tres problemas en secuencia. Aun así la optimización sigue siendo una de
las etapas rápidas del flujo, muy por detrás de SUMO y del cálculo de línea de
vista.

> **Detalle revelador:** la suma ponderada obtiene el **peor** valor de la Ec. 1
> de los tres, y eso es precisamente lo único que estaba minimizando. Paró dentro
> dentro de su tolerancia relativa del 0,01 %, que sobre un total de 5,65
> millones son ~565 puntos de margen; a `Cost = 10` por antena, eso son **56
> antenas de holgura** que el solver tenía permitido no buscar. Las 25 de más que
> devuelve caben de sobra ahí. Es el problema de escala descrito arriba, visto en
> una sola cifra.

**Lo que permite afirmar.** Con la suma ponderada el resultado era un compromiso
cuyo peso relativo era una decisión del autor. Con la jerarquía se puede afirmar
algo con estructura: *de entre todos los despliegues que dejan al mínimo posible
de vehículos sin cobertura, este es el que usa menos RSU; y de entre esos, el que
menos saltos exige*.

Está **activo por defecto**. La casilla *"Resolver por prioridades"* del panel M3
permite volver a la suma ponderada para comparar; la respuesta trae los tres
objetivos por separado en `objetivos` —en orden de prioridad—, y `objetivo`
re-evalúa la Ec. 1 sobre la solución encontrada para que el KPI siga siendo
comparable entre modos y con corridas antiguas.

<a id="pesos"></a>

### Los pesos del modelo y qué gobierna cada uno

Los cuatro parámetros de [`construir_datos_opl()`](backend/exportar_dat.py) que
definen el comportamiento del modelo:

| Parámetro | Valor actual | Qué es |
|---|---|---|
| `cap_real` | `300` | Capacidad de una RSU **en unidades de carga × saltos** |
| `carga_default` | `10` | Carga `L` de cada vehículo (p. ej. Mbps) |
| `Cost[r]` | `10` | Lo que cuesta instalar una antena |
| `penal_desconexion` | `1000` | `P[hmax]`: lo que paga un vehículo sin cobertura. **Solo se usa en la suma ponderada**: con el [lexicográfico de 3 niveles](#lex) es inerte |

**Ojo con la capacidad:** la Ec. 4 consume `Rts · P_h · L`, no solo `L`. O sea, un
vehículo servido a 2 saltos gasta **el doble** de capacidad que uno directo. Con
los valores actuales, cada RSU aguanta **30 vehículos a 1 salto**, 15 a 2 saltos
o 10 a 3, por instante.

> `cap_inf` (capacidad de `r_inf`) **no se usa**: ambos modelos excluyen a `r_inf`
> de la Ec. 4, porque no es una antena sino "no tener cobertura". Ponerle un tope
> haría el modelo infactible en vez de reportar la desconexión.

> Con el [multi-objetivo lexicográfico](#lex) activo (por defecto), **ni el
> número de RSU ni la cobertura dependen ya de estos pesos**: cada uno se
> optimiza en su propio nivel de prioridad, y `penal_desconexion` no llega
> siquiera a entrar en el modelo. Lo único que siguen gobernando es la Ec. 4
> (capacidad) y, en el tercer nivel, cuántos saltos se aceptan. **Todo lo que
> sigue en esta sección describe la suma ponderada**, que se conserva para
> comparar; es el análisis que motivó pasar a la jerarquía.

**La razón que de verdad manda.** No son los valores sueltos, sino cuántas antenas
está dispuesto el modelo a pagar por rescatar un vehículo-instante:

```
antenas que paga = (P[hmax] − P_h) × L / Cost
```

Con los valores actuales: `(1000 − 1) × 10 / 10 = ` **999 antenas**. Como ningún
vehículo alcanzable necesita 999 antenas dedicadas, en la práctica el modelo
**conecta a todos los que son físicamente alcanzables**, y los que quedan fuera
son irreducibles (no ven ninguna candidata, ni directamente ni por multisalto).

**Cómo se eligió.** Medido sobre el mismo escenario (3691 pares, 1649
candidatas, MaxR libre, tope 120 s), moviendo solo `penal_desconexion`:

| `P[hmax]` | RSU | Cobertura | Motor | Paga hasta |
|---|---|---|---|---|
| 8 | 249 | 96,23 % | 76,3 s | 7 antenas |
| 100 | 249 | 96,23 % | 15,2 s | 99 antenas |
| **1000** (actual) | **252** | **96,23 %** | **1,0 s** | **999 antenas** |

La cobertura es la misma en los tres; lo que cambia es el tiempo y la precisión:

- **Con 8** la garantía es frágil: si en otro mapa un vehículo necesitara 8
  antenas para ser alcanzado, el modelo lo abandonaría **sin avisar** — verías
  menos cobertura y parecería que ese vehículo era imposible de conectar. Y
  encima es el más lento (76 s), porque con un objetivo tan pequeño el margen del
  0,01 % vale una décima de antena y el solver pelea por cada una.
- **Con 1000** el solver cierra en **1 segundo** y la garantía de cobertura es
  muy fuerte, a cambio de ~3 antenas de imprecisión sobre 250: el margen del
  0,01 % de `Z` crece con `Z`, y recortar esas últimas antenas ya no le baja el
  objetivo lo suficiente como para molestarse.

Es un intercambio deliberado: **se prioriza la garantía de cobertura y la
velocidad sobre la exactitud del recuento de RSU**. Si en algún momento la cifra
exacta de antenas fuera lo importante, `100` es el punto intermedio.

Análisis completo en [`explicaciones/medicion_y_afinado.pdf`](explicaciones/)
(no versionado).

### Áreas grandes: descarga OSM y tiempos de SUMO

La descarga pide a Overpass **solo lo que el proyecto usa** —`highway=*` para la
red vial y `building=*` para los obstáculos de la línea de vista—, no todo el
contenido del rectángulo. Eso reduce el volumen de forma drástica y es lo que
permite bajar áreas metropolitanas.

Además, calles y edificios se piden **por separado y en paralelo**, los
edificios se **trocean en cuadrantes** cuando el servidor no puede con ellos, se
prueban **varias instancias de Overpass** hasta que una responde, y **lo
descargado se cachea por bbox** para que repetir el mismo área no vuelva a
esperar. El detalle y las mediciones están en la ficha de
`descargar_mapa_osm()`, en la sección *Backend — Documentación Detallada*.
Resultado sobre el área Quito–Sangolquí: **168 MB en 71 s**.

Los límites de tiempo de las herramientas de SUMO también son configurables,
porque con una ciudad entera 300 s no alcanzan:

```powershell
$env:SUMO_TIMEOUT_S = "3600"     # 1 h por herramienta de SUMO (0 = sin límite)
$env:SUMO_SEMILLA = "42"         # semilla de randomTrips y sumo (reproducibilidad)
$env:SUMO_HILOS = "16"           # hilos de duarouter y de la simulación (0 = todos)
$env:SUMO_UMBRAL_HILOS = "700"   # por debajo de N viajes no se paraleliza (sale peor)
$env:OVERPASS_TIMEOUT_S = "300"  # lo que se le concede al servidor de Overpass
$env:OVERPASS_REINTENTOS = "3"   # rondas completas sobre la lista de servidores
$env:OVERPASS_CARRERA = "2"      # instancias que compiten a la vez por cada consulta
$env:OVERPASS_HTTP_TIMEOUT_S = "120"  # espera máxima por servidor
$env:OVERPASS_ESPERA_S = "20"    # pausa entre rondas (los 504 son transitorios)
$env:MAX_EDIFICIOS_MAPA = "15000"  # OPCIONAL: limita cuántos edificios se DIBUJAN
$env:OSM_CACHE_DIAS = "30"       # antigüedad máxima de la caché de .osm (0 = sin caché)
$env:OSM_CACHE_DIR = "D:\osm"    # OPCIONAL: dónde vive la caché (por defecto .osm_cache/)
uvicorn api.main:app --reload --port 8000
```

**Qué se optimizó para que M1 no se eternice.** Con la red de Quito el
`.net.xml` pesa **565 MB** y se recorría entero varias veces:

| | Antes | Ahora | Cómo |
|---|---|---|---|
| `obtener_proyeccion` | 17,3 s | **0,0 s** | `iterparse` + `break` al hallar `<location>` |
| Re-filtrar RSU | 66 s cada vez | **0,0 s** | caché de grados por red |
| Memoria durante el parseo | varios GB (árbol completo) | constante | lectura en streaming |
| Descarga de Overpass | 151 s en serie | coste de la más lenta | vías y edificios **en paralelo** |
| Repetir el mismo área | 151 s otra vez | **0,0 s** | [caché de `.osm` por bbox](#-backend--documentación-detallada) |
| `duarouter` (rutas) | 1 núcleo + dijkstra | **N núcleos + A\*** | [paralelismo](#paralelismo) |

**Cómo se repartía el tiempo de M1** antes del paralelismo, medido sobre un área
de Quito (reconstruido desde las marcas de tiempo de los archivos de `output/`):

| Sub-etapa | tiempo | % |
|---|---|---|
| **Overpass: vías** | 114 s | 56 % |
| **Overpass: edificios** | 37 s | 18 % |
| netconvert | 10 s | 5 % |
| polyconvert | 6 s | 3 % |
| randomTrips (+ `duarouter`) | 34 s | 17 % |
| Parseo junctions + edificios | 3 s | 1 % |
| **Total** | **~204 s** | |

Las dos descargas eran **el 74 % de M1**, y no eran cómputo: era la CPU parada
esperando a un servidor público. De ahí que las dos primeras optimizaciones de
la tabla ataquen eso y no el código.

El reparto cambia por completo al subir los vehículos: `randomTrips` pasa a
dominar, porque `duarouter` calcula un camino mínimo **por vehículo**. Medido en
esa misma corrida de 50 000 vehículos sobre la red de 379 MB:

| Herramienta | Tiempo | % de la etapa |
|---|---|---|
| netconvert | 57 s | 2 % |
| polyconvert | 21 s | 0,7 % |
| **randomTrips** (→ `duarouter`) | **2 743 s** y seguía | **97 %** |

Ni `netconvert` ni `polyconvert` admiten hilos —no tienen la opción— pero es
irrelevante: aunque costaran cero se ahorrarían 78 s de casi una hora. Los dos
que sí la tienen, `duarouter` y `sumo`, son justo los que dominan, y son los que
se paralelizan.

> El cronómetro imprime **una línea por herramienta**. Antes las agrupaba en un
> solo `SUMO (netconvert/polyconvert/trips)`, y con ese número junto es imposible
> saber cuál cuesta — llevaba a culpar a `polyconvert`, que es el 0,7 %.

> **Sobre el peso del mapa.** Con un área metropolitana la respuesta de
> edificios ronda los **27 MB (165 000 polígonos)** y el navegador va lento al
> dibujarla. Se probó enviar un muestreo, pero el mapa deja de verse como es:
> por eso **por defecto se envían todos**. Si en algún momento el navegador se
> vuelve inusable, `MAX_EDIFICIOS_MAPA` activa el muestreo uniforme (0 = sin
> tope, que es el valor por defecto). En ningún caso afecta al cálculo: la línea
> de vista usa siempre el conjunto completo del backend.

> **Dónde está el verdadero muro.** Subir estos límites hace que la descarga y
> SUMO terminen, pero el coste se traslada a la optimización, que escala de forma
> **combinatoria** con el nº de RSU candidatas (ver
> [Experimento: cobertura frente a presupuesto de RSU](#experimento-cobertura-frente-a-presupuesto-de-rsu)).
> Para un área metropolitana hay que subir el **radio de clúster** a 200–500 m y
> el **grado mínimo** a 5–6: con un radio de 20 m se generan candidatas cada 20
> metros en toda la ciudad, que no es un despliegue realista ni un problema
> resoluble.

### Cómo cambiar la zona geográfica

1. Levantar la app (API + `npm run dev`, ver [Instalación](#-instalación-y-ejecución)).
2. Botón **"◱ Seleccionar área"** y **dos clics** en el mapa (cualquier zona del mundo).
3. **Generar escenario** → **Filtrar RSU**; ajusta los *sliders* y vuelve a filtrar
   para ver cómo cambia el número de RSU.

### Dónde quedan los resultados

Cada **"Generar escenario"** crea su propia carpeta `datos/corridas/web_v{veh}_t{min}_s{semilla}_{fecha}/`
y ahí van todos los archivos de esa sesión: `junctions_limpias.json`,
`edificios_limpios.json`, `tuplas_visibilidad.json` (Matriz B / V2I), `tuplas_v2v.json`
(Matriz A / V2V), el `dataset.dat` de la optimización y un **`manifest.json`** que
cada clic va completando (bbox, vehículos, semilla, filtrado, radio, métricas,
despliegue). Al pulsar **Optimizar**, la corrida queda además **registrada en el
catálogo** con los mismos campos que una del CLI —ver [Campañas, catálogo y
almacén](#campanas)—. No hay que exportar nada a mano: son los mismos archivos
que la API lee para rehidratar el escenario al reiniciar (el puntero está en
`datos/web_ultima.txt`). Por compatibilidad, `optimizacion/rsu_backend.dat` se
sigue actualizando con una copia del último `.dat`.

---

<a id="campanas"></a>

## 🧪 Campañas por lotes: `scn.py`, el catálogo y el almacén de etapas

La interfaz sirve para **una** corrida: se dibuja el área y se pulsan cuatro
botones. Para el artículo hacen falta **decenas** —barridos de semilla, de
demanda, de filtrado— y repetir clics no escala ni deja registro. De ahí tres
piezas que trabajan juntas:

| Pieza | Archivo | Qué resuelve |
|---|---|---|
| **CLI** | `scn.py` | Lanzar corridas desde la terminal, en bucle, con la semilla fijada |
| **Catálogo** | `backend/catalogo.py` → `datos/catalogo.sqlite` | Saber **qué** se corrió, con **qué** parámetros y **qué** salió |
| **Almacén de etapas** | `backend/almacen.py` → `datos/cache/` | No volver a calcular una etapa cuya salida ya existe |

La web y el CLI son dos clientes del mismo núcleo (`backend/flujo.py`) y **guardan
igual**: carpeta propia, `manifest.json`, fila en el catálogo. La diferencia es
solo quién pulsa.

### El CLI, en cuatro pasos

```powershell
# 1. Elegir el área en el navegador (una vez): dibujas el rectángulo y Guardar
.\.venv\Scripts\python.exe scn.py mapa --nombre centro

# 2. Ver qué haría la campaña (cuántas corridas, qué se reutiliza)
.\.venv\Scripts\python.exe scn.py campana campanas\fisica_v1.yaml --plan

# 3. Lanzarla (se puede cortar con Ctrl+C y volver a lanzar: continúa).
#    Con varios YAML se ejecutan juntos, semilla a semilla (ver "Varias semillas")
.\.venv\Scripts\python.exe scn.py campana campanas\fisica_v1.yaml

# 4. Figuras + tabla LaTeX + CSV para Power BI / Excel; con `semillas` en el
#    YAML, --semillas da la media y el intervalo de confianza de cada punto
.\.venv\Scripts\python.exe scn.py reporte --campana fisica_v1 --semillas
```

| Orden | Qué hace |
|---|---|
| `mapa --nombre N` | abre una página local (Python, sin la API) con un mapa; el rectángulo se guarda en `datos/areas.json` con ese nombre. Pinta las áreas ya guardadas y la cobertura del extracto local |
| `areas` | lista las áreas; `areas --agregar N --bbox=...` guarda una sin mapa |
| `correr --area N ...` | una corrida suelta (ver opciones abajo) |
| `campana A.yaml [B.yaml ...]` | uno o varios lotes factoriales (con varios, o con `semillas`, se ejecutan semilla a semilla); `--plan` (no ejecuta), `--semilla S` (solo esa semilla), `--solo K` (los K primeros pendientes de cada campaña y semilla), `--sin-m3`, `--detalle`, `--paralelo N\|auto` (varias optimizaciones a la vez, ver [En paralelo](#paralelo)) |
| `listar` · `estado` | corridas registradas · resumen del catálogo y del almacén |
| `exportar --campana N` | CSV con una fila por corrida (`datos/reportes/N/N.csv`) en formato de Excel en español: separador `;`, coma decimal, UTF-8 con BOM. En Power BI, importarlo con la configuración regional *Español*. Con `--semillas`, `N` es una familia: `N_semillas.csv` (todas las corridas) y `N_resumen.csv` (media, desviación e IC 95 % por punto) |
| `reporte --campana N` | CSV + figuras (PDF vectorial + PNG) + tablas `.tex` en `datos/reportes/N/`; si la campaña tiene `carga` o `presupuesto`, también las de esos factores. Con `--semillas`, las mismas con la media de las semillas y barras de error, en `datos/reportes/N_semillas/` |
| `powerbi [--campana A B] [--abrir]` | exporta los CSV y escribe un **proyecto de Power BI** listo (`datos/reportes/powerbi/SmartCityNet.pbip`): una tabla y una página por campaña, con segmentaciones y cuatro gráficos (RSU, cobertura, multisalto y uso de capacidad frente a la carga, el presupuesto o los vehículos), ya resumidos por promedio y con los colores de las figuras de la tesis. Al abrirlo: *Actualizar ahora*. Regenerarlo sobrescribe la carpeta: lo editado a mano, guárdalo con otro nombre |
| `extracto` | descarga/registra el mapa de Ecuador para trabajar sin internet |

Opciones de `correr`:

| Opción | Qué es | Por defecto |
|---|---|---|
| `--area` o `--bbox=` | área guardada, o `min_lon,min_lat,max_lon,max_lat` (el `=` es obligatorio) | — |
| `--vehiculos` · `--duracion` | demanda (**máximo 5 000**) y minutos simulados | 100 · 10 |
| `--semilla` | fija `randomTrips` y `sumo`; misma semilla = mismo escenario | 42 |
| `--gmin` · `--rho` | filtrado de candidatas: grado mínimo y radio de clúster (m) | 4 · 20 |
| `--fisica` | `TASA:CRITERIO` (p. ej. `6:r90`): radio, $P[h]$ y Cap del modelo del tutor | — (usa `--radio`) |
| `--radio` · `--paso` · `--H` | alcance OBU si no hay `--fisica` (m), muestreo (min), saltos | 300 · 2 · 3 |
| `--optimizar` · `--tope-m3` | resolver M3 y guardar el despliegue · tope total en s | no · 5400 |
| `--campana` · `--silencioso` · `--sin-cache` | etiqueta · menos salida · recalcular todo | — |

### Las campañas (`campanas/*.yaml`)

Una campaña es un **experimento factorial**: un área, una semilla y listas de
niveles; se ejecuta el producto cartesiano. El archivo YAML se versiona con el
código y **es la especificación del experimento** (además queda copiado en la
tabla `campana` del catálogo). Ver [`campanas/fisica_v1.yaml`](campanas/fisica_v1.yaml):

```yaml
nombre: fisica_v1
area: centro                      # la de `scn.py mapa --nombre centro`
semillas: [42, 1, 2, 3, 4, 5, 6, 7, 8, 9]   # o `semilla: 42` para una sola
duracion_min: 60
muestreo_min: 5
tope_m3_s: 5400                   # 1 h 30 por optimización
factores:
  vehiculos: [1000, 2500, 5000]
  fisica: ["3:r80", "3:r90", "6:r80", "6:r90", "12:r80", "12:r90"]
  H: [1, 2, 3]
  filtrado: [C, A]                # del artículo V5
```

**Por qué el factor es la "física" y no el radio.** El alcance, el coste del
salto y la capacidad no se eligen a mano: los fija la configuración de 802.11p a
través del modelo del tutor ([Capa física](#fisica)). Cada nivel `TASA:CRITERIO`
fija **juntos y coherentes** el radio ($r_{80}$/$r_{90}$ con interferente), $P[h] = \Gamma_h$
y $\mathrm{Cap} = \alpha C_0$. `"clasica"` reproduce los valores de antes como línea base.

| Nivel | 3:r80 | 3:r90 | 6:r80 | 6:r90 | 12:r80 | 12:r90 |
|---|---|---|---|---|---|---|
| Radio (1000 B, con interferente) | 275 m | 135 m | 200 m | 100 m | 95 m | 45 m |

**Qué se reutiliza.** Con la semilla fija, M1 depende solo de la demanda y M2
de la demanda, el filtrado y el radio. El orden de ejecución (vehículos →
filtrado → física → $H$) y la última simulación en memoria hacen que en
`fisica_v1` SUMO corra **3 veces** y la línea de vista **36**, para 108 puntos.

**M3 tampoco se repite.** Cada despliegue guarda la huella de su problema
(`despliegue.clave_m3`: el CVR con $P$, Cap, $L$, MaxR y los topes). Si otra
corrida, de esta campaña o de otra, ya resolvió **exactamente** el mismo
problema, se copia su resultado y `despliegue.origen` apunta al original (en la
bitácora: *M3 idéntico ya resuelto*). Así la carga ×1 de `trafico_v1` y el
presupuesto *libre* de `presupuesto_v1` se resuelven una sola vez.
`SCN_CACHE=0` lo desactiva, igual que el almacén.

<a id="semillas"></a>
### Varias semillas

Con una semilla, toda diferencia entre puntos se debe a los factores, pero no
se sabe cuánto de cada resultado es azar del tráfico. Con `semillas: [...]` en
vez de `semilla`, la campaña se repite con cada una: **otro tráfico** (rutas de
`randomTrips.py` y azar de SUMO) sobre **la misma área y las mismas
candidatas**. El área no se vuelve a elegir: es la guardada con `scn.py mapa`.

- Cada semilla es una campaña aparte en el catálogo, `<nombre>_s<semilla>`
  (`fisica_v1_s42`, `fisica_v1_s1`...), con su huella de configuración, su
  carpeta y su reanudación; todas llevan `familia: <nombre>` en su spec. Las
  campañas de una sola semilla que ya existían (p. ej. `fisica_v1`) no se tocan.
- Con varios YAML en la misma orden, se ejecutan **semilla a semilla**: la 1.ª
  semilla de todas, luego la 2.ª... Así, si se corta a los pocos días, quedan
  semillas **completas** de cada campaña (y el reporte agregado ya sirve), y
  dentro de cada semilla `trafico_v1` va antes que `presupuesto_v1`, que copia
  de ella el M3 del nivel *libre*.
- `scn.py reporte --campana <nombre> --semillas` junta las semillas que haya:
  por punto, la media de cada métrica (las figuras de siempre), su desviación
  (`_sd`, con n − 1), cuántas semillas entran (`_n`) y el semiancho del
  intervalo de confianza del 95 % (`_ic95` = t(0,975; n − 1) · sd / √n, con la
  t de Student de una tabla: con 10 semillas, 2,262). Las figuras dibujan el
  IC como barras de error; el anillo rojo marca los puntos cortados en alguna
  semilla; las semillas sin solución útil no entran en la media. Las tablas
  `.tex` ponen *media ± IC*.

```powershell
# Las tres campañas de la tesis con 10 semillas (6 120 puntos; 42 + nueve nuevas)
.\.venv\Scripts\python.exe scn.py campana campanas\fisica_v1.yaml campanas\trafico_v1.yaml campanas\presupuesto_v1.yaml --paralelo auto
.\.venv\Scripts\python.exe scn.py reporte --campana trafico_v1 --semillas
```

**Cuánto tarda.** Medido con la semilla 42: `fisica_v1` unas 2 h 45 y
`trafico_v1` unas 7 h 45 (con `--paralelo auto`); `presupuesto_v1` se estima en
5-10 h (con MaxR el problema es más difícil). Unas 15-20 h por semilla y
**6-8 días** para las nueve nuevas, sin parar. La semilla 42 sale casi gratis:
SUMO y la línea de vista vienen del almacén, y el M3 de `trafico_v1` (y con él
el *libre* de `presupuesto_v1`) se copia de la primera tanda. El de
`fisica_v1` no: esa campaña es anterior a `clave_m3`, así que `fisica_v1_s42`
vuelve a resolver sus 108 puntos (≈ 2,6 h de CPLEX), lo que de paso comprueba
que el resultado se reproduce. `pruebas/semillas.py` verifica la validación, el
desdoble por semilla, el orden y el cálculo de medias e intervalos.

### Carga y presupuesto como factores

Dos factores opcionales, que solo entran en la clave del punto si el YAML los
usa (las claves de `fisica_v1` no cambian):

| Factor | Qué varía | Ejemplo de clave |
|---|---|---|
| `carga: [1, 2, 3, 4]` | multiplica la carga por vehículo $L$ de `fisica_base` (80 → 160, 240, 320 kb/s): solo cambia la Ec. 4 | `v5000_C_6-r80_H3_x2` |
| `presupuesto: [libre, alto, bajo]` | el número máximo de RSU (MaxR, Ec. 5); los niveles se definen en `presupuestos:` con un valor fijo o uno por demanda | `v5000_C_6-r80_H3_max60` |

```yaml
factores:
  presupuesto: [libre, alto, bajo]
presupuestos:
  alto: {2500: 60, 5000: 80}     # MaxR según la demanda
  bajo: {2500: 40, 5000: 60}
reparto_tope: [1, 4, 1]          # sin MaxR: el nivel difícil es el 2
reparto_tope_limitado: [4, 1, 1] # con MaxR: el difícil es el 1
```

**El reparto del tope cambia con MaxR.** Sin límite de RSU, el nivel 1
(cobertura) es fácil —basta encender todo— y el 2 (mínimo de antenas) es el
difícil. Con el número de RSU limitado es al revés: elegir *qué* k antenas dan
más cobertura es el problema de máxima cobertura. Medido con 5 000 vehículos,
6 Mb/s $r_{80}$, $H = 3$ y MaxR = 60: con 600 s para el nivel 1 terminó con
óptimo (395 s); con 150 s quedó cortado. Por eso cada YAML puede fijar
`reparto_tope` y `reparto_tope_limitado` (pesos de los tres niveles).

Las dos campañas que los usan, con la misma semilla y área que `fisica_v1`
(sus simulaciones salen del almacén):

| Campaña | Pregunta | Diseño | Tope |
|---|---|---|---|
| [`trafico_v1`](campanas/trafico_v1.yaml) | ¿cuánta carga hace falta para que la capacidad obligue a desplegar más RSU? | 2 demandas (2500, 5000) × 6 físicas × 3 $H$ × 2 filtrados × 4 cargas = **288** | 3 h (30 min / 2 h / 30 min) |
| [`presupuesto_v1`](campanas/presupuesto_v1.yaml) | ¿cuánta cobertura se pierde con menos RSU, y cuánto la compensa el multisalto? | 2 × 6 × 3 × 2 × 3 presupuestos = **216** | 3 h (2 h / 30 min / 30 min con MaxR) |

Con 1 000 vehículos la capacidad no llega a limitar ni con ×4 (uso medio ≤ 3,6 %
con ×1 en `fisica_v1`), por eso no entran.

<a id="paralelo"></a>
### En paralelo: todos los núcleos sin agotar la RAM

```powershell
.\.venv\Scripts\python.exe scn.py campana campanas\trafico_v1.yaml --paralelo auto
```

Con `--paralelo N` el proceso principal prepara los puntos uno a uno
(simulación del almacén + CVR, segundos) y reparte las **optimizaciones** entre
N procesos, cada uno con `núcleos / N` hilos de CPLEX. Varias optimizaciones con
4 hilos rinden más que una con 16: el árbol de ramificación no escala bien con
tantos hilos, y la parte secuencial de cada solve deja núcleos parados. En
paralelo los puntos van **de más pesado a más ligero**, para que los largos no
queden al final con el resto de núcleos sin trabajo.

**La RAM manda.** Un M3 ocupa ≈ 0,3 GB + 1 GB por cada 100 000 tuplas del CVR
(medido: 3,1 GB de pico con las 301 090 de `v5000_A_3-r80_H3`). Un punto solo
se lanza si su estimación cabe en la RAM libre del arranque (menos 2,5 GB para
el proceso principal y el sistema) y en la libre en ese momento; los pesados
esperan turno. Además cada CPLEX tiene `workmem` = 1 GB y, al superarlo, guarda
los nodos del árbol **comprimidos en disco** (`mip.strategy.file = 3`) en vez de
crecer en RAM: así no se repite lo de la prueba de 50 000 vehículos, que se
quedó 8 h paginando. `auto` usa un proceso por cada 4 núcleos lógicos, sin pasar
de lo que cabe en la RAM libre: **cierra el navegador y lo que no uses antes de
lanzar**. Sin `--paralelo` (o con 1), CPLEX usa todos los núcleos y casi toda la
RAM libre como `workmem`.

Solo el proceso principal escribe en el catálogo. Con Ctrl+C se cierran los
procesos de CPLEX al momento, y los puntos que estaban en curso quedan
*fallidos — interrumpida durante M3* y se repiten al relanzar (comprobado con
dos M3 pesados en marcha).

**Reanudar.** Cada punto tiene una clave (`v5000_C_6-r90_H3`); los que ya
están hechos (con despliegue) se saltan. Un punto que falla se anota y la
campaña sigue. Todo queda también en `datos/corridas/<campaña>/campana.log`.

**Qué pasa cuando algo sale mal** (comprobado caso por caso):

| Situación | Qué hace la campaña |
|---|---|
| **Ctrl+C mientras CPLEX resuelve** | CPLEX captura la señal y aborta el solve *sin* `KeyboardInterrupt`; se detecta (estado `stopped` antes de agotar los topes), la corrida queda *fallida — interrumpida*, la campaña se detiene y ese punto se repite al relanzar |
| M3 sin solución (memoria, error de CPLEX) | corrida *fallida*, la campaña sigue con el siguiente; se reintenta al relanzar |
| M3 cortado por tiempo | se guarda la mejor solución hallada, marcada como cortada (círculo rojo en las figuras, † en la tabla) |
| Nivel 1 cortado sin cobertura | no es un despliegue (0 RSU, 0 %): se trata como fallo, no como resultado |
| Editar el YAML a mitad de campaña (área, semilla, duración, muestreo, `fisica_base`, filtrados) | se **niega** a continuar: cada punto guarda una huella de esa configuración fija y mezclar dos configuraciones daría figuras engañosas. Para la configuración nueva, usar otro `nombre` |
| `correr --campana X` sobre una campaña de YAML | se niega: descuadraría su reporte |
| Clic dentro de la ventana de PowerShell (título "Seleccionar ...") | la consola de Windows entra en modo selección y congela el programa al escribir la siguiente línea, hasta pulsar **Esc** (los CPLEX en curso terminan y esperan). `campana` desactiva ese modo al arrancar; en una ventana lanzada antes: clic derecho en la barra de título > Propiedades > quitar *Modo de edición rápida* |
| La laptop entra en espera (espera moderna) por inactividad | en esta laptop la espera llega al **apagarse la pantalla** (a los 5 min sin uso), aunque "Suspender" esté en *Nunca*: del 30-oct al 3-nov estuvo 67 h en espera y la última vez no despertó (pantalla negra, reinicio forzado). CPLEX siguió trabajando (mismos puntos cortados que la semilla 42), pero el riesgo es colgarse. Por eso `campana` pide a Windows mantener **la pantalla encendida** mientras corre (bajar el brillo); no pulsar el botón de encendido, que también la manda a espera |

Antes de esto, los dos primeros casos se guardaban como un punto *hecho* con
0 RSU y no se repetían nunca (hay una corrida web así en el catálogo:
`417f66d32b5b`).

**Límites de trabajo.** Máximo **5 000 vehículos** (por encima, M2/M3 colapsan
en esta máquina). M3 con **tope de 1 h 30** por punto (indicación del tutor;
`trafico_v1` y `presupuesto_v1` usan 3 h, porque en `fisica_v1` los dos puntos
cortados quedaron lejos del óptimo): si no termina, se guarda la mejor solución
hallada, marcada como cortada.

> ⚠️ **El tope del lexicográfico es POR NIVEL.** Con un tope *global*, CPLEX
> multi-objetivo que no termina devuelve **ninguna** solución
> (`multi-objective stopped`): pasó en una corrida real de 5 000 vehículos
> (`417f66d32b5b`: 1 589 s de solver y 0 RSU). Ahora el tope total se reparte
> 15 / 60 / 15 min entre los niveles (`FRACCIONES_NIVEL` en `optimizar_rsu.py`):
> el nivel 1 (cobertura) es fácil, el 2 (nº de RSU, un cubrimiento de
> conjuntos) es el difícil, y el 3 trabaja con las antenas ya acotadas. Al
> agotarse un nivel, CPLEX sigue con lo mejor que tenía y al final devuelve
> `multi-objective non-optimal`. Medido en una instancia de 110 k tuplas con
> tope de 12 s: misma cobertura y mismas antenas que el óptimo, saltos algo
> peores. La web usa el mismo reparto.

### El análisis: figuras en Python, CSV para explorar

`scn.py reporte` genera desde el catálogo, con un comando, todas las figuras;
cada una responde una pregunta: RSU y cobertura frente a la física (por demanda
y $H$), valor del multisalto frente a $H$ y frente a la demanda, filtrado C
frente a A (la pregunta del revisor), tiempo del solver frente a
$|\mathrm{CVR}|$, mapa de calor de RSU y `tabla_resumen.tex`. Con el factor
`carga`: RSU, cobertura, uso medio de la capacidad y multisalto frente a la
carga (`tabla_carga.tex`); con `presupuesto`: la curva cobertura–RSU, el
multisalto frente al presupuesto y cuánto compensa $H$ la falta de antenas
(`tabla_presupuesto.tex`). En esas campañas, las figuras de siempre usan el
nivel base (carga ×1, presupuesto libre). El uso medio de la capacidad sale del
nivel 3 del lexicográfico: $\sum R_{ts} P[h] L$ es justo la carga que reciben
las RSU encendidas en todos los instantes (el lado izquierdo de la Ec. 4). Se generan en Python —y no en Power BI— porque así son
**reproducibles** (se regeneran al cambiar los datos), salen en PDF vectorial
para LaTeX y el script va en git. Para explorar a mano, el CSV de
`scn.py exportar` abre con doble clic en Excel en español y en Power BI
(configuración regional *Español*). Solo entran en las figuras los puntos que
define el YAML de la campaña, y `reporte` avisa si detecta mezcla de áreas,
semillas o configuraciones. Con `--semillas`, las figuras son las mismas con la
media de las semillas y barras del IC 95 % ([Varias semillas](#semillas)), y
avisa si no todos los puntos tienen las mismas semillas.

### El catálogo (`datos/catalogo.sqlite`)

**Principio: el disco es la verdad; la base de datos es un índice.** Los
artefactos pesados viven en las carpetas; el catálogo guarda rutas, hashes,
parámetros y métricas, y se puede borrar y reconstruir desde los `manifest.json`.

Es SQLite porque viene con Python (nada que instalar), el acceso es de un solo
proceso y el volumen es una fila por corrida. El SQL es estándar a propósito:
migrar a PostgreSQL —si algún día escriben varias máquinas— sería cambiar la
conexión. Está en modo WAL, así que se puede **leer mientras una campaña escribe**.

Las tablas siguen las etapas del flujo, y **cada una se identifica por sus
entradas, no por su nombre**:

| Tabla | Identidad | Consecuencia |
|---|---|---|
| `area` | bbox + hash del conjunto de `.osm` | dos corridas del mismo sitio son la misma área aunque se etiqueten distinto |
| `red` | área + opciones de `netconvert` + hash del **contenido** del `.net.xml` | el hash ignora la cabecera (fecha, rutas): dos redes iguales hechas en días distintos coinciden |
| `movilidad` | red + vehículos + duración + **semilla** + muestreo | otra semilla es otra movilidad; otro filtrado, **no** |
| `candidatas` | red + `gmin` + `rho` | no depende de la movilidad: distintas demandas comparten candidatas |
| `corrida` | movilidad + candidatas + radio + H | una fila por ejecución, con `campana`, `estado` y `carpeta` |
| `resultado` · `instante` | métricas agregadas (N, K, \|CVR\|, Q_reach, M_h) y una fila por instante | responden "cómo evoluciona la cobertura" sin abrir un `.dat` |
| `despliegue` | lo que devolvió CPLEX (RSU, objetivo, cobertura, tiempo, estado, topes por nivel) | web, y CLI con `--optimizar` o en campañas |
| `campana` | la especificación YAML de cada campaña | `corrida.punto` y `corrida.factores` (JSON con los niveles y la física aplicada) enlazan cada corrida con ella |
| `entorno` | Python, NumPy, SUMO, commit, hilos | sin esto un resultado de hace meses no se puede interpretar |

Esto se comprobó a la primera de cambio: la versión inicial identificaba `area`
por el nombre y `red` por los bytes del archivo, y cuatro corridas dejaron
**3 áreas y 4 redes**. Con la identidad por contenido: **1 área, 1 red,
2 movilidades**.

**Para verlo:** [DB Browser for SQLite](https://sqlitebrowser.org) → *Open
Database* → `datos\catalogo.sqlite`. Una corrida no está entera en ninguna
tabla: pega la consulta 1 de [`consultas.sql`](consultas.sql) en *Execute SQL*
(`Ctrl+Return`) y sale una fila por corrida con todo. Dos avisos: DB Browser no
se refresca solo (`F5`), y si dejas **cambios sin guardar** retiene la escritura
y `scn.py` falla con `database is locked` — *Write Changes* o ciérralo antes de
lanzar corridas.

### El almacén de etapas (`datos/cache/`)

Cada etapa es una **función pura de sus entradas**: con el mismo mapa, los
mismos parámetros y la misma semilla produce exactamente el mismo archivo
(`pruebas/determinismo.py` lo demuestra). Entonces no hay motivo para
calcularla dos veces. Antes de ejecutar una herramienta, el flujo busca la
salida por una **clave derivada de sus entradas**; si existe, la enlaza en la
carpeta de la corrida y la etapa cuesta milisegundos. Si no, la ejecuta y la
guarda.

Las claves se **encadenan**, así que nada se reutiliza por error:

| Etapa | Clave | Se invalida al cambiar… |
|---|---|---|
| `red` | versión de SUMO + hash del OSM + opciones de `netconvert` | el área, el filtro de vías, SUMO |
| `poly` | `red` | lo mismo |
| `parseo` | `red` + `poly` | lo mismo (junctions y edificios JSON) |
| `rutas` | `red` + vehículos + periodo + fin + **semilla** | la demanda o la semilla |
| `fcd` | `rutas` + duración + muestreo + semilla | lo anterior o el muestreo |
| `los` | `fcd` + conjunto de candidatas + radio + bidireccional | lo anterior, el filtrado o el radio |

Medido sobre el mismo escenario, cuatro corridas seguidas:

| Corrida | Qué se recalculó | Qué salió del almacén |
|---|---|---|
| semilla 42, 1ª vez | todo (M1 1,61 s) | — |
| semilla 42 otra vez | nada (M1 **0,27 s**) | red, poly, parseo, rutas, traza, LoS |
| `--gmin 3` | solo la LoS | red, poly, parseo, rutas, traza |
| semilla 7 | rutas, traza, LoS | red, poly, parseo |

Y lo que importa: **la web y el CLI comparten el almacén**. Un escenario
generado desde el navegador sobre un área que el CLI ya calculó no ejecuta
ninguna herramienta de SUMO. En una ciudad, cada etapa reutilizada ahorra su
coste medido en este mismo documento: `netconvert` ~57 s, `duarouter` de uno a
diez minutos según la demanda, y la LoS, que es O(V²) por instante.

**Cómo se guarda.** Con **enlaces duros** (`os.link`): una red de 500 MB no se
copia a cada carpeta, son dos nombres del mismo archivo. El riesgo es que una
herramienta *sobrescriba en sitio* el archivo de la corrida y corrompa el del
almacén; por eso, antes de ejecutar cualquier herramienta, se rompe el enlace
(`almacen.desvincular`) y la herramienta crea un archivo nuevo. `meta.json` se
escribe **al final**: una entrada sin él está incompleta y se ignora.

| Control | Efecto |
|---|---|
| `SCN_CACHE=0` | desactiva el almacén (lo hace `pruebas/determinismo.py`: si la segunda corrida saliera de él, compararía un archivo consigo mismo) |
| `SCN_CACHE_DIR` | otra carpeta (por defecto `datos/cache/`) |
| `scn.py correr --sin-cache` | lo mismo que `SCN_CACHE=0` para una corrida |
| `scn.py estado` | cuántas entradas y MB hay por etapa |

> **Si cambias un algoritmo, sube su versión.** La clave no puede saber que el
> código cambió: `VERSION_LOS` en `flujo.py` (línea de vista) y `VERSION_CFG`
> en `simulacion_sumo.py` (lo que escribe el `.sumocfg`) forman parte de la
> clave. Si no se suben, el almacén serviría resultados del método viejo.

---

## 🔗 Módulo Multisalto — Conectividad de varios saltos

Esta sección documenta el módulo [`backend/multisalto.py`](backend/multisalto.py), que implementa el documento *"Construcción de matrices de conectividad multisalto vehículo–RCU"*. Toma las matrices de **un salto** que ya genera el proyecto (A y B) y calcula si un vehículo puede alcanzar un RSU **rebotando a través de otros vehículos**.

### ¿Qué problema resuelve?

Hasta ahora, la Matriz B solo dice si un vehículo ve **directamente** un RSU (1 salto). Pero en una VANET un vehículo puede estar fuera del alcance de todo RSU y aun así comunicarse, **usando a otros vehículos como repetidores**:

```
1 salto:   V_i ───────────────────────► R_k        (B directo)
2 saltos:  V_i ──► V_j ──────────────► R_k        (rebota en 1 vehículo)
3 saltos:  V_i ──► V_j ──► V_l ───────► R_k        (rebota en 2 vehículos)
```

El módulo responde, para **cada instante de tiempo por separado**: *¿qué vehículos alcanzan qué RSU usando como máximo H saltos, y cuáles quedan totalmente incomunicados?*

### Las fórmulas (y qué significa cada una)

| Símbolo | Nombre | Fórmula | Significado |
|---------|--------|---------|-------------|
| `β(X)` | Binarización | `β(X)=1 si X>0, si no 0` | Solo importa si existe **al menos un** camino, no cuántos |
| `Ã` | A con identidad | `Ã = A ∨ I` | Pone 1 en la diagonal; conserva conexiones al subir de saltos (**monotonía**) |
| `R_h` | Acumulada | `R₁=B`, `R_h=β(Ã·R_{h-1})` | vᵢ alcanza rₖ usando **hasta** h saltos |
| `S_h` | Primera aparición | `S₁=R₁`, `S_h=R_h − R_{h-1}` | vᵢ alcanza rₖ con un **mínimo exacto** de h saltos |
| `D_H` | Desconexión | `D_H = J − R_H` | 1 = vᵢ **no** logró conectarse con rₖ ni con H saltos |
| `d` | Vector aislados | `dᵢ=1 si fila i de R_H es todo ceros` | vᵢ no alcanza **ningún** RSU |

**¿Por qué la identidad `Ã = A ∨ I`?** Sin ella, `A·B` daría caminos de longitud *exactamente* h (se "perderían" las conexiones más cortas al multiplicar). Al poner 1 en la diagonal, un vehículo "se incluye a sí mismo" y las conexiones ya halladas se arrastran: así se garantiza `R₁ ≤ R₂ ≤ ... ≤ R_H` (acumulación real).

### Pieza clave: alinear A y B

Para poder multiplicar `Ã · B`, **ambas matrices deben usar el mismo orden de vehículos**. El módulo usa como orden canónico el de `matrices_v2v[t]["vehiculos"]` (el que ya produce el V2V) y reconstruye B sobre ese mismo orden con [`construir_matriz_B()`](backend/multisalto.py). Esto es exactamente lo que faltaba antes: la Matriz B solo existía como lista de tuplas suelta.

> **Simetría de A:** físicamente, si el vehículo i ve al j, entonces j ve al i. Por eso `analizar_timestep()` simetriza A por defecto (`forzar_simetria=True`, calcula `A = β(A ∨ Aᵀ)`). Esto repara automáticamente el caso en que la simulación se haya corrido con V2V *dirigida* (no simétrica), que rompería el multisalto.

### Funciones principales

| Función | Qué hace |
|---------|----------|
| `binarizar(X)` | Aplica β(X): convierte cualquier valor > 0 en 1 |
| `agregar_identidad(A)` | Calcula Ã = A ∨ I (1s en la diagonal) |
| `construir_matriz_A(matriz_v2v_t, forzar_simetria)` | Saca A del JSON V2V; opcionalmente la simetriza |
| `construir_matriz_B(tuplas_v2i, t, vehiculos, rsu_ids)` | Reconstruye B **alineada** al orden de A |
| `calcular_R(Ã, B, H)` | Devuelve `[R₁, …, R_H]` |
| `calcular_S(lista_R)` | Devuelve `[S₁, …, S_H]` |
| `calcular_D(R_H)` / `calcular_vector_d(R_H)` | Matriz de desconexión y vector de aislados |
| `analizar_timestep(...)` | **Pipeline completo** de un instante: A, Ã, B, R, S, D, d + resumen |
| `analizar_todos(...)` / `guardar_multisalto_json(...)` | Procesa todos los instantes y exporta a `multisalto.json` |

### Ejemplo resuelto (el del documento)

Con 4 vehículos, 3 RSU y H=3:

```
A = [[0,1,0,0],     B = [[1,0,0],      (v1→r1, v2→r3, v3→r2;
     [1,0,1,0],          [0,0,1],        enlaces V2V: v1↔v2, v2↔v3;
     [0,1,0,0],          [0,1,0],        v4 sin ningún enlace)
     [0,0,0,0]]          [0,0,0]]
```

Resultado (verificado por el módulo):

```
R₃ = [[1,1,1],    S₂ = [[0,0,1],    S₃ = [[0,1,0],    D₃ = [[0,0,0],   d = [0,
      [1,1,1],          [1,1,0],          [0,0,0],          [0,0,0],        0,
      [1,1,1],          [0,0,1],          [1,0,0],          [0,0,0],        0,
      [0,0,0]]          [0,0,0]]          [0,0,0]]          [1,1,1]]        1]
```

Lectura: **v1, v2 y v3 alcanzan las 3 RSU** en ≤3 saltos (p. ej. `v1→v2→v3→r2` es un camino de 3 saltos que aparece en S₃). **v4 queda totalmente aislado** (`d₄=1`) porque no tiene ningún enlace, ni directo ni multisalto.

### Visualización en la UI

En la pestaña **"🔗 Multisalto"** (dentro de los resultados del Módulo 2) puedes:

- Elegir el **máximo de saltos H** (1–6) y el **instante de tiempo**.
- Activar/desactivar **"Forzar A simétrica"**.
- Ver una **tabla resumen por salto**: pares vehículo→RSU alcanzables acumulados, vehículos con al menos un RSU, y pares nuevos en cada salto.
- Seleccionar y ver cualquier matriz `R_h`, `S_h` o `D_H` como tabla.
- Ver el **vector `d`** con los vehículos totalmente desconectados (también resaltados con una alerta).

---

<a id="fisica"></a>

## 📡 Capa física — de dónde salen el radio, P[h] y la capacidad (IEEE 802.11p)

Tres números del modelo estaban puestos a ojo: el **radio de la OBU** (300 m),
la **penalización por salto** (`P[h] = h`) y la **capacidad de una RSU**
(`Cap = 300`, `L = 10`, sin unidades). El tutor entregó dos notas técnicas y un
programa (carpeta [`Luis Urquiza/`](Luis%20Urquiza/)) que los derivan de un
modelo físico publicado y reproducible con semilla. `backend/capa_fisica.py`
hace de puente, y el panel **Capa física** de la interfaz permite elegir la
configuración y aplicarla a M2 y M3 **sin perder los valores clásicos**.

### Qué calcula el programa del tutor

`channel_functions.py` simula, por Monte Carlo, si **un paquete llega** a una
distancia dada. Cada paquete pasa por esta cadena:

| Paso | Qué hace | Función |
|---|---|---|
| 1 | Potencia media recibida con el modelo *Empirical Inexpensive* de Sommer (exponente 2,2, 5,89 GHz, 24 dBm) | `empirical_inexpensive_power_dbm` |
| 2 | Fading Rician (K = 10) sobre esa potencia, normalizado para conservar la media | `rician_power_w` |
| 3 | Un interferente co-canal a distancia U(10, 2000) m, con su propio fading | ídem |
| 4 | SINR = P_señal / (P_interferencia + kTB) | `thermal_noise_w` |
| 5 | Umbral de sensibilidad del receptor por tasa PHY (−85 dBm a 3 Mb/s … −68 a 27) | `RX_SENSITIVITY_DBM` |
| 6 | PER con el ajuste de dos matrices de Reinoso-Chisaguano (modelo 7, ns-3) | `per_reinoso_model7` |
| 7 | Éxito ⟺ potencia ≥ sensibilidad **y** U(0,1) > PER | `simulate_packet_batch` |

Repetido 5000 veces en cada distancia de 10 a 1000 m (`simulate_distance_curve`)
da la curva P(éxito) vs distancia, y de ella los radios (`reliable_radius`):

| | 6 Mb/s, 1000 B, con interferente | solo ruido |
|---|---|---|
| **r80** — mayor distancia con P ≥ 0,8 | **200 m** | 355 m |
| **r90** — mayor distancia con P ≥ 0,9 | **100 m** | 315 m |
| radio por sensibilidad (potencia media) | 440 m | 440 m |

Y el **experimento multisalto** (`simulate_multihop`): rutas de H saltos con
longitudes U(10, r_q); la ruta tiene éxito solo si **todos** los saltos lo
tienen. Si un fallo obliga a retransmitir desde el origen, el número esperado de
intentos es Γ_H = 1 / P(ruta):

| H | 1 | 2 | 3 | 4 | 5 | 6 |
|---|---|---|---|---|---|---|
| Γ_H con r90 (6 Mb/s, 1000 B) | 1,054 | 1,107 | 1,169 | 1,217 | 1,286 | 1,373 |
| Γ_H con r80 | 1,114 | 1,233 | 1,385 | 1,519 | 1,725 | 1,940 |

La segunda nota da la **capacidad unicast** de una RSU tras los overheads
MAC (preámbulo, SIGNAL, cabecera, ACK, SIFS, AIFS): `C₀(R, L) = 8L / T₀`, y la
capacidad agregada de planificación **α·C₀** con α ≈ 0,80 (contienda
moderada). A 6 Mb/s y 1000 B: C₀ = 4,92 Mb/s → α·C₀ = 3,94 Mb/s.
`capa_fisica.capacidad` la implementa y `pruebas/capa_fisica.py` la
verifica contra las **32 cifras** de sus tablas.

**Cómo correr su programa tal cual** (desde su carpeta; usa `numpy`, `pandas`
y `matplotlib`, que ya están en el `.venv`):

```powershell
cd "Luis Urquiza"
..\.venv\Scripts\python.exe run_experiments.py --no-show --output-dir results
```

Deja `results/` con `distance_curves.csv`, `range_summary.csv`,
`multihop_results.csv`, `parameters.json` y las figuras. Comprobado en esta
máquina: reproduce sus CSV **exactamente** (las únicas diferencias son de
10⁻¹⁴ en el último dígito de un float, y los finales de línea).

### Cómo se conecta con el flujo

| Del tutor | A tu modelo | Dónde |
|---|---|---|
| r80 / r90 | `radio_obu` de M2 (línea de vista V2I y V2V) | slider *Radio OBU*; `SimReq.radio_obu` (mínimo 10 m) |
| Γ_1 … Γ_H | `P[1..H]` del `.dat` (`penalizaciones` en `construir_datos_opl`) | `OptReq.penalizaciones` |
| α·C₀ y la carga por vehículo | `Cap[r]` y `L[s][v]`, **en la misma unidad (kb/s)** | `OptReq.cap_kbps`, `OptReq.carga_kbps` |

`backend/capa_fisica.py` **importa `channel_functions.py` por ruta, sin
copiarlo ni tocarlo**: lo que corre es el archivo que él entregó. Cuando la
configuración pedida coincide con su experimento (semilla 20260914, 5000
muestras) lee sus CSV oficiales; si se pide otra semilla u otro número de
muestras, recalcula en vivo con su mismo código. Lo que se aplicó queda
anotado en el `manifest.json` de la corrida (`fisica_radio`,
`fisica_modelo`, `parametros_fisicos`) y en la consola del backend.

**Lo que cambia, medido** sobre la misma área de prueba y la misma semilla:

| | Radio | P[h] | RSU desplegadas | Cobertura |
|---|---|---|---|---|
| Valores clásicos | 300 m | 1, 2, 3 | **5** | **98,85 %** |
| Capa física (6 Mb/s, 1000 B, r90) | 100 m | Γ_h = 1,05 / 1,11 / 1,17 | **17** | **81,61 %** |

Con un radio justificado, el mismo mapa necesita más del triple de antenas y
aun así deja un 18 % sin servicio. Es el tipo de tabla "antes / después" que
convierte los parámetros en una decisión defendible.

### Dos cosas que hay que saber al interpretar

* **Con el objetivo lexicográfico, `P[h]` solo desempata.** El primer nivel
  maximiza la cobertura y el segundo minimiza las RSU; `P[h]` entra en el
  tercero, entre despliegues que ya empatan en los dos anteriores. Γ_h
  cambiaría de lleno el resultado en la suma ponderada clásica, no aquí. `Cap`
  y `L` sí restringen (Ec. 4) en cualquiera de los dos modos.
* **La carga por vehículo (80 kb/s = 10 paquetes/s de 1000 B) es un supuesto
  nuestro**, no viene de las notas. Está pendiente de confirmar con el tutor,
  igual que si `P[h]` debe ser Γ_h o Γ_h − 1 (el panel ofrece las dos).

---

## 🧮 Exportación a la Optimización — El archivo `.dat`

Esta sección documenta [`backend/exportar_dat.py`](backend/exportar_dat.py), el **puente** entre la parte VANET del proyecto (que produce las matrices de conectividad) y la parte de **optimización de despliegue de RSU** que vive en [`optimizacion/`](optimizacion/). La optimización se resuelve con **IBM CPLEX** desde Python vía **`docplex`** (ver [Resolución con docplex/CPLEX](#resolución-con-docplexcplex-python-ya-no-oplrun) más abajo); el archivo `.dat` que genera este módulo sigue siendo útil para inspección y compatibilidad con OPL, pero ya **no** es necesario para resolver.

> ✅ **Alcance.** `exportar_dat.py` genera el archivo `.dat` y arma en memoria el dict de datos; la resolución la hace [`optimizacion/optimizar_rsu.py`](optimizacion/optimizar_rsu.py) con docplex. **Ambos están integrados en la interfaz (frontend React → `POST /api/optimize`) como el Módulo 3:** tras la simulación V2I+V2V, el botón *"Optimizar Despliegue de RSU"* construye el CVR en memoria (`exportar_dat_desde_memoria`), resuelve con `optimizar()` y dibuja las RSU seleccionadas sobre el mismo plano generado por el frontend. También se puede correr por CLI (ver más abajo).

### ¿Qué es el `.dat` y por qué se necesita?

El modelo de optimización [`optimizacion/rsu_model.mod`](optimizacion/rsu_model.mod) elige el **subconjunto mínimo de RSU candidatos** que hay que instalar para que los vehículos (en varios instantes/escenarios) alcancen alguna RSU por multisalto, penalizando los caminos largos y la desconexión. Está basado en Urquiza-Aguiar, Tripp-Barba & Aguilar-Igartua (2016), *"A Stochastic Optimization Model for the Placement of RSUs"*.

Ese modelo `.mod` describe la **lógica** (variables, objetivo, restricciones) pero no los **datos**. Los datos concretos de un escenario se pasan en un archivo `.dat` separado, en la sintaxis de OPL. Hasta ahora ese `.dat` existía solo como un **micro-ejemplo hecho a mano** ([`rsu_micro.dat`](optimizacion/rsu_micro.dat), 3 RSU / 4 vehículos / 2 escenarios). Lo que faltaba era **generar ese `.dat` automáticamente desde los datos reales de la simulación**. Eso es justo lo que hace este módulo.

### El flujo de datos completo

```
tuplas_v2v.json  (Matriz A: V2V)  ─┐
                                    ├─► multisalto (S_h) ─► CVR ─► rsu_backend.dat ─► (CPLEX)
tuplas_visibilidad.json (Matriz B) ─┘
```

1. Se leen los dos JSON que ya deja el backend en `output/`.
2. Cada **instante de tiempo** de la simulación se convierte en un **escenario `s`** de la optimización (snapshot).
3. Para cada instante se corre el **multisalto** (`backend/multisalto.py`) y se obtienen sus matrices de **primera aparición `S_h`**.
4. Cada `1` en `S_h[v][r]` produce una **tupla de conectividad `<s, h, v, r>`** (la clave `CVR` del modelo). Es decir: *en el escenario `s`, el vehículo `v` alcanza el RSU `r` con un mínimo de `h` saltos.*
5. Se escriben todos los conjuntos y parámetros que el modelo espera y se guarda el `.dat`.

Esta correspondencia "un 1 en `S_h[v][r]` → `<s,h,v,r>`" es exactamente la que pide el comentario de `rsu_model.mod`.

### Traducción de identificadores (backend → OPL)

El backend usa ids de texto (`"V0"`, `"268824778"`) pero OPL trabaja con **conjuntos de enteros**. El módulo traduce y **guarda el mapa inverso** (lo escribe como comentario en la cabecera del `.dat`) para poder interpretar la solución del solver:

| Concepto backend | Concepto OPL | Regla de traducción |
|------------------|--------------|---------------------|
| Instante `t` (p. ej. `120.0`) | Escenario `s` (`1, 2, 3, …`) | Se numeran en orden temporal |
| Vehículo `"V137"` | Vehículo `137` (∈ `V`) | Se toman los dígitos del id |
| RSU `"268824778"` | RSU `1..m` (∈ `R`) | Se numeran `1..m` sobre `sorted(rsus)` |
| — | RSU artificial `r_inf = 0` | Id reservado para "desconectado" |

### El RSU artificial `r_inf` (garantiza factibilidad)

El modelo exige que **toda la carga de cada vehículo se sirva** (restricción Ec. 2). Si un vehículo no alcanza ninguna RSU real, esa restricción sería infactible. Para evitarlo, a **cada vehículo presente en cada escenario** se le añade una tupla extra `<s, hmax, v, 0>`: la opción de "caer" en el RSU artificial `r_inf` (id 0) al salto `hmax = H+1`, con una **penalización** (`P[hmax]`, ver [Los pesos del modelo](#pesos)). Así el modelo siempre es factible y la desconexión solo se usa como último recurso.

### Los conjuntos y parámetros que escribe

| Símbolo OPL | Qué es | Cómo se genera |
|-------------|--------|----------------|
| `hmax` | Nº de saltos incl. desconexión | `H + 1` |
| `rInf` | Id del RSU artificial | `0` |
| `MaxR` | Máx. de RSU reales a desplegar | Parámetro: casilla *"Limitar nº de RSU"* de la UI o `--max-rsu` en CLI; si no se da, **default = nº de candidatos** (no ata) — ver [MaxR desde la interfaz](#maxr) |
| `R` | RSU candidatos (incluye `0`) | `{0}` ∪ RSU que aparecen en algún `CVR` |
| `S` | Escenarios | Un id por instante |
| `V` | Todos los vehículos | Unión de vehículos de todos los instantes |
| `Vs[s]` | Vehículos presentes en `s` | `matrices_v2v[t]["vehiculos"]` |
| `Cost[r]` | Costo de instalar `r` | `0` para `r_inf`; `10` cada RSU real (⇒ minimiza **cantidad**) |
| `Cap[r]` | Capacidad de `r` | `cap_real` (300) para las reales; **`r_inf` no tiene restricción de capacidad** |
| `P[1..hmax]` | Penalización por salto | `[1, 2, …, H, penal_desconexion]` |
| `L[s][v]` | Carga de tráfico | `carga_default` (10) para todos |
| `CVR` | Tuplas `<s,h,v,r>` | De las matrices `S_h` (ver arriba) + tuplas `r_inf` |

> **Solo RSU conectados (por defecto).** Los RSU que **ningún** vehículo alcanza jamás son inútiles (el modelo nunca los elegiría) y solo inflan el archivo. Por eso, por defecto, `R` incluye solo los RSU que aparecen en al menos una tupla `CVR`. Con `--todos-los-rsu` se incluyen todos los candidatos. Es una reducción **sin pérdida** para el óptimo.

### Funciones principales

| Función | Qué hace |
|---------|----------|
| `construir_datos_opl(matrices_v2v, tuplas_v2i, rsu_ids, H, …)` | Corre el multisalto en cada instante y arma en memoria **todos** los conjuntos/parámetros + `CVR` + los mapas de traducción |
| `escribir_dat(datos, dat_path)` | Vuelca esa estructura al archivo `.dat` con la **sintaxis exacta** de OPL (`#[ k:v ]#`, `{ … }`, `<s,h,v,r>`) y una cabecera con la trazabilidad |
| `exportar_dat_desde_json(output_dir, dat_path, H, …)` | **Punto de entrada:** lee `tuplas_v2v.json` + `tuplas_visibilidad.json` y escribe el `.dat` |
| `exportar_dat_desde_memoria(matrices_v2v, tuplas_v2i, rsus, dat_path, H, …)` | Igual pero desde estructuras en memoria; lo usa la API en `POST /api/optimize` (sin pasar por disco) |

### Cómo generarlo (línea de comandos)

```bash
# Lee output/tuplas_v2v.json + output/tuplas_visibilidad.json,
# calcula el multisalto y escribe optimizacion/rsu_backend.dat
python -m backend.exportar_dat

# Con parámetros:
python -m backend.exportar_dat --H 3 --max-rsu 10
python -m backend.exportar_dat --todos-los-rsu       # incluir todos los candidatos
```

| Flag | Default | Descripción |
|------|---------|-------------|
| `--output-dir` | `output/` | Carpeta con los JSON del backend |
| `--dat` | `optimizacion/rsu_backend.dat` | Ruta del `.dat` de salida |
| `--H` | `3` | Nº máximo de saltos reales (el salto de desconexión es `H+1`) |
| `--max-rsu` | sin límite | `MaxR`: nº máximo de RSU reales a desplegar |
| `--todos-los-rsu` | (off) | Incluir todos los RSU candidatos, no solo los conectados |

### Ejemplo de salida (escenario de referencia)

Lo que sigue ilustra **el formato**, con las cifras de un escenario pequeño del
Centro Histórico (31 instantes, 132 vehículos, 278 RSU candidatas con grado 4 /
radio 20 m, `H=3`, `MaxR=10`). Los números de tu `output/` serán otros; el
formato es el mismo:

```
============================================================
  .dat GENERADO CORRECTAMENTE
============================================================
  Archivo........: optimizacion/rsu_backend.dat
  Escenarios.....: 31
  Vehículos......: 132
  RSU candidatos.: 227 (de 278)      # 51 RSU nunca alcanzados → excluidos
  Saltos H.......: 3  (hmax = 4)
  Tuplas CVR.....: 1628
  MaxR...........: 10
============================================================
```

El `.dat` resultante empieza con una **cabecera de trazabilidad** (mapa `escenario → t` y `id_RSU_OPL → id_RSU_backend`) y luego los datos. Un fragmento del `CVR`:

```opl
CVR = {
  // escenario 1
  <1,1,0,18>, <1,1,0,19>, <1,1,0,20>, <1,1,0,58>, ..., <1,4,0,0>,
  // escenario 2
  <2,1,1,...>, ...
};
```

Léase `<1,1,0,18>` como *"en el escenario 1, el vehículo 0 alcanza el RSU 18 en 1 salto"*, y `<1,4,0,0>` como *"el vehículo 0 tiene la opción de quedar desconectado (r_inf) al salto 4, con penalización alta"*.

### Resolución con docplex/CPLEX (Python, ya no `oplrun`)

Antes la optimización se resolvía llamando al binario `oplrun` de IBM CPLEX Optimization Studio con el modelo OPL. **Ahora el modelo se construye y se resuelve directamente en Python con `docplex`** (IBM Decision Optimization CPLEX Modeling for Python), que usa el motor CPLEX como backend. El módulo [`optimizacion/optimizar_rsu.py`](optimizacion/optimizar_rsu.py) es la **traducción 1:1** de `rsu_model.mod`:

| Elemento OPL | Equivalente docplex |
|--------------|---------------------|
| `dvar boolean Sel[R]` | `mdl.binary_var_dict(R)` |
| `dvar float Rts[CVR] in 0..1` | `mdl.continuous_var(lb=0, ub=1)` por tupla |
| `minimize Σ Sel·Cost + Σ Rts·P[h]·L` | `mdl.minimize(...)` |
| Ec.2–5 (`forall`, `sum`, capacidad, `MaxR`) | `mdl.add_constraint(...)` |

**Ventaja:** los datos de entrada son el **mismo dict** que produce `construir_datos_opl()` — ya no hace falta pasar por el archivo `.dat` para resolver (el `.dat` se sigue generando solo para inspección/compatibilidad OPL).

**Requisitos e instalación del motor:**

```bash
pip install docplex            # capa de modelado (pura Python)
# Motor CPLEX. `pip install cplex` = edición Community (límite 1000 vars/restricciones,
# sirve para el micro-ejemplo pero NO para el problema completo).
# Para el problema real usa el motor COMPLETO de CPLEX Studio, con Python 3.7–3.10:
python "C:\Program Files\IBM\ILOG\CPLEX_Studio2211\python\setup.py" install
```

> ⚠️ **Nota de versión de Python.** El motor completo de CPLEX 22.11 soporta **Python 3.7–3.10**. Con Python 3.12/3.14 solo funciona la edición Community (vía `pip install cplex`), que resuelve el micro-ejemplo pero rechaza el problema real (1967 variables, 3132 restricciones > 1000). El código detecta ese caso y avisa con un mensaje claro (no revienta).
>
> ✅ **Recomendación (un solo entorno para todo).** Como el código exige **≥ 3.10** y el motor completo exige **≤ 3.10**, la intersección es **exactamente Python 3.10**: es la única versión que corre el backend VANET *y* el solver real en el mismo `.venv`, evitando tener dos entornos. Se comprobó que el proyecto **no usa sintaxis de 3.12+** (ni PEP 695 ni `from __future__`), así que bajar a 3.10 no rompe nada; con `requirements.txt` (cotas `>=`) pip resuelve versiones compatibles de NumPy/pandas/etc. Python 3.12 **no** sirve para unificar, porque el motor completo no llega a 3.12.
>
> ```powershell
> # Crear el entorno único del proyecto con Python 3.10 (¡desde cero, ver aviso abajo!)
> py -3.10 -m venv .venv
> .\.venv\Scripts\activate
> pip install -r requirements.txt
> ```
>
> 🛑 **No reutilices un `.venv` viejo al cambiar de versión de Python.** Si corres
> `py -3.10 -m venv .venv` *encima* de un `.venv` creado con otra versión (p. ej. 3.14),
> el intérprete cambia a 3.10 pero **se conservan los paquetes compilados para la versión
> anterior** (numpy/pandas con binarios de otra ABI). pip dirá *"already satisfied"* pero
> `import numpy` fallará. **Solución:** bórralo y recréalo limpio:
> `deactivate; Remove-Item -Recurse -Force .venv; py -3.10 -m venv .venv; .\.venv\Scripts\activate; pip install -r requirements.txt`.
>
> 🔧 **Motor completo de CPLEX sin permisos de administrador.** El instalador oficial
> `python "C:\Program Files\...\setup.py" install` falla con `error: could not create
> 'cplex.egg-info': Acceso denegado`, porque intenta escribir dentro de `C:\Program Files`.
> Dos formas de resolverlo:
> - **(A) Como Administrador:** abre PowerShell *"Ejecutar como administrador"*, activa el
>   `.venv` y corre el `setup.py install`.
> - **(B) Sin admin (recomendado):** copia el paquete a una carpeta escribible e instálalo
>   desde ahí (el `egg-info` se crea en la copia, no en `Program Files`):
>   ```powershell
>   Copy-Item "C:\Program Files\IBM\ILOG\CPLEX_Studio2211\cplex\python\3.10\x64_win64" "$env:TEMP\cplex_full" -Recurse -Force
>   pip install "$env:TEMP\cplex_full"
>   ```
>   Esto instala `cplex 22.1.1.0` (motor completo) reemplazando la edición Community.
>
> ✔️ **Verificado en este proyecto (Python 3.10.11):** tras recrear el `.venv` e instalar
> el motor completo por el método (B), el problema real resuelve a óptimo
> (`31 escenarios · 132 vehículos · 278 RSU candidatos · 1628 CVR`, objetivo 2237.0,
> *integer optimal solution*, 38 RSU desplegadas), y el micro-ejemplo sigue dando
> `{R1, R3}` = 11.0.

**Cómo ejecutarlo y demostrar que funciona:**

```bash
# 1) Auto-test de validación: resuelve el micro-ejemplo (réplica de rsu_micro.dat).
#    Debe elegir {R1, R3} con objetivo 11.0 — idéntico al OPL original.
python optimizacion/optimizar_rsu.py --micro

# 2) Caso real: genera el .dat desde output/ Y resuelve con docplex en un solo paso.
python optimizacion/optimizar_rsu.py --H 3 --max-rsu 10
```

Salida del auto-test (`--micro`):

```
  OBJETIVO = 11.0000   (estado: integer optimal solution)
  ✅ RSU a desplegar (ids OPL):     [1, 3]
     RSU a desplegar (ids backend):  ['R1', 'R3']
  Validación: esperado [1, 3], obtenido [1, 3] -> ✅ OK
```

Con datos reales, el solver devuelve los **ids de RSU del backend** a desplegar (usando el mapa inverso de la cabecera del `.dat`). Ese resultado ya está **integrado en la interfaz** (Módulo 3, vía `POST /api/optimize`): las RSU elegidas se resaltan en verde sobre el plano, con las candidatas no desplegadas en gris. En el escenario de referencia (Centro Histórico de Quito, 31 escenarios, 227 RSU candidatas, 1628 tuplas CVR) el óptimo entero es **objetivo = 2237.0 con 38 RSU desplegadas**.

---

## 📚 Scripts didácticos (para entender y explicar el proyecto)

Además de la aplicación, el proyecto incluye **4 scripts de consola** pensados para *entender* y *explicar* cómo funciona el pipeline, de lo más simple a lo más real. Todos usan las **funciones reales** del proyecto (`backend/visibilidad.py` y `backend/multisalto.py`), así que no son cálculos "de mentira".

| Script | Qué muestra | Cuándo usarlo |
|--------|-------------|---------------|
| [`mini_proyecto_vanet.py`](mini_proyecto_vanet.py) | **Todo el flujo** en miniatura: posiciones de coches + 1 edificio → línea de vista (LoS) → tuplas → Matriz A (V2V) y Matriz B (V2I) → multisalto (R, S, D, d) | Para explicar el proyecto **completo** de principio a fin |
| [`ejemplo_multisalto.py`](ejemplo_multisalto.py) | Solo la parte de **multisalto**, con A y B dadas a mano (cadena V1→V2→V3→RSU + un coche aislado) | Para entender **solo las matrices** y los saltos |
| [`explicar_multisalto.py`](explicar_multisalto.py) | El multisalto sobre un **instante real** de tu simulación (lee `output/*.json`) | Para demostrar que funciona con **datos verdaderos** |
| [`optimizacion/explicar_optimizacion.py`](optimizacion/explicar_optimizacion.py) | La **optimización** paso a paso sobre el micro-ejemplo: tuplas CVR, modelo, restricciones y por qué el solver eligió esas RSU | Para explicar **el Módulo 3** sin la complejidad del caso real |

**Cómo ejecutarlos:**

```bash
python mini_proyecto_vanet.py          # demo completa (escenario de juguete)
python ejemplo_multisalto.py           # demo del multisalto
python explicar_multisalto.py          # instante real (elige uno automáticamente)
python explicar_multisalto.py 120 3    # instante t=120 s con H=3 saltos

python optimizacion/explicar_optimizacion.py   # la optimización explicada
SIN_PAUSA=1 python optimizacion/explicar_optimizacion.py   # sin pausas entre pasos
```

> Los dos primeros (`mini_proyecto_vanet.py` y `ejemplo_multisalto.py`) son **autocontenidos**: no necesitan haber corrido la simulación. `explicar_multisalto.py` sí necesita los JSON de `output/`.

**Ejemplo de lo que imprime `mini_proyecto_vanet.py`** (escenario: V1 ve la antena, V2 la tiene tapada por un edificio, V3 está fuera de rango, V4 aislado):

```
V1 ↔ R1: dist  80.0 m  (≤ 120) ✓  y SIN edificio ✓  → ¡CONEXIÓN!
V2 ↔ R1: dist 103.1 m  (≤ 120) ✓  pero un EDIFICIO tapa ✗  → NLoS, sin conexión
...
RESULTADO FINAL:
  V1:  ✅ conectado — mínimo 1 salto(s)     (la ve directo)
  V2:  ✅ conectado — mínimo 2 salto(s)     (V2 → V1 → R1)
  V3:  ✅ conectado — mínimo 3 salto(s)     (V3 → V2 → V1 → R1)
  V4:  🚫 AISLADO
```

Puedes cambiar las posiciones (`COCHES`, `ANTENAS`, `EDIFICIOS`, `RADIO_OBU`) al inicio de `mini_proyecto_vanet.py` y volver a correr para ver cómo cambia todo el resultado.

---


---

## 🖥️ El frontend (`web/`) — documentación detallada

Frontend en **React + TypeScript + Vite**, con **react-leaflet** para el mapa. El
diseño es una **consola científica/ingeniería** (fondo claro, un acento azul
acero, verde semántico para "óptimo", datos en monoespaciada, marco tipo *plotter*).

### ¿Por qué dos procesos y por qué `uvicorn`?

El frontend (React) **no hace la ciencia**: solo dibuja y recoge parámetros. Todo
el cálculo pesado — correr SUMO, la línea de vista, el multisalto, resolver con
CPLEX — ocurre en el **backend Python**, que se expone como una **API HTTP**. Esa
API se sirve con **`uvicorn`**, el servidor que ejecuta aplicaciones FastAPI
(*ASGI*). El comando `uvicorn api.main:app` significa: *"toma el objeto `app`
(la instancia de FastAPI) definido en `api/main.py` y ponlo a escuchar peticiones"*.

Por eso hay **dos procesos** que corren a la vez:

```
Navegador ──► Vite dev server (:5173) ──proxy /api──► uvicorn/FastAPI (:8000) ──► backend + optimizacion
   React                (frontend)                          (API)                     (la ciencia)
```

En desarrollo, el servidor de Vite reenvía (*proxy*) toda ruta `/api` al backend en
el puerto 8000, así que el frontend usa rutas relativas y no hay CORS.

### Flujo de una acción (de un clic a un resultado)

Ejemplo con **"Generar escenario"**:

1. El usuario ajusta los *sliders* → se guardan en el estado `p` de React (`App.tsx`).
2. Clic en el botón → llama a la acción `generar()`.
3. `generar()` invoca `api.generate({bbox, num_vehiculos, tiempo_min})` de
   `client.ts`, que hace `POST /api/scenario/generate` con esos datos en JSON.
4. Vite proxya la petición al backend; FastAPI ejecuta OSM + SUMO + parseo y
   responde con los edificios (en lat/lon) y los conteos.
5. `generar()` guarda la respuesta en el estado (`setEdificios`, `setBounds`,
   `setKpis`); React **re-renderiza** el mapa (nuevos polígonos) y los KPIs.

Todos los botones siguen ese mismo patrón: *acción → `client.ts` → API → estado → re-render*.

### `web/src/api/client.ts` — el cliente de la API

Un único lugar para hablar con el backend. Define las **interfaces TypeScript** de
cada respuesta (para tener autocompletado y detectar errores en compilación) y un
objeto `api` con **una función por endpoint**. Todas pasan por el helper `req()`,
que hace el `fetch`, verifica el estado HTTP y lanza un error legible si falla.

| Función | Llama a | Para qué |
|---|---|---|
| `api.health()` | `GET /api/health` | Comprueba que el backend responde |
| `api.state()` | `GET /api/state` | Qué hay cargado (no se usa al arrancar; ver nota) |
| `api.buildings()` | `GET /api/scenario/buildings` | Edificios del escenario en lat/lon |
| `api.generate(body)` | `POST /api/scenario/generate` | **M1**: genera el escenario con SUMO |
| `api.filterRsu(body)` | `POST /api/rsu/filter` | Filtra las RSU candidatas |
| `api.simulate(body)` | `POST /api/simulate` | **M2**: LoS + tuplas + matrices |
| `api.timesteps()` | `GET /api/timesteps` | Instantes para la línea de tiempo |
| `api.connectivity(t)` | `GET /api/connectivity?t=` | Vehículos + enlaces de un instante |
| `api.optimize(body)` | `POST /api/optimize` | **M3**: resuelve el despliegue de RSU |
| `api.tuplesV2i/​V2v(limit)` | `GET /api/tuples/…` | Tuplas para las tablas |
| `api.multihop(t, H)` | `GET /api/multihop` | A, B, Rₕ, Sₕ, D_H, d de un instante |

### `web/src/App.tsx` — el orquestador

Es el "cerebro" de la interfaz. Contiene:

- **Estado (`useState`):** los parámetros `p` (vehículos, duración, grado, radio…),
  y los resultados (`edificios`, `candidatas`, `desplegadas`, `bounds`, `kpis`), más
  el estado de la animación (`timesteps`, `tIdx`, `frame`, `playing`) y de la UI
  (`busy`, `error`, `drawing`, `cobertura…`, `maxRsuOn`/`maxRsu`, `topeOn`/`tope`).
- **Acciones** (una por paso del pipeline). Cada una envuelve su llamada en `run()`,
  que pone el indicador *"⏳ …"*, captura errores y los muestra en un *banner*:
  - `generar()` → `api.generate` → dibuja edificios y **limpia** la línea de tiempo
    anterior (evita pedir conectividad de un escenario que ya no existe).
  - `filtrar()` → `api.filterRsu` → pinta las **RSU candidatas (rojas)**.
  - `simular()` → `api.simulate` → llena los KPIs y `cargarTimesteps()` (activa la
    línea de tiempo).
  - `optimizar()` → `api.optimize` → pinta las **RSU desplegadas (verdes)**. Envía
    `max_rsu: <número>` si la casilla *"Limitar nº de RSU (MaxR)"* está encendida,
    y `null` si no (comportamiento por defecto, sin límite efectivo); igual con
    `limite_tiempo` y la casilla *"Limitar el tiempo del solver"* (`null` = sin
    tope), y con `lexicografico` y la casilla *"Resolver por prioridades"*
    (ver [multi-objetivo lexicográfico](#lex)). Con la respuesta llena también
    los KPIs **Solver** y **Tiempo solver**
    (ver [El límite de tiempo del solver](#solver)).

Los KPIs admiten dos formas: un valor suelto (`"RSU desplegadas": 12`) o un objeto
`{ value, sub, tone }` cuando hace falta subtítulo y color — así se pintan *Solver*
(verde si el óptimo está demostrado, ámbar si se cortó por tiempo) y *Tiempo solver*.
- **Reproducción (`useEffect`):** cuando `playing` es verdadero, un `setInterval`
  avanza `tIdx` cada 700 ms y pide `api.connectivity(t)` de ese instante, guardando
  el `frame` que el mapa dibuja.
- `nuevoEscenario()`: reinicia todo el estado para empezar de cero (lo usan el botón
  *"↺ Nuevo escenario"* y *"◱ Seleccionar área"*).
- **Al arrancar** solo comprueba `api.health()`: la app abre **en blanco** para que
  el usuario dibuje el área (no rehidrata el escenario precargado del backend).

### `web/src/components/ScenarioMap.tsx` — el mapa

Envuelve el `<MapContainer>` de react-leaflet (fondo CARTO Voyager) dentro del
marco *plotter* (esquinas). Piezas:

- **`URL_TILES`** — la URL del mapa base. CARTO exige API key en sus teselas
  raster; la clave se lee de `import.meta.env.VITE_CARTO_KEY` (definida en
  `web/.env.local`, no versionado). Si no está definida, el mapa **carga igual**
  pero con la marca de agua *"API KEY REQUIRED"*.

- **`DrawRectangle`** — selección del área **por dos clics** (sin `leaflet-draw`,
  que se rompe con Leaflet moderno). Usa `useMapEvents`: el 1er clic fija una
  esquina, el movimiento del ratón previsualiza el rectángulo, el 2º clic lo cierra
  y entrega el `bbox` al `App`.
- **`FitBounds`** — encuadra el mapa al escenario (`fitBounds`) y llama a
  `invalidateSize()` tras el *layout* para que **los overlays no salgan
  desalineados** en el primer render.
- **Capas** (se dibujan según las props): edificios como una capa `GeoJSON`
  (naranja), **RSU candidatas** (círculos rojos), **RSU desplegadas** (círculos
  verdes), **cobertura** (círculos verdes discontinuos si se activa) y, por
  instante, **vehículos** (azul) con sus **enlaces V2I** (verde) y **V2V** (ámbar).

### `web/src/components/ResultsTabs.tsx` — la sección "Análisis"

Pestañas ligadas al instante activo de la línea de tiempo. Carga los datos **bajo
demanda** (solo pide a la API cuando abres la pestaña o cambia el instante):

- **Tuplas V2I / V2V** — tablas con un **filtro de texto** (por vehículo, RSU o t).
- **Matrices A/B** — usa `MatrixGrid` para pintar rejillas binarias 0/1: **A**
  (vehículo×vehículo) y **B** (vehículo×RSU, solo las alcanzadas para que no explote
  con cientos de RSU).
- **Multisalto** — resumen por salto (pares alcanzables, vehículos conectados,
  nuevos por salto) + aviso de desconectados, y un **selector** para ver las
  matrices **Rₕ / Sₕ / D_H** del instante.

### Diseño — `src/design/tokens.css` y `src/App.css`

`tokens.css` define el sistema (paleta como variables CSS, tipografías, radios).
`App.css` estila la consola (encabezado, *stepper*, paneles, marco del mapa, línea
de tiempo, tarjetas KPI, tablas y rejillas). El objetivo es que **el color
signifique algo**: azul = acento/acción, verde = óptimo/desplegado, rojo = RSU
candidata, ámbar = V2V.

---


## 📁 Archivos de Salida

> Desde la incorporación del CLI, la carpeta de cada corrida es
> `datos/corridas/<etiqueta>/` (antes `output/`). Los nombres de archivo de
> abajo no cambian; además cada carpeta lleva `manifest.json` (la corrida
> descrita) y `claves.json` (las claves de reutilización de sus etapas).

Todos los archivos se generan en la carpeta `output/`:

### Módulo 1 — Escenario VANET

| Archivo | Formato | Generado por | Contenido |
|---------|---------|-------------|-----------|
| `map.osm` | XML (OSM) | `descargar_osm.py` | La **red vial** cruda (`highway=*` + restricciones de giro) |
| `map_edificios*.osm` | XML (OSM) | `descargar_osm.py` | Los **edificios**, en uno o varios archivos según haya hecho falta trocear |
| `mapa.net.xml` | XML (SUMO) | `netconvert` | Red vial: junctions (intersecciones), edges (segmentos viales), connections (giros), traffic lights |
| `mapa.poly.xml` | XML (SUMO) | `polyconvert` | Polígonos: edificios, parques, agua, uso del suelo con coordenadas proyectadas |
| `mapa.rou.xml` | XML (SUMO) | `randomTrips.py` | Rutas vehiculares: pares origen-destino y secuencia de edges por ruta |
| `junctions_limpias.json` | JSON | `parsear_xml.py` | Solo intersecciones con `type ≠ internal ∧ type ≠ dead_end`, con coordenadas `{x, y}` |
| `edificios_limpios.json` | JSON | `parsear_xml.py` | Solo edificios, con lista de vértices `[[x₁,y₁], [x₂,y₂], ...]` |

### Módulo 2 — Simulación V2I + V2V

| Archivo | Formato | Generado por | Contenido |
|---------|---------|-------------|-----------|
| `mapa.sumocfg` | XML (SUMO) | `simulacion_sumo.py` | Configuración de la simulación: red, rutas, tiempos, salidas FCD |
| `fcd.xml` | XML (SUMO) | `sumo` (simulador) | Floating Car Data: posición (x, y), velocidad y ángulo de cada vehículo en cada timestep |
| `tuplas_visibilidad.json` | JSON | `visibilidad.py` | Matriz B de tuplas `<t, V, RSU>` con LoS confirmado, estadísticas por RSU |
| `tuplas_v2v.json` | JSON | `visibilidad.py` | Matriz A de tuplas `<t, Vi, Vj>` con LoS confirmado, matrices A por timestep, estadísticas V2V |
| `multisalto.json` | JSON | `multisalto.py` | (Opcional) `R_H`, `D_H` y vector `d` por instante + resumen por salto. Se genera al exportar el análisis multisalto |

### Optimización (carpeta `optimizacion/`)

| Archivo | Formato | Generado por | Contenido |
|---------|---------|-------------|-----------|
| `rsu_backend.dat` | DAT (OPL) | `exportar_dat.py` | Datos para CPLEX generados desde el backend: conjuntos `R/S/V`, parámetros `Cost/Cap/P/L`, y tuplas `CVR = <s,h,v,r>` derivadas de las matrices `S_h` |

---


---

## 💡 Consideraciones Técnicas

### Sistema de coordenadas (proyección exacta)

SUMO trabaja en **metros** (x, y). Para dibujar edificios y RSU sobre el mapa hay
que volver a **lat/lon**. La conversión (`backend/parsear_xml.py::convertir_xy_a_lonlat`)
usa la **proyección real de SUMO** (UTM, vía `pyproj`) leída del `.net.xml`
(`projParameter` + `netOffset`):

```
xy_sumo = proj(lon, lat) + netOffset   ⇒   lon, lat = proj⁻¹(xy_sumo − netOffset)
```

Antes se hacía por **interpolación lineal** entre `convBoundary` y `origBoundary`,
pero `netconvert` **recorta** la red (su `convBoundary` deja de coincidir con el
`origBoundary` de la descarga), lo que desplazaba los polígonos ~178 m. La
proyección real elimina ese error (fallback lineal si faltara `pyproj`).

### CPLEX y Python 3.10

El motor **completo** de CPLEX (sin el límite de 1000 variables de la edición
community) sólo soporta **Python 3.7–3.10**, y el backend necesita **≥ 3.10** →
**3.10** es la única versión que corre ambas cosas. La licencia académica de IBM
da el motor completo gratis.

### El escenario en `datos/corridas/`

`datos/` **no se versiona** (ver [Estructura del proyecto](#-estructura-del-proyecto)):
son artefactos generados. Tras clonar el repositorio la carpeta no existe, y la
app arranca **en blanco** — que es su comportamiento normal.

Para crear un escenario: dibuja un área en el mapa y pulsa
**Generar → Filtrar → Simular → Optimizar**. La API crea la carpeta sola.

Al arrancar, la API **retoma la última carpeta de la web** (`datos/web_ultima.txt`)
con los parámetros reales que guarda su `manifest.json` —vehículos, duración,
semilla, grado, radio— y se puede seguir desde donde se dejó, incluso pulsar
*Optimizar* directamente tras un reinicio. Si no hay ninguna, mira si queda un
`output/` de versiones anteriores.

### Limitaciones y trabajo futuro

- Un escenario a la vez en memoria (herramienta de un usuario).
- Los tiempos del cronómetro se imprimen **solo en la consola** del backend y
  viven en la memoria del proceso: reiniciar `uvicorn` borra la sesión de medición.
- **La optimización no escala a ciudades enteras.** El coste crece de forma
  combinatoria con el nº de RSU candidatas por la simetría entre ellas: con 3 244
  candidatas y `MaxR` libre, una corrida tardó más de una hora. El mando efectivo
  es filtrar más (grado mínimo y radio de clúster), no esperar.
- **El mapa dibuja un muestreo de edificios** (`MAX_EDIFICIOS_MAPA`), porque
  Leaflet no puede con ~190 000 polígonos. El cálculo sí usa todos.
- **`duarouter` es lo que domina M1 con muchos vehículos**: un camino mínimo por
  vehículo sobre toda la red. Se paraleliza y usa A\*, pero sigue creciendo con
  el número de vehículos; los *presets* del panel M1 existen para no pedir más
  carga de la que el escenario puede digerir.
- **La descarga depende de instancias públicas de Overpass**, que se saturan a
  diario. Se reintenta en varios servidores, pero para trabajo intensivo con
  áreas grandes conviene un extracto local (p. ej. de Geofabrik).
- Extensiones pendientes: integración con NS-3 para simular protocolos VANET;
  cortes de simetría para el solver; y acelerar el cálculo de línea de vista y
  las herramientas de SUMO, que son las dos etapas que dominan el tiempo total
  en áreas grandes (40 % y 38 % respectivamente).

---

## 📝 Licencia

Trabajo de Integración Curricular — Escuela Politécnica Nacional.
