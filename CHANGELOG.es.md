# Changelog

[English](CHANGELOG.md) · **Español**

Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/). Versionado [SemVer](https://semver.org/lang/es/).

## [Unreleased]

## [0.2.0] - 2026-10-06

Primera versión pública.

### Añadido

- Logo (`docs/assets/logo.svg`), diseñado con Claude Design.
- Lista de pruebas manuales en Claude Desktop (`docs/testing/claude-desktop.es.md`).
- Resolución de problemas, a partir de las preguntas más frecuentes de los issues y de la wiki de Sonarr/Radarr:
  - `explain_search`: búsqueda interactiva con los releases agrupados por motivo de rechazo, más comprobaciones básicas.
  - `grab_release`: descargar un release concreto aunque se haya rechazado.
  - `diagnose_import`: causa probable de una importación fallida y cómo arreglarla.
  - `check_paths`: carpetas raíz, remote path mappings, clientes de descarga y visibilidad de las carpetas de descarga.
  - `find_stalled_downloads`: descargas atascadas, sin progreso o con error del cliente.
  - `parse_release`: cómo se interpreta y puntúa un release, con una estimación de si sería una mejora.
- Mantenimiento: `bulk_edit` (primero vista previa, luego aplicar), `preview_rename` / `rename_files`, `library_report`, `test_download_clients`.
- `get_health` añade a cada health check conocido su solución habitual.
- `manual_import` acepta `matches` para asignar a mano archivos no identificados. Sonarr/Radarr revalidan la asignación antes de importar.
- Mensajes en inglés y español (`ARR_LANG`, por defecto `en`).
- Documentación en inglés y en español (README, DESIGN, ROADMAP, TOOLS, CHANGELOG).

### Cambiado

- **Renombrado de `arr-mcp` a `arr-doctor`** (paquete, comando y repositorio): `arr-mcp` ya estaba ocupado en PyPI y en decenas de repos de GitHub. Logo nuevo: un latido que termina en un botón de play.

- `bulk_edit` se separa en `bulk_edit_preview` (solo lectura) y `bulk_edit_apply`, y `rename_files` solo aplica (`preview_rename` devuelve el código): en Claude Desktop el segundo diálogo de permiso dice ahora «…Bulk edit apply…» en lugar del mismo nombre que la vista previa.

- El código de la vista previa no bastaba: en Claude Desktop el modelo hizo la vista previa y aplicó en el mismo turno. Si el cliente soporta *elicitation* de MCP, `bulk_edit` (varios elementos o un filtro) y `rename_files` (varios archivos) preguntan ahora directamente al usuario, y su respuesta manda sobre cualquier código; sin *elicitation* se mantiene el flujo del código.

- De la segunda pasada en Claude Desktop (el modelo aplicó una etiqueta sin enseñar la vista previa): `bulk_edit` y `rename_files` necesitan ahora el `confirmation_token` de la vista previa para aplicar a varios elementos, a una selección por filtro o a varios archivos; un solo elemento nombrado se sigue aplicando directamente. `set_monitored` acepta serie + temporada + números de episodio en una sola llamada.

- De la primera pasada de pruebas en Claude Desktop:
  - `find_suspicious_releases` también marca las descargas hechas más de un día antes de la emisión del episodio (o del estreno digital/físico de la película), como `likely: fake` si nunca se importaron y `early_release` si sí (temporadas publicadas de golpe antes de las fechas de emisión), y descargas distintas de episodios distintos con exactamente el mismo tamaño. En una biblioteca real: 17 probables falsos, y dos temporadas de la BBC reconocidas correctamente como estrenos adelantados.
  - `get_queue(only_problems=true)` incluye las descargas atascadas (`stall_reason`) aunque Sonarr/Radarr digan que están bien.
  - `explain_search` agrupa en una línea los resultados de otros episodios, temporadas o series; una búsqueda posterior del mismo elemento remite a sus releases aprobados (`grab_release`) en lugar de decir que no encontrará nada nuevo.
  - `preview_rename`/`rename_files` avisan si el renombrado está desactivado en Media Management.
  - Las tools de Prowlarr devuelven `prowlarr_id` (Sonarr/Radarr numeran los indexers de otra forma); los indexers desactivados ya no parecen fallando.
  - Coincidencia de títulos más estricta: palabras completas, y las sugerencias ignoran el artículo inicial.
  - Texto de solución más claro para el aviso de actualización.

- Las búsquedas se saltan los episodios no emitidos y las películas que Radarr no considera disponibles (`force=true` lo fuerza): encontrado cuando un episodio que se estrenaba al día siguiente solo tenía releases `.exe` falsos. `remove_from_queue` avisa si lanza la búsqueda de un sustituto para algo que aún no ha salido.

- `manual_import` acepta `allow_downgrade` (junto con `allow_replace`) para importar a propósito una versión de menor calidad; el resto de rechazos siguen bloqueando. Los archivos se asocian a la descarga de su elemento de la cola, así que el modo `auto` copia en lugar de mover un torrent que sigue compartiéndose.

- Encontrado con un Sonarr real: un pack de temporada es una entrada de cola por episodio. `get_queue`, `diagnose_import`, `find_stalled_downloads` y `find_suspicious_releases` muestran ahora una entrada por descarga (con `episodes` y `queue_ids`), y `diagnose_import` ya no añade un falso «faltan episodios en el pack» cuando todos los archivos están pero se rechazan.
- `find_suspicious_releases` también reconoce los títulos tal como los guardan Sonarr/Radarr («…H264 VICE exe», sin el punto).

- Encontrado con un Prowlarr real: `get_indexer_stats` ignoraba los fallos de RSS, así que los indexers caídos (30 de 30 llamadas RSS fallidas y ninguna búsqueda) salían por debajo de los sanos. Ahora ordena por tasa de fallo global (búsquedas + RSS + descargas). `list_indexers` muestra un `state` (ok / failing / disabled), y los avisos de salud propios de Prowlarr también traen solución.

- Probadas todas las tools, también las de escritura, contra contenedores desechables de Sonarr 4.0.20, Radarr 5.28 y 6.4.4, y Prowlarr 2.6.5.
- `bulk_edit` vuelve a leer los elementos tras aplicar y muestra lo que guardaron Sonarr/Radarr (antes mostraba el estado anterior al cambio).

- **Seguridad:** ya no se siguen las redirecciones HTTP (una redirección a otro dominio habría enviado la cabecera `X-Api-Key` a otro servidor, y un 301/302 podía convertir un POST en GET); el error indica el destino para corregir la URL. Las API keys son `SecretStr` en la configuración.
- Corregido: `parse_release` nunca veía el archivo existente del episodio (faltaba `includeEpisodeFile`), así que siempre respondía «aún no hay archivo».
- `explain_search` solo gasta presupuesto de indexers una vez resuelta la serie o película. mypy se ejecuta en el CI.

- `manual_import` espera hasta 40 s y verifica cada archivo; las importaciones más largas (mover gigas entre volúmenes de un NAS tardó 4 min en una prueba real) las verifica `get_command_status` cuando terminan. Un archivo solo cuenta si se añadió mientras corría ese comando. Antes: (`result`: imported / partial / failed, con el motivo sacado del log de Sonarr/Radarr). Encontrado en un NAS real: Sonarr dio por buena «Manually imported 6 files» mientras los seis fallaban con «Not a directory». Con `wait=false` se mantiene el comportamiento anterior.
- `diagnose_import` reconoce una ruta de la biblioteca bloqueada por un archivo (`path_conflict`).

- Encontrado al probar contra un Radarr real: la cola ya no incluye descargas que Sonarr/Radarr no lanzaron (`get_queue` las cuenta en `unknown_items_hidden`; `include_unknown=true` las lista). Inundaban `get_queue` y `diagnose_import` y podían ocultar archivos huérfanos reales.
- `find_stalled_downloads` también detecta descargas sin velocidad durante horas (`no_activity`) y magnets que nunca obtuvieron metadatos (`no_metadata`), e ignora las que están en pausa o en espera.
- `get_logs` admite hasta 60 s (filtrar la base de datos de logs es lento en un NAS).

- **Protecciones de buenas prácticas** (ver docs/GOOD_PRACTICES.es.md): presupuesto horario de indexers (`ARR_INDEXER_BUDGET_PER_HOUR`), se omite lo buscado hace poco (`ARR_SEARCH_COOLDOWN_MINUTES`, `force=true`), las búsquedas y retiradas de la cola de más de `ARR_SEARCH_CONFIRM_ABOVE` elementos requieren `confirm=true`, y `rename_files` solo enseña la vista previa salvo con `apply=true`.
- `manual_import` usa por defecto `import_mode="auto"` (copia o hardlink mientras se comparte, como la interfaz web) en lugar de `move`, y sustituir archivos existentes requiere `allow_replace=true`; avisa si no hay papelera.

- `ARR_DOWNLOADS_PATH` es opcional: `find_orphan_downloads` deduce las carpetas de descarga de la cola y del historial de importaciones.
- Las rutas de Sonarr/Radarr se comparan bien sean POSIX, de Windows o UNC.
- Windows y Linux se prueban en el CI, incluido un test de extremo a extremo del proceso real por stdio.

- Los errores de conexión dan una pista genérica (puerto cambiado, contenedor parado) en lugar de asumir Synology.
- Los 404 muestran el mensaje del servidor cuando aporta algo (p. ej. «try searching again»).

## [0.1.0] - 2026-10-04

### Añadido

- Servidor MCP por stdio (`arr-doctor`) basado en FastMCP 2.12.
- Configuración por variables de entorno o `.env`, con registro condicional por servicio y modo `ARR_READONLY`.
- Estado: `get_system_status`.
- Catálogo: `search_library`, `get_series`, `get_episodes`, `get_movie`, `get_missing`, `get_cutoff_unmet`, `get_calendar`.
- Diagnóstico: `get_queue`, `get_history`, `get_blocklist`, `get_health`, `get_logs`, `get_disk_space`, `find_orphan_downloads`, `find_suspicious_releases`, `get_command_status`.
- Acciones: `search_episodes`, `search_season`, `search_missing`, `search_movie`, `set_monitored`, `remove_from_queue`, `refresh_item`, `add_series`, `add_movie`, `manual_import`.
- Prowlarr: `list_indexers`, `get_indexer_stats`, `set_indexer_enabled`, `test_indexers`.
- `scripts/smoke.py` para probar las tools de solo lectura contra el servidor real, y `scripts/gen_tools_doc.py` para generar la referencia de tools.
- CI en GitHub Actions (Linux y Windows, Python 3.11–3.13) y ruff.
