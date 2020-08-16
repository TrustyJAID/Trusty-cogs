from .retrigger import ReTrigger


__red_end_user_data_statement__ = (
    "This cog may store attachments and command information provided by Users for the purposes of performing actions."
    "Some User ID's may be stored in the bots logging information."
    "Users may delete their own data with or without making a data request."
)


async def setup(bot):
    cog = ReTrigger(bot)
    await cog.initialize()
    bot.add_cog(cog)
