import discord

from redbot.core import commands, checks
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import pagify, humanize_list

from .abc import MixinMeta

_ = Translator("AdventureAlert", __file__)


class TranscendedAlert(MixinMeta):
    """Alert when a transcended appears in adventure"""

    @commands.group()
    async def transcendedalert(self, ctx: commands.Context) -> None:
        """Set notifications for transcendeds appearing in adventure"""
        pass

    @transcendedalert.command(name="role", aliases=["roles"])
    @checks.mod_or_permissions(manage_roles=True)
    async def transcended_role(self, ctx: commands.Context, *, role: discord.Role) -> None:
        """Add or remove a role to be pinged when a transcended appears"""
        if role.id in await self.config.guild(ctx.guild).transcended_roles():
            async with self.config.guild(ctx.guild).transcended_roles() as data:
                data.remove(role.id)
            await ctx.send(
                _("{role} will no longer receive notifications on transcendeds.").format(role=role.name)
            )
        else:
            async with self.config.guild(ctx.guild).transcended_roles() as data:
                data.append(role.id)
            await ctx.send(
                _("{role} will now receive notifications on transcendeds.").format(role=role.name)
            )

    @commands.guild_only()
    @transcendedalert.command(name="add", aliases=["user", "users", "remove", "rem"])
    async def transcended_users(self, ctx: commands.Context) -> None:
        """Toggle transcended notifications on this server"""
        if ctx.author.id in await self.config.guild(ctx.guild).transcended_users():
            async with self.config.guild(ctx.guild).transcended_users() as data:
                data.remove(ctx.author.id)
            await ctx.send(_("You will no longer receive notifications on transcendeds."))
        else:
            async with self.config.guild(ctx.guild).transcended_users() as data:
                data.append(ctx.author.id)
            await ctx.send(_("You will now receive notifications on transcendeds."))

    @transcendedalert.command(name="global")
    async def transcended_global(self, ctx: commands.Context) -> None:
        """Toggle transcended notifications across all shared servers"""
        cur_setting = await self.config.user(ctx.author).transcended()
        await self.config.user(ctx.author).transcended.set(not cur_setting)
        if cur_setting:
            await ctx.send(_("Removed from transcended alerts across all shared servers."))
        else:
            await ctx.send(_("Added to transcended alerts across all shared servers."))

    @transcendedalert.command(name="removeuser")
    @checks.mod_or_permissions(manage_messages=True)
    async def transcended_removeusers(self, ctx: commands.Context, user_id: int) -> None:
        """Remove a specific user ID from transcended alerts"""
        if user_id in await self.config.guild(ctx.guild).transcended_users():
            async with self.config.guild(ctx.guild).transcended_users() as data:
                data.remove(user_id)
            await ctx.send(
                _("{user_id} will no longer receive notifications on transcendeds.").format(
                    user_id=user_id
                )
            )
        else:
            await ctx.send(
                _("{user_id} is not receiving notifications on transcendeds.").format(user_id=user_id)
            )

    @commands.Cog.listener()
    async def on_adventure_transcended(self, ctx: commands.Context) -> None:
        roles = [f"<@&{rid}>" for rid in await self.config.guild(ctx.guild).transcended_roles()]
        users = [f"<@!{uid}>" for uid in await self.config.guild(ctx.guild).transcended_users()]
        guild_members = [m.id for m in ctx.guild.members]
        all_users = await self.config.all_users()
        for u_id, data in all_users.items():
            user_mention = f"<@!{u_id}>"
            if u_id in guild_members and data["transcended"] and user_mention not in users:
                users.append(user_mention)
        if roles or users:
            msg = (
                f"{humanize_list(roles) if roles else ''} "
                + f"{humanize_list(users) if users else ''} "
                + _("A transcended has appeared!")
            )
            for page in pagify(msg):
                await ctx.send(page, **self.sanitize)
