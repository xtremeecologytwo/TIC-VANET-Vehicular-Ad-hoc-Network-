# SmartCityNet — Frontend React (migración)

SPA en **React + TypeScript + Vite** que consume la **API FastAPI** (`../api/`).
Es la migración del frontend Streamlit: la ciencia (SUMO, LoS, multisalto,
optimización) sigue en `backend/` y `optimizacion/`, expuesta como HTTP.

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

## Estructura

```
web/src/
├── api/client.ts            # cliente tipado de la API
├── design/tokens.css        # sistema de diseño (consola clara)
├── components/ScenarioMap.tsx  # mapa react-leaflet + dibujo + capas
├── App.tsx                  # layout de consola + flujo M1→M2→M3
└── App.css                  # estilos de la consola + marco "plotter"
```

## Estado de la migración

- [x] API FastAPI que reutiliza el backend (scenario, rsu, simulate, connectivity, optimize)
- [x] SPA: layout de consola, stepper M1/M2/M3, mapa con dibujo de rectángulo,
      edificios + RSU candidatas/desplegadas, KPIs, flujo completo contra la API
- [ ] Tablas de tuplas V2I/V2V y visor de matrices A/B (pendiente)
- [ ] Visor multisalto (R_h, S_h, D_H) (pendiente)
- [ ] Animación de vehículos por instante en el mapa (endpoint `/api/connectivity` ya listo)
