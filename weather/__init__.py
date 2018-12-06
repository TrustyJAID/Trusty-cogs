from .weather import Weather

def setup(bot):
    n = Weather(bot)
    bot.add_cog(n)