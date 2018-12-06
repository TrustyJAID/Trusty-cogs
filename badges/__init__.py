from .badges import Badges
from redbot.core import data_manager

def setup(bot):
    cog = Badges(bot)
    data_manager.load_bundled_data(cog, __file__)
    bot.add_cog(cog)