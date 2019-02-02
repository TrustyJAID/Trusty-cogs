from .core import Elements


def setup(bot):
    cog = Elements(bot)
    bot.add_cog(cog)
