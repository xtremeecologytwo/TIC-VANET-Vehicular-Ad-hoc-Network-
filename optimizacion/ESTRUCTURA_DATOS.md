# Estructuras de datos: qué recibe el solver y en qué orden

Con la migración a **docplex** ya no hace falta escribir las tuplas en el formato
de texto de un `.dat`: se construyen **en memoria**, en estructuras de Python, y
se le pasan directamente al modelo. Este documento describe **cómo se llaman
esas estructuras, qué campos tienen, de qué tipo son y en qué orden se guardan**,
para poder escribir funciones independientes que las consuman.

Todos los valores de ejemplo salen del **escenario de referencia V5** (Centro
Histórico de Quito, configuración C: 278 RSU candidatas, 31 instantes, H = 3).

---

## 1. El recorrido de los datos

```
FCD de SUMO
   │
   ├─► generar_tuplas_v2v(...)        ──► matrices_v2v   (conectividad V2V por instante)
   └─► generar_tuplas_visibilidad(...)──► tuplas_v2i     (enlaces V2I)
                    │
                    ▼
            analizar_timestep(...)     ──► A, Ã, B, R_h, S_h, D, d   (un instante)
                    │
                    ▼
           construir_datos_opl(...)    ──► dict con CVR y todos los conjuntos
                    │
                    ▼
             construir_modelo(datos)   ──► docplex / CPLEX
```

Los módulos son `backend/visibilidad.py`, `backend/multisalto.py`,
`backend/exportar_dat.py` y `optimizacion/optimizar_rsu.py`.

---

## 2. `tuplas_v2i` — enlaces vehículo ↔ RSU

Sale de `generar_tuplas_visibilidad(...)` (primer elemento de la tupla que
retorna).

**Tipo:** `list[dict]` — en el escenario de referencia, **1242 elementos**.

| Campo | Tipo | Significado | Ejemplo |
|---|---|---|---|
| `t` | `float` | Instante de simulación, en segundos | `0.0` |
| `vehiculo` | `str` | Id del vehículo con prefijo `V` | `'V0'` |
| `rsu` | `str` | Id de la *junction* de SUMO | `'11135269234'` |
| `distancia` | `float` | Distancia euclídea en metros | `9.72` |

```python
{'t': 0.0, 'vehiculo': 'V0', 'rsu': '11135269234', 'distancia': 9.72}
```

> Un elemento de esta lista significa: *en el instante `t`, el vehículo
> `vehiculo` ve directamente (línea de vista, sin edificios de por medio) a la
> RSU `rsu`, a `distancia` metros*.

---

## 3. `matrices_v2v` — conectividad vehículo ↔ vehículo por instante

Sale de `generar_tuplas_v2v(...)` (**segundo** elemento de la tupla que retorna).

**Tipo:** `dict[float, dict]` — 31 entradas, una por instante muestreado.

- **Clave:** `t` (`float`), el instante en segundos: `0.0, 120.0, …, 3600.0`.
- **Valor:** un `dict` con dos campos:

| Campo | Tipo | Contenido |
|---|---|---|
| `vehiculos` | `list[str]` | Ids de los vehículos activos en ese instante |
| `A` | `list[list[int]]` | Matriz n×n de 0/1; `A[i][j] = 1` si los vehículos `i` y `j` tienen enlace V2V |

`A` es **simétrica** cuando se usa `forzar_simetria=True` (el valor por defecto).
La posición `i` de `A` corresponde a `vehiculos[i]`.

---

## 4. Conectividad de un instante — `analizar_timestep(...)`

Devuelve un `dict` con todas las matrices del procedimiento multisalto para **un
solo instante**. Ejemplo real con 5 vehículos y 278 RSU:

| Clave | Tipo | Forma | Qué es |
|---|---|---|---|
| `t` | `float` | — | Instante |
| `H` | `int` | — | Máximo de saltos reales (3) |
| `vehiculos` | `list[str]` | n | Orden de las **filas** de todas las matrices |
| `rsu_ids` | `list[str]` | m | Orden de las **columnas** de B, R, S, D |
| `A` | `np.ndarray` int64 | (n, n) | Enlaces V2V |
| `A_tilde` | `np.ndarray` int64 | (n, n) | Ã = A ∨ I |
| `B` | `np.ndarray` int64 | (n, m) | Enlaces V2I directos |
| `R` | `list[np.ndarray]` | H × (n, m) | **Acumuladas**: `R[h-1][i][k]=1` si el vehículo i alcanza la RSU k en ≤ h saltos |
| `S` | `list[np.ndarray]` | H × (n, m) | **Primera llegada**: `S[h-1][i][k]=1` si el mínimo nº de saltos es exactamente h |
| `D` | `np.ndarray` int64 | (n, m) | Matriz de desconexión |
| `d` | `np.ndarray` int64 | (n,) | `d[i]=1` si el vehículo i no alcanza ninguna RSU |
| `resumen` | `dict` | — | Contadores por salto (ver abajo) |

`resumen["por_salto"]` es una `list[dict]` de longitud H, con las claves
`h`, `pares_acumulados`, `vehiculos_conectados` y `pares_nuevos` (todos `int`).

---

## 5. `construir_datos_opl(...)` — lo que consume el solver

**Es la estructura que se le pasa a docplex.** Un único `dict`:

| Clave | Tipo | Ejemplo real | Significado |
|---|---|---|---|
| `hmax` | `int` | `4` | Salto de desconexión = H + 1 |
| `rInf` | `int` | `0` | Id entero de la RSU artificial |
| `MaxR` | `int` | `278` | Máximo de RSU reales a desplegar |
| `R` | `list[int]` | 279 elementos | Ids de RSU, **incluye el 0** |
| `S` | `list[int]` | `[1, 2, …, 31]` | Escenarios (instantes) |
| `V` | `list[int]` | 113 elementos | Todos los vehículos |
| `Vs` | `dict[int, list[int]]` | 31 entradas | Vehículos presentes en cada escenario |
| `Cost` | `dict[int, float]` | 279 entradas | Coste de instalar cada RSU (`Cost[0] = 0.0`) |
| `Cap` | `dict[int, float]` | 279 entradas | Capacidad de cada RSU |
| `P` | `list[float]` | `[1.0, 2.0, 3.0, 1000.0]` | Penalización por nº de saltos, índice `h-1` |
| `L` | `dict[int, dict[int, float]]` | 31 × 113 | Carga de tráfico `L[s][v]` |
| **`CVR`** | **`list[tuple[int,int,int,int]]`** | **1598 tuplas** | **Las tuplas de conectividad** |
| `mapas` | `dict` | — | Traducción a los ids originales |
| `resumen` | `dict` | — | Contadores |

### 5.1 `CVR`: la estructura central

Es una **lista de tuplas de 4 enteros**:

```python
CVR: list[tuple[int, int, int, int]]
#                 s     h     v     r
```

| Posición | Nombre | Tipo | Significado |
|---|---|---|---|
| 0 | `s` | `int` | Escenario (instante), numerado desde **1** |
| 1 | `h` | `int` | Nº de saltos: `1..H` reales, `hmax` = desconexión |
| 2 | `v` | `int` | Vehículo (el número del id: `'V12'` → `12`) |
| 3 | `r` | `int` | RSU (`0` = artificial `r_inf`) |

```python
(1, 1, 0, 22)    # escenario 1: el vehículo 0 alcanza la RSU 22 en 1 salto
(4, 2, 6, 48)    # escenario 4: el vehículo 6 alcanza la RSU 48 en 2 saltos
(1, 4, 0, 0)     # escenario 1: el vehículo 0 puede quedar sin servicio (h=hmax, r=0)
```

### 5.2 `mapas`: volver a los identificadores originales

| Clave | Tipo | Para qué |
|---|---|---|
| `escenario_a_t` | `dict[int, float]` | `s` → instante real en segundos |
| `int_a_rsu` | `dict[int, str]` | `r` → id de la *junction* de SUMO |

El vehículo no necesita mapa: `v` es el número contenido en el id
(`'V12'` → `12`), así que el id original se recupera como `f"V{v}"`.

---

## 6. El ORDEN en que se guarda todo

Esta es la parte con más trampa. Todo lo de abajo está **verificado sobre los
datos reales**, no supuesto.

### 6.1 Escenarios

`S = [1, 2, …, 31]`, asignados en **orden temporal creciente**. La
correspondencia con el tiempo está en `mapas["escenario_a_t"]`.

### 6.2 Vehículos — ⚠️ el orden es ALFABÉTICO, no numérico

Las **filas** de `A`, `B`, `R_h` y `S_h` siguen la lista `vehiculos`, que está
ordenada **alfabéticamente por la cadena del id**, no por su valor numérico:

```python
['V10', 'V11', 'V12', 'V3', 'V4', 'V6', 'V8']   # t = 360.0, caso real
#  ▲ 'V10' va antes que 'V3' porque '1' < '3' como carácter
```

Verificado: se cumple en los 31 instantes, y en 3 de ellos el orden alfabético
**no coincide** con el numérico. **Quien indexe asumiendo orden numérico se
equivocará de fila.** La forma segura de pasar de un vehículo a su fila es
siempre:

```python
i = vehiculos.index('V3')      # o construir un dict {id: indice} una sola vez
```

En cambio, la lista `V` del `dict` final **sí** está ordenada numéricamente,
porque ahí los vehículos ya son enteros.

### 6.3 RSU

`rsu_ids` es el orden canónico de las **columnas**, y el proyecto siempre pasa
`sorted(rsus)` (orden alfabético de los ids de *junction*). El entero asignado a
cada RSU sigue ese mismo orden, empezando en **1**:

```python
('10004552905', 1), ('10079171430', 2), ('10860719326', 3), …
```

El **0 queda reservado** para la RSU artificial `r_inf`.

### 6.4 Orden dentro de `CVR`

Las tuplas se generan recorriendo, en este orden:

1. **Escenario `s`** creciente (1, 2, 3, …).
2. Dentro de cada escenario, **salto `h`** creciente: primero todos los de
   `h=1`, luego `h=2`, … hasta `h=H`. *(Si un salto no aporta tuplas, no
   aparece: es normal ver un escenario con `h=1` y `h=4` pero sin `h=2`.)*
3. Dentro de cada `(s, h)`, se recorre `S_h` por **filas** (en el orden de
   `vehiculos`, o sea alfabético) y, en cada fila, por **columnas** (en el orden
   de `rsu_ids`, o sea `r` creciente).
4. **Al final de cada escenario** se añaden las tuplas artificiales
   `(s, hmax, v, 0)`, **una por cada vehículo presente**.

Comprobado sobre los datos reales:

| Propiedad | ¿Se cumple? |
|---|---|
| `s` nunca decrece a lo largo de la lista | ✅ |
| Dentro de cada `s`, `h` nunca decrece | ✅ |
| Las tuplas artificiales van al final de su escenario | ✅ |
| Dentro de `(s, h)`, ordenado por `(vehículo, rsu)` **numéricamente** | ❌ — sigue el orden alfabético de las filas |

> ⚠️ **Estas garantías valen para el `CVR` construido en memoria por
> `construir_datos_opl()`.** Si en cambio se lee un `.dat` de vuelta con
> `leer_dat()`, las tuplas conservan **el orden del archivo**. En el `.dat` que
> genera el proyecto ese orden coincide con el de construcción, pero un `.dat`
> escrito a mano puede venir en cualquier orden —el micro-ejemplo, por ejemplo,
> no está agrupado por `h`—. **Si el análisis depende del orden, conviene
> ordenar explícitamente** en vez de confiar en el que traiga:
>
> ```python
> cvr = sorted(datos["CVR"])      # por s, luego h, luego vehículo, luego RSU
> ```

---

## 7. Invariantes que sirven para validar

| Invariante | Valor en el escenario de referencia |
|---|---|
| `\|CVR\| = K + N` (pares reales + instancias vehículo–instante) | 1598 = 1419 + 179 |
| Nº de tuplas con `r == 0` = nº de instancias `N` | 179 |
| `h == hmax` ⟺ `r == 0` | siempre |
| No hay tuplas repetidas | ✅ |

---

## 8. Cómo consumirlo desde una función independiente

El `dict` completo es autosuficiente: no hace falta ningún archivo. Ejemplo
mínimo que analiza la conectividad por instante a partir de `CVR`:

```python
from collections import defaultdict

def analizar_cvr(datos):
    """Recorre el CVR y resume la conectividad de cada escenario."""
    hmax = datos["hmax"]
    t_de_s = datos["mapas"]["escenario_a_t"]
    rsu_de_int = datos["mapas"]["int_a_rsu"]

    por_escenario = defaultdict(lambda: {"por_salto": defaultdict(int),
                                         "desconectables": 0,
                                         "vehiculos": set()})
    for s, h, v, r in datos["CVR"]:          # <- la estructura, tal cual
        info = por_escenario[s]
        info["vehiculos"].add(v)
        if h == hmax:                         # tupla artificial (r == 0)
            info["desconectables"] += 1
        else:
            info["por_salto"][h] += 1

    for s in sorted(por_escenario):
        info = por_escenario[s]
        reales = sum(info["por_salto"].values())
        print("t=%7.1f s | %3d vehiculos | %4d pares reales | %s"
              % (t_de_s[s], len(info["vehiculos"]), reales,
                 dict(sorted(info["por_salto"].items()))))
```

Se obtiene el `dict` sin tocar disco:

```python
from backend.exportar_dat import construir_datos_opl

datos = construir_datos_opl(matrices_v2v, tuplas_v2i, sorted(rsus), H=3)
analizar_cvr(datos)
```

O bien desde un `.dat` ya generado, que reconstruye **el mismo `dict`**,
incluidos los `mapas` para volver a los identificadores originales:

```python
from optimizacion.explicar_optimizacion import leer_dat

datos = leer_dat("resultados/output/rsu_backend.dat")
analizar_cvr(datos)
```

Hay un ejemplo ejecutable y comentado en
[`optimizacion/ejemplo_leer_cvr.py`](ejemplo_leer_cvr.py).

---

## 9. Y el `.dat` ¿para qué queda?

Ya **no es necesario para resolver**: `optimizar_rsu.py` construye el modelo
directamente desde este `dict`. El `.dat` se sigue generando para dos cosas:

- **Inspección**: leerlo a mano y comprobar los datos.
- **Validación cruzada**: el mismo problema resuelto con `oplrun` sobre el
  modelo OPL, para confirmar que las dos implementaciones dan lo mismo
  (ver [`VALIDACION_OPL.md`](VALIDACION_OPL.md)).
