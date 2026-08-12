# ============================================================
# dev.ps1 — Levanta SmartCityNet en desarrollo (backend + frontend)
# ============================================================
# Abre DOS ventanas de PowerShell:
#   1) API FastAPI  → http://localhost:8000   (backend: SUMO, LoS, CPLEX)
#   2) Frontend React → http://localhost:5173 (la interfaz; ábrela en el navegador)
#
# Uso (clic derecho → "Ejecutar con PowerShell", o desde una terminal):
#   .\dev.ps1
#
# La primera vez, instala las dependencias del frontend antes:
#   cd web ; npm install
# ============================================================

$root = $PSScriptRoot

# 1) Backend — usa el Python del entorno virtual del repo
Start-Process powershell -ArgumentList '-NoExit', '-Command',
  "cd '$root'; Write-Host 'API FastAPI en http://localhost:8000' -ForegroundColor Cyan; .\.venv\Scripts\python -m uvicorn api.main:app --reload --port 8000"

# 2) Frontend — servidor de desarrollo de Vite
Start-Process powershell -ArgumentList '-NoExit', '-Command',
  "cd '$root\web'; Write-Host 'Frontend React en http://localhost:5173' -ForegroundColor Green; npm run dev"

Write-Host ""
Write-Host "  SmartCityNet arrancando…" -ForegroundColor Yellow
Write-Host "  API : http://localhost:8000   (deja esa ventana abierta)"
Write-Host "  App : http://localhost:5173   <-- abre esta en el navegador"
Write-Host ""
