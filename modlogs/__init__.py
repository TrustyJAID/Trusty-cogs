from .modlogs import ModLogs

def setup(bot):
    bot.add_cog(ModLogs(bot))