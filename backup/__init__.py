from .backup import Backup


__red_end_user_data_statement__ = "This cog extracts messages including user data and saves locally on the bots harddrive. This data is meant for personal use only and not recommended to be stored indefinitely."


def setup(bot):
    bot.add_cog(Backup(bot))
