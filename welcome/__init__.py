from .welcomeleave import WelcomeLeave


def setup(bot):
    n = WelcomeLeave(bot)
    bot.add_cog(n)
