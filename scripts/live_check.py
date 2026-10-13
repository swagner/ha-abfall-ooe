"""Run the real client against umweltprofis.at and print the next dates.

Usage (names are matched case-insensitively as substrings):
    python scripts/live_check.py "Perg" "Perg" "Aisthofen" "1" ["4-wöchentlich"]
"""

from __future__ import annotations

import asyncio
import sys
from datetime import date
from pathlib import Path

import aiohttp

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components"))
# Import the modules directly so the package __init__ (which needs Home
# Assistant) is not executed.
import types  # noqa: E402

_pkg = types.ModuleType("abfall_ooe")
_pkg.__path__ = [str(Path(sys.path[0]) / "abfall_ooe")]
sys.modules["abfall_ooe"] = _pkg
from abfall_ooe.api import AbfallOoeClient, Location  # noqa: E402


def pick(choices: dict[str, str], query: str, what: str) -> str:
    exact = [k for k, v in choices.items() if v.lower() == query.lower()]
    hits = exact or [k for k, v in choices.items() if query.lower() in v.lower()]
    if not hits:
        sys.exit(f"No {what} matches {query!r}. Options: {sorted(choices.values())[:30]}")
    print(f"{what}: {choices[hits[0]]} ({hits[0]})")
    return hits[0]


async def main(district: str, city: str, street: str, number: str, interval: str | None) -> None:
    async with aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar()) as session:
        client = AbfallOoeClient(session)
        d = pick(await client.get_districts(), district, "district")
        c = pick(await client.get_cities(d), city, "city")
        s = pick(await client.get_streets(c), street, "street")
        h = pick(await client.get_house_numbers(s), number, "house number")
        intervals = await client.get_intervals(s, h)
        print("intervals:", intervals)
        i = pick(intervals, interval, "interval") if interval and intervals else None

        pickups = await client.get_pickups(Location(d, c, s, h), i)
        print(f"{len(pickups)} pickups, {pickups[0].date if pickups else '-'} .. "
              f"{pickups[-1].date if pickups else '-'}")
        today = date.today()
        nxt: dict[str, list[date]] = {}
        for p in pickups:
            if p.date >= today:
                nxt.setdefault(p.waste_type, []).append(p.date)
        for name, dates in nxt.items():
            print(f"  {name:<20} next {dates[0]}  then {[d.isoformat() for d in dates[1:4]]}")


if __name__ == "__main__":
    args = sys.argv[1:]
    if len(args) < 4:
        sys.exit(__doc__)
    asyncio.run(main(*args[:4], args[4] if len(args) > 4 else None))
