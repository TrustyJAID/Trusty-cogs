from .hue import Hue

def setup(bot):
    bot.add_cog(Hue(bot))