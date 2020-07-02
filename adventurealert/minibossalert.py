import discord

from redbot.core import commands, checks
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import pagify, humanize_list

from .abc import MixinMeta

_ = Translator("AdventureAlert", __file__)


class MinibossAlert(MixinMeta):
    """Alert when a miniboss appears in adventure"""

    @commands.group()
    async def minibossalert(self, ctx: commands.Context):
        """Set notifications for minibosses appearing in adventure"""
        pass

    @minibossalert.command(name="role", aliases=["roles"])
    @checks.mod_or_permissions(manage_roles=True)
    async def miniboss_role(self, ctx: commands.Context, *, role: discord.Role) -> None:
        """Add or remove a role to be pinged when the miniboss appears"""
        if role.id in await self.config.guild(ctx.guild).miniboss_roles():
            async with self.config.guild(ctx.guild).miniboss_roles() as data:
                data.remove(role.id)
            await ctx.send(
                _("{role} will no longer receive notifications on minibosses.").format(
                    role=role.name
                )
            )
        else:
            async with self.config.guild(ctx.guild).miniboss_roles() as data:
                data.append(role.id)
            await ctx.send(
                _("{role} will now receive notifications on minibosses.").format(
                    role=role.name
                )
            )

    @commands.guild_only()
    @minibossalert.command(name="add", aliases=["user", "users", "remove", "rem", "toggle"])
    async def miniboss_users(self, ctx: commands.Context) -> None:
        """Toggle miniboss notifications in this server"""
        if ctx.author.id in await self.config.guild(ctx.guild).miniboss_users():
            async with self.config.guild(ctx.guild).miniboss_users() as data:
                data.remove(ctx.author.id)
            await ctx.send(_("You will no longer receive notifications on minibosses."))
        else:
            async with self.config.guild(ctx.guild).miniboss_users() as data:
                data.append(ctx.author.id)
            await ctx.send(_("You will now receive notifications on minibosses."))

    @minibossalert.command(name="global")
    async def miniboss_global(self, ctx: commands.Context) -> None:
        """Toggle miniboss notifications in all shared servers"""
        cur_setting = await self.config.user(ctx.author).miniboss()
        await self.config.user(ctx.author).miniboss.set(not cur_setting)
        if cur_setting:
            await ctx.send(_("Removed from miniboss alerts across all shared servers."))
        else:
            await ctx.send(_("Added to miniboss alerts across all shared servers."))

    @minibossalert.command(name="removeuser")
    @checks.mod_or_permissions(manage_messages=True)
    async def miniboss_removeusers(self, ctx: commands.Context, user_id: int) -> None:
        """Remove a specific user ID from miniboss alerts"""
        if user_id in await self.config.guild(ctx.guild).miniboss_users():
            async with self.config.guild(ctx.guild).miniboss_users() as data:
                data.remove(user_id)
            await ctx.send(
                _("{user_id} will no longer receive notifications on minibosses.").format(
                    user_id=user_id
                )
            )
        else:
            await ctx.send(
                _("{user_id} is not receiving notifications on minibosses.").format(
                    user_id=user_id
                )
            )

    @commands.Cog.listener()
    async def on_adventure_miniboss(self, ctx: commands.Context) -> None:
        roles = [f"<@&{rid}>" for rid in await self.config.guild(ctx.guild).miniboss_roles()]
        users = [f"<@!{uid}>" for uid in await self.config.guild(ctx.guild).miniboss_users()]
        guild_members = [m.id for m in ctx.guild.members]
        all_users = await self.config.all_users()
        for u_id, data in all_users.items():
            user_mention = f"<@!{u_id}>"
            if u_id in guild_members and data["miniboss"] and user_mention not in users:
                users.append(user_mention)
        if roles or users:
            msg = (
                f"{humanize_list(roles) if roles else ''} "
                + f"{humanize_list(users) if users else ''} "
                + _("A miniboss has appeared, come join!")
            )
            for page in pagify(msg):
                await ctx.send(page, **self.sanitize)
