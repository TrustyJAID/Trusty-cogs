import discord

from redbot.core import commands, checks, Config
from redbot.core.utils.chat_formatting import pagify, humanize_list


class AdventureAlert(commands.Cog):
    """Alert when a dragon appears in adventure"""

    __version__ = "1.2.0"
    __author__ = ["TrustyJAID"]

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
            "miniboss_roles": [],
        }
        self.config = Config.get_conf(self, 154497072148643840, force_registration=True)
        self.config.register_guild(**default_guild)
        self.config.register_user(adventure=False, miniboss=False, dragon=False, cart=False)

    def format_help_for_context(self, ctx: commands.Context) -> str:
        """
            Thanks Sinbad!
        """
        pre_processed = super().format_help_for_context(ctx)
        return f"{pre_processed}\n\nCog Version: {self.__version__}"

    @commands.group()
    async def dragonalert(self, ctx: commands.Context) -> None:
        """Set notifications for dragons appearing in adventure"""
        pass

    @dragonalert.command()
    @checks.mod_or_permissions(manage_messages=True)
    async def role(self, ctx: commands.Context, *, role: discord.Role) -> None:
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
    async def addusers(self, ctx: commands.Context) -> None:
        """Toggle dragon notifications on this server"""
        if ctx.author.id in await self.config.guild(ctx.guild).users():
            async with self.config.guild(ctx.guild).users() as data:
                data.remove(ctx.author.id)
            await ctx.send("You will no longer receive notifications on dragons.")
        else:
            async with self.config.guild(ctx.guild).users() as data:
                data.append(ctx.author.id)
            await ctx.tick()

    @dragonalert.command(name="global")
    async def addglobal(self, ctx: commands.Context) -> None:
        """Toggle dragon notifications across all shared servers"""
        cur_setting = await self.config.user(ctx.author).dragon()
        await self.config.user(ctx.author).dragon.set(not cur_setting)
        if cur_setting:
            await ctx.send("Removed from dragon alerts across all shared servers.")
        else:
            await ctx.send("Added to dragon alerts across all shared servers.")

    @dragonalert.command(name="removeuser")
    @checks.mod_or_permissions(manage_messages=True)
    async def removeusers(self, ctx: commands.Context, user_id: int) -> None:
        """Remove a specific user ID from dragon alerts"""
        if user_id in await self.config.guild(ctx.guild).users():
            async with self.config.guild(ctx.guild).users() as data:
                data.remove(user_id)
            await ctx.send(f"{user_id} will no longer receive notifications on dragons.")
        else:
            await ctx.send(f"{user_id} is not receiving notifications on dragons.")

    @commands.group()
    async def adventurealert(self, ctx: commands.Context) -> None:
        """Set notifications for all adventures"""
        pass

    @adventurealert.command(name="role", aliases=["roles"])
    @checks.mod_or_permissions(manage_messages=True)
    async def adventure_role(self, ctx: commands.Context, *, role: discord.Role) -> None:
        """Add or remove a role to be pinged when a dragon appears"""
        if role.id in await self.config.guild(ctx.guild).adventure_roles():
            async with self.config.guild(ctx.guild).adventure_roles() as data:
                data.remove(role.id)
            await ctx.send(f"{role.name} will no longer receive notifications on adventures.")
        else:
            async with self.config.guild(ctx.guild).adventure_roles() as data:
                data.append(role.id)
            await ctx.tick()

    @adventurealert.command(name="add", aliases=["user", "users", "remove", "rem", "toggle"])
    async def adventure_users(self, ctx: commands.Context) -> None:
        """Toggle adventure notifications in this server"""
        if ctx.author.id in await self.config.guild(ctx.guild).adventure_users():
            async with self.config.guild(ctx.guild).adventure_users() as data:
                data.remove(ctx.author.id)
            await ctx.send("You will no longer receive notifications on adventures.")
        else:
            async with self.config.guild(ctx.guild).adventure_users() as data:
                data.append(ctx.author.id)
            await ctx.tick()

    @adventurealert.command(name="global")
    async def adventure_global(self, ctx: commands.Context) -> None:
        """Toggle adventure notifications in all shared servers"""
        cur_setting = await self.config.user(ctx.author).adventure()
        await self.config.user(ctx.author).adventure.set(not cur_setting)
        if cur_setting:
            await ctx.send("Removed from adventure alerts across all shared servers.")
        else:
            await ctx.send("Added to adventure alerts across all shared servers.")

    @adventurealert.command(name="removeuser")
    @checks.mod_or_permissions(manage_messages=True)
    async def adventure_removeusers(self, ctx: commands.Context, user_id: int) -> None:
        """Remove a specific user ID from adventure alerts"""
        if user_id in await self.config.guild(ctx.guild).adventure_users():
            async with self.config.guild(ctx.guild).adventure_users() as data:
                data.remove(user_id)
            await ctx.send(f"{user_id} will no longer receive notifications on adventures.")
        else:
            await ctx.send(f"{user_id} is not receiving notifications on adventures.")

    @commands.group()
    async def cartalert(self, ctx):
        """Set notifications for carts appearning"""
        pass

    @cartalert.command(name="role", aliases=["roles"])
    @checks.mod_or_permissions(manage_messages=True)
    async def cart_role(self, ctx: commands.Context, *, role: discord.Role) -> None:
        """Add or remove a role to be pinged when the cart appears"""
        if role.id in await self.config.guild(ctx.guild).cart_roles():
            async with self.config.guild(ctx.guild).cart_roles() as data:
                data.remove(role.id)
            await ctx.send(f"{role.name} will no longer receive notifications on carts.")
        else:
            async with self.config.guild(ctx.guild).cart_roles() as data:
                data.append(role.id)
            await ctx.tick()

    @cartalert.command(name="add", aliases=["user", "users", "remove", "rem", "toggle"])
    async def cart_users(self, ctx: commands.Context) -> None:
        """Toggle cart notifications on this server"""
        if ctx.author.id in await self.config.guild(ctx.guild).cart_users():
            async with self.config.guild(ctx.guild).cart_users() as data:
                data.remove(ctx.author.id)
            await ctx.send("You will no longer receive notifications on carts.")
        else:
            async with self.config.guild(ctx.guild).cart_users() as data:
                data.append(ctx.author.id)
            await ctx.tick()

    @cartalert.command(name="global")
    async def cart_global(self, ctx: commands.Context) -> None:
        """Toggle cart notifications in all shared servers"""
        cur_setting = await self.config.user(ctx.author).cart()
        await self.config.user(ctx.author).cart.set(not cur_setting)
        if cur_setting:
            await ctx.send("Removed from cart alerts across all shared servers.")
        else:
            await ctx.send("Added to cart alerts across all shared servers.")

    @cartalert.command(name="removeuser")
    @checks.mod_or_permissions(manage_messages=True)
    async def cart_removeusers(self, ctx: commands.Context, user_id: int) -> None:
        """Remove a specific user ID from cart alerts"""
        if user_id in await self.config.guild(ctx.guild).cart_users():
            async with self.config.guild(ctx.guild).cart_users() as data:
                data.remove(user_id)
            await ctx.send(f"{user_id} will no longer receive notifications on adventures.")
        else:
            await ctx.send(f"{user_id} is not receiving notifications on adventures.")

    @commands.group()
    async def minibossalert(self, ctx: commands.Context):
        """Set notifications for minibosses appearing in adventure"""
        pass

    @minibossalert.command(name="role", aliases=["roles"])
    @checks.mod_or_permissions(manage_messages=True)
    async def miniboss_role(self, ctx: commands.Context, *, role: discord.Role) -> None:
        """Add or remove a role to be pinged when the cart appears"""
        if role.id in await self.config.guild(ctx.guild).miniboss_roles():
            async with self.config.guild(ctx.guild).miniboss_roles() as data:
                data.remove(role.id)
            await ctx.send(f"{role.name} will no longer receive notifications on minibosses.")
        else:
            async with self.config.guild(ctx.guild).miniboss_roles() as data:
                data.append(role.id)
            await ctx.tick()

    @minibossalert.command(name="add", aliases=["user", "users", "remove", "rem", "toggle"])
    async def miniboss_users(self, ctx: commands.Context) -> None:
        """Toggle miniboss notifications in this server"""
        if ctx.author.id in await self.config.guild(ctx.guild).miniboss_users():
            async with self.config.guild(ctx.guild).miniboss_users() as data:
                data.remove(ctx.author.id)
            await ctx.send("You will no longer receive notifications on minibosses.")
        else:
            async with self.config.guild(ctx.guild).miniboss_users() as data:
                data.append(ctx.author.id)
            await ctx.tick()

    @minibossalert.command(name="global")
    async def miniboss_global(self, ctx: commands.Context) -> None:
        """Toggle miniboss notifications in all shared servers"""
        cur_setting = await self.config.user(ctx.author).cart()
        await self.config.user(ctx.author).cart.set(not cur_setting)
        if cur_setting:
            await ctx.send("Removed from miniboss alerts across all shared servers.")
        else:
            await ctx.send("Added to cart miniboss across all shared servers.")

    @minibossalert.command(name="removeuser")
    @checks.mod_or_permissions(manage_messages=True)
    async def miniboss_removeusers(self, ctx: commands.Context, user_id: int) -> None:
        """Remove a specific user ID from miniboss alerts"""
        if user_id in await self.config.guild(ctx.guild).miniboss_users():
            async with self.config.guild(ctx.guild).miniboss_users() as data:
                data.remove(user_id)
            await ctx.send(f"{user_id} will no longer receive notifications on minibosses.")
        else:
            await ctx.send(f"{user_id} is not receiving notifications on minibosses.")

    @commands.Cog.listener()
    async def on_adventure(self, ctx: commands.Context) -> None:
        roles = [f"<@&{rid}>" for rid in await self.config.guild(ctx.guild).adventure_roles()]
        users = [f"<@!{uid}>" for uid in await self.config.guild(ctx.guild).adventure_users()]
        guild_members = [m.id for m in ctx.guild.members]
        all_users = await self.config.all_users()
        for u_id, data in all_users.items():
            user_mention = f"<@!{u_id}>"
            if u_id in guild_members and data["adventure"] and user_mention not in users:
                users.append(user_mention)
        if roles or users:
            msg = (
                f"{humanize_list(roles) if roles else ''} "
                f"{humanize_list(users) if users else ''} "
                "An adventure has started, come join!"
            )
            for page in pagify(msg):
                await ctx.send(page)

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
                f"{humanize_list(users) if users else ''} "
                "An adventure has started, come join!"
            )
            for page in pagify(msg):
                await ctx.send(page)

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
                f"{humanize_list(users) if users else ''} "
                "An adventure has started, come join!"
            )
            for page in pagify(msg):
                await ctx.send(page)

    @commands.Cog.listener()
    async def on_adventure_cart(self, ctx: commands.Context) -> None:
        roles = [f"<@&{rid}>" for rid in await self.config.guild(ctx.guild).cart_roles()]
        users = [f"<@!{uid}>" for uid in await self.config.guild(ctx.guild).cart_users()]
        guild_members = [m.id for m in ctx.guild.members]
        all_users = await self.config.all_users()
        for u_id, data in all_users.items():
            user_mention = f"<@!{u_id}>"
            if u_id in guild_members and data["cart"] and user_mention not in users:
                users.append(user_mention)
        if roles or users:
            msg = (
                f"{humanize_list(roles) if roles else ''} "
                f"{humanize_list(users) if users else ''} "
                "An adventure has started, come join!"
            )
            for page in pagify(msg):
                await ctx.send(page)
