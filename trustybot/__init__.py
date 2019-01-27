from .trustybot import TrustyBot


def setup(bot):
    n = TrustyBot(bot)
    bot.add_cog(n)
