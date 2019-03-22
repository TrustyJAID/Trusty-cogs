from .fenrir import Fenrir


def setup(bot):
    bot.add_cog(Fenrir(bot))
