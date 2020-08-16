from .stickyroles import StickyRoles


__red_end_user_data_statement__ = (
    "This cog stores User ID's for the purposes of re-assigning roles when the user re-joins a server."
    "User ID's may be stored in the bots log information."
)


def setup(bot):
    bot.add_cog(StickyRoles(bot))
