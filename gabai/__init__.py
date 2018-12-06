from .gabai import Gabai

def setup(bot):
    n = Gabai(bot)
    bot.add_cog(n)