from .cleverbot import Cleverbot

def setup(bot):
    cog = Cleverbot(bot)
    bot.add_cog(cog)