# Buenas prácticas y protecciones

[English](GOOD_PRACTICES.md) · **Español**

Un servidor MCP deja que un modelo de lenguaje maneje Sonarr, Radarr y Prowlarr. Un modelo puede entender mal una petición, llamar a una tool en bucle o actuar ante una instrucción vaga. Por eso este servidor sigue las prácticas que recomienda la wiki de Servarr (la documentación oficial de Sonarr, Radarr y Prowlarr) y las aplica en el código, no solo en la descripción de las tools.

## Qué dice la documentación oficial

| Práctica | Fuente |
|---|---|
| Sonarr/Radarr **no buscan de forma periódica**: leen el RSS de los indexers y descargan lo que coincide. Las búsquedas activas son para casos concretos (añadir algo, una búsqueda manual, Wanted). | [Sonarr FAQ — How does Sonarr find episodes](https://wiki.servarr.com/sonarr/faq#how-does-sonarr-find-episodes) |
| Antes de un «Search All», la interfaz web dice cuántos episodios va a buscar, algo «especialmente útil si tus indexers limitan las llamadas a la API». | [Sonarr — Wanted](https://wiki.servarr.com/sonarr/wanted) |
| Los indexers limitan las consultas y descargas por día u hora («Query Limit» y «Grab Limit» en Prowlarr). | [Prowlarr — Indexers](https://wiki.servarr.com/prowlarr/indexers) |
| Los indexers limitan la frecuencia de peticiones y algunos banean la IP. | [Sonarr troubleshooting — Hitting rate limits / IP Ban](https://wiki.servarr.com/sonarr/troubleshooting) |
| Intervalo de sincronización RSS: mínimo 10 minutos. | [Sonarr settings — Indexers](https://wiki.servarr.com/sonarr/settings) |
| Los torrents que siguen compartiéndose (seeding) se copian o se enlazan (hardlink), no se mueven. El modo de importación «Auto» de Sonarr lo hace solo. | [Sonarr settings — Use Hard links instead of Copy](https://wiki.servarr.com/sonarr/settings), [TRaSH Guides — Hardlinks](https://trash-guides.info/hardlinks), código de Sonarr (`ImportMode.Auto`) |
| Los archivos borrados o sustituidos solo van a la papelera si hay una configurada. | [Sonarr settings — Recycling Bin](https://wiki.servarr.com/sonarr/settings) |
| La API key es secreta y no se debe compartir. | [Prowlarr settings — Security](https://wiki.servarr.com/prowlarr/settings) |

## Cómo lo aplica el servidor

### Indexers: buscar es la excepción

- **Presupuesto horario de indexers.** Cada operación que consulta los indexers cuenta en una ventana deslizante de una hora: búsquedas automáticas, búsquedas interactivas (`explain_search`), descargas forzadas (`grab_release`), pruebas de indexers y añadir algo con «buscar ahora». Al agotarse, la tool se niega con un mensaje claro, así que un modelo atascado en un bucle no puede machacar tus indexers. Por defecto, 30 por hora (`ARR_INDEXER_BUDGET_PER_HOUR`; `0` = sin límite).
- **No se busca nada antes del estreno.** Los episodios no emitidos y las películas que Radarr no considera disponibles se saltan (`force=true` lo fuerza): antes del estreno, lo que coincide son falsos (un episodio real que se estrenaba al día siguiente solo tenía releases `.exe`). El RSS coge el real cuando sale.
- **Sin búsquedas repetidas.** `search_episodes` y `search_movie` se saltan lo que Sonarr/Radarr buscaron hace menos de 60 minutos (`lastSearchTime`): volver a buscar tan pronto casi nunca encuentra nada nuevo. `force=true` lo fuerza (`ARR_SEARCH_COOLDOWN_MINUTES`; `0` = desactivado).
- **Búsquedas masivas en dos pasos.** Por encima de 10 elementos (`ARR_SEARCH_CONFIRM_ABOVE`), `search_episodes`, `search_movie` y `search_missing` primero dicen cuántos elementos buscarían, y solo buscan con `confirm=true`, igual que el aviso del «Search All» de la interfaz web. `search_missing` dice que no falta nada en lugar de buscar.
- **Blocklist más búsqueda de sustituto** en `remove_from_queue` cuenta una búsqueda por elemento, y se comprueba **antes** de quitar nada.

### Archivos: nunca perder datos sin avisar

- **`manual_import` usa el modo `auto` por defecto**, igual que la interfaz web: copia o hace hardlink si el cliente de descargas sigue compartiendo el archivo, y mueve si no. `move` (que rompe el seeding) hay que pedirlo expresamente.
- **Bajar de calidad** (un archivo que Sonarr/Radarr rechazan como «not an upgrade») solo se importa con `allow_downgrade=true` más `allow_replace=true`; cualquier otro rechazo sigue bloqueando.
- **Sustituir archivos** que ya están en la biblioteca requiere `allow_replace=true`. Si no hay papelera de reciclaje configurada, la respuesta avisa de que los antiguos se borran para siempre.
- **Todo o nada:** `manual_import` no importa nada si algún archivo se rechaza, no se identifica o compite con otro por el mismo episodio o película. Un emparejado manual lo revalidan Sonarr/Radarr; nunca sirve para saltarse sus comprobaciones.
- **Verificar, no fiarse:** Sonarr/Radarr dan por buena una importación manual aunque fallen todos los archivos. `manual_import` espera al comando y comprueba que cada episodio o película tiene de verdad un archivo nuevo, y devuelve el motivo del log para los que no.
- **Primero la vista previa, en una tool aparte:** `bulk_edit_preview` y `preview_rename` son de solo lectura; los cambios los hacen `bulk_edit_apply` y `rename_files`, así que en el diálogo de permiso del cliente se ve claramente cuál cambia cosas. Para varios elementos, una selección por filtro o varios archivos, aplicar exige además el `confirmation_token` de la vista previa, así que el modelo no puede saltarse el cálculo de la vista previa. Aun así, un modelo podía hacer la vista previa y aplicar en el mismo turno sin preguntar, así que, si el cliente MCP soporta *elicitation*, el servidor pregunta además directamente al usuario («¿aplicar X a N elementos?»): el modelo no puede contestar por él. Sin *elicitation*, la protección es el diálogo de permiso del cliente: nunca elijas «Permitir siempre» para las tools de escritura.
- **Quitar muchos elementos de la cola** (más de `ARR_SEARCH_CONFIRM_ABOVE`) requiere `confirm=true`. La descripción de la tool avisa de que quitar un torrent del cliente detiene el seeding (cuenta como hit-and-run en trackers privados).
- **Ninguna tool borra series, películas ni archivos** de la biblioteca. Es intencionado.
- `bulk_edit_apply` **no** cambia carpetas raíz, porque eso mueve archivos.

### Configuración y secretos

- **Modo solo lectura** (`ARR_READONLY=true`): no se registra ninguna tool de escritura. Es una buena forma de empezar.
- Las redirecciones nunca se siguen, así que la API key solo se envía a la URL configurada.
- Las API keys solo se leen del entorno o de `.env`. Nunca aparecen en respuestas, errores ni logs, y la configuración de clientes de descarga e indexers que devuelven las tools omite las credenciales.
- Las tools de escritura llevan las anotaciones MCP `readOnlyHint: false`, más `destructiveHint: true` cuando borran. Las que contactan con servicios externos llevan `openWorldHint: true`, para que los clientes puedan pedir confirmación.

### Instrucciones para el modelo

Las instrucciones MCP del servidor le dicen al modelo que confíe en el RSS, que busque solo ante peticiones concretas, que no consulte `get_command_status` en bucle y que enseñe al usuario las vistas previas y los recuentos antes de confirmar. Las protecciones de arriba se aplican aunque el modelo las ignore.

## Ajustes

| Variable | Por defecto | Efecto |
|---|---|---|
| `ARR_INDEXER_BUDGET_PER_HOUR` | `30` | Máximo de búsquedas, descargas y pruebas de indexers por hora. `0` = sin límite |
| `ARR_SEARCH_CONFIRM_ABOVE` | `10` | Búsquedas o retiradas de la cola de más elementos que esto requieren `confirm=true` |
| `ARR_SEARCH_COOLDOWN_MINUTES` | `60` | Saltarse lo buscado hace menos de estos minutos. `0` = desactivado |
| `ARR_READONLY` | `false` | `true` = ninguna tool de escritura |
