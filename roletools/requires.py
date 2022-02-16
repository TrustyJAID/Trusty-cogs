import logging
from typing import Union

from discord import Interaction
from redbot.core import commands
from redbot.core.commands import Context
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import humanize_list

from .abc import RoleToolsMixin, roletools
from .converter import RoleHierarchyConverter

log = logging.getLogger("red.Trusty-cogs.RoleTools")
_ = Translator("RoleTools", __file__)


class RoleToolsRequires(RoleToolsMixin):
    """This class handles required role settings."""

    @roletools.group(name="required")
    async def required_roles(self, ctx: Union[Context, Interaction]) -> None:
        """
        Set role requirements
        """
        if isinstance(ctx, Interaction):
            command_mapping = {"add": self.required_add, "remove": self.required_remove}
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

    @required_roles.command(name="add")
    @commands.admin_or_permissions(manage_roles=True)
    async def required_add(
        self,
        ctx: Union[Context, Interaction],
        role: RoleHierarchyConverter,
        *,
        required: commands.Greedy[RoleHierarchyConverter],
    ) -> None:
        """
        Add role requirements

        `<role>` This is the role a user may acquire you want to set requirements for.
        `<requires>` The role(s) the user requires before being allowed to gain this role.

        Note: This will only work for reaction roles from this cog.
        """
        is_slash = False
        if isinstance(ctx, Interaction):
            is_slash = True
            try:
                role = await RoleHierarchyConverter().convert(ctx, role.mention)
                required = [await RoleHierarchyConverter().convert(ctx, required.mention)]
            except commands.BadArgument as e:
                await ctx.response.send_message(e, ephemeral=True)
                return
            await ctx.response.defer()
        else:
            await ctx.trigger_typing()

        cur_setting = await self.config.role(role).required()
        for included_role in required:
            if included_role.id not in cur_setting:
                cur_setting.append(included_role.id)
        await self.config.role(role).required.set(cur_setting)
        roles = [ctx.guild.get_role(i) for i in cur_setting]
        role_names = humanize_list([i.mention for i in roles if i])
        msg = _(
            "The {role} role will now only be given if the following roles "
            "are already owned.\n{included_roles}."
        ).format(role=role.mention, included_roles=role_names)
        if is_slash:
            await ctx.followup.send(msg)
        else:
            await ctx.send(msg)

    @required_roles.command(name="remove")
    @commands.admin_or_permissions(manage_roles=True)
    async def required_remove(
        self,
        ctx: Union[Context, Interaction],
        role: RoleHierarchyConverter,
        *,
        required: commands.Greedy[RoleHierarchyConverter],
    ) -> None:
        """
        Remove role requirements

        `<role>` This is the role a user may acquire you want to set requirements for.
        `<requires>` The role(s) you wish to have added when a user gains the `<role>`

        Note: This will only work for reaction roles from this cog.
        """
        is_slash = False
        if isinstance(ctx, Interaction):
            is_slash = True
            try:
                role = await RoleHierarchyConverter().convert(ctx, role.mention)
                required = [await RoleHierarchyConverter().convert(ctx, required.mention)]
            except commands.BadArgument as e:
                await ctx.response.send_message(e, ephemeral=True)
                return
            await ctx.response.defer()
        else:
            await ctx.trigger_typing()

        cur_setting = await self.config.role(role).required()
        for included_role in required:
            if included_role.id in cur_setting:
                cur_setting.remove(included_role.id)
        await self.config.role(role).required.set(cur_setting)
        roles = [ctx.guild.get_role(i) for i in cur_setting]
        if roles:
            role_names = humanize_list([i.mention for i in roles if i])
            msg = _(
                "The {role} role will now only be given if the following roles "
                "are already owned.\n{included_roles}."
            ).format(role=role.mention, included_roles=role_names)
            if is_slash:
                await ctx.followup.send(msg)
            else:
                await ctx.send(msg)
        else:
            msg = _("The {role} role will no longer require any other roles to be added.").format(
                role=role.mention
            )
            if is_slash:
                await ctx.followup.send(msg)
            else:
                await ctx.send(msg)
