from .spoiler import Spoiler


def setup(bot):
    bot.add_cog(Spoiler(bot))
