from .imagemaker import ImageMaker


def setup(bot):
    cog = ImageMaker(bot)
    bot.add_cog(cog)
