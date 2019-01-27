from .badges import Badges


def setup(bot):
    cog = Badges(bot)
    bot.add_cog(cog)
