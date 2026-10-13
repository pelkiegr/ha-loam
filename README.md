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
4. Search by zip code or trail name and pick a network. Repeat for each network.

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
| Modeled at (diagnostic) | timestamp of Loam's latest model run |

Conditions refresh every 30 minutes; Loam models them hourly.

## Development

```sh
uv run --python 3.13 --with pytest --with pytest-asyncio --with aiohttp pytest
```
