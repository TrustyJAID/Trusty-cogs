from .translate import Translate


__red_end_user_data_statement__ = "This cog does not persistently store data or metadata about users. However, this cog does pass user data to an external API for the purposes of analyzing and translating languages."


async def setup(bot):
    cog = Translate(bot)
    await cog.init()
    bot.add_cog(cog)
