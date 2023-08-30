from __future__ import annotations

import re
from typing import List, Optional, Tuple, Union

import discord
from discord.ext.commands import BadArgument, Converter
from red_commons.logging import getLogger
from redbot.core import commands
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import humanize_list

from .components import ButtonRole, SelectRole, SelectRoleOption

log = getLogger("red.Trusty-cogs.RoleTools")
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


class ButtonRoleConverter(discord.app_commands.Transformer):
    @classmethod
    async def convert(cls, ctx: commands.Context, argument: str) -> ButtonRole:
        cog = ctx.bot.get_cog("RoleTools")
        async with cog.config.guild(ctx.guild).buttons() as buttons:
            if argument.lower() in buttons:
                # log.debug("%s Button exists", argument.lower())
                button_data = buttons[argument.lower()]
                role_id = button_data["role_id"]
                emoji = button_data["emoji"]
                if emoji is not None:
                    emoji = discord.PartialEmoji.from_str(emoji)
                button = ButtonRole(
                    style=button_data["style"],
                    label=button_data["label"],
                    emoji=emoji,
                    custom_id=f"{argument.lower()}-{role_id}",
                    role_id=role_id,
                    name=argument.lower(),
                )
                button.replace_label(ctx.guild)
                return button
            else:
                raise commands.BadArgument(
                    _("Button with name `{name}` does not seem to exist.").format(
                        name=argument.lower()
                    )
                )

    async def autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> List[discord.app_commands.Choice]:
        guild = interaction.guild
        cog = interaction.client.get_cog("RoleTools")
        select_options = await cog.config.guild(guild).buttons()
        supplied_options = ""
        new_option = ""
        for sup in current.split(" "):
            if sup in list(select_options.keys()):
                supplied_options += f"{sup} "
            else:
                new_option = sup

        ret = [
            discord.app_commands.Choice(
                name=f"{supplied_options} {g}", value=f"{supplied_options} {g}"
            )
            for g in list(select_options.keys())
            if new_option in g
        ]
        if supplied_options:
            ret.insert(
                0, discord.app_commands.Choice(name=supplied_options, value=supplied_options)
            )
        return ret


class SelectOptionRoleConverter(discord.app_commands.Transformer):
    @classmethod
    async def convert(cls, ctx: commands.Context, argument: str) -> SelectRoleOption:
        cog = ctx.bot.get_cog("RoleTools")
        async with cog.config.guild(ctx.guild).select_options() as select_options:
            if argument.lower() in select_options:
                select_data = select_options[argument.lower()]
                role_id = select_data["role_id"]
                emoji = select_data["emoji"]
                if emoji and len(emoji) > 20:
                    emoji = discord.PartialEmoji.from_str(emoji)
                label = select_data["label"]
                description = select_data["description"]
                select_role = SelectRoleOption(
                    name=argument.lower(),
                    label=label,
                    value=f"RTSelect-{argument.lower()}-{role_id}",
                    role_id=role_id,
                    description=description,
                    emoji=emoji,
                )
                return select_role
            else:
                raise commands.BadArgument(
                    _("Select Option with name `{name}` does not seem to exist.").format(
                        name=argument.lower()
                    )
                )

    async def autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> List[discord.app_commands.Choice]:
        guild = interaction.guild
        select_options = await self.config.guild(guild).select_options()
        supplied_options = ""
        new_option = ""
        for sup in current.split(" "):
            if sup in list(select_options.keys()):
                supplied_options += f"{sup} "
            else:
                new_option = sup

        ret = [
            discord.app_commands.Choice(
                name=f"{supplied_options} {g}", value=f"{supplied_options} {g}"
            )
            for g in list(select_options.keys())
            if new_option in g
        ]
        if supplied_options:
            ret.insert(
                0, discord.app_commands.Choice(name=supplied_options, value=supplied_options)
            )
        return ret


class SelectRoleConverter(discord.app_commands.Transformer):
    @classmethod
    async def convert(cls, ctx: commands.Context, argument: str) -> SelectRole:
        cog = ctx.bot.get_cog("RoleTools")
        async with cog.config.guild(ctx.guild).select_menus() as select_menus:
            # log.debug(argument)
            if argument.lower() in select_menus:
                select_data = select_menus[argument.lower()]
                options = []
                all_option_data = await cog.config.guild(ctx.guild).select_options()
                for option_name in select_data["options"]:
                    try:
                        option_data = all_option_data[option_name]
                        role_id = option_data["role_id"]
                        description = option_data["description"]
                        emoji = option_data["emoji"]
                        if emoji is not None:
                            emoji = discord.PartialEmoji.from_str(emoji)
                        label = option_data["label"]
                        option = SelectRoleOption(
                            name=option_name,
                            label=label,
                            value=f"RTSelect-{option_name}-{role_id}",
                            role_id=role_id,
                            description=description,
                            emoji=emoji,
                        )
                        options.append(option)
                    except KeyError:
                        log.exception("Somehow this errored")
                        continue
                sr = SelectRole(
                    name=argument.lower(),
                    custom_id=f"RTSelect-{argument.lower()}-{ctx.guild.id}",
                    min_values=select_data["min_values"],
                    max_values=select_data["max_values"],
                    placeholder=select_data["placeholder"],
                    options=options,
                )
                sr.update_options(ctx.guild)
                return sr
            else:
                raise commands.BadArgument(
                    _("Select Option with name `{name}` does not seem to exist.").format(
                        name=argument.lower()
                    )
                )

    async def autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> List[discord.app_commands.Choice]:
        guild = interaction.guild
        cog = interaction.client.get_cog("RoleTools")
        select_options = await cog.config.guild(guild).select_menus()
        supplied_options = ""
        new_option = ""
        for sup in current.split(" "):
            if sup in list(select_options.keys()):
                supplied_options += f"{sup} "
            else:
                new_option = sup

        ret = [
            discord.app_commands.Choice(
                name=f"{supplied_options} {g}", value=f"{supplied_options} {g}"
            )
            for g in list(select_options.keys())
            if new_option in g
        ]
        if supplied_options:
            ret.insert(
                0, discord.app_commands.Choice(name=supplied_options, value=supplied_options)
            )
        return ret


class SelectMenuFlags(commands.FlagConverter, case_insensitive=True):
    min_values: Optional[commands.Range[int, 0, 25]] = commands.flag(
        name="min", aliases=["min_values"], default=None
    )
    max_values: Optional[commands.Range[int, 0, 25]] = commands.flag(
        name="max", aliases=["max_values"], default=None
    )
    placeholder: Optional[str] = commands.flag(name="placeholder", default=None)


class SelectOptionFlags(commands.FlagConverter, case_insensitive=True):
    label: commands.Range[str, 1, 100] = commands.flag(name="label", default=None)
    description: Optional[commands.Range[str, 0, 100]] = commands.flag(
        name="description", aliases=["desc"], default=None
    )
    emoji: Optional[Union[discord.PartialEmoji, str]] = commands.flag(name="emoji", default=None)


class ButtonFlags(commands.FlagConverter, case_insensitive=True):
    label: Optional[commands.Range[str, 0, 80]] = commands.flag(name="label", default=None)
    emoji: Optional[Union[discord.PartialEmoji, str]] = commands.flag(name="emoji", default=None)
    style: discord.ButtonStyle = commands.flag(
        name="style", default=discord.ButtonStyle.primary, converter=ButtonStyleConverter
    )
