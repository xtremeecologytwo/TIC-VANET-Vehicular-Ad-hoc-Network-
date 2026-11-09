-- ---------------------------------------------------------------------------
-- Consultas de uso diario sobre datos/catalogo.sqlite
--
-- Se pegan en la pestaña "Execute SQL" de DB Browser for SQLite y se ejecutan
-- con Ctrl+Return. Las tablas están normalizadas por etapa del flujo (área →
-- red → movilidad → candidatas → corrida), así que una corrida entera no se ve
-- en ninguna tabla suelta: hay que unirlas. Eso es justo lo que hace la
-- primera consulta, y es la que se quiere el 90 % de las veces.
-- ---------------------------------------------------------------------------


-- 1. TODAS LAS CORRIDAS, una fila cada una, con todo lo que hace falta para
--    interpretarlas: parámetros, métricas, versión de SUMO y commit.
SELECT c.uuid,
       c.campana,
       a.nombre                AS area,
       m.n_vehiculos           AS veh,
       m.duracion_s / 60.0     AS min,
       m.semilla,
       cd.min_grado            AS gmin,
       cd.radio_cluster        AS rho,
       cd.n                    AS Y,
       c.radio_obu,
       c.H,
       r.n_instantes,
       r.N,
       r.K,
       r.cvr                   AS "|CVR|",
       ROUND(r.q_reach, 2)     AS q_reach,
       r.m1, r.m2, r.m3,
       d.n_rsu                 AS rsu_desplegadas,   -- NULL si no se corrió M3
       ROUND(d.cobertura_pct, 2) AS cobertura_pct,
       d.status                AS solver,
       c.estado,
       e.sumo,
       e.commit_git,
       c.carpeta
FROM corrida c
JOIN movilidad   m  ON m.id  = c.movilidad_id
JOIN red         rd ON rd.id = m.red_id
JOIN area        a  ON a.id  = rd.area_id
JOIN candidatas  cd ON cd.id = c.candidatas_id
LEFT JOIN resultado  r ON r.corrida_id = c.id
LEFT JOIN despliegue d ON d.corrida_id = c.id
LEFT JOIN entorno    e ON e.corrida_id = c.id
ORDER BY c.id;


-- 2. EFECTO DE LA SEMILLA. Misma configuración, distinta semilla: la dispersión
--    entre estas filas es la variabilidad estadística del escenario, que es lo
--    que hay que reportar como intervalo en el artículo.
SELECT m.semilla,
       cd.n                AS Y,
       r.N, r.K,
       ROUND(r.q_reach, 2) AS q_reach
FROM corrida c
JOIN movilidad  m  ON m.id  = c.movilidad_id
JOIN candidatas cd ON cd.id = c.candidatas_id
JOIN resultado  r  ON r.corrida_id = c.id
WHERE m.n_vehiculos = 120        -- ajustar
  AND cd.min_grado  = 4          -- ajustar
ORDER BY m.semilla;


-- 3. CÓMO EVOLUCIONA LA COBERTURA DENTRO DE UNA CORRIDA, sin abrir un .dat.
--    `sin_servicio` son las instancias vehículo-instante que no alcanzan
--    ninguna RSU candidata en ese momento.
SELECT i.s,
       i.t,
       i.n_vehiculos,
       i.pares_h1, i.pares_h2, i.pares_h3,
       i.sin_servicio
FROM instante i
JOIN corrida c ON c.id = i.corrida_id
WHERE c.uuid = '9eb1801d0c13'    -- ajustar
ORDER BY i.s;


-- 4. QUÉ TRABAJO SE ESTÁ REPITIENDO. Si una movilidad aparece con varias
--    corridas, esas corridas comparten la simulación de SUMO: es trabajo que el
--    flujo todavía rehace y que podría saltarse.
SELECT m.id, m.semilla, m.n_vehiculos, m.duracion_s / 60.0 AS min,
       COUNT(c.id) AS corridas
FROM movilidad m
JOIN corrida c ON c.movilidad_id = m.id
GROUP BY m.id
HAVING COUNT(c.id) > 1
ORDER BY corridas DESC;


-- 5. CORRIDAS DEGENERADAS O ROTAS, para no meterlas en las tablas del artículo.
SELECT c.uuid, c.campana, c.estado, cd.min_grado, cd.n AS Y,
       ROUND(r.q_reach, 2) AS q_reach, c.error
FROM corrida c
JOIN candidatas cd ON cd.id = c.candidatas_id
LEFT JOIN resultado r ON r.corrida_id = c.id
WHERE c.estado <> 'hecha' OR cd.n = 0 OR r.q_reach IS NULL
ORDER BY c.id;
