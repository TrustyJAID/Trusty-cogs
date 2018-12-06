from .addimage import AddImage

def setup(bot):
    n = AddImage(bot)
    bot.add_cog(n)