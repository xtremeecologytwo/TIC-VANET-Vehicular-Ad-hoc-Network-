# =====================================================================
# SmartCityNet — imagen de despliegue de la consola VANET (Streamlit)
# =====================================================================
# Empaqueta la app con TODO lo que necesita en el servidor:
#   - Python 3.10  (única versión que corre el motor COMPLETO de CPLEX)
#   - SUMO         (netconvert, polyconvert, randomTrips) para el pipeline
#   - dependencias de requirements.txt (streamlit, folium, docplex, cplex…)
#
# Construir:   docker build -t smartcitynet .
# Ejecutar:    docker run -p 8501:8501 smartcitynet
#              → abrir http://localhost:8501
#
# NOTA sobre CPLEX: `requirements.txt` instala docplex + la edición COMMUNITY
# de cplex (límite 1000 variables), suficiente para el micro-ejemplo y escenas
# pequeñas. Para resolver el problema real (miles de tuplas CVR) copia el motor
# COMPLETO de CPLEX (licencia académica gratuita de IBM) dentro de la imagen —
# ver DESPLIEGUE.md, sección "CPLEX en el contenedor".
# =====================================================================
FROM python:3.10-slim

ENV DEBIAN_FRONTEND=noninteractive \
    SUMO_HOME=/usr/share/sumo \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# --- Dependencias del sistema: SUMO + proyección + curl (healthcheck) ---
RUN apt-get update && apt-get install -y --no-install-recommends \
        sumo sumo-tools proj-bin curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Instalar dependencias Python primero (mejor caché de capas)
COPY requirements.txt .
RUN pip install -r requirements.txt

# Copiar el resto de la app
COPY . .

EXPOSE 8501

# Streamlit expone /_stcore/health cuando el servidor está listo
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fs http://localhost:8501/_stcore/health || exit 1

CMD ["streamlit", "run", "app.py", \
     "--server.port=8501", "--server.address=0.0.0.0", "--server.headless=true"]
