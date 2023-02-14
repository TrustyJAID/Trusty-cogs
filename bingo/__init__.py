from .bingo import Bingo


async def setup(bot):
    cog = Bingo(bot)
    await bot.add_cog(cog)
