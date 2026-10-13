# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Home Assistant custom integration (`custom_components/abfall_ooe`, domain `abfall_ooe`) that scrapes waste pickup dates for Upper Austrian addresses from umweltprofis.at and exposes one date sensor per waste type, a "next pickup" sensor and a calendar entity.

## Commands

The Home Assistant test harness imports `fcntl` and does **not** run on Windows. Run tests in WSL (Ubuntu) using the Linux venv at `~/.venvs/abfall_ooe` (Python 3.14, `pytest-homeassistant-custom-component`):

```powershell
wsl.exe -d Ubuntu --cd /mnt/e/dev/HA/abfall_ooe -- ~/.venvs/abfall_ooe/bin/python -m pytest -q -p no:cacheprovider
# single test
wsl.exe -d Ubuntu --cd /mnt/e/dev/HA/abfall_ooe -- ~/.venvs/abfall_ooe/bin/python -m pytest -q -p no:cacheprovider tests/test_sensor.py::test_calendar
```

Call `wsl.exe` from PowerShell, not Git Bash: Git Bash rewrites `/mnt/...` paths and expands `$VARS` before WSL sees them. To recreate the venv: `uv venv ~/.venvs/abfall_ooe --python 3.14 && uv pip install --python ~/.venvs/abfall_ooe/bin/python -r requirements_test.txt`.

Live check against the real website (no Home Assistant needed; arguments are substring matches on the dropdown labels):

```powershell
wsl.exe -d Ubuntu --cd /mnt/e/dev/HA/abfall_ooe -- ~/.venvs/abfall_ooe/bin/python scripts/live_check.py Perg Perg Aisthofen 1 "4-wöchentlich"
```

hassfest (Home Assistant's manifest/translation validator, also run in CI) uses a shallow HA core checkout at `~/.cache/ha-core-2026.10.1` in WSL. Run it from inside that checkout with the venv's `bin` on `PATH` (it needs `ruff`): `python -m script.hassfest --integration-path /mnt/e/dev/HA/abfall_ooe/custom_components/abfall_ooe`.

CI (`.github/workflows/validate.yml`) runs the HACS action (with the `brands` check ignored), hassfest and pytest.

## Release / HACS

Published as a HACS custom repository at `swagner/ha-abfall-ooe`. To release, bump `version` in `manifest.json` and publish a GitHub release tagged `v<version>`. `hacs.json` declares the minimum HA version (2025.8, needed for `OptionsFlowWithReload`).

## How the site works (no public API)

umweltprofis.at is a TYPO3/Extbase site. `api.py` replays the browser flow:

1. GET the calendar page (`CALENDAR_PAGE`, the Linz-Land page, which works for every district). It contains the `ajax*Url` lookup endpoints as inline JS variables, signed with a `cHash`. The `%23%23%23REPLACE%23%23%23` / `REPLACE2` placeholders can be substituted without breaking the hash, so these URLs are read from the page at runtime rather than hardcoded.
2. Lookups (`ajaxGetCities`/`Streets`/`HouseNumbers`/`Intervals`) return JSON `[{"uid", "title"}]`. Districts come from the `#district-selector` dropdown on the page.
3. POST the IDs to the `#choose-location-form` action together with all hidden Extbase fields (`__referrer`, `__trustedProperties`). The location is stored in the **server-side session** (`fe_typo_user` cookie). The response may be `redirect: <url>`, which is followed.
4. GET the calendar again. Rows are parallel `div`s `row1-N` (type name + `waste-type-tNNN` + `interval-type-oNNN` classes), `row2-N` (date `DD.MM.YYYY`) and `row3-N` (interval label).

Consequences:
- Every client needs its **own cookie jar** (`create_client` in `__init__.py`); never use HA's shared session.
- **Interval filtering** (`parser.filter_pickups`): types with several schedules (usually Restabfall: weekly, 2-, 4- or 6-weekly) list a row for every variant. Each type's `#type-selector-tNNN` dropdown says which `oNNN` intervals it offers. Rows are kept only for the user's interval; single-schedule types are left untouched.
- The `oNNN` interval IDs and the city/street/house-number UIDs are database keys that may change when the operator imports new data. The entry therefore stores the labels too (`<key>_name`, including `interval_name`). `filter_pickups` falls back to matching the interval by label. If a fetch returns no pickups, `AbfallOoeCoordinator._async_relocate` looks the address up again by name and updates the entry data and unique ID.
- Linz, Wels and Steyr return streets but no calendar rows. The config flow aborts with `no_pickups`.

## Code layout

- `parser.py`: pure regex parsing, no HA/aiohttp imports (keeps it unit-testable and importable by `scripts/live_check.py`, which loads the package without running `__init__.py`).
- `api.py`: aiohttp client; raises `AbfallOoeConnectionError` / `AbfallOoeParseError`.
- `coordinator.py`: `DataUpdateCoordinator[list[Pickup]]`, refreshed every 12 h; stored in `entry.runtime_data`. The interval comes from `entry.options` first (options flow), then `entry.data`. `entry.data` is rewritten at runtime by `_async_relocate`, so don't add a config-entry update listener: it would reload the entry mid-refresh. The options flow is an `OptionsFlowWithReload` instead.
- `__init__.py`: also schedules a midnight `async_update_listeners()` so the "next" dates roll over without a refetch.
- `sensor.py`: waste-type sensors are created dynamically from the data (unique ID `<entry_id>_<tNNN>`); new types appearing later are added via a coordinator listener.
- `config_flow.py`: steps `user` (district) → `city` → `street` → `house_number` → `interval` (skipped if none). Unique ID is the house-number UID. Entry data stores IDs plus `<key>_name` labels and the available `intervals` map, which the options flow uses.

Translations: `strings.json` is the source; keep `translations/en.json` identical to it and update `translations/de.json` alongside.
