import logging
import json

from pathlib import Path

from .retrigger import ReTrigger


with open(Path(__file__).parent / "info.json") as fp:
    __red_end_user_data_statement__ = json.load(fp)["end_user_data_statement"]

log = logging.getLogger("red.trusty-cogs.retrigger")


async def setup(bot):
    cog = ReTrigger(bot)
    try:
        await cog.initialize()
    except Exception:
        log.exception("Error loading ReTrigger")
        raise
    bot.add_cog(cog)
