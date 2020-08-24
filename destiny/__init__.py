from .destiny import Destiny


__red_end_user_data_statement__ = "This cog stores User ID's linked to an external API token for the purposes of granting OAuth access and information about the external API for the user."


def setup(bot):
    bot.add_cog(Destiny(bot))
