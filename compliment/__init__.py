from .compliment import Compliment

def setup(bot):
    n = Compliment(bot)
    bot.add_cog(n)
