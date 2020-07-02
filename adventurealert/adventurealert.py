import discord

from abc import ABC
from redbot import VersionInfo, version_info
from redbot.core import commands, checks, Config
from redbot.core.i18n import Translator, cog_i18n
from redbot.core.utils.chat_formatting import pagify, humanize_list

from .bossalert import BossAlert
from .minibossalert import MinibossAlert
from .cartalert import CartAlert
from .ascendedalert import AscendedAlert
from .transcendedalert import TranscendedAlert
from .immortalalert import ImmortalAlert
from .possessedalert import PossessedAlert


_ = Translator("AdventureAlert", __file__)


class CompositeMetaClass(type(commands.Cog), type(ABC)):
    """
    This allows the metaclass used for proper type detection to
    coexist with discord.py's metaclass

    This is from
    https://github.com/Cog-Creators/Red-DiscordBot/blob/V3/develop/redbot/cogs/mod/mod.py#L23
    """

    pass


@cog_i18n(_)
class AdventureAlert(
    BossAlert,
    MinibossAlert,
    CartAlert,
    AscendedAlert,
    TranscendedAlert,
    ImmortalAlert,
    PossessedAlert,
    commands.Cog,
    metaclass=CompositeMetaClass,
):
    """Alert when a dragon appears in adventure"""

    __version__ = "1.4.0"
    __author__ = ["TrustyJAID"]

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, 154497072148643840, force_registration=True)
        self.config.register_guild(
            roles=[],
            users=[],
            adventure_roles=[],
            adventure_users=[],
            cart_users=[],
            cart_roles=[],
            miniboss_users=[],
            miniboss_roles=[],
            ascended_users=[],
            ascended_roles=[],
            transcended_users=[],
            transcended_roles=[],
            immortal_users=[],
            immortal_roles=[],
            possessed_users=[],
            possessed_roles=[],
        )
        self.config.register_user(
            adventure=False,
            miniboss=False,
            dragon=False,
            cart=False,
            ascended=False,
            transcended=False,
            immortal=False,
            possessed=False,
        )
        self.sanitize = {}

    def format_help_for_context(self, ctx: commands.Context) -> str:
        """
            Thanks Sinbad!
        """
        pre_processed = super().format_help_for_context(ctx)
        return f"{pre_processed}\n\nCog Version: {self.__version__}"

    @commands.group()
    async def adventurealert(self, ctx: commands.Context) -> None:
        """Set notifications for all adventures"""
        pass

    @adventurealert.command(name="settings", aliases=["setting"])
    async def alert_settings(self, ctx: commands.Context):
        """
            Shows a list of servers you have alerts
        """
        global_settings = await self.config.user(ctx.author).all()
        msg = ""
        if any(v for k, v in global_settings.items()):
            msg += _("__**Global Notifications**__: {g_set}\n\n").format(
                g_set=humanize_list([k.title() for k, v in global_settings.items() if v])
            )
        all_data: dict = {
            "cart_servers": ([], _("Cart Notifications")),
            "adventure_servers": ([], _("Adventure Notifications")),
            "boss_servers": ([], _("Dragon Notifications")),
            "miniboss_servers": ([], _("Miniboss Notifications")),
        }
        all_guilds = await self.config.all_guilds()
        for g_id, settings in all_guilds.items():
            guild = self.bot.get_guild(g_id)
            if not guild:
                continue
            if ctx.author.id in settings["users"]:
                all_data["boss_servers"][0].append(guild.name)
            if ctx.author.id in settings["adventure_users"]:
                all_data["adventure_servers"][0].append(guild.name)
            if ctx.author.id in settings["miniboss_users"]:
                all_data["miniboss_servers"][0].append(guild.name)
            if ctx.author.id in settings["cart_users"]:
                all_data["cart_servers"][0].append(guild.name)
        for k, v in all_data.items():
            if v[0]:
                msg += f"__**{v[1]}**__: {humanize_list(v[0])}\n\n"
        if msg:
            for line in pagify(msg):
                await ctx.maybe_send_embed(line)
        else:
            await ctx.maybe_send_embed(_("You do not have any adventure notifications set."))

    @adventurealert.command(name="role", aliases=["roles"])
    @checks.mod_or_permissions(manage_roles=True)
    async def adventure_role(self, ctx: commands.Context, *, role: discord.Role) -> None:
        """Add or remove a role to be pinged when a dragon appears"""
        if role.id in await self.config.guild(ctx.guild).adventure_roles():
            async with self.config.guild(ctx.guild).adventure_roles() as data:
                data.remove(role.id)
            await ctx.send(
                _("{role} will no longer receive notifications on adventures.").format(
                    role=role.name
                )
            )
        else:
            async with self.config.guild(ctx.guild).adventure_roles() as data:
                data.append(role.id)
            await ctx.send(
                _("{role} will now receive notifications on adventures.").format(role=role.name)
            )

    @commands.guild_only()
    @adventurealert.command(name="add", aliases=["user", "users", "remove", "rem", "toggle"])
    async def adventure_users(self, ctx: commands.Context) -> None:
        """Toggle adventure notifications in this server"""
        if ctx.author.id in await self.config.guild(ctx.guild).adventure_users():
            async with self.config.guild(ctx.guild).adventure_users() as data:
                data.remove(ctx.author.id)
            await ctx.send(_("You will no longer receive notifications on adventures."))
        else:
            async with self.config.guild(ctx.guild).adventure_users() as data:
                data.append(ctx.author.id)
            await ctx.send(_("You will now receive notifications on adventures."))

    @adventurealert.command(name="global")
    async def adventure_global(self, ctx: commands.Context) -> None:
        """Toggle adventure notifications in all shared servers"""
        cur_setting = await self.config.user(ctx.author).adventure()
        await self.config.user(ctx.author).adventure.set(not cur_setting)
        if cur_setting:
            await ctx.send(_("Removed from adventure alerts across all shared servers."))
        else:
            await ctx.send(_("Added to adventure alerts across all shared servers."))

    @adventurealert.command(name="removeuser")
    @checks.mod_or_permissions(manage_messages=True)
    async def adventure_removeusers(self, ctx: commands.Context, user_id: int) -> None:
        """Remove a specific user ID from adventure alerts"""
        if user_id in await self.config.guild(ctx.guild).adventure_users():
            async with self.config.guild(ctx.guild).adventure_users() as data:
                data.remove(user_id)
            await ctx.send(
                _("{user_id} will no longer receive notifications on adventures.").format(
                    user_id=user_id
                )
            )
        else:
            await ctx.send(
                _("{user_id} is not receiving notifications on adventures.").format(
                    user_id=user_id
                )
            )

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
                + f"{humanize_list(users) if users else ''} "
                + _("An adventure has started, come join!")
            )
            for page in pagify(msg):
                await ctx.send(page, **self.sanitize)
