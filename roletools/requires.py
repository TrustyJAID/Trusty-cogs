from typing import Union

import discord
from discord import Interaction
from red_commons.logging import getLogger
from redbot.core import commands
from redbot.core.commands import Context
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import humanize_list

from .abc import RoleToolsMixin
from .converter import RoleHierarchyConverter

roletools = RoleToolsMixin.roletools

log = getLogger("red.Trusty-cogs.RoleTools")
_ = Translator("RoleTools", __file__)


class RoleToolsRequires(RoleToolsMixin):
    """This class handles required role settings."""

    @roletools.group(name="required", aliases=["requires", "require", "req"])
    async def required_roles(self, ctx: Union[Context, Interaction]) -> None:
        """
        Set role requirements
        """

    @required_roles.command(name="any")
    @commands.admin_or_permissions(manage_roles=True)
    async def required_any(self, ctx: Context, role: RoleHierarchyConverter, require_any: bool):
        """
        Set the required roles to require any of the roles instead of all of them

        `<role>` This is the role a user may acquire you want to set requirements for.
        `<require_any>` Either `True` or `False`. If `True` any of the required roles will allow
        the user to acquire the `<role>`.

        Note: This will only work for roles assigned by this cog.
        """
        await self.config.role(role).require_any.set(require_any)
        cur_setting = await self.config.role(role).required()
        roles = [ctx.guild.get_role(i) for i in cur_setting if ctx.guild.get_role(i) is not None]
        role_names = humanize_list([i.mention for i in roles if i])
        any_of = _("the") if require_any is False else _("any of the")
        msg = _(
            "The {role} role will now only be given if {any_of} following roles "
            "are already owned.\n{included_roles}."
        ).format(role=role.mention, included_roles=role_names, any_of=any_of)
        await ctx.send(msg)

    @required_roles.command(name="add")
    @commands.admin_or_permissions(manage_roles=True)
    async def required_add(
        self,
        ctx: Union[Context, Interaction],
        role: RoleHierarchyConverter,
        required: commands.Greedy[discord.Role],
    ) -> None:
        """
        Add role requirements

        `<role>` This is the role a user may acquire you want to set requirements for.
        `<requires>` The role(s) the user requires before being allowed to gain this role.

        Note: This will only work for roles assigned by this cog.
        """
        await ctx.typing()
        cur_setting = await self.config.role(role).required()
        require_any = await self.config.role(role).require_any()
        for included_role in required:
            if included_role.id not in cur_setting:
                cur_setting.append(included_role.id)
        await self.config.role(role).required.set(cur_setting)
        roles = [ctx.guild.get_role(i) for i in cur_setting]
        role_names = humanize_list([i.mention for i in roles if i])
        any_of = _("the") if require_any is False else _("any of the")
        msg = _(
            "The {role} role will now only be given if {any_of} following roles "
            "are already owned.\n{included_roles}."
        ).format(role=role.mention, included_roles=role_names, any_of=any_of)
        await ctx.send(msg)

    @required_roles.command(name="remove")
    @commands.admin_or_permissions(manage_roles=True)
    async def required_remove(
        self,
        ctx: Union[Context, Interaction],
        role: RoleHierarchyConverter,
        required: commands.Greedy[discord.Role],
    ) -> None:
        """
        Remove role requirements

        `<role>` This is the role a user may acquire you want to set requirements for.
        `<requires>` The role(s) you wish to have added when a user gains the `<role>`

        Note: This will only work for roles assigned by this cog.
        """
        await ctx.typing()
        cur_setting = await self.config.role(role).required()
        require_any = await self.config.role(role).require_any()
        for included_role in required:
            if included_role.id in cur_setting:
                cur_setting.remove(included_role.id)
        await self.config.role(role).required.set(cur_setting)
        roles = [ctx.guild.get_role(i) for i in cur_setting]
        if roles:
            role_names = humanize_list([i.mention for i in roles if i])
            any_of = _("the") if require_any is False else _("any of the")
            msg = _(
                "The {role} role will now only be given if {any_of} following roles "
                "are already owned.\n{included_roles}."
            ).format(role=role.mention, included_roles=role_names, any_of=any_of)
            await ctx.send(msg)
        else:
            msg = _("The {role} role will no longer require any other roles to be added.").format(
                role=role.mention
            )
            await ctx.send(msg)
