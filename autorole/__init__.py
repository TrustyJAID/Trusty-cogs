import json
from pathlib import Path

from .autorole import Autorole

with open(Path(__file__).parent / "info.json") as fp:
    __red_end_user_data_statement__ = json.load(fp)["end_user_data_statement"]


def setup(bot):
    n = Autorole(bot)
    bot.add_cog(n)
    # bot.add_listener(n._roler, "on_member_join")
    # bot.add_listener(n._verify_json, "on_error")
