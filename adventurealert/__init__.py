from .adventurealert import AdventureAlert


async def setup(bot):
    bot.add_cog(AdventureAlert(bot))
