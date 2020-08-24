from .core import Elements


__red_end_user_data_statement__ = (
    "This cog does not persistently store data or metadata about users."
)


def setup(bot):
    cog = Elements(bot)
    bot.add_cog(cog)
