import re
from typing import Tuple

import discord
from discord.ext.commands import BadArgument, Converter
from redbot.core import commands
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import humanize_list

_ = Translator("RoleTools", __file__)


_id_regex = re.compile(r"([0-9]{15,21})$")
_mention_regex = re.compile(r"<@!?([0-9]{15,21})>$")


class RawUserIds(Converter):
    # https://github.com/Cog-Creators/Red-DiscordBot/blob/V3/develop/redbot/cogs/mod/converters.py
    async def convert(self, ctx: commands.Context, argument: str) -> int:
        # This is for the hackban and unban commands, where we receive IDs that
        # are most likely not in the guild.
        # Mentions are supported, but most likely won't ever be in cache.

        if match := _id_regex.match(argument) or _mention_regex.match(argument):
            return int(match.group(1))

        raise BadArgument(_("{} doesn't look like a valid user ID.").format(argument))


class RoleHierarchyConverter(commands.RoleConverter):
    """Similar to d.py's RoleConverter but only returns if we have already
    passed our hierarchy checks.
    """

    async def convert(self, ctx: commands.Context, argument: str) -> discord.Role:
        if not ctx.guild.me.guild_permissions.manage_roles:
            raise BadArgument(_("I require manage roles permission to use this command."))
        if isinstance(ctx, discord.Interaction):
            author = ctx.user
        else:
            author = ctx.author
        try:
            role = await commands.RoleConverter().convert(ctx, argument)
        except commands.BadArgument:
            raise
        else:
            if getattr(role, "is_bot_managed", None) and role.is_bot_managed():
                raise BadArgument(
                    _(
                        "The {role} role is a bot integration role "
                        "and cannot be assigned or removed."
                    ).format(role=role.mention)
                )
            if getattr(role, "is_integration", None) and role.is_integration():
                raise BadArgument(
                    _(
                        "The {role} role is an integration role and cannot be assigned or removed."
                    ).fromat(role=role.mention)
                )
            if getattr(role, "is_premium_subscriber", None) and role.is_premium_subscriber():
                raise BadArgument(
                    _(
                        "The {role} role is a premium subscriber role and can only "
                        "be assigned or removed by Nitro boosting the server."
                    ).format(role=role.mention)
                )
            if role >= ctx.guild.me.top_role:
                raise BadArgument(
                    _(
                        "The {role} role is higher than my highest role in the discord hierarchy."
                    ).format(role=role.mention)
                )
            if role >= author.top_role and author.id != ctx.guild.owner_id:
                raise BadArgument(
                    _(
                        "The {role} role is higher than your "
                        "highest role in the discord hierarchy."
                    ).format(role=role.mention)
                )
        return role


class SelfRoleConverter(commands.RoleConverter):
    """Converts a partial role name into a role object that can actually be applied."""

    async def convert(self, ctx: commands.Context, argument: str) -> discord.Role:
        if not ctx.guild.me.guild_permissions.manage_roles:
            raise BadArgument(_("I require manage roles permission to use this command."))
        if isinstance(ctx, discord.Interaction):
            author = ctx.user
        else:
            author = ctx.author
        role = None
        try:
            role = await commands.RoleConverter().convert(ctx, argument)
        except commands.BadArgument:
            for roles in ctx.guild.roles:
                if roles.name.lower() == argument.lower():
                    role = roles
        if role is None:
            raise commands.RoleNotFound(argument)
        else:
            if role.is_bot_managed():
                raise BadArgument(
                    _(
                        "The {role} role is a bot integration role "
                        "and cannot be assigned or removed."
                    ).format(role=role.mention)
                )
            if role.is_integration():
                raise BadArgument(
                    _(
                        "The {role} role is an integration role and cannot be assigned or removed."
                    ).fromat(role=role.mention)
                )
            if role.is_premium_subscriber():
                raise BadArgument(
                    _(
                        "The {role} role is a premium subscriber role and can only "
                        "be assigned or removed by Nitro boosting the server."
                    ).format(role=role.mention)
                )
            if role >= ctx.guild.me.top_role:
                raise BadArgument(
                    _(
                        "The {role} role is higher than my highest role in the discord hierarchy."
                    ).format(role=role.mention)
                )
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


class ButtonStyleConverter(Converter):
    async def convert(self, ctx: commands.Context, argument: str) -> discord.ButtonStyle:
        available_styles = [
            i for i in dir(discord.ButtonStyle) if not i.startswith("_") and i != "try_value"
        ]
        if argument.lower() in available_styles:
            return getattr(discord.ButtonStyle, argument.lower())
        else:
            raise BadArgument(
                _("`{argument}` is not an available Style. Choose one from {styles}").format(
                    argument=argument, styles=humanize_list(available_styles)
                )
            )
