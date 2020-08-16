from .cleverbot import Cleverbot


__red_end_user_data_statement__ = "This cog does not persistently store data or metadata about users. However, this cog does pass user data to an external API for the purposes of simulated conversation responses."


def setup(bot):
    cog = Cleverbot(bot)
    bot.add_cog(cog)
