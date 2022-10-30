import json
from asyncio import create_task
from pathlib import Path

from .spotify import Spotify

DASHBOARD_COG_NAME = "Dashboard"
DASHBOARD_COG_FOLDER = "dashboard"


with open(Path(__file__).parent / "info.json") as fp:
    __red_end_user_data_statement__ = json.load(fp)["end_user_data_statement"]


async def dashboard_deferred_load(bot):
    if DASHBOARD_COG_FOLDER in await bot._config.packages() and not bot.get_cog(
        DASHBOARD_COG_NAME
    ):
        await bot.wait_for("cog_add", check=lambda c: c.qualified_name == DASHBOARD_COG_NAME)
    cog = Spotify(bot)
    bot.add_cog(cog)


def setup(bot):
    create_task(dashboard_deferred_load(bot))
