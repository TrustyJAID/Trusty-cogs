from redbot.core.bot import Red
from .reportspin import Reports


def setup(bot: Red):
    bot.add_cog(Reports(bot))
