from .crabrave import CrabRave


def setup(bot):
    cog = CrabRave(bot)
    bot.add_cog(cog)
