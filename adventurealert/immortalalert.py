import discord

from redbot.core import commands, checks
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import pagify, humanize_list

from .abc import MixinMeta

_ = Translator("AdventureAlert", __file__)


class ImmortalAlert(MixinMeta):
    """Alert when a immortal appears in adventure"""

    @commands.group()
    async def immortalalert(self, ctx: commands.Context) -> None:
        """Set notifications for immortals appearing in adventure"""
        pass

    @immortalalert.command(name="role", aliases=["roles"])
    @checks.mod_or_permissions(manage_roles=True)
    async def immortal_role(self, ctx: commands.Context, *, role: discord.Role) -> None:
        """Add or remove a role to be pinged when an immortal appears"""
        if role.id in await self.config.guild(ctx.guild).immortal_roles():
            async with self.config.guild(ctx.guild).immortal_roles() as data:
                data.remove(role.id)
            await ctx.send(
                _("{role} will no longer receive notifications on immortals.").format(role=role.name)
            )
        else:
            async with self.config.guild(ctx.guild).immortal_roles() as data:
                data.append(role.id)
            await ctx.send(
                _("{role} will now receive notifications on immortals.").format(role=role.name)
            )

    @commands.guild_only()
    @immortalalert.command(name="add", aliases=["user", "users", "remove", "rem"])
    async def immortal_users(self, ctx: commands.Context) -> None:
        """Toggle immortal notifications on this server"""
        if ctx.author.id in await self.config.guild(ctx.guild).immortal_users():
            async with self.config.guild(ctx.guild).immortal_users() as data:
                data.remove(ctx.author.id)
            await ctx.send(_("You will no longer receive notifications on immortals."))
        else:
            async with self.config.guild(ctx.guild).immortal_users() as data:
                data.append(ctx.author.id)
            await ctx.send(_("You will now receive notifications on immortals."))

    @immortalalert.command(name="global")
    async def immortal_global(self, ctx: commands.Context) -> None:
        """Toggle immortal notifications across all shared servers"""
        cur_setting = await self.config.user(ctx.author).immortal()
        await self.config.user(ctx.author).immortal.set(not cur_setting)
        if cur_setting:
            await ctx.send(_("Removed from immortal alerts across all shared servers."))
        else:
            await ctx.send(_("Added to immortal alerts across all shared servers."))

    @immortalalert.command(name="removeuser")
    @checks.mod_or_permissions(manage_messages=True)
    async def immortal_removeusers(self, ctx: commands.Context, user_id: int) -> None:
        """Remove a specific user ID from immortal alerts"""
        if user_id in await self.config.guild(ctx.guild).immortal_users():
            async with self.config.guild(ctx.guild).immortal_users() as data:
                data.remove(user_id)
            await ctx.send(
                _("{user_id} will no longer receive notifications on immortals.").format(
                    user_id=user_id
                )
            )
        else:
            await ctx.send(
                _("{user_id} is not receiving notifications on immortals.").format(user_id=user_id)
            )

    @commands.Cog.listener()
    async def on_adventure_immortal(self, ctx: commands.Context) -> None:
        roles = [f"<@&{rid}>" for rid in await self.config.guild(ctx.guild).immortal_roles()]
        users = [f"<@!{uid}>" for uid in await self.config.guild(ctx.guild).immortal_users()]
        guild_members = [m.id for m in ctx.guild.members]
        all_users = await self.config.all_users()
        for u_id, data in all_users.items():
            user_mention = f"<@!{u_id}>"
            if u_id in guild_members and data["immortal"] and user_mention not in users:
                users.append(user_mention)
        if roles or users:
            msg = (
                f"{humanize_list(roles) if roles else ''} "
                + f"{humanize_list(users) if users else ''} "
                + _("An immortal has appeared!")
            )
            for page in pagify(msg):
                await ctx.send(page, **self.sanitize)
