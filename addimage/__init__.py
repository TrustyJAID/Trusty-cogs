from .addimage import AddImage


async def setup(bot):
    n = AddImage(bot)
    await n.initialize()
    bot.add_cog(n)
