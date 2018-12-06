from .runescape import Runescape

def setup(bot):
    n = Runescape(bot)
    bot.add_cog(n)