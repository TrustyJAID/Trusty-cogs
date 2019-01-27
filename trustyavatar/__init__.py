from .trustyavatar import TrustyAvatar


def setup(bot):
    n = TrustyAvatar(bot)
    bot.add_cog(n)
