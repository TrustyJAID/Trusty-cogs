import re
import discord
from typing import Tuple
from discord.ext.commands import BadArgument, Converter

from redbot.core import commands


class RoleHierarchyConverter(commands.RoleConverter):
    async def convert(self, ctx: commands.Context, argument: str) -> discord.Role:

        try:
            role = await commands.RoleConverter().convert(ctx, argument)
        except commands.BadArgument:
            raise
        if ctx.author.id == ctx.guild.owner.id:
            return role
        else:
            if role.position >= ctx.me.top_role.position:
                raise BadArgument("That role is higher than my highest role in the discord hierarchy.")
            if role.position >= ctx.author.top_role.position:
                raise BadArgument("That role is higher than your own in the discord hierarchy.")
        return role


class RoleEmojiConverter(Converter):
    async def convert(self, ctx: commands.Context, argument: str) -> Tuple[discord.Role, str]:
        arg_split = re.split(r";|,|\||-", argument)
        try:
            role, emoji = arg_split
        except Exception:
            raise BadArgument(
                "Role Emoji must be a role followed by an emoji separated by either `;`, `,`, `|`, or `-`."
            )
        custom_emoji = None
        try:
            custom_emoji = await commands.PartialEmojiConverter().convert(ctx, emoji.strip())
        except commands.BadArgument:
            pass
        if not custom_emoji:
            try:
                await ctx.message.add_reaction(str(emoji.strip()))
                custom_emoji = str(emoji)
            except discord.errors.HTTPException:
                raise BadArgument("That does not look like a valid emoji.")
        try:
            role = await RoleHierarchyConverter().convert(ctx, role.strip())
        except commands.BadArgument:
            raise
        return role, custom_emoji
