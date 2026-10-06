"""User-facing messages in English and Spanish (``ARR_LANG=en|es``).

Tool descriptions stay in English (they are read by the model); everything a
tool returns as an error, note or hint goes through :func:`t`.
"""

from __future__ import annotations

from typing import Any, Literal

Lang = Literal["en", "es"]
_lang: Lang = "en"


def set_language(lang: str) -> None:
    global _lang
    _lang = "es" if lang.lower().startswith("es") else "en"


def get_language() -> Lang:
    return _lang


def t_opt(key: str, **kwargs: Any) -> str | None:
    """Like :func:`t` but returns None for unknown keys."""
    return t(key, **kwargs) if key in MESSAGES else None


def t(key: str, **kwargs: Any) -> str:
    entry = MESSAGES[key]
    return entry.get(_lang, entry["en"]).format(**kwargs)


MESSAGES: dict[str, dict[str, str]] = {
    # ------------------------------------------------------------ HTTP / client
    "connect_error": {
        "en": "Could not connect to {svc} at {url} ({detail}). Is the service/container running? "
        "If the port was assigned automatically (e.g. Docker, Synology Container Manager) it may have "
        "changed; check {env}_URL.",
        "es": "No se pudo conectar con {svc} en {url} ({detail}). ¿Está el servicio o contenedor arrancado? "
        "Si el puerto se asignó automáticamente (p. ej. Docker, Synology Container Manager) puede haber "
        "cambiado; revisa {env}_URL.",
    },
    "timeout": {
        "en": "{svc} did not answer within {secs:g} s ({method} {path}). It may be busy; try again or raise ARR_TIMEOUT.",
        "es": "{svc} no respondió en {secs:g} s ({method} {path}). Puede estar ocupado; prueba de nuevo o sube ARR_TIMEOUT.",
    },
    "network_error": {
        "en": "Network error talking to {svc}: {detail}",
        "es": "Error de red hablando con {svc}: {detail}",
    },
    "not_json": {
        "en": "{svc} returned a non-JSON response for {method} {path}. Is {env}_URL correct?",
        "es": "{svc} devolvió una respuesta que no es JSON en {method} {path}. ¿Es correcta {env}_URL?",
    },
    "http_401": {
        "en": "{svc} returned 401: wrong API key (check {env}_API_KEY).",
        "es": "{svc} devolvió 401: API key incorrecta (revisa {env}_API_KEY).",
    },
    "http_403": {
        "en": "{svc} returned 403: access denied to {method} {path}.",
        "es": "{svc} devolvió 403: acceso denegado a {method} {path}.",
    },
    "http_404": {
        "en": "{svc} returned 404: {path} does not exist.",
        "es": "{svc} devolvió 404: no existe {path}.",
    },
    "http_4xx": {
        "en": "{svc} returned {code} for {method} {path}: {detail}",
        "es": "{svc} devolvió {code} en {method} {path}: {detail}",
    },
    "http_5xx": {
        "en": "{svc} returned {code} (internal error) for {method} {path}: {detail}",
        "es": "{svc} devolvió {code} (error interno) en {method} {path}: {detail}",
    },
    "request_rejected": {"en": "request rejected", "es": "petición rechazada"},
    "no_detail": {"en": "no details", "es": "sin detalle"},
    # ------------------------------------------------------------ config
    "not_configured": {
        "en": "{svc} is not configured ({env}_URL / {env}_API_KEY missing).",
        "es": "{svc} no está configurado (faltan {env}_URL / {env}_API_KEY).",
    },
    "no_services": {
        "en": "No service configured: set SONARR_URL + SONARR_API_KEY and/or RADARR_URL + RADARR_API_KEY "
        "(in .env or in the env block of your MCP client config).",
        "es": "No hay ningún servicio configurado: define SONARR_URL + SONARR_API_KEY y/o RADARR_URL + "
        "RADARR_API_KEY (en .env o en el bloque env de la configuración del cliente MCP).",
    },
    "incomplete_service": {
        "en": "{svc} has only a URL or only an API key; ignored (set {env}_URL and {env}_API_KEY).",
        "es": "{svc} tiene solo URL o solo API key; se ignora (define {env}_URL y {env}_API_KEY).",
    },
    # ------------------------------------------------------------ resolution
    "ambiguous": {
        "en": "'{query}' matches several {kind}. Call again with the ID of the right one.",
        "es": "'{query}' coincide con varias {kind}. Repite la llamada con el ID de la correcta.",
    },
    "kind_series": {"en": "series", "es": "series"},
    "kind_movies": {"en": "movies", "es": "películas"},
    "need_title_or_id": {"en": "Give a title or an ID.", "es": "Indica un título o un ID."},
    "series_not_found": {
        "en": "No series found with the title '{query}'.{hint}",
        "es": "No encontré ninguna serie con el título '{query}'.{hint}",
    },
    "movie_not_found": {
        "en": "No movie found with the title '{query}'.{hint}",
        "es": "No encontré ninguna película con el título '{query}'.{hint}",
    },
    "did_you_mean": {"en": " Did you mean: {options}?", "es": " ¿Quizá: {options}?"},
    "indexer_not_found": {
        "en": "There is no indexer called '{query}'. Available: {names}",
        "es": "No hay ningún indexer llamado '{query}'. Disponibles: {names}",
    },
    "indexer_ambiguous": {
        "en": "'{query}' matches several indexers: {names}",
        "es": "'{query}' coincide con varios indexers: {names}",
    },
    # ------------------------------------------------------------ actions
    "command_note": {
        "en": "Asynchronous command: follow it with get_command_status.",
        "es": "Comando asíncrono: consulta su progreso con get_command_status.",
    },
    "episodes_not_in_season": {
        "en": "{title} has no episodes {missing} in season {season}.",
        "es": "{title} no tiene los episodios {missing} en la temporada {season}.",
    },
    "need_season_and_episodes": {
        "en": "With `series` also give `season` and `episodes` (episode numbers).",
        "es": "Con `series` indica también `season` y `episodes` (números de episodio).",
    },
    "need_episode_target": {
        "en": "Give `episode_ids` or `series` + `season` + `episodes`.",
        "es": "Indica `episode_ids` o `series` + `season` + `episodes`.",
    },
    "already_in_library": {
        "en": "'{title}' is already in {svc} (id {id}).",
        "es": "'{title}' ya está en {svc} (id {id}).",
    },
    "no_such_season": {
        "en": "{title} has no season {season}.",
        "es": "{title} no tiene temporada {season}.",
    },
    "series_monitor_note": {
        "en": "Monitoring the series does not change its seasons; use `season` for each one.",
        "es": "Monitorizar la serie no cambia sus temporadas; usa `season` para cada una.",
    },
    "need_monitor_target": {
        "en": "Give `episode_ids`, `series` (optionally with `season`) or `movie`.",
        "es": "Indica `episode_ids`, `series` (opcionalmente con `season`) o `movie`.",
    },
    "need_series_or_movie": {"en": "Give `series` or `movie`.", "es": "Indica `series` o `movie`."},
    "not_in_queue": {"en": "not in the queue", "es": "no está en la cola"},
    "import_not_found": {
        "en": "does not exist or is not an importable video file",
        "es": "no existe o no es un archivo de vídeo importable",
    },
    "import_rejected": {"en": "rejected", "es": "rechazado"},
    "import_unidentified_series": {
        "en": "could not identify the series/episode; pass series + episodes in `matches`",
        "es": "no se pudo identificar la serie/episodio; indica serie y episodios en `matches`",
    },
    "import_unidentified_movie": {
        "en": "could not identify the movie; pass the movie in `matches`",
        "es": "no se pudo identificar la película; indica la película en `matches`",
    },
    "import_same_target": {
        "en": "several files for the same {target} (id {id}); pick one",
        "es": "varios archivos para el mismo {target} (id {id}); elige uno",
    },
    "target_episode": {"en": "episode", "es": "episodio"},
    "target_movie": {"en": "movie", "es": "película"},
    "nothing_imported": {"en": "Nothing was imported.", "es": "No se ha importado nada."},
    "match_for_unknown_file": {
        "en": "`matches` refers to a file that is not in `files`: {path}",
        "es": "`matches` se refiere a un archivo que no está en `files`: {path}",
    },
    "match_bad_episodes": {
        "en": "{title} has no episode(s) {codes}",
        "es": "{title} no tiene los episodios {codes}",
    },
    "lookup_empty": {
        "en": "The online lookup for '{term}' returned no results.",
        "es": "La búsqueda online de '{term}' no devolvió resultados.",
    },
    "lookup_id_missing": {
        "en": "No result for '{term}' has {label}={id}.",
        "es": "Ningún resultado de '{term}' tiene {label}={id}.",
    },
    "lookup_ambiguous": {
        "en": "Several results for '{term}'. Call again with {label}.",
        "es": "Hay varios resultados para '{term}'. Repite la llamada con {label}.",
    },
    "profile_missing": {"en": "quality_profile '{value}' does not exist", "es": "quality_profile '{value}' no existe"},
    "folder_missing": {"en": "root_folder '{value}' does not exist", "es": "root_folder '{value}' no existe"},
    "choose_profile_folder": {
        "en": "Give quality_profile and root_folder (pick from the options).",
        "es": "Indica quality_profile y root_folder (elige de las opciones).",
    },
    # ------------------------------------------------------------ diagnostics
    "remove_hint": {
        "en": "To remove them: remove_from_queue with blocklist=true (skip_redownload=false searches for another "
        "release; if the episode/movie is not out yet, use skip_redownload=true: before release only fakes show up).",
        "es": "Para quitarlos: remove_from_queue con blocklist=true (skip_redownload=false busca otra versión; "
        "si el episodio o la película aún no ha salido, usa skip_redownload=true: antes del estreno solo hay falsos).",
    },
    "movie_multiple_files": {
        "en": "several files for the same movie",
        "es": "varios archivos para la misma película",
    },
    # ------------------------------------------------------------ troubleshooting: import diagnosis
    "diag_dangerous": {
        "en": "The download contains an executable or dangerous file: it is almost certainly a fake release.",
        "es": "La descarga contiene un ejecutable o un archivo peligroso: casi seguro que es un release falso.",
    },
    "fix_dangerous": {
        "en": "remove_from_queue with blocklist=true (a replacement is searched automatically). Check which indexer it came from.",
        "es": "remove_from_queue con blocklist=true (se busca otro release automáticamente). Revisa de qué indexer vino.",
    },
    "diag_permissions": {
        "en": "Sonarr/Radarr do not have permission to read the download or write to the library.",
        "es": "Sonarr/Radarr no tienen permisos para leer la descarga o escribir en la biblioteca.",
    },
    "fix_permissions": {
        "en": "Make the download client and Sonarr/Radarr run with the same user/group (PUID/PGID in Docker) and give that group read/write on both folders.",
        "es": "Haz que el cliente de descargas y Sonarr/Radarr usen el mismo usuario/grupo (PUID/PGID en Docker) y da a ese grupo lectura/escritura en ambas carpetas.",
    },
    "diag_path_missing": {
        "en": "The path reported by the download client does not exist from Sonarr/Radarr's point of view.",
        "es": "La ruta que da el cliente de descargas no existe desde el punto de vista de Sonarr/Radarr.",
    },
    "fix_path_missing": {
        "en": "Use the same paths in both containers (e.g. mount /data in both) or add a Remote Path Mapping (Settings → Download Clients). Run check_paths.",
        "es": "Usa las mismas rutas en ambos contenedores (p. ej. monta /data en los dos) o añade un Remote Path Mapping (Settings → Download Clients). Ejecuta check_paths.",
    },
    "diag_path_not_visible": {
        "en": "Sonarr/Radarr cannot see any video file in {path}.",
        "es": "Sonarr/Radarr no ven ningún archivo de vídeo en {path}.",
    },
    "fix_path_not_visible": {
        "en": "Either the folder is not mounted/visible in the Sonarr/Radarr container (fix Docker volumes or add a Remote Path Mapping), or the download has no video (only archives/samples).",
        "es": "O la carpeta no está montada/visible en el contenedor de Sonarr/Radarr (corrige los volúmenes de Docker o añade un Remote Path Mapping), o la descarga no tiene vídeo (solo comprimidos/samples).",
    },
    "diag_root_inaccessible": {
        "en": "The root folder {path} is not accessible.",
        "es": "La carpeta raíz {path} no es accesible.",
    },
    "fix_root_inaccessible": {
        "en": "Check that the volume is mounted in the container and the user has write access.",
        "es": "Comprueba que el volumen está montado en el contenedor y que el usuario tiene permiso de escritura.",
    },
    "diag_unknown_match": {
        "en": "Sonarr/Radarr could not match the release to a series/episode or movie automatically.",
        "es": "Sonarr/Radarr no han podido asociar el release a una serie/episodio o película automáticamente.",
    },
    "fix_unknown_match": {
        "en": "Use manual_import with `matches` to assign it by hand. If it happens often, add an alias/scene mapping or check the series type.",
        "es": "Usa manual_import con `matches` para asignarlo a mano. Si pasa a menudo, añade un alias/scene mapping o revisa el tipo de serie.",
    },
    "diag_not_upgrade": {
        "en": "The existing file is already as good or better (quality or custom format score).",
        "es": "El archivo existente ya es igual o mejor (calidad o puntuación de custom formats).",
    },
    "fix_not_upgrade": {
        "en": "Remove it from the queue (it is not needed), or compare both with parse_release if you think it is better.",
        "es": "Quítalo de la cola (no hace falta), o compara ambos con parse_release si crees que es mejor.",
    },
    "diag_partial_pack": {
        "en": "Some episodes expected in the release were not found in the download.",
        "es": "Faltan en la descarga algunos episodios que se esperaban en el release.",
    },
    "fix_partial_pack": {
        "en": "Import the files that are there with manual_import and search the missing episodes separately.",
        "es": "Importa los archivos que sí están con manual_import y busca por separado los episodios que faltan.",
    },
    "diag_sample": {
        "en": "The file was detected as a sample (too short or too small).",
        "es": "El archivo se ha detectado como sample (demasiado corto o pequeño).",
    },
    "fix_sample": {
        "en": "Blocklist the release and search another one; if it really is the full episode, import it manually.",
        "es": "Mete el release en la blocklist y busca otro; si de verdad es el episodio completo, impórtalo a mano.",
    },
    "diag_corrupt": {
        "en": "The video file could not be analysed (runtime 0 or invalid/corrupt file).",
        "es": "No se ha podido analizar el vídeo (duración 0 o archivo inválido/corrupto).",
    },
    "fix_corrupt": {
        "en": "The download is probably incomplete or broken: remove it with blocklist=true.",
        "es": "La descarga probablemente está incompleta o rota: quítala con blocklist=true.",
    },
    "diag_no_files": {
        "en": "No importable video files were found in the download.",
        "es": "No se encontraron archivos de vídeo importables en la descarga.",
    },
    "fix_no_files": {
        "en": "It may contain only archives (.rar) or the wrong content. Check the folder; remove it with blocklist if it is wrong.",
        "es": "Puede contener solo comprimidos (.rar) o un contenido erróneo. Revisa la carpeta; quítala con blocklist si está mal.",
    },
    "diag_unpacking": {
        "en": "The download is packed (RAR) or still being unpacked.",
        "es": "La descarga está comprimida (RAR) o aún se está descomprimiendo.",
    },
    "fix_unpacking": {
        "en": "Sonarr/Radarr do not unpack: use a client/tool that extracts automatically (e.g. Unpackerr) and wait for it.",
        "es": "Sonarr/Radarr no descomprimen: usa un cliente o herramienta que extraiga automáticamente (p. ej. Unpackerr) y espera.",
    },
    "diag_locked": {
        "en": "The file is locked or in use by another process.",
        "es": "El archivo está bloqueado o en uso por otro proceso.",
    },
    "fix_locked": {
        "en": "Usually temporary: wait a few minutes. If it persists, check whether the client is still moving or seeding from a locked location.",
        "es": "Suele ser temporal: espera unos minutos. Si sigue, revisa si el cliente aún está moviendo el archivo o sembrando desde una ubicación bloqueada.",
    },
    "diag_disk_space": {
        "en": "There is not enough free space to import.",
        "es": "No hay espacio libre suficiente para importar.",
    },
    "fix_disk_space": {
        "en": "Free space on the library volume (get_disk_space).",
        "es": "Libera espacio en el volumen de la biblioteca (get_disk_space).",
    },
    "diag_still_downloading": {
        "en": "It has not finished downloading yet.",
        "es": "Todavía no ha terminado de descargarse.",
    },
    "fix_still_downloading": {
        "en": "Wait; if it does not progress, check find_stalled_downloads.",
        "es": "Espera; si no avanza, revisa find_stalled_downloads.",
    },
    "diag_unknown": {
        "en": "No known cause found in the status messages.",
        "es": "No se ha encontrado una causa conocida en los mensajes de estado.",
    },
    "fix_unknown": {
        "en": "Check get_logs (level warn) around the import time and check_paths.",
        "es": "Revisa get_logs (nivel warn) en torno a la hora de la importación y check_paths.",
    },
    "queue_item_not_found": {
        "en": "There is no queue item with id {id}.",
        "es": "No hay ningún elemento en la cola con id {id}.",
    },
    "stalled_hint": {
        "en": "To replace them: remove_from_queue with blocklist=true (a different release will be searched).",
        "es": "Para sustituirlos: remove_from_queue con blocklist=true (se buscará otro release).",
    },
    # ------------------------------------------------------------ troubleshooting: search
    "need_season": {"en": "With `series` give at least `season`.", "es": "Con `series` indica al menos `season`."},
    "check_series_unmonitored": {
        "en": "The series is not monitored: automatic searches skip it.",
        "es": "La serie no está monitorizada: las búsquedas automáticas la ignoran.",
    },
    "check_season_unmonitored": {
        "en": "Season {season} is not monitored.",
        "es": "La temporada {season} no está monitorizada.",
    },
    "check_episode_unmonitored": {
        "en": "The episode is not monitored.",
        "es": "El episodio no está monitorizado.",
    },
    "check_not_aired": {
        "en": "It has not aired yet ({date}); releases usually appear after airing.",
        "es": "Aún no se ha emitido ({date}); los releases suelen aparecer después de la emisión.",
    },
    "check_series_type": {
        "en": "Series type is '{type}': if releases use normal SxxEyy numbering, the type may be wrong.",
        "es": "El tipo de serie es '{type}': si los releases usan numeración SxxEyy normal, el tipo puede ser incorrecto.",
    },
    "check_movie_unmonitored": {
        "en": "The movie is not monitored: automatic searches skip it.",
        "es": "La película no está monitorizada: las búsquedas automáticas la ignoran.",
    },
    "check_movie_not_available": {
        "en": "The movie is not considered available yet (minimum availability: {availability}); automatic searches wait.",
        "es": "La película aún no se considera disponible (disponibilidad mínima: {availability}); las búsquedas automáticas esperan.",
    },
    "check_has_file": {
        "en": "It already has a file: only upgrades are grabbed.",
        "es": "Ya tiene archivo: solo se descargan mejoras.",
    },
    "check_no_results": {
        "en": "The indexers returned nothing: check the indexers (list_indexers/test_indexers), the series aliases/scene numbering, or try other indexers.",
        "es": "Los indexers no devolvieron nada: revisa los indexers (list_indexers/test_indexers), los alias/numeración de escena de la serie, o prueba otros indexers.",
    },
    "check_none_approved": {
        "en": "There are releases but all were rejected; see rejection_reasons.",
        "es": "Hay releases pero todos se rechazaron; mira rejection_reasons.",
    },
    "grab_note": {
        "en": "To download one anyway: grab_release with its guid and indexer_id (valid ~30 min).",
        "es": "Para descargar uno igualmente: grab_release con su guid e indexer_id (válido ~30 min).",
    },
    # ------------------------------------------------------------ troubleshooting: parse
    "parse_failed": {
        "en": "The title could not be parsed as a release name.",
        "es": "No se ha podido interpretar el título como nombre de release.",
    },
    "parse_no_series": {
        "en": "Parsed, but it does not match any series in the library.",
        "es": "Se interpreta, pero no corresponde a ninguna serie de la biblioteca.",
    },
    "parse_no_movie": {
        "en": "Parsed, but it does not match any movie in the library.",
        "es": "Se interpreta, pero no corresponde a ninguna película de la biblioteca.",
    },
    "verdict_quality_not_allowed": {
        "en": "Its quality is not allowed in the quality profile.",
        "es": "Su calidad no está permitida en el perfil de calidad.",
    },
    "verdict_below_min_score": {
        "en": "Custom format score {score} is below the profile minimum ({min}).",
        "es": "La puntuación de custom formats {score} está por debajo del mínimo del perfil ({min}).",
    },
    "verdict_no_file": {"en": "There is no file yet, so it would be grabbed.", "es": "Aún no hay archivo, así que se descargaría."},
    "verdict_upgrades_disabled": {
        "en": "Upgrades are disabled in the quality profile.",
        "es": "Las mejoras están desactivadas en el perfil de calidad.",
    },
    "verdict_cutoff_met": {
        "en": "The existing file already meets the quality cutoff.",
        "es": "El archivo existente ya alcanza el corte de calidad.",
    },
    "verdict_better_quality": {
        "en": "Higher quality than the existing file in the profile order.",
        "es": "Calidad superior a la del archivo existente según el orden del perfil.",
    },
    "verdict_worse_quality": {
        "en": "Lower quality than the existing file in the profile order.",
        "es": "Calidad inferior a la del archivo existente según el orden del perfil.",
    },
    "verdict_score_cutoff_met": {
        "en": "Same quality, and the existing file already reaches the custom format cutoff ({cutoff}).",
        "es": "Misma calidad, y el archivo existente ya alcanza el corte de custom formats ({cutoff}).",
    },
    "verdict_better_score": {
        "en": "Same quality but better custom format score ({new} vs {old}).",
        "es": "Misma calidad pero mejor puntuación de custom formats ({new} frente a {old}).",
    },
    "verdict_same_or_lower_score": {
        "en": "Same quality and custom format score not high enough ({new} vs {old}).",
        "es": "Misma calidad y puntuación de custom formats insuficiente ({new} frente a {old}).",
    },
    "no_download_folder": {
        "en": "Could not detect {svc}'s download folder (empty queue and no recent imports). "
        "Pass `folder` or set ARR_DOWNLOADS_PATH.",
        "es": "No se ha podido detectar la carpeta de descargas de {svc} (cola vacía y sin importaciones "
        "recientes). Indica `folder` o define ARR_DOWNLOADS_PATH.",
    },
    # ------------------------------------------------------------ health fixes (by health check source)
    "health_DownloadClientCheck": {
        "en": 'Check that the download client is running and that host, port, user and password in Settings → Download Clients are right; use test_download_clients.',
        "es": 'Comprueba que el cliente de descargas está en marcha y que host, puerto, usuario y contraseña en Settings → Download Clients son correctos; usa test_download_clients.',
    },
    "health_DownloadClientStatusCheck": {
        "en": 'The download client failed repeatedly and was temporarily disabled. Fix the connection (test_download_clients); it re-enables itself after a while.',
        "es": 'El cliente de descargas falló varias veces y se ha desactivado temporalmente. Arregla la conexión (test_download_clients); se reactiva solo al cabo de un rato.',
    },
    "health_DownloadClientRootFolderCheck": {
        "en": 'The download client saves into a library root folder. Downloads and library must be different folders.',
        "es": 'El cliente de descargas guarda dentro de una carpeta raíz de la biblioteca. Descargas y biblioteca deben ser carpetas distintas.',
    },
    "health_DownloadClientRemovesCompletedDownloadsCheck": {
        "en": 'The download client deletes completed downloads before they can be imported. Disable that option in the client.',
        "es": 'El cliente de descargas borra las descargas completadas antes de que se importen. Desactiva esa opción en el cliente.',
    },
    "health_DownloadClientSortingCheck": {
        "en": 'The download client sorts/renames completed downloads into other folders. Disable sorting for this category.',
        "es": 'El cliente de descargas ordena o renombra las descargas completadas en otras carpetas. Desactiva esa función para esta categoría.',
    },
    "health_ImportMechanismCheck": {
        "en": 'Completed Download Handling is disabled or misconfigured: enable it in Settings → Download Clients.',
        "es": 'La gestión de descargas completadas está desactivada o mal configurada: actívala en Settings → Download Clients.',
    },
    "health_RemotePathMappingCheck": {
        "en": 'Sonarr/Radarr cannot see the path the download client reports. Mount the same folder in both containers or add a Remote Path Mapping; run check_paths.',
        "es": 'Sonarr/Radarr no ven la ruta que da el cliente de descargas. Monta la misma carpeta en ambos contenedores o añade un Remote Path Mapping; ejecuta check_paths.',
    },
    "health_RootFolderCheck": {
        "en": 'A root folder is missing or not accessible. Check that the volume is mounted and writable, or fix the series/movie paths.',
        "es": 'Falta una carpeta raíz o no es accesible. Comprueba que el volumen está montado y con permiso de escritura, o corrige las rutas de las series/películas.',
    },
    "health_MountCheck": {
        "en": 'A folder is mounted read-only. Mount it read-write.',
        "es": 'Hay una carpeta montada en solo lectura. Móntala con lectura y escritura.',
    },
    "health_IndexerRssCheck": {
        "en": 'No indexer has RSS enabled, so new releases are not grabbed automatically. Enable RSS on at least one indexer.',
        "es": 'Ningún indexer tiene RSS activado, así que los releases nuevos no se descargan solos. Activa RSS en al menos un indexer.',
    },
    "health_IndexerSearchCheck": {
        "en": 'No indexer has search enabled. Enable automatic/interactive search on at least one indexer.',
        "es": 'Ningún indexer tiene la búsqueda activada. Activa la búsqueda automática o interactiva en al menos un indexer.',
    },
    "health_IndexerStatusCheck": {
        "en": 'Some indexers failed and are temporarily disabled. Check them with list_indexers / test_indexers.',
        "es": 'Algunos indexers han fallado y están desactivados temporalmente. Revísalos con list_indexers / test_indexers.',
    },
    "health_IndexerLongTermStatusCheck": {
        "en": 'Some indexers have been failing for more than 6 hours. They are probably down or blocked; consider disabling them.',
        "es": 'Algunos indexers llevan más de 6 horas fallando. Probablemente estén caídos o bloqueados; plantéate desactivarlos.',
    },
    "health_IndexerJackettAllCheck": {
        "en": "Jackett's /all endpoint is used. Add each indexer separately (or use Prowlarr).",
        "es": 'Se usa el endpoint /all de Jackett. Añade cada indexer por separado (o usa Prowlarr).',
    },
    "health_IndexerDownloadClientCheck": {
        "en": 'An indexer points to a download client that no longer exists. Edit the indexer.',
        "es": 'Un indexer apunta a un cliente de descargas que ya no existe. Edita el indexer.',
    },
    "health_ImportListStatusCheck": {
        "en": 'Some import lists are failing (often IMDb/Trakt changes). Re-authenticate or check the list URL.',
        "es": 'Algunas listas de importación fallan (a menudo por cambios de IMDb/Trakt). Vuelve a autenticarte o revisa la URL de la lista.',
    },
    "health_ImportListRootFolderCheck": {
        "en": 'An import list uses a root folder that no longer exists. Edit the list.',
        "es": 'Una lista de importación usa una carpeta raíz que ya no existe. Edita la lista.',
    },
    "health_SystemTimeCheck": {
        "en": 'The system clock is wrong. Fix the time/time zone of the host or container.',
        "es": 'La hora del sistema es incorrecta. Corrige la hora o la zona horaria del equipo o contenedor.',
    },
    "health_UpdateCheck": {
        "en": 'If the message says an update is available: in Docker, update by pulling the new image and recreating the container; otherwise use System → Updates. If it says the update cannot be installed: check that the app folder is writable by its user (built-in updates are disabled in Docker on purpose).',
        "es": 'Si el mensaje dice que hay una actualización: en Docker, descarga la imagen nueva y vuelve a crear el contenedor; si no, usa System → Updates. Si dice que no se puede instalar: comprueba que el usuario de la app puede escribir en su carpeta (en Docker las actualizaciones internas están desactivadas a propósito).',
    },
    "health_ProxyCheck": {
        "en": 'The configured proxy does not work. Fix or remove it in Settings → General.',
        "es": 'El proxy configurado no funciona. Corrígelo o quítalo en Settings → General.',
    },
    "health_RemovedSeriesCheck": {
        "en": 'Some series were removed from TheTVDB. Search for them again or delete them.',
        "es": 'Algunas series se han eliminado de TheTVDB. Búscalas de nuevo o bórralas.',
    },
    "health_RemovedMovieCheck": {
        "en": 'Some movies were removed from TMDb. Search for them again or delete them.',
        "es": 'Algunas películas se han eliminado de TMDb. Búscalas de nuevo o bórralas.',
    },
    "health_RecyclingBinCheck": {
        "en": 'The recycling bin folder is not writable. Fix its permissions or path.',
        "es": 'La carpeta de la papelera no tiene permiso de escritura. Corrige sus permisos o su ruta.',
    },
    "health_NotificationStatusCheck": {
        "en": 'Some notifications (Plex, Discord…) are failing. Test them in Settings → Connect.',
        "es": 'Algunas notificaciones (Plex, Discord…) fallan. Pruébalas en Settings → Connect.',
    },
    "health_AppDataLocationCheck": {
        "en": 'The app data folder is inside the program folder and would be lost on update. Move it.',
        "es": 'La carpeta de datos está dentro de la carpeta del programa y se perdería al actualizar. Muévela.',
    },
    "health_ApiKeyValidationCheck": {
        "en": 'The API key is too short. Regenerate it in Settings → General (and update it here).',
        "es": 'La API key es demasiado corta. Regenérala en Settings → General (y actualízala aquí).',
    },
    # ------------------------------------------------------------ maintenance
    "nothing_to_rename": {"en": "Everything already matches the naming settings.", "es": "Todo cumple ya la configuración de nombres."},
    "bulk_need_selection": {
        "en": "Select what to edit: `items` and/or at least one filter (status, monitored, quality_profile, tag, year_from, year_to, complete).",
        "es": "Indica qué editar: `items` y/o al menos un filtro (status, monitored, quality_profile, tag, year_from, year_to, complete).",
    },
    "bulk_need_change": {
        "en": "Give at least one change (set_monitored, set_quality_profile, add_tags, remove_tags, set_series_type, set_minimum_availability).",
        "es": "Indica al menos un cambio (set_monitored, set_quality_profile, add_tags, remove_tags, set_series_type, set_minimum_availability).",
    },
    "bulk_wrong_service": {"en": "`{field}` only applies to {svc}.", "es": "`{field}` solo se aplica a {svc}."},
    "bulk_preview_note": {
        "en": "Preview only, nothing changed. Show it to the user; if they agree, call bulk_edit_apply with the same selection and changes plus this confirmation_token.",
        "es": "Solo vista previa, no se ha cambiado nada. Enséñasela al usuario; si está de acuerdo, llama a bulk_edit_apply con la misma selección y cambios y este confirmation_token.",
    },
    "bulk_nothing_matched": {"en": "Nothing matches the selection.", "es": "Nada coincide con la selección."},
    "id_not_found": {"en": "There are no {kind} with id {id}.", "es": "No hay {kind} con id {id}."},
    # ------------------------------------------------------------ guardrails
    "budget_exceeded": {
        "en": "Indexer budget reached: {limit} searches/grabs/tests in the last hour. This protects your indexers "
        "(API and grab limits, bans). Try again in about {minutes} min, or raise ARR_INDEXER_BUDGET_PER_HOUR.",
        "es": "Presupuesto de indexers agotado: {limit} búsquedas/descargas/pruebas en la última hora. Es para proteger "
        "tus indexers (límites de API y de descargas, baneos). Vuelve a intentarlo en unos {minutes} min o sube "
        "ARR_INDEXER_BUDGET_PER_HOUR.",
    },
    "search_confirm": {
        "en": "This would search {n} items (more than {threshold}). Sonarr/Radarr already pick up new releases via RSS; "
        "a mass search queries every indexer once per item. Tell the user the count and call again with confirm=true "
        "only if they agree.",
        "es": "Esto buscaría {n} elementos (más de {threshold}). Sonarr/Radarr ya recogen los releases nuevos por RSS; "
        "una búsqueda masiva consulta todos los indexers una vez por elemento. Dile al usuario cuántos son y repite "
        "con confirm=true solo si está de acuerdo.",
    },
    "all_recently_searched": {
        "en": "Everything was already searched in the last {minutes} min; searching again so soon rarely finds anything. "
        "Use force=true if really needed.",
        "es": "Todo se buscó ya en los últimos {minutes} min; volver a buscar tan pronto casi nunca encuentra nada. "
        "Usa force=true si de verdad hace falta.",
    },
    "nothing_missing": {"en": "Nothing monitored is missing.", "es": "No falta nada monitorizado."},
    "remove_confirm": {
        "en": "This would remove {n} queue items. Tell the user and call again with confirm=true if they agree.",
        "es": "Esto quitaría {n} elementos de la cola. Díselo al usuario y repite con confirm=true si está de acuerdo.",
    },
    "replace_needs_allow": {
        "en": "These files would replace files already in the library (the old ones are deleted). Pass allow_replace=true if the user agrees.",
        "es": "Estos archivos sustituirían a otros que ya están en la biblioteca (los antiguos se borran). Pasa allow_replace=true si el usuario está de acuerdo.",
    },
    "recycle_bin_off": {
        "en": "No recycle bin is configured: the replaced files are deleted permanently.",
        "es": "No hay papelera de reciclaje configurada: los archivos sustituidos se borran para siempre.",
    },
    "rename_preview_note": {
        "en": "Preview only, nothing renamed. Show it to the user and call again with apply=true to rename.",
        "es": "Solo vista previa, no se ha renombrado nada. Enséñasela al usuario y repite con apply=true para renombrar.",
    },
    "import_still_running": {
        "en": "The import is still running (moving files on a NAS can take minutes). Call get_command_status with this command_id in a while: when it finishes it verifies every file.",
        "es": "La importación sigue en marcha (mover archivos en un NAS puede tardar minutos). Llama a get_command_status con este command_id dentro de un rato: cuando termine, verificará cada archivo.",
    },
    "import_verify_failed": {
        "en": "{svc} reported the command as finished, but these files did not reach the library. Nothing was lost: they are still where they were. See `reason`.",
        "es": "{svc} dio el comando por terminado, pero estos archivos no han llegado a la biblioteca. No se ha perdido nada: siguen donde estaban. Mira `reason`.",
    },
    "diag_path_conflict": {
        "en": "Something in the library path is in the way: a file exists where a folder should be created (\"Not a directory\" / \"already exists\").",
        "es": "Algo estorba en la ruta de la biblioteca: hay un archivo donde se debería crear una carpeta («Not a directory» / «already exists»).",
    },
    "fix_path_conflict": {
        "en": "Look at the path in the error with your file manager, rename or move the file that blocks it, then import again.",
        "es": "Mira la ruta del error con tu gestor de archivos, renombra o mueve el archivo que la bloquea y vuelve a importar.",
    },
    "redirected": {
        "en": "{svc} answered {code} redirecting to {location}. Redirects are not followed (the API key must not be "
        "sent anywhere else): set {env}_URL to the final address.",
        "es": "{svc} respondió {code} redirigiendo a {location}. Las redirecciones no se siguen (la API key no debe "
        "enviarse a otro sitio): pon en {env}_URL la dirección final.",
    },
    # ------------------------------------------------------------ Prowlarr health fixes
    "health_IndexerNoDefinitionCheck": {
        "en": 'These indexers have no definition any more (the site changed or closed) and will not work. Delete them in Prowlarr and add a working alternative.',
        "es": 'Estos indexers ya no tienen definición (el sitio cambió o cerró) y no funcionarán. Bórralos en Prowlarr y añade una alternativa que funcione.',
    },
    "health_OutdatedDefinitionCheck": {
        "en": 'These indexers use an obsolete definition. Delete them and add them again in Prowlarr.',
        "es": 'Estos indexers usan una definición obsoleta. Bórralos y vuelve a añadirlos en Prowlarr.',
    },
    "health_IndexerVIPCheck": {
        "en": 'A VIP/premium membership on these indexers expires soon. Renew it or the indexer will stop working.',
        "es": 'La membresía VIP de estos indexers caduca pronto. Renuévala o el indexer dejará de funcionar.',
    },
    "health_IndexerVIPExpiredCheck": {
        "en": 'The VIP/premium membership on these indexers has expired. Renew it or disable them.',
        "es": 'La membresía VIP de estos indexers ha caducado. Renuévala o desactívalos.',
    },
    "health_IndexerProxyStatusCheck": {
        "en": 'An indexer proxy (e.g. FlareSolverr) is not working. Check it is running and reachable from Prowlarr.',
        "es": 'Un proxy de indexers (p. ej. FlareSolverr) no funciona. Comprueba que está en marcha y que Prowlarr lo alcanza.',
    },
    "health_ApplicationStatusCheck": {
        "en": 'Prowlarr cannot sync with some apps (Sonarr/Radarr). Check their URL and API key in Prowlarr → Settings → Apps.',
        "es": 'Prowlarr no puede sincronizar con algunas apps (Sonarr/Radarr). Revisa su URL y API key en Prowlarr → Settings → Apps.',
    },
    "health_ApplicationLongTermStatusCheck": {
        "en": 'Prowlarr has not been able to sync with some apps for more than 6 hours. Check their URL and API key in Prowlarr → Settings → Apps.',
        "es": 'Prowlarr lleva más de 6 horas sin poder sincronizar con algunas apps. Revisa su URL y API key en Prowlarr → Settings → Apps.',
    },
    "health_IndexerCheck": {
        "en": 'No indexer is enabled: Prowlarr has nothing to search.',
        "es": 'No hay ningún indexer activado: Prowlarr no tiene dónde buscar.',
    },
    "import_downgrade_needs_allow": {
        "en": "the library already has a better version (\"not an upgrade\"). Only if the user explicitly wants this lower version: allow_downgrade=true and allow_replace=true (the better file is deleted), and consider changing the quality profile so it is not upgraded back.",
        "es": "la biblioteca ya tiene una versión mejor («not an upgrade»). Solo si el usuario quiere expresamente esta versión inferior: allow_downgrade=true y allow_replace=true (el archivo mejor se borra), y plantéate cambiar el perfil de calidad para que no vuelva a mejorarla.",
    },
    "all_not_released": {
        "en": "Not released yet (the episode has not aired / the movie is not available): before release, matching results are fakes. Sonarr/Radarr will pick it up via RSS when it comes out. Use force=true only if really needed.",
        "es": "Aún no ha salido (el episodio no se ha emitido / la película no está disponible): antes del estreno, lo que aparece son falsos. Sonarr/Radarr lo cogerán por RSS cuando salga. Usa force=true solo si de verdad hace falta.",
    },
    "replacement_not_released": {
        "en": "Careful: this has not been released yet, so the replacement search will most likely find more fakes. Next time use skip_redownload=true and let RSS pick up the real release.",
        "es": "Ojo: aún no ha salido, así que la búsqueda de sustituto probablemente encontrará más falsos. La próxima vez usa skip_redownload=true y deja que el RSS coja el release real.",
    },
    "other_item_results": {
        "en": "Results for other episodes, seasons or series (not relevant here)",
        "es": "Resultados de otros episodios, temporadas o series (no vienen al caso)",
    },
    "indexer_disabled_was_failing": {
        "en": "Disabled; it had also been failing before that (see last_failure).",
        "es": "Desactivado; antes de eso también fallaba (ver last_failure).",
    },
    "rename_disabled": {
        "en": "Renaming is switched off in {svc} (Settings → Media Management → {setting}), so it would not rename anything. Turn it on first if you want files renamed.",
        "es": "El renombrado está desactivado en {svc} (Settings → Media Management → {setting}), así que no renombraría nada. Actívalo primero si quieres renombrar archivos.",
    },
    "use_explain_results": {
        "en": "It was just searched with explain_search, which found {n} approved release(s). Instead of searching again, grab one with grab_release (guid + indexer_id from those results), or use force=true.",
        "es": "Se acaba de buscar con explain_search, que encontró {n} release(s) aprobado(s). En lugar de buscar otra vez, descarga uno con grab_release (guid + indexer_id de esos resultados), o usa force=true.",
    },
    "needs_preview_token": {
        "en": "Not applied: this changes several items. Get the preview first (bulk_edit_preview / preview_rename), show it to the user and, if they agree, call again with its confirmation_token.",
        "es": "No se ha aplicado: afecta a varios elementos. Primero saca la vista previa (bulk_edit_preview / preview_rename), enséñasela al usuario y, si está de acuerdo, repite la llamada con su confirmation_token.",
    },
    "confirm_bulk_edit": {
        "en": "arr-doctor: apply {changes} to {n} items? ({items})",
        "es": "arr-doctor: ¿aplicar {changes} a {n} elementos? ({items})",
    },
    "confirm_rename": {
        "en": "arr-doctor: rename {n} files of {what}?",
        "es": "arr-doctor: ¿renombrar {n} archivos de {what}?",
    },
    "user_declined": {
        "en": "The user declined in the confirmation dialog. Nothing was changed; do not retry unless they ask.",
        "es": "El usuario lo rechazó en el diálogo de confirmación. No se ha cambiado nada; no lo reintentes salvo que te lo pida.",
    },
}
