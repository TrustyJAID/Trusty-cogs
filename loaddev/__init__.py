from .loaddev import LoadDev


__red_end_user_data_statement__ = (
    "This cog does not persistently store data or metadata about users."
)


def setup(bot):
    cog = LoadDev(bot)
    bot.add_cog(cog)
