from .welcome import Welcome


def setup(bot):
    n = Welcome(bot)
    bot.add_cog(n)
