import asyncio
from abc import ABC
from typing import Any, Dict, List, Optional, Union

import discord
from red_commons.logging import getLogger
from redbot.core import Config, bank, commands
from redbot.core.bot import Red
from redbot.core.commands import Context
from redbot.core.i18n import Translator, cog_i18n
from redbot.core.utils import AsyncIter, bounded_gather
from redbot.core.utils.chat_formatting import humanize_list

from .abc import RoleToolsMixin
from .buttons import RoleToolsButtons
from .converter import RawUserIds, RoleHierarchyConverter, SelfRoleConverter
from .events import RoleToolsEvents
from .exclusive import RoleToolsExclusive
from .inclusive import RoleToolsInclusive
from .menus import BaseMenu, ConfirmView, RolePages
from .messages import RoleToolsMessages
from .reactions import RoleToolsReactions
from .requires import RoleToolsRequires
from .select import RoleToolsSelect
from .settings import RoleToolsSettings

roletools = RoleToolsMixin.roletools

log = getLogger("red.Trusty-cogs.RoleTools")
_ = Translator("RoleTools", __file__)


class CompositeMetaClass(type(commands.Cog), type(ABC)):
    """
    This allows the metaclass used for proper type detection to
    coexist with discord.py's metaclass
    """

    pass


def custom_cooldown(ctx: commands.Context) -> Optional[discord.app_commands.Cooldown]:
    who = ctx.args[3:]
    members = []

    for entity in who:
        log.verbose("custom_cooldown entity: %s", entity)
        if isinstance(entity, discord.TextChannel) or isinstance(entity, discord.Role):
            members += entity.members
        elif isinstance(entity, discord.Member):
            members.append(entity)
        else:
            if entity not in ["everyone", "here", "bots", "humans"]:
                continue
            elif entity == "everyone":
                members = ctx.guild.members
                break
            elif entity == "here":
                members += [m for m in ctx.guild.members if str(m.status) == "online"]
            elif entity == "bots":
                members += [m for m in ctx.guild.members if m.bot]
            elif entity == "humans":
                members += [m for m in ctx.guild.members if not m.bot]
    members = list(set(members))
    log.debug("Returning cooldown of 1 per %s", min(len(members) * 10, 3600))
    return discord.app_commands.Cooldown(1, min(len(members) * 10, 3600))


@cog_i18n(_)
class RoleTools(
    RoleToolsEvents,
    RoleToolsButtons,
    RoleToolsExclusive,
    RoleToolsInclusive,
    RoleToolsMessages,
    RoleToolsReactions,
    RoleToolsRequires,
    RoleToolsSettings,
    RoleToolsSelect,
    commands.Cog,
    metaclass=CompositeMetaClass,
):
    """
    Role related tools for moderation
    """

    __author__ = ["TrustyJAID"]
    __version__ = "1.5.11"

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=218773382617890828, force_registration=True)
        self.config.register_global(
            version="0.0.0",
            atomic=True,
            enable_slash=False,
        )
        self.config.register_guild(
            reaction_roles={},
            auto_roles=[],
            atomic=None,
            buttons={},
            select_options={},
            select_menus={},
        )
        self.config.register_role(
            sticky=False,
            auto=False,
            reactions=[],
            buttons=[],
            select_options=[],
            selfassignable=False,
            selfremovable=False,
            exclusive_to=[],
            inclusive_with=[],
            required=[],
            require_any=False,
            cost=0,
        )
        self.config.register_member(sticky_roles=[])
        self.settings: Dict[int, Any] = {}
        self._ready: asyncio.Event = asyncio.Event()
        self.views: Dict[int, Dict[str, discord.ui.View]] = {}
        self._repo = ""
        self._commit = ""

    def cog_check(self, ctx: commands.Context) -> bool:
        return self._ready.is_set()

    def format_help_for_context(self, ctx: commands.Context) -> str:
        """
        Thanks Sinbad!
        """
        pre_processed = super().format_help_for_context(ctx)
        ret = f"{pre_processed}\n\n- Cog Version: {self.__version__}\n"
        # we'll only have a repo if the cog was installed through Downloader at some point
        if self._repo:
            ret += f"- Repo: {self._repo}\n"
        # we should have a commit if we have the repo but just incase
        if self._commit:
            ret += f"- Commit: [{self._commit[:9]}]({self._repo}/tree/{self._commit})"
        return ret

    async def add_cog_to_dev_env(self):
        await self.bot.wait_until_red_ready()
        if self.bot.owner_ids and 218773382617890828 in self.bot.owner_ids:
            try:
                self.bot.add_dev_env_value("roletools", lambda x: self)
            except Exception:
                pass

    async def _get_commit(self):
        downloader = self.bot.get_cog("Downloader")
        if not downloader:
            return
        cogs = await downloader.installed_cogs()
        for cog in cogs:
            if cog.name == "roletools":
                if cog.repo is not None:
                    self._repo = cog.repo.clean_url
                self._commit = cog.commit

    async def load_views(self):
        self.settings = await self.config.all_guilds()
        await self.bot.wait_until_red_ready()
        try:
            await self.initialize_select()
        except Exception:
            log.exception("Error initializing Select")
        try:
            await self.initialize_buttons()
        except Exception:
            log.exception("Error initializing Buttons")
        for guild_id, guild_views in self.views.items():
            for msg_ids, view in guild_views.items():
                log.trace("Adding view %r to %s", view, guild_id)
                channel_id, message_id = msg_ids.split("-")
                self.bot.add_view(view, message_id=int(message_id))
                # These should be unique messages containing views
                # and we should track them seperately
        self._ready.set()

    async def cog_load(self) -> None:
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
                        async with self.config.guild_from_id(
                            int(guild_id)
                        ).auto_roles() as auto_roles:
                            if role.id not in auto_roles:
                                auto_roles.append(role.id)
            await self.config.version.set("1.0.1")
        loop = asyncio.get_running_loop()
        loop.create_task(self.load_views())
        loop.create_task(self.add_cog_to_dev_env())
        loop.create_task(self._get_commit())

    async def cog_unload(self):
        for views in self.views.values():
            for view in views.values():
                # Don't forget to remove persistent views when the cog is unloaded.
                log.verbose("Stopping view %s", view)
                view.stop()
        try:
            self.bot.remove_dev_env_value("roletools")
        except Exception:
            pass

    async def confirm_selfassignable(
        self, ctx: commands.Context, roles: List[discord.Role]
    ) -> None:
        not_assignable = [r for r in roles if not await self.config.role(r).selfassignable()]
        if not_assignable:
            role_list = "\n".join(f"- {role.mention}" for role in not_assignable)
            msg_str = _(
                "The following roles are not self assignable:\n{roles}\n"
                "Would you liked to make them self assignable and self removeable?"
            ).format(
                roles=role_list,
            )
            pred = ConfirmView(ctx.author)
            pred.message = await ctx.send(
                msg_str, view=pred, allowed_mentions=discord.AllowedMentions(roles=False)
            )
            await pred.wait()
            if pred.result:
                for role in not_assignable:
                    await self.config.role(role).selfassignable.set(True)
                    await self.config.role(role).selfremovable.set(True)
                await ctx.channel.send(
                    _(
                        "The following roles have been made self assignable and self removeable:\n{roles}"
                    ).format(roles=role_list)
                )
            else:
                await ctx.channel.send(
                    _("Okay I won't make the following rolesself assignable:\n{roles}").format(
                        roles=role_list
                    )
                )

    @roletools.group(invoke_without_command=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def selfrole(self, ctx: Context) -> None:
        """
        Add or remove a defined selfrole
        """
        pass

    @selfrole.command(name="add")
    async def selfrole_add(self, ctx: Context, *, role: SelfRoleConverter) -> None:
        """
        Give yourself a role

        `<role>` The role you want to give yourself
        """
        await ctx.typing()
        author = ctx.author

        if not await self.config.role(role).selfassignable():
            msg = _("The {role} role is not currently selfassignable.").format(role=role.mention)
            await ctx.send(msg)
            return
        if required := await self.config.role(role).required():
            has_required = True
            for role_id in required:
                r = ctx.guild.get_role(role_id)
                if r is None:
                    async with self.config.role(role).required() as required_roles:
                        required_roles.remove(role_id)
                    continue
                if r not in author.roles:
                    has_required = False
            if not has_required:
                msg = _(
                    "I cannot grant you the {role} role because you "
                    "are missing a required role."
                ).format(role=role.mention)
                await ctx.send(msg)
                return
        if cost := await self.config.role(role).cost():
            currency_name = await bank.get_currency_name(ctx.guild)
            if not await bank.can_spend(author, cost):
                msg = _(
                    "You do not have enough {currency_name} to acquire "
                    "this role. You need {cost} {currency_name}."
                ).format(currency_name=currency_name, cost=cost)
                await ctx.send(msg)
                return
        await self.give_roles(author, [role], _("Selfrole command."))
        msg = _("You have been given the {role} role.").format(role=role.mention)
        await ctx.send(msg)

    @selfrole.command(name="remove")
    async def selfrole_remove(self, ctx: Context, *, role: SelfRoleConverter) -> None:
        """
        Remove a role from yourself

        `<role>` The role you want to remove.
        """
        await ctx.typing()
        author = ctx.author

        if not await self.config.role(role).selfremovable():
            msg = _("The {role} role is not currently self removable.").format(role=role.mention)
            await ctx.send(msg)
            return
        await self.remove_roles(author, [role], _("Selfrole command."))
        msg = _("The {role} role has been removed from you.").format(role=role.mention)
        await ctx.send(msg)

    @roletools.command(cooldown_after_parsing=True, with_app_command=False)
    @commands.bot_has_permissions(manage_roles=True)
    @commands.admin_or_permissions(manage_roles=True)
    @commands.max_concurrency(1, commands.BucketType.guild)
    @commands.dynamic_cooldown(custom_cooldown, commands.BucketType.guild)
    async def giverole(
        self,
        ctx: Context,
        role: RoleHierarchyConverter,
        *who: Union[discord.Role, discord.TextChannel, discord.Member, str],
    ) -> None:
        """
        Gives a role to designated members.

        `<role>` The role you want to give.
        `[who...]` Who you want to give the role to. This can include any of the following:```diff
        + Member
            A specified member of the server.
        + Role
            People who already have a specified role.
        + TextChannel
            People who have access to see the channel provided.
        Or one of the following:
        + everyone - everyone in the server.
        + here     - everyone who appears online in the server.
        + bots     - all the bots in the server.
        + humans   - all the humans in the server.
        ```
        **Note:** This runs through exclusive and inclusive role checks
        which may cause unintended roles to be removed/applied.

        **This command is on a cooldown of 10 seconds per member who receives
        a role up to a maximum of 1 hour.**
        """
        await ctx.typing()

        if len(who) == 0:
            await ctx.send_help()
            ctx.command.reset_cooldown(ctx)
            return
        async with ctx.typing():
            members = []
            for entity in who:
                if isinstance(entity, discord.TextChannel) or isinstance(entity, discord.Role):
                    members += entity.members
                elif isinstance(entity, discord.Member):
                    members.append(entity)
                else:
                    if entity not in ["everyone", "here", "bots", "humans"]:
                        msg = _("`{who}` cannot have roles assigned to them.").format(who=entity)
                        await ctx.send(msg)
                        ctx.command.reset_cooldown(ctx)
                        return
                    elif entity == "everyone":
                        members = ctx.guild.members
                        break
                    elif entity == "here":
                        members += [
                            m
                            async for m in AsyncIter(ctx.guild.members, steps=500)
                            if str(m.status) == "online"
                        ]
                    elif entity == "bots":
                        members += [
                            m async for m in AsyncIter(ctx.guild.members, steps=500) if m.bot
                        ]
                    elif entity == "humans":
                        members += [
                            m async for m in AsyncIter(ctx.guild.members, steps=500) if not m.bot
                        ]
            members = list(set(members))
            tasks = []
            async for m in AsyncIter(members, steps=500):
                if m.top_role >= ctx.me.top_role or role in m.roles:
                    continue
                # tasks.append(m.add_roles(role, reason=_("Roletools Giverole command")))
                tasks.append(
                    self.give_roles(
                        m, [role], _("Roletools Giverole command"), check_cost=False, atomic=False
                    )
                )
            await bounded_gather(*tasks)
        added_to = humanize_list([getattr(en, "name", en) for en in who])
        msg = _("Added {role} to {added}.").format(role=role.mention, added=added_to)
        await ctx.send(msg)

    @roletools.command(with_app_command=False)
    @commands.bot_has_permissions(manage_roles=True)
    @commands.admin_or_permissions(manage_roles=True)
    @commands.max_concurrency(1, commands.BucketType.guild)
    @commands.dynamic_cooldown(custom_cooldown, commands.BucketType.guild)
    async def removerole(
        self,
        ctx: Context,
        role: RoleHierarchyConverter,
        *who: Union[discord.Role, discord.TextChannel, discord.Member, str],
    ) -> None:
        """
        Removes a role from the designated members.

        `<role>` The role you want to give.
        `[who...]` Who you want to give the role to. This can include any of the following:```diff
        + Member
            A specified member of the server.
        + Role
            People who already have a specified role.
        + TextChannel
            People who have access to see the channel provided.
        Or one of the following:
        + everyone - everyone in the server.
        + here     - everyone who appears online in the server.
        + bots     - all the bots in the server.
        + humans   - all the humans in the server.
        ```
        **Note:** This runs through exclusive and inclusive role checks
        which may cause unintended roles to be removed/applied.

        **This command is on a cooldown of 10 seconds per member who receives
        a role up to a maximum of 1 hour.**
        """
        await ctx.typing()

        if len(who) == 0:
            return await ctx.send_help()
        async with ctx.typing():
            members = []
            for entity in who:
                if isinstance(entity, discord.TextChannel) or isinstance(entity, discord.Role):
                    members += entity.members
                elif isinstance(entity, discord.Member):
                    members.append(entity)
                else:
                    if entity not in ["everyone", "here", "bots", "humans"]:
                        msg = _("`{who}` cannot have roles removed from them.").format(who=entity)
                        await ctx.send(msg)
                        ctx.command.reset_cooldown(ctx)
                        return
                    elif entity == "everyone":
                        members = ctx.guild.members
                        break
                    elif entity == "here":
                        members += [
                            m
                            async for m in AsyncIter(ctx.guild.members, steps=500)
                            if str(m.status) == "online"
                        ]
                    elif entity == "bots":
                        members += [
                            m async for m in AsyncIter(ctx.guild.members, steps=500) if m.bot
                        ]
                    elif entity == "humans":
                        members += [
                            m async for m in AsyncIter(ctx.guild.members, steps=500) if not m.bot
                        ]
            members = list(set(members))
            tasks = []
            async for m in AsyncIter(members, steps=500):
                if m.top_role >= ctx.me.top_role or role not in m.roles:
                    continue
                # tasks.append(m.add_roles(role, reason=_("Roletools Giverole command")))
                tasks.append(
                    self.remove_roles(m, [role], _("Roletools Removerole command"), atomic=False)
                )
            await bounded_gather(*tasks)
        removed_from = humanize_list([getattr(en, "name", en) for en in who])
        msg = _("Removed the {role} from {removed}.").format(
            role=role.mention, removed=removed_from
        )
        await ctx.send(msg)

    @roletools.command()
    @commands.admin_or_permissions(manage_roles=True)
    async def forcerole(
        self,
        ctx: Context,
        users: commands.Greedy[Union[discord.Member, RawUserIds]],
        *,
        role: RoleHierarchyConverter,
    ) -> None:
        """
        Force a sticky role on one or more users.

        `<users>` The users you want to have a forced stickyrole applied to.
        `<roles>` The role you want to set.

        Note: The only way to remove this would be to manually remove the role from
        the user.
        """
        await ctx.typing()
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
        msg = _("{users} will have the role {role} force applied to them.").format(
            users=humanize_list(users), role=role.name
        )
        await ctx.send(msg)
        if errors:
            await ctx.channel.send("".join([e for e in errors]))

    @roletools.command()
    @commands.admin_or_permissions(manage_roles=True)
    async def forceroleremove(
        self,
        ctx: Context,
        users: commands.Greedy[Union[discord.Member, RawUserIds]],
        *,
        role: RoleHierarchyConverter,
    ) -> None:
        """
        Force remove sticky role on one or more users.

        `<users>` The users you want to have a forced stickyrole applied to.
        `<roles>` The role you want to set.

        Note: This is generally only useful for users who have left the server.
        """
        await ctx.typing()

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
        msg = _("{users} will have the role {role} force removed from them.").format(
            users=humanize_list(users), role=role.name
        )
        await ctx.send(msg)
        if errors:
            await ctx.channel.send("".join([e for e in errors]))

    @roletools.command(aliases=["viewrole"])
    @commands.bot_has_permissions(read_message_history=True, add_reactions=True, embed_links=True)
    async def viewroles(self, ctx: Context, *, role: Optional[discord.Role] = None) -> None:
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

    # @roletools.group(name="slash")
    # @commands.admin_or_permissions(manage_guild=True)
    async def roletools_slash(self, ctx: Context) -> None:
        """
        Slash command toggling for roletools
        """
        pass

    # @roletools_slash.command(name="global")
    # @commands.is_owner()
    async def roletools_global_slash(self, ctx: Context) -> None:
        """Toggle this cog to register slash commands"""
        current = await self.config.enable_slash()
        await self.config.enable_slash.set(not current)
        verb = _("enabled") if not current else _("disabled")
        await ctx.send(_("Slash commands are {verb}.").format(verb=verb))
        if not current:
            self.bot.tree.add_command(self, override=True)
        else:
            self.bot.tree.remove_command("role-tools")
