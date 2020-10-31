import re
import discord
from typing import Tuple
from discord.ext.commands import BadArgument, Converter
from redbot.core.i18n import Translator

from redbot.core import commands

_ = Translator("RoleTools", __file__)


_id_regex = re.compile(r"([0-9]{15,21})$")
_mention_regex = re.compile(r"<@!?([0-9]{15,21})>$")


class RawUserIds(Converter):
    # https://github.com/Cog-Creators/Red-DiscordBot/blob/V3/develop/redbot/cogs/mod/converters.py
    async def convert(self, ctx, argument):
        # This is for the hackban and unban commands, where we receive IDs that
        # are most likely not in the guild.
        # Mentions are supported, but most likely won't ever be in cache.

        if match := _id_regex.match(argument) or _mention_regex.match(argument):
            return int(match.group(1))

        raise BadArgument(_("{} doesn't look like a valid user ID.").format(argument))


class RoleHierarchyConverter(commands.RoleConverter):
    async def convert(self, ctx: commands.Context, argument: str) -> discord.Role:
        if not ctx.me.guild_permissions.manage_roles:
            raise BadArgument(_("I require manage roles permission to use this command."))
        try:
            role = await commands.RoleConverter().convert(ctx, argument)
        except commands.BadArgument:
            raise
        if ctx.author.id == ctx.guild.owner.id:
            return role
        else:
            if role.position >= ctx.me.top_role.position:
                raise BadArgument(
                    _("That role is higher than my highest role in the discord hierarchy.")
                )
            if role.position >= ctx.author.top_role.position:
                raise BadArgument(_("That role is higher than your own in the discord hierarchy."))
        return role


class RoleEmojiConverter(Converter):
    async def convert(self, ctx: commands.Context, argument: str) -> Tuple[discord.Role, str]:
        arg_split = re.split(r";|,|\||-", argument)
        try:
            role, emoji = arg_split
        except Exception:
            raise BadArgument(
                _(
                    "Role Emoji must be a role followed by an "
                    "emoji separated by either `;`, `,`, `|`, or `-`."
                )
            )
        custom_emoji = None
        try:
            custom_emoji = await commands.PartialEmojiConverter().convert(ctx, emoji.strip())
        except commands.BadArgument:
            pass
        if not custom_emoji:
            try:
                await ctx.message.add_reaction(str(emoji.strip()))
                custom_emoji = emoji
            except discord.errors.HTTPException:
                raise BadArgument(_("That does not look like a valid emoji."))
        try:
            role = await RoleHierarchyConverter().convert(ctx, role.strip())
        except commands.BadArgument:
            raise
        return role, custom_emoji
