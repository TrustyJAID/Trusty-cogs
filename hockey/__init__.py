from .hockey import Hockey


__red_end_user_data_statement__ = (
    "This cog does not persistently store data or metadata about users."
)


async def setup(bot):
    cog = Hockey(bot)
    await cog.initialize_pickems()
    bot.add_cog(cog)
