from .backup import Backup


def setup(bot):
    bot.add_cog(Backup(bot))
