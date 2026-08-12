# Despliegue de SmartCityNet

> **Estado: pendiente.** Todavía no desplegamos. Este documento deja anotado el
> plan y las opciones para cuando toque hacerlo. El `Dockerfile` se creará en ese
> momento (el anterior era del frontend Streamlit, ya retirado).

## Qué hay que servir

La app son **dos piezas**:

1. **API FastAPI** (`api/`) — necesita un **servidor real** porque el backend
   ejecuta **SUMO** (binarios `netconvert`/`polyconvert`/`randomTrips`) y **CPLEX**
   (motor de optimización). Esto no cambia: siempre hará falta un servidor, no un
   hosting estático.
2. **Frontend React** (`web/`) — se compila a estáticos con `npm run build`
   (`web/dist/`). Lo más simple para producción es **servir `web/dist` desde la
   propia FastAPI** (un solo proceso/puerto) y así evitar CORS.

## Plan de despliegue (un contenedor)

Cuando lo hagamos, un `Dockerfile` con dos etapas:

1. **build del frontend**: `node` → `npm ci && npm run build` → `web/dist`.
2. **runtime Python 3.10**: instala SUMO (`apt-get install sumo sumo-tools`) +
   `requirements.txt`, copia el backend/api y el `web/dist`, monta el `dist` como
   estáticos en FastAPI y arranca `uvicorn`.

## Dónde desplegarlo

| Opción | Sirve | Notas |
|---|---|---|
| **Hugging Face Spaces (Docker)** | ✅ gratis | Corre el contenedor con SUMO. Ideal para el **demo de la defensa**. |
| **Render / Railway / Fly.io** | ✅ | Deploy desde GitHub con el `Dockerfile`. Puede requerir plan de pago por RAM. |
| **VPS** (Hetzner/DigitalOcean) | ✅ | ~$5–12/mes, control total, detrás de Nginx con HTTPS. |
| **Servidor / Azure académico de la EPN** | ✅ (ideal) | Sin costo ni fricción de licencias; permite instalar CPLEX académico completo. |
| **Hostings estáticos** (Vercel, Netlify, Streamlit Cloud) | ❌ | No pueden correr SUMO ni CPLEX. |

## CPLEX en el contenedor

`requirements.txt` instala **docplex** + la edición **community** de `cplex`
(límite 1000 variables) — suficiente para escenarios pequeños. Para el problema
real hay que meter el motor **completo**:

1. Consigue la **licencia académica gratuita** de IBM (IBM Academic Initiative →
   *ILOG CPLEX Optimization Studio*).
2. En el `Dockerfile`, tras copiar la app, instálalo desde el Studio:
   `python <CPLEX_Studio>/python/setup.py install`.

> El motor completo sólo soporta **Python 3.7–3.10** — por eso la imagen fija
> Python 3.10. Sin él, la app sigue corriendo: `optimizar_rsu` devuelve un estado
> claro al superar el límite community, y el resto del flujo funciona igual.
