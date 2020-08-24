from .runescape import Runescape


__red_end_user_data_statement__ = (
    "This cog may store User ID's linked with an external API name for the purposes of simplifying command usage."
    "Users may clear this saved information at any time by command."
)


def setup(bot):
    n = Runescape(bot)
    bot.add_cog(n)
