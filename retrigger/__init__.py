from .retrigger import ReTrigger

def setup(bot):
    n = ReTrigger(bot)
    bot.add_cog(n)

