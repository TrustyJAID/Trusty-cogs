from typing import Union

import discord
from redbot.core import commands
from redbot.core.i18n import Translator

from .starboard_entry import StarboardEntry

_ = Translator("Starboard", __file__)


class StarboardExists(commands.Converter):
    async def convert(self, ctx: commands.Context, argument: str) -> StarboardEntry:
        cog = ctx.cog
        guild = ctx.guild
        if guild.id not in cog.starboards:
            raise commands.BadArgument(_("There are no starboards setup on this server!"))
        try:
            starboard = cog.starboards[guild.id][argument.lower()]
        except KeyError:
            raise commands.BadArgument(
                _("There is no starboard named {name}").format(name=argument)
            )
        return starboard


class RealEmoji(commands.EmojiConverter):
    async def convert(self, ctx: commands.Context, argument: str) -> Union[discord.Emoji, str]:
        try:
            emoji = await super().convert(ctx, argument)
        except commands.BadArgument:
            try:
                await ctx.message.add_reaction(argument)
            except discord.HTTPException:
                raise commands.EmojiNotFound(argument)
            else:
                emoji = argument
        return emoji
