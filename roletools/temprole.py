import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional, Union

import discord
from dateutil.relativedelta import relativedelta
from discord import Interaction
from discord.ext import tasks
from red_commons.logging import getLogger
from redbot.core import commands
from redbot.core.commands import Context
from redbot.core.commands.converter import RelativedeltaConverter
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import humanize_timedelta, pagify
from redbot.core.utils.views import SimpleMenu

from .abc import RoleToolsMixin
from .converter import RoleHierarchyConverter

RELATIVE_CONVERTER = RelativedeltaConverter(
    allowed_units=["years", "months", "weeks", "days", "hours", "minutes", "seconds"]
)

roletools = RoleToolsMixin.roletools

log = getLogger("red.Trusty-cogs.RoleTools")
_ = Translator("RoleTools", __file__)


@dataclass
class TempRole:
    user_id: int
    role_id: int
    remove_at: float
    guild: discord.Guild

    @property
    def member(self) -> Optional[discord.Member]:
        return self.guild.get_member(int(self.user_id))

    @property
    def role(self) -> Optional[discord.Role]:
        return self.guild.get_role(int(self.role_id))

    @property
    def datetime(self) -> datetime:
        return datetime.fromtimestamp(self.remove_at, tz=timezone.utc)

    @property
    def discord_timestamp(self) -> str:
        return discord.utils.format_dt(self.datetime)

    @property
    def time_left(self) -> float:
        return (self.datetime - datetime.now(timezone.utc)).total_seconds()


class RoleToolsTemporary(RoleToolsMixin):
    """This class handles temporary role removal and setup."""

    @roletools.group(name="temporary", aliases=["temp"])
    async def temporary_roles(self, ctx: Union[Context, Interaction]):
        """
        Setup temporary roles
        """

    @temporary_roles.command(name="set")
    @commands.admin_or_permissions(manage_roles=True)
    async def temporary_roles_set(
        self,
        ctx: Union[Context, Interaction],
        role: RoleHierarchyConverter,
        *,
        duration: Optional[relativedelta] = commands.parameter(
            converter=RELATIVE_CONVERTER, default=None
        ),
    ):
        """
        Set the duration the role will last before being removed.

        `<role>` The role you want to apply temporary duration for.
        `[duration]` How long you want the role to be applied for.
        If no duration is given then the role will not be automatically removed.
        Note: The loop will check temporary role removal every 5 minutes.
        It is recommended to have a duration longer than 5 minutes to work effectively.

        Example:
        `[p]roletools temp set @role 2 months`
        This will remove `@role` 2 months after the user has received it via roletools.
        """

        if duration is not None:
            new_time = ctx.message.created_at + duration
            # convert relativedelta into a new datetime object
            td = new_time - ctx.message.created_at
            # convert back into normalized timedelta for future calculation
            # relativedelta doesn't have some of the niceties of timedeltas
            await self.config.role(role).duration.set(int(td.total_seconds()))
            await ctx.send(
                _(
                    "Role {role} will automatically be removed after {duration} when applied by roletools."
                ).format(role=role.mention, duration=humanize_timedelta(timedelta=td))
            )
        else:
            await self.config.role(role).duration.clear()
            await ctx.send(_("Role {role} will not be automatically removed after being applied."))

    @temporary_roles.command(name="list")
    async def temporary_roles_list(
        self, ctx: commands.Context, *, member: Optional[discord.Member] = None
    ):
        """
        List the currently pending temporary roles and when they expire.

        - `[member]` If you want to check a specific member's temporary roles you can provide it here.
        If not provided will show all temporary role members for moderators with `manage_roles` permission.
        If not provided by a member with `manage_roles` it will only show their own temporary roles if they have any.
        """
        msg = ""
        temp_roles = []

        async with self.config.guild(ctx.guild).temporary_roles() as tr:
            for t in tr:
                temp_roles.append(TempRole(**t, guild=ctx.guild))
        show_all = ctx.channel.permissions_for(ctx.author).manage_roles and member is None
        if member is None:
            member = ctx.author
        for temp in temp_roles:
            if temp.member and temp.role:
                if not show_all and temp.member.id != member.id:
                    continue
                msg += _("- {member} will have {role} removed on {date}\n").format(
                    member=temp.member.mention,
                    role=temp.role.mention,
                    date=temp.discord_timestamp,
                )
        if msg:
            pages = []
            for page in pagify(msg):
                if await ctx.embed_requested():
                    title = _("Pending Temporary Roles for {guild}").format(guild=ctx.guild.name)
                    if not show_all:
                        title = _("Pending Temporary Roles for {guild}").format(
                            guild=member.display_name
                        )
                    em = discord.Embed(
                        colour=await self.bot.get_embed_colour(ctx),
                        description=page,
                        title=title,
                    )
                    pages.append(em)
                else:
                    pages.append(page)
            menu = SimpleMenu(pages)
            await menu.start(ctx)
        else:
            if show_all:
                await ctx.send(
                    _("There are no currently waiting temporary roles in {guild}.").format(
                        guild=ctx.guild.name
                    )
                )
            else:
                await ctx.send(
                    _("You have no currently waiting temporary roles in {guild}.").format(
                        guild=ctx.guild.name
                    )
                )

    @tasks.loop(seconds=300)
    async def temporary_roles_task(self):
        all_guilds = await self.config.all_guilds()
        now = datetime.now(timezone.utc)

        for guild_id, data in all_guilds.items():
            if not data["temporary_roles"]:
                continue
            guild = self.bot.get_guild(guild_id)
            if guild is None:
                continue
            for tr in data["temporary_roles"]:
                temp_role = TempRole(**tr, guild=guild)

                if temp_role.member is None:
                    async with self.config.guild(guild).temporary_roles() as temp_roles:
                        temp_roles.pop(temp_roles.index(tr))
                    log.debug("Removing %r because member is None", temp_role)
                    continue

                if temp_role.role is None:
                    async with self.config.guild(guild).temporary_roles() as temp_roles:
                        temp_roles.pop(temp_roles.index(tr))
                    log.debug("Removing %r because role is None", temp_role)
                    continue
                if temp_role.role not in temp_role.member.roles:
                    async with self.config.guild(guild).temporary_roles() as temp_roles:
                        temp_roles.pop(temp_roles.index(tr))
                    log.debug("Removing %r because member doesn't have role", temp_role)
                    continue
                remove_date = temp_role.datetime
                log.debug("maybe removing %r, %s", temp_role, now - remove_date)
                if (remove_date - now) <= timedelta(minutes=5):
                    async with self.config.guild(guild).temporary_roles() as temp_roles:
                        temp_roles.pop(temp_roles.index(tr))
                    asyncio.create_task(self.remove_temporary_role(temp_role))

    @temporary_roles_task.before_loop
    async def before_temporary_roles_loop(self):
        await self.bot.wait_until_red_ready()

    async def remove_temporary_role(self, temp_role: TempRole):
        log.debug("Waiting %s to remove %r", temp_role.time_left, temp_role)
        await asyncio.sleep(temp_role.time_left)
        member = temp_role.member
        role = temp_role.role
        if member is None or role is None:
            return
        try:
            await self.remove_roles(member, [role], _("Temporary Role Removal"))
        except Exception:
            log.exception(
                "Error removing temporary role %s from %s", temp_role.role, temp_role.member
            )
