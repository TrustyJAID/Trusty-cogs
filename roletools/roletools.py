import asyncio
import logging

from typing import Optional, Union

import discord
from redbot import version_info, VersionInfo
from redbot.core import Config, commands
from redbot.core.i18n import Translator, cog_i18n
from redbot.core.commands import Context
from redbot.core.utils.chat_formatting import pagify, humanize_list
from redbot.core.utils.predicates import ReactionPredicate
from redbot.core.utils.menus import start_adding_reactions

from .events import RoleEvents
from .converter import RoleEmojiConverter, RoleHierarchyConverter, RawUserIds
from .menus import BaseMenu, ReactRolePages, RolePages

log = logging.getLogger("red.trusty-cogs.roletools")
_ = Translator("RoleTools", __file__)


@cog_i18n(_)
class RoleTools(RoleEvents, commands.Cog):
    """
    Role related tools for moderation
    """

    __author__ = ["TrustyJAID"]
    __version__ = "1.3.1"

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=218773382617890828, force_registration=True)
        self.config.register_global(version="0.0.0")
        default_guild = {
            "reaction_roles": {},
            "auto_roles": [],
        }
        default_role = {
            "sticky": False,
            "auto": False,
            "reactions": [],
            "selfassignable": False,
            "selfremovable": False,
            "exclusive_to": [],
            "inclusive_with": [],
            "required": [],
        }
        default_member = {"sticky_roles": []}
        self.config.register_guild(**default_guild)
        self.config.register_role(**default_role)
        self.config.register_member(**default_member)
        self.settings = {}

    def format_help_for_context(self, ctx: commands.Context) -> str:
        """
        Thanks Sinbad!
        """
        pre_processed = super().format_help_for_context(ctx)
        return f"{pre_processed}\n\nCog Version: {self.__version__}"

    async def initalize(self):
        if await self.config.version() < "1.0.1":
            sticky_role_config = Config.get_conf(
                None, identifier=1358454876, cog_name="StickyRoles"
            )
            sticky_settings = await sticky_role_config.all_guilds()
            for guild_id, data in sticky_settings.items():
                guild = self.bot.get_guild(guild_id)
                if not guild:
                    continue
                for role_id in data["sticky_roles"]:
                    role = guild.get_role(role_id)
                    if role:
                        await self.config.role(role).sticky.set(True)
            auto_role_config = Config.get_conf(None, identifier=45463543548, cog_name="Autorole")
            auto_settings = await auto_role_config.all_guilds()
            for guild_id, data in auto_settings.items():
                guild = self.bot.get_guild(guild_id)
                if not guild:
                    continue
                if ("ENABLED" in data and not data["ENABLED"]) or (
                    "AGREE_CHANNEL" in data and data["AGREE_CHANNEL"] is not None
                ):
                    continue
                if "ROLE" not in data:
                    continue
                for role_id in data["ROLE"]:
                    role = guild.get_role(role_id)
                    if role:
                        await self.config.role(role).auto.set(True)
                        async with self.config.guild_from_id(guild_id).auto_roles() as auto_roles:
                            if role.id not in auto_roles:
                                auto_roles.append(role.id)
            await self.config.version.set("1.0.1")

        self.settings = await self.config.all_guilds()

    @commands.group()
    async def roletools(self, ctx: Context):
        """
        Role tools commands
        """
        pass

    @roletools.group(name="exclude", aliases=["exclusive"])
    async def exclusive(self, ctx: Context):
        """
        Set role exclusions
        """
        pass

    @roletools.group(name="include", aliases=["inclusive"])
    async def inclusive(self, ctx: Context):
        """
        Set role inclusion
        """
        pass

    @roletools.group(name="required")
    async def required_roles(self, ctx: Context):
        """
        Set role requirements
        """
        pass

    @roletools.command()
    @commands.admin_or_permissions(manage_roles=True)
    async def selfadd(
        self, ctx: Context, true_or_false: Optional[bool] = None, *, role: RoleHierarchyConverter
    ):
        """
        Set whether or not a user can apply the role to themselves.

        `[true_or_false]` optional boolean of what to set the setting to.
        If not provided the current setting will be shown instead.
        `<role>` The role you want to set.
        """
        cur_setting = await self.config.role(role).selfassignable()
        if true_or_false is None:
            if cur_setting:
                return await ctx.send(_("The role {role} is self assignable.").format(role=role))
            else:
                return await ctx.send(
                    _(
                        "The role {role} is not self assignable. Run the command "
                        "`{prefix}roletools selfadd yes {role}` to make it self assignable."
                    ).format(role=role.name, prefix=ctx.clean_prefix)
                )
        if true_or_false is True:
            await self.config.role(role).selfassignable.set(True)
            return await ctx.send(_("{role} is now self assignable.").format(role=role.name))
        if true_or_false is False:
            await self.config.role(role).selfassignable.set(False)
            return await ctx.send(_("{role} is no longer self assignable.").format(role=role.name))

    @roletools.command()
    @commands.admin_or_permissions(manage_roles=True)
    async def selfrem(
        self, ctx: Context, true_or_false: Optional[bool] = None, *, role: RoleHierarchyConverter
    ):
        """
        Set whether or not a user can remove the role from themselves.

        `[true_or_false]` optional boolean of what to set the setting to.
        If not provided the current setting will be shown instead.
        `<role>` The role you want to set.
        """
        cur_setting = await self.config.role(role).selfremovable()
        if true_or_false is None:
            if cur_setting:
                return await ctx.send(_("The role {role} is self removeable.").format(role=role))
            else:
                return await ctx.send(
                    _(
                        "The role {role} is not self removable. Run the command "
                        "`{prefix}roletools selfrem yes {role}` to make it self removeable."
                    ).format(role=role.name, prefix=ctx.clean_prefix)
                )
        if true_or_false is True:
            await self.config.role(role).selfremovable.set(True)
            return await ctx.send(_("{role} is now self removeable.").format(role=role.name))
        if true_or_false is False:
            await self.config.role(role).selfremovable.set(False)
            return await ctx.send(_("{role} is no longer self removeable.").format(role=role.name))

    @roletools.command()
    @commands.admin_or_permissions(manage_roles=True)
    async def forcerole(
        self,
        ctx: Context,
        users: commands.Greedy[Union[discord.Member, RawUserIds]],
        *,
        role: RoleHierarchyConverter,
    ):
        """
        Force a sticky role on one or more users.

        `<users>` The users you want to have a forced stickyrole applied to.
        `<roles>` The role you want to set.

        Note: The only way to remove this would be to manually remove the role from
        the user.
        """
        errors = []
        for user in users:
            if isinstance(user, int):
                async with self.config.member_from_ids(
                    ctx.guild.id, user
                ).sticky_roles() as setting:
                    if role.id not in setting:
                        setting.append(role.id)
            elif isinstance(user, discord.Member):
                async with self.config.member(user).sticky_roles() as setting:
                    if role.id not in setting:
                        setting.append(role.id)
                try:
                    await self.give_roles(user, [role], reason=_("Forced Sticky Role"))
                except discord.HTTPException:
                    errors.append(
                        _("There was an error force applying the role to {user}.\n").format(
                            user=user
                        )
                    )
        await ctx.send(
            _("{users} will have the role {role} force applied to them.").format(
                users=humanize_list(users), role=role.name
            )
        )
        if errors:
            await ctx.send("".join([e for e in errors]))

    @roletools.command()
    @commands.admin_or_permissions(manage_roles=True)
    async def forceroleremove(
        self,
        ctx: Context,
        users: commands.Greedy[Union[discord.Member, RawUserIds]],
        *,
        role: RoleHierarchyConverter,
    ):
        """
        Force remove sticky role on one or more users.

        `<users>` The users you want to have a forced stickyrole applied to.
        `<roles>` The role you want to set.

        Note: This is generally only useful for users who have left the server.
        """
        errors = []
        for user in users:
            if isinstance(user, int):
                async with self.config.member_from_ids(
                    ctx.guild.id, user
                ).sticky_roles() as setting:
                    if role in setting:
                        setting.remove(role.id)
            elif isinstance(user, discord.Member):
                async with self.config.member(user).sticky_roles() as setting:
                    if role.id in setting:
                        setting.append(role.id)
                try:
                    await self.remove_roles(user, [role], reason=_("Force removed sticky role"))
                except discord.HTTPException:
                    errors.append(
                        _("There was an error force removing the role from {user}.\n").format(
                            user=user
                        )
                    )
        await ctx.send(
            _("{users} will have the role {role} force removed from them.").format(
                users=humanize_list(users), role=role.name
            )
        )
        if errors:
            await ctx.send("".join([e for e in errors]))

    @roletools.command()
    @commands.admin_or_permissions(manage_roles=True)
    async def sticky(
        self, ctx: Context, true_or_false: Optional[bool] = None, *, role: RoleHierarchyConverter
    ):
        """
        Set whether or not a role will be re-applied when a user leaves and rejoins the server.

        `[true_or_false]` optional boolean of what to set the setting to.
        If not provided the current setting will be shown instead.
        `<role>` The role you want to set.
        """
        cur_setting = await self.config.role(role).sticky()
        if true_or_false is None:
            if cur_setting:
                return await ctx.send(_("The role {role} is sticky.").format(role=role))
            else:
                return await ctx.send(
                    _(
                        "The role {role} is not sticky. Run the command "
                        "`{prefix}roletools sticky yes {role}` to make it sticky."
                    ).format(role=role.name, prefix=ctx.clean_prefix)
                )
        if true_or_false is True:
            await self.config.role(role).sticky.set(True)
            return await ctx.send(_("{role} is now sticky.").format(role=role.name))
        if true_or_false is False:
            await self.config.role(role).sticky.set(False)
            return await ctx.send(_("That role is no longer sticky."))

    @roletools.command(aliases=["autorole"])
    @commands.admin_or_permissions(manage_roles=True)
    async def auto(
        self, ctx: Context, true_or_false: Optional[bool] = None, *, role: RoleHierarchyConverter
    ):
        """
        Set a role to be automatically applied when a user joins the server.

        `[true_or_false]` optional boolean of what to set the setting to.
        If not provided the current setting will be shown instead.
        `<role>` The role you want to set.
        """
        cur_setting = await self.config.role(role).auto()
        if true_or_false is None:
            if cur_setting:
                return await ctx.send(
                    _("The role {role} is automatically applied on joining.").format(role=role)
                )
            else:
                return await ctx.send(
                    _(
                        "The role {role} is not automatically applied "
                        "when a user joins. Run the command "
                        "`{prefix}roletools auto yes {role}` to make "
                        "it automatically apply when a user joins."
                    ).format(role=role.name, prefix=ctx.clean_prefix)
                )
        if true_or_false is True:
            async with self.config.guild(ctx.guild).auto_roles() as current_roles:
                if role.id not in current_roles:
                    current_roles.append(role.id)
                if ctx.guild.id not in self.settings:
                    self.settings[ctx.guild.id] = await self.config.guild(ctx.guild).all()
                if role.id not in self.settings[ctx.guild.id]["auto_roles"]:
                    self.settings[ctx.guild.id]["auto_roles"].append(role.id)
            await self.config.role(role).auto.set(True)
            return await ctx.send(
                _("{role} is now automatically applied when a user joins.").format(role=role.name)
            )
        if true_or_false is False:
            async with self.config.guild(ctx.guild).auto_roles() as current_roles:
                if role.id in current_roles:
                    current_roles.remove(role.id)
                if (
                    ctx.guild.id in self.settings
                    and role.id in self.settings[ctx.guild.id]["auto_roles"]
                ):
                    self.settings[ctx.guild.id]["auto_roles"].remove(role.id)
            await self.config.role(role).auto.set(False)
            return await ctx.send(_("That role is no automatically applied when a user joins."))

    @exclusive.command(name="add")
    @commands.admin_or_permissions(manage_roles=True)
    async def exclusive_add(
        self, ctx: Context, role: RoleHierarchyConverter, *exclude: RoleHierarchyConverter
    ):
        """
        Add role exclusion (This will remove if the designated role is acquired
        if the included roles are not selfremovable they will not be removed
        and the designated role will not be given)

        `<role>` This is the role a user may acquire you want to set exclusions for.
        `<exclude>` The role(s) you wish to have removed when a user gains the `<role>`

        Note: This will only work for reaction roles and automatic roles from this cog.
        """
        cur_setting = await self.config.role(role).exclusive_to()
        inclusive = await self.config.role(role).inclusive_with()
        for excluded_role in exclude:
            if excluded_role.id in inclusive:
                return await ctx.send(
                    _("You cannot exclude a role that is already considered inclusive.")
                )
            if excluded_role.id not in cur_setting:
                cur_setting.append(excluded_role.id)
        await self.config.role(role).exclusive_to.set(cur_setting)
        roles = [ctx.guild.get_role(i) for i in cur_setting]
        allowed_mentions = {}
        role_names = humanize_list([i.name for i in roles if i])
        if version_info >= VersionInfo.from_str("3.4.0"):
            allowed_mentions = {"allowed_mentions": discord.AllowedMentions(roles=False)}
            role_names = humanize_list([i.mention for i in roles if i])
        await ctx.send(
            _(
                "Role {role} will now remove the following roles if it "
                "is acquired automatically or via reaction roles.\n{excluded_roles}."
            ).format(role=role.name, excluded_roles=role_names),
            **allowed_mentions
        )

    @exclusive.command(name="remove")
    @commands.admin_or_permissions(manage_roles=True)
    async def exclusive_remove(
        self, ctx: Context, role: RoleHierarchyConverter, *exclude: RoleHierarchyConverter
    ):
        """
        Remove role exclusion

        `<role>` This is the role a user may acquire you want to set exclusions for.
        `<exclude>` The role(s) currently excluded you no longer wish to have excluded
        """
        cur_setting = await self.config.role(role).exclusive_to()
        for excluded_role in exclude:
            if excluded_role.id in cur_setting:
                cur_setting.remove(excluded_role.id)
        await self.config.role(role).exclusive_to.set(cur_setting)
        roles = [ctx.guild.get_role(i) for i in cur_setting]
        if roles:
            allowed_mentions = {}
            role_names = humanize_list([i.name for i in roles if i])
            if version_info >= VersionInfo.from_str("3.4.0"):
                allowed_mentions = {"allowed_mentions": discord.AllowedMentions(roles=False)}
                role_names = humanize_list([i.mention for i in roles if i])
            await ctx.send(
                _(
                    "Role {role} will now remove the following roles if it "
                    "is acquired automatically or via reaction roles.\n{excluded_roles}."
                ).format(role=role.name, excluded_roles=role_names),
                **allowed_mentions
            )
        else:
            return await ctx.send(
                _("Role {role} will not have any excluded roles.").format(role=role.name)
            )

    @inclusive.command(name="add")
    @commands.admin_or_permissions(manage_roles=True)
    async def inclusive_add(
        self, ctx: Context, role: RoleHierarchyConverter, *include: RoleHierarchyConverter
    ):
        """
        Add role inclusion (This will add roles if the designated role is acquired
        if the designated role is removed the included roles will also be removed
        if the included roles are set to selfremovable)

        `<role>` This is the role a user may acquire you want to set exclusions for.
        `<include>` The role(s) you wish to have added when a user gains the `<role>`

        Note: This will only work for reaction roles and automatic roles from this cog.
        """
        cur_setting = await self.config.role(role).inclusive_with()
        exclusive = await self.config.role(role).exclusive_to()
        for included_role in include:
            if included_role.id in exclusive:
                return await ctx.send(
                    _("You cannot include a role that is already considered exclusive.")
                )
            if included_role.id not in cur_setting:
                cur_setting.append(included_role.id)
        await self.config.role(role).inclusive_with.set(cur_setting)
        roles = [ctx.guild.get_role(i) for i in cur_setting]
        allowed_mentions = {}
        role_names = humanize_list([i.name for i in roles if i])
        if version_info >= VersionInfo.from_str("3.4.0"):
            allowed_mentions = {"allowed_mentions": discord.AllowedMentions(roles=False)}
            role_names = humanize_list([i.mention for i in roles if i])
        await ctx.send(
            _(
                "Role {role} will now add the following roles if it "
                "is acquired automatically or via reaction roles.\n{included_roles}."
            ).format(role=role.name, included_roles=role_names),
            **allowed_mentions
        )

    @inclusive.command(name="remove")
    @commands.admin_or_permissions(manage_roles=True)
    async def inclusive_remove(
        self, ctx: Context, role: RoleHierarchyConverter, *include: RoleHierarchyConverter
    ):
        """
        Remove role inclusion

        `<role>` This is the role a user may acquire you want to set exclusions for.
        `<include>` The role(s) currently inclusive you no longer wish to have included
        """
        cur_setting = await self.config.role(role).inclusive_with()
        for included_role in include:
            if included_role.id in cur_setting:
                cur_setting.remove(included_role.id)
        await self.config.role(role).inclusive_with.set(cur_setting)
        roles = [ctx.guild.get_role(i) for i in cur_setting]
        if roles:
            allowed_mentions = {}
            role_names = humanize_list([i.name for i in roles if i])
            if version_info >= VersionInfo.from_str("3.4.0"):
                allowed_mentions = {"allowed_mentions": discord.AllowedMentions(roles=False)}
                role_names = humanize_list([i.mention for i in roles if i])
            await ctx.send(
                _(
                    "Role {role} will now add the following roles if it "
                    "is acquired automatically or via reaction roles.\n{included_roles}."
                ).format(role=role.name, included_roles=role_names),
                **allowed_mentions
            )
        else:
            return await ctx.send(
                _("Role {role} will no longer have included roles.").format(role=role.name)
            )

    @required_roles.command(name="add")
    @commands.admin_or_permissions(manage_roles=True)
    async def required_add(
        self, ctx: Context, role: RoleHierarchyConverter, *required: RoleHierarchyConverter
    ):
        """
        Add role requirements

        `<role>` This is the role a user may acquire you want to set requirements for.
        `<requires>` The role(s) the user requires before being allowed to gain this role.

        Note: This will only work for reaction roles from this cog.
        """
        cur_setting = await self.config.role(role).required()
        for included_role in required:
            if included_role.id not in cur_setting:
                cur_setting.append(included_role.id)
        await self.config.role(role).required.set(cur_setting)
        roles = [ctx.guild.get_role(i) for i in cur_setting]
        allowed_mentions = {}
        role_names = humanize_list([i.name for i in roles if i])
        if version_info >= VersionInfo.from_str("3.4.0"):
            allowed_mentions = {"allowed_mentions": discord.AllowedMentions(roles=False)}
            role_names = humanize_list([i.mention for i in roles if i])
        await ctx.send(
            _(
                "Role {role} will now only be given if the following roles "
                "are already owned.\n{included_roles}."
            ).format(role=role.name, included_roles=role_names),
            **allowed_mentions
        )

    @required_roles.command(name="remove")
    @commands.admin_or_permissions(manage_roles=True)
    async def required_remove(
        self, ctx: Context, role: RoleHierarchyConverter, *required: RoleHierarchyConverter
    ):
        """
        Remove role requirements

        `<role>` This is the role a user may acquire you want to set requirements for.
        `<requires>` The role(s) you wish to have added when a user gains the `<role>`

        Note: This will only work for reaction roles from this cog.
        """
        cur_setting = await self.config.role(role).required()
        for included_role in required:
            if included_role.id in cur_setting:
                cur_setting.remove(included_role.id)
        await self.config.role(role).required.set(cur_setting)
        roles = [ctx.guild.get_role(i) for i in cur_setting]
        if roles:
            allowed_mentions = {}
            role_names = humanize_list([i.name for i in roles if i])
            if version_info >= VersionInfo.from_str("3.4.0"):
                allowed_mentions = {"allowed_mentions": discord.AllowedMentions(roles=False)}
                role_names = humanize_list([i.mention for i in roles if i])
            await ctx.send(
                _(
                    "Role {role} will now only be given if the following roles "
                    "are already owned.\n{included_roles}."
                ).format(role=role.name, included_roles=role_names),
                **allowed_mentions
            )
        else:
            return await ctx.send(
                _("Role {role} will no longer require any other roles to be added.").format(
                    role=role.name
                )
            )

    @roletools.command(aliases=["reactionroles", "reactrole"])
    @commands.admin_or_permissions(manage_roles=True)
    async def reactroles(self, ctx: Context):
        """
        View current bound roles in the server
        """
        if ctx.guild.id not in self.settings:
            return await ctx.send(_("There are no bound roles in this server."))
        async with ctx.typing():
            msg = _("Reaction Roles in {guild}\n").format(guild=ctx.guild.name)
            for key, role_id in self.settings[ctx.guild.id]["reaction_roles"].items():
                channel_id, msg_id, emoji = key.split("-")
                if emoji.isdigit():
                    emoji = self.bot.get_emoji(int(emoji))
                if not emoji:
                    emoji = _("Emoji from another server")
                role = ctx.guild.get_role(role_id)
                channel = ctx.guild.get_channel(int(channel_id))
                try:
                    message = await channel.fetch_message(int(msg_id))
                except Exception:
                    message = None

                msg += _("{emoji} - {role} [Reaction Message]({message})\n").format(
                    role=role.name if role else _("None"),
                    emoji=emoji,
                    message=message.jump_url if message else _("None"),
                )
            pages = list(pagify(msg))
        await BaseMenu(
            source=ReactRolePages(
                pages=pages,
            ),
            delete_message_after=False,
            clear_reactions_after=True,
            timeout=60,
            cog=self,
            page_start=0,
        ).start(ctx=ctx)

    @roletools.command(aliases=["viewrole"])
    @commands.bot_has_permissions(embed_links=True)
    async def viewroles(self, ctx: Context, *, role: Optional[discord.Role]):
        """
        View current roletools setup for each role in the server

        `[role]` The role you want to see settings for.
        """
        page_start = 0
        if role:
            page_start = ctx.guild.roles.index(role)
        await BaseMenu(
            source=RolePages(
                roles=ctx.guild.roles,
            ),
            delete_message_after=False,
            clear_reactions_after=True,
            timeout=60,
            cog=self,
            page_start=page_start,
        ).start(ctx=ctx)

    @roletools.command()
    @commands.admin_or_permissions(manage_roles=True)
    async def cleanup(self, ctx: Context):
        """
        Cleanup old/missing reaction roles and settings.

        Note: This will also clear out reaction roles if the bot is just
        missing permissions to see the reactions.
        """
        guild = ctx.guild
        async with ctx.typing():
            async with self.config.guild(ctx.guild).reaction_roles() as cur_settings:
                to_remove = []
                for key, role_id in cur_settings.items():
                    chan_id, message_id, emoji = key.split("-")
                    channel = guild.get_channel(int(chan_id))
                    if not channel:
                        to_remove.append((key, role_id))
                        continue
                    try:
                        await channel.fetch_message(int(message_id))
                    except Exception:
                        to_remove.append((key, role_id))
                        continue
                    role = guild.get_role(int(role_id))
                    if not role:
                        to_remove.append((key, role_id))
                for key, role_id in to_remove:
                    del cur_settings[key]
                    del self.settings[guild.id]["reaction_roles"][key]
                    async with self.config.role_from_id(role_id).reactions() as reactions:
                        reactions.remove(key)
        await ctx.send(_("I am finished deleting old settings."))

    @roletools.command()
    @commands.is_owner()
    async def ownercleanup(self, ctx: Context):
        """
        Cleanup old/missing reaction roles and settings on the bot.

        Note: This will also clear out reaction roles if the bot is just
        missing permissions to see the reactions.
        """
        async with ctx.typing():
            for guild_id in self.settings:
                guild = self.bot.get_guild(guild_id)
                if not guild:
                    continue
                async with self.config.guild(ctx.guild).reaction_roles() as cur_settings:
                    to_remove = []
                    for key, role_id in cur_settings.items():
                        chan_id, message_id, emoji = key.split("-")
                        channel = guild.get_channel(int(chan_id))
                        if not channel:
                            to_remove.append((key, role_id))
                            continue
                        message = await channel.fetch_message(int(message_id))
                        if not message:
                            to_remove.append((key, role_id))
                            continue
                        role = guild.get_role(int(role_id))
                        if not role:
                            to_remove.append((key, role_id))
                    for key, role_id in to_remove:
                        del cur_settings[key]
                        del self.settings[guild.id]["reaction_roles"][key]
                        async with self.config.role_from_id(role_id).reactions() as reactions:
                            reactions.remove(key)
        await ctx.send(_("I am finished deleting old settings."))


    @roletools.command(aliases=["reacts"])
    @commands.admin_or_permissions(manage_roles=True)
    async def react(
        self,
        ctx: Context,
        message: discord.Message,
        emoji: Union[discord.Emoji, str],
        *,
        role: RoleHierarchyConverter,
    ):
        """
        Create a reaction role

        `<message>` can be the channel_id-message_id pair
        from copying message ID while holding SHIFT or a message link
        `<emoji>` The emoji you want people to react with to get the role.
        `<role>` The role you want people to receive for reacting.
        """
        if not message.guild or message.guild.id != ctx.guild.id:
            return await ctx.send(
                _("You cannot add a Reaction Role to a message not in this guild.")
            )
        async with self.config.guild(ctx.guild).reaction_roles() as cur_setting:
            if isinstance(emoji, discord.Emoji):
                use_emoji = str(emoji.id)
            else:
                use_emoji = str(emoji).strip("\N{VARIATION SELECTOR-16}")
            key = f"{message.channel.id}-{message.id}-{use_emoji}"
            send_to_react = False
            try:
                await message.add_reaction(str(emoji).strip("\N{VARIATION SELECTOR-16}"))
            except discord.HTTPException:
                send_to_react = True
            if ctx.guild.id not in self.settings:
                self.settings[ctx.guild.id] = await self.config.guild(ctx.guild).all()
            self.settings[ctx.guild.id]["reaction_roles"][key] = role.id
            cur_setting[key] = role.id
        async with self.config.role(role).reactions() as reactions:
            reactions.append(key)
        await ctx.send(
            _("Created the reaction role {role} to {emoji} on {message}").format(
                role=role.name, emoji=emoji, message=message.jump_url
            )
        )
        if send_to_react:
            await ctx.send(
                _(
                    "I couldn't add the emoji to the message. Please make "
                    "sure to add the emoji to the message for this to work."
                )
            )
        if not await self.config.role(role).selfassignable():
            msg_str = _(
                "{role} is not self assignable. Would you liked to make "
                "it self assignable and self removeable?"
            ).format(role=role.name, prefix=ctx.clean_prefix)
            msg = await ctx.send(msg_str)
            start_adding_reactions(msg, ReactionPredicate.YES_OR_NO_EMOJIS)
            pred = ReactionPredicate.yes_or_no(msg, ctx.author)
            try:
                await ctx.bot.wait_for("reaction_add", check=pred, timeout=60)
            except asyncio.TimeoutError:
                return await ctx.send(
                    _("Okay I won't automatically make {role} self assignable.").format(
                        role=role.name
                    )
                )
            if pred.result:
                await self.config.role(role).selfassignable.set(True)
                await self.config.role(role).selfremovable.set(True)
                await ctx.send(
                    _("{role} has been made self assignable and self removeable.").format(
                        role=role.name
                    )
                )

    @roletools.command(aliases=["remreacts"])
    @commands.admin_or_permissions(manage_roles=True)
    async def remreact(
        self,
        ctx: Context,
        message: discord.Message,
        *,
        role_or_emoji: Union[RoleHierarchyConverter, discord.Emoji, str],
    ):
        """
        Remove a reaction role

        `<message>` can be the channel_id-message_id pair
        from copying message ID while holding SHIFT or a message link
        `<emoji>` The emoji you want people to react with to get the role.
        `<role>` The role you want people to receive for reacting.
        """
        if not message.guild or message.guild.id != ctx.guild.id:
            return await ctx.send(
                _("You cannot remove a Reaction Role from a message not in this guild.")
            )
        if ctx.guild.id not in self.settings:
            return await ctx.send(_("There are no roletools settings on this server."))
        if not self.settings[ctx.guild.id]["reaction_roles"]:
            return await ctx.send(_("There are no reaction roles setup for this guild."))
        found = False
        for key, role_id in self.settings[ctx.guild.id]["reaction_roles"].items():
            if isinstance(role_or_emoji, discord.Role):
                if role_or_emoji.id == role_id:
                    found = True
                    break
            elif isinstance(role_or_emoji, discord.Emoji):
                if str(role_or_emoji.id) in key:
                    found = True
                    break
            else:
                if str(role_or_emoji.strip("\N{VARIATION SELECTOR-16}")) in key:
                    found = True
                    break
        if found:
            channel, message_id, emoji = key.split("-")
            if emoji.isdigit():
                emoji = self.bot.get_emoji(int(emoji))
            async with self.config.guild(ctx.guild).reaction_roles() as cur_setting:
                role = ctx.guild.get_role(cur_setting[key])
                del self.settings[ctx.guild.id]["reaction_roles"][key]
                del cur_setting[key]
                async with self.config.role_from_id(role_id).reactions() as reactions:
                    reactions.remove(key)

            await ctx.send(
                _("Removed role reaction on {role} to {emoji} on {message}").format(
                    role=role, emoji=emoji, message=message.jump_url
                )
            )
        else:
            await ctx.send(
                _(
                    "I could not find a reaction role on that message or for that role/emoji combination."
                )
            )

    @roletools.command(aliases=["bulksreacts"])
    @commands.admin_or_permissions(manage_roles=True)
    async def bulkreact(
        self,
        ctx: Context,
        message: discord.Message,
        *role_emoji: RoleEmojiConverter,
    ):
        """
        Create multiple roles reactions for a single message

        `<message>` can be the channel_id-message_id pair
        from copying message ID while holding SHIFT or a message link
        `[role_emoji...]` Must be a role-emoji pair separated by either `;`, `,`, `|`, or `-`.

        Note: Any spaces will be considered a new set of role-emoji pairs so ensure
        there's no spaces between the role-emoji pair.

        e.g. `[p]roletools bulkreact 461417772115558410-821105109097644052 @member-:smile:`
        `[p]roletools bulkreact 461417772115558410-821105109097644052 role-:frown:`
        """
        if not message.guild or message.guild.id != ctx.guild.id:
            return await ctx.send(
                _("You cannot add a Reaction Role to a message not in this guild.")
            )
        added = []
        not_added = []
        send_to_react = False
        async with self.config.guild(ctx.guild).reaction_roles() as cur_setting:
            for role, emoji in role_emoji:
                log.debug(type(emoji))
                if isinstance(emoji, discord.PartialEmoji):
                    use_emoji = str(emoji.id)
                else:
                    use_emoji = str(emoji).strip("\N{VARIATION SELECTOR-16}")
                key = f"{message.channel.id}-{message.id}-{use_emoji}"
                if key not in cur_setting:
                    try:
                        await message.add_reaction(
                            str(emoji).strip().strip("\N{VARIATION SELECTOR-16}")
                        )
                    except discord.HTTPException:
                        send_to_react = True
                        log.exception("could not add reaction to message")
                        pass
                    if ctx.guild.id not in self.settings:
                        self.settings[ctx.guild.id] = await self.config.guild(ctx.guild).all()
                    self.settings[ctx.guild.id]["reaction_roles"][key] = role.id
                    cur_setting[key] = role.id
                    added.append((key, role))
                    async with self.config.role(role).reactions() as reactions:
                        reactions.append(key)

                else:
                    not_added.append((key, role))
        ask_to_modify = False
        if added:
            msg = _("__The following Reaction Roles were created__\n")

            if any(
                [
                    m is False
                    for m in [await self.config.role(r).selfassignable() for x, r in added]
                ]
            ):
                ask_to_modify = True
            for item, role in added:
                channel, message_id, emoji = item.split("-")
                if emoji.isdigit():
                    emoji = self.bot.get_emoji(int(emoji))
                msg += _("{role} - {emoji} on {message}\n").format(
                    role=role.name, emoji=emoji, message=message.jump_url
                )
            for page in pagify(msg):
                await ctx.send(page)
            if send_to_react:
                await ctx.send(
                    _(
                        "I couldn't add an emoji to the message. Please make "
                        "sure to add the missing emojis to the message for this to work."
                    )
                )
        if not_added:
            msg = _("__The following Reaction Roles could not be created__\n")
            for item, role in not_added:
                channel, message_id, emoji = item.split("-")
                if emoji.isdigit():
                    emoji = self.bot.get_emoji(int(emoji))
                msg += _("{role} - {emoji} on {message}\n").format(
                    role=role.name, emoji=emoji, message=message.jump_url
                )
            await ctx.send(msg)

        if ask_to_modify:
            msg_str = _(
                "Some roles are not self assignable. Would you liked to make "
                "them self assignable and self removeable?"
            ).format(role=role.name, prefix=ctx.clean_prefix)
            msg = await ctx.send(msg_str)
            start_adding_reactions(msg, ReactionPredicate.YES_OR_NO_EMOJIS)
            pred = ReactionPredicate.yes_or_no(msg, ctx.author)
            try:
                await ctx.bot.wait_for("reaction_add", check=pred, timeout=60)
            except asyncio.TimeoutError:
                return await ctx.send(
                    _("Okay I won't automatically make {role} self assignable.").format(
                        role=role.name
                    )
                )
            if pred.result:
                for key, role in added:
                    await self.config.role(role).selfassignable.set(True)
                    await self.config.role(role).selfremovable.set(True)
                await ctx.send(
                    _("{roles} have been made self assignable and self removeable.").format(
                        roles=humanize_list([r for x, r in added])
                    )
                )
