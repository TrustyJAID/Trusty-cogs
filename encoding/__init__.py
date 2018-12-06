from .encoding import Encoding

def setup(bot):
    n = Encoding(bot)
    bot.add_cog(n)