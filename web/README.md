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

En dev, Vite proxya `/api` → `:8000` (ver `vite.config.ts`), así que no hay CORS.
Si ya hay un escenario en `output/`, la API lo carga al arrancar y el SPA lo
rehidrata (muestra edificios y permite optimizar directamente).

## Build de producción

```bash
npm run build      # genera web/dist/ (estático)
```
En producción, el `dist/` se sirve como estático y la API corre aparte (o se
sirve el `dist/` desde la propia FastAPI). Ver `../DESPLIEGUE.md`.

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
  actualiza mapa + KPIs. Controla también el *play* de la línea de tiempo.
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
- [x] Tablas de tuplas V2I/V2V · matrices A/B · multisalto
- [ ] Alinear el `output/` de demo (el pre-cargado es un mosaico de sesiones)
- [ ] Deploy combinado (servir `web/dist` desde FastAPI) — ver `../DESPLIEGUE.md`
