import asyncio
import logging

from typing import Optional, Union

import discord
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
    __version__ = "1.1.1"

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
        }
        default_member = {"sticky_roles": []}
        self.config.register_guild(**default_guild)
        self.config.register_role(**default_role)
        self.config.register_member(**default_member)
        self.settings = {}

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

    @roletools.command()
    @commands.admin_or_permissions(manage_roles=True)
    async def selfadd(
        self, ctx: Context, set_to: Optional[bool] = None, *, role: RoleHierarchyConverter
    ):
        """
        Set whether or not a user can apply the role to themselves.

        `[set_to]` optional boolean of what to set the setting to.
        If not provided the current settingwill be shown instead.
        `<role>` The role you want to set.
        """
        cur_setting = await self.config.role(role).selfassignable()
        if set_to is None:
            if cur_setting:
                return await ctx.send(_("The role {role} is self assignable.").format(role=role))
            else:
                return await ctx.send(
                    _(
                        "The role {role} is not self assignable. Run the command "
                        "`{prefix}roletools selfadd yes {role}` to make it self assignable."
                    ).format(role=role.name, prefix=ctx.clean_prefix)
                )
        if set_to is True:
            await self.config.role(role).selfassignable.set(True)
            return await ctx.send(_("{role} is now self assignable.").format(role=role.name))
        if set_to is False:
            await self.config.role(role).selfassignable.set(False)
            return await ctx.send(_("{role} is no longer self assignable.").format(role=role.name))

    @roletools.command()
    @commands.admin_or_permissions(manage_roles=True)
    async def selfrem(
        self, ctx: Context, set_to: Optional[bool] = None, *, role: RoleHierarchyConverter
    ):
        """
        Set whether or not a user can remove the role from themselves.

        `[set_to]` optional boolean of what to set the setting to.
        If not provided the current settingwill be shown instead.
        `<role>` The role you want to set.
        """
        cur_setting = await self.config.role(role).selfremovable()
        if set_to is None:
            if cur_setting:
                return await ctx.send(_("The role {role} is self removeable.").format(role=role))
            else:
                return await ctx.send(
                    _(
                        "The role {role} is not self removable. Run the command "
                        "`{prefix}roletools selfrem yes {role}` to make it self removeable."
                    ).format(role=role.name, prefix=ctx.clean_prefix)
                )
        if set_to is True:
            await self.config.role(role).selfremovable.set(True)
            return await ctx.send(_("{role} is now self removeable.").format(role=role.name))
        if set_to is False:
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
                async with self.config.member_from_ids(ctx.guild.id, user).sticky_roles() as setting:
                    if role not in setting:
                        setting.append(role.id)
            elif isinstance(user, discord.Member):
                async with self.config.member(user).sticky_roles() as setting:
                    if role not in setting:
                        setting.append(role.id)
                try:
                    await self.give_roles(user, [role], reason=_("Forced Sticky Role"))
                except discord.HTTPException:
                    errors.append(_("There was an error force applying the role to {user}.\n").format(user=user))
        await ctx.send(_("{users} will have the role {role} force applied to them.").format(users=humanize_list(users), role=role.name))
        if errors:
            await ctx.send("".join([e for e in errors]))


    @roletools.command()
    @commands.admin_or_permissions(manage_roles=True)
    async def sticky(
        self, ctx: Context, set_to: Optional[bool] = None, *, role: RoleHierarchyConverter
    ):
        """
        Set whether or not a role will be re-applied when a user leaves and rejoins the server.

        `[set_to]` optional boolean of what to set the setting to.
        If not provided the current settingwill be shown instead.
        `<role>` The role you want to set.
        """
        cur_setting = await self.config.role(role).sticky()
        if set_to is None:
            if cur_setting:
                return await ctx.send(_("The role {role} is sticky.").format(role=role))
            else:
                return await ctx.send(
                    _(
                        "The role {role} is not sticky. Run the command "
                        "`{prefix}roletools sticky yes {role}` to make it sticky."
                    ).format(role=role.name, prefix=ctx.clean_prefix)
                )
        if set_to is True:
            await self.config.role(role).sticky.set(True)
            return await ctx.send(_("{role} is now sticky.").format(role=role.name))
        if set_to is False:
            await self.config.role(role).sticky.set(False)
            return await ctx.send(_("That role is no longer sticky."))

    @roletools.command(aliases=["autorole"])
    @commands.admin_or_permissions(manage_roles=True)
    async def auto(
        self, ctx: Context, set_to: Optional[bool] = None, *, role: RoleHierarchyConverter
    ):
        """
        Set a role to be automatically applied when a user joins the server.

        `[set_to]` optional boolean of what to set the setting to.
        If not provided the current settingwill be shown instead.
        `<role>` The role you want to set.
        """
        cur_setting = await self.config.role(role).auto()
        if set_to is None:
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
        if set_to is True:
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
        if set_to is False:
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
        `[role_emoji...]` Must be a role followed by the emoji tied to that role
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
