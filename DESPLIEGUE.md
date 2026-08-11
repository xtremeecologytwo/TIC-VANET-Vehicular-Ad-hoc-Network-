# Despliegue de SmartCityNet

La app **no es un frontend estático**: el "frontend" (Streamlit) llama al backend
en el mismo proceso, y ese backend necesita **SUMO** (binarios `netconvert`,
`polyconvert`, `randomTrips`) y **CPLEX** (motor de optimización) en el servidor.
Por eso siempre hace falta un **servidor real** (no un hosting estático) — da igual
si algún día se migra a React.

El repo ya trae un [`Dockerfile`](Dockerfile) que empaqueta Python 3.10 + SUMO +
las dependencias. Con eso el despliegue es prácticamente un clic.

---

## 1. Local (sin Docker)

```bash
python -m venv .venv && .venv\Scripts\activate     # (Linux/Mac: source .venv/bin/activate)
pip install -r requirements.txt
streamlit run app.py
```
Requiere tener **SUMO** instalado y `SUMO_HOME` configurado.

## 2. Local con Docker (recomendado para probar el deploy)

```bash
docker build -t smartcitynet .
docker run -p 8501:8501 smartcitynet
# abrir http://localhost:8501
```

---

## 3. Dónde desplegarlo

| Opción | Sirve | Notas |
|---|---|---|
| **Streamlit Community Cloud** | ❌ No | No permite instalar SUMO ni el motor CPLEX. Solo apps Python puras. |
| **Hugging Face Spaces (Docker SDK)** | ✅ Sí, **gratis** | Sube el repo con este `Dockerfile`; corre Streamlit + SUMO en la imagen. Ideal para el **demo de la defensa**. Para el problema real, incluir CPLEX académico (ver abajo). |
| **Render / Railway / Fly.io** | ✅ Sí | Deploy desde GitHub con el `Dockerfile`. Puede requerir plan de pago por RAM (SUMO + CPLEX). |
| **VPS** (Hetzner, DigitalOcean, Linode) | ✅ Sí | ~$5–12/mes, control total. `docker run` detrás de un Nginx con HTTPS. |
| **Servidor / Azure académico de la EPN** | ✅ Sí (ideal) | Sin costo ni fricción de licencias; se puede instalar CPLEX académico completo. |

**Recomendación:** Hugging Face Spaces (Docker) para un demo público gratuito, o
un VPS/servidor de la EPN si quieres el motor CPLEX completo de forma permanente.

---

## 4. CPLEX en el contenedor

`requirements.txt` instala **docplex** + la edición **Community** de `cplex`
(límite de 1000 variables/restricciones). Con eso funcionan el micro-ejemplo y
escenarios pequeños, pero **no** el problema real (miles de tuplas CVR).

Para el **motor completo** (sin límite):

1. Consigue la **licencia académica gratuita** de IBM (IBM Academic Initiative →
   *ILOG CPLEX Optimization Studio*). Es gratis para estudiantes/docentes.
2. En el `Dockerfile`, tras copiar la app, instala el motor desde el Studio:
   ```dockerfile
   # (ejemplo) copiar el instalador del Studio a la imagen y registrarlo
   COPY cplex_studio /opt/cplex_studio
   RUN python /opt/cplex_studio/python/setup.py install
   ```
   > El motor completo solo soporta **Python 3.7–3.10** — por eso la imagen fija
   > **Python 3.10**.

Sin el motor completo, la app sigue corriendo: al superar el límite Community,
`optimizar_rsu.py` devuelve un estado claro (`community-limit-exceeded`) en vez de
fallar, y el resto del flujo (Módulos 1 y 2) funciona igual.

---

## 5. Notas de producción

- El tema y el modo headless ya están fijados en [`.streamlit/config.toml`](.streamlit/config.toml).
- Los archivos de `output/` se generan en tiempo de ejecución; en un contenedor
  efímero se pierden al reiniciar (está bien: se regeneran desde la interfaz).
  Si quieres conservarlos, monta un volumen en `/app/output`.
- Detrás de un proxy inverso, habilita WebSockets (Streamlit los usa).
