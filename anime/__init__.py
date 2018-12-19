from .anime import Anime

def setup(bot):
    bot.add_cog(Anime(bot))