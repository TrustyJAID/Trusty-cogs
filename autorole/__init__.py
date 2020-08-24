from .autorole import Autorole


__red_end_user_data_statement__ = (
    "This cog does not persistently store data or metadata about users."
)


def setup(bot):
    n = Autorole(bot)
    bot.add_cog(n)
    # bot.add_listener(n._roler, "on_member_join")
    # bot.add_listener(n._verify_json, "on_error")
