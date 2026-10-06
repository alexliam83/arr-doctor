<p align="center">
  <img src="docs/assets/logo.svg" width="112" height="112" alt="arr-doctor logo">
</p>

<h1 align="center">arr-doctor</h1>

<p align="center">Diagnose and fix Sonarr · Radarr · Prowlarr from Claude</p>

<p align="center"><strong>English</strong> · <a href="README.es.md">Español</a></p>

An [MCP](https://modelcontextprotocol.io) server to query, troubleshoot and manage **Sonarr**, **Radarr** and **Prowlarr** from Claude Desktop or any other MCP client.

It focuses on the questions that come up most often in the Sonarr and Radarr issues and wiki:

- "Why didn't it grab S03E04? Which releases are out there and why were they rejected?"
- "Why isn't this download importing?"
- "Which downloads are stalled? Remove them and find another release."
- "Would this release be an upgrade over my file? Why does it say 'not an upgrade'?"
- "Remove the `.exe` releases from the queue, blocklist them and search again."
- "Which indexer failed the most this month?"
- "Add Severance with the HD-1080p profile."

> Status: **v0.2.0**. 43 tools, 269 tests. Validated against a real Sonarr, Radarr and Prowlarr on a Synology NAS, and every tool (including writes) against disposable Sonarr/Radarr/Prowlarr containers. See [Status](#status).

## Features

- **42 tools** in seven groups: status, library, diagnostics, troubleshooting, maintenance, actions and Prowlarr. Full reference in [docs/TOOLS.md](docs/TOOLS.md).
- **Guided troubleshooting:**
  - `explain_search` runs an interactive search and groups the releases by rejection reason (language, size, quality, custom format score…).
  - `diagnose_import` and `check_paths` give the probable cause of a failed import and how to fix it: remote path mapping, permissions, manual match, "not an upgrade"…
  - `find_stalled_downloads` spots stuck downloads.
  - `parse_release` shows how a release is scored and estimates whether it would be an upgrade.
  - `get_health` adds the usual fix to each known health warning; `test_download_clients` tests the download clients.
- **Maintenance:** `bulk_edit_preview` / `bulk_edit_apply` change many series/movies at once (monitoring, quality profile, tags…), always with a preview first; `preview_rename` / `rename_files` rename with a preview; `library_report` shows what takes space and what could be cleaned up.
- **Follows Sonarr/Radarr good practice, enforced in code:** an hourly indexer budget, no repeated searches, mass searches and removals in two steps, imports that never break seeding or replace files without permission, and previews before bulk changes. See [docs/GOOD_PRACTICES.md](docs/GOOD_PRACTICES.md).
- **Compact answers.** Never returns raw API JSON: overviews are trimmed, images and internal fields are dropped, and lists are paged with `limit` and `truncated`.
- **Readable errors in English or Spanish** (`ARR_LANG`). For example, "Sonarr returned 401: wrong API key (check SONARR_API_KEY)" instead of a traceback.
- **Titles or IDs.** Tools accept `"The Capture"`, `"Dune 2021"` or `42`. When a title is ambiguous they return the candidates instead of guessing.
- **Partial failures are tolerated.** If Radarr is down, `get_queue` still shows Sonarr's queue and flags Radarr's error.
- **Read-only mode** (`ARR_READONLY=true`): write tools are not even registered.
- **Safe imports.** `manual_import` only imports files listed one by one, never imports two files for the same episode, and imports nothing if anything is wrong. Unidentified files can be matched by hand; Sonarr/Radarr re-validate the match before importing.
- **Fake releases** (`.exe .scr .lnk .bat .cmd .msi .zipx`) and **orphaned downloads** (files left in the download folder that nothing is tracking).

## Requirements

- Windows or Linux (tested in CI on both, Python 3.11–3.13; macOS should work but is not tested).
- Python ≥ 3.11
- Sonarr v4 and/or Radarr v5–v6 (`/api/v3`). Tested with Sonarr 4.0.16 and 4.0.20, Radarr 5.28, 6.2 and 6.4.4. Prowlarr (`/api/v1`, tested with 2.4.0 and 2.6.5) is optional.
- The API key of each service (in each app: *Settings → General → Security → API Key*).

## Installation

### Quickest: with uv (no Git, no manual Python setup)

[uv](https://docs.astral.sh/uv/) downloads Python by itself and runs arr-doctor straight from the [latest release](https://github.com/alexliam83/arr-doctor/releases/latest).

1. Install uv once:
   - Windows (PowerShell): `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`
   - Linux / macOS: `curl -LsSf https://astral.sh/uv/install.sh | sh`
2. In Claude Desktop (**Settings → Developer → Edit Config**), add inside `mcpServers`:

   ```json
   "arr": {
     "command": "uvx",
     "args": ["--from", "https://github.com/alexliam83/arr-doctor/releases/download/v0.2.0/arr_doctor-0.2.0-py3-none-any.whl", "arr-doctor"],
     "env": {
       "SONARR_URL": "http://192.168.1.10:8989",
       "SONARR_API_KEY": "your-sonarr-api-key",
       "RADARR_URL": "http://192.168.1.10:7878",
       "RADARR_API_KEY": "your-radarr-api-key"
     }
   }
   ```

   If Claude Desktop cannot find `uvx`, put its full path in `command`, e.g. `"command": "C:\\Users\\<you>\\.local\\bin\\uvx.exe"` on Windows or `"~/.local/bin/uvx"` elsewhere.
3. Restart Claude Desktop completely.

Without uv: `pip install https://github.com/alexliam83/arr-doctor/releases/download/v0.2.0/arr_doctor-0.2.0-py3-none-any.whl` installs the `arr-doctor` command.

### From source (Windows, Claude Desktop)

```powershell
cd C:\
git clone https://github.com/alexliam83/arr-doctor.git
cd arr-doctor
python -m venv .venv
.\.venv\Scripts\pip install -e .
```

In Claude Desktop, open **Settings → Developer → Edit Config** and add this inside `mcpServers`, leaving the rest of the file alone:

```json
"arr": {
  "command": "C:\\arr-doctor\\.venv\\Scripts\\arr-doctor.exe",
  "env": {
    "SONARR_URL": "http://192.168.1.10:8989",
    "SONARR_API_KEY": "your-sonarr-api-key",
    "RADARR_URL": "http://192.168.1.10:7878",
    "RADARR_API_KEY": "your-radarr-api-key"
  }
}
```

If the file was empty, it ends up like this:

```json
{
  "mcpServers": {
    "arr": { "command": "…", "env": { "…": "…" } }
  }
}
```

Restart Claude Desktop **completely**, quitting it from the system tray icon too. In a new conversation, the tools icon should list `arr`.

> **Claude Desktop from the Microsoft Store.** This version keeps its config in a virtualized path, usually `%LOCALAPPDATA%\Packages\Claude_…\LocalCache\Roaming\Claude\claude_desktop_config.json`. Always open it with "Edit Config" to be sure you edit the right file. Server logs are in the `logs` folder of that same directory (`mcp-server-arr.log`).

### Linux / macOS

```bash
git clone https://github.com/alexliam83/arr-doctor.git && cd arr-doctor
python3 -m venv .venv
.venv/bin/pip install -e .
cp .env.example .env   # and fill in the keys
```

In your MCP client config, use `/path/to/arr-doctor/.venv/bin/arr-doctor` as the `command`.

## Configuration

Variables are read from the environment (the `env` block of the MCP client) or from a `.env` file in the repository folder. There is a template in [.env.example](.env.example).

| Variable | Required | Default | Description |
|---|---|---|---|
| `SONARR_URL` | yes\* | — | Full URL, e.g. `http://192.168.1.10:8989` |
| `SONARR_API_KEY` | yes\* | — | |
| `RADARR_URL` | yes\* | — | e.g. `http://192.168.1.10:7878` |
| `RADARR_API_KEY` | yes\* | — | |
| `PROWLARR_URL` | no | — | e.g. `http://192.168.1.10:9696` |
| `PROWLARR_API_KEY` | no | — | |
| `ARR_LANG` | no | `en` | Language of errors and notes: `en` or `es` |
| `ARR_READONLY` | no | `false` | `true` disables every write tool |
| `ARR_INDEXER_BUDGET_PER_HOUR` | no | `30` | Max searches/grabs/indexer tests per hour (`0` = unlimited) |
| `ARR_SEARCH_CONFIRM_ABOVE` | no | `10` | Searches or queue removals over this many items need confirmation |
| `ARR_SEARCH_COOLDOWN_MINUTES` | no | `60` | Skip items searched less than this many minutes ago (`0` = off) |
| `ARR_TIMEOUT` | no | `15` | HTTP timeout in seconds. Scans and interactive searches use higher values |
| `ARR_DOWNLOADS_PATH` | no | auto | Download folder **as Sonarr/Radarr see it**, used by `find_orphan_downloads`. If unset, it is detected from the queue and the import history |

\* At least Sonarr or Radarr is required. A service without both a URL **and** an API key is not registered, so its tools do not appear. Full URLs are used so reverse proxies and HTTPS work.

> **Docker / NAS.** If the port is assigned automatically (for example, Synology Container Manager in auto mode), it may change when the container is recreated. If `get_system_status` cannot connect, check the port, or better, pin it.

**API keys never go into the repository.** `.env` is in `.gitignore`.

## Usage

Typical conversations and the tools Claude usually picks:

| Question | Tools |
|---|---|
| "Why didn't it grab S03E04?" | `explain_search` → `grab_release` if you want a rejected one |
| "Why isn't it importing?" | `diagnose_import` → `check_paths` → `manual_import(matches=…)` |
| "Which downloads are stalled?" | `find_stalled_downloads` → `remove_from_queue(blocklist=true)` |
| "Would this release be an upgrade?" | `parse_release` |
| "What's stuck in the queue?" | `get_queue(only_problems=true)` |
| "Remove the `.exe` releases and search again" | `find_suspicious_releases` → `remove_from_queue(blocklist=true)` |
| "Which indexer fails the most this month?" | `get_indexer_stats(days=30)` |
| "What takes the most space?" | `library_report` |
| "Unmonitor every ended series that is complete" | `bulk_edit_preview` → `bulk_edit_apply` |
| "Which files don't follow my naming scheme?" | `preview_rename` → `rename_files` |
| "Add Severance in HD-1080p" | `add_series` (if profile or root folder are missing, it returns the options) |
| "Import what was left in downloads" | `find_orphan_downloads` → `manual_import(files=[…])` |

Searches, refreshes and imports are **asynchronous commands** in Sonarr/Radarr. The tool returns a `command_id` you can follow with `get_command_status`.

`explain_search` queries every indexer **live** (it is the same interactive search as the web UI). Use it for a specific episode or movie, not in a loop.

### Tools that change or delete things

- `remove_from_queue`: removes queue items. By default it also removes the task from the download client (`remove_from_client=true`). With `blocklist=true` the release is blocklisted and, unless `skip_redownload=true`, Sonarr/Radarr automatically search for another one.
- `manual_import`: imports specific files into the library. By default (`import_mode="auto"`) it copies/hardlinks while the download is seeding and moves otherwise. Replacing a file already in the library needs `allow_replace=true`.
- `grab_release`: sends a specific release to the download client even if it was rejected.
- `bulk_edit_apply`: changes many items at once; for several items it needs the token from `bulk_edit_preview`.
- `rename_files`: renames files on disk to match the naming settings.

Claude Desktop asks for permission the first time each tool is used. For these it is better not to choose "Always allow", so you can review each call. The two that delete also carry the MCP `destructiveHint` annotation.

## Development

```bash
python -m venv .venv
.venv/bin/pip install -e ".[dev]"        # Windows: .venv\Scripts\pip
.venv/bin/pytest                          # unit tests with respx (no network)
uvx ruff check arr_doctor tests scripts      # lint
python scripts/gen_tools_doc.py           # regenerates docs/TOOLS.md and docs/TOOLS.es.md (a test checks they are up to date)
```

**Against a real server** (read-only, uses `.env`):

```bash
python scripts/smoke.py              # calls every read-only tool and prints a summary
python scripts/smoke.py --verbose    # also prints each answer
python scripts/smoke.py --capture    # saves anonymized raw responses to scripts/captures/ (git-ignored)
```

`smoke.py` refuses to call any tool that is not annotated `readOnlyHint`, and skips `explain_search` because it queries the indexers.

**In Claude Desktop:** a manual checklist (does the model pick the right tools, respect confirmations, explain results?) is in [docs/testing/claude-desktop.md](docs/testing/claude-desktop.md).

**MCP Inspector:**

```bash
npx @modelcontextprotocol/inspector .venv/bin/python -m arr_doctor.server          # web UI
npx @modelcontextprotocol/inspector --cli .venv/bin/arr-doctor -e SONARR_URL=… -e SONARR_API_KEY=… --method tools/list
```

On Windows, replace `.venv/bin/python` with `.venv/Scripts/python.exe`.

### Layout

```
arr_doctor/
├── server.py         # FastMCP, conditional tool registration, main()
├── config.py         # Settings (pydantic-settings)
├── i18n.py           # English and Spanish messages
├── paths.py          # comparing POSIX / Windows / UNC paths from Sonarr/Radarr
├── formatting.py     # compacting API responses
├── clients/          # HTTP: base.py (errors, X-Api-Key), sonarr.py, radarr.py, prowlarr.py
└── tools/            # library, diagnostics, troubleshoot, maintenance, actions, indexers, common
tests/                # pytest + respx; fixtures/ with sample responses
scripts/              # smoke.py, gen_tools_doc.py
docs/                 # TOOLS (generated), DESIGN, ROADMAP — in English and Spanish
```

- Good practices and guardrails: [docs/GOOD_PRACTICES.md](docs/GOOD_PRACTICES.md).
- Design decisions and API details: [docs/DESIGN.md](docs/DESIGN.md).
- What's next, based on the Sonarr and Radarr issues: [docs/ROADMAP.md](docs/ROADMAP.md).
- Changes: [CHANGELOG.md](CHANGELOG.md).

## Status

All tools have unit tests (mocked HTTP) and the server has an end-to-end stdio test. On top of that, they were run against **a real Sonarr 4.0.16 and Radarr 6.2 on a Synology NAS** (real library, read-only plus a few approved changes) and against **disposable Docker containers** of Sonarr 4.0.20, Radarr 5.28 and 6.4.4, and Prowlarr 2.6.5 (empty libraries, every tool including writes):

| Block | Real NAS | Containers | Notes |
|---|---|---|---|
| Skeleton, `get_system_status` | ✅ | ✅ | stdio, MCP Inspector, readable errors |
| Library and diagnostics (read-only) | ✅ | ✅ | Every tool, Sonarr and Radarr |
| Troubleshooting (read-only) | ✅ | ✅ | On the NAS it found a real fake `.exe`, stalled downloads and orphaned files. `explain_search` ran in containers only (no indexers there) |
| Write actions | ✅ partly | ✅ | NAS: `refresh_item`, `remove_from_queue` with blocklist, `manual_import` (6 episodes). Containers: `add_series`/`add_movie`, `set_monitored`, all searches. `grab_release` only mocked (needs real indexers) |
| Maintenance | ✅ partly | ✅ | NAS: `library_report`, `preview_rename`. Containers: `bulk_edit_preview` / `bulk_edit_apply`, `test_download_clients`. `rename_files` apply only mocked (needs files on disk) |
| Prowlarr | ✅ | ✅ | NAS (Prowlarr 2.4.0, 11 indexers): every tool, including `test_indexers` and `set_indexer_enabled` (8 dead indexers disabled; credentials untouched) |
| Windows and Linux | ✅ | — | CI on both + a real Windows machine |
| Good-practice guardrails | ✅ | ✅ | |
| Roadmap low priority | — | — | Not started |

Testing against the real server found and fixed several issues mocks could not show (unknown queue items, stalled-download cases, imports reported as successful that had failed, long imports vs. client timeouts). The fixtures in `tests/fixtures/` still use made-up data shaped like the official OpenAPI schemas; they can be replaced with anonymized real responses (`smoke.py --capture`).

## Credits and license

Created by **Alexliam** ([@alexliam](https://x.com/alexliam)).

Inspired by [BerryKuipers/mcp_services_radarr_sonarr](https://github.com/BerryKuipers/mcp_services_radarr_sonarr). This is a new implementation that does **not** reuse its code.

[MIT](LICENSE) license.
