import discord
from redbot import VersionInfo, version_info
from redbot.core import checks, commands
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import humanize_list, pagify

from .abc import MixinMeta

_ = Translator("AdventureAlert", __file__)


class AscendedAlert(MixinMeta):
    """Alert when a ascended appears in adventure"""

    @commands.group()
    async def ascendedalert(self, ctx: commands.Context) -> None:
        """Set notifications for ascendeds appearing in adventure"""
        pass

    @ascendedalert.command(name="role", aliases=["roles"])
    @checks.mod_or_permissions(manage_roles=True)
    async def ascended_role(self, ctx: commands.Context, *, role: discord.Role) -> None:
        """Add or remove a role to be pinged when an ascended appears"""
        if role.id in await self.config.guild(ctx.guild).ascended_roles():
            async with self.config.guild(ctx.guild).ascended_roles() as data:
                data.remove(role.id)
            await ctx.send(
                _("{role} will no longer receive notifications on ascendeds.").format(
                    role=role.name
                )
            )
        else:
            async with self.config.guild(ctx.guild).ascended_roles() as data:
                data.append(role.id)
            await ctx.send(
                _("{role} will now receive notifications on ascendeds.").format(role=role.name)
            )

    @commands.guild_only()
    @ascendedalert.command(name="add", aliases=["user", "users", "remove", "rem"])
    async def ascended_users(self, ctx: commands.Context) -> None:
        """Toggle ascended notifications on this server"""
        if ctx.author.id in await self.config.guild(ctx.guild).ascended_users():
            async with self.config.guild(ctx.guild).ascended_users() as data:
                data.remove(ctx.author.id)
            await ctx.send(_("You will no longer receive notifications on ascendeds."))
        else:
            async with self.config.guild(ctx.guild).ascended_users() as data:
                data.append(ctx.author.id)
            await ctx.send(_("You will now receive notifications on ascendeds."))

    @ascendedalert.command(name="global")
    async def ascended_global(self, ctx: commands.Context) -> None:
        """Toggle ascended notifications across all shared servers"""
        cur_setting = await self.config.user(ctx.author).ascended()
        await self.config.user(ctx.author).ascended.set(not cur_setting)
        if cur_setting:
            await ctx.send(_("Removed from ascended alerts across all shared servers."))
        else:
            await ctx.send(_("Added to ascended alerts across all shared servers."))

    @ascendedalert.command(name="removeuser")
    @checks.mod_or_permissions(manage_messages=True)
    async def ascended_removeusers(self, ctx: commands.Context, user_id: int) -> None:
        """Remove a specific user ID from ascended alerts"""
        if user_id in await self.config.guild(ctx.guild).ascended_users():
            async with self.config.guild(ctx.guild).ascended_users() as data:
                data.remove(user_id)
            await ctx.send(
                _("{user_id} will no longer receive notifications on ascendeds.").format(
                    user_id=user_id
                )
            )
        else:
            await ctx.send(
                _("{user_id} is not receiving notifications on ascendeds.").format(user_id=user_id)
            )

    @commands.Cog.listener()
    async def on_adventure_ascended(self, ctx: commands.Context) -> None:
        if version_info >= VersionInfo.from_str("3.4.0"):
            if await self.bot.cog_disabled_in_guild(self, ctx.guild):
                return
        roles = [f"<@&{rid}>" for rid in await self.config.guild(ctx.guild).ascended_roles()]
        users = [f"<@!{uid}>" for uid in await self.config.guild(ctx.guild).ascended_users()]
        guild_members = [m.id for m in ctx.guild.members]
        all_users = await self.config.all_users()
        for u_id, data in all_users.items():
            user_mention = f"<@!{u_id}>"
            if u_id in guild_members and data["ascended"] and user_mention not in users:
                users.append(user_mention)
        if roles or users:
            msg = (
                f"{humanize_list(roles) if roles else ''} "
                + f"{humanize_list(users) if users else ''} "
                + _("An Ascended has appeared!")
            )
            for page in pagify(msg):
                await ctx.send(page, **self.sanitize)
