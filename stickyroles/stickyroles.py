import logging
from typing import Literal

import discord
from redbot import VersionInfo, version_info
from redbot.core import Config, checks, commands
from redbot.core.i18n import Translator, cog_i18n

_ = Translator("StickyRoles", __file__)
log = logging.getLogger("red.trusty-cogs.stickyroles")


@cog_i18n(_)
class StickyRoles(commands.Cog):
    """
    Reapplies specific roles on join. Rewritten for V3 from

    https://github.com/Twentysix26/26-Cogs/blob/master/stickyroles/stickyroles.py
    """

    __author__ = ["Twentysix", "TrustyJAID"]
    __version__ = "2.0.1"

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, 1358454876)
        self.config.register_guild(sticky_roles=[], to_reapply={})

    def format_help_for_context(self, ctx: commands.Context) -> str:
        """
        Thanks Sinbad!
        """
        pre_processed = super().format_help_for_context(ctx)
        return f"{pre_processed}\n\nCog Version: {self.__version__}"

    async def red_delete_data_for_user(
        self,
        *,
        requester: Literal["discord_deleted_user", "owner", "user", "user_strict"],
        user_id: int,
    ):
        """
        Method for finding users data inside the cog and deleting it.
        """
        all_guilds = await self.config.all_guilds()
        for guild_id, data in all_guilds.items():
            if str(user_id) in data["to_reapply"]:
                del data["to_reapply"][str(user_id)]
                await self.config.guild_from_id(guild_id).to_reapply.set(data["to_reapply"])

    @commands.group(aliases=["stickyrole"])
    @checks.admin()
    async def stickyroles(self, ctx: commands.Context) -> None:
        """Adds / removes roles to be reapplied on join"""
        pass

    @stickyroles.command()
    async def add(self, ctx: commands.Context, *, role: discord.Role) -> None:
        """Adds role to be reapplied on join"""
        guild = ctx.message.guild
        sticky_roles = await self.config.guild(guild).sticky_roles()
        if not guild.me.top_role.position > role.position:
            msg = _(
                "I don't have enough permissions to add that "
                "role. Remember to take role hierarchy in "
                "consideration."
            )
            await ctx.send(msg)
            return
        if role.id in sticky_roles:
            await ctx.send(role.name + _(" is already in the sticky roles."))
            return
        sticky_roles.append(role.id)
        await self.config.guild(guild).sticky_roles.set(sticky_roles)
        await ctx.send(_("That role will now be reapplied on join."))

    @stickyroles.command()
    async def remove(self, ctx: commands.Context, *, role: discord.Role) -> None:
        """Removes role to be reapplied on join"""
        guild = ctx.message.guild
        sticky_roles = await self.config.guild(guild).sticky_roles()
        if role.id not in sticky_roles:
            await ctx.send(_("That role was never added in the first place."))
            return
        sticky_roles.remove(role.id)
        await self.config.guild(guild).sticky_roles.set(sticky_roles)
        await ctx.send(_("That role won't be reapplied on join."))

    @stickyroles.command()
    async def clear(self, ctx: commands.Context) -> None:
        """Removes all sticky roles"""
        guild = ctx.message.guild
        await self.config.guild(guild).sticky_roles.clear()
        await self.config.guild(guild).to_reapply.clear()
        await ctx.send(_("All sticky roles have been removed."))

    @stickyroles.command(name="list")
    async def _list(self, ctx: commands.Context):
        """Lists sticky roles"""
        guild = ctx.message.guild
        roles = await self.config.guild(guild).sticky_roles()
        roles = [guild.get_role(r) for r in await self.config.guild(guild).sticky_roles()]
        roles = [r.name for r in roles if r is not None]
        if roles:
            await ctx.send(_("Sticky roles:\n\n") + ", ".join(roles))
        else:
            msg = _("No sticky roles. Add some with ") + "`{}stickyroles add`".format(ctx.prefix)
            await ctx.send(msg)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        guild = member.guild
        if version_info >= VersionInfo.from_str("3.4.0"):
            if await self.bot.cog_disabled_in_guild(self, guild):
                return
        sticky_roles = await self.config.guild(guild).sticky_roles()
        to_reapply = await self.config.guild(guild).to_reapply()
        if sticky_roles is None:
            return

        save = False

        for role in member.roles:
            if role.id in sticky_roles:
                if str(member.id) not in to_reapply:
                    to_reapply[str(member.id)] = []
                to_reapply[str(member.id)].append(role.id)
                save = True

        if save:
            await self.config.guild(guild).to_reapply.set(to_reapply)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        guild = member.guild
        if version_info >= VersionInfo.from_str("3.4.0"):
            if await self.bot.cog_disabled_in_guild(self, guild):
                return
        sticky_roles = await self.config.guild(guild).sticky_roles()
        to_reapply = await self.config.guild(guild).to_reapply()
        if to_reapply is None:
            return

        if str(member.id) not in to_reapply:
            return

        to_add = []

        for role_id in to_reapply[str(member.id)]:
            if role_id not in sticky_roles:
                continue
            role = discord.utils.get(guild.roles, id=role_id)
            if role:
                to_add.append(role)

        del to_reapply[str(member.id)]

        if to_add:
            try:
                await member.add_roles(*to_add, reason="Sticky roles")
            except discord.Forbidden:
                log.info(
                    _("Failed to add roles")
                    + _("I lack permissions to do that.")
                    + "{} ({})\n{}\n".format(member, member.id, to_add)
                )
            except discord.HTTPException:
                msg = _("Failed to add roles to ") + "{} ({})\n{}".format(
                    member, member.id, to_add
                )
                log.exception(msg)

        await self.config.guild(guild).to_reapply.set(to_reapply)
