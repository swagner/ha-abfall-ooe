# Abfall OÖ (Umweltprofis) for Home Assistant

Custom integration that reads the pickup calendar
("Wann wird mein Abfall abgeholt?") from [umweltprofis.at](https://www.umweltprofis.at/)
for addresses in Upper Austria and exposes the next pickup date for every waste type.

## Installation

**HACS:** in HACS open the ⋮ menu → *Custom repositories*, add
`https://github.com/swagner/ha-abfall-ooe` with type *Integration*, then install
*Abfall OÖ (Umweltprofis)* and restart Home Assistant.

**Manual:** copy `custom_components/abfall_ooe` into the `custom_components` folder of your
Home Assistant config directory and restart Home Assistant.

Then go to *Settings → Devices & services → Add integration → Abfall OÖ*.

## Configuration

The setup dialog follows the same cascade as the website:

1. **Bezirk** (district)
2. **Gemeinde** (municipality)
3. **Straße** (street)
4. **Hausnummer** (house number)
5. **Abfuhrintervall** (pickup interval), only shown if the address offers a choice,
   typically Restabfall weekly / 2-weekly / 4-weekly / 6-weekly. It can be changed later
   via *Configure* on the integration.

Each address is added once; add the integration again for more addresses.

## Entities

Per address (grouped as one device):

| Entity | State | Attributes |
|---|---|---|
| `sensor.<address>_<waste type>` (one per type, e.g. Restabfall, Bioabfall, Gelber Sack, Altpapier) | next pickup date | `days_until`, `upcoming` (next 5 dates), `interval` |
| `sensor.<address>_next_pickup` | next pickup date of any type | `days_until`, `waste_types` collected that day |
| `calendar.<address>` | all pickups as all-day events | |

Data is refreshed every 12 hours; the "next" values roll over at midnight.

Example template for a reminder automation:

```yaml
{{ state_attr('sensor.aisthofen_1_perg_next_pickup', 'days_until') == 1 }}
```

Requires Home Assistant 2025.8 or newer.

## Limitations

- The site has no public API; this integration replays the website's form, so markup changes
  on umweltprofis.at can break it.
- The statutory cities Linz, Wels and Steyr list streets but publish no pickup dates on
  umweltprofis.at; setup aborts with a message for those addresses.
- Interval and address are stored by the site's internal IDs and by name; if the IDs change
  when the operator publishes new data, the integration falls back to the names.
- Only the waste types the website lists for an address appear (e.g. some Linz-Land
  municipalities show no Restabfall dates).

## Development

Tests use `pytest-homeassistant-custom-component` (Linux/macOS/WSL only):

```bash
pip install -r requirements_test.txt
pytest
```

`scripts/live_check.py` queries the real website without Home Assistant.

## Releasing

Bump `version` in `custom_components/abfall_ooe/manifest.json`, commit, and publish a GitHub
release with a matching tag (e.g. `v0.1.0`); HACS offers releases as versions.

## License

MIT
