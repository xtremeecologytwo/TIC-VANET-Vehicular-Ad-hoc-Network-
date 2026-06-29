"""
Módulo de Simulación SUMO — Floating Car Data (FCD)
====================================================
Ejecuta el simulador SUMO para obtener la posición exacta (x, y) de
cada vehículo en cada instante de tiempo de la simulación.

Utiliza la salida FCD (Floating Car Data), que es un archivo XML donde
SUMO registra, para cada timestep, la posición, velocidad y ángulo de
cada vehículo activo en la red.

Flujo:
  1. Generar archivo de configuración mapa.sumocfg
  2. Ejecutar `sumo -c mapa.sumocfg` como subproceso
  3. Parsear el fcd.xml resultante → diccionario {timestep: [vehículos]}
"""

import os
import subprocess
import xml.etree.ElementTree as ET


def generar_sumocfg(output_dir: str, tiempo_simulacion: float = 100.0,
                    periodo_fcd: float = 1.0) -> str:
    """
    Genera el archivo de configuración SUMO (.sumocfg) necesario para
    ejecutar la simulación de tráfico.

    El archivo .sumocfg le indica a SUMO qué red vial usar, qué rutas
    vehiculares cargar, cuánto tiempo simular, y qué salidas generar.

    Parámetros:
        output_dir: Directorio donde están los archivos de la red y rutas.
        tiempo_simulacion: Duración total de la simulación en segundos.
                          Debe ser >= al tiempo de salida del último vehículo
                          en las rutas, más el tiempo que tarda en completar
                          su ruta, para capturar todo el movimiento.
        periodo_fcd: Cada cuántos segundos SUMO escribe la posición de los
                          vehículos en el FCD. Por defecto 1.0 (cada segundo).
                          Si el muestreo es por minutos (ej. 120 s = 2 min),
                          conviene igualarlo para que el fcd.xml no sea enorme:
                          SUMO solo escribe en t = 0, periodo, 2·periodo, ...

    Retorna:
        Ruta absoluta al archivo .sumocfg generado.

    Nota sobre el tiempo de simulación:
        Si un vehículo parte en t=99 y su ruta dura 60 segundos, necesitamos
        que la simulación dure al menos 159 segundos para capturar su
        recorrido completo. Por eso se recomienda un tiempo_simulacion
        mayor que el tiempo de generación de vehículos.
    """
    net_path = os.path.join(output_dir, "mapa.net.xml")
    rou_path = os.path.join(output_dir, "mapa.rou.xml")
    fcd_path = os.path.join(output_dir, "fcd.xml")
    cfg_path = os.path.join(output_dir, "mapa.sumocfg")

    # Estructura XML del archivo de configuración SUMO
    # Referencia: https://sumo.dlr.de/docs/sumo.html#configuration_files
    contenido = f"""<?xml version="1.0" encoding="UTF-8"?>
<configuration xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
               xsi:noNamespaceSchemaLocation="http://sumo.dlr.de/xsd/sumoConfiguration.xsd">

    <!-- Archivos de entrada: red vial y rutas vehiculares -->
    <input>
        <net-file value="{os.path.basename(net_path)}"/>
        <route-files value="{os.path.basename(rou_path)}"/>
    </input>

    <!-- Duración de la simulación -->
    <time>
        <begin value="0"/>
        <end value="{tiempo_simulacion}"/>
    </time>

    <!-- Salida FCD: posición de cada vehículo. device.fcd.period controla
         cada cuántos segundos se registra la posición (alineado al reloj
         global: t = 0, periodo, 2·periodo, ...), para que el muestreo por
         minutos no genere un archivo gigante y todos los autos queden
         registrados en los MISMOS instantes (necesario para las matrices). -->
    <output>
        <fcd-output value="{os.path.basename(fcd_path)}"/>
    </output>
    <processing>
        <device.fcd.period value="{periodo_fcd}"/>
    </processing>

    <!-- Configuración del reporte: suprimir warnings para ejecución limpia -->
    <report>
        <no-warnings value="true"/>
        <no-step-log value="true"/>
    </report>

</configuration>
"""

    with open(cfg_path, "w", encoding="utf-8") as f:
        f.write(contenido)

    return cfg_path


def ejecutar_simulacion_sumo(output_dir: str,
                              tiempo_simulacion: float = 100.0,
                              periodo_fcd: float = 1.0) -> tuple[str | None, str | None]:
    """
    Ejecuta la simulación de tráfico SUMO y genera el archivo FCD.

    Esta función:
      1. Genera el archivo de configuración .sumocfg
      2. Ejecuta `sumo` (versión sin GUI) como subproceso
      3. Verifica que el archivo FCD se haya generado correctamente

    Utiliza `sumo` en lugar de `sumo-gui` porque:
      - No requiere interfaz gráfica (puede ejecutarse en servidor)
      - Es más rápido al no renderizar gráficos
      - Es compatible con Streamlit (que ya tiene su propia interfaz)

    Parámetros:
        output_dir: Directorio con los archivos de red y rutas.
        tiempo_simulacion: Duración total de la simulación en segundos.

    Retorna:
        (ruta_fcd, None) si fue exitoso,
        (None, mensaje_error) si hubo error.
    """
    # Paso 1: Generar el archivo de configuración
    cfg_path = generar_sumocfg(output_dir, tiempo_simulacion, periodo_fcd)
    fcd_path = os.path.join(output_dir, "fcd.xml")

    # Paso 2: Ejecutar SUMO como subproceso
    # Usamos os.path.basename porque cwd=output_dir hace que SUMO
    # busque los archivos relativos al directorio de salida
    cmd = ["sumo", "-c", os.path.basename(cfg_path)]

    try:
        resultado = subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True,
            timeout=600,  # 10 minutos máximo para simulaciones largas (ej. 2-3 h)
            cwd=output_dir  # Ejecutar desde el directorio de salida
        )
    except FileNotFoundError:
        return None, (
            "No se encontró el ejecutable 'sumo'. "
            "¿Está SUMO instalado y el ejecutable 'sumo' en el PATH del sistema? "
            "Nota: se necesita 'sumo' (sin GUI), no 'sumo-gui'."
        )
    except subprocess.CalledProcessError as e:
        return None, f"Error en la simulación SUMO:\n{e.stderr[:500]}"
    except subprocess.TimeoutExpired:
        return None, "La simulación SUMO excedió el tiempo máximo (10 minutos)."

    # Paso 3: Verificar que el FCD se generó
    if not os.path.isfile(fcd_path):
        return None, "La simulación terminó pero no se generó el archivo FCD."

    if os.path.getsize(fcd_path) < 100:
        return None, (
            "El archivo FCD está casi vacío. Posibles causas:\n"
            "- Las rutas no son válidas para la red actual\n"
            "- El tiempo de simulación es demasiado corto\n"
            "- No hay vehículos activos en la simulación"
        )

    return fcd_path, None


def parsear_fcd(fcd_path: str,
                step_intervalo: float = 1.0) -> tuple[dict | None, str | None]:
    """
    Parsea el archivo FCD (Floating Car Data) generado por SUMO y extrae
    la posición de cada vehículo en cada timestep.

    El archivo FCD tiene la estructura:
    ```xml
    <fcd-export>
        <timestep time="0.00">
            <vehicle id="0" x="128.60" y="206.25" angle="90" speed="0.00"
                     pos="0.00" lane="24734058#1_0" slope="0.00"/>
        </timestep>
        <timestep time="1.00">
            <vehicle id="0" x="130.50" y="206.25" .../>
            <vehicle id="1" x="348.37" y="212.89" .../>
        </timestep>
    </fcd-export>
    ```

    Notas importantes:
    - Las coordenadas x, y están en el sistema SUMO (metros UTM con offset),
      que es el MISMO sistema que usan edificios y junctions/RSU.
    - Un vehículo aparece en un timestep solo si está ACTIVO en la red
      (ya partió y aún no llegó a su destino).
    - step_intervalo permite muestrear cada N segundos en lugar de cada 1s.

    Parámetros:
        fcd_path: Ruta al archivo fcd.xml generado por SUMO.
        step_intervalo: Intervalo de muestreo en segundos. Si es 1.0, se
                       toma cada timestep. Si es 2.0, se toma cada 2 segundos.

    Retorna:
        (diccionario_fcd, None) si fue exitoso,
        (None, mensaje_error) si hubo error.

    Estructura del diccionario retornado:
        {
            0.0: [
                {"id": "0", "x": 128.6, "y": 206.25, "speed": 0.0, "angle": 90.0},
                ...
            ],
            1.0: [...],
            ...
        }
    """
    try:
        tree = ET.parse(fcd_path)
        root = tree.getroot()
    except ET.ParseError as e:
        return None, f"Error parseando FCD XML: {e}"
    except FileNotFoundError:
        return None, f"Archivo FCD no encontrado: {fcd_path}"

    datos_fcd = {}
    ultimo_t_registrado = -step_intervalo  # Para controlar el muestreo

    for timestep in root.findall("timestep"):
        t = float(timestep.get("time", "0"))

        # Aplicar el intervalo de muestreo:
        # Solo registrar si ha pasado al menos step_intervalo desde el último
        if t - ultimo_t_registrado < step_intervalo - 0.001:
            continue

        ultimo_t_registrado = t
        vehiculos_en_t = []

        for vehicle in timestep.findall("vehicle"):
            try:
                vehiculos_en_t.append({
                    "id": vehicle.get("id"),
                    "x": float(vehicle.get("x", "0")),
                    "y": float(vehicle.get("y", "0")),
                    "speed": float(vehicle.get("speed", "0")),
                    "angle": float(vehicle.get("angle", "0")),
                })
            except (ValueError, TypeError):
                continue

        # Solo registrar timesteps que tengan vehículos activos
        if vehiculos_en_t:
            datos_fcd[t] = vehiculos_en_t

    if not datos_fcd:
        return None, "El archivo FCD no contiene datos de vehículos."

    return datos_fcd, None
