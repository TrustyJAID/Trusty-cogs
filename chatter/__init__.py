from .chatter import Chatter

def setup(bot):
    bot.add_cog(Chatter(bot))