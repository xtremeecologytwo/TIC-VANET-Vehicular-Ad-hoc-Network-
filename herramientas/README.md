# herramientas/

Binarios de terceros que usa el backend para recortar mapas de un extracto
local de OpenStreetMap (ver la sección *Mapas sin red* del README principal).
**No se versionan** (`.gitignore`): hay que descargarlos una vez.

| Archivo | Qué hace | De dónde |
|---|---|---|
| `osmconvert.exe` | recorta un rectángulo de un extracto `.osm.pbf` y da sus estadísticas | `http://m.m.i24.cc/osmconvert64.exe` (enlace oficial de la [wiki de OSM](https://wiki.openstreetmap.org/wiki/Osmconvert)) |
| `osmfilter.exe` | se queda solo con vías, edificios y restricciones de giro | `http://m.m.i24.cc/osmfilter.exe` ([wiki](https://wiki.openstreetmap.org/wiki/Osmfilter)) |

Descarga en PowerShell, desde la raíz del repo:

```powershell
curl.exe -L -o herramientas\osmconvert.exe http://m.m.i24.cc/osmconvert64.exe
curl.exe -L -o herramientas\osmfilter.exe  http://m.m.i24.cc/osmfilter.exe
```

Versiones probadas: osmconvert 0.8.10, osmfilter 1.4.5. El backend también los
acepta desde el `PATH` o desde las variables de entorno `OSMCONVERT` /
`OSMFILTER`.

> `--complete-ways` de osmconvert **no funciona en esta build de Windows**
> (salida vacía). El backend no la usa: recorta con un margen alrededor del
> rectángulo (`OSM_MARGEN_GRADOS`, 0,003° ≈ 330 m) para que las calles que
> cruzan el borde lleguen completas.
