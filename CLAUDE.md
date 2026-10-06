# arr-doctor

Servidor MCP (Model Context Protocol) para consultar y gestionar Sonarr, Radarr y Prowlarr desde Claude Desktop. Proyecto nuevo, escrito desde cero. Toma como referencia `BerryKuipers/mcp_services_radarr_sonarr` (PR #5), pero **no reutiliza su código**: ese repo no tiene LICENSE y su empaquetado está roto.

## Objetivo

Poder preguntar a Claude cosas como:

- "¿Por qué no se ha importado el S03E04 de The Capture?"
- "¿Qué hay atascado en la cola y por qué?"
- "Quita de la cola los `.exe`, mételos en la blocklist y busca otra versión."
- "¿Qué indexer me da más fallos este mes?"
- "Añade la serie X con el perfil HD-1080p."

## Entorno de pruebas reales

El entorno concreto del desarrollador (NAS, URLs, carpetas, cliente MCP) está en `CLAUDE.local.md`, que no se sube al repo. Las API keys **nunca** se escriben en el repo: van en `.env` (en `.gitignore`) o en el bloque `env` de la configuración del cliente MCP.

## Stack

- Python ≥ 3.11
- `fastmcp>=2.12,<2.13`, fijado. La 2.14 rompe por incompatibilidad con `mcp` y la 4.x cambia la API. Subir de versión solo con los tests en verde.
- `httpx` en modo asíncrono para HTTP. No usar `requests`.
- `pydantic` y `pydantic-settings` para la configuración y los modelos.
- Tests: `pytest`, `pytest-asyncio` y `respx` para mockear httpx.
- Empaquetado: **solo** `pyproject.toml`, sin `setup.py` ni `requirements.txt`. Punto de entrada: `arr-doctor = "arr_doctor.server:main"`.

## Estructura

```
arr-doctor/
├── CLAUDE.md               # este archivo (CLAUDE.local.md: entorno personal, ignorado por git)
├── README.md / README.es.md
├── CHANGELOG.md / CHANGELOG.es.md
├── LICENSE                 # MIT
├── pyproject.toml
├── .env.example
├── arr_doctor/
│   ├── server.py           # crea FastMCP, registra los módulos de tools, main()
│   ├── config.py           # Settings (pydantic-settings) desde el entorno
│   ├── i18n.py             # mensajes en inglés y español (ARR_LANG)
│   ├── guards.py           # presupuesto de indexers y búsquedas recientes
│   ├── paths.py            # comparar rutas POSIX / Windows / UNC
│   ├── formatting.py       # recortar y resumir respuestas de la API
│   ├── clients/            # base.py (errores, X-Api-Key, sin redirecciones), sonarr.py, radarr.py, prowlarr.py
│   └── tools/
│       ├── library.py      # catálogo: series, películas, episodios, faltantes, calendario
│       ├── diagnostics.py  # cola, historial, blocklist, salud, logs, huérfanos, sospechosos
│       ├── troubleshoot.py # explain_search, diagnose_import, check_paths, descargas paradas, parse_release
│       ├── maintenance.py  # bulk_edit_preview/apply, renombrado, informe de espacio, test de clientes de descarga
│       ├── actions.py      # búsquedas, monitorizar, quitar de la cola, añadir, importar
│       ├── importcheck.py  # verificación de importaciones manuales
│       ├── indexers.py     # Prowlarr
│       └── common.py       # servicios, resolución de títulos, per_service
├── scripts/                # smoke.py (lectura contra servidor real), gen_tools_doc.py
├── docs/                   # TOOLS, DESIGN, ROADMAP, GOOD_PRACTICES (en/es), assets/logo.svg
└── tests/                  # pytest + respx; fixtures/ con datos de ejemplo
```

## Configuración (variables de entorno)

| Variable | Obligatoria | Ejemplo / por defecto |
|---|---|---|
| `SONARR_URL` | sí* | `http://192.168.1.10:8989` |
| `SONARR_API_KEY` | sí* | — |
| `RADARR_URL` | sí* | `http://192.168.1.10:7878` |
| `RADARR_API_KEY` | sí* | — |
| `PROWLARR_URL` | no | `http://192.168.1.10:9696` |
| `PROWLARR_API_KEY` | no | — |
| `ARR_LANG` | no (por defecto `en`) | `es` para mensajes en español |
| `ARR_READONLY` | no (por defecto `false`) | `true` desactiva todas las tools de escritura |
| `ARR_TIMEOUT` | no (por defecto `15`) | segundos |
| `ARR_DOWNLOADS_PATH` | no (por defecto, autodetectada) | carpeta de descargas tal como la ve Sonarr/Radarr |
| `ARR_INDEXER_BUDGET_PER_HOUR` | no (por defecto `30`) | `0` = sin límite |
| `ARR_SEARCH_CONFIRM_ABOVE` | no (por defecto `10`) | |
| `ARR_SEARCH_COOLDOWN_MINUTES` | no (por defecto `60`) | `0` = desactivado |

\* Hace falta al menos un servicio configurado. Si uno no está configurado, sus tools **no se registran**, en lugar de fallar en tiempo de ejecución.

Se usan URLs completas, no IP + puerto por separado, para soportar un proxy inverso o HTTPS en el futuro.

## Principios de diseño

1. **stdio limpio.** El transporte es stdio, así que **nunca** se escribe en stdout salvo el propio protocolo. Todo el logging va a stderr.
2. **Respuestas compactas.** No se devuelve el JSON crudo de la API. Se recortan las sinopsis (≤ 200 caracteres o se omiten), las imágenes y los campos internos. Las listas van con `limit` (por defecto 50) y un indicador `truncated`. El objetivo es no reventar el contexto de Claude.
3. **Errores legibles.** Se capturan `httpx` y los HTTP 4xx/5xx y se devuelve un mensaje claro, por ejemplo "Sonarr devolvió 401: API key incorrecta", nunca un traceback.
4. **Anotaciones MCP.** Las tools de lectura llevan `annotations={"readOnlyHint": True}`. Las de escritura, `{"destructiveHint": True}` cuando borran o bloquean algo.
5. **Modo solo lectura.** Si `ARR_READONLY=true`, las tools de escritura no se registran.
6. **Descripciones de las tools en inglés**, concisas y con 1-2 ejemplos de pregunta. Es lo que lee el modelo para decidir qué tool usar.
7. **Identificadores flexibles.** Las tools que reciben una serie o película aceptan el ID o el título. Si el título es ambiguo, devuelven los candidatos en vez de elegir uno.
8. **Buenas prácticas de Sonarr/Radarr, aplicadas en el código** (`docs/GOOD_PRACTICES.es.md`): toda operación que consulte los indexers pasa por el presupuesto horario (`svc.budget`); las búsquedas o acciones masivas devuelven primero un recuento o vista previa y solo actúan con `confirm`/`apply`; nada sustituye o borra archivos sin un permiso explícito. Cualquier tool nueva tiene que cumplirlo.
9. Tipado completo, `async` en todo y una función por tool. La lógica HTTP va en `clients/`, nunca en `tools/`.

## Tools por fases

### Fase 0: esqueleto

- `pyproject.toml`, `config.py`, `clients/base.py` y `server.py` con `main()`.
- La tool `get_system_status` devuelve la versión y el estado de cada servicio configurado (`/api/v3/system/status`).
- **Hecho cuando:** arranca por stdio, aparece en MCP Inspector y `get_system_status` responde contra un servidor real.

### Fase 1: catálogo y diagnóstico (solo lectura)

Las rutas de Sonarr y Radarr usan `/api/v3`.

| Tool | Servicio | Endpoint | Notas |
|---|---|---|---|
| `search_library` | S/R | `/series`, `/movie` | Búsqueda local por título, resultado compacto |
| `get_series` | S | `/series/{id}` | Incluye estadísticas por temporada |
| `get_episodes` | S | `/episode?seriesId=&seasonNumber=` | `hasFile`, `monitored`, fecha de emisión |
| `get_movie` | R | `/movie/{id}` | |
| `get_missing` | S/R | `/wanted/missing` | Paginado |
| `get_cutoff_unmet` | S/R | `/wanted/cutoff` | |
| `get_calendar` | S/R | `/calendar?start=&end=` | |
| `get_queue` | S/R | `/queue?includeSeries=true` / `includeMovie=true` | `trackedDownloadState`, `trackedDownloadStatus`, `statusMessages[].messages`, `indexer`, `downloadClient` |
| `get_history` | S/R | `/history` | Filtros: serie o película, `eventType`, días hacia atrás. Incluye `data.indexer` |
| `get_blocklist` | S/R | `/blocklist` | Indexer y motivo |
| `get_health` | S/R | `/health` | Avisos de salud |
| `get_logs` | S/R | `/log?level=error` | Últimos N errores |
| `get_disk_space` | S/R | `/diskspace` | |
| `find_orphan_downloads` | S/R | `/manualimport?folder=…&filterExistingFiles=true` (carpeta autodetectada o `ARR_DOWNLOADS_PATH`) | Archivos importables que nadie rastrea. Agrupa por serie o película e indica si el episodio ya tiene archivo (duplicado) o falta |
| `find_suspicious_releases` | S/R | `/queue` + `/history` | Detecta extensiones `.exe .scr .lnk .bat .cmd .msi .zipx` y devuelve el indexer de origen |

**Hecho cuando:** con un servidor real, Claude explica por qué un episodio no se ha importado combinando `get_episodes`, `get_queue` y `find_orphan_downloads`.

### Fase 2: acciones (escritura)

| Tool | Endpoint | Notas |
|---|---|---|
| `search_episodes` | `POST /command` `{"name":"EpisodeSearch","episodeIds":[…]}` | |
| `search_season` | `POST /command` `{"name":"SeasonSearch","seriesId":…,"seasonNumber":…}` | |
| `search_missing` | `POST /command` `{"name":"MissingEpisodeSearch"}` / Radarr `MissingMoviesSearch` | |
| `search_movie` | `POST /command` `{"name":"MoviesSearch","movieIds":[…]}` | |
| `set_monitored` | `PUT /episode/monitor` `{"episodeIds":[…],"monitored":bool}` · temporada o serie vía `PUT /series/{id}` | |
| `remove_from_queue` | `DELETE /queue/{id}?removeFromClient=&blocklist=&skipRedownload=` | Destructiva. Acepta varios IDs |
| `refresh_item` | `POST /command` `RefreshSeries` / `RefreshMovie` | |
| `add_series` | `/series/lookup?term=` → `POST /series` | Requiere `qualityProfileId` (`/qualityprofile`) y `rootFolderPath` (`/rootfolder`). Si no se indican, devuelve las opciones en lugar de adivinar |
| `add_movie` | `/movie/lookup?term=` → `POST /movie` | Ídem |
| `manual_import` | `GET /manualimport?folder=` → `POST /command` `{"name":"ManualImport","importMode":"auto","files":[…]}` | Destructiva. Recibe una lista explícita de archivos. Modo `auto` por defecto (como la interfaz web: no rompe el seeding); sustituir archivos existentes requiere `allow_replace`. **Nunca** importa todo lo de la carpeta a ciegas: si hay varios archivos para el mismo episodio, devuelve el conflicto y no importa |

Las búsquedas son comandos asíncronos en Sonarr/Radarr: se devuelve el ID del comando y su estado inicial. Se puede añadir `get_command_status` (`GET /command/{id}`).

**Hecho cuando:** "quita los `.exe` de la cola con blocklist y busca otra versión" funciona de principio a fin.

### Fase 3: Prowlarr (`/api/v1`)

| Tool | Endpoint |
|---|---|
| `list_indexers` | `GET /indexer` (nombre, activo, prioridad, protocolo) |
| `get_indexer_stats` | `GET /indexerstats?startDate=&endDate=` (consultas, capturas, fallos por indexer) |
| `set_indexer_enabled` | `GET /indexer/{id}` → `PUT /indexer/{id}` con `enable` |
| `test_indexers` | `POST /indexer/testall` |

### Fase 4: opcional

- Download Station (API Web de Synology, `SYNO.DownloadStation2.Task`): tareas activas y tareas borradas antes de que se importaran.
- Estado de "visto" desde Plex, solo si se configura `PLEX_URL` y `PLEX_TOKEN`.

## Casos reales que motivaron el diseño

- **Releases falsos con `.exe`** desde indexers públicos. `find_suspicious_releases` los detecta y devuelve el indexer de origen.
- **Descargas huérfanas.** El cliente de descargas quita la tarea antes de que Sonarr la importe y el archivo se queda sin rastrear. Lo resuelve `find_orphan_downloads`.
- **Duplicados en la carpeta de descargas** (pack de temporada y episodios sueltos). `manual_import` nunca importa dos archivos para el mismo `episodeId`.
- **Puertos asignados automáticamente** (Docker, Synology Container Manager). Un error de conexión sugiere que el puerto puede haber cambiado.

## Tests

- Unitarios con `respx` y fixtures JSON en `tests/fixtures/` (datos de ejemplo con la forma de los esquemas OpenAPI; se pueden sustituir por respuestas reales anonimizadas). Cada tool tiene al menos un test con la respuesta correcta y otro con el error (401, timeout).
- `scripts/smoke.py`: llama a todas las tools de **solo lectura** contra el servidor real usando `.env`. Nunca ejecuta tools de escritura.
- `tests/test_e2e_stdio.py`: arranca el proceso real por stdio contra un Sonarr falso local (Linux y Windows en el CI).
- Inspección manual: `npx @modelcontextprotocol/inspector .venv/Scripts/python.exe -m arr_doctor.server`.

## Instalación en Claude Desktop

Ver la sección de instalación de `README.md` / `README.es.md`.

## Forma de trabajar (para Claude Code)

- Ir **fase a fase**. No empezar la siguiente sin cumplir el "Hecho cuando" de la actual y sin `pytest` en verde.
- Contra un servidor real, ejecutar **solo** tools de lectura. Las de escritura se prueban con mocks. Para probarlas en real, pedir confirmación antes indicando qué se va a modificar.
- Antes de implementar un endpoint, comprobar los campos reales con una petición de lectura o con la documentación OpenAPI de Sonarr/Radarr, y no asumir nombres de campos.
- No hacer commit de `.env`, de API keys ni de rutas personales en las fixtures.
- Commits pequeños, uno por tool o grupo de tools, con mensaje en inglés.

## Idiomas

- Las descripciones de las tools, en inglés (las lee el modelo).
- Todo texto que una tool devuelva al usuario (errores, notas, pistas) pasa por `arr_doctor.i18n.t()` y tiene que existir en inglés y en español. `ARR_LANG` elige el idioma (por defecto `en`).
- La documentación se mantiene en los dos idiomas: `README.md` / `README.es.md`, `docs/DESIGN*.md`, `docs/ROADMAP*.md`, `CHANGELOG*.md`. `docs/TOOLS*.md` se generan con `python scripts/gen_tools_doc.py`.

## Estado actual

Actualizado el 2026-10-06. Versión publicada: **0.2.0**.

- Fases 0–3 implementadas, más las prioridades alta y media del roadmap (resolución de problemas y mantenimiento). 42 tools, 245 tests en verde (mocks con `respx` y uno de extremo a extremo por stdio). CI en Windows y Linux con ruff y mypy.
- Validado contra Sonarr v4 y Radarr 6.2 reales: todas las tools de lectura (salvo `explain_search` y `test_download_clients`) y, con permiso, `refresh_item`, `remove_from_queue` con blocklist y `manual_import`. Detalles en `CLAUDE.local.md`.
- Todas las tools, también las de escritura, probadas contra contenedores Docker desechables de Sonarr 4.0.20, Radarr 5.28 y 6.4.4, y Prowlarr 2.6.5 (bibliotecas vacías).
- Las pruebas reales destaparon y corrigieron: elementos desconocidos de la cola, detección de descargas paradas, importaciones dadas por buenas que habían fallado y la espera frente a los timeouts de los clientes MCP.
- Prowlarr real validado en lectura (detalles en `CLAUDE.local.md`).
- Siguiente: pruebas en Claude Desktop (`docs/testing/claude-desktop.es.md`) y decidir la publicación (nombre, autor del LICENSE, historial limpio). Después, la prioridad baja de `docs/ROADMAP.es.md`. La distribución sin dependencias (`.mcpb`, ejecutable, PyPI, Docker en NAS) está anotada como idea, sin decidir.
- Repositorio: https://github.com/alexliam83/arr-doctor (público desde la v0.2.0, 2026-10-06, con historial limpio; el historial de desarrollo está en el repo privado `arr-doctor-history`). Nombre definitivo `arr-doctor` (antes `arr-mcp`, ocupado en PyPI y GitHub). La carpeta local de desarrollo sigue llamándose `arr-mcp`.
