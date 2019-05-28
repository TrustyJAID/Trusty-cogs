import discord

from redbot.core import commands, checks, Config
from redbot.core.utils.chat_formatting import pagify

listener = getattr(commands.Cog, "listener", None)  # red 3.0 backwards compatibility support

if listener is None:  # thanks Sinbad
    def listener(name=None):
        return lambda x: x


class AdventureAlert(commands.Cog):
    """Alert when a dragon appears in adventure"""

    __version__ = "1.0.0"
    __author__ = "TrustyJAID"

    def __init__(self, bot):
        self.bot = bot
        default_guild = {
            "roles": [],
            "users": [],
            "adventure_roles": [],
            "adventure_users": [],
            "cart_users": [],
            "cart_roles": [],
            "miniboss_users": [],
            "miniboss_roles": []
        }
        self.config = Config.get_conf(self, 154497072148643840, force_registration=True)
        self.config.register_guild(**default_guild)

    @commands.group()
    async def dragonalert(self, ctx):
        """Set dragon alert roles for adventure"""
        pass

    @dragonalert.command()
    @checks.mod_or_permissions(manage_messages=True)
    async def role(self, ctx, *, role: discord.Role):
        """Add or remove a role to be pinged when a dragon appears"""
        if role.id in await self.config.guild(ctx.guild).roles():
            async with self.config.guild(ctx.guild).roles() as data:
                data.remove(role.id)
            await ctx.send(f"{role.name} will no longer receive notifications on dragons.")
        else:
            async with self.config.guild(ctx.guild).roles() as data:
                data.append(role.id)
            await ctx.tick()

    @dragonalert.command(name="add", aliases=["user", "users", "remove", "rem"])
    async def addusers(self, ctx):
        """Add or remove yourself from dragon role pings"""
        if ctx.author.id in await self.config.guild(ctx.guild).users():
            async with self.config.guild(ctx.guild).users() as data:
                data.remove(ctx.author.id)
            await ctx.send("You will no longer receive notifications on dragons.")
        else:
            async with self.config.guild(ctx.guild).users() as data:
                data.append(ctx.author.id)
            await ctx.tick()

    @commands.group()
    async def adventurealert(self, ctx):
        """Set dragon alert roles for adventure"""
        pass

    @adventurealert.command(name="role", aliases=["roles"])
    @checks.mod_or_permissions(manage_messages=True)
    async def adventure_role(self, ctx, *, role: discord.Role):
        """Add or remove a role to be pinged when a dragon appears"""
        if role.id in await self.config.guild(ctx.guild).adventure_roles():
            async with self.config.guild(ctx.guild).adventure_roles() as data:
                data.remove(role.id)
            await ctx.send(f"{role.name} will no longer receive notifications on adventures.")
        else:
            async with self.config.guild(ctx.guild).adventure_roles() as data:
                data.append(role.id)
            await ctx.tick()

    @adventurealert.command(name="add", aliases=["user", "users", "remove", "rem"])
    async def adventure_users(self, ctx):
        """Add or remove yourself from dragon role pings"""
        if ctx.author.id in await self.config.guild(ctx.guild).adventure_users():
            async with self.config.guild(ctx.guild).adventure_users() as data:
                data.remove(ctx.author.id)
            await ctx.send("You will no longer receive notifications on adventures.")
        else:
            async with self.config.guild(ctx.guild).adventure_users() as data:
                data.append(ctx.author.id)
            await ctx.tick()

    @commands.group()
    async def cartalert(self, ctx):
        """Set notifications for carts appearning"""
        pass

    @cartalert.command(name="role", aliases=["roles"])
    @checks.mod_or_permissions(manage_messages=True)
    async def cart_role(self, ctx, *, role: discord.Role):
        """Add or remove a role to be pinged when the cart appears"""
        if role.id in await self.config.guild(ctx.guild).cart_roles():
            async with self.config.guild(ctx.guild).cart_roles() as data:
                data.remove(role.id)
            await ctx.send(f"{role.name} will no longer receive notifications on carts.")
        else:
            async with self.config.guild(ctx.guild).cart_roles() as data:
                data.append(role.id)
            await ctx.tick()

    @cartalert.command(name="add", aliases=["user", "users", "remove", "rem"])
    async def cart_users(self, ctx):
        """Add or remove yourself from cart notifications"""
        if ctx.author.id in await self.config.guild(ctx.guild).cart_users():
            async with self.config.guild(ctx.guild).cart_users() as data:
                data.remove(ctx.author.id)
            await ctx.send("You will no longer receive notifications on carts.")
        else:
            async with self.config.guild(ctx.guild).cart_users() as data:
                data.append(ctx.author.id)
            await ctx.tick()

    @commands.group()
    async def minibossalert(self, ctx):
        """Set notifications for minibosses"""
        pass

    @minibossalert.command(name="role", aliases=["roles"])
    @checks.mod_or_permissions(manage_messages=True)
    async def miniboss_role(self, ctx, *, role: discord.Role):
        """Add or remove a role to be pinged when the cart appears"""
        if role.id in await self.config.guild(ctx.guild).miniboss_roles():
            async with self.config.guild(ctx.guild).miniboss_roles() as data:
                data.remove(role.id)
            await ctx.send(f"{role.name} will no longer receive notifications on minibosses.")
        else:
            async with self.config.guild(ctx.guild).miniboss_roles() as data:
                data.append(role.id)
            await ctx.tick()

    @minibossalert.command(name="add", aliases=["user", "users", "remove", "rem"])
    async def miniboss_users(self, ctx):
        """Add or remove yourself from miniboss notifications"""
        if ctx.author.id in await self.config.guild(ctx.guild).miniboss_users():
            async with self.config.guild(ctx.guild).miniboss_users() as data:
                data.remove(ctx.author.id)
            await ctx.send("You will no longer receive notifications on minibosses.")
        else:
            async with self.config.guild(ctx.guild).miniboss_users() as data:
                data.append(ctx.author.id)
            await ctx.tick()

    @listener()
    async def on_adventure(self, ctx):
        roles = ", ".join(
            f"<@&{rid}>" for rid in await self.config.guild(ctx.guild).adventure_roles()
        )
        users = ", ".join(
            f"<@{rid}>" for rid in await self.config.guild(ctx.guild).adventure_users()
        )
        if roles or users:
            msg = (
                f"{roles+', ' if roles else ''} {users+', ' if users else ''} "
                "An adventure has started, come join!"
            )
            for page in pagify(msg):
                await ctx.send(page)

    @listener()
    async def on_adventure_boss(self, ctx):
        roles = ", ".join(
            f"<@&{rid}>" for rid in await self.config.guild(ctx.guild).roles()
        )
        users = ", ".join(
            f"<@{rid}>" for rid in await self.config.guild(ctx.guild).users()
        )
        if roles or users:
            msg = (
                f"{roles+', ' if roles else ''} {users+', ' if users else ''} "
                "A dragon has appeared! Come help!"
            )
            for page in pagify(msg):
                await ctx.send(page)

    @listener()
    async def on_adventure_miniboss(self, ctx):
        roles = ", ".join(
            f"<@&{rid}>" for rid in await self.config.guild(ctx.guild).miniboss_roles()
        )
        users = ", ".join(
            f"<@{rid}>" for rid in await self.config.guild(ctx.guild).miniboss_users()
        )
        if roles or users:
            msg = (
                f"{roles+', ' if roles else ''} {users+', ' if users else ''} "
                "A miniboss has appeared! Quick equip the right gear!"
            )
            for page in pagify(msg):
                await ctx.send(page)

    @listener()
    async def on_adventure_cart(self, ctx):
        roles = ", ".join(
            f"<@&{rid}>" for rid in await self.config.guild(ctx.guild).cart_roles()
        )
        users = ", ".join(
            f"<@{rid}>" for rid in await self.config.guild(ctx.guild).cart_users()
        )
        if roles or users:
            msg = (
                f"{roles+', ' if roles else ''} {users+', ' if users else ''} "
                "The cart has come around, come buy stuff!"
            )
            for page in pagify(msg):
                await ctx.send(page)
