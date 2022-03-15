from .roletools import RoleTools


async def setup(bot):
    cog = RoleTools(bot)
    await bot.add_cog(cog)
    await cog.initalize()
