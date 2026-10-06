# Referencia de tools

<!-- Generado por scripts/gen_tools_doc.py. No editar a mano. -->

English version: [TOOLS.md](TOOLS.md).

Las descripciones están en inglés porque son lo que lee el modelo para elegir la tool.
Las tools de escritura no se registran con `ARR_READONLY=true`, y las de un servicio sin
configurar tampoco.

## Estado

### `get_system_status`

_solo lectura_

Version and reachability of every configured service (Sonarr, Radarr, Prowlarr).

Use it first when something fails, to check connectivity and API keys.
Examples: "Are Sonarr and Radarr up?", "Which Radarr version am I running?"

## Catálogo (solo lectura)

### `search_library`

_solo lectura_

Search the local Sonarr/Radarr library (what is already added) by title.

Does not search the internet; use add_series/add_movie for that.
Examples: "Do I have The Capture?", "Which Star Wars movies are in my library?"

| Parámetro | Tipo | Por defecto | Descripción |
|---|---|---|---|
| `query` | string | `''` | Text to look for in titles; empty lists everything |
| `service` | `sonarr` \| `radarr` \| null | `null` | 'sonarr' or 'radarr'; omit to query both |
| `limit` | integer | `50` | Max items to return |

### `get_series`

_solo lectura · requiere Sonarr_

Details of one series in Sonarr, including per-season statistics
(episodes on disk vs aired, monitored seasons, size).

Examples: "How complete is The Capture?", "Which seasons of Severance are monitored?"

| Parámetro | Tipo | Por defecto | Descripción |
|---|---|---|---|
| `series` | string \| integer | obligatorio | Series ID or title (e.g. 'The Capture') |

### `get_episodes`

_solo lectura · requiere Sonarr_

Episodes of a series with has_file, monitored, air date and file quality.

Examples: "Is S03E04 of The Capture downloaded?", "Which episodes of season 2 are missing?"

| Parámetro | Tipo | Por defecto | Descripción |
|---|---|---|---|
| `series` | string \| integer | obligatorio | Series ID or title (e.g. 'The Capture') |
| `season` | integer \| null | `null` | Season number; omit for all seasons |
| `only_missing` | boolean | `False` | Only aired episodes without a file |
| `limit` | integer | `100` | Max items to return |

### `get_movie`

_solo lectura · requiere Radarr_

Details of one movie in Radarr: file, quality, availability, release dates.

Examples: "Do I have Dune in 4K?", "Why hasn't Oppenheimer downloaded? Is it available yet?"

| Parámetro | Tipo | Por defecto | Descripción |
|---|---|---|---|
| `movie` | string \| integer | obligatorio | Movie ID or title, optionally with year ('Dune 2021') |

### `get_missing`

_solo lectura_

Wanted/missing: monitored episodes (Sonarr) or movies (Radarr) without a file.

Examples: "What episodes am I missing?", "Which movies are still not downloaded?"

| Parámetro | Tipo | Por defecto | Descripción |
|---|---|---|---|
| `service` | `sonarr` \| `radarr` \| null | `null` | 'sonarr' or 'radarr'; omit to query both |
| `limit` | integer | `50` | Max items to return |
| `monitored_only` | boolean | `True` |  |

### `get_cutoff_unmet`

_solo lectura_

Items that have a file but below the quality profile cutoff (upgrade candidates).

Examples: "What could be upgraded to better quality?", "Which movies are below cutoff?"

| Parámetro | Tipo | Por defecto | Descripción |
|---|---|---|---|
| `service` | `sonarr` \| `radarr` \| null | `null` | 'sonarr' or 'radarr'; omit to query both |
| `limit` | integer | `50` | Max items to return |
| `monitored_only` | boolean | `True` |  |

### `get_calendar`

_solo lectura_

Upcoming (or recent) episode air dates and movie releases.

Examples: "What airs this week?", "What came out in the last 3 days?"

| Parámetro | Tipo | Por defecto | Descripción |
|---|---|---|---|
| `days_ahead` | integer | `7` |  |
| `days_back` | integer | `0` |  |
| `service` | `sonarr` \| `radarr` \| null | `null` | 'sonarr' or 'radarr'; omit to query both |
| `include_unmonitored` | boolean | `False` |  |
| `limit` | integer | `100` | Max items to return |

## Diagnóstico (solo lectura)

### `get_queue`

_solo lectura_

Download queue with tracked state (downloading, importBlocked, importPending, failed…),
status messages explaining why an import is stuck, indexer and download client.
Downloads that Sonarr/Radarr did not grab themselves are hidden (as in the web UI) and
only counted, unless include_unknown=true. Stalled downloads (no activity, no metadata,
no progress for 6 h) are marked with stall_reason and count as problems, even when
Sonarr/Radarr report them as healthy.

Examples: "What's stuck in the queue and why?", "Is S03E04 of The Capture still downloading?"

| Parámetro | Tipo | Por defecto | Descripción |
|---|---|---|---|
| `service` | `sonarr` \| `radarr` \| null | `null` | 'sonarr' or 'radarr'; omit to query both |
| `only_problems` | boolean | `False` | Only items with warnings/errors or blocked imports |
| `include_unknown` | boolean | `False` | Also list downloads in the client that Sonarr/Radarr did not grab |
| `limit` | integer | `50` | Max items to return |

### `get_history`

_solo lectura_

Activity history: grabs (with indexer), imports, failed downloads, deletions.

Examples: "Which indexer did S03E04 of The Capture come from?",
"What failed to download in the last 7 days?"

| Parámetro | Tipo | Por defecto | Descripción |
|---|---|---|---|
| `service` | `sonarr` \| `radarr` \| null | `null` | 'sonarr' or 'radarr'; omit to query both |
| `series` | string \| integer \| null | `null` | Sonarr series ID or title |
| `movie` | string \| integer \| null | `null` | Radarr movie ID or title |
| `event_type` | `grabbed` \| `imported` \| `failed` \| `deleted` \| `renamed` \| `ignored` \| null | `null` |  |
| `days` | integer \| null | `null` | Only the last N days |
| `limit` | integer | `50` | Max items to return |

### `get_blocklist`

_solo lectura_

Blocklisted releases with the indexer they came from and the reason.

Examples: "What's in the blocklist?", "Which indexer has the most blocklisted releases?"

| Parámetro | Tipo | Por defecto | Descripción |
|---|---|---|---|
| `service` | `sonarr` \| `radarr` \| null | `null` | 'sonarr' or 'radarr'; omit to query both |
| `limit` | integer | `50` | Max items to return |

### `get_health`

_solo lectura_

Health warnings and errors reported by Sonarr/Radarr (and Prowlarr if configured):
unreachable download client, missing root folder, indexers failing… each with the
usual fix when it is a known check.

Examples: "Any health warnings?", "Is something wrong with Radarr?"

| Parámetro | Tipo | Por defecto | Descripción |
|---|---|---|---|
| `service` | `sonarr` \| `radarr` \| null | `null` | 'sonarr' or 'radarr'; omit to query both |

### `get_logs`

_solo lectura_

Latest log entries at the given level (default: errors).

Examples: "Show me Sonarr's recent errors", "Why is Radarr failing? check the logs"

| Parámetro | Tipo | Por defecto | Descripción |
|---|---|---|---|
| `service` | `sonarr` \| `radarr` \| null | `null` | 'sonarr' or 'radarr'; omit to query both |
| `level` | `error` \| `warn` \| `info` | `'error'` |  |
| `limit` | integer | `20` |  |

### `get_disk_space`

_solo lectura_

Free and total space of the disks/volumes seen by Sonarr/Radarr.

Examples: "How much disk space is left on the NAS?"

| Parámetro | Tipo | Por defecto | Descripción |
|---|---|---|---|
| `service` | `sonarr` \| `radarr` \| null | `null` | 'sonarr' or 'radarr'; omit to query both |

### `find_orphan_downloads`

_solo lectura_

Importable files in the downloads folder that no queue item is tracking
(e.g. Download Station removed the task before Sonarr imported it).
Groups them by series/movie and says whether each episode/movie already has
a file (duplicate) or is missing. Also flags several files for the same episode.
If no folder is configured, the download folders are detected from the queue and the
import history. The scan can take a while on a NAS.

Examples: "Why wasn't S03E04 of The Capture imported?", "Is anything stuck in /downloads?"

| Parámetro | Tipo | Por defecto | Descripción |
|---|---|---|---|
| `service` | `sonarr` \| `radarr` \| null | `null` | 'sonarr' or 'radarr'; omit to query both |
| `folder` | string \| null | `null` | Folder to scan as seen by Sonarr/Radarr; default ARR_DOWNLOADS_PATH or auto-detected |
| `limit` | integer | `50` | Max items to return |

### `find_suspicious_releases`

_solo lectura_

Detect fake/malicious releases, with the indexer that provided them:
executables (.exe .scr .lnk .bat .cmd .msi .zipx) in the queue, history and blocklist;
grabs made more than a day before the episode aired or the movie's digital/physical
release (likely="fake" if they never imported, "early_release" if they did, e.g. box
sets); and different downloads for different episodes with the exact same size.

Examples: "Is there any .exe in the queue?", "Which indexer is sending me fake releases?"

| Parámetro | Tipo | Por defecto | Descripción |
|---|---|---|---|
| `service` | `sonarr` \| `radarr` \| null | `null` | 'sonarr' or 'radarr'; omit to query both |
| `days` | integer | `30` | How far back to look in history |

### `get_command_status`

_solo lectura_

Status of an asynchronous command (search, refresh, manual import) started earlier.
For a finished manual import it also checks that each file really reached the library.

Examples: "Has the search for S03E04 finished?", "Did the manual import work?"

| Parámetro | Tipo | Por defecto | Descripción |
|---|---|---|---|
| `service` | `sonarr` \| `radarr` | obligatorio | 'sonarr' (series) or 'radarr' (movies) |
| `command_id` | integer | obligatorio |  |

## Resolución de problemas

### `explain_search`

_solo lectura · contacta con servicios externos_

Explain why Sonarr/Radarr did not grab something: run an interactive search and
summarize every release found, grouped by rejection reason (language, size, quality,
custom format score, already have it…), plus basic checks (monitored, aired, available).
The guids returned can be grabbed with grab_release. Queries every indexer live, so it
counts against the hourly indexer budget: use it for one item at a time, never in a loop.

Examples: "Why didn't Sonarr grab S03E04 of The Capture?",
"Why is Dune not downloading? What releases are out there?"

| Parámetro | Tipo | Por defecto | Descripción |
|---|---|---|---|
| `series` | string \| integer \| null | `null` | Sonarr series ID or title |
| `season` | integer \| null | `null` | Season number |
| `episode` | integer \| null | `null` | Episode number within `season`; omit to search the whole season |
| `movie` | string \| integer \| null | `null` | Radarr movie ID or title |
| `limit` | integer | `5` |  |

### `grab_release`

_escritura_

Send a specific release (from explain_search) to the download client, even if it
was rejected. Only works within ~30 minutes of the search; search again if it fails.

Examples: "Grab that 1080p release anyway", "Download the second one from the list"

| Parámetro | Tipo | Por defecto | Descripción |
|---|---|---|---|
| `service` | `sonarr` \| `radarr` | obligatorio | 'sonarr' (series) or 'radarr' (movies) |
| `guid` | string | obligatorio | Release guid from explain_search |
| `indexer_id` | integer | obligatorio | indexer_id from explain_search (Sonarr/Radarr's id, not Prowlarr's) |

### `diagnose_import`

_solo lectura_

Diagnose why a download is not being imported: combines the queue status messages,
Sonarr/Radarr's own rejections for the files in the download, and path visibility,
and returns the probable cause with a concrete fix (remote path mapping, permissions,
manual match, not an upgrade, sample, fake release…).

Examples: "Why isn't S03E04 importing?", "Why is everything stuck in importBlocked?"

| Parámetro | Tipo | Por defecto | Descripción |
|---|---|---|---|
| `service` | `sonarr` \| `radarr` | obligatorio | 'sonarr' (series) or 'radarr' (movies) |
| `queue_id` | integer \| null | `null` | Queue item ID (from get_queue); omit to check every stuck item |

### `check_paths`

_solo lectura_

Check the path setup that breaks most imports: root folders (accessible, free space),
remote path mappings, download clients, whether Sonarr/Radarr can actually see the
download clients' output folders, and the related health warnings.

Examples: "Is my remote path mapping right?", "Why does Sonarr say the path does not exist?"

| Parámetro | Tipo | Por defecto | Descripción |
|---|---|---|---|
| `service` | `sonarr` \| `radarr` \| null | `null` | 'sonarr' or 'radarr'; omit to query both |

### `find_stalled_downloads`

_solo lectura_

Find downloads that are stuck: reported as stalled / no connections / no seeds by the
download client, with a download client error, or — after `min_hours` — still at 0 %
(no_progress), downloading with no speed/ETA (no_activity), or with no metadata yet
(size 0, typical of magnets without peers). Paused or queued items are not reported.
Pair with remove_from_queue(blocklist=true) to grab a different release.

Examples: "Which downloads are stalled?", "Remove the stuck torrents and find another release"

| Parámetro | Tipo | Por defecto | Descripción |
|---|---|---|---|
| `service` | `sonarr` \| `radarr` \| null | `null` | 'sonarr' or 'radarr'; omit to query both |
| `min_hours` | number | `6.0` | Ignore items added less than N hours ago (no-progress check) |

### `parse_release`

_solo lectura_

Show how Sonarr/Radarr interpret a release name: matched series/episodes or movie,
quality, languages, custom formats and score. If the item already has a file, compares
both and estimates whether it would be an upgrade under the quality profile and why.

Examples: "How would Sonarr score 'The.Capture.S03E04.2160p.WEB.DV-GRP'?",
"Why is this release 'not an upgrade'?"

| Parámetro | Tipo | Por defecto | Descripción |
|---|---|---|---|
| `title` | string | obligatorio | Release name, e.g. 'The.Capture.S03E04.1080p.WEB.H264-NTb' |
| `service` | `sonarr` \| `radarr` \| null | `null` | 'sonarr' or 'radarr'; omit to query both |

## Mantenimiento

### `library_report`

_solo lectura_

Disk usage and cleanup report: total size, biggest series/movies, unmonitored items
that still have files, ended series that are complete, size per quality (movies) and
free space per root folder. Read-only: it never deletes anything.

Examples: "What takes the most space?", "What could I delete to free space?"

| Parámetro | Tipo | Por defecto | Descripción |
|---|---|---|---|
| `service` | `sonarr` \| `radarr` \| null | `null` | 'sonarr' or 'radarr'; omit to query both |
| `limit` | integer | `10` |  |

### `bulk_edit_preview`

_solo lectura_

Preview a change to many series or movies at once (monitoring, quality profile, tags,
series type, minimum availability): which items match and what would change. Changes
nothing. Select items by IDs/titles and/or filters (status, monitored, quality profile,
tag, year, complete). Show the preview to the user; if they agree, apply it with
bulk_edit_apply and the confirmation_token returned here.

Examples: "Which ended series would be unmonitored?", "Preview putting the 4K profile on all 2024 movies"

| Parámetro | Tipo | Por defecto | Descripción |
|---|---|---|---|
| `service` | `sonarr` \| `radarr` | obligatorio | 'sonarr' (series) or 'radarr' (movies) |
| `items` | list[string \| integer] \| null | `null` | Series/movie IDs or titles to edit |
| `status` | string \| null | `null` | Filter by status. Sonarr: continuing, ended, upcoming. Radarr: announced, inCinemas, released |
| `monitored` | boolean \| null | `null` | Filter: currently monitored or not |
| `quality_profile` | string \| integer \| null | `null` | Filter: current quality profile name or ID |
| `tag` | string \| null | `null` | Filter: has this tag |
| `year_from` | integer \| null | `null` | Filter: year >= this |
| `year_to` | integer \| null | `null` | Filter: year <= this |
| `complete` | boolean \| null | `null` | Filter: all episodes on disk (series) / has file (movies) |
| `set_monitored` | boolean \| null | `null` | Change: monitor or unmonitor |
| `set_quality_profile` | string \| integer \| null | `null` | Change: new quality profile name or ID |
| `add_tags` | list[string] \| null | `null` | Change: tags to add (created if missing) |
| `remove_tags` | list[string] \| null | `null` | Change: tags to remove |
| `set_series_type` | `standard` \| `daily` \| `anime` \| null | `null` | Change (Sonarr) |
| `set_minimum_availability` | `announced` \| `inCinemas` \| `released` \| null | `null` | Change (Radarr) |

### `bulk_edit_apply`

_escritura_

Apply a change to many series or movies at once. For several items or a filter
selection, call bulk_edit_preview first, show it to the user and only call this once
they agree, passing the preview's confirmation_token (same selection and changes). A
single item named by the user can be changed directly. Root folders are not changed
here because that would move files.

Examples: "Yes, unmonitor those ended series", "Tag The Capture with 'uk'"

| Parámetro | Tipo | Por defecto | Descripción |
|---|---|---|---|
| `service` | `sonarr` \| `radarr` | obligatorio | 'sonarr' (series) or 'radarr' (movies) |
| `items` | list[string \| integer] \| null | `null` | Series/movie IDs or titles to edit |
| `status` | string \| null | `null` | Filter by status. Sonarr: continuing, ended, upcoming. Radarr: announced, inCinemas, released |
| `monitored` | boolean \| null | `null` | Filter: currently monitored or not |
| `quality_profile` | string \| integer \| null | `null` | Filter: current quality profile name or ID |
| `tag` | string \| null | `null` | Filter: has this tag |
| `year_from` | integer \| null | `null` | Filter: year >= this |
| `year_to` | integer \| null | `null` | Filter: year <= this |
| `complete` | boolean \| null | `null` | Filter: all episodes on disk (series) / has file (movies) |
| `set_monitored` | boolean \| null | `null` | Change: monitor or unmonitor |
| `set_quality_profile` | string \| integer \| null | `null` | Change: new quality profile name or ID |
| `add_tags` | list[string] \| null | `null` | Change: tags to add (created if missing) |
| `remove_tags` | list[string] \| null | `null` | Change: tags to remove |
| `set_series_type` | `standard` \| `daily` \| `anime` \| null | `null` | Change (Sonarr) |
| `set_minimum_availability` | `announced` \| `inCinemas` \| `released` \| null | `null` | Change (Radarr) |
| `confirmation_token` | string \| null | `null` | Token from bulk_edit_preview; required for several items or a filter selection |

### `preview_rename`

_solo lectura_

Preview which files would be renamed by the current naming settings
(current path -> new path). Nothing is changed. Show it to the user; if they agree,
apply with rename_files and the confirmation_token returned here.

Examples: "Which files of The Capture don't follow my naming scheme?",
"Preview renaming Dune"

| Parámetro | Tipo | Por defecto | Descripción |
|---|---|---|---|
| `series` | string \| integer \| null | `null` | Sonarr series ID or title |
| `season` | integer \| null | `null` | Only this season |
| `movie` | string \| integer \| null | `null` | Radarr movie ID or title |
| `limit` | integer | `50` |  |

### `rename_files`

_escritura_

Rename the files of a series (optionally one season) or a movie to match the
current naming settings. Call preview_rename first, show it to the user and only call
this once they agree, passing the preview's confirmation_token (required for more
than one file).

Examples: "Yes, rename the files of The Capture season 3", "Apply the rename to Dune"

| Parámetro | Tipo | Por defecto | Descripción |
|---|---|---|---|
| `series` | string \| integer \| null | `null` | Sonarr series ID or title |
| `season` | integer \| null | `null` | Only this season |
| `movie` | string \| integer \| null | `null` | Radarr movie ID or title |
| `confirmation_token` | string \| null | `null` | Token from preview_rename; required to rename more than one file |

### `test_download_clients`

_solo lectura · contacta con servicios externos_

Test the connection to every download client configured in Sonarr/Radarr
and report which ones fail and why.

Examples: "Can Sonarr reach my download client?", "Test the download clients"

| Parámetro | Tipo | Por defecto | Descripción |
|---|---|---|---|
| `service` | `sonarr` \| `radarr` \| null | `null` | 'sonarr' or 'radarr'; omit to query both |

## Acciones (escritura)

### `search_episodes`

_escritura · requiere Sonarr_

Trigger an indexer search for specific episodes (by ID, or series + season + episode numbers).
Episodes searched in the last hour are skipped (force=true to override) and searches over
many episodes ask for confirmation first, to respect indexer limits.

Examples: "Search S03E04 of The Capture again", "Look for episodes 3 and 4 of season 1 of Severance"

| Parámetro | Tipo | Por defecto | Descripción |
|---|---|---|---|
| `episode_ids` | list[integer] \| null | `null` | Sonarr episode IDs |
| `series` | string \| integer \| null | `null` | Series ID or title, with season + episodes |
| `season` | integer \| null | `null` |  |
| `episodes` | list[integer] \| null | `null` | Episode numbers within `season` |
| `confirm` | boolean | `False` | Required when the search covers many items (shows the count first) |
| `force` | boolean | `False` | Also search items Sonarr/Radarr searched very recently |

### `search_season`

_escritura · requiere Sonarr_

Trigger an indexer search for a whole season (season packs or every episode).

Examples: "Search season 2 of The Capture"

| Parámetro | Tipo | Por defecto | Descripción |
|---|---|---|---|
| `series` | string \| integer | obligatorio | Series ID or title |
| `season` | integer | obligatorio |  |

### `search_missing`

_escritura_

Trigger a search for every monitored missing episode (Sonarr) and/or movie (Radarr).
Sonarr/Radarr normally find new releases through RSS on their own; mass searches hit
every indexer once per item and can exceed indexer limits. Over a few items it first
returns how many would be searched and needs confirm=true. Prefer narrower searches.

Examples: "Search everything that's missing", "Search all missing episodes of The Capture"

| Parámetro | Tipo | Por defecto | Descripción |
|---|---|---|---|
| `service` | `sonarr` \| `radarr` \| null | `null` | 'sonarr' or 'radarr'; omit to query both |
| `series` | string \| integer \| null | `null` | Limit the Sonarr search to one series |
| `confirm` | boolean | `False` | Required when many items would be searched (shows the count first) |

### `search_movie`

_escritura · requiere Radarr_

Trigger an indexer search for one or more movies. Movies searched in the last hour are
skipped (force=true to override) and searches over many movies ask for confirmation first.

Examples: "Search Dune again", "Look for a new release of Oppenheimer"

| Parámetro | Tipo | Por defecto | Descripción |
|---|---|---|---|
| `movies` | list[string \| integer] | obligatorio | Movie IDs or titles |
| `confirm` | boolean | `False` | Required when the search covers many items (shows the count first) |
| `force` | boolean | `False` | Also search items Sonarr/Radarr searched very recently |

### `set_monitored`

_escritura_

Monitor or unmonitor episodes (by ID, or series + season + episode numbers in one
call), a whole season, a whole series, or a movie.

Examples: "Stop monitoring S03E02 of Lioness", "Stop monitoring season 1 of The Capture",
"Unmonitor the movie Cats"

| Parámetro | Tipo | Por defecto | Descripción |
|---|---|---|---|
| `monitored` | boolean | obligatorio |  |
| `episode_ids` | list[integer] \| null | `null` | Sonarr episode IDs |
| `series` | string \| integer \| null | `null` | Series ID or title |
| `season` | integer \| null | `null` | With `series`: only this season |
| `episodes` | list[integer] \| null | `null` | With `series` + `season`: only these episode numbers |
| `movie` | string \| integer \| null | `null` | Radarr movie ID or title |

### `remove_from_queue`

_**destructiva**_

Remove items from the download queue, optionally deleting them from the download
client and blocklisting the release. With blocklist=true and skip_redownload=false,
Sonarr/Radarr automatically search for another release. Removing a torrent from the
client stops seeding (private trackers may count it as hit-and-run). Many items at
once need confirm=true.

Examples: "Remove the .exe releases from the queue, blocklist them and find another version",
"Delete queue item 42 from Download Station"

| Parámetro | Tipo | Por defecto | Descripción |
|---|---|---|---|
| `service` | `sonarr` \| `radarr` | obligatorio | 'sonarr' (series) or 'radarr' (movies) |
| `queue_ids` | list[integer] | obligatorio | Queue item IDs (from get_queue) |
| `remove_from_client` | boolean | `True` | Also delete the task/files in the download client |
| `blocklist` | boolean | `False` | Add the release to the blocklist |
| `skip_redownload` | boolean | `False` | With blocklist=true, do NOT search for a replacement automatically |
| `confirm` | boolean | `False` | Required when removing many items at once |

### `refresh_item`

_escritura_

Refresh metadata and rescan files on disk for a series or movie.

Examples: "Refresh The Capture", "Rescan the files of Dune"

| Parámetro | Tipo | Por defecto | Descripción |
|---|---|---|---|
| `series` | string \| integer \| null | `null` | Series ID or title |
| `movie` | string \| integer \| null | `null` | Movie ID or title |

### `add_series`

_escritura · requiere Sonarr_

Add a new series to Sonarr. Looks it up online first; if several results match it
returns the candidates, and if quality profile or root folder are missing it returns
the available options instead of guessing.

Examples: "Add The Capture with the HD-1080p profile", "Add Severance and search for it"

| Parámetro | Tipo | Por defecto | Descripción |
|---|---|---|---|
| `term` | string | obligatorio | Title to look up online, or 'tvdb:12345' |
| `quality_profile` | string \| integer \| null | `null` | Quality profile name or ID |
| `root_folder` | string \| null | `null` | Root folder path |
| `tvdb_id` | integer \| null | `null` | Pick this exact result from the lookup |
| `monitor` | `all` \| `future` \| `missing` \| `existing` \| `firstSeason` \| `lastSeason` \| `pilot` \| `recent` \| `none` | `'all'` |  |
| `search_now` | boolean | `True` | Search for missing episodes right away |

### `add_movie`

_escritura · requiere Radarr_

Add a new movie to Radarr. Looks it up online first; if several results match it
returns the candidates, and if quality profile or root folder are missing it returns
the available options instead of guessing.

Examples: "Add Dune Part Two in HD-1080p", "Add the movie Past Lives"

| Parámetro | Tipo | Por defecto | Descripción |
|---|---|---|---|
| `term` | string | obligatorio | Title to look up online, or 'tmdb:12345' / 'imdb:tt123' |
| `quality_profile` | string \| integer \| null | `null` | Quality profile name or ID |
| `root_folder` | string \| null | `null` | Root folder path |
| `tmdb_id` | integer \| null | `null` | Pick this exact result from the lookup |
| `minimum_availability` | `announced` \| `inCinemas` \| `released` | `'released'` |  |
| `search_now` | boolean | `True` | Search for the movie right away |

### `manual_import`

_**destructiva**_

Import specific files from the downloads folder into the library (all or nothing).
Never imports a whole folder blindly: every file must be listed, must be matched to a
series/episode or movie, must have no rejections, and no two files may target the same
episode or movie. If anything fails, nothing is imported and the problems are returned.
When Sonarr/Radarr cannot identify a file ("Unknown Series", "matched by ID, manual import
required"), pass `matches` to assign it by hand; the assignment is re-validated first.
Replacing a file that is already in the library needs allow_replace=true.
By default it waits for the import and verifies each file (Sonarr/Radarr report the
command as successful even when a file fails to move), returning the reason from
their log for any file that did not get in.

Examples: "Import /downloads/The.Capture.S03E04.1080p.mkv",
"Import that file as episode 4 of season 3 of The Capture"

| Parámetro | Tipo | Por defecto | Descripción |
|---|---|---|---|
| `service` | `sonarr` \| `radarr` | obligatorio | 'sonarr' (series) or 'radarr' (movies) |
| `files` | list[string] | obligatorio | Exact file paths as seen by Sonarr/Radarr (from find_orphan_downloads) |
| `import_mode` | `auto` \| `copy` \| `move` | `'auto'` | auto (default, like the web UI): copy/hardlink if the download client is still seeding, move otherwise. copy: always copy/hardlink. move: always move (breaks seeding). |
| `allow_replace` | boolean | `False` | Allow replacing files that are already in the library (they are deleted) |
| `allow_downgrade` | boolean | `False` | Also import files Sonarr/Radarr reject as 'not an upgrade' (lower quality or score than the current file). Only when the user explicitly wants the lower version; needs allow_replace. |
| `matches` | list[any] \| null | `null` | Manual identification for files that were not matched (or were matched wrongly) |
| `wait` | boolean | `True` | Wait (up to 2 min) for the import and check that every file really got in |

## Prowlarr

### `list_indexers`

_solo lectura · requiere Prowlarr_

Indexers configured in Prowlarr: state (ok / failing = paused by Prowlarr after
repeated failures / disabled), priority, protocol and privacy.

Examples: "Which indexers do I have?", "Is LimeTorrents disabled?"

### `get_indexer_stats`

_solo lectura · requiere Prowlarr_

Per-indexer statistics from Prowlarr: queries, RSS, grabs, failures and response
times, sorted by failure rate (searches + RSS + grabs).

Examples: "Which indexer fails the most this month?", "How many grabs did each indexer give me?"

| Parámetro | Tipo | Por defecto | Descripción |
|---|---|---|---|
| `days` | integer | `30` | Look back N days (ignored if start_date is set) |
| `start_date` | string \| null | `null` | ISO date, e.g. 2026-10-01 |
| `end_date` | string \| null | `null` | ISO date; default now |

### `set_indexer_enabled`

_escritura · requiere Prowlarr_

Enable or disable an indexer in Prowlarr.

Examples: "Disable LimeTorrents", "Turn TheRARBG back on"

| Parámetro | Tipo | Por defecto | Descripción |
|---|---|---|---|
| `indexer` | string \| integer | obligatorio | Indexer ID or name |
| `enabled` | boolean | obligatorio |  |

### `test_indexers`

_escritura · requiere Prowlarr_

Run Prowlarr's connectivity test on every indexer and report which ones fail and why.
It can take a minute.

Examples: "Test all my indexers", "Which indexers are broken right now?"
