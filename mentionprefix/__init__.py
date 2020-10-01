import asyncio
import json
from pathlib import Path

from .mentionprefix import MentionPrefix

with open(Path(__file__).parent / "info.json") as fp:
    __red_end_user_data_statement__ = json.load(fp)["end_user_data_statement"]


async def setup(bot):
    cog = MentionPrefix(bot)
    bot.add_cog(cog)
    asyncio.create_task(cog.initialize())
