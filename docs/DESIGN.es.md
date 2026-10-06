# Notas de diseño

[English](DESIGN.md) · **Español**

Decisiones tomadas durante la implementación y detalles de la API de Sonarr/Radarr/Prowlarr que no son obvios. Los campos y endpoints se han comprobado contra los `openapi.json` oficiales (Sonarr `main`/v4, Radarr `develop`, Prowlarr `develop`) y, cuando hacía falta, contra el código fuente C#.

## Arquitectura

- **`clients/`** contiene toda la lógica HTTP: un método por endpoint y ningún formateo. **`tools/`** contiene las tools MCP: resuelven títulos, llaman a los clientes y compactan con `formatting.py`. Las tools nunca construyen URLs.
- **Un `httpx.AsyncClient` por petición.** Con un servidor stdio de un solo usuario y una red local, el coste es despreciable. A cambio, no hay estado compartido entre bucles de eventos, lo que simplifica los tests, y no hay conexiones colgadas si el NAS se reinicia.
- **`ArrError` hereda de `fastmcp.exceptions.ToolError`.** FastMCP devuelve su mensaje tal cual al modelo (`isError: true`) sin traceback. Un filtro de logging evita que fastmcp vuelque el traceback de estos errores esperados a stderr; los errores inesperados sí se registran.
- **Registro condicional.** `build_server(settings)` solo registra las tools de los servicios configurados, y las de escritura solo si `ARR_READONLY` es `false`. Las tools que no existen no confunden al modelo.
- **`per_service()`.** Las tools que consultan Sonarr y Radarr a la vez lo hacen en paralelo. Si uno falla, su entrada pasa a `{"error": …}` y el otro se devuelve igualmente. Solo se lanza error si fallan todos, o si se pidió un único servicio.
- **Idioma.** Las descripciones de las tools están en inglés, porque las lee el modelo. Todo lo que una tool devuelve como error, nota o pista pasa por `i18n.t()`, que usa el catálogo en inglés y español de `arr_doctor/i18n.py`. El idioma se elige con `ARR_LANG` (`en` por defecto). Un test comprueba que cada mensaje existe en los dos idiomas con los mismos parámetros.
- **Las rutas son las del equipo de Sonarr/Radarr**, no las del equipo donde corre este servidor, así que `arr_doctor/paths.py` las compara sin `pathlib`: funcionan rutas POSIX, de Windows (`D:\…`, sin distinguir mayúsculas) y UNC.
- **Windows y Linux.** El CI ejecuta todos los tests en ambos, incluido uno de extremo a extremo que lanza el proceso real (`python -m arr_doctor.server` y el ejecutable `arr-doctor`) por stdio contra un Sonarr falso local. stderr se reconfigura para que los logs con caracteres no ASCII nunca fallen en las tuberías de Windows.
- **stdio limpio.** Todo el logging va a stderr. `show_banner=False`. Los avisos de deprecación de `authlib` (dependencia indirecta de fastmcp) se silencian: authlib instala su propio filtro `always` al importarse, así que el nuestro se añade justo después.

## Identificadores flexibles

- Un `int` siempre es un ID.
- Un string formado solo por dígitos se trata **primero como título exacto** y después como ID. Así funcionan series y películas como «24» o «1917».
- Coincidencia de títulos: se normaliza (minúsculas, sin acentos ni puntuación) y se busca en `title`, `originalTitle` y `alternateTitles`. Se acepta un año al final («Dune 2021», «The Office (2005)»). Si hay una coincidencia exacta, se usa. Si hay varias, se devuelven `{"ambiguous": true, "candidates": […]}`. Si no hay exactas, se prueba por subcadena. Si tampoco hay ninguna, se lanza error con sugerencias de `difflib`.
- El caso ambiguo se devuelve como **resultado normal**, no como error, para que el modelo pregunte al usuario en lugar de reintentar.

## Detalles de la API

- **`eventType` del historial es un entero** en la query (`/history?eventType=1`), pero un string en la respuesta (`"grabbed"`). Los valores salen de los enums C#:
  - Sonarr: grabbed 1, seriesFolderImported 2, downloadFolderImported 3, downloadFailed 4, episodeFileDeleted 5, episodeFileRenamed 6, downloadIgnored 7.
  - Radarr: grabbed 1, downloadFolderImported 3, downloadFailed 4, movieFileDeleted 6, movieFolderImported 7, movieFileRenamed 8, downloadIgnored 9 (el 2 y el 5 están obsoletos).
- **`/history` no filtra por fecha.** Con `days`, se usa `/history/since?date=` y se filtra por serie o película en el cliente.
- **Parámetros de lista** (`seriesIds`, `eventType`): se envían repetidos (`?seriesIds=1&seriesIds=2`), como espera ASP.NET.
- **`/manualimport?folder=`** admite también **la ruta de un archivo** (`ManualImportService.GetMediaFiles`: si la ruta no es una carpeta pero existe como archivo, procesa solo ese archivo). `manual_import` lo aprovecha para escanear exactamente los archivos pedidos.
- **El comando `ManualImport`** recibe `files[]` con `path`, `seriesId` + `episodeIds` (Sonarr) o `movieId` (Radarr), además de `quality`, `languages`, `releaseGroup`, `downloadId`, `indexerFlags` y, en Sonarr, `releaseType`, copiados del resultado del escaneo. `importMode` puede ser `move`, `copy` o `auto`; se expone `move` (por defecto) y `copy`.
- **`RefreshSeries`** acepta `seriesIds` (lista) en v4. **`RefreshMovie`**, `movieIds`.
- **`MissingEpisodeSearch`** acepta un `seriesId` opcional y `monitored`.
- **Prowlarr `POST /indexer/testall`** responde **400** con el mismo cuerpo (`[{id, isValid, validationFailures}]`) cuando falla algún indexer. El cliente acepta ese 400 como respuesta válida.
- **Prowlarr `PUT /indexer/{id}`** necesita el recurso completo, así que primero se hace `GET` y luego se cambia `enable`. Los campos secretos llegan enmascarados como `********`; Prowlarr conserva el valor guardado cuando recibe esa máscara (`SchemaBuilder`), así que las credenciales sobreviven a la ida y vuelta (comprobado en el código y con un indexer privado real).
- **Monitorizar una serie** (`PUT /series/{id}` con `monitored`) no cambia sus temporadas. Para una temporada se modifica `seasons[n].monitored` y se envía la serie completa.
- **Monitorizar películas**: `PUT /movie/editor` con `{movieIds, monitored}`.
- **Los 404 genéricos** (`{"message": "NotFound"}`) se traducen a «no existe la ruta». Si el cuerpo trae un mensaje útil (por ejemplo, «Couldn't find requested release in cache, try searching again»), se muestra ese.
- **`GET /release`** es la búsqueda interactiva: consulta en directo todos los indexers y devuelve cada release con la decisión de Sonarr/Radarr (`approved`, `temporarilyRejected`, `rejections[]` como strings, `customFormatScore`). Los devuelve ya **ordenados por preferencia**. Admite `episodeId`, o `seriesId` + `seasonNumber` para una temporada (Sonarr), y `movieId` (Radarr).
- **`POST /release`** con `{guid, indexerId}` descarga un release. Sonarr/Radarr lo buscan en una caché de la búsqueda interactiva que dura **30 minutos** (clave `indexerId_guid`). Pasado ese tiempo, responden 404 y hay que volver a buscar.
- **`POST /manualimport`** (reprocess) recibe archivos con una asignación manual (`seriesId` + `seasonNumber` + `episodeIds`, o `movieId`) y los devuelve **revalidados**, con `rejections` y custom formats recalculados. Sonarr devuelve los `episodes` pero no el objeto `series`.
- **`GET /manualimport?downloadId=`** escanea la carpeta de salida de una descarga de la cola. Devuelve `[]` si Sonarr/Radarr no ven esa ruta.
- **`GET /parse?title=`** devuelve cómo se interpreta un nombre de release: `parsedEpisodeInfo` / `parsedMovieInfo`, la serie o película asociada, `customFormats` y `customFormatScore`.

## Descargas huérfanas (`find_orphan_downloads`)

1. Carpetas a escanear: el parámetro `folder`, `ARR_DOWNLOADS_PATH` o, si no hay ninguno, las que se deducen de la cola (padres de `outputPath`) y de las importaciones de los últimos 60 días (`droppedPath`, subiendo un nivel si la carpeta se llama como el release). Como mucho 3, y nunca una carpeta dentro de otra ya elegida.
2. `GET /manualimport?folder=…&filterExistingFiles=true` por carpeta, con un timeout de al menos 180 s porque en un NAS puede tardar.
3. Se descartan los archivos que rastrea la cola: su `downloadId` coincide con uno de la cola, o su ruta está dentro del `outputPath` de algún elemento de la cola.
4. Se agrupan por serie o película. Cada archivo se marca como `missing` (el episodio no tiene archivo), `duplicate` (ya lo tiene) o `partial` (multiepisodio con unos sí y otros no).
5. `episode_conflicts` lista los episodios con varios archivos candidatos, el caso típico de pack de temporada más episodio suelto.
6. Los archivos sin identificar van a `unmatched`. Si Sonarr y Radarr comparten la carpeta, las películas aparecen como `unmatched` en Sonarr y viceversa.

## Releases sospechosos (`find_suspicious_releases`)

- Los títulos de release se guardan normalizados («…H264-VICE.exe» pasa a «…H264 VICE exe»), así que al final de un título también cuenta un espacio, `_` o `-` antes de la extensión. Una regex de release profile como `/\.(exe|…)$/i` no los coge; `/[.\s_-](exe|scr|lnk|bat|cmd|msi)$/i` sí.
- Extensiones: `.exe .scr .lnk .bat .cmd .msi .zipx`. La expresión regular exige que no siga ninguna letra ni dígito, así que `.exe2` y `.msix` no cuentan, y `The.Executive` tampoco.
- Busca en la cola (título, `outputPath`, `errorMessage`, `statusMessages`), en el historial de los últimos N días (`sourceTitle`, `data.message`, `droppedPath`, `importedPath`) y en la blocklist.
- El indexer se toma del propio elemento o, si no viene, del evento `grabbed` con el mismo `downloadId`.
- `by_indexer` cuenta cada descarga una sola vez, aunque aparezca en la cola y en el historial.
- **Descargas antes del estreno:** una descarga hecha más de 24 h antes de la emisión del episodio (o del estreno digital/físico más temprano de una película). No todas son falsas: a veces una plataforma publica la temporada entera antes de las fechas de emisión. Lo que las distingue es qué pasó después: `likely: fake` si nunca se importó o falló, `early_release` si se importó. Solo los probables falsos cuentan por indexer.
- **Mismo tamaño:** descargas distintas (`downloadId` distintos) de episodios distintos con exactamente el mismo tamaño en bytes. Un pack de temporada es una sola descarga anotada por episodio con el tamaño del pack, así que nunca cuenta.

## Mantenimiento (`tools/maintenance.py`)

- **`bulk_edit_preview` / `bulk_edit_apply`** son tools separadas para que el diálogo de permiso del cliente nombre la llamada que escribe. La vista previa devuelve un `confirmation_token` (hash de los elementos y los cambios); la tool de aplicar lo exige para varios elementos o una selección por filtro, y pregunta directamente al usuario si el cliente soporta *elicitation*. Se seleccionan por IDs o títulos (resueltos sobre la lista ya cargada, sin peticiones extra) y/o con filtros. Los cambios van a `PUT /series/editor` o `/movie/editor` en una sola llamada; las etiquetas usan `applyTags: "add"`, y quitar etiquetas necesita una segunda llamada con `applyTags: "remove"`. Las etiquetas que no existen solo se crean al aplicar. La carpeta raíz no se ofrece: cambiarla mueve archivos.
- **`preview_rename` / `rename_files`** usan `GET /rename` (Sonarr: `seriesId` y opcionalmente `seasonNumber`; Radarr: `movieId`) y el comando `RenameFiles` con los IDs de archivo de esa vista previa (`episodeFileId` / `movieFileId`), así que se renombran exactamente los archivos mostrados.
- **`library_report`** se calcula con las estadísticas de `/series` y con `/movie` (`sizeOnDisk`, `movieFile.quality`). Solo lectura.
- **`get_health`** añade un `fix` a cada aviso cuyo `source` es un health check conocido (`DownloadClientCheck`, `RemotePathMappingCheck`, `IndexerStatusCheck`…, nombres sacados de `NzbDrone.Core/HealthCheck/Checks`). Los desconocidos se devuelven tal cual.
- **`test_download_clients`**: `POST /downloadclient/testall`, que, igual que en Prowlarr, responde 400 con los resultados de cada cliente cuando alguno falla.

## `manual_import`: todo o nada

No importa nada si alguno de los archivos:

- no existe o no es un vídeo importable,
- tiene `rejections` (por ejemplo, «Not an upgrade»),
- no se ha podido identificar como serie y episodio, o como película,
- apunta al mismo episodio (o película) que otro archivo de la lista.

En esos casos devuelve `problems` y `ok_files` para que el modelo pueda proponer una lista corregida.

Después de mandar el comando espera hasta 40 segundos (los clientes MCP suelen cortar una llamada a una tool al cabo de un minuto) y verifica cada archivo: un episodio o película solo cuenta como importado si el `dateAdded` de su archivo cae entre el `queued` y el `ended` del comando, así que no se confunde ni con un archivo antiguo ni con una importación posterior. Si el comando sigue en marcha, `get_command_status` hace la misma comprobación cuando termina, con la lista de archivos que guarda el propio comando (`body.files`). Código: `tools/importcheck.py`. Los fallos sacan el motivo de las entradas `warn` del log que mencionan el archivo. Existe porque Sonarr dio por buena una importación real de seis archivos en la que todos los movimientos fallaron («Not a directory»).

Con `matches`, un archivo se puede asignar a mano a una serie, temporada y episodios, o a una película. La asignación se manda primero a `POST /manualimport` para que Sonarr/Radarr la revaliden. Solo se importa si después no hay rechazos: el emparejado manual nunca sirve para saltarse las comprobaciones.

## Resolución de problemas (`tools/troubleshoot.py`)

- **`explain_search`**: primero hace comprobaciones baratas (monitorizado, emitido, disponibilidad mínima, tipo de serie, ya tiene archivo) y después la búsqueda interactiva. Los rechazos se agrupan sustituyendo los números por `#`, así que «Release is 14.2 GB…» y «Release is 18.7 GB…» cuentan como el mismo motivo. `closest_rejected` ordena los rechazados empezando por los temporales y por los que tienen menos motivos: son los que casi pasan.
- **`diagnose_import`**: junta los `statusMessages` y `errorMessage` de la cola con los `rejections` del escaneo de la descarga, y les aplica reglas por expresión regular (`IMPORT_RULES`), por prioridad: ejecutable/peligroso, permisos, ruta inexistente, sin identificar, not an upgrade, pack incompleto, sample, archivo corrupto, sin vídeos, RAR, bloqueado, sin espacio. Si el escaneo vuelve vacío y hay `outputPath`, el diagnóstico es «Sonarr no ve esa carpeta» (volúmenes de Docker o remote path mapping). Cada causa lleva su explicación y su solución en los dos idiomas.
- **`check_paths`**: muestra las carpetas raíz, los remote path mappings y los clientes de descarga (host, categoría y carpeta; nunca usuario ni contraseña). Comprueba que se ven las carpetas padre de las descargas completadas, con un escaneo de cada una (máximo 5), y añade los avisos de salud relacionados con rutas.
- **`find_stalled_downloads`**: marca como `stalled` las descargas cuyo mensaje dice stalled, no connections, no seeds o metadata; como `client_error` las que tienen estado `failed`, `downloadClientUnavailable` o `warning` con mensaje; y como `no_progress` las que siguen al 0 % pasadas `min_hours`. Las completadas o pendientes de importar no cuentan: eso es cosa de `diagnose_import`.
- **`parse_release`**: estima si un release sería una mejora. Es una **estimación** que reproduce las reglas principales del perfil de calidad, no el motor de decisión completo:
  - El rango de calidad sale del orden de `items` del perfil (de peor a mejor). Los grupos comparten rango, y su `id` puede ser el `cutoff`.
  - Calidad no permitida, o puntuación por debajo de `minFormatScore`: se rechaza.
  - Si no hay archivo: se descargaría.
  - Si las mejoras están desactivadas, o el archivo ya alcanza el `cutoff`: no es mejora.
  - Calidad mayor: mejora. Calidad menor: no lo es.
  - Con la misma calidad decide la puntuación de custom formats, respetando `cutoffFormatScore` y `minUpgradeFormatScore`.
  - Sin `S01E01` en el título y con los dos servicios configurados, se asume que es una película.

## Pendiente o abierto

- Validado contra Sonarr v4 y Radarr 6.2 reales (incluido que Sonarr acepta el `sortKey` de `/wanted/missing` sacado de la interfaz web). Pendiente: Prowlarr contra un servidor real y sustituir las fixtures de ejemplo por respuestas reales anonimizadas (`smoke.py --capture`).
- Fase 4: Download Station (`SYNO.DownloadStation2.Task`) y Plex.
