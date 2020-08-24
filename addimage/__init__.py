from .addimage import AddImage


__red_end_user_data_statement__ = (
    "This cog stores attachements uploaded by users for the purposes of creating custom commands to send uploaded attachments."
    "Users may delete their own data with or without making a data request."
)


async def setup(bot):
    n = AddImage(bot)
    await n.initialize()
    bot.add_cog(n)
