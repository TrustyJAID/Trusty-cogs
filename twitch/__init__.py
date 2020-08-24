from .twitch import Twitch


__red_end_user_data_statement__ = "This cog stores User ID's linked to an external API name for the purposes of tracking information from the external API."


async def setup(bot):
    cog = Twitch(bot)
    await cog.initialize()
    bot.add_cog(cog)
