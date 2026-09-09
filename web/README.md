# SmartCityNet — Frontend React

SPA en **React + TypeScript + Vite** que consume la **API FastAPI** (`../api/`).
Es el frontend del proyecto: la ciencia (SUMO, LoS, multisalto, optimización)
vive en `backend/` y `optimizacion/`, expuesta como HTTP por `api/`.

```
web/ (React SPA, :5173)  ──HTTP /api──►  api/ (FastAPI, :8000)  ──►  backend/ + optimizacion/
```

## Correr en desarrollo

Hacen falta **dos procesos**: la API y el SPA.

```bash
# 1) API (desde la RAÍZ del repo, en el venv con SUMO + docplex/CPLEX)
uvicorn api.main:app --reload --port 8000

# 2) Frontend (desde web/)
npm install        # solo la primera vez
npm run dev        # abre http://localhost:5173
```

### Clave del mapa base (opcional)

CARTO exige una API key para sus teselas raster; sin ella el mapa sale con la
marca de agua *"API KEY REQUIRED"*. Para quitarla:

```bash
cp .env.example .env.local     # copy .env.example .env.local  en Windows
# y pon tu clave en VITE_CARTO_KEY=
```

La clave se consigue gratis en [carto.com/basemaps/apikey](https://carto.com/basemaps/apikey)
(5 000 000 de teselas al mes). `.env.local` **no se versiona**. Sin clave la app
funciona igual, solo que con la marca de agua.

En dev, Vite proxya `/api` → `:8000` (ver `vite.config.ts`), así que no hay CORS.
Si ya hay un escenario en `output/`, la API lo carga al arrancar y el SPA lo
rehidrata (muestra edificios y permite optimizar directamente).

## Build de producción

```bash
npm run build      # genera web/dist/ (estático)
```
El `dist/` es estático y la API corre aparte. (El empaquetado/despliegue se hará
más adelante.)

## Estructura y responsabilidades

```
web/src/
├── main.tsx                    # punto de entrada (monta <App/>)
├── App.tsx                     # orquestador: estado, flujo M1→M2→M3, línea de tiempo
├── App.css                     # estilos de la consola + marco "plotter"
├── api/client.ts               # cliente HTTP tipado (una función por endpoint)
├── design/tokens.css           # sistema de diseño (paleta, tipografía)
└── components/
    ├── ScenarioMap.tsx         # mapa react-leaflet: dibujo del área + capas
    └── ResultsTabs.tsx         # tablas de tuplas, matrices A/B, multisalto
```

- **`client.ts`** — expone `api.generate/filterRsu/simulate/connectivity/optimize/
  timesteps/tuplesV2i/tuplesV2v/multihop` con sus tipos de respuesta. Un solo lugar
  para hablar con el backend.
- **`App.tsx`** — guarda los parámetros y los resultados; cada botón dispara una
  acción (`generar`, `filtrar`, `simular`, `optimizar`) que llama al cliente y
  actualiza mapa + KPIs. En **M1** hay tres *presets* de carga —Rápido (500),
  Medio (5 000), Denso (50 000)— que fijan a la vez vehículos, duración y
  muestreo, porque son las tres cifras que se mueven juntas: los pares
  (instante, vehículo) son su producto y son los que deciden si la optimización
  termina. Debajo se muestra el nº de instantes resultante, para verlo **antes**
  de lanzar. Controla también el *play* de la línea de tiempo. En
  **M3** viven dos casillas: *"Limitar nº de RSU (MaxR)"* — apagada envía
  `max_rsu: null` (sin límite efectivo, el comportamiento por defecto), encendida
  envía el número escrito — y *"Limitar el tiempo del solver"*, encendida en 60 s
  por defecto, que apagada envía `limite_tiempo: null` para que CPLEX busque hasta
  demostrar el óptimo. Una tercera, *"Resolver por prioridades"*, activa el
  multi-objetivo lexicográfico (`lexicografico: true`, por defecto): CPLEX
  minimiza en tres niveles — 1º la carga sin cobertura, 2º el nº de RSU y 3º el
  coste por saltos. Los KPIs **MaxR**, **Solver** y **Tiempo solver** dejan
  constancia de con qué valores se resolvió.
- **`ScenarioMap.tsx`** — `DrawRectangle` selecciona el área con **2 clics** (sin
  leaflet-draw); `FitBounds` encuadra e invalida el tamaño (evita el desalineo del
  primer render). Capas: edificios (GeoJSON), RSU candidatas/desplegadas y, por
  instante, vehículos + enlaces V2I/V2V.
- **`ResultsTabs.tsx`** — pestañas de tuplas, rejillas de las matrices A/B y el
  resumen multisalto del instante activo.

## Estado

- [x] API FastAPI que reutiliza el backend (scenario, rsu, simulate, connectivity,
      optimize, tuples, multihop)
- [x] Consola: stepper M1/M2/M3, **selección del área por 2 clics**, edificios +
      RSU candidatas/desplegadas, KPIs, flujo completo contra la API
- [x] Animación de vehículos + enlaces V2I/V2V por instante (línea de tiempo)
- [x] Tablas de tuplas V2I/V2V · matrices A/B · multisalto (resumen + visor Rₕ/Sₕ/D_H)
- [x] Flujo completo verificado end-to-end con SUMO real (generar→filtrar→simular→optimizar)
- [x] `output/` de demo consistente (una sola corrida; no se versiona)
- [x] Filtros en las tablas de tuplas · círculos de cobertura de RSU · botón "Nuevo escenario"
- [x] Control de **MaxR** (límite de RSU desplegables) en el panel M3
- [x] Control del **tope de tiempo del solver** (5–3600 s, o sin límite)
- [x] Casilla **Resolver por prioridades**: multi-objetivo lexicográfico de
      CPLEX en 3 niveles (cobertura → nº de RSU → saltos) en vez de la suma
      ponderada; deja `penal_desconexion` sin efecto
- [x] KPIs **Solver** / **Tiempo solver**: si el óptimo está demostrado o si CPLEX
      se cortó por el límite de tiempo, y cuántos segundos consumió el motor
- [x] KPIs **Cobertura** / **Desconectados** / **Multisalto**: qué porcentaje de
      los pares (instante, vehículo) queda comunicado y por qué vía
- [x] Cronómetro por etapa en la consola del backend (`api/cronometro.py`)
- [x] *Presets* de carga (Rápido/Medio/Denso) + nº de instantes visible antes de lanzar
- [x] Campo **Vehículos** escribible de verdad: se puede vaciar y no deja el
      mínimo plantado delante de lo que se teclea
- [ ] Empaquetado/despliegue (más adelante)
