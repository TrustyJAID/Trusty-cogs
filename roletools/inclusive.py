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


class RoleToolsInclusive(RoleToolsMixin):
    """This class handles setting inclusive roles."""

    @roletools.group(name="include", aliases=["inclusive"])
    async def inclusive(self, ctx: Context) -> None:
        """
        Set role inclusion
        """

    @inclusive.command(name="add")
    @commands.admin_or_permissions(manage_roles=True)
    async def inclusive_add(
        self,
        ctx: Context,
        role: RoleHierarchyConverter,
        include: commands.Greedy[RoleHierarchyConverter],
    ) -> None:
        """
        Add role inclusion (This will add roles if the designated role is acquired
        if the designated role is removed the included roles will also be removed
        if the included roles are set to selfremovable)

        `<role>` This is the role a user may acquire you want to set exclusions for.
        `<include>` The role(s) you wish to have added when a user gains the `<role>`

        Note: This will only work for roles assigned by this cog.
        """
        await ctx.typing()
        cur_setting = await self.config.role(role).inclusive_with()
        exclusive = await self.config.role(role).exclusive_to()
        for included_role in include:
            if included_role.id in exclusive:
                msg = _("You cannot include a role that is already considered exclusive.")
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
        await ctx.send(msg)

    @inclusive.command(name="mutual", with_app_command=False)
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
        ctx: Context,
        role: RoleHierarchyConverter,
        include: commands.Greedy[RoleHierarchyConverter],
    ) -> None:
        """
        Remove role inclusion

        `<role>` This is the role a user may acquire you want to set exclusions for.
        `<include>` The role(s) currently inclusive you no longer wish to have included
        """
        await ctx.typing()
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
            await ctx.send(msg)
        else:
            msg = _("The {role} role will no longer have included roles.").format(
                role=role.mention
            )
            await ctx.send(msg)
