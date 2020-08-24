from .eventposter import EventPoster


__red_end_user_data_statement__ = (
    "This cog stores User ID's for the purposes of tracking user created events."
)


async def setup(bot):
    cog = EventPoster(bot)
    bot.add_cog(cog)
