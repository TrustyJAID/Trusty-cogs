from .serverstats import ServerStats

def setup(bot):
	bot.add_cog(ServerStats(bot))