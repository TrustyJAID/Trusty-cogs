import logging
from typing import Union

import discord
from discord import Interaction
from redbot.core import commands
from redbot.core.commands import Context
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import humanize_list

from .abc import RoleToolsMixin, roletools
from .converter import RoleHierarchyConverter

log = logging.getLogger("red.Trusty-cogs.RoleTools")
_ = Translator("RoleTools", __file__)


class RoleToolsInclusive(RoleToolsMixin):
    """This class handles setting inclusive roles."""

    @roletools.group(name="include", aliases=["inclusive"])
    async def inclusive(self, ctx: Union[Context, Interaction]) -> None:
        """
        Set role inclusion
        """
        if isinstance(ctx, discord.Interaction):
            command_mapping = {
                "remove": self.inclusive_remove,
                "add": self.inclusive_add,
                "mutual": self.mutual_inclusive_add,
            }
            options = ctx.data["options"][0]["options"][0]["options"]
            option = ctx.data["options"][0]["options"][0]["name"]
            func = command_mapping[option]
            if getattr(func, "requires", None):
                if not await self.check_requires(func, ctx):
                    return

            try:
                kwargs = {}
                for option in options:
                    name = option["name"]
                    kwargs[name] = self.convert_slash_args(ctx, option)
            except KeyError:
                kwargs = {}
                pass
            except AttributeError:
                await ctx.response.send_message(
                    ("One or more options you have provided are not available in DM's."),
                    ephemeral=True,
                )
                return
            await func(ctx, **kwargs)

    @inclusive.command(name="add")
    @commands.admin_or_permissions(manage_roles=True)
    async def inclusive_add(
        self,
        ctx: Union[Context, Interaction],
        role: RoleHierarchyConverter,
        include: commands.Greedy[RoleHierarchyConverter],
    ) -> None:
        """
        Add role inclusion (This will add roles if the designated role is acquired
        if the designated role is removed the included roles will also be removed
        if the included roles are set to selfremovable)

        `<role>` This is the role a user may acquire you want to set exclusions for.
        `<include>` The role(s) you wish to have added when a user gains the `<role>`

        Note: This will only work for reaction roles and automatic roles from this cog.
        """
        is_slash = False
        if isinstance(ctx, discord.Interaction):
            is_slash = True
            try:
                role = await RoleHierarchyConverter().convert(ctx, role.mention)
                include = [await RoleHierarchyConverter().convert(ctx, include.mention)]
            except commands.BadArgument as e:
                await ctx.response.send_message(e, ephemeral=True)
                return
            await ctx.response.defer()
        else:
            await ctx.trigger_typing()

        cur_setting = await self.config.role(role).inclusive_with()
        exclusive = await self.config.role(role).exclusive_to()
        for included_role in include:
            if included_role.id in exclusive:
                msg = _("You cannot include a role that is already considered exclusive.")
                if is_slash:
                    await ctx.followup.send(msg)
                else:
                    await ctx.send(msg)
                return
            if included_role.id not in cur_setting:
                cur_setting.append(included_role.id)
        await self.config.role(role).inclusive_with.set(cur_setting)
        roles = [ctx.guild.get_role(i) for i in cur_setting]
        role_names = humanize_list([i.mention for i in roles if i])
        msg = _(
            "The {role} role will now add the following roles if it "
            "is acquired through roletools.\n{included_roles}."
        ).format(role=role.mention, included_roles=role_names)
        if is_slash:
            await ctx.followup.send(msg)
        else:
            await ctx.send(msg)

    @inclusive.command(name="mutual")
    @commands.admin_or_permissions(manage_roles=True)
    async def mutual_inclusive_add(self, ctx: Context, *roles: RoleHierarchyConverter) -> None:
        """
        Allow setting roles mutually inclusive to eachother

        This is equivalent to individually setting each roles inclusive roles to another
        set of roles.

        `[role...]` The roles you want to set as mutually inclusive.
        """
        if len(roles) <= 1:
            await ctx.send_help()
            return
        for role in roles:
            exclusive = await self.config.role(role).exclusive_to()
            async with self.config.role(role).inclusive_with() as inclusive_roles:
                for add_role in roles:
                    if add_role.id == role.id:
                        continue
                    if add_role.id in exclusive:
                        await ctx.send(
                            _("You cannot exclude a role that is already considered exclusive.")
                        )
                        return
                    if add_role.id not in inclusive_roles:
                        inclusive_roles.append(add_role.id)
        await ctx.send(
            _("The following roles are now mutually inclusive to eachother:\n{roles}").format(
                roles=humanize_list([r.mention for r in roles])
            )
        )

    @inclusive.command(name="remove")
    @commands.admin_or_permissions(manage_roles=True)
    async def inclusive_remove(
        self,
        ctx: Union[Context, Interaction],
        role: RoleHierarchyConverter,
        include: commands.Greedy[RoleHierarchyConverter],
    ) -> None:
        """
        Remove role inclusion

        `<role>` This is the role a user may acquire you want to set exclusions for.
        `<include>` The role(s) currently inclusive you no longer wish to have included
        """
        is_slash = False
        if isinstance(ctx, discord.Interaction):
            is_slash = True
            try:
                role = await RoleHierarchyConverter().convert(ctx, role.mention)
                include = [await RoleHierarchyConverter().convert(ctx, include.mention)]
            except commands.BadArgument as e:
                await ctx.response.send_message(e, ephemeral=True)
                return
            await ctx.response.defer()
        else:
            await ctx.trigger_typing()

        cur_setting = await self.config.role(role).inclusive_with()
        for included_role in include:
            if included_role.id in cur_setting:
                cur_setting.remove(included_role.id)
        await self.config.role(role).inclusive_with.set(cur_setting)
        roles = [ctx.guild.get_role(i) for i in cur_setting]
        if roles:
            role_names = humanize_list([i.mention for i in roles if i])
            msg = _(
                "The {role} role will now add the following roles if it "
                "is acquired through roletools.\n{included_roles}."
            ).format(role=role.mention, included_roles=role_names)
            if is_slash:
                await ctx.followup.send(msg)
            else:
                await ctx.send(msg)
        else:
            msg = _("The {role} role will no longer have included roles.").format(
                role=role.mention
            )
            if is_slash:
                await ctx.followup.send(msg)
            else:
                await ctx.send(msg)
