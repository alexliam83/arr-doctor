# Roadmap: what the average Sonarr/Radarr user needs

**English** · [Español](ROADMAP.es.md)

Analysis from 2026-10-04. Sources:

- The 300 most upvoted issues of [Sonarr/Sonarr](https://github.com/Sonarr/Sonarr/issues) and [Radarr/Radarr](https://github.com/Radarr/Radarr/issues), sorted by 👍.
- Issue counts per support topic (keyword searches).
- The FAQ and Troubleshooting pages of the [Servarr wiki](https://wiki.servarr.com). The repos have no Discussions and send support to Discord and Reddit, so the wiki is the best summary of what people ask most.

Most upvoted requests are features of the apps themselves (multi-user, SSO, several versions of one file…) that an MCP server cannot add. What an MCP server can do is **explain** what the web UI hides and **automate repetitive work in natural language**. This list focuses on that.

Every endpoint mentioned exists in the official OpenAPI specs (Sonarr v4, Radarr, Prowlarr).

## High priority — ✅ done (v0.2.0, unreleased)

### 1. "Why didn't it grab X?" → `explain_search` + `grab_release` ✅

This is the most frequent question: the wiki has whole sections for it ("Why didn't Sonarr grab an episode I was expecting", "Query Successful - No Results Returned", "Media is Unmonitored", "Wrong Series Type"…). "Force grab" is also Sonarr's third most upvoted issue (#395, 112 👍).

- `explain_search(series/episode | movie)`: runs `GET /release?episodeId=` or `?movieId=` (interactive search) and groups the results by **rejection reason** (`rejections`). For example: "23 releases: 15 for language, 5 for size, 2 for custom format score, 1 approved". It includes quality, CF score, seeders and indexer. It checks the basics first: monitored, right series type, right profile.
- `grab_release(guid, indexer_id)`: force-grabs a specific release (`POST /release`). It is a write tool.

### 2. "Why isn't it importing?" → `diagnose_import` and `check_paths` ✅

"Import failed", "not importing" and "remote path" add up to about 570 issues across both projects. It is also the longest troubleshooting section: Remote Path Mapping, permissions, Docker and paths, download folder same as the library, wrong category…

- `diagnose_import(queue_id)`: combines the `statusMessages`, the `rejections` from scanning its folder (`/manualimport?downloadId=`) and the output path, and returns a probable cause with its fix. Pending: also correlate with recent log errors.
- `check_paths`: compares root folders (`/rootfolder`, accessible or not), queue output paths and `remotepathmapping`. It catches the classic case: "the download client says `/volume1/downloads/x`, but Sonarr cannot see that path".
- `manual_import` with **manual matching**: lets you give the series and episodes, or the movie, when Sonarr/Radarr cannot identify the file. Covers "Found matching series via grab history… Manual import required" and "Unknown movie" (Radarr #1441, 82 comments).

### 3. Stalled downloads → `find_stalled_downloads` ✅

Sonarr #958 (50 👍, open) and Radarr #5407 (29 👍, open). A long-standing request that is still open.

- Finds queue items that are not progressing: `warning` or `stalled` status, no progress for a long time, or the client's stalled message. Combined with `remove_from_queue(blocklist=true)` to search for another release.

### 4. Releases and custom formats → `parse_release` ✅

Custom formats and scores are a constant source of confusion: "custom format score" appears in about 180 issues, Sonarr #5598 "Improve CF Comparison Between Release and File" has 21 👍, and there are many "Not an upgrade" and upgrade-loop reports.

- `parse_release(title)`: uses `GET /parse?title=` to show how Sonarr/Radarr interpret a release name: series and episode, quality, language, custom formats and score. If the item already has a file, it compares both and says whether it would be an upgrade and why.

## Medium priority — ✅ done (v0.2.0, unreleased)

### 5. Bulk editing → `bulk_edit_preview` / `bulk_edit_apply` ✅

In Radarr, "bulk" appears in about 300 issues and "tags" in about 400; Sonarr has similar numbers. Examples: adding tags based on attributes (#3870), custom filters in Wanted (#3657).

- `bulk_edit(filter, changes)` with `PUT /series/editor` and `/movie/editor`: change quality profile, monitoring, tags, series type or minimum availability of many items at once. Root folders are left out on purpose, because changing them moves files. For example: "unmonitor every ended series", "set the 4K profile on the 2024 movies". Always with a preview of what would change before applying.

### 6. Rename with preview → `preview_rename` / `rename_files` ✅

"rename" appears in more than 600 issues per project, and Radarr #5566 asks precisely for a preview screen.

- `preview_rename(series | movie)` with `GET /rename` (current path vs new path), and `rename_files` with the `RenameFiles` command.

### 7. Disk usage and cleanup report → `library_report` ✅

Sonarr #314 "Auto delete episodes after certain criteria" (29 👍, open) and #1984 "Recycling Bin Management".

- Biggest items, unmonitored items that have files, ended series that are complete, size per quality (movies) and missing items. Read-only: deleting would be a separate, explicit step. Pending: "qualities above the profile".

### 8. Health with fixes → improve `get_health` ✅

- Add the usual cause and fix to each health warning (download client unreachable, missing root folder, indexers disabled and why, failing import lists…), on top of the wiki link already returned.
- `test_download_clients` with `POST /downloadclient/testall`.

## Low priority

9. **Running commands:** `list_tasks` and `cancel_command` (`GET`/`DELETE /command`). Sonarr #1194 "Cancel/Suspend all tasks".
10. **Backups:** `list_backups` and `create_backup` (`/system/backup`, `Backup` command). A frequent FAQ question.
11. **Import lists:** status and exclusions (`/importlist`, `/importlistexclusion`). IMDb and Trakt lists break often (Sonarr #6915, Radarr #10121).
12. **Fake-release filter:** check and set up a release-profile rule that blocks executables in Sonarr/Radarr (`/api/v3/releaseprofile`), using the regex that also matches normalized titles (`/[.\s_-](exe|scr|lnk|bat|cmd|msi)$/i`). Found on a real setup where the usual dotted regex let three fakes through.
13. **Prowlarr search** (`GET /search`) across every indexer, to compare with what Sonarr sees ("Jackett shows more results than Sonarr").

## Make user-specific bits generic

- ✅ `find_orphan_downloads`: no longer depends on `ARR_DOWNLOADS_PATH`; the folders are detected from the queue and the import history.
- ✅ Error messages: the port hint is generic (port changed, container stopped), with Synology only as an example.
- `find_suspicious_releases`: the extension list should be configurable.
- ✅ Documentation in English (main) and Spanish; tool messages in both languages (`ARR_LANG`).

## Distribution (idea, not decided)

Today installing requires Python (and Git, or downloading the ZIP). Options to make it easier for non-technical users, all built automatically by GitHub Actions on each release:

- **Claude Desktop extension (`.mcpb`, "binary" type):** double-click install, Claude asks for URLs and API keys in a form (keys stored as sensitive). No Python needed. Claude Desktop only (Windows/macOS).
- **Standalone executable** (`arr-doctor.exe` / Linux binary) on GitHub Releases: no Python needed; works with any MCP client.
- **PyPI + `uvx arr-doctor`:** only `uv` needed (it downloads Python itself).
- **Docker on a NAS/server** with HTTP transport and a mandatory token. Not recommended on the desktop (it needs Docker Desktop running) nor through WSL (more moving parts and the client's `env` does not reach WSL).

Caveats: unsigned executables can trigger SmartScreen; packaged Python executables are 30–50 MB and sometimes flagged by antivirus; downloads require a public repository.

## Out of scope for an MCP server

Multi-user, SSO/LDAP, several versions of the same file, unpacking RARs, new download clients, Prometheus metrics, notifications. These are features of Sonarr/Radarr themselves.
