from .qposts import QPosts


def setup(bot):
    bot.add_cog(QPosts(bot))
