# Good practices and guardrails

**English** · [Español](GOOD_PRACTICES.es.md)

An MCP server lets a language model drive Sonarr, Radarr and Prowlarr. A model can misunderstand a request, call a tool in a loop or act on a vague instruction. This server therefore follows the practices recommended by the Servarr wiki (the official documentation of Sonarr, Radarr and Prowlarr) and enforces them in code, not just in the tool descriptions.

## What the official documentation says

| Practice | Source |
|---|---|
| Sonarr/Radarr **do not search regularly**: they read the indexers' RSS feeds and grab what matches. Active searches are for specific cases (adding an item, a manual search, Wanted). | [Sonarr FAQ — How does Sonarr find episodes](https://wiki.servarr.com/sonarr/faq#how-does-sonarr-find-episodes) |
| Before "Search All", the web UI shows how many episodes will be searched, "particularly helpful to know if your indexers limit your API calls". | [Sonarr — Wanted](https://wiki.servarr.com/sonarr/wanted) |
| Indexers limit API hits and grabs per day/hour (Prowlarr "Query Limit" and "Grab Limit"). | [Prowlarr — Indexers](https://wiki.servarr.com/prowlarr/indexers) |
| Indexers rate-limit, and some ban IP addresses. | [Sonarr troubleshooting — Hitting rate limits / IP Ban](https://wiki.servarr.com/sonarr/troubleshooting) |
| RSS sync interval: minimum 10 minutes. | [Sonarr settings — Indexers](https://wiki.servarr.com/sonarr/settings) |
| Torrents that are still seeding must be copied or hardlinked, not moved. Sonarr's "Auto" import mode does this by itself. | [Sonarr settings — Use Hard links instead of Copy](https://wiki.servarr.com/sonarr/settings), [TRaSH Guides — Hardlinks](https://trash-guides.info/hardlinks), Sonarr source (`ImportMode.Auto`) |
| Deleted or replaced files only go to the recycle bin if one is configured. | [Sonarr settings — Recycling Bin](https://wiki.servarr.com/sonarr/settings) |
| The API key is secret and should not be shared. | [Prowlarr settings — Security](https://wiki.servarr.com/prowlarr/settings) |

## How the server enforces them

### Indexers: searching is the exception

- **Hourly indexer budget.** Every operation that queries the indexers counts against a one-hour sliding window: automatic searches, interactive searches (`explain_search`), forced grabs (`grab_release`), indexer tests, and adding an item with "search now". When the budget is reached the tool refuses with a clear message, so a model stuck in a loop cannot hammer your indexers. Default: 30 per hour (`ARR_INDEXER_BUDGET_PER_HOUR`, `0` = unlimited).
- **Nothing is searched before release.** Episodes that have not aired, and movies Radarr does not consider available, are skipped (`force=true` overrides): before release, matching results are fakes (a real episode airing the next day only had `.exe` releases). RSS picks up the real one when it comes out.
- **No repeated searches.** `search_episodes` and `search_movie` skip items that Sonarr/Radarr searched less than 60 minutes ago (`lastSearchTime`); searching again that soon almost never finds anything new. `force=true` overrides it (`ARR_SEARCH_COOLDOWN_MINUTES`, `0` = off).
- **Mass searches in two steps.** Above 10 items (`ARR_SEARCH_CONFIRM_ABOVE`), `search_episodes`, `search_movie` and `search_missing` first return how many items would be searched, and only run with `confirm=true`, like the web UI's "Search All" warning. `search_missing` says when nothing is missing instead of searching.
- **Blocklist + replacement search** in `remove_from_queue` counts one search per item, checked **before** anything is removed.

### Files: never lose data silently

- **`manual_import` uses `auto` mode by default**, the same as the web UI: copy or hardlink if the download client is still seeding, move otherwise. `move` (which breaks seeding) has to be chosen explicitly.
- **Downgrades** (a file Sonarr/Radarr reject as "not an upgrade") are only imported with `allow_downgrade=true` plus `allow_replace=true`; every other rejection still blocks.
- **Replacing files** that are already in the library needs `allow_replace=true`. If no recycle bin is configured, the answer warns that the old files are deleted permanently.
- **All or nothing:** `manual_import` imports nothing if any file is rejected, unidentified, or competes with another file for the same episode/movie. A manual match is re-validated by Sonarr/Radarr; it can never skip their checks.
- **Verify, don't trust:** Sonarr/Radarr report a manual import as successful even when every file fails to move. `manual_import` waits for the command and checks each episode/movie really got a new file, returning the reason from the log for any that did not.
- **Preview first, in a separate tool:** `bulk_edit_preview` and `preview_rename` are read-only; the changes are made by `bulk_edit_apply` and `rename_files`, so the client's permission dialog shows clearly which call changes things. For several items, a filter selection or several files, applying also needs the preview's `confirmation_token`, so a model cannot skip computing the preview. That still let a model preview and apply in the same turn without asking, so when the MCP client supports elicitation the server also asks the user directly ("apply X to N items?"): the model cannot answer for them. Without elicitation, the client's permission dialog is the safeguard: never "always allow" write tools.
- **Big queue removals** (more than `ARR_SEARCH_CONFIRM_ABOVE` items) need `confirm=true`. The tool description warns that removing a torrent from the client stops seeding (hit-and-run on private trackers).
- **No tool deletes series, movies or files** from the library. That is deliberate.
- `bulk_edit_apply` does **not** change root folders, because that moves files.

### Configuration and secrets

- **Read-only mode** (`ARR_READONLY=true`) does not register any write tool. It is a good way to start.
- Redirects are never followed, so the API key is only ever sent to the configured URL.
- API keys are only read from the environment or `.env`. They never appear in answers, errors or logs, and the download client and indexer settings returned by tools leave out credentials.
- Write tools carry the MCP annotations `readOnlyHint: false`, plus `destructiveHint: true` when they delete. Tools that contact external services carry `openWorldHint: true`, so clients can ask for confirmation.

### Instructions for the model

The server's MCP instructions tell the model to rely on RSS, to search only for specific requests, not to poll `get_command_status` in a tight loop, and to show previews/counts to the user before confirming. The guardrails above apply even if the model ignores them.

## Settings

| Variable | Default | Effect |
|---|---|---|
| `ARR_INDEXER_BUDGET_PER_HOUR` | `30` | Max searches/grabs/indexer tests per hour. `0` = unlimited |
| `ARR_SEARCH_CONFIRM_ABOVE` | `10` | Searches or queue removals over this many items need `confirm=true` |
| `ARR_SEARCH_COOLDOWN_MINUTES` | `60` | Skip items searched less than this many minutes ago. `0` = off |
| `ARR_READONLY` | `false` | `true` = no write tools at all |
