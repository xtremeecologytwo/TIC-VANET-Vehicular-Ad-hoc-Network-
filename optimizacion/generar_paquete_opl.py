"""
generar_paquete_opl.py — arma la carpeta que se le entrega al profesor
=======================================================================
Produce un **proyecto de OPL listo para abrir** en IBM ILOG CPLEX Optimization
Studio, con los modelos, los datos y las configuraciones de ejecución ya
definidas. El objetivo es que quien lo reciba pueda comprobar los resultados
**con su propio CPLEX**, sin instalar Python ni tocar el resto del proyecto.

Qué genera:

    paquete_opl/
      .project            <- para que el IDE lo reconozca como proyecto OPL
      .oplproject         <- configuraciones de ejecución (los 4 casos)
      rsu_model_lex.mod   <- modelo lexicográfico de 3 niveles (el que usa docplex)
      rsu_model.mod       <- modelo original de suma ponderada (Ec. 1)
      rsu_micro.dat       <- micro-ejemplo, resultado conocido: {R1, R3}
      rsu_backend.dat     <- el escenario real generado por la aplicación
      LEEME.md            <- cómo ejecutarlo, y qué debe salir
      comparacion.txt     <- salida de comparar_motores.py (docplex vs oplrun)

Uso:
    python optimizacion/generar_paquete_opl.py
    python optimizacion/generar_paquete_opl.py --salida D:\\entrega
"""

import os
import shutil
import subprocess
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)

# Todo lo que este modulo escribe. Se borra al empezar cada corrida para que la
# carpeta refleje SIEMPRE el escenario actual y no una mezcla.
ARCHIVOS_DEL_PAQUETE = (
    "rsu_model_lex.mod", "rsu_model.mod", "rsu_micro.dat", "rsu_backend.dat",
    ".project", ".oplproject", "LEEME.md", "comparacion.txt",
)

PROJECT = """<?xml version="1.0" encoding="UTF-8"?>
<projectDescription>
\t<name>rsu_validacion</name>
\t<comment>Despliegue optimo de RSU - validacion cruzada docplex / oplrun</comment>
\t<projects>
\t</projects>
\t<buildSpec>
\t</buildSpec>
\t<natures>
\t\t<nature>ilog.odms.ide.core.opl.project.nature</nature>
\t</natures>
</projectDescription>
"""

OPLPROJECT = """<?xml version="1.0" encoding="ASCII"?>
<project>
  <version>1.0</version>
  <description>Ubicacion optima de RSU en una VANET (Urquiza-Aguiar et al., 2016).
Validacion cruzada: el mismo modelo resuelto por OPL y por docplex.</description>
  <configs>
    <config category="opl" default="true" name="1. Lexicografico - micro-ejemplo">
      <ref type="model" name="rsu_model_lex.mod"></ref>
      <ref type="data" name="rsu_micro.dat"></ref>
    </config>
    <config category="opl" default="false" name="2. Lexicografico - escenario real">
      <ref type="model" name="rsu_model_lex.mod"></ref>
      <ref type="data" name="rsu_backend.dat"></ref>
    </config>
    <config category="opl" default="false" name="3. Suma ponderada - micro-ejemplo">
      <ref type="model" name="rsu_model.mod"></ref>
      <ref type="data" name="rsu_micro.dat"></ref>
    </config>
    <config category="opl" default="false" name="4. Suma ponderada - escenario real">
      <ref type="model" name="rsu_model.mod"></ref>
      <ref type="data" name="rsu_backend.dat"></ref>
    </config>
  </configs>
</project>
"""

LEEME = """# Validación del modelo de despliegue de RSU

Paquete autocontenido para comprobar, **con su propio IBM ILOG CPLEX**, los
resultados que produce la aplicación.

## Qué se está comprobando

La aplicación resuelve el modelo de Urquiza-Aguiar, Tripp-Barba y Aguilar
Igartua (2016) usando **`docplex`**, la librería de Python que construye el
modelo en memoria y lo entrega al motor CPLEX.

Este paquete contiene una implementación **independiente** de la misma
formulación, escrita en **lenguaje OPL**. Son dos traducciones distintas del
mismo modelo matemático: si ambas dan el mismo resultado sobre los mismos datos,
la traducción es correcta.

## Cómo abrirlo en CPLEX Optimization Studio

1. **File → Open → Project...** y seleccionar esta carpeta.
2. En el panel de proyecto aparecen cuatro configuraciones de ejecución.
3. Clic derecho sobre una → **Run this**.

Desde la línea de comandos, sin el IDE:

```
oplrun rsu_model_lex.mod rsu_micro.dat
oplrun rsu_model_lex.mod rsu_backend.dat
```

## Las cuatro configuraciones

| # | Modelo | Datos | Para qué |
|---|---|---|---|
| 1 | `rsu_model_lex.mod` | `rsu_micro.dat` | Comprobación rápida: resultado conocido |
| 2 | `rsu_model_lex.mod` | `rsu_backend.dat` | El escenario real de la aplicación |
| 3 | `rsu_model.mod` | `rsu_micro.dat` | Formulación original (suma ponderada) |
| 4 | `rsu_model.mod` | `rsu_backend.dat` | Ídem sobre el escenario real |

**Por qué hay dos modelos.** `rsu_model.mod` implementa la Ec. 1 tal cual: una
**suma** del coste de instalación y del tráfico penalizado. `rsu_model_lex.mod`
resuelve la misma formulación por **prioridades** (`staticLex`), en tres niveles:

1. minimizar la carga sin cobertura,
2. entre esas soluciones, la que use menos RSU,
3. entre esas, la de menos saltos.

La aplicación usa hoy el lexicográfico, así que **la configuración 2 es la que
hay que comparar** contra sus resultados. Comparar la suma ponderada contra el
lexicográfico no probaría nada: son criterios distintos.

## Qué debe salir

### Micro-ejemplo (configuración 1)

Ejemplo pequeño con solución conocida de antemano. Debe desplegar **R1 y R3**:

```
OBJ_DESCONEXION=0
OBJ_INSTALACION=2
OBJ_TRAFICO=9
OBJETIVO=11
SELECTED=1,3,
```

### Escenario real (configuración 2)

Los valores dependen del escenario que se haya generado. Lo que importa es que
coincidan con los de `docplex`; el archivo **`comparacion.txt`** de esta carpeta
trae esa comparación campo a campo, generada automáticamente.

## Sobre el conjunto de RSU elegidas

Puede ocurrir que ambos motores desplieguen **el mismo número** de RSU pero **no
exactamente las mismas**. Eso **no es un error**.

El problema tiene muchas soluciones óptimas equivalentes: hay candidatas a pocos
metros unas de otras, con la misma cobertura y el mismo coste, y son
intercambiables. Cada motor se queda con una según cómo recorra el árbol de
búsqueda. Lo que certifica que el modelo está bien traducido es que ambos
alcancen **el mismo valor objetivo, el mismo número de antenas y la misma
cobertura** — no que coincida la selección concreta.

## Formato de la salida

El bloque `execute` de cada `.mod` imprime pares `CLAVE=valor` para que se
puedan leer sin depender del formato del log de CPLEX:

| Clave | Significado |
|---|---|
| `OBJ_DESCONEXION` | carga que se queda sin cobertura (nivel 1) |
| `OBJ_INSTALACION` | coste de las antenas desplegadas (nivel 2) |
| `OBJ_TRAFICO` | coste por saltos del tráfico servido (nivel 3) |
| `OBJETIVO` | valor de la Ec. 1 original, para poder comparar |
| `SELECTED` | ids de las RSU desplegadas |
| `N_RSU` | cuántas |
| `N_PARES` | pares (instante, vehículo) del escenario |
| `DESCONECTADOS` / `DIRECTOS` / `MULTISALTO` | reparto de la carga |
| `ESTADO` | código de estado de CPLEX (301 = óptimo multi-objetivo) |
"""


def construir_paquete(destino: str, dat_path: str | None = None,
                      comparar: bool = True, meta: dict | None = None) -> dict:
    """
    Arma el paquete de validación en `destino`.

    Parámetros:
        destino: carpeta donde escribir el proyecto (se crea si no existe).
        dat_path: escenario real a incluir. Por defecto, el
            `optimizacion/rsu_backend.dat` que escribe `/api/optimize`, es decir
            **el escenario que se está probando en ese momento**.
        comparar: si True, ejecuta `comparar_motores.py` y guarda el informe.
            Es lo que hace el paquete autoexplicativo, pero cuesta resolver dos
            veces; se puede desactivar para ir rápido.
        meta: datos del escenario (nº de vehículos, H, radio...) que se añaden
            al LEEME para que quien lo reciba sepa QUÉ está reproduciendo.

    Retorna:
        dict con "destino", "archivos" [(nombre, bytes)], "coincide" (True/False/
        None si no se comparó) e "informe" (texto de la comparación).
    """
    dat_path = dat_path or os.path.join(AQUI, "rsu_backend.dat")
    destino = os.path.abspath(destino)
    os.makedirs(destino, exist_ok=True)

    # La carpeta se REUTILIZA (no se borra y se vuelve a crear): asi sigue
    # existiendo entre corridas y se puede tener abierta en el IDE. Pero se
    # vacia de lo que el paquete produce, para que nunca queden restos de un
    # escenario anterior mezclados con el actual.
    for viejo in ARCHIVOS_DEL_PAQUETE:
        ruta = os.path.join(destino, viejo)
        if os.path.exists(ruta):
            try:
                os.remove(ruta)
            except OSError:
                pass

    for nombre in ("rsu_model_lex.mod", "rsu_model.mod", "rsu_micro.dat"):
        origen = os.path.join(AQUI, nombre)
        if os.path.exists(origen):
            shutil.copyfile(origen, os.path.join(destino, nombre))

    hay_real = os.path.exists(dat_path)
    if hay_real:
        shutil.copyfile(dat_path, os.path.join(destino, "rsu_backend.dat"))

    # El LEEME lleva una cabecera con el escenario concreto: sin eso, quien lo
    # recibe no sabe si el .dat corresponde a la captura que le enseñaron.
    leeme = LEEME
    if meta:
        lineas = ["", "## Escenario incluido", ""]
        for k, v in meta.items():
            # Una clave entre guiones actua como subtitulo, no como dato: sirve
            # para separar los parametros del resultado que hay que reproducir.
            if k.startswith("---") and k.endswith("---"):
                lineas += ["", "### " + k.strip("- ").capitalize(), ""]
            else:
                lineas.append(f"- **{k}**: {v}")
        lineas.append("")
        i = leeme.index("## Qué se está comprobando")
        leeme = leeme[:i] + "\n".join(lineas) + "\n" + leeme[i:]

    for nombre, contenido in ((".project", PROJECT),
                              (".oplproject", OPLPROJECT),
                              ("LEEME.md", leeme)):
        with open(os.path.join(destino, nombre), "w", encoding="utf-8") as f:
            f.write(contenido)

    informe, coincide = "", None
    if comparar and hay_real:
        r = subprocess.run(
            [sys.executable, os.path.join(AQUI, "comparar_motores.py"),
             "--dat", dat_path],
            capture_output=True, text=True, cwd=RAIZ)
        informe = (r.stdout or "") + (("\n--- stderr ---\n" + r.stderr)
                                      if r.stderr else "")
        coincide = "los dos motores COINCIDEN" in informe
        with open(os.path.join(destino, "comparacion.txt"), "w",
                  encoding="utf-8") as f:
            f.write(informe)

    archivos = sorted(
        (n, os.path.getsize(os.path.join(destino, n)))
        for n in os.listdir(destino)
        if os.path.isfile(os.path.join(destino, n)))

    return {"destino": destino, "archivos": archivos,
            "coincide": coincide, "informe": informe,
            "escenario_real": hay_real}


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser(description="Arma el paquete OPL de validacion")
    ap.add_argument("--salida", default=os.path.join(RAIZ, "paquete_opl"),
                    help="carpeta destino")
    ap.add_argument("--dat", default=os.path.join(AQUI, "rsu_backend.dat"),
                    help="escenario real a incluir")
    ap.add_argument("--sin-comparacion", action="store_true",
                    help="no ejecutar comparar_motores.py (mas rapido)")
    args = ap.parse_args()

    if not os.path.exists(args.dat):
        print(f"AVISO: no existe {args.dat}. El paquete ira sin escenario real;")
        print("       genera uno desde la aplicacion y vuelve a ejecutar esto.")

    res = construir_paquete(args.salida, args.dat,
                            comparar=not args.sin_comparacion)
    if res["informe"]:
        print(res["informe"])

    print(f"\nPaquete listo en: {res['destino']}")
    for nombre, tam in res["archivos"]:
        print("   %-20s %8.1f KB" % (nombre, tam / 1024))
    print("\nEntrega esa carpeta (o un .zip de ella).")


if __name__ == "__main__":
    main()
