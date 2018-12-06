from .emojireact import EmojiReactions

def setup(bot):
    bot.add_cog(EmojiReactions(bot))
