<img src="https://raw.githubusercontent.com/pelkiegr/ha-loam/main/custom_components/loam/brand/icon.png" alt="Loam" width="96" align="right">

# Loam Ride Conditions for Home Assistant

A Home Assistant custom integration that shows modeled mountain bike trail
conditions from [Loam](https://loamrideconditions.com/).

Loam is not affiliated with this project and has no public API. The integration
reads each trail network's public page, so it can stop working if Loam changes
its site.

## Install (HACS)

1. HACS → ⋮ → **Custom repositories** → add `https://github.com/pelkiegr/ha-loam`,
   category **Integration**.
2. Download **Loam Ride Conditions**, then restart Home Assistant.
3. Settings → Devices & Services → **Add integration** → **Loam Ride Conditions**.
4. Search by zip code or trail name and tick one or more networks.

Only networks with a public page on loamrideconditions.com can be added; some
networks shown in the Loam app are app-only.

## Entities

Each trail network is a device with:

| Entity | Example |
| --- | --- |
| Status (`sensor`, enum) | `prime`, `dry`, `dusty`, `caution`, `stay_off`, `frozen` |
| Rideable (`binary_sensor`) | on for prime, dry, dusty |
| Outlook | Expected rideable in ~1 hour |
| Note | No significant rain before then. |
| Last rain | 0.9″ of rain, 11h ago |
| Dryness | 83 % (Loam's 0–1 drying model as a percentage) |
| Next change | when the next confirmed status change is forecast; `to_status` attribute |
| Modeled at (diagnostic) | timestamp of Loam's latest model run |

Conditions refresh every 30 minutes; Loam models them hourly.

## Dashboard cards

The integration ships two cards and loads them automatically. No extra
resource or HACS frontend install is needed. Add them from the dashboard card
picker ("Loam trail" and "Loam trails") or in YAML:

```yaml
type: custom:loam-trail-card
entity: sensor.green_mountain_park_status
days_back: 3          # optional, history shown before "now" (1–10)
```

```yaml
type: custom:loam-trails-card
title: Trail conditions   # optional
days_back: 3              # optional, history in the expanded chart
sort: rideable            # optional: config (as listed, default), rideable, name
entities:
  - sensor.green_mountain_park_status
  - sensor.dakota_ridge_status
```

Any entity of a trail works; the card looks up the trail it belongs to.

![Loam cards](https://raw.githubusercontent.com/pelkiegr/ha-loam/main/docs/cards.png)

Tap a row in the trails card to expand that trail's facts and drying chart
inline; tap again to collapse it.

![Expanded trails card](https://raw.githubusercontent.com/pelkiegr/ha-loam/main/docs/trails-card.png)

The trail card's chart shows hourly modeled dryness colored by status, with
the forecast dashed, hourly rain as blue bars, and each day's high and rain
total underneath. Click the trail card's name to open its more-info dialog.

## Development

```sh
uv run --python 3.13 --with pytest --with pytest-asyncio --with aiohttp pytest
```
