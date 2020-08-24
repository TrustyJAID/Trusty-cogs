from .weather import Weather


__red_end_user_data_statement__ = (
    "This cog may store User ID's for the purposes of setting default preferred temperature units."
)


def setup(bot):
    n = Weather(bot)
    bot.add_cog(n)
