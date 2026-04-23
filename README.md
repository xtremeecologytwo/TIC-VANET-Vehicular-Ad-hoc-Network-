# 🛰️ VANET Scenario Generator — Módulo 1

**Trabajo de Integración Curricular — Redes Vehiculares Ad-hoc (VANETs)**

Aplicación web que automatiza la generación de escenarios de simulación para redes vehiculares (VANETs). Permite seleccionar un área geográfica real desde un mapa interactivo, descargar la topología vial desde OpenStreetMap, procesarla automáticamente con las herramientas CLI de SUMO, y extraer los datos matemáticos útiles (intersecciones y edificios) en formato JSON para su uso posterior en simulaciones NS-3 u OMNET++.

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
│         Coordina la interacción entre Frontend y Backend         │
├──────────────────────────┬───────────────────────────────────────┤
│     📊 FRONTEND          │              ⚙️ BACKEND               │
│                          │                                       │
│  frontend/               │  backend/                             │
│  ├── __init__.py         │  ├── __init__.py                      │
│  ├── mapa.py             │  ├── descargar_osm.py                 │
│  │   ├── crear_mapa()    │  │   ├── validar_coordenadas()        │
│  │   ├── extraer_bbox()  │  │   └── descargar_mapa_osm()         │
│  │   └── mapa_resultados │  ├── sumo_pipeline.py                 │
│  └── estilos.py          │  │   ├── _buscar_random_trips()       │
│      ├── inyectar_css()  │  │   └── ejecutar_pipeline_sumo()     │
│      ├── renderizar_*()  │  └── parsear_xml.py                   │
│      └── COLORES{}       │      ├── parsear_junctions()          │
│                          │      ├── parsear_edificios()           │
│                          │      ├── obtener_proyeccion()          │
│                          │      ├── convertir_xy_a_lonlat()       │
│                          │      ├── calcular_grado_junctions() 🆕│
│                          │      └── filtrar_junctions_rsu()    🆕│
└──────────────────────────┴───────────────────────────────────────┘
                                    │
                                    ▼
                           📁 output/ (archivos generados)
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

### Herramientas Externas (SUMO)

| Herramienta | Tipo | Descripción |
|-------------|------|-------------|
| **`netconvert`** | Ejecutable SUMO | Convierte datos de red de diferentes fuentes (OSM, Shapefile) al formato interno de SUMO (`.net.xml`). Aplica optimizaciones: `--geometry.remove` (simplifica geometrías), `--edges.join` (fusiona aristas redundantes), `--ramps.guess` (detecta rampas), `--remove-edges.isolated` (elimina aristas aisladas) |
| **`polyconvert`** | Ejecutable SUMO | Extrae polígonos y puntos de interés (POIs) del archivo OSM y los proyecta sobre la red vial. Genera `mapa.poly.xml` con los edificios, parques y otros elementos geográficos |
| **`randomTrips.py`** | Script Python SUMO | Genera pares origen-destino aleatorios sobre la red vial y calcula rutas usando el algoritmo de Dijkstra. El parámetro `-e 100` indica 100 unidades de tiempo de simulación |

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

1. **Python 3.10+** — Requerido por la sintaxis `tuple[X | None]` (type hints modernas)
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

La aplicación se abrirá automáticamente en `http://localhost:8501`.

---

## 📂 Estructura de Archivos Detallada

```
TIC-VANET-Vehicular-Ad-hoc-Network-/
│
├── app.py                      # 🎯 Orquestador principal (~310 líneas)
├── requirements.txt            # 📦 Dependencias Python
├── README.md                   # 📖 Este archivo
│
├── frontend/                   # 🖥️ Capa de presentación
│   ├── __init__.py             #    Inicializador del paquete
│   ├── mapa.py                 #    Mapa interactivo + mapa de resultados RSU (~240 líneas)
│   └── estilos.py              #    CSS premium + componentes UI (~500 líneas)
│
├── backend/                    # ⚙️ Capa de lógica de negocio
│   ├── __init__.py             #    Inicializador del paquete
│   ├── descargar_osm.py        #    Descarga de datos OSM (~86 líneas)
│   ├── sumo_pipeline.py        #    Automatización SUMO CLI (~173 líneas)
│   └── parsear_xml.py          #    Parseo XML + proyección + filtrado RSU (~300 líneas)
│
└── output/                     # 📁 Archivos generados (auto-creado)
    ├── map.osm                 #    Datos crudos de OpenStreetMap
    ├── mapa.net.xml            #    Red vial SUMO (junctions + edges + connections)
    ├── mapa.poly.xml           #    Polígonos de edificios SUMO
    ├── mapa.rou.xml            #    Rutas vehiculares aleatorias
    ├── junctions_limpias.json  #    Intersecciones útiles (todas, sin filtrar)
    └── edificios_limpios.json  #    Polígonos de edificios (datos limpios)
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
4. **Tamaño del área:** Calcula `(max_lon - min_lon) × (max_lat - min_lat)` y rechaza áreas mayores a `0.25°²` (≈780 km² en el ecuador). Esto previene solicitudes demasiado grandes que la API de OSM rechazaría (límite de ~50,000 nodos).

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
python randomTrips.py -n output/mapa.net.xml -r output/mapa.rou.xml -e 100
```

- `-n`: Archivo de red vial de entrada
- `-r`: Archivo de rutas de salida
- `-e 100`: Tiempo final de simulación (100 unidades = 100 vehículos)
- Se ejecuta con `sys.executable` para usar el mismo intérprete Python del entorno virtual

**Ejecución con `subprocess.run()`:**
- `check=True`: Lanza `CalledProcessError` si el código de retorno no es 0
- `capture_output=True`: Captura stdout y stderr para diagnóstico
- `text=True`: Decodifica la salida como texto (no bytes)
- `timeout=120`: Mata el proceso si tarda más de 120 segundos

**Manejo de excepciones por paso:**
- `FileNotFoundError`: El ejecutable no está en el PATH
- `CalledProcessError`: El comando retornó un código de error (se muestra `stderr[:500]`)
- `TimeoutExpired`: El proceso excedió los 120s

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

**Ejemplo real:** Para una zona del Centro Histórico de Quito, SUMO generó **620 junctions** tras el parseo inicial. Después del filtrado RSU, se redujeron a **160 candidatos** (reducción del 74%) conservando solo las intersecciones significativas.

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

**¿Qué es el grado?** El grado de una junction es el número de aristas (edges) no-internas que se conectan a ella. En SUMO, cada calle bidireccional genera **2 edges** (una por sentido), por lo que:

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
grados = {}
for edge in root.findall("edge"):
    if edge.get("function") == "internal":
        continue  # Ignorar edges internas de SUMO
    from_id = edge.get("from")
    to_id = edge.get("to")
    grados[from_id] = grados.get(from_id, 0) + 1
    grados[to_id] = grados.get(to_id, 0) + 1
```

Se recorre cada `<edge>` del archivo `mapa.net.xml`, se ignoran las internas (`function="internal"`), y para cada edge vehicular se incrementa el contador del nodo origen (`from`) y del nodo destino (`to`).

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
| Centro Histórico | ~0.5 | 620 | 4 | 20 | 160 | 74% |
| Centro Histórico | ~0.5 | 620 | 6 | 30 | 63 | 90% |
| Zona Norte | ~0.8 | — | 4 | 20 | — | — |
| Zona Industrial | ~1.0 | — | 4 | 20 | — | — |

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

**Detección automática de modo RSU:**

```python
es_rsu = any("grado" in coords for coords in junctions.values())
```

Si al menos una junction tiene el campo `grado`, el mapa entra en **modo RSU** y muestra:
- Nombre del grupo: "📡 RSU Candidatos" (en vez de "⭐ Intersecciones")
- Tooltip enriquecido con grado de conectividad y coordenadas geográficas
- Popup con coordenadas SUMO (x, y) y geográficas (lat, lon)

**Conversión de coordenadas:** Cada junction y vértice de edificio se convierte de coordenadas SUMO (x, y en metros) a lat/lon usando `convertir_xy_a_lonlat()` con los parámetros de proyección del `.net.xml`.

---

### 📁 `frontend/estilos.py`

Este módulo contiene todo el diseño visual de la aplicación. Inyecta CSS personalizado en Streamlit mediante `st.markdown(unsafe_allow_html=True)`.

**Librerías utilizadas:** `streamlit`

#### `COLORES` (diccionario)

Paleta de colores centralizada del proyecto:

| Variable | Valor | Uso |
|----------|-------|-----|
| `bg_primary` | `#0a0e1a` | Fondo principal (oscuro profundo) |
| `bg_secondary` | `#111827` | Fondo de tarjetas |
| `accent_cyan` | `#06b6d4` | Acento principal, coordenadas, botones |
| `accent_blue` | `#3b82f6` | Acento secundario, gradientes |
| `accent_purple` | `#8b5cf6` | Acento terciario, hover effects |
| `accent_emerald` | `#10b981` | Estados exitosos (✅) |
| `accent_amber` | `#f59e0b` | Advertencias, iconos de archivos |
| `accent_red` | `#ef4444` | Estados de error (❌) |
| `text_primary` | `#f1f5f9` | Texto principal |
| `text_secondary` | `#94a3b8` | Texto secundario, subtítulos |

#### `inyectar_css()`

Inyecta más de 500 líneas de CSS personalizado con:
- **Google Fonts:** `Inter` (pesos 300-800) para la interfaz, `JetBrains Mono` (pesos 400-500) para datos numéricos
- **Glassmorphism:** Tarjetas con `backdrop-filter: blur(20px)` y gradientes semitransparentes
- **Animaciones CSS:** 5 keyframes animados (`gradient-slide`, `text-gradient`, `btn-gradient`, `pulse-dot`, `pulse-border`)
- **Responsive:** Grid CSS para coordenadas, Flexbox para pasos y estadísticas
- **Oculta elementos Streamlit:** Esconde el menú hamburguesa, footer y header nativos

#### Funciones de renderizado

| Función | Propósito |
|---------|-----------|
| `renderizar_header()` | Encabezado hero con badge, título animado, descripción y tech tags |
| `renderizar_map_label()` | Label superior del mapa con punto verde pulsante de "activo" |
| `renderizar_instrucciones()` | Tarjeta glassmorphism con 3 pasos numerados |
| `renderizar_coordenadas(min_lat, min_lon, max_lat, max_lon)` | Grid 2×2 con las 4 coordenadas en fuente monospace cyan |
| `renderizar_estado_vacio()` | Estado vacío con icono y mensaje centrado |
| `renderizar_paso_pipeline(nombre, exito, detalle)` | Fila de log del pipeline con icono ✅/❌, borde verde/rojo y detalle en monospace |
| `renderizar_divider(texto)` | Línea separadora horizontal con etiqueta centrada en mayúsculas |
| `renderizar_resumen(n_junctions, n_edificios)` | Tarjeta final con estadísticas numéricas y lista de archivos generados |

---

## 🎯 Orquestador Principal (`app.py`)

El archivo `app.py` (~310 líneas) es el punto de entrada de la aplicación. No contiene lógica de negocio propia — su función es **orquestar** los módulos del frontend y backend, incluyendo los controles interactivos de filtrado RSU.

### Gestión de Estado con `st.session_state`

Streamlit re-ejecuta **todo el script** en cada interacción del usuario. Para persistir datos entre reruns, se usan tres variables de estado:

| Variable | Tipo | Propósito |
|----------|------|-----------|
| `bbox` | `tuple\|None` | Coordenadas del Bounding Box dibujado por el usuario |
| `ejecutar_pipeline` | `bool` | Flag que indica si el pipeline debe ejecutarse en este rerun |
| `pipeline_resultados` | `dict\|None` | Resultados del último pipeline, incluyendo datos para filtrado RSU |

La estructura de `pipeline_resultados` después de una ejecución exitosa:

```python
{
    "pasos": [("Descarga OSM", True, "map.osm (45 KB)"), ...],  # Log de pasos
    "junctions": 620,             # Conteo total de junctions parseadas
    "edificios": 85,              # Conteo total de edificios parseados
    "junctions_data": {...},      # Dict completo de junctions para filtrado RSU
    "edificios_data": {...},      # Dict completo de edificios para visualización
    "proyeccion": {"orig": [...], "conv": [...]},  # Params de proyección UTM
    "net_xml": "output/mapa.net.xml"  # Ruta al net.xml para calcular grados
}
```

Esta estructura permite que el filtrado RSU funcione **en tiempo real** sin re-ejecutar el pipeline: los sliders simplemente llaman a `filtrar_junctions_rsu()` con los datos ya almacenados en sesión.

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

| Archivo | Formato | Generado por | Contenido |
|---------|---------|-------------|-----------|
| `map.osm` | XML (OSM) | `descargar_osm.py` | Datos geográficos crudos: nodos, vías, relaciones, edificios, POIs |
| `mapa.net.xml` | XML (SUMO) | `netconvert` | Red vial: junctions (intersecciones), edges (segmentos viales), connections (giros), traffic lights |
| `mapa.poly.xml` | XML (SUMO) | `polyconvert` | Polígonos: edificios, parques, agua, uso del suelo con coordenadas proyectadas |
| `mapa.rou.xml` | XML (SUMO) | `randomTrips.py` | Rutas vehiculares: pares origen-destino y secuencia de edges por ruta |
| `junctions_limpias.json` | JSON | `parsear_xml.py` | Solo intersecciones con `type ≠ internal ∧ type ≠ dead_end`, con coordenadas `{x, y}` |
| `edificios_limpios.json` | JSON | `parsear_xml.py` | Solo edificios, con lista de vértices `[[x₁,y₁], [x₂,y₂], ...]` |

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

1. **Módulo 2:** Visualización de tráfico simulado sobre el mapa usando datos de SUMO
2. **Módulo 3:** Integración con NS-3 para simulación de protocolos VANET
3. **API REST:** Migrar el backend a FastAPI para desacoplar completamente frontend y backend
4. **Docker:** Containerizar la aplicación con SUMO incluido para facilitar despliegues

---

## 📝 Licencia

Trabajo de Integración Curricular — Universidad. Todos los derechos reservados.
