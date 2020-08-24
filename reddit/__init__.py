from .reddit import Reddit


__red_end_user_data_statement__ = (
    "This cog does not persistently store data or metadata about users."
)


async def setup(bot):
    cog = Reddit(bot)
    bot.add_cog(cog)
