"""
Registro de los subprocesos que el backend tiene en marcha
==========================================================
Las herramientas de SUMO (`netconvert`, `polyconvert`, `randomTrips` →
`duarouter`, `sumo`) se lanzan como subprocesos y pueden tardar **minutos**.
Los endpoints de la API son síncronos, así que FastAPI los ejecuta en un hilo
del *threadpool*… y **un hilo de Python no se puede interrumpir desde fuera**.
Consecuencia práctica: pulsar "Generar escenario" mientras había otra corrida
dejaba las dos peleándose por la CPU y la RAM, y ni Ctrl+C en la consola las
paraba (uvicorn espera a que el hilo termine, y el hilo está bloqueado
esperando al subproceso).

La salida es no depender del hilo: lo que de verdad consume la máquina es el
**subproceso**, y a un subproceso sí se le puede matar. Este módulo lleva la
cuenta de los que están vivos para que `cancelar_todo()` los corte.

Uso:
    from .procesos import correr, cancelar_todo

    correr(cmd, timeout=..., cwd=...)   # en vez de subprocess.run(...)
    cancelar_todo()                     # al empezar un escenario nuevo

`correr()` se comporta como `subprocess.run(check=True, capture_output=True,
text=True)`: devuelve un `CompletedProcess` y lanza `CalledProcessError` o
`TimeoutExpired` igual que antes, así que el manejo de errores existente sigue
valiendo.
"""

import os
import subprocess
import threading

# pid -> (Popen, etiqueta legible)
_vivos: dict[int, tuple[subprocess.Popen, str]] = {}
_lock = threading.Lock()

# Windows necesita matar el ÁRBOL, no el proceso: `randomTrips.py` es un Python
# que lanza `duarouter.exe` como hijo, y matar al padre deja al hijo huérfano
# consumiendo varios GB (visto: duarouter con 5 GB sobreviviendo a su padre).
_ES_WINDOWS = os.name == "nt"


def _matar(proc: subprocess.Popen) -> None:
    """Mata un proceso y toda su descendencia, sin propagar errores."""
    try:
        if _ES_WINDOWS:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                           capture_output=True, timeout=20)
        else:
            proc.kill()
    except Exception:
        pass
    try:
        proc.wait(timeout=10)
    except Exception:
        pass


def correr(cmd: list[str], timeout: float | None = None,
           cwd: str | None = None, etiqueta: str | None = None):
    """
    Ejecuta un comando registrándolo para que se pueda cancelar.

    Equivalente a `subprocess.run(cmd, check=True, capture_output=True,
    text=True, timeout=timeout, cwd=cwd)`.

    Parámetros:
        cmd: comando y argumentos.
        timeout: segundos máximos; None = sin límite.
        cwd: directorio de trabajo.
        etiqueta: nombre legible para los mensajes (por defecto, el ejecutable).

    Retorna:
        subprocess.CompletedProcess con stdout/stderr como texto.

    Lanza:
        FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired
        — los mismos que `subprocess.run`, para no cambiar el manejo de errores.
    """
    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, cwd=cwd,
    )
    with _lock:
        _vivos[proc.pid] = (proc, etiqueta or os.path.basename(str(cmd[0])))
    try:
        salida, error = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        _matar(proc)
        raise
    finally:
        with _lock:
            _vivos.pop(proc.pid, None)

    if proc.returncode != 0:
        raise subprocess.CalledProcessError(proc.returncode, cmd, salida, error)
    return subprocess.CompletedProcess(cmd, proc.returncode, salida, error)


def cancelar_todo() -> list[str]:
    """
    Mata todos los subprocesos registrados y devuelve sus etiquetas.

    Se llama al empezar un escenario nuevo: si quedaba una corrida a medias, se
    corta en vez de dejar dos compitiendo por la máquina. Devolver la lista
    permite decir en el log QUÉ se cortó, para que no parezca magia.
    """
    with _lock:
        pendientes = list(_vivos.values())
        _vivos.clear()
    cortados = []
    for proc, etiqueta in pendientes:
        if proc.poll() is None:      # sigue vivo
            _matar(proc)
            cortados.append(etiqueta)
    return cortados


def en_marcha() -> list[str]:
    """Etiquetas de lo que está corriendo ahora mismo (para diagnóstico)."""
    with _lock:
        return [e for p, e in _vivos.values() if p.poll() is None]
