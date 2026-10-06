# Roadmap: necesidades del usuario medio de Sonarr/Radarr

[English](ROADMAP.md) · **Español**

Análisis del 2026-10-04. Fuentes:

- Los 300 issues más votados de [Sonarr/Sonarr](https://github.com/Sonarr/Sonarr/issues) y [Radarr/Radarr](https://github.com/Radarr/Radarr/issues), ordenados por 👍.
- Recuento de issues por tema de soporte (búsquedas por palabra clave).
- Las páginas de FAQ y Troubleshooting de la [wiki de Servarr](https://wiki.servarr.com). Los repos no tienen Discussions y mandan el soporte a Discord y Reddit, así que la wiki es el mejor resumen de lo que más se pregunta.

La mayoría de las peticiones votadas son funciones de la propia aplicación (multiusuario, SSO, varias versiones de un archivo…) que un MCP no puede añadir. Lo que sí puede aportar un MCP es **explicar** lo que la interfaz web esconde y **automatizar operaciones repetitivas en lenguaje natural**. La lista se centra en eso.

Todos los endpoints citados existen en los OpenAPI oficiales (Sonarr v4, Radarr, Prowlarr).

## Prioridad alta — ✅ hecho (v0.2.0, sin publicar)

### 1. «¿Por qué no ha descargado X?» → `explain_search` + `grab_release` ✅

Es la pregunta más frecuente: la wiki tiene secciones enteras para ella («Why didn't Sonarr grab an episode I was expecting», «Query Successful - No Results Returned», «Media is Unmonitored», «Wrong Series Type»…). Además, «Force grab» es el tercer issue más votado de Sonarr (#395, 112 👍).

- `explain_search(series/episode | movie)`: hace `GET /release?episodeId=` o `?movieId=` (búsqueda interactiva) y agrupa los resultados por **motivo de rechazo** (`rejections`). Por ejemplo: «23 releases: 15 por idioma, 5 por tamaño, 2 por puntuación de custom format, 1 aprobado». Incluye calidad, CF score, seeders e indexer. Antes comprueba lo básico: que esté monitorizado, que sea del tipo de serie correcto y que el perfil sea el adecuado.
- `grab_release(guid, indexer_id)`: descarga a la fuerza un release concreto (`POST /release`). Es una tool de escritura.

### 2. «¿Por qué no se importa?» → `diagnose_import` y `check_paths` ✅

«Import failed», «not importing» y «remote path» suman unos 570 issues entre los dos proyectos. Es también el apartado más largo del troubleshooting: Remote Path Mapping, permisos, Docker y rutas, carpeta de descargas igual que la biblioteca, categoría incorrecta…

- `diagnose_import(queue_id)`: junta los `statusMessages`, los `rejections` del escaneo de su carpeta (`/manualimport?downloadId=`) y la ruta de salida, y devuelve una causa probable con su solución. Pendiente: cruzarlo también con los errores recientes del log.
- `check_paths`: compara las carpetas raíz (`/rootfolder`, accesibles o no), las rutas de salida de la cola y las `remotepathmapping`. Detecta el caso típico: «el cliente de descargas dice `/volume1/downloads/x`, pero Sonarr no ve esa ruta».
- `manual_import` con **emparejado manual**: permitir indicar la serie y los episodios, o la película, cuando Sonarr/Radarr no lo identifican. Cubre «Found matching series via grab history… Manual import required» y «Unknown movie» (Radarr #1441, 82 comentarios).

### 3. Descargas atascadas → `find_stalled_downloads` ✅

Sonarr #958 (50 👍, abierto) y Radarr #5407 (29 👍, abierto). Es una petición histórica sin resolver.

- Detecta en la cola los elementos sin progreso: estado `warning` o `stalled`, sin `timeleft` durante mucho tiempo, o con el mensaje de stalled del cliente. Los combina con `remove_from_queue(blocklist=true)` para buscar otro release.

### 4. Releases y custom formats → `parse_release` ✅

Los custom formats y las puntuaciones son un foco constante de confusión: «custom format score» aparece en unos 180 issues, Sonarr #5598 «Improve CF Comparison Between Release and File» tiene 21 👍, y hay muchos casos de «Not an upgrade» o bucles de upgrade.

- `parse_release(title)`: usa `GET /parse?title=` para mostrar cómo interpreta Sonarr/Radarr el nombre de un release: serie y episodio, calidad, idioma, custom formats y puntuación. Si el elemento ya tiene archivo, compara con él y dice si sería un upgrade y por qué.

## Prioridad media — ✅ hecho (v0.2.0, sin publicar)

### 5. Edición masiva → `bulk_edit_preview` / `bulk_edit_apply` ✅

En Radarr, «bulk» aparece en unos 300 issues y «tags» en unos 400; Sonarr tiene cifras parecidas. Ejemplos de peticiones: añadir etiquetas según atributos (#3870), filtros personalizados en Wanted (#3657).

- `bulk_edit(filtro, cambios)` con `PUT /series/editor` y `/movie/editor`: cambiar perfil de calidad, monitorización, etiquetas, tipo de serie o disponibilidad mínima de muchos elementos a la vez. La carpeta raíz se deja fuera a propósito, porque cambiarla mueve archivos. Por ejemplo: «pasa todas las series terminadas a no monitorizadas», «pon el perfil 4K a las películas de 2024». Siempre con una vista previa de qué elementos cambiarían antes de aplicar.

### 6. Renombrado con vista previa → `preview_rename` / `rename_files` ✅

«rename» aparece en más de 600 issues por proyecto, y Radarr #5566 pide justamente una pantalla de vista previa.

- `preview_rename(series | movie)` con `GET /rename` (ruta actual frente a ruta nueva), y `rename_files` con el comando `RenameFiles`.

### 7. Informe de espacio y limpieza → `library_report` ✅

Sonarr #314 «Auto delete episodes after certain criteria» (29 👍, abierto) y #1984 «Recycling Bin Management».

- Elementos que más ocupan, elementos no monitorizados que tienen archivos, series terminadas y completas, tamaño por calidad (películas) y elementos que faltan. Es solo de lectura: borrar sería un paso aparte y explícito. Pendiente: «calidades por encima del perfil».

### 8. Salud con solución → mejorar `get_health` ✅

- A cada aviso de salud se le añade la causa habitual y cómo arreglarla (cliente de descargas inaccesible, carpeta raíz ausente, indexers deshabilitados con su motivo, listas de importación que fallan…), además del enlace a la wiki que ya se devuelve.
- `test_download_clients` con `POST /downloadclient/testall`.

## Prioridad baja

9. **Comandos en curso:** `list_tasks` y `cancel_command` (`GET`/`DELETE /command`). Sonarr #1194 «Cancel/Suspend all tasks».
10. **Copias de seguridad:** `list_backups` y `create_backup` (`/system/backup`, comando `Backup`). Es una pregunta frecuente de la FAQ.
11. **Listas de importación:** estado y exclusiones (`/importlist`, `/importlistexclusion`). Las listas de IMDb y Trakt fallan a menudo (Sonarr #6915, Radarr #10121).
12. **Filtro de releases falsos:** comprobar y configurar en Sonarr/Radarr una regla de release profile que bloquee ejecutables (`/api/v3/releaseprofile`), con la regex que también coge los títulos normalizados (`/[.\s_-](exe|scr|lnk|bat|cmd|msi)$/i`). Surgió en una instalación real donde la regex habitual, con punto, dejó pasar tres falsos.
13. **Búsqueda en Prowlarr** (`GET /search`) en todos los indexers, para comparar con lo que ve Sonarr («Jackett shows more results than Sonarr»).

## Generalizar lo que hoy es específico de un usuario

- ✅ `find_orphan_downloads`: ya no depende de `ARR_DOWNLOADS_PATH`; las carpetas se deducen de la cola y del historial de importaciones.
- ✅ Mensajes de error: la pista sobre los puertos es genérica (puerto cambiado, contenedor parado), con Synology solo como ejemplo.
- `find_suspicious_releases`: la lista de extensiones debe ser configurable.
- ✅ Documentación en inglés (principal) y en español; mensajes de las tools en los dos idiomas (`ARR_LANG`).

## Distribución (idea, sin decidir)

Hoy, para instalarlo hace falta Python (y Git, o bajar el ZIP). Opciones para que sea más fácil para gente no técnica, todas generadas automáticamente por GitHub Actions en cada versión:

- **Extensión de Claude Desktop (`.mcpb`, tipo «binary»):** se instala con doble clic y Claude pide las URLs y API keys en un formulario (las keys se guardan como datos sensibles). No necesita Python. Solo Claude Desktop (Windows/macOS).
- **Ejecutable suelto** (`arr-doctor.exe` / binario de Linux) en GitHub Releases: no necesita Python; sirve para cualquier cliente MCP.
- **PyPI + `uvx arr-doctor`:** solo hace falta `uv` (descarga Python por su cuenta).
- **Docker en un NAS o servidor**, por HTTP y con token obligatorio. No se recomienda en el PC (necesita Docker Desktop abierto) ni a través de WSL (más piezas, y el `env` del cliente no llega a WSL).

Pegas: los ejecutables sin firma pueden activar el aviso de SmartScreen; los ejecutables con Python empaquetado ocupan 30–50 MB y algún antivirus los marca a veces; las descargas necesitan un repositorio público.

## Descartado (fuera del alcance de un MCP)

Multiusuario, SSO/LDAP, varias versiones de un mismo archivo, descomprimir RAR, nuevos clientes de descarga, métricas de Prometheus, notificaciones. Son funciones del propio Sonarr/Radarr.
