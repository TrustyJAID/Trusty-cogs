from .compliment import Compliment


__red_end_user_data_statement__ = (
    "This cog does not persistently store data or metadata about users."
)


def setup(bot):
    n = Compliment(bot)
    bot.add_cog(n)
