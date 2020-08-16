from .chatter import Chatter


__red_end_user_data_statement__ = (
    "This cog extracts user messages for the purposes of training the chat response algorithm."
)


def setup(bot):
    bot.add_cog(Chatter(bot))
