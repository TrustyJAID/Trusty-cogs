import json
from pathlib import Path

from .roletools import RoleTools

with open(Path(__file__).parent / "info.json") as fp:
    __red_end_user_data_statement__ = json.load(fp)["end_user_data_statement"]


async def setup(bot):
    cog = RoleTools(bot)
    await bot.add_cog(cog)
    if not await cog.config.slash_enabled():
        bot.tree.remove_command("role-tools")
