<p align="center">
  <img src="docs/assets/logo.svg" width="112" height="112" alt="arr-doctor logo">
</p>

<h1 align="center">arr-doctor</h1>

<p align="center">Diagnostica y arregla Sonarr · Radarr · Prowlarr desde Claude</p>

<p align="center"><a href="README.md">English</a> · <strong>Español</strong></p>

Servidor [MCP](https://modelcontextprotocol.io) para consultar, diagnosticar y gestionar **Sonarr**, **Radarr** y **Prowlarr** desde Claude Desktop o cualquier otro cliente MCP.

Está pensado sobre todo para las preguntas que más se repiten en los issues y en la wiki de Sonarr y Radarr:

- «¿Por qué no ha descargado el S03E04? ¿Qué releases hay y por qué se rechazaron?»
- «¿Por qué no se importa esta descarga?»
- «¿Qué descargas están atascadas? Quítalas y busca otra versión.»
- «¿Este release sería una mejora del archivo que ya tengo? ¿Por qué dice “not an upgrade”?»
- «Quita de la cola los `.exe`, mételos en la blocklist y busca otra versión.»
- «¿Qué indexer me da más fallos este mes?»
- «Añade la serie Severance con el perfil HD-1080p.»

> Estado: **v0.2.0**. 43 tools, 269 tests. Validado contra Sonarr, Radarr y Prowlarr reales en un NAS Synology, y todas las tools (también las de escritura) contra contenedores desechables de Sonarr, Radarr y Prowlarr. Ver [Estado](#estado).

## Características

- **42 tools** en siete grupos: estado, catálogo, diagnóstico, resolución de problemas, mantenimiento, acciones y Prowlarr. Referencia completa en [docs/TOOLS.es.md](docs/TOOLS.es.md).
- **Resolución de problemas guiada:**
  - `explain_search` lanza una búsqueda interactiva y agrupa los releases por motivo de rechazo (idioma, tamaño, calidad, puntuación de custom formats…).
  - `diagnose_import` y `check_paths` dan la causa probable de una importación fallida y cómo arreglarla: remote path mapping, permisos, emparejado manual, «not an upgrade»…
  - `find_stalled_downloads` detecta descargas atascadas.
  - `parse_release` muestra cómo se puntúa un release y estima si sería una mejora.
  - `get_health` añade a cada aviso de salud conocido su solución habitual; `test_download_clients` prueba los clientes de descarga.
- **Mantenimiento:** `bulk_edit_preview` / `bulk_edit_apply` cambian muchas series o películas a la vez (monitorización, perfil de calidad, etiquetas…), siempre con vista previa antes; `preview_rename` / `rename_files` renombran con vista previa; `library_report` muestra qué ocupa espacio y qué se podría limpiar.
- **Sigue las buenas prácticas de Sonarr/Radarr, aplicadas en el código:** presupuesto horario de indexers, sin búsquedas repetidas, búsquedas y retiradas masivas en dos pasos, importaciones que nunca rompen el seeding ni sustituyen archivos sin permiso, y vista previa antes de los cambios masivos. Ver [docs/GOOD_PRACTICES.es.md](docs/GOOD_PRACTICES.es.md).
- **Respuestas compactas.** Nunca devuelve el JSON crudo de la API: recorta sinopsis, quita imágenes y campos internos, y pagina con `limit` y `truncated`.
- **Errores legibles en inglés o español** (`ARR_LANG`). Por ejemplo, «Sonarr devolvió 401: API key incorrecta (revisa SONARR_API_KEY)» en lugar de un traceback.
- **Títulos o IDs.** Las tools aceptan `"The Capture"`, `"Dune 2021"` o `42`. Si el título es ambiguo, devuelven los candidatos en vez de elegir uno.
- **Tolerante a fallos parciales.** Si Radarr está caído, `get_queue` sigue mostrando la cola de Sonarr y marca el error de Radarr.
- **Modo solo lectura** (`ARR_READONLY=true`): las tools de escritura ni siquiera se registran.
- **Importaciones seguras.** `manual_import` solo importa archivos indicados uno a uno, nunca importa dos archivos para el mismo episodio y, si algo falla, no importa nada. Admite emparejado manual de archivos no identificados, y Sonarr/Radarr lo revalidan antes de importar.
- **Releases falsos** (`.exe .scr .lnk .bat .cmd .msi .zipx`) y **descargas huérfanas** (archivos que se han quedado en la carpeta de descargas sin que nadie los rastree).

## Requisitos

- Windows o Linux (probado en CI en ambos, Python 3.11–3.13; en macOS debería funcionar, pero no se prueba).
- Python ≥ 3.11
- Sonarr v4 y/o Radarr v5–v6 (API `/api/v3`). Probado con Sonarr 4.0.16 y 4.0.20, y Radarr 5.28, 6.2 y 6.4.4. Prowlarr (API `/api/v1`, probado con la 2.4.0 y la 2.6.5) es opcional.
- La API key de cada servicio (en cada aplicación: *Settings → General → Security → API Key*).

## Instalación

### La más rápida: con uv (sin Git ni instalar Python a mano)

[uv](https://docs.astral.sh/uv/) descarga Python por su cuenta y ejecuta arr-doctor directamente desde la [última release](https://github.com/alexliam83/arr-doctor/releases/latest).

1. Instala uv una vez:
   - Windows (PowerShell): `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`
   - Linux / macOS: `curl -LsSf https://astral.sh/uv/install.sh | sh`
2. En Claude Desktop (**Configuración → Desarrollador → Editar configuración**), añade dentro de `mcpServers`:

   ```json
   "arr": {
     "command": "uvx",
     "args": ["--from", "https://github.com/alexliam83/arr-doctor/releases/download/v0.2.0/arr_doctor-0.2.0-py3-none-any.whl", "arr-doctor"],
     "env": {
       "SONARR_URL": "http://192.168.1.10:8989",
       "SONARR_API_KEY": "tu-api-key-de-sonarr",
       "RADARR_URL": "http://192.168.1.10:7878",
       "RADARR_API_KEY": "tu-api-key-de-radarr",
       "ARR_LANG": "es"
     }
   }
   ```

   Si Claude Desktop no encuentra `uvx`, pon su ruta completa en `command`, p. ej. `"command": "C:\\Users\\<tú>\\.local\\bin\\uvx.exe"` en Windows o `"~/.local/bin/uvx"` en el resto.
3. Reinicia Claude Desktop del todo.

Sin uv: `pip install https://github.com/alexliam83/arr-doctor/releases/download/v0.2.0/arr_doctor-0.2.0-py3-none-any.whl` instala el comando `arr-doctor`.

### Desde el código fuente (Windows, Claude Desktop)

```powershell
cd C:\
git clone https://github.com/alexliam83/arr-doctor.git
cd arr-doctor
python -m venv .venv
.\.venv\Scripts\pip install -e .
```

En Claude Desktop, abre **Configuración → Desarrollador → Editar configuración** y añade esto dentro de `mcpServers`, sin tocar el resto del archivo:

```json
"arr": {
  "command": "C:\\arr-doctor\\.venv\\Scripts\\arr-doctor.exe",
  "env": {
    "SONARR_URL": "http://192.168.1.10:8989",
    "SONARR_API_KEY": "tu-api-key-de-sonarr",
    "RADARR_URL": "http://192.168.1.10:7878",
    "RADARR_API_KEY": "tu-api-key-de-radarr",
    "ARR_LANG": "es"
  }
}
```

Si el archivo estaba vacío, queda así:

```json
{
  "mcpServers": {
    "arr": { "command": "…", "env": { "…": "…" } }
  }
}
```

Reinicia Claude Desktop **del todo**, cerrándolo también desde el icono de la bandeja del sistema. En una conversación nueva, el icono de herramientas debe mostrar `arr`.

> **Claude Desktop de Microsoft Store.** Esta versión guarda la configuración en una ruta virtualizada, normalmente `%LOCALAPPDATA%\Packages\Claude_…\LocalCache\Roaming\Claude\claude_desktop_config.json`. Ábrela siempre con «Editar configuración» para asegurarte de editar el archivo correcto. Los logs del servidor están en la carpeta `logs` de ese mismo directorio (`mcp-server-arr.log`).

### Linux / macOS

```bash
git clone https://github.com/alexliam83/arr-doctor.git && cd arr-doctor
python3 -m venv .venv
.venv/bin/pip install -e .
cp .env.example .env   # y rellena las claves
```

En la configuración de tu cliente MCP, usa `/ruta/a/arr-doctor/.venv/bin/arr-doctor` como `command`.

## Configuración

Las variables se leen del entorno (el bloque `env` del cliente MCP) o de un archivo `.env` en la carpeta del repositorio. Hay una plantilla en [.env.example](.env.example).

| Variable | Obligatoria | Por defecto | Descripción |
|---|---|---|---|
| `SONARR_URL` | sí\* | — | URL completa, p. ej. `http://192.168.1.10:8989` |
| `SONARR_API_KEY` | sí\* | — | |
| `RADARR_URL` | sí\* | — | p. ej. `http://192.168.1.10:7878` |
| `RADARR_API_KEY` | sí\* | — | |
| `PROWLARR_URL` | no | — | p. ej. `http://192.168.1.10:9696` |
| `PROWLARR_API_KEY` | no | — | |
| `ARR_LANG` | no | `en` | Idioma de los errores y las notas: `en` o `es` |
| `ARR_READONLY` | no | `false` | `true` desactiva todas las tools de escritura |
| `ARR_INDEXER_BUDGET_PER_HOUR` | no | `30` | Máximo de búsquedas, descargas y pruebas de indexers por hora (`0` = sin límite) |
| `ARR_SEARCH_CONFIRM_ABOVE` | no | `10` | Búsquedas o retiradas de la cola de más elementos que esto piden confirmación |
| `ARR_SEARCH_COOLDOWN_MINUTES` | no | `60` | Saltarse lo buscado hace menos de estos minutos (`0` = desactivado) |
| `ARR_TIMEOUT` | no | `15` | Timeout HTTP en segundos. Los escaneos y las búsquedas interactivas usan valores más altos |
| `ARR_DOWNLOADS_PATH` | no | auto | Carpeta de descargas **tal como la ve Sonarr/Radarr**, que se usa en `find_orphan_downloads`. Si no se define, se deduce de la cola y del historial de importaciones |

\* Hace falta al menos Sonarr o Radarr. Si un servicio no tiene URL **y** API key, no se registra y sus tools no aparecen. Se usan URLs completas para poder usar un proxy inverso o HTTPS.

> **Docker / NAS.** Si el puerto se asigna automáticamente (por ejemplo, en Synology Container Manager en modo auto), puede cambiar al recrear el contenedor. Si `get_system_status` dice que no puede conectar, revisa el puerto o, mejor aún, fíjalo.

**Las API keys nunca van al repositorio.** `.env` está en `.gitignore`.

## Uso

Conversaciones típicas y las tools que Claude suele usar:

| Pregunta | Tools |
|---|---|
| «¿Por qué no ha descargado el S03E04?» | `explain_search` → `grab_release` si quieres uno rechazado |
| «¿Por qué no se importa?» | `diagnose_import` → `check_paths` → `manual_import(matches=…)` |
| «¿Qué descargas están atascadas?» | `find_stalled_downloads` → `remove_from_queue(blocklist=true)` |
| «¿Este release sería una mejora?» | `parse_release` |
| «¿Qué hay atascado en la cola?» | `get_queue(only_problems=true)` |
| «Quita los `.exe` de la cola y busca otra versión» | `find_suspicious_releases` → `remove_from_queue(blocklist=true)` |
| «¿Qué indexer falla más este mes?» | `get_indexer_stats(days=30)` |
| «¿Qué ocupa más espacio?» | `library_report` |
| «Deja de monitorizar las series terminadas y completas» | `bulk_edit_preview` → `bulk_edit_apply` |
| «¿Qué archivos no siguen mi formato de nombres?» | `preview_rename` → `rename_files` |
| «Añade Severance en HD-1080p» | `add_series` (si faltan el perfil o la carpeta raíz, devuelve las opciones) |
| «Importa lo que se quedó en descargas» | `find_orphan_downloads` → `manual_import(files=[…])` |

Las búsquedas, los refrescos y las importaciones son **comandos asíncronos** de Sonarr/Radarr. La tool devuelve un `command_id`, que se consulta con `get_command_status`.

`explain_search` consulta **en directo** todos los indexers (es la misma búsqueda interactiva de la interfaz web). Úsala para un episodio o una película concretos, no en bucle.

### Tools que modifican o borran

- `remove_from_queue`: borra elementos de la cola. Por defecto también borra la tarea en el cliente de descarga (`remove_from_client=true`). Con `blocklist=true` añade el release a la blocklist y, salvo que se pase `skip_redownload=true`, Sonarr/Radarr buscan otro release automáticamente.
- `manual_import`: importa archivos concretos a la biblioteca. Por defecto (`import_mode="auto"`) copia o hace hardlink mientras la descarga se comparte, y mueve si no. Sustituir un archivo que ya está en la biblioteca requiere `allow_replace=true`.
- `grab_release`: manda un release concreto al cliente de descarga aunque se hubiera rechazado.
- `bulk_edit_apply`: cambia muchos elementos a la vez; para varios necesita el código de `bulk_edit_preview`.
- `rename_files`: renombra archivos en disco según la configuración de nombres.

Claude Desktop pide permiso la primera vez que usa cada tool. Para estas es mejor no elegir «Permitir siempre», así puedes revisar cada llamada. Las dos que borran llevan además la anotación MCP `destructiveHint`.

## Desarrollo

```bash
python -m venv .venv
.venv/bin/pip install -e ".[dev]"        # Windows: .venv\Scripts\pip
.venv/bin/pytest                          # tests unitarios con respx (sin red)
uvx ruff check arr_doctor tests scripts      # lint
python scripts/gen_tools_doc.py           # regenera docs/TOOLS.md y docs/TOOLS.es.md (un test comprueba que están al día)
```

**Contra un servidor real** (solo lectura, usa `.env`):

```bash
python scripts/smoke.py              # llama a todas las tools de solo lectura y resume el resultado
python scripts/smoke.py --verbose    # muestra también cada respuesta
python scripts/smoke.py --capture    # guarda respuestas crudas anonimizadas en scripts/captures/ (ignorada por git)
```

`smoke.py` se niega a llamar a cualquier tool que no esté anotada como `readOnlyHint`, y se salta `explain_search` porque consulta los indexers.

**En Claude Desktop:** hay una lista de pruebas manuales (¿elige bien las tools el modelo, respeta las confirmaciones, explica los resultados?) en [docs/testing/claude-desktop.es.md](docs/testing/claude-desktop.es.md).

**MCP Inspector:**

```bash
npx @modelcontextprotocol/inspector .venv/bin/python -m arr_doctor.server          # interfaz web
npx @modelcontextprotocol/inspector --cli .venv/bin/arr-doctor -e SONARR_URL=… -e SONARR_API_KEY=… --method tools/list
```

En Windows, cambia `.venv/bin/python` por `.venv/Scripts/python.exe`.

### Estructura

```
arr_doctor/
├── server.py         # FastMCP, registro condicional de tools, main()
├── config.py         # Settings (pydantic-settings)
├── i18n.py           # mensajes en inglés y español
├── paths.py          # comparar rutas POSIX / Windows / UNC de Sonarr/Radarr
├── formatting.py     # compactar las respuestas de la API
├── clients/          # HTTP: base.py (errores, X-Api-Key), sonarr.py, radarr.py, prowlarr.py
└── tools/            # library, diagnostics, troubleshoot, maintenance, actions, indexers, common
tests/                # pytest + respx; fixtures/ con respuestas de ejemplo
scripts/              # smoke.py, gen_tools_doc.py
docs/                 # TOOLS (generado), DESIGN, ROADMAP — en inglés y en español
```

- Buenas prácticas y protecciones: [docs/GOOD_PRACTICES.es.md](docs/GOOD_PRACTICES.es.md).
- Decisiones de diseño y detalles de la API: [docs/DESIGN.es.md](docs/DESIGN.es.md).
- Próximos pasos, a partir de los issues de Sonarr y Radarr: [docs/ROADMAP.es.md](docs/ROADMAP.es.md).
- Cambios: [CHANGELOG.es.md](CHANGELOG.es.md).

## Estado

Todas las tools tienen tests unitarios (HTTP simulado) y el servidor tiene un test de extremo a extremo por stdio. Además, se han ejecutado contra **Sonarr 4.0.16 y Radarr 6.2 reales en un NAS Synology** (biblioteca real: lectura más algunos cambios aprobados) y contra **contenedores Docker desechables** de Sonarr 4.0.20, Radarr 5.28 y 6.4.4, y Prowlarr 2.6.5 (bibliotecas vacías: todas las tools, también las de escritura):

| Bloque | NAS real | Contenedores | Notas |
|---|---|---|---|
| Esqueleto, `get_system_status` | ✅ | ✅ | stdio, MCP Inspector, errores legibles |
| Catálogo y diagnóstico (lectura) | ✅ | ✅ | Todas las tools, Sonarr y Radarr |
| Resolución de problemas (lectura) | ✅ | ✅ | En el NAS encontró un `.exe` falso real, descargas paradas y archivos huérfanos. `explain_search` solo en contenedores (allí no hay indexers) |
| Acciones de escritura | ✅ en parte | ✅ | NAS: `refresh_item`, `remove_from_queue` con blocklist, `manual_import` (6 episodios). Contenedores: `add_series`/`add_movie`, `set_monitored`, todas las búsquedas. `grab_release` solo con mocks (necesita indexers reales) |
| Mantenimiento | ✅ en parte | ✅ | NAS: `library_report`, `preview_rename`. Contenedores: `bulk_edit_preview` / `bulk_edit_apply`, `test_download_clients`. `rename_files` aplicado solo con mocks (necesita archivos en disco) |
| Prowlarr | ✅ | ✅ | NAS (Prowlarr 2.4.0, 11 indexers): todas las tools, incluidas `test_indexers` y `set_indexer_enabled` (8 indexers caídos desactivados; credenciales intactas) |
| Windows y Linux | ✅ | — | CI en ambos + un Windows real |
| Protecciones de buenas prácticas | ✅ | ✅ | |
| Prioridad baja del roadmap | — | — | Sin empezar |

Las pruebas contra el servidor real encontraron y corrigieron varios fallos que los mocks no podían mostrar (elementos desconocidos en la cola, casos de descargas paradas, importaciones dadas por buenas que habían fallado, importaciones largas frente a los timeouts del cliente). Las fixtures de `tests/fixtures/` siguen usando datos de ejemplo con la forma de los esquemas OpenAPI oficiales; se pueden sustituir por respuestas reales anonimizadas (`smoke.py --capture`).

## Créditos y licencia

Creado por **Alexliam** ([@alexliam](https://x.com/alexliam)).

La idea se inspira en [BerryKuipers/mcp_services_radarr_sonarr](https://github.com/BerryKuipers/mcp_services_radarr_sonarr). Es una implementación nueva que **no** reutiliza su código.

Licencia [MIT](LICENSE).
