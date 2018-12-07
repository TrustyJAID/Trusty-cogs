from .extendedmodlog import ExtendedModLog

def setup(bot):
    bot.add_cog(ExtendedModLog(bot))