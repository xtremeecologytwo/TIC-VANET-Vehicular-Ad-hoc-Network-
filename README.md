# 🛰️ VANET Scenario Generator — Módulo 1 & 2

**Trabajo de Integración Curricular — Redes Vehiculares Ad-hoc (VANETs)**

Aplicación web que automatiza la generación de escenarios de simulación para redes vehiculares (VANETs). Permite seleccionar un área geográfica real desde un mapa interactivo, descargar la topología vial desde OpenStreetMap, procesarla con las herramientas CLI de SUMO, y **simular la conectividad V2I (Vehicle-to-Infrastructure) y V2V (Vehicle-to-Vehicle)** con detección de línea de vista directa (Line of Sight — LoS) considerando edificios como obstrucciones. Las conexiones se generan considerando **únicamente la cobertura del OBU (On Board Unit)** de los vehículos. Genera:
- **Tuplas `<t, V, RSU>`** — Conectividad V2I (Matriz B: vehículo–RSU)
- **Tuplas `<t, Vi, Vj>`** — Conectividad V2V (Matriz A: vehículo–vehículo)

---

## 📑 Tabla de Contenidos

- [Arquitectura del Proyecto](#-arquitectura-del-proyecto)
- [Flujo de Trabajo Completo](#-flujo-de-trabajo-completo)
- [Tecnologías y Librerías](#-tecnologías-y-librerías)
- [Requisitos Previos](#-requisitos-previos)
- [Instalación y Ejecución](#-instalación-y-ejecución)
- [Estructura de Archivos Detallada](#-estructura-de-archivos-detallada)
- [Backend — Documentación Detallada](#-backend--documentación-detallada)
- [**Filtrado Inteligente para RSU Placement**](#-filtrado-inteligente-para-rsu-placement)
- [**Módulo 2 — Simulación V2I y Tuplas de Visibilidad**](#-módulo-2--simulación-v2i-y-tuplas-de-visibilidad)
- [**Módulo V2V — Conectividad Vehículo-Vehículo**](#-módulo-v2v--conectividad-vehículo-vehículo)
- [**Matrices de Conectividad**](#-matrices-de-conectividad)
- [**Módulo Multisalto — Conectividad de varios saltos**](#-módulo-multisalto--conectividad-de-varios-saltos)
- [**Exportación a la Optimización — El archivo `.dat`**](#-exportación-a-la-optimización--el-archivo-dat)
- [**Scripts didácticos**](#-scripts-didácticos-para-entender-y-explicar-el-proyecto)
- [Frontend — Documentación Detallada](#-frontend--documentación-detallada)
- [Orquestador Principal (app.py)](#-orquestador-principal-apppy)
- [Guía de Experimentación](#-guía-de-experimentación)
- [Archivos de Salida](#-archivos-de-salida)
- [Consideraciones Técnicas](#-consideraciones-técnicas)

---

## 🏗️ Arquitectura del Proyecto

El proyecto sigue una arquitectura **MVC simplificada** con separación clara entre frontend y backend:

```
┌──────────────────────────────────────────────────────────────────┐
│                        app.py (Orquestador)                      │
│  Coordina Módulo 1 (Escenario), Módulo 2 (V2I/V2V) y Módulo 3    │
│              (Optimización del despliegue de RSU)                 │
├──────────────────────────┬───────────────────────────────────────┤
│     📊 FRONTEND          │              ⚙️ BACKEND               │
│                          │                                       │
│  frontend/               │  backend/                             │
│  ├── __init__.py         │  ├── __init__.py                      │
│  ├── mapa.py             │  ├── descargar_osm.py                 │
│  │   ├── crear_mapa()    │  │   ├── validar_coordenadas()        │
│  │   ├── extraer_bbox()  │  │   └── descargar_mapa_osm()         │
│  │   ├── mapa_resultados │  ├── sumo_pipeline.py                 │
│  │   └── mapa_conectiv.  │  │   ├── _buscar_random_trips()       │
│  └── estilos.py          │  │   └── ejecutar_pipeline_sumo()     │
│      ├── inyectar_css()  │  ├── parsear_xml.py                   │
│      ├── renderizar_*()  │  │   ├── parsear_junctions()          │
│      └── COLORES{}       │  │   ├── parsear_edificios()           │
│                          │  │   ├── obtener_proyeccion()          │
│                          │  │   ├── convertir_xy_a_lonlat()       │
│                          │  │   ├── calcular_grado_junctions()    │
│                          │  │   └── filtrar_junctions_rsu()       │
│                          │  ├── simulacion_sumo.py           🆕  │
│                          │  │   ├── generar_sumocfg()             │
│                          │  │   ├── ejecutar_simulacion_sumo()    │
│                          │  │   └── parsear_fcd()                 │
│                          │  ├── visibilidad.py               🆕  │
│                          │  │   ├── tiene_linea_de_vista()        │
│                          │  │   ├── generar_tuplas_visibilidad()  │
│                          │  │   ├── guardar_tuplas_json()         │
│                          │  │   ├── generar_tuplas_v2v()      🆕  │
│                          │  │   └── guardar_tuplas_v2v_json() 🆕  │
│                          │  ├── multisalto.py               🆕🆕 │
│                          │  │   ├── agregar_identidad() (Ã=A∨I)   │
│                          │  │   ├── construir_matriz_A/B()        │
│                          │  │   ├── calcular_R/S/D()              │
│                          │  │   ├── calcular_vector_d()           │
│                          │  │   └── analizar_timestep()           │
│                          │  └── exportar_dat.py             🆕🆕 │
│                          │      ├── construir_datos_opl()         │
│                          │      ├── escribir_dat() (sintaxis OPL) │
│                          │      └── exportar_dat_desde_json()     │
└──────────────────────────┴───────────────────────────────────────┘
                                    │
                                    ▼
                 📁 output/  +  📁 optimizacion/ (archivos generados)
```

---

## 🔄 Flujo de Trabajo Completo

El pipeline se ejecuta de forma secuencial cuando el usuario presiona "Generar Escenario":

```
┌─────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│  1. SELECCIÓN    │     │  2. DESCARGA     │     │  3. NETCONVERT   │
│  Bounding Box    │────▶│  API OSM         │────▶│  .osm → .net.xml │
│  (mapa Folium)   │     │  (requests)      │     │  (red vial)      │
└─────────────────┘     └──────────────────┘     └────────┬─────────┘
                                                          │
┌─────────────────┐     ┌──────────────────┐     ┌────────▼─────────┐
│  7. FILTRADO RSU │     │  5. PARSEO       │     │  4. POLYCONVERT  │
│  Grado + Cluster │◀────│  XML → JSON      │◀────│  .osm → .poly.xml│
│  (candidatos)    │     │  (ElementTree)   │     │  (edificios)     │
└────────┬────────┘     └──────────────────┘     └──────────────────┘
         │                    │
         ▼              ┌─────┴──────────┐
┌─────────────────┐     │  randomTrips.py │
│  8. VISUALIZAR   │     │  .net.xml →     │
│  Mapa Folium     │     │  .rou.xml       │
│  (RSU + edificios)│    └────────────────┘
└─────────────────┘
```

### Descripción paso a paso:

| Paso | Herramienta | Entrada | Salida | Descripción |
|------|-------------|---------|--------|-------------|
| 1 | Folium + Draw | Interacción usuario | Bounding Box (4 coordenadas) | El usuario dibuja un rectángulo sobre el mapa |
| 2 | API OSM via `requests` | `min_lon, min_lat, max_lon, max_lat` | `map.osm` (XML) | Descarga los datos geográficos crudos de OpenStreetMap |
| 3 | `netconvert` (SUMO CLI) | `map.osm` | `mapa.net.xml` | Convierte la topología OSM en una red vial SUMO con nodos, aristas y junctions |
| 4 | `polyconvert` (SUMO CLI) | `map.osm` + `mapa.net.xml` | `mapa.poly.xml` | Extrae los polígonos de edificios, parques, etc. del archivo OSM |
| 5 | `randomTrips.py` (SUMO) | `mapa.net.xml` | `mapa.rou.xml` | Genera rutas vehiculares aleatorias usando la red vial generada |
| 6 | `xml.etree.ElementTree` | `mapa.net.xml` + `mapa.poly.xml` | `junctions_limpias.json` + `edificios_limpios.json` | Parsea los XML y extrae solo los datos matemáticos útiles |
| 7 | `filtrar_junctions_rsu()` | `junctions_limpias.json` + `mapa.net.xml` | Junctions filtradas (en memoria) | **Filtra por grado de conectividad y clustering espacial** para determinar puntos candidatos para RSU |
| 8 | Folium (CircleMarker + Polygon) | Junctions filtradas + edificios + proyección | Mapa visual | Muestra RSU candidatos (círculos rojos) y edificios (polígonos naranjas) |

---

## 🧰 Tecnologías y Librerías

### Librerías de Python (Frontend)

| Librería | Versión | Propósito | Uso en el proyecto |
|----------|---------|-----------|-------------------|
| **`streamlit`** | ≥1.20.0 | Framework web para aplicaciones de datos en Python | Motor principal de la interfaz: renderiza componentes, gestiona estado de sesión (`.session_state`), layout responsive con `st.columns`, y ejecuta reruns reactivos |
| **`folium`** | ≥0.14.0 | Generador de mapas interactivos Leaflet.js en Python | Crea mapas con tiles de OpenStreetMap, capas alternativas (CARTO), herramientas de dibujo (`Draw`), minimapa (`MiniMap`), marcadores circulares (`CircleMarker`) y polígonos (`Polygon`) |
| **`streamlit-folium`** | ≥0.11.0 | Puente bidireccional entre Streamlit y Folium | Renderiza el mapa Folium como componente Streamlit (`st_folium`) y captura eventos del usuario (dibujos, clics) devolviendo los datos como diccionario Python |

### Librerías de Python (Backend)

| Librería | Versión | Propósito | Uso en el proyecto |
|----------|---------|-----------|-------------------|
| **`requests`** | ≥2.28.0 | Cliente HTTP para Python | Realiza solicitudes GET a la API REST de OpenStreetMap (`api.openstreetmap.org/api/0.6/map`) con timeout de 120s y manejo de códigos de error HTTP (400, 509) |
| **`subprocess`** | stdlib | Ejecución de procesos del sistema | Invoca las herramientas CLI de SUMO (`netconvert`, `polyconvert`, `randomTrips.py`) como subprocesos con captura de stdout/stderr, timeout y manejo de errores |
| **`xml.etree.ElementTree`** | stdlib | Parser XML estándar de Python | Parsea los archivos XML generados por SUMO, navega el árbol DOM con `findall()`, y extrae atributos de los elementos `<junction>`, `<poly>` y `<location>` |
| **`json`** | stdlib | Serialización JSON | Escribe los datos extraídos en archivos `.json` formateados con indentación para inspección humana |
| **`os`** | stdlib | Operaciones del sistema de archivos | Gestión de rutas (`os.path.join`), creación de directorios (`os.makedirs`), verificación de archivos (`os.path.isfile`, `os.path.getsize`) y variables de entorno (`os.environ.get`) |
| **`sys`** | stdlib | Información del sistema | Obtiene la ruta del intérprete Python activo (`sys.executable`) para ejecutar `randomTrips.py` con el mismo entorno virtual |
| **`pandas`** | ≥1.5.0 | Manipulación de datos tabulares | Utilizado para la visualización de las matrices A, B y de multisalto (R, S, D) como DataFrames interactivos en Streamlit |
| **`numpy`** | ≥1.23.0 | Álgebra lineal y matrices | Motor del **módulo de multisalto**: producto de matrices (`@`), binarización, OR con la identidad y operaciones vectorizadas para calcular R_h, S_h, D_H y el vector `d` |

### Herramientas Externas (SUMO)

| Herramienta | Tipo | Descripción |
|-------------|------|-------------|
| **`netconvert`** | Ejecutable SUMO | Convierte datos de red de diferentes fuentes (OSM, Shapefile) al formato interno de SUMO (`.net.xml`). Aplica optimizaciones: `--geometry.remove` (simplifica geometrías), `--edges.join` (fusiona aristas redundantes), `--ramps.guess` (detecta rampas), `--remove-edges.isolated` (elimina aristas aisladas) |
| **`polyconvert`** | Ejecutable SUMO | Extrae polígonos y puntos de interés (POIs) del archivo OSM y los proyecta sobre la red vial. Genera `mapa.poly.xml` con los edificios, parques y otros elementos geográficos |
| **`randomTrips.py`** | Script Python SUMO | Genera pares origen-destino aleatorios sobre la red vial y calcula rutas usando el algoritmo de Dijkstra. El parámetro `-e` indica el tiempo final de simulación |

### CSS y Diseño Visual

| Tecnología | Uso |
|------------|-----|
| **Google Fonts** | Tipografías `Inter` (interfaz) y `JetBrains Mono` (código/datos) |
| **CSS Glassmorphism** | Tarjetas con `backdrop-filter: blur(20px)` y bordes semitransparentes |
| **CSS Animations** | Gradientes animados en título y botón (`@keyframes`), pulsación en indicadores |
| **CSS Grid** | Layout de coordenadas en grid 2×2 responsive |

---

## 📋 Requisitos Previos

### Software Obligatorio

1. **Python 3.10 (recomendado para todo el proyecto en un mismo entorno)** — El código
   usa type hints modernas (`tuple[X | None]`), por lo que exige **≥ 3.10**; y el
   **motor completo de CPLEX** (necesario para la optimización real de RSU) solo
   soporta **≤ 3.10**. Por tanto **Python 3.10 es la única versión que ejecuta todo
   —backend VANET *y* el solver real— en un solo `.venv`**. El resto de librerías
   (Streamlit, Folium, NumPy, pandas, matplotlib) soportan 3.10 sin problema. Con
   Python 3.12/3.14 el backend funciona, pero la optimización queda limitada a la
   edición Community de CPLEX (solo el micro-ejemplo); ver la
   [Nota de versión de Python](#-resolución-con-docplexcplex-python-ya-no-oplrun).
2. **SUMO (Simulation of Urban MObility)** — Suite de simulación de tráfico
   - Descargar desde: https://sumo.dlr.de/docs/Downloads.php
   - Los ejecutables `netconvert` y `polyconvert` **deben estar en el PATH del sistema**
   - La variable de entorno `SUMO_HOME` debe apuntar al directorio de instalación de SUMO (necesario para `randomTrips.py`)

### Verificar Instalación de SUMO

```bash
# Verificar que netconvert está en el PATH
netconvert --version

# Verificar que SUMO_HOME está configurado
echo %SUMO_HOME%    # Windows
echo $SUMO_HOME     # Linux/Mac

# Verificar que randomTrips.py existe
python "%SUMO_HOME%/tools/randomTrips.py" --help
```

### Conexión a Internet

Necesaria para:
- Descargar datos de la API de OpenStreetMap
- Cargar tiles del mapa (OpenStreetMap, CARTO)
- Cargar fuentes de Google Fonts

---

## 🚀 Instalación y Ejecución

### 1. Clonar el repositorio

```bash
git clone https://github.com/tu-usuario/TIC-VANET-Vehicular-Ad-hoc-Network-.git
cd TIC-VANET-Vehicular-Ad-hoc-Network-
```

### 2. Crear entorno virtual

```bash
python -m venv .venv

# Activar (Windows)
.venv\Scripts\activate

# Activar (Linux/Mac)
source .venv/bin/activate
```

### 3. Instalar dependencias

```bash
pip install -r requirements.txt
```

### 4. Ejecutar la aplicación

```bash
streamlit run app.py
```

La aplicación se abrirá automáticamente en `http://localhost:8501`. El tema visual
("claro científico/ingeniería") y el modo headless quedan fijados en
[`.streamlit/config.toml`](.streamlit/config.toml).

### 5. Desplegar (Docker)

El repo incluye un [`Dockerfile`](Dockerfile) que empaqueta Python 3.10 + SUMO +
las dependencias:

```bash
docker build -t smartcitynet .
docker run -p 8501:8501 smartcitynet
```

Dónde desplegarla, opciones gratuitas/de pago, y cómo incluir el motor **CPLEX
completo** (licencia académica de IBM): ver **[`DESPLIEGUE.md`](DESPLIEGUE.md)**.

> ⚠️ La app necesita un **servidor real** (SUMO + CPLEX corren en el backend), así
> que **Streamlit Community Cloud no sirve**. Alternativas: Hugging Face Spaces
> (Docker, gratis), Render/Railway/Fly.io, un VPS, o el servidor de la EPN.

### 6. Frontend React + API FastAPI (migración en curso)

Además del frontend Streamlit, el proyecto se está migrando a **React + FastAPI**:
la ciencia (SUMO, LoS, multisalto, optimización) sigue en `backend/` y
`optimizacion/`, expuesta como **API HTTP** (`api/`) que consume un **SPA React**
(`web/`).

```bash
# 1) API (desde la raíz, en el venv con SUMO + docplex/CPLEX)
uvicorn api.main:app --reload --port 8000
# 2) SPA React (desde web/)
cd web && npm install && npm run dev      # http://localhost:5173
```

Detalles y estado de la migración: [`web/README.md`](web/README.md). Endpoints:
`api/main.py` (`/api/scenario/generate`, `/api/rsu/filter`, `/api/simulate`,
`/api/connectivity`, `/api/optimize`).

---

## 📂 Estructura de Archivos Detallada

```
TIC-VANET-Vehicular-Ad-hoc-Network-/
│
├── app.py                      # 🎯 Orquestador principal Módulos 1, 2 & 3 (~1250 líneas)
├── requirements.txt            # 📦 Dependencias Python
├── README.md                   # 📖 Este archivo
├── Dockerfile                  # 🐳 Imagen de despliegue (Python 3.10 + SUMO + deps)
├── DESPLIEGUE.md               # 🚀 Guía de despliegue (dónde y cómo)
├── .dockerignore               # 🐳 Exclusiones de la imagen
├── .streamlit/
│   └── config.toml             # 🎨 Tema claro científico/ingeniería + headless
│
├── mini_proyecto_vanet.py      # 🆕📚 Demo de TODO el flujo: mapa → LoS → A/B → multisalto
├── ejemplo_multisalto.py       # 🆕📚 Demo solo del multisalto (A y B dados a mano)
├── explicar_multisalto.py      # 🆕📚 Multisalto sobre un instante REAL de la simulación
│
├── frontend/                   # 🖥️ Capa de presentación
│   ├── __init__.py             #    Inicializador del paquete
│   ├── mapa.py                 #    Mapas: interactivo + RSU + conectividad + optimización (~520 líneas)
│   └── estilos.py              #    CSS de la consola clara + componentes UI + stepper
│
├── backend/                    # ⚙️ Capa de lógica de negocio
│   ├── __init__.py             #    Inicializador del paquete
│   ├── descargar_osm.py        #    Descarga de datos OSM (~86 líneas)
│   ├── sumo_pipeline.py        #    Automatización SUMO CLI (~180 líneas)
│   ├── parsear_xml.py          #    Parseo XML + proyección + filtrado RSU (~300 líneas)
│   ├── simulacion_sumo.py      # 🆕 Simulación SUMO + parseo FCD (~240 líneas)
│   ├── visibilidad.py          # 🆕 Algoritmo LoS + tuplas V2I + tuplas V2V (~670 líneas)
│   ├── multisalto.py           # 🆕 Conectividad multisalto R_h, S_h, D_H, d (~430 líneas)
│   └── exportar_dat.py         # 🆕 Puente VANET → optimización: escribe el .dat OPL (~430 líneas)
│
├── optimizacion/               # 🧮 Optimización de despliegue de RSU (docplex/CPLEX)
│   ├── optimizar_rsu.py        # 🆕 Modela y RESUELVE con docplex/CPLEX (Python, ya no oplrun)
│   ├── rsu_model.mod           #    Modelo OPL de referencia (misma matemática, para docs)
│   ├── rsu_micro.dat           #    Micro-ejemplo hecho a mano (referencia de formato)
│   └── rsu_backend.dat         # 🆕 .dat GENERADO desde los datos reales del backend (inspección)
│
└── output/                     # 📁 Archivos generados (auto-creado)
    ├── map.osm                 #    Datos crudos de OpenStreetMap
    ├── mapa.net.xml            #    Red vial SUMO (junctions + edges + connections)
    ├── mapa.poly.xml           #    Polígonos de edificios SUMO
    ├── mapa.rou.xml            #    Rutas vehiculares aleatorias
    ├── mapa.sumocfg            # 🆕 Configuración de simulación SUMO
    ├── fcd.xml                 # 🆕 Floating Car Data (posiciones vehiculares)
    ├── junctions_limpias.json  #    Intersecciones útiles (todas, sin filtrar)
    ├── edificios_limpios.json  #    Polígonos de edificios (datos limpios)
    ├── tuplas_visibilidad.json # 🆕 Tuplas <t, V, RSU> con LoS confirmado (Matriz B)
    ├── tuplas_v2v.json         # 🆕 Tuplas <t, Vi, Vj> + Matrices A por timestep
    └── multisalto.json         # 🆕 R_H, D_H y vector d por instante (opcional, si se exporta)
```

---

## ⚙️ Backend — Documentación Detallada

### 📁 `backend/descargar_osm.py`

Este módulo gestiona la comunicación con la API REST de OpenStreetMap para descargar los datos geográficos crudos.

**Librerías utilizadas:** `os`, `requests`

#### `validar_coordenadas(min_lon, min_lat, max_lon, max_lat) → (bool, str)`

Valida que las coordenadas del Bounding Box estén dentro de rangos geográficos reales antes de enviar la solicitud a la API.

**Validaciones implementadas:**
1. **Rango de longitud:** Verifica que ambas longitudes estén en `[-180°, 180°]`
2. **Rango de latitud:** Verifica que ambas latitudes estén en `[-90°, 90°]`
3. **Orden lógico:** Verifica que `min < max` para ambos ejes
4. **Tamaño del área:** Calcula `(max_lon - min_lon) × (max_lat - min_lat)` y rechaza áreas mayores a `0.25°²` (≈**3.000 km²** cerca del ecuador, ya que 1° ≈ 111 km y 0.25°² ≈ 55 km × 55 km). Esto previene solicitudes demasiado grandes que la API de OSM rechazaría (límite de ~50,000 nodos).

**Parámetros:**
- `min_lon` (float): Longitud mínima del Bounding Box
- `min_lat` (float): Latitud mínima del Bounding Box
- `max_lon` (float): Longitud máxima del Bounding Box
- `max_lat` (float): Latitud máxima del Bounding Box

**Retorna:** Tupla `(True, "")` si es válido, o `(False, "mensaje de error descriptivo")` si no lo es.

---

#### `descargar_mapa_osm(min_lon, min_lat, max_lon, max_lat, output_dir) → (str|None, str|None)`

Descarga el archivo `.osm` (formato XML) desde la API pública de OpenStreetMap.

**Funcionamiento interno:**
1. Llama a `validar_coordenadas()` como primera línea de defensa
2. Crea el directorio `output/` si no existe (`os.makedirs(exist_ok=True)`)
3. Construye la URL de la API: `https://api.openstreetmap.org/api/0.6/map?bbox=left,bottom,right,top`
4. Realiza la solicitud HTTP GET con `requests.get(url, timeout=120)`
5. Si `status_code == 200`, escribe el contenido binario en `output/map.osm`
6. Verifica que el archivo no sea menor a 100 bytes (indicaría área sin datos)

**Manejo de errores por código HTTP:**
- `400 Bad Request`: Coordenadas incorrectas o área demasiado grande
- `509 Bandwidth Limit Exceeded`: Demasiadas solicitudes al servidor OSM
- `Timeout (120s)`: El servidor no respondió a tiempo
- `ConnectionError`: Sin acceso a internet

**Retorna:** `(ruta_archivo, None)` en éxito, o `(None, "mensaje de error")` en fallo.

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
python randomTrips.py -n output/mapa.net.xml -r output/mapa.rou.xml -e <end_time> -p <periodo_s>
```

- `-n`: Archivo de red vial de entrada
- `-r`: Archivo de rutas de salida
- `-e <end_time>`: Tiempo final de generación de vehículos. Se calcula como `end_time = num_vehiculos × periodo_salida` (en segundos), que equivale a la duración total
- `-p <periodo_s>`: Periodo de salida en **segundos** entre vehículos
- Se ejecuta con `sys.executable` para usar el mismo intérprete Python del entorno virtual
- **Parámetros configurables (UI):** `num_vehiculos` (5–200, **default 100**) y `tiempo_simulacion` en **minutos** (1–180, **default 120 min** = 2 h). El `periodo_salida` ya **no se elige a mano**: se calcula automáticamente como `tiempo_simulacion / num_vehiculos` para repartir todos los autos a lo largo de la simulación (tráfico continuo)

**Ejecución con `subprocess.run()`:**
- `check=True`: Lanza `CalledProcessError` si el código de retorno no es 0
- `capture_output=True`: Captura stdout y stderr para diagnóstico
- `text=True`: Decodifica la salida como texto (no bytes)
- `timeout`: Mata el proceso si tarda demasiado. **120 s** para `netconvert` y `polyconvert`; **300 s** para `randomTrips` (puede tardar más al generar muchos vehículos)

**Manejo de excepciones por paso:**
- `FileNotFoundError`: El ejecutable no está en el PATH
- `CalledProcessError`: El comando retornó un código de error (se muestra `stderr[:500]`)
- `TimeoutExpired`: El proceso excedió su tiempo límite (120 s / 300 s según el paso)

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

---

#### `convertir_xy_a_lonlat(x, y, proy) → (lat, lon)`

Convierte una coordenada SUMO `(x, y)` en metros a coordenadas geográficas `(lat, lon)` en grados decimales.

**Método matemático: Interpolación lineal**

```
lon = orig_lon_min + (x - conv_x_min) / (conv_x_max - conv_x_min) × (orig_lon_max - orig_lon_min)
lat = orig_lat_min + (y - conv_y_min) / (conv_y_max - conv_y_min) × (orig_lat_max - orig_lat_min)
```

Esta interpolación es precisa para áreas pequeñas (< 10 km²) donde la curvatura de la Tierra es despreciable. Para áreas más grandes sería necesario usar la librería `pyproj` con los parámetros UTM exactos.

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
for edge in root.findall("edge"):
    if edge.get("function") == "internal":
        continue  # Ignorar edges internas de SUMO
    a, b = edge.get("from"), edge.get("to")
    if not a or not b or a == b:
        continue  # descartar aristas incompletas o lazos
    vecinos.setdefault(a, set()).add(b)   # pares no ordenados
    vecinos.setdefault(b, set()).add(a)
grados = {j: len(vs) for j, vs in vecinos.items()}  # nº de vecinos únicos
```

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

Estos parámetros se controlan directamente en Streamlit mediante el panel expandible "⚙️ Configuración de filtrado RSU":

| Parámetro | Control UI | Default | Rango | Función |
|-----------|-----------|---------|-------|---------|
| `min_grado` | Slider: 🔗 Grado mínimo | **4** | 2 – 8 | Filtro topológico |
| `radio_cluster` | Slider: 📏 Radio de agrupación | **20m** | 0 – 100m | Filtro espacial |
| `mostrar_cobertura` | Checkbox: 📶 Mostrar radio | **Falso** | On / Off | Visualización |
| `radio_cobertura` | Slider: 📡 Radio de cobertura | **200m** | 50 – 500m | Alcance visual |

**¿Dónde cambiar los defaults en el código?**

En `app.py`, dentro de la sección `# ---- Controles de filtrado ----`:

```python
min_grado = st.slider(
    "🔗 Grado mínimo de conectividad",
    min_value=2, max_value=8, value=4, step=1,  # ← cambiar 'value' para el default
)

radio_cluster = st.slider(
    "📏 Radio de agrupación (metros)",
    min_value=0, max_value=100, value=20, step=5,  # ← cambiar 'value' para el default
)
```

Si se desea **cambiar los rangos** de los sliders, modificar `min_value` y `max_value`.

Si se desea **llamar al filtrado directamente desde código** (sin UI):

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

**¿Dónde cambiar los defaults en el código?**

En `app.py`, dentro de la sección `# ---- Controles de generación de escenario ----` y `# ---- Controles de simulación V2I + V2V ----`. Cada slider tiene un parámetro `value` que define el default.

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

### Cómo cambiar la zona geográfica

1. Abrir la aplicación (`streamlit run app.py`)
2. Dibujar un nuevo rectángulo en el mapa (cualquier zona del mundo)
3. Presionar "Generar Escenario" para ejecutar todo el pipeline
4. Los sliders de filtrado RSU aparecen automáticamente debajo del mapa de resultados
5. Ajustar los sliders en tiempo real para ver cómo cambia el número de RSU

### Cómo exportar los resultados filtrados

Los datos filtrados están disponibles en `st.session_state.pipeline_resultados` durante la sesión. Para exportarlos a un archivo JSON permanente, se puede agregar al final de `app.py`:

```python
import json

# Después de aplicar el filtrado
json_path = os.path.join(OUTPUT_DIR, "rsu_candidatos.json")
with open(json_path, "w", encoding="utf-8") as f:
    json.dump(junctions_rsu, f, indent=4, ensure_ascii=False)
```

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

## 🧮 Exportación a la Optimización — El archivo `.dat`

Esta sección documenta [`backend/exportar_dat.py`](backend/exportar_dat.py), el **puente** entre la parte VANET del proyecto (que produce las matrices de conectividad) y la parte de **optimización de despliegue de RSU** que vive en [`optimizacion/`](optimizacion/). La optimización se resuelve con **IBM CPLEX** desde Python vía **`docplex`** (ver [Resolución con docplex/CPLEX](#resolución-con-docplexcplex-python-ya-no-oplrun) más abajo); el archivo `.dat` que genera este módulo sigue siendo útil para inspección y compatibilidad con OPL, pero ya **no** es necesario para resolver.

> ✅ **Alcance.** `exportar_dat.py` genera el archivo `.dat` y arma en memoria el dict de datos; la resolución la hace [`optimizacion/optimizar_rsu.py`](optimizacion/optimizar_rsu.py) con docplex. **Ambos están integrados en la interfaz (`app.py`) como el Módulo 3:** tras la simulación V2I+V2V, el botón *"Optimizar Despliegue de RSU"* construye el CVR en memoria (`exportar_dat_desde_memoria`), resuelve con `optimizar()` y dibuja las RSU seleccionadas sobre el mismo plano generado por el frontend. También se puede correr por CLI (ver más abajo).

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

El modelo exige que **toda la carga de cada vehículo se sirva** (restricción Ec. 2). Si un vehículo no alcanza ninguna RSU real, esa restricción sería infactible. Para evitarlo, a **cada vehículo presente en cada escenario** se le añade una tupla extra `<s, hmax, v, 0>`: la opción de "caer" en el RSU artificial `r_inf` (id 0) al salto `hmax = H+1`, con una **penalización enorme** (`P[hmax]`, por defecto 1000). Así el modelo siempre es factible y la desconexión solo se usa como último recurso.

### Los conjuntos y parámetros que escribe

| Símbolo OPL | Qué es | Cómo se genera |
|-------------|--------|----------------|
| `hmax` | Nº de saltos incl. desconexión | `H + 1` |
| `rInf` | Id del RSU artificial | `0` |
| `MaxR` | Máx. de RSU reales a desplegar | Parámetro (`--max-rsu`); default = nº de candidatos |
| `R` | RSU candidatos (incluye `0`) | `{0}` ∪ RSU que aparecen en algún `CVR` |
| `S` | Escenarios | Un id por instante |
| `V` | Todos los vehículos | Unión de vehículos de todos los instantes |
| `Vs[s]` | Vehículos presentes en `s` | `matrices_v2v[t]["vehiculos"]` |
| `Cost[r]` | Costo de instalar `r` | `0` para `r_inf`; `1` cada RSU real (⇒ minimiza **cantidad**) |
| `Cap[r]` | Capacidad de `r` | `r_inf` grande (1000); reales `cap_real` (100) |
| `P[1..hmax]` | Penalización por salto | `[1, 2, …, H, penal_desconexion]` |
| `L[s][v]` | Carga de tráfico | `carga_default` (1) para todos |
| `CVR` | Tuplas `<s,h,v,r>` | De las matrices `S_h` (ver arriba) + tuplas `r_inf` |

> **Solo RSU conectados (por defecto).** Los RSU que **ningún** vehículo alcanza jamás son inútiles (el modelo nunca los elegiría) y solo inflan el archivo. Por eso, por defecto, `R` incluye solo los RSU que aparecen en al menos una tupla `CVR`. Con `--todos-los-rsu` se incluyen todos los candidatos. Es una reducción **sin pérdida** para el óptimo.

### Funciones principales

| Función | Qué hace |
|---------|----------|
| `construir_datos_opl(matrices_v2v, tuplas_v2i, rsu_ids, H, …)` | Corre el multisalto en cada instante y arma en memoria **todos** los conjuntos/parámetros + `CVR` + los mapas de traducción |
| `escribir_dat(datos, dat_path)` | Vuelca esa estructura al archivo `.dat` con la **sintaxis exacta** de OPL (`#[ k:v ]#`, `{ … }`, `<s,h,v,r>`) y una cabecera con la trazabilidad |
| `exportar_dat_desde_json(output_dir, dat_path, H, …)` | **Punto de entrada:** lee `tuplas_v2v.json` + `tuplas_visibilidad.json` y escribe el `.dat` |
| `exportar_dat_desde_memoria(matrices_v2v, tuplas_v2i, rsus, dat_path, H, …)` | Igual pero desde estructuras en memoria (para conectar con `app.py` en el futuro, sin pasar por disco) |

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

### Ejemplo de salida (con los datos reales de `output/`)

Con la simulación de ejemplo (31 instantes, 132 vehículos, 278 RSU candidatos [config. de referencia, grado 4 / radio 20 m], `H=3`, `MaxR=10`) el módulo genera:

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

Con datos reales, el solver devuelve los **ids de RSU del backend** a desplegar (usando el mapa inverso de la cabecera del `.dat`). Ese resultado ya está **integrado en la interfaz** (Módulo 3 de `app.py`): las RSU elegidas se resaltan en verde sobre el plano, con las candidatas no desplegadas en gris. En el escenario de referencia (Centro Histórico de Quito, 31 escenarios, 227 RSU candidatas, 1628 tuplas CVR) el óptimo entero es **objetivo = 2237.0 con 38 RSU desplegadas**.

---

## 📚 Scripts didácticos (para entender y explicar el proyecto)

Además de la aplicación, el proyecto incluye **3 scripts de consola** pensados para *entender* y *explicar* cómo funciona el pipeline, de lo más simple a lo más real. Todos usan las **funciones reales** del proyecto (`backend/visibilidad.py` y `backend/multisalto.py`), así que no son cálculos "de mentira".

| Script | Qué muestra | Cuándo usarlo |
|--------|-------------|---------------|
| [`mini_proyecto_vanet.py`](mini_proyecto_vanet.py) | **Todo el flujo** en miniatura: posiciones de coches + 1 edificio → línea de vista (LoS) → tuplas → Matriz A (V2V) y Matriz B (V2I) → multisalto (R, S, D, d) | Para explicar el proyecto **completo** de principio a fin |
| [`ejemplo_multisalto.py`](ejemplo_multisalto.py) | Solo la parte de **multisalto**, con A y B dadas a mano (cadena V1→V2→V3→RSU + un coche aislado) | Para entender **solo las matrices** y los saltos |
| [`explicar_multisalto.py`](explicar_multisalto.py) | El multisalto sobre un **instante real** de tu simulación (lee `output/*.json`) | Para demostrar que funciona con **datos verdaderos** |

**Cómo ejecutarlos:**

```bash
python mini_proyecto_vanet.py          # demo completa (escenario de juguete)
python ejemplo_multisalto.py           # demo del multisalto
python explicar_multisalto.py          # instante real (elige uno automáticamente)
python explicar_multisalto.py 120 3    # instante t=120 s con H=3 saltos
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

## 🖥️ Frontend — Documentación Detallada

### 📁 `frontend/mapa.py`

Este módulo gestiona la creación y configuración de los mapas interactivos Folium.

**Librerías utilizadas:** `folium`, `folium.plugins.Draw`, `folium.plugins.MiniMap`

#### `crear_mapa(centro_lat, centro_lon, zoom) → folium.Map`

Crea el mapa principal de la aplicación con las herramientas de dibujo.

**Configuración del mapa:**
- **Tiles base:** OpenStreetMap estándar (máxima compatibilidad con todos los navegadores)
- **Capas alternativas:** CARTO Light (Claro) y CARTO Voyager (Detallado), seleccionables desde el control de capas
- **Control de capas:** Botón en la esquina superior derecha (`LayerControl`)
- **Minimapa:** Vista miniatura en la esquina inferior derecha (`MiniMap`) para orientación rápida
- **Centro por defecto:** Quito, Ecuador (`-0.2186, -78.5097`)

**Herramienta de dibujo (Draw plugin):**
- Solo permite dibujar **rectángulos** (polyline, polygon, circle, marker y circlemarker están deshabilitados)
- Estilo del rectángulo:
  - Borde: Línea punteada azul (`#3b82f6`, `dashArray: '5, 5'`)
  - Relleno: Púrpura semitransparente (`#8b5cf6`, `fillOpacity: 0.2`)
  - Grosor del borde: 3px
- La edición post-dibujo está deshabilitada (`edit: False`)

---

#### `extraer_coordenadas_bbox(st_data) → tuple|None`

Extrae las coordenadas del Bounding Box desde el diccionario que devuelve `st_folium()`.

**Proceso de extracción:**
1. Busca el dibujo en `st_data["last_active_drawing"]` (prioritario) o en `st_data["all_drawings"][-1]` (último dibujo)
2. Accede a la geometría GeoJSON: `dibujo["geometry"]["coordinates"][0]`
3. En GeoJSON, las coordenadas de un polígono son `[lon, lat]` (longitud primero)
4. Calcula `min()` y `max()` para ambos ejes

**Validaciones:**
- Longitudes en `[-180°, 180°]`
- Latitudes en `[-90°, 90°]`
- El rectángulo tiene área positiva (`min < max`)

**Retorna:** `(min_lon, min_lat, max_lon, max_lat)` o `None`.

---

#### `crear_mapa_resultados(junctions, edificios, proy) → folium.Map`

Crea un mapa de visualización con los datos extraídos del pipeline. **Detecta automáticamente** si las junctions vienen del filtrado RSU (tienen campo `grado`) o son junctions crudas, y adapta el estilo de los marcadores.

**Elementos visuales:**

| Tipo | Condición | Representación | Color | Radio | Componente Folium |
|------|-----------|---------------|-------|-------|-------------------|
| **RSU Candidato** | Junction con campo `grado` | Círculo sólido, borde grueso | Rojo `#ef4444` | 9px | `CircleMarker` |
| **Junction cruda** | Junction sin campo `grado` | Círculo, borde fino | Azul `#3b82f6` | 6px | `CircleMarker` |
| **Edificio** | Siempre | Polígono relleno semi-transparente | Naranja `#f97316` | — | `Polygon` |

---

#### `crear_mapa_conectividad(rsus, edificios, proy, tuplas, datos_fcd, timestep_exacto, tuplas_v2v) → folium.Map`

Crea un mapa de Folium que visualiza la conectividad V2I **y V2V** en un instante de tiempo exacto.

**Capas del mapa:**

| Capa | Elementos | Color | Estilo |
|------|-----------|-------|--------|
| 🏢 Edificios | Polígonos de edificios | Naranja `#f97316` | Relleno semi-transparente |
| 🚗 Vehículos | Posiciones de vehículos | Multicolor | CircleMarker, radio 6px |
| 📡 Conexiones V2I | Líneas vehículo↔RSU | Verde `#22c55e` | PolyLine punteada |
| 🚗 Conexiones V2V | Líneas vehículo↔vehículo | Amarillo `#eab308` | PolyLine punteada |
| 📡 RSU Candidatos | Posiciones RSU | Rojo `#ef4444` | CircleMarker, radio 9px |

Las conexiones V2V se dibujan sin duplicar líneas (para pares bidireccionales, solo se dibuja una línea).

---

### 📁 `frontend/estilos.py`

Contiene el diseño visual de la aplicación: la **consola clara científica/ingeniería**.
Inyecta CSS en Streamlit con `st.markdown(unsafe_allow_html=True)` y complementa al
tema base fijado en [`.streamlit/config.toml`](.streamlit/config.toml).

**Dirección de diseño:** instrumento científico, no web decorativa. Fondo claro frío,
**un único acento azul acero** (`#2557a7`), **verde reservado como color semántico**
para "óptimo/desplegado" (`#0f9d6b`), **datos en monoespaciada con cifras tabulares**,
hairlines de plano de ingeniería y un motivo sutil de **graticula cartográfica** en el
encabezado. Sin gradientes animados ni neón (se retiró el estilo oscuro anterior).

**Librerías utilizadas:** `streamlit`

#### `COLORES` (diccionario)

Paleta centralizada (claro). Se conservan alias con los nombres antiguos
(`accent_cyan`, `text_primary`, …) apuntando a la nueva paleta para compatibilidad.

| Variable | Valor | Uso |
|----------|-------|-----|
| `ground` | `#f6f7f9` | Fondo de la app (frío, claro) |
| `surface` | `#ffffff` | Fondo de tarjetas/paneles |
| `ink` | `#0f1b2d` | Texto principal (navy) |
| `muted` | `#5b6b7f` | Texto secundario |
| `line` | `#e2e6ec` | Bordes hairline |
| `accent` | `#2557a7` | Acento único (azul acero): acciones, datos, links |
| `ok` | `#0f9d6b` | Semántico: óptimo / RSU desplegada / éxito |
| `warn` | `#b9770b` | Semántico: advertencia |
| `crit` | `#c0392b` | Semántico: error |

#### `inyectar_css()`

Inyecta el CSS de la consola: tipografía de sistema + monoespaciada para datos,
tarjetas y paneles con hairlines, botón primario azul sólido (sin gradiente),
**estilado de los widgets nativos** (`st.metric`, tabs, expanders, sliders,
dataframes) para que armonicen, y oculta el chrome de Streamlit.

#### Funciones de renderizado

| Función | Propósito |
|---------|-----------|
| `renderizar_header()` | Encabezado con eyebrow, título, descripción, tech tags y graticula |
| `renderizar_stepper(activo)` | **Nuevo.** Stepper de módulos M1→M2→M3 (hecho=verde, activo=azul) |
| `renderizar_map_label()` | Label superior del mapa con punto de estado |
| `renderizar_instrucciones()` | Tarjeta con 3 pasos numerados |
| `renderizar_coordenadas(min_lat, min_lon, max_lat, max_lon)` | Grid 2×2 con las 4 coordenadas en monoespaciada |
| `renderizar_estado_vacio()` | Estado vacío con icono y mensaje |
| `renderizar_paso_pipeline(nombre, exito, detalle)` | Fila de log del pipeline con estado ✓/✕ |
| `renderizar_divider(texto)` | Separador de sección con etiqueta mono en chip |
| `renderizar_resumen(n_junctions, n_edificios)` | Tarjeta de resumen del M1 con archivos generados |
| `renderizar_simulacion_stats(estadisticas)` | Tiles con métricas V2I |
| `renderizar_v2v_stats(estadisticas_v2v)` | Tiles con métricas V2V |

---

## 🎯 Orquestador Principal (`app.py`)

El archivo `app.py` (~1100 líneas) es el punto de entrada de la aplicación. No contiene lógica de negocio propia — su función es **orquestar** los módulos del frontend y backend, incluyendo los controles interactivos de filtrado RSU y la simulación V2I + V2V.

### Gestión de Estado con `st.session_state`

Streamlit re-ejecuta **todo el script** en cada interacción del usuario. Para persistir datos entre reruns, se usan cinco variables de estado:

| Variable | Tipo | Propósito |
|----------|------|-----------|
| `bbox` | `tuple\|None` | Coordenadas del Bounding Box dibujado por el usuario |
| `ejecutar_pipeline` | `bool` | Flag que indica si el pipeline debe ejecutarse en este rerun |
| `pipeline_resultados` | `dict\|None` | Resultados del último pipeline, incluyendo datos para filtrado RSU |
| `ejecutar_simulacion` | `bool` | Flag que indica si la simulación V2I/V2V debe ejecutarse |
| `simulacion_resultados` | `dict\|None` | Resultados de la simulación V2I y V2V, incluyendo tuplas y matrices |

La estructura de `simulacion_resultados` después de una ejecución exitosa:

```python
{
    "tuplas": [...],                # Lista de tuplas V2I <t, V, RSU>
    "estadisticas": {...},          # Resumen V2I
    "datos_fcd": {...},             # Posiciones vehiculares por timestep
    "rsus": {...},                  # RSU candidatos
    "edificios": {...},             # Edificios
    "proyeccion": {...},            # Parámetros de proyección
    "radio_obu": 300,               # Radio OBU usado
    "tuplas_v2v": [...],            # Lista de tuplas V2V <t, Vi, Vj>
    "matrices_v2v": {...},          # Matrices A por timestep
    "estadisticas_v2v": {...},      # Resumen V2V
}
```

### Solución al Bug del Doble Re-render

**Problema:** El componente `st_folium` causa un re-render adicional de Streamlit al montar el mapa. Si el usuario presiona el botón "Generar Escenario", el primer rerun tiene `btn_generar=True`, pero `st_folium` dispara un segundo rerun donde `btn_generar=False`, y el pipeline nunca se ejecuta.

**Solución:** En lugar de usar `if st.button(...)`, se usa el callback `on_click` del botón:

```python
def _on_click_generar():
    st.session_state.ejecutar_pipeline = True

st.button("Generar Escenario", on_click=_on_click_generar)
```

El callback se ejecuta **antes** del rerun, así que `st.session_state.ejecutar_pipeline = True` persiste correctamente incluso si hay múltiples reruns.

### Layout de Columnas

```python
col_mapa, col_panel = st.columns([5, 2], gap="large")
```

- **Columna izquierda (5/7):** Mapa interactivo Folium (520px de alto)
- **Columna derecha (2/7):** Panel de control con instrucciones, coordenadas y botón

---

## 📁 Archivos de Salida

Todos los archivos se generan en la carpeta `output/`:

### Módulo 1 — Escenario VANET

| Archivo | Formato | Generado por | Contenido |
|---------|---------|-------------|-----------|
| `map.osm` | XML (OSM) | `descargar_osm.py` | Datos geográficos crudos: nodos, vías, relaciones, edificios, POIs |
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

## 💡 Consideraciones Técnicas

### Sistema de Coordenadas

El proyecto maneja **dos sistemas de coordenadas**:

1. **Geográficas (WGS84):** `lon, lat` en grados decimales. Usadas por OpenStreetMap, Folium y la interfaz del usuario.
2. **Proyectadas (UTM):** `x, y` en metros. Usadas internamente por SUMO después de `netconvert`. La zona UTM se determina automáticamente según la ubicación del Bounding Box (por ejemplo, Zona 17 para Ecuador).

La conversión entre ambos sistemas se hace mediante `obtener_proyeccion()` + `convertir_xy_a_lonlat()`, usando interpolación lineal sobre los boundaries del archivo `.net.xml`.

### Limitaciones Conocidas

- **Tamaño del área:** La API de OSM limita las descargas a ~50,000 nodos. El módulo limita el área a `0.25°²` como protección.
- **Dependencia de SUMO:** Los ejecutables `netconvert` y `polyconvert` deben estar instalados en el sistema y accesibles desde el PATH.
- **Precisión de la conversión:** La interpolación lineal es suficiente para áreas menores a ~10 km². Para áreas mayores, sería necesario usar `pyproj` con los parámetros UTM exactos.
- **Navegador:** Microsoft Edge con "Prevención de seguimiento" en modo Estricto puede bloquear CDN externas (Leaflet, Google Fonts). Se recomienda usar Chrome o Firefox.

### Extensiones Futuras

1. ~~**Módulo 2:** Visualización de tráfico simulado sobre el mapa usando datos de SUMO~~ ✅ **Implementado**
2. ~~**Conectividad V2V:** Matriz A vehículo-vehículo con tuplas `<t, Vi, Vj>`~~ ✅ **Implementado**
3. ~~**Conectividad multisalto:** Uso de las matrices A y B para calcular conectividad a múltiples saltos mediante producto binario de matrices (R_h, S_h, D_H, vector d)~~ ✅ **Implementado** (módulo [`backend/multisalto.py`](backend/multisalto.py))
4. ~~**Exportación a la optimización:** Generar el `.dat` de OPL/CPLEX desde los datos del backend (conjuntos, parámetros y `CVR` desde las `S_h`)~~ ✅ **Implementado** (módulo [`backend/exportar_dat.py`](backend/exportar_dat.py)).
5. ~~**Resolver la optimización:** Ejecutar el solver de despliegue de RSU~~ ✅ **Implementado** con **docplex/CPLEX en Python** ([`optimizacion/optimizar_rsu.py`](optimizacion/optimizar_rsu.py), ya no `oplrun`). Validado contra el micro-ejemplo (elige `{R1, R3}`, objetivo 11.0, idéntico al OPL) y resuelve datos reales del backend.
6. ~~**Integrar la optimización en la UI:** botón que construye el CVR, resuelve con docplex/CPLEX y dibuja las RSU desplegadas sobre el plano~~ ✅ **Implementado** (Módulo 3 de [`app.py`](app.py) + [`crear_mapa_optimizacion`](frontend/mapa.py)). Cierra el flujo completo *escenario → simulación → conectividad → despliegue óptimo* dentro del frontend.
7. **NS-3:** Integración con NS-3 para simulación de protocolos VANET
8. **API REST:** Migrar el backend a FastAPI para desacoplar completamente frontend y backend
9. **Docker:** Containerizar la aplicación con SUMO incluido para facilitar despliegues

---

## 📝 Licencia

Trabajo de Integración Curricular — Universidad. Todos los derechos reservados.
