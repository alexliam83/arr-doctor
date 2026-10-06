# Changelog

**English** · [Español](CHANGELOG.es.md)

Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Versioning follows [SemVer](https://semver.org/).

## [Unreleased]

## [0.2.0] - 2026-10-06

First public release.

### Added

- Logo (`docs/assets/logo.svg`), designed in Claude Design.
- Manual Claude Desktop test checklist (`docs/testing/claude-desktop.md`).
- Troubleshooting, based on the most frequent questions in the Sonarr/Radarr issues and wiki:
  - `explain_search`: interactive search with releases grouped by rejection reason, plus basic checks.
  - `grab_release`: grab a specific release even if it was rejected.
  - `diagnose_import`: probable cause of a failed import and how to fix it.
  - `check_paths`: root folders, remote path mappings, download clients and visibility of download folders.
  - `find_stalled_downloads`: stalled downloads, downloads with no progress, download client errors.
  - `parse_release`: how a release is interpreted and scored, with an upgrade estimate.
- Maintenance: `bulk_edit` (preview first, then apply), `preview_rename` / `rename_files`, `library_report`, `test_download_clients`.
- `get_health` adds the usual fix to each known health check.
- `manual_import` accepts `matches` to assign unidentified files by hand. Sonarr/Radarr re-validate the assignment before importing.
- Messages in English and Spanish (`ARR_LANG`, default `en`).
- Documentation in English and Spanish (README, DESIGN, ROADMAP, TOOLS, CHANGELOG).

### Changed

- **Renamed from `arr-mcp` to `arr-doctor`** (package, command, repository): `arr-mcp` was already taken on PyPI and by dozens of GitHub repos. New logo: a heartbeat that ends in a play button.

- `bulk_edit` is split into `bulk_edit_preview` (read-only) and `bulk_edit_apply`, and `rename_files` only applies (`preview_rename` returns the token): in Claude Desktop the second permission dialog now reads "…Bulk edit apply…" instead of the same name as the preview.

- The preview token alone was not enough: in Claude Desktop the model previewed and applied in the same turn. When the client supports MCP elicitation, `bulk_edit` (several items or a filter) and `rename_files` (several files) now ask the user directly, and their answer wins over any token; without elicitation the token flow still applies.

- From the second Claude Desktop run (the model applied a tag without showing the preview): `bulk_edit` and `rename_files` now need the preview's `confirmation_token` to apply to several items, a filter selection or several files; a single named item still applies directly. `set_monitored` accepts series + season + episode numbers in one call.

- From the first Claude Desktop test run:
  - `find_suspicious_releases` also flags grabs made more than a day before the episode aired (or the movie's digital/physical release), marked `likely: fake` when they never imported and `early_release` when they did (box sets released ahead of the air dates), plus separate downloads for different episodes with the exact same size. On a real library: 17 likely fakes, while two BBC box sets were correctly recognised as early releases.
  - `get_queue(only_problems=true)` includes stalled downloads (`stall_reason`) even when Sonarr/Radarr report them as healthy.
  - `explain_search` groups results for other episodes/seasons/series into one line; a follow-up search of the same item points to its approved releases (`grab_release`) instead of saying nothing new would turn up.
  - `preview_rename`/`rename_files` say when renaming is switched off in Media Management.
  - Prowlarr tools return `prowlarr_id` (Sonarr/Radarr number indexers differently); disabled indexers no longer look like failing ones.
  - Stricter title matching: whole words, and suggestions ignore leading articles.
  - Clearer fix text for the update health check.

- Searches skip episodes that have not aired and movies Radarr does not consider available (`force=true` overrides): found when an episode airing the next day only had fake `.exe` releases. `remove_from_queue` warns when a replacement search is started for something not released yet.

- `manual_import` accepts `allow_downgrade` (with `allow_replace`) to import a lower-quality version on purpose; other rejections still block. Files are linked to their queue item's download, so `auto` mode copies instead of moving a torrent that is still seeding.

- Found with a real Sonarr: a season pack is one queue record per episode. `get_queue`, `diagnose_import`, `find_stalled_downloads` and `find_suspicious_releases` now show one entry per download (with `episodes` and `queue_ids`), and `diagnose_import` no longer adds a false "missing from the pack" when every file is present but rejected.
- `find_suspicious_releases` also catches release titles as Sonarr/Radarr store them ("…H264 VICE exe", without the dot).

- Found with a real Prowlarr: `get_indexer_stats` ignored RSS failures, so dead indexers (30/30 failed RSS calls, never searched) ranked below healthy ones. It now ranks by overall failure rate (searches + RSS + grabs). `list_indexers` shows a `state` (ok / failing / disabled), and Prowlarr's own health checks get a fix too.

- Tested every tool, writes included, against disposable containers of Sonarr 4.0.20, Radarr 5.28 and 6.4.4, and Prowlarr 2.6.5.
- `bulk_edit` reads the items back after applying and shows what Sonarr/Radarr stored (it used to show the state before the change).

- **Security:** HTTP redirects are no longer followed (a cross-origin redirect would have sent the `X-Api-Key` header to another host, and 301/302 could turn a POST into a GET); the error names the target so the URL can be fixed. API keys are `SecretStr` in the settings.
- Fixed: `parse_release` never saw the existing episode file (missing `includeEpisodeFile`), so it always answered "no file yet".
- `explain_search` only spends indexer budget once the series/movie is resolved. mypy runs in CI.

- `manual_import` waits up to 40 s and verifies every file; longer imports (moving gigabytes between volumes on a NAS took 4 min in a real test) are verified by `get_command_status` once they finish. A file counts only if it was added while that command ran. Before: (`result`: imported / partial / failed, with the reason from the Sonarr/Radarr log). Found on a real NAS: Sonarr reported "Manually imported 6 files" as successful while all six failed with "Not a directory". `wait=false` keeps the old fire-and-forget behaviour.
- `diagnose_import` recognises a library path blocked by a file (`path_conflict`).

- Found while testing against a real Radarr: the queue no longer includes downloads that Sonarr/Radarr did not grab (`get_queue` counts them as `unknown_items_hidden`; `include_unknown=true` lists them). They flooded `get_queue`/`diagnose_import` and could hide real orphaned files.
- `find_stalled_downloads` also reports downloads with no speed for hours (`no_activity`) and magnets that never got metadata (`no_metadata`), and ignores paused/queued items.
- `get_logs` allows up to 60 s (filtering the log database is slow on a NAS).

- **Good-practice guardrails** (see docs/GOOD_PRACTICES.md): hourly indexer budget (`ARR_INDEXER_BUDGET_PER_HOUR`), recently searched items are skipped (`ARR_SEARCH_COOLDOWN_MINUTES`, `force=true`), searches and queue removals over `ARR_SEARCH_CONFIRM_ABOVE` items need `confirm=true`, `rename_files` previews unless `apply=true`.
- `manual_import` defaults to `import_mode="auto"` (copy/hardlink while seeding, like the web UI) instead of `move`, and replacing existing files needs `allow_replace=true`; it warns when there is no recycle bin.

- `ARR_DOWNLOADS_PATH` is optional: `find_orphan_downloads` detects the download folders from the queue and import history.
- Paths from Sonarr/Radarr are compared correctly whether they are POSIX, Windows or UNC paths.
- Windows and Linux are both tested in CI, including an end-to-end stdio test of the real process.

- Connection errors give a generic hint (port changed, container stopped) instead of assuming Synology.
- 404 errors show the server's message when it is useful (e.g. "try searching again").

## [0.1.0] - 2026-10-04

### Added

- stdio MCP server (`arr-doctor`) built on FastMCP 2.12.
- Configuration from environment variables or `.env`, with per-service conditional registration and `ARR_READONLY` mode.
- Status: `get_system_status`.
- Library: `search_library`, `get_series`, `get_episodes`, `get_movie`, `get_missing`, `get_cutoff_unmet`, `get_calendar`.
- Diagnostics: `get_queue`, `get_history`, `get_blocklist`, `get_health`, `get_logs`, `get_disk_space`, `find_orphan_downloads`, `find_suspicious_releases`, `get_command_status`.
- Actions: `search_episodes`, `search_season`, `search_missing`, `search_movie`, `set_monitored`, `remove_from_queue`, `refresh_item`, `add_series`, `add_movie`, `manual_import`.
- Prowlarr: `list_indexers`, `get_indexer_stats`, `set_indexer_enabled`, `test_indexers`.
- `scripts/smoke.py` to try the read-only tools against a real server, and `scripts/gen_tools_doc.py` to generate the tool reference.
- GitHub Actions CI (Linux and Windows, Python 3.11–3.13) and ruff.
