import discord

from redbot.core import commands, checks
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import pagify, humanize_list

from .abc import MixinMeta

_ = Translator("AdventureAlert", __file__)


class BossAlert(MixinMeta):
    """Alert when a boss appears in adventure"""

    @commands.group(aliases=["bossalert"])
    async def dragonalert(self, ctx: commands.Context) -> None:
        """Set notifications for dragons appearing in adventure"""
        pass

    @dragonalert.command(name="role", aliases=["roles"])
    @checks.mod_or_permissions(manage_roles=True)
    async def boss_role(self, ctx: commands.Context, *, role: discord.Role) -> None:
        """Add or remove a role to be pinged when a dragon appears"""
        if role.id in await self.config.guild(ctx.guild).roles():
            async with self.config.guild(ctx.guild).roles() as data:
                data.remove(role.id)
            await ctx.send(
                _("{role} will no longer receive notifications on dragons.").format(role=role.name)
            )
        else:
            async with self.config.guild(ctx.guild).roles() as data:
                data.append(role.id)
            await ctx.send(
                _("{role} will now receive notifications on dragons.").format(role=role.name)
            )

    @commands.guild_only()
    @dragonalert.command(name="add", aliases=["user", "users", "remove", "rem"])
    async def boss_users(self, ctx: commands.Context) -> None:
        """Toggle dragon notifications on this server"""
        if ctx.author.id in await self.config.guild(ctx.guild).users():
            async with self.config.guild(ctx.guild).users() as data:
                data.remove(ctx.author.id)
            await ctx.send(_("You will no longer receive notifications on dragons."))
        else:
            async with self.config.guild(ctx.guild).users() as data:
                data.append(ctx.author.id)
            await ctx.send(_("You will now receive notifications on dragons."))

    @dragonalert.command(name="global")
    async def boss_global(self, ctx: commands.Context) -> None:
        """Toggle dragon notifications across all shared servers"""
        cur_setting = await self.config.user(ctx.author).dragon()
        await self.config.user(ctx.author).dragon.set(not cur_setting)
        if cur_setting:
            await ctx.send(_("Removed from dragon alerts across all shared servers."))
        else:
            await ctx.send(_("Added to dragon alerts across all shared servers."))

    @dragonalert.command(name="removeuser")
    @checks.mod_or_permissions(manage_messages=True)
    async def boss_removeusers(self, ctx: commands.Context, user_id: int) -> None:
        """Remove a specific user ID from dragon alerts"""
        if user_id in await self.config.guild(ctx.guild).users():
            async with self.config.guild(ctx.guild).users() as data:
                data.remove(user_id)
            await ctx.send(
                _("{user_id} will no longer receive notifications on dragons.").format(
                    user_id=user_id
                )
            )
        else:
            await ctx.send(
                _("{user_id} is not receiving notifications on dragons.").format(user_id=user_id)
            )

    @commands.Cog.listener()
    async def on_adventure_boss(self, ctx: commands.Context) -> None:
        roles = [f"<@&{rid}>" for rid in await self.config.guild(ctx.guild).roles()]
        users = [f"<@!{uid}>" for uid in await self.config.guild(ctx.guild).users()]
        guild_members = [m.id for m in ctx.guild.members]
        all_users = await self.config.all_users()
        for u_id, data in all_users.items():
            user_mention = f"<@!{u_id}>"
            if u_id in guild_members and data["dragon"] and user_mention not in users:
                users.append(user_mention)
        if roles or users:
            msg = (
                f"{humanize_list(roles) if roles else ''} "
                + f"{humanize_list(users) if users else ''} "
                + _("A Dragon has appeared!")
            )
            for page in pagify(msg):
                await ctx.send(page, **self.sanitize)
