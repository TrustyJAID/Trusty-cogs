import json
from pathlib import Path

from .extendedmodlog import ExtendedModLog

with open(Path(__file__).parent / "info.json") as fp:
    __red_end_user_data_statement__ = json.load(fp)["end_user_data_statement"]


async def setup(bot):
    cog = ExtendedModLog(bot)
    await bot.add_cog(cog)
