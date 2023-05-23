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


class RoleToolsExclusive(RoleToolsMixin):
    """This class handles setting exclusive role settings."""

    @roletools.group(name="exclude", aliases=["exclusive"])
    async def exclusive(self, ctx: Context) -> None:
        """
        Set role exclusions
        """

    @exclusive.command(name="add")
    @commands.admin_or_permissions(manage_roles=True)
    async def exclusive_add(
        self,
        ctx: Context,
        role: RoleHierarchyConverter,
        exclude: commands.Greedy[RoleHierarchyConverter],
    ) -> None:
        """
        Add role exclusion (This will remove if the designated role is acquired
        if the included roles are not selfremovable they will not be removed
        and the designated role will not be given)

        `<role>` This is the role a user may acquire you want to set exclusions for.
        `<exclude>` The role(s) you wish to have removed when a user gains the `<role>`

        Note: This will only work for roles assigned by this cog.
        """
        await ctx.typing()
        cur_setting = await self.config.role(role).exclusive_to()
        inclusive = await self.config.role(role).inclusive_with()
        for excluded_role in exclude:
            if excluded_role.id in inclusive:
                msg = _("You cannot exclude a role that is already considered inclusive.")
                await ctx.send(msg)
                return
            if excluded_role.id not in cur_setting:
                cur_setting.append(excluded_role.id)
        await self.config.role(role).exclusive_to.set(cur_setting)
        roles = [ctx.guild.get_role(i) for i in cur_setting]
        role_names = humanize_list([i.mention for i in roles if i])
        msg = _(
            "The {role} role will now remove the following roles if it "
            "is acquired through roletools.\n{excluded_roles}."
        ).format(role=role.mention, excluded_roles=role_names)
        await ctx.send(msg)

    @exclusive.command(name="mutual", with_app_command=False)
    @commands.admin_or_permissions(manage_roles=True)
    async def mutual_exclusive_add(self, ctx: Context, *roles: RoleHierarchyConverter) -> None:
        """
        Allow setting roles mutually exclusive to eachother

        This is equivalent to individually setting each roles exclusive roles to another
        set of roles.

        `[role...]` The roles you want to set as mutually exclusive.
        """
        if len(roles) <= 1:
            await ctx.send_help()
            return
        for role in roles:
            inclusive = await self.config.role(role).inclusive_with()
            async with self.config.role(role).exclusive_to() as exclusive_roles:
                for add_role in roles:
                    if add_role.id == role.id:
                        continue
                    if add_role.id in inclusive:
                        await ctx.send(
                            _("You cannot exclude a role that is already considered inclusive.")
                        )
                        return
                    if add_role.id not in exclusive_roles:
                        exclusive_roles.append(add_role.id)
        await ctx.send(
            _("The following roles are now mutually exclusive to eachother:\n{roles}").format(
                roles=humanize_list([r.mention for r in roles])
            )
        )

    @exclusive.command(name="remove")
    @commands.admin_or_permissions(manage_roles=True)
    async def exclusive_remove(
        self,
        ctx: Context,
        role: RoleHierarchyConverter,
        exclude: commands.Greedy[RoleHierarchyConverter],
    ) -> None:
        """
        Remove role exclusion

        `<role>` This is the role a user may acquire you want to set exclusions for.
        `<exclude>` The role(s) currently excluded you no longer wish to have excluded
        """
        await ctx.typing()
        cur_setting = await self.config.role(role).exclusive_to()
        for excluded_role in exclude:
            if excluded_role.id in cur_setting:
                cur_setting.remove(excluded_role.id)
        await self.config.role(role).exclusive_to.set(cur_setting)
        roles = [ctx.guild.get_role(i) for i in cur_setting]
        if roles:
            role_names = humanize_list([i.mention for i in roles if i])
            msg = _(
                "The {role} role will now remove the following roles if it "
                "is acquired through roletools.\n{excluded_roles}."
            ).format(role=role.mention, excluded_roles=role_names)
            await ctx.send(msg)
        else:
            msg = _("Role {role} will not have any excluded roles.").format(role=role.mention)
            await ctx.send(msg)
