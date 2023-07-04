from datetime import datetime, timedelta, timezone
from typing import Optional

__all__ = [
    "RUNEDATE_EPOCH",
    "IMAGE_URL",
    "get_runedate",
    "name_to_image",
    "HEADERS",
]

RUNEDATE_EPOCH = datetime(year=2002, month=2, day=27, hour=0, tzinfo=timezone.utc)

IMAGE_URL = "https://runescape.wiki/w/Special:FilePath/"

HEADERS = {"User-Agent": f"Red-DiscordBot Trusty-cogs Runescape Cog"}


def get_runedate(date: Optional[datetime] = None) -> float:
    if date is None:
        date = datetime.now(timezone.utc)
    return (date - RUNEDATE_EPOCH).total_seconds() / (60 * 60 * 24)


def runedate_to_datetime(runedate: float) -> datetime:
    seconds = runedate * 60 * 60 * 24
    return RUNEDATE_EPOCH + timedelta(seconds=seconds)


def name_to_image(name: str) -> str:
    name = name.replace(" ", "_").replace("'", "")
    return f"{IMAGE_URL}{name}_detail.png"
