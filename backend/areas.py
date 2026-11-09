"""
areas.py — áreas con nombre y el selector de mapa del CLI
=========================================================
El CLI de campañas no debería obligar a escribir coordenadas a mano. Aquí se
guardan las áreas de estudio con un NOMBRE (`datos/areas.json`) y se ofrece un
selector: `scn.py mapa --nombre centro` abre una pestaña del navegador con un
mapa, se dibuja el rectángulo con dos clics, se pulsa Guardar y el CLI recibe
el área. A partir de ahí todo se refiere a ella por su nombre.

El selector es una página mínima servida por la librería estándar de Python
(`http.server`) en 127.0.0.1 y un puerto libre: no hace falta levantar la API
ni el frontend React. Leaflet y las teselas de OpenStreetMap se cargan desde
internet, igual que en la aplicación web.

Formato de `datos/areas.json`:
    {"centro-quito": {"bbox": [min_lon, min_lat, max_lon, max_lat],
                      "km2": 1.2, "creada": "2026-10-18T10:00:00"}}
"""

import json
import math
import os
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARCHIVO = os.path.join(_RAIZ, "datos", "areas.json")

# Por encima de esto, 5000 vehículos se reparten tanto que casi no hay
# multisalto, y SUMO/LoS crecen con la red. Solo se avisa.
KM2_AVISO = 15.0


def km2(bbox) -> float:
    """Superficie aproximada de un rectángulo lon/lat, en km²."""
    w, s, e, n = bbox
    lat = math.radians((s + n) / 2)
    return abs(e - w) * 111.32 * math.cos(lat) * abs(n - s) * 110.57


def listar() -> dict:
    try:
        with open(ARCHIVO, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def obtener(nombre: str) -> list:
    """bbox [min_lon, min_lat, max_lon, max_lat] del área con ese nombre."""
    areas = listar()
    if nombre not in areas:
        disponibles = ", ".join(sorted(areas)) or "(ninguna; crea una con `scn.py mapa`)"
        raise KeyError(f"no existe el área '{nombre}'. Disponibles: {disponibles}")
    return list(areas[nombre]["bbox"])


def guardar(nombre: str, bbox) -> dict:
    nombre = nombre.strip()
    if not nombre or any(c in nombre for c in '\\/:*?"<>|'):
        raise ValueError("nombre de área vacío o con caracteres no válidos")
    w, s, e, n = (float(x) for x in bbox)
    if not (w < e and s < n):
        raise ValueError("bbox mal formado: debe ser min_lon,min_lat,max_lon,max_lat")
    areas = listar()
    areas[nombre] = {"bbox": [round(w, 6), round(s, 6), round(e, 6), round(n, 6)],
                     "km2": round(km2((w, s, e, n)), 3),
                     "creada": time.strftime("%Y-%m-%dT%H:%M:%S")}
    os.makedirs(os.path.dirname(ARCHIVO), exist_ok=True)
    tmp = ARCHIVO + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(areas, f, indent=2, ensure_ascii=False)
    os.replace(tmp, ARCHIVO)
    return areas[nombre]


# ----------------------------------------------------------------------
# El selector en el navegador
# ----------------------------------------------------------------------

_PAGINA = r"""<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<title>SmartCityNet · elegir área</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css">
<style>
  html,body{margin:0;height:100%;font:14px system-ui,Segoe UI,sans-serif;color:#1a1a2e}
  #mapa{position:absolute;inset:0 0 0 340px}
  #panel{position:absolute;left:0;top:0;bottom:0;width:340px;box-sizing:border-box;
         padding:18px;background:#f7f8fb;border-right:1px solid #d6dbe6;overflow:auto}
  h1{font-size:17px;margin:0 0 4px} .sub{color:#667;font-size:12px;margin-bottom:14px}
  label{display:block;font-weight:600;margin:12px 0 4px}
  input{width:100%;box-sizing:border-box;padding:7px 9px;border:1px solid #c9cede;border-radius:6px;font:inherit}
  button{width:100%;margin-top:12px;padding:9px;border:0;border-radius:6px;font:600 14px inherit;cursor:pointer}
  .ok{background:#2557a7;color:#fff} .ok:disabled{opacity:.45;cursor:default}
  .sec{background:#e6ecf7;color:#2557a7}
  .dato{font-family:ui-monospace,Consolas,monospace;font-size:12px;background:#fff;border:1px solid #d6dbe6;
        border-radius:6px;padding:8px;margin-top:8px;white-space:pre-wrap}
  .aviso{color:#b9770b} .err{color:#d92020} .bien{color:#0f9d6b}
  ol{padding-left:18px;margin:6px 0} li{margin:3px 0}
  .ley{font-size:12px;color:#556;margin-top:16px;line-height:1.6}
  .ley i{display:inline-block;width:14px;height:3px;vertical-align:middle;margin-right:6px}
</style></head><body>
<div id="panel">
  <h1>Elegir área de estudio</h1>
  <div class="sub">SmartCityNet · CLI de campañas</div>
  <ol>
    <li>Clic en una esquina del área.</li>
    <li>Clic en la esquina opuesta.</li>
    <li>Revisa el tamaño y pulsa <b>Guardar</b>.</li>
  </ol>
  <label for="nombre">Nombre del área</label>
  <input id="nombre" value="__NOMBRE__" autocomplete="off">
  <div id="info" class="dato">Aún no hay rectángulo.</div>
  <button id="guardar" class="ok" disabled>Guardar y cerrar</button>
  <button id="rehacer" class="sec">Rehacer el rectángulo</button>
  <div id="msg" style="margin-top:10px"></div>
  <div class="ley">
    <div><i style="background:#2557a7"></i>área que estás dibujando</div>
    <div><i style="background:#0f9d6b"></i>áreas ya guardadas</div>
    <div><i style="background:#b9770b"></i>cobertura del extracto local (mapa sin internet)</div>
  </div>
</div>
<div id="mapa"></div>
<script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js"></script>
<script>
const AREAS = __AREAS__, EXTRACTOS = __EXTRACTOS__, AVISO_KM2 = __AVISO__;
const mapa = L.map('mapa').setView([-0.2108, -78.5007], 14);   // centro de Quito
L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',
  {maxZoom: 19, attribution: '&copy; OpenStreetMap'}).addTo(mapa);
for (const e of EXTRACTOS) {
  L.rectangle([[e[1], e[0]], [e[3], e[2]]], {color:'#b9770b', weight:1.5, fill:false, dashArray:'6 4'}).addTo(mapa);
}
for (const [n, a] of Object.entries(AREAS)) {
  const b = a.bbox;
  L.rectangle([[b[1], b[0]], [b[3], b[2]]], {color:'#0f9d6b', weight:2, fillOpacity:.06})
   .bindTooltip(n + ' (' + a.km2 + ' km²)').addTo(mapa);
}
let p1 = null, rect = null, marca = null, bbox = null;
const info = document.getElementById('info'), btn = document.getElementById('guardar'),
      msg = document.getElementById('msg');
function km2(b){ const lat=(b[1]+b[3])/2*Math.PI/180;
  return Math.abs(b[2]-b[0])*111.32*Math.cos(lat)*Math.abs(b[3]-b[1])*110.57; }
function dentroExtracto(b){ return EXTRACTOS.some(e => e[0]<=b[0] && e[1]<=b[1] && e[2]>=b[2] && e[3]>=b[3]); }
function limpiar(){ if(rect) mapa.removeLayer(rect); if(marca) mapa.removeLayer(marca);
  rect=marca=p1=bbox=null; btn.disabled=true; info.textContent='Aún no hay rectángulo.'; msg.textContent=''; }
mapa.on('click', ev => {
  if (bbox) limpiar();
  if (!p1) { p1 = ev.latlng; marca = L.circleMarker(p1, {radius:5, color:'#2557a7'}).addTo(mapa);
             info.textContent = 'Primera esquina puesta. Falta la opuesta.'; return; }
  const p2 = ev.latlng;
  bbox = [Math.min(p1.lng,p2.lng), Math.min(p1.lat,p2.lat), Math.max(p1.lng,p2.lng), Math.max(p1.lat,p2.lat)]
         .map(x => Math.round(x*1e6)/1e6);
  rect = L.rectangle([[bbox[1],bbox[0]],[bbox[3],bbox[2]]], {color:'#2557a7', weight:2.5}).addTo(mapa);
  const a = km2(bbox);
  let txt = 'bbox = ' + bbox.join(',') + '\nsuperficie = ' + a.toFixed(2) + ' km²';
  txt += dentroExtracto(bbox) ? '\nmapa: extracto local (sin internet)' : '\nmapa: Overpass (necesita internet)';
  info.textContent = txt;
  msg.innerHTML = a > AVISO_KM2
    ? '<span class="aviso">Área grande: con 5000 vehículos habrá poco multisalto y M2 será lento.</span>' : '';
  btn.disabled = false;
});
document.getElementById('rehacer').onclick = limpiar;
btn.onclick = async () => {
  const nombre = document.getElementById('nombre').value.trim();
  if (!nombre) { msg.innerHTML = '<span class="err">Pon un nombre.</span>'; return; }
  btn.disabled = true;
  const r = await fetch('/guardar', {method:'POST', headers:{'Content-Type':'application/json'},
                                      body: JSON.stringify({nombre, bbox})});
  const j = await r.json();
  if (j.ok) { msg.innerHTML = '<span class="bien">Guardada como <b>' + nombre +
                '</b>. Ya puedes cerrar esta pestaña y volver a la consola.</span>'; }
  else { msg.innerHTML = '<span class="err">' + j.error + '</span>'; btn.disabled = false; }
};
</script></body></html>"""


def seleccionar_en_mapa(nombre: str, abrir: bool = True, espera_max_s: float = 1800) -> dict | None:
    """
    Abre el selector en el navegador y espera a que se guarde un área.

    Retorna el área guardada ({"bbox", "km2", "creada"}) o None si se cancela
    (Ctrl+C) o se agota la espera.
    """
    from . import descargar_osm
    extractos = [e["bbox"] for e in descargar_osm.extractos()]
    pagina = (_PAGINA.replace("__NOMBRE__", nombre.replace('"', ""))
              .replace("__AREAS__", json.dumps(listar()))
              .replace("__EXTRACTOS__", json.dumps(extractos))
              .replace("__AVISO__", str(KM2_AVISO))).encode("utf-8")
    resultado: dict = {}
    hecho = threading.Event()

    class Manejador(BaseHTTPRequestHandler):
        def log_message(self, *a):          # silencio: la consola es del CLI
            pass

        def _json(self, codigo, obj):
            cuerpo = json.dumps(obj).encode("utf-8")
            self.send_response(codigo)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(cuerpo)))
            self.end_headers()
            self.wfile.write(cuerpo)

        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(pagina)))
            self.end_headers()
            self.wfile.write(pagina)

        def do_POST(self):
            if self.path != "/guardar":
                return self._json(404, {"ok": False, "error": "ruta desconocida"})
            try:
                datos = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
                area = guardar(datos["nombre"], datos["bbox"])
            except (KeyError, ValueError, TypeError) as e:
                return self._json(400, {"ok": False, "error": str(e)})
            resultado.update({"nombre": datos["nombre"].strip(), **area})
            self._json(200, {"ok": True})
            hecho.set()

    servidor = ThreadingHTTPServer(("127.0.0.1", 0), Manejador)
    url = f"http://127.0.0.1:{servidor.server_address[1]}/"
    hilo = threading.Thread(target=servidor.serve_forever, daemon=True)
    hilo.start()
    print(f"  selector de área en {url}")
    if abrir:
        webbrowser.open(url)
    print("  dibuja el rectángulo en el navegador y pulsa Guardar (Ctrl+C para cancelar)")
    try:
        t0 = time.time()
        while not hecho.wait(0.5):
            if time.time() - t0 > espera_max_s:
                print("  tiempo de espera agotado")
                break
    except KeyboardInterrupt:
        print("\n  cancelado")
    finally:
        servidor.shutdown()
    return resultado or None
