from .dev import Dev


def setup(bot):
    bot.add_cog(Dev(bot))
