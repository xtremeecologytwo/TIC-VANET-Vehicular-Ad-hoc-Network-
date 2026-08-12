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

- [x] API FastAPI que reutiliza el backend (scenario, rsu, simulate, connectivity,
      optimize, tuples, multihop)
- [x] SPA: layout de consola, stepper M1/M2/M3, mapa con dibujo de rectángulo,
      edificios + RSU candidatas/desplegadas, KPIs, flujo completo contra la API
- [x] Animación de vehículos + enlaces V2I/V2V por instante (línea de tiempo)
- [x] Tablas de tuplas V2I/V2V
- [x] Visor de matrices A/B por instante
- [x] Visor multisalto (resumen por salto R_h/S_h + desconectados)
- [ ] Alinear el `output/` de demo (el pre-cargado es un mosaico de sesiones)
- [ ] Deploy combinado (servir `web/dist` desde FastAPI) — ver `../DESPLIEGUE.md`
