# Rama `opl-validacion` — comprobar docplex contra `oplrun`

Esta rama sale de `react-migration` y añade un **segundo camino de resolución**
del modelo de despliegue de RSU, ejecutado por el binario `oplrun` de IBM ILOG
CPLEX Optimization Studio, como se hacía originalmente.

## Para qué

Para **validación cruzada**. El proyecto resuelve hoy con `docplex`, una
librería que construye el modelo en memoria desde Python. Esta rama mantiene una
implementación **independiente** de la misma formulación, escrita en lenguaje
OPL. Dos traducciones distintas del mismo modelo matemático deben dar el mismo
resultado; si no lo dan, una de las dos está mal.

No es una rama para desarrollar: es un banco de pruebas para poder afirmar, con
evidencia, que los números que salen de `docplex` son correctos.

## Qué hay aquí

| Archivo | Qué es |
|---|---|
| `rsu_model.mod` | Modelo OPL original — **suma ponderada** (Ec. 1 tal cual) |
| `rsu_model_lex.mod` | Modelo OPL **lexicográfico de 3 niveles** — replica lo que hace `docplex` hoy |
| `resolver_opl.py` | Ejecuta `oplrun` y devuelve el resultado con la misma forma que `optimizar()` |
| `comparar_motores.py` | Resuelve los mismos datos con los dos motores y compara campo a campo |

`rsu_model_lex.mod` es nuevo porque el `.mod` original implementa la Ec. 1 como
una suma, mientras que `docplex` pasó a resolver por prioridades. Comparar la
suma contra el lexicográfico no probaría nada: **hay que comparar lo mismo con
lo mismo**.

## Cómo se usa

```bash
# Comprobación rápida sobre el micro-ejemplo (resultado conocido: {R1, R3})
python optimizacion/comparar_motores.py --micro

# Sobre el escenario real que haya en optimizacion/rsu_backend.dat
python optimizacion/comparar_motores.py

# Resolver solo con OPL, sin comparar
python optimizacion/resolver_opl.py --micro
python optimizacion/resolver_opl.py --dat optimizacion/rsu_backend.dat
python optimizacion/resolver_opl.py --dat ... --suma   # el modelo de suma ponderada
```

`oplrun` se busca solo en las rutas habituales de CPLEX Studio en Windows. Si
está en otro sitio:

```powershell
$env:OPLRUN = "D:\ruta\a\oplrun.exe"
```

## Qué se compara, y qué NO

Se comparan las magnitudes que **tienen que ser iguales**:

- los tres valores objetivo (desconexión, instalación, tráfico),
- el valor de la Ec. 1,
- el número de RSU desplegadas,
- la cobertura y el reparto por saltos (directos, multisalto, desconectados).

**El conjunto concreto de RSU elegidas NO tiene por qué coincidir**, y que
difiera no es un fallo. El problema tiene muchas soluciones óptimas equivalentes
—candidatas casi intercambiables, a pocos metros unas de otras y con la misma
cobertura y coste— y cada motor puede quedarse con una distinta según cómo
recorra el árbol de búsqueda. Lo que debe coincidir es el **valor**, no la
elección. Por eso el comparador lo informa aparte, como dato.

## Resultados

### Micro-ejemplo (`rsu_micro.dat`)

Todas las magnitudes coinciden:

| magnitud | docplex | oplrun | |
|---|---|---|---|
| obj 1 · desconexión | 0,00 | 0,00 | OK |
| obj 2 · instalación | 2,00 | 2,00 | OK |
| obj 3 · tráfico | 9,00 | 9,00 | OK |
| objetivo (Ec. 1) | 11,00 | 11,00 | OK |
| RSU desplegadas | 2 | 2 | OK |
| cobertura | 100,00 % | 100,00 % | OK |
| directos / multisalto | 3 / 3 | 3 / 3 | OK |

Y además eligieron **las mismas** dos antenas, `{R1, R3}`, que es el resultado
correcto conocido de antemano para ese ejemplo.

### Escenario real

Sobre `rsu_backend.dat` (8 526 tuplas CVR, 2 387 RSU candidatas, 1 532 pares
instante-vehículo). **Las diez magnitudes coinciden**:

| magnitud | docplex | oplrun | |
|---|---|---|---|
| obj 1 · desconexión | 2 430,00 | 2 430,00 | OK |
| obj 2 · instalación | 4 110,00 | 4 110,00 | OK |
| obj 3 · tráfico | 13 360,00 | 13 360,00 | OK |
| objetivo (Ec. 1) | 2 447 470,00 | 2 447 470,00 | OK |
| **RSU desplegadas** | **411** | **411** | OK |
| pares totales | 1 532 | 1 532 | OK |
| desconectados | 243 | 243 | OK |
| directos (1 salto) | 1 246 | 1 246 | OK |
| multisalto | 43 | 43 | OK |
| **cobertura** | **84,14 %** | **84,14 %** | OK |

Ambos con estado `multi-objective optimal`: óptimo demostrado, no cortado por
tiempo. docplex tardó 1,7 s y oplrun 0,8 s.

**RSU en común: 279 de 411.** Los conjuntos difieren y eso es exactamente lo
esperado: con 2 387 candidatas para cubrir 1 532 pares hay muchísimas soluciones
óptimas equivalentes, y cada motor se queda con una según cómo recorra el árbol.
Lo que certifica el modelo es que **las dos llegan al mismo valor con el mismo
número de antenas y la misma cobertura**, no que elijan las mismas.

Es, de hecho, la evidencia más útil de las dos: dos implementaciones
independientes, partiendo de los mismos datos y por caminos distintos,
convergen en el mismo óptimo.

## Nota sobre el límite de tiempo

`oplrun` no expone el límite de tiempo del solver por línea de comandos, así que
`resolver_opl.py` aplica un tope al **proceso** completo, no al motor. Para una
comparación limpia conviene dejar que ambos terminen sin tope: si uno se corta
por tiempo y el otro no, la diferencia no dice nada sobre el modelo.
