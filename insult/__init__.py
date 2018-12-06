from .insult import Insult

def setup(bot):
    n = Insult(bot)
    bot.add_cog(n)
