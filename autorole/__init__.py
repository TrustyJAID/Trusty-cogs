from .autorole import Autorole


def setup(bot):
    n = Autorole(bot)
    bot.add_cog(n)
    # bot.add_listener(n._roler, "on_member_join")
    # bot.add_listener(n._verify_json, "on_error")
