from .notsobot import NotSoBot
from redbot.core import data_manager

def setup(bot):
    cog = NotSoBot(bot)
    data_manager.load_bundled_data(cog, __file__)
    bot.add_cog(cog)