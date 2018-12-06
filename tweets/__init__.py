from .tweets import Tweets

def setup(bot):
    bot.add_cog(Tweets(bot))
