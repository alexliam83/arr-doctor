# Design notes

**English** · [Español](DESIGN.es.md)

Decisions made during implementation, and Sonarr/Radarr/Prowlarr API details that are not obvious. Fields and endpoints were checked against the official `openapi.json` files (Sonarr `main`/v4, Radarr `develop`, Prowlarr `develop`) and, where needed, against the C# source.

## Architecture

- **`clients/`** holds all the HTTP logic: one method per endpoint, no formatting. **`tools/`** holds the MCP tools: they resolve titles, call the clients and compact the output with `formatting.py`. Tools never build URLs.
- **One `httpx.AsyncClient` per request.** For a single-user stdio server on a local network the cost is negligible. In exchange there is no state shared across event loops, which keeps tests simple, and no stale connections when the server restarts.
- **`ArrError` subclasses `fastmcp.exceptions.ToolError`.** FastMCP returns its message to the model as-is (`isError: true`), with no traceback. A logging filter stops fastmcp from dumping the traceback of these expected errors to stderr; unexpected errors are still logged.
- **Conditional registration.** `build_server(settings)` only registers the tools of configured services, and write tools only when `ARR_READONLY` is `false`. Tools that don't exist can't confuse the model.
- **`per_service()`.** Tools that query Sonarr and Radarr at once do it concurrently. If one fails, its entry becomes `{"error": …}` and the other is still returned. It only raises when every service fails, or when a single service was requested.
- **Language.** Tool descriptions are in English, because the model reads them. Everything a tool returns as an error, note or hint goes through `i18n.t()`, which uses the English/Spanish catalogue in `arr_doctor/i18n.py`. The language is set with `ARR_LANG` (`en` by default). A test checks that every message exists in both languages with the same placeholders.
- **Paths belong to the Sonarr/Radarr host**, not to the machine running this server, so `arr_doctor/paths.py` compares them without `pathlib`: POSIX, Windows (`D:\…`, case-insensitive) and UNC paths all work.
- **Windows and Linux.** CI runs every test on both, including an end-to-end test that launches the real process (`python -m arr_doctor.server` and the `arr-doctor` console script) over stdio against a local fake Sonarr. stderr is reconfigured so non-ASCII logs never fail on Windows pipes.
- **Clean stdio.** All logging goes to stderr, with `show_banner=False`. Deprecation warnings from `authlib` (an indirect fastmcp dependency) are silenced: authlib installs its own `always` filter on import, so ours is added right after it.

## Flexible identifiers

- An `int` is always an ID.
- A digit-only string is tried **first as an exact title**, then as an ID. That way series and movies such as "24" or "1917" work.
- Title matching: titles are normalized (lower case, no accents or punctuation) and compared against `title`, `originalTitle` and `alternateTitles`. A trailing year is accepted ("Dune 2021", "The Office (2005)"). A single exact match is used. Several exact matches return `{"ambiguous": true, "candidates": […]}`. With no exact match, substring matching is tried. If nothing matches, an error with `difflib` suggestions is raised.
- The ambiguous case is a **normal result**, not an error, so the model asks the user instead of retrying.

## API details

- **History `eventType` is an integer** in the query (`/history?eventType=1`) but a string in the response (`"grabbed"`). Values come from the C# enums:
  - Sonarr: grabbed 1, seriesFolderImported 2, downloadFolderImported 3, downloadFailed 4, episodeFileDeleted 5, episodeFileRenamed 6, downloadIgnored 7.
  - Radarr: grabbed 1, downloadFolderImported 3, downloadFailed 4, movieFileDeleted 6, movieFolderImported 7, movieFileRenamed 8, downloadIgnored 9 (2 and 5 are deprecated).
- **`/history` cannot filter by date.** With `days`, `/history/since?date=` is used and the series/movie filter is applied client-side.
- **List parameters** (`seriesIds`, `eventType`) are sent repeated (`?seriesIds=1&seriesIds=2`), as ASP.NET expects.
- **`/manualimport?folder=`** also accepts **a file path** (`ManualImportService.GetMediaFiles`: if the path is not a folder but exists as a file, only that file is processed). `manual_import` uses this to scan exactly the requested files.
- **The `ManualImport` command** takes `files[]` with `path`, `seriesId` + `episodeIds` (Sonarr) or `movieId` (Radarr), plus `quality`, `languages`, `releaseGroup`, `downloadId`, `indexerFlags` and, in Sonarr, `releaseType`, all copied from the scan result. `importMode` can be `move`, `copy` or `auto`; `move` (default) and `copy` are exposed.
- **`RefreshSeries`** takes `seriesIds` (list) in v4. **`RefreshMovie`** takes `movieIds`.
- **`MissingEpisodeSearch`** takes an optional `seriesId` and `monitored`.
- **Prowlarr `POST /indexer/testall`** answers **400** with the same body (`[{id, isValid, validationFailures}]`) when any indexer fails. The client accepts that 400 as a valid response.
- **Prowlarr `PUT /indexer/{id}`** needs the full resource, so it does a `GET` first and then flips `enable`. Secret fields come back masked as `********`; Prowlarr keeps the stored value when it receives that mask (`SchemaBuilder`), so credentials survive the round trip (checked against the source and a real private indexer).
- **Monitoring a series** (`PUT /series/{id}` with `monitored`) does not change its seasons. For one season, `seasons[n].monitored` is changed and the whole series is sent back.
- **Monitoring movies**: `PUT /movie/editor` with `{movieIds, monitored}`.
- **Generic 404s** (`{"message": "NotFound"}`) become "path does not exist". When the body has a useful message (for example "Couldn't find requested release in cache, try searching again"), that message is shown instead.
- **`GET /release`** is the interactive search: it queries every indexer live and returns each release with Sonarr/Radarr's decision (`approved`, `temporarilyRejected`, `rejections[]` as strings, `customFormatScore`), already **sorted by preference**. It takes `episodeId`, or `seriesId` + `seasonNumber` for a season (Sonarr), and `movieId` (Radarr).
- **`POST /release`** with `{guid, indexerId}` grabs a release. Sonarr/Radarr look it up in an interactive-search cache that lasts **30 minutes** (key `indexerId_guid`). After that they answer 404 and you have to search again.
- **`POST /manualimport`** (reprocess) takes files with a manual assignment (`seriesId` + `seasonNumber` + `episodeIds`, or `movieId`) and returns them **re-validated**, with recalculated `rejections` and custom formats. Sonarr returns the `episodes` but not the `series` object.
- **`GET /manualimport?downloadId=`** scans the output folder of a queued download. It returns `[]` when Sonarr/Radarr cannot see that path.
- **`GET /parse?title=`** returns how a release name is interpreted: `parsedEpisodeInfo` / `parsedMovieInfo`, the matched series or movie, `customFormats` and `customFormatScore`.

## Orphaned downloads (`find_orphan_downloads`)

1. Folders to scan: the `folder` parameter, `ARR_DOWNLOADS_PATH`, or, if neither is set, folders detected from the queue (`outputPath` parents) and from the last 60 days of imports (`droppedPath`, one level higher when the folder is named after the release). Up to 3, never a folder inside another one already chosen.
2. `GET /manualimport?folder=…&filterExistingFiles=true` per folder, with a timeout of at least 180 s because it can be slow on a NAS.
3. Files tracked by the queue are dropped: their `downloadId` matches a queue item, or their path is inside some queue item's `outputPath`.
4. Files are grouped by series or movie. Each one is marked `missing` (the episode has no file), `duplicate` (it already has one) or `partial` (multi-episode file with some episodes present and others not).
5. `episode_conflicts` lists episodes with several candidate files, the classic season pack + single episode case.
6. Unidentified files go to `unmatched`. If Sonarr and Radarr share the folder, movies show up as `unmatched` in Sonarr and vice versa.

## Suspicious releases (`find_suspicious_releases`)

- Release titles are stored normalized ("…H264-VICE.exe" becomes "…H264 VICE exe"), so at the very end of a title a space, `_` or `-` before the extension also counts. A release profile regex like `/\.(exe|…)$/i` misses those; `/[.\s_-](exe|scr|lnk|bat|cmd|msi)$/i` does not.
- Extensions: `.exe .scr .lnk .bat .cmd .msi .zipx`. The regex requires that no letter or digit follows, so `.exe2` and `.msix` don't count, and neither does `The.Executive`.
- It looks in the queue (title, `outputPath`, `errorMessage`, `statusMessages`), in the history of the last N days (`sourceTitle`, `data.message`, `droppedPath`, `importedPath`) and in the blocklist.
- The indexer comes from the item itself or, if missing, from the `grabbed` event with the same `downloadId`.
- `by_indexer` counts each download once, even if it shows up in both the queue and the history.
- **Pre-release grabs:** a grab more than 24 h before the episode's air date (or a movie's earliest digital/physical release). Not every one is fake: services sometimes drop a whole season before the per-episode air dates. The outcome tells them apart: `likely: fake` when the download never imported or failed, `early_release` when it imported. Only the likely fakes are counted per indexer.
- **Identical sizes:** separate downloads (different `downloadId`s) for different episodes with the exact same byte size. A season pack is one download recorded per episode with the pack size, so it never counts.

## Troubleshooting (`tools/troubleshoot.py`)

- **`explain_search`**: runs cheap checks first (monitored, aired, minimum availability, series type, already has a file), then the interactive search. Rejections are grouped after replacing numbers with `#`, so "Release is 14.2 GB…" and "Release is 18.7 GB…" count as the same reason. `closest_rejected` sorts rejected releases with temporary rejections and fewer reasons first: the near misses.
- **`diagnose_import`**: combines the queue's `statusMessages` and `errorMessage` with the `rejections` from scanning the download, and applies regex rules (`IMPORT_RULES`) in priority order: executable/dangerous, permissions, missing path, unidentified, not an upgrade, partial pack, sample, corrupt file, no video files, RAR, locked, no disk space. If the scan comes back empty and there is an `outputPath`, the diagnosis is "Sonarr cannot see that folder" (Docker volumes or remote path mapping). Each cause comes with an explanation and a fix in both languages.
- **`check_paths`**: shows root folders, remote path mappings and download clients (host, category and directory; never username or password). It checks that the parent folders of completed downloads are visible by scanning each one (at most 5), and adds the path-related health warnings.
- **`find_stalled_downloads`**: flags as `stalled` the downloads whose message says stalled, no connections, no seeds or metadata; as `client_error` those with status `failed`, `downloadClientUnavailable`, or `warning` with a message; and as `no_progress` those still at 0 % after `min_hours`. Completed or import-pending items are not included: that is `diagnose_import`'s job.
- **`parse_release`**: estimates whether a release would be an upgrade. It is an **estimate** that follows the main quality profile rules, not the full decision engine:
  - Quality rank comes from the order of the profile's `items` (worst to best). Groups share a rank, and a group's `id` can be the `cutoff`.
  - Quality not allowed, or score below `minFormatScore`: rejected.
  - No existing file: it would be grabbed.
  - Upgrades disabled, or the existing file already meets the `cutoff`: not an upgrade.
  - Higher quality: upgrade. Lower quality: not an upgrade.
  - With the same quality, the custom format score decides, honouring `cutoffFormatScore` and `minUpgradeFormatScore`.
  - With no `S01E01` in the title and both services configured, it is assumed to be a movie.

## Maintenance (`tools/maintenance.py`)

- **`bulk_edit_preview` / `bulk_edit_apply`** are separate tools so the client's permission dialog names the call that writes. The preview returns a `confirmation_token` (a hash of the items and changes); the apply tool needs it for several items or a filter selection, and asks the user directly when the client supports elicitation. Items can be selected by IDs/titles (resolved against the already loaded list, no extra requests) and/or filters. Changes go to `PUT /series/editor` or `/movie/editor` in one call; tags use `applyTags: "add"`, and removing tags needs a second call with `applyTags: "remove"`. Missing tags are created only when applying. Root folders are not exposed: changing them moves files.
- **`preview_rename` / `rename_files`** use `GET /rename` (Sonarr: `seriesId` + optional `seasonNumber`; Radarr: `movieId`) and the `RenameFiles` command with the file IDs from that preview (`episodeFileId` / `movieFileId`), so exactly the previewed files are renamed.
- **`library_report`** is computed from `/series` statistics and `/movie` (`sizeOnDisk`, `movieFile.quality`). Read-only.
- **`get_health`** adds a `fix` to each warning whose `source` is a known health check (`DownloadClientCheck`, `RemotePathMappingCheck`, `IndexerStatusCheck`…, names taken from `NzbDrone.Core/HealthCheck/Checks`). Unknown sources are returned unchanged.
- **`test_download_clients`**: `POST /downloadclient/testall`, which, like Prowlarr's, answers 400 with the per-client results when one fails.

## `manual_import`: all or nothing

Nothing is imported if any of the files:

- does not exist or is not an importable video,
- has `rejections` (for example, "Not an upgrade"),
- could not be identified as a series and episode, or as a movie,
- targets the same episode (or movie) as another file in the list.

In those cases it returns `problems` and `ok_files` so the model can propose a corrected list.

After sending the command it waits up to 40 seconds (MCP clients often abort tool calls after about a minute) and verifies each file: an episode/movie counts as imported only if its file's `dateAdded` falls between the command's `queued` and `ended` times, so neither an old file nor a later import is mistaken for this one. If the command is still running, `get_command_status` runs the same check when it finishes, using the file list stored in the command body (`body.files`). Code: `tools/importcheck.py`. Failures get their reason from the `warn` log entries that mention the file. This exists because Sonarr marked a real import of six files as successful while every move failed ("Not a directory").

With `matches`, a file can be assigned by hand to a series, season and episodes, or to a movie. The assignment is first sent to `POST /manualimport` so Sonarr/Radarr re-validate it. The file is only imported if there are no rejections afterwards: a manual match can never be used to skip the checks.

## Pending or open

- Validated against a real Sonarr v4 and Radarr 6.2 (including Sonarr accepting the `/wanted/missing` `sortKey` taken from the web UI). Pending: Prowlarr against a real server, and replacing the made-up fixtures with anonymized real responses (`smoke.py --capture`).
- Optional: Download Station (`SYNO.DownloadStation2.Task`) and Plex.
