from .mock import Mock

def setup(bot):
    bot.add_cog(Mock(bot))
