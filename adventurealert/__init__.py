from .adventurealert import AdventureAlert


__red_end_user_data_statement__ = (
    "This cog stores discord User ID's for the purposes of mentioning the user on certain events."
    "Users may delete their own data with or without making a data request."
)


async def setup(bot):
    bot.add_cog(AdventureAlert(bot))
