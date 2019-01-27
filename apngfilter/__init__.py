from .apngfilter import APNGFilter


def setup(bot):
    cog = APNGFilter(bot)
    bot.add_cog(cog)
