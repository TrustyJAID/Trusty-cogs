from .hockey import Hockey


__red_end_user_data_statement__ = (
    "This cog stores User ID's for the purposes of tracking votes in pickems."
)


async def setup(bot):
    cog = Hockey(bot)
    await cog.initialize_pickems()
    bot.add_cog(cog)
