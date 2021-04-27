import asyncio
import logging

from abc import ABC
from typing import Optional, Union, Any, Dict

import discord
from redbot.core import Config, commands, bank
from redbot.core.bot import Red
from redbot.core.i18n import Translator, cog_i18n
from redbot.core.commands import Context
from redbot.core.utils import AsyncIter, bounded_gather
from redbot.core.utils.chat_formatting import humanize_list

from .abc import roletools
from .converter import RoleHierarchyConverter, RawUserIds, SelfRoleConverter
from .events import RoleToolsEvents
from .exclusive import RoleToolsExclusive
from .inclusive import RoleToolsInclusive
from .reactions import RoleToolsReactions
from .requires import RoleToolsRequires
from .settings import RoleToolsSettings

from .menus import BaseMenu, RolePages


log = logging.getLogger("red.Trusty-cogs.RoleTools")
_ = Translator("RoleTools", __file__)


class CompositeMetaClass(type(commands.Cog), type(ABC)):
    """
    This allows the metaclass used for proper type detection to
    coexist with discord.py's metaclass
    """

    pass


@cog_i18n(_)
class RoleTools(
    RoleToolsEvents,
    RoleToolsExclusive,
    RoleToolsInclusive,
    RoleToolsReactions,
    RoleToolsRequires,
    RoleToolsSettings,
    commands.Cog,
    metaclass=CompositeMetaClass,
):
    """
    Role related tools for moderation
    """

    __author__ = ["TrustyJAID"]
    __version__ = "1.4.3"

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=218773382617890828, force_registration=True)
        self.config.register_global(version="0.0.0", atomic=True)
        self.config.register_guild(reaction_roles={}, auto_roles=[], atomic=None)
        self.config.register_role(
            sticky=False,
            auto=False,
            reactions=[],
            selfassignable=False,
            selfremovable=False,
            exclusive_to=[],
            inclusive_with=[],
            required=[],
            cost=0,
        )
        self.config.register_member(sticky_roles=[])
        self.settings: Dict[int, Any] = {}
        self._ready: asyncio.Event = asyncio.Event()

    def cog_check(self, ctx: commands.Context) -> bool:
        return self._ready.is_set()

    def format_help_for_context(self, ctx: commands.Context) -> str:
        """
        Thanks Sinbad!
        """
        pre_processed = super().format_help_for_context(ctx)
        return f"{pre_processed}\n\nCog Version: {self.__version__}"

    async def initalize(self) -> None:
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
        self._ready.set()

    def update_cooldown(
        self, ctx: commands.Context, rate: int, per: float, _type: commands.BucketType
    ) -> None:
        """
        This should be replaced if d.py ever adds the ability to do this
        without hacking the cooldown system as I have here.

        This calls the same method as `commands.reset_cooldown(ctx)`
        but rather than resetting the cooldown value we want to dynamically change
        what the cooldown actually is.

        In this cog I only care to change the per value but theoretically
        this will for other modifications to the cooldown after we have parsed
        the command.

        This, in my case, is being used to dynamically adjust the cooldown rate
        so that bots aren't spamming the API with add/remove role requests for large
        guilds. It doesn't make sense to constantly have a 1 hour cooldown until you've
        run this on a rather large server for everyone in the server.

        Technically speaking cooldown is added as 10 seconds per member who has had their role
        modified with these commands up to a maximum of 1 hour. This means small guilds trying
        to give everyone a role can do it semi-frequently but large guilds can only run
        it once for everyone in the server every hour.
        """
        if ctx.command._buckets.valid:
            bucket = ctx.command._buckets.get_bucket(ctx.message)
            bucket.rate = int(rate)
            bucket.per = float(per)
            bucket.type = _type

    @roletools.group(invoke_without_command=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def selfrole(self, ctx: Context, *, role: SelfRoleConverter) -> None:
        """
        Give yourself a role

        `<role>` The role you want to give yourself
        """
        if ctx.invoked_subcommand is None:
            if not await self.config.role(role).selfassignable():
                await ctx.send(
                    _("The {role} role is not currently selfassignable.").format(role=role.mention)
                )
                return
            if required := await self.config.role(role).required():
                has_required = True
                for role_id in required:
                    r = ctx.guild.get_role(role_id)
                    if r is None:
                        async with self.config.role(role).required() as required_roles:
                            required_roles.remove(role_id)
                        continue
                    if r not in ctx.author.roles:
                        has_required = False
                if not has_required:
                    await ctx.send(
                        _(
                            "I cannot grant you the {role} role because you "
                            "are missing a required role."
                        ).format(role=role.mention)
                    )
                    return
            if cost := await self.config.role(role).cost():
                currency_name = await bank.get_currency_name(ctx.guild)
                if not await bank.can_spend(ctx.author, cost):
                    await ctx.send(
                        _(
                            "You do not have enough {currency_name} to acquire "
                            "this role. You need {cost} {currency_name}."
                        ).format(currency_name=currency_name, cost=cost)
                    )
                    return
            await self.give_roles(ctx.author, [role], _("Selfrole command."))
            await ctx.send(_("You have been given the {role} role.").format(role=role.mention))

    @selfrole.command(name="remove")
    async def selfrole_remove(self, ctx: Context, *, role: SelfRoleConverter) -> None:
        """
        Remove a role from yourself

        `<role>` The role you want to remove.
        """
        if not await self.config.role(role).selfremovable():
            await ctx.send(
                _("The {role} role is not currently self removable.").format(role=role.mention)
            )
            return
        await self.remove_roles(ctx.author, [role], _("Selfrole command."))
        await ctx.send(_("The {role} role has been removed from you.").format(role=role.mention))

    @roletools.command(cooldown_after_parsing=True)
    @commands.bot_has_permissions(manage_roles=True)
    @commands.admin_or_permissions(manage_roles=True)
    @commands.max_concurrency(1, commands.BucketType.guild)
    @commands.cooldown(1, 10, commands.BucketType.guild)
    async def giverole(
        self,
        ctx: Context,
        role: RoleHierarchyConverter,
        *who: Union[discord.Role, discord.TextChannel, discord.Member, str],
    ) -> None:
        """
        Gives a role to designatd members.

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
                        await ctx.send(
                            _("`{who}` cannot have roles assigned to them.").format(who=entity)
                        )
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
        self.update_cooldown(ctx, 1, min(len(tasks) * 10, 3600), commands.BucketType.guild)
        added_to = humanize_list([getattr(en, "name", en) for en in who])
        await ctx.send(_("Added {role} to {added}.").format(role=role.mention, added=added_to))

    @roletools.command()
    @commands.bot_has_permissions(manage_roles=True)
    @commands.admin_or_permissions(manage_roles=True)
    @commands.max_concurrency(1, commands.BucketType.guild)
    @commands.cooldown(1, 10, commands.BucketType.guild)
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
                        await ctx.send(
                            _("`{who}` cannot have roles assigned to them.").format(who=entity)
                        )
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
        self.update_cooldown(ctx, 1, min(len(tasks) * 10, 3600), commands.BucketType.guild)
        removed_from = humanize_list([getattr(en, "name", en) for en in who])
        await ctx.send(
            _("Removed the {role} from {removed}.").format(role=role.mention, removed=removed_from)
        )

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
    ) -> None:
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

    @roletools.command(aliases=["viewrole"])
    @commands.bot_has_permissions(read_message_history=True, add_reactions=True, embed_links=True)
    async def viewroles(self, ctx: Context, *, role: Optional[discord.Role]) -> None:
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
