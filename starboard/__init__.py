from .starboard import Starboard


__red_end_user_data_statement__ = "This stores message information from Users for the purposes of tracking reactions to the message."


async def setup(bot):
    cog = Starboard(bot)
    await cog.initialize()
    bot.add_cog(cog)
