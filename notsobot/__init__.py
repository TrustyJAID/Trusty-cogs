from .notsobot import NotSoBot


def setup(bot):
    cog = NotSoBot(bot)
    bot.add_cog(cog)
