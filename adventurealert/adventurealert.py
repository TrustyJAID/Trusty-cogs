from abc import ABC
from typing import Literal, Optional

import discord
from redbot.core import Config, checks, commands
from redbot.core.i18n import Translator, cog_i18n
from redbot.core.utils.chat_formatting import humanize_list, pagify

from .listeners import AdventureAlertListeners, AlertTypeConverter, AlertTypes

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
    AdventureAlertListeners,
    commands.Cog,
    metaclass=CompositeMetaClass,
):
    """Alert when a dragon appears in adventure"""

    __version__ = "1.5.1"
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
        await self.config.user_from_id(user_id).clear()
        all_guilds = await self.config.all_guilds()
        for g_id, settings in all_guilds.items():
            if user_id in settings["users"]:
                async with self.config.guild_from_id(int(g_id)).users() as users:
                    users.remove(user_id)

            if user_id in settings["adventure_users"]:
                async with self.config.guild_from_id(
                    int(g_id)
                ).adventure_users() as adventure_users:
                    adventure_users.remove(user_id)

            if user_id in settings["miniboss_users"]:
                async with self.config.guild_from_id(int(g_id)).miniboss_users() as miniboss_users:
                    miniboss_users.remove(user_id)

            if user_id in settings["cart_users"]:
                async with self.config.guild_from_id(int(g_id)).cart_users() as cart_users:
                    cart_users.remove(user_id)

            if user_id in settings["ascended_users"]:
                async with self.config.guild_from_id(int(g_id)).ascended_users() as ascended_users:
                    ascended_users.remove(user_id)

            if user_id in settings["transcended_users"]:
                async with self.config.guild_from_id(
                    g_id
                ).transcended_users() as transcended_users:
                    transcended_users.remove(user_id)

            if user_id in settings["immortal_users"]:
                async with self.config.guild_from_id(int(g_id)).immortal_users() as immortal_users:
                    immortal_users.remove(user_id)

            if user_id in settings["possessed_users"]:
                async with self.config.guild_from_id(
                    int(g_id)
                ).possessed_users() as possessed_users:
                    possessed_users.remove(user_id)

    @commands.hybrid_group()
    async def adventurealert(self, ctx: commands.Context) -> None:
        """Set notifications for all adventures"""
        pass

    @adventurealert.command()
    async def removeall(self, ctx: commands.Context) -> None:
        """Remove all adventurealert settings in all guilds"""
        await self.red_delete_data_for_user(requester="user", user_id=ctx.author.id)
        await ctx.send(_("Your Adventure Alerts have all been removed."))

    @adventurealert.command()
    @commands.is_owner()
    async def removealluser(self, ctx: commands.Context, user_id: int) -> None:
        """Remove A specified user from adventurealert across the bot"""
        await self.red_delete_data_for_user(requester="owner", user_id=user_id)
        await ctx.send(_("Adventure Alerts have all been removed for that user."))

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
            "ascended_servers": ([], _("Ascended Notifications")),
            "transcended_servers": ([], _("Transcended Notifications")),
            "immortal_servers": ([], _("Immortal Notifications")),
            "possessed_servers": ([], _("Possessed Notifications")),
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
            if ctx.author.id in settings["ascended_users"]:
                all_data["ascended_servers"][0].append(guild.name)
            if ctx.author.id in settings["transcended_users"]:
                all_data["transcended_servers"][0].append(guild.name)
            if ctx.author.id in settings["immortal_users"]:
                all_data["immortal_servers"][0].append(guild.name)
            if ctx.author.id in settings["possessed_users"]:
                all_data["possessed_servers"][0].append(guild.name)
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
    async def adventure_role(
        self,
        ctx: commands.Context,
        alert_style: Optional[AlertTypeConverter] = None,
        *,
        role: discord.Role,
    ) -> None:
        """
        Add or remove a role to be pinged when a dragon appears

        `alert_style` - Must be one of:
            - `adventure` (default)
            - `boss` or `dragon`
            - `cart`
            - `immortal`
            - `miniboss`
            - `possessed`
            - `ascended`
            - `transcended`
        """
        if alert_style is None:
            style = AlertTypes.adventure
        else:
            style = alert_style
        conf = style.get_role_config(self.config.guild(ctx.guild))
        if role.id in await conf():
            async with conf() as data:
                data.remove(role.id)
            await ctx.send(
                _("{role} will no longer receive notifications on {style} alerts.").format(
                    role=role.mention, style=style.get_name()
                ),
                allowed_mentions=discord.AllowedMentions(roles=False),
            )
        else:
            async with conf() as data:
                data.append(role.id)
            await ctx.send(
                _("{role} will now receive notifications on {style} alerts.").format(
                    role=role.mention, style=style.get_name()
                ),
                allowed_mentions=discord.AllowedMentions(roles=False),
            )

    @commands.guild_only()
    @adventurealert.command(name="toggle", aliases=["user", "users", "remove", "rem", "add"])
    async def adventure_users(
        self, ctx: commands.Context, alert_style: Optional[AlertTypeConverter] = None
    ) -> None:
        """
        Toggle adventure notifications in this server

        `alert_style` - Must be one of:
            - `adventure` (default)
            - `boss` or `dragon`
            - `cart`
            - `immortal`
            - `miniboss`
            - `possessed`
            - `ascended`
            - `transcended`
        """
        if alert_style is None:
            style = AlertTypes.adventure
        else:
            style = alert_style
        conf = style.get_user_config(self.config.guild(ctx.guild))
        if ctx.author.id in await conf():
            async with conf() as data:
                data.remove(ctx.author.id)
            await ctx.send(
                _("You will no longer receive notifications on {style} alerts.").format(
                    style=style.get_name()
                )
            )
        else:
            async with conf() as data:
                data.append(ctx.author.id)
            await ctx.send(
                _("You will now receive notifications on {style} alerts.").format(
                    style=style.get_name()
                )
            )

    @adventurealert.command(name="global")
    async def adventure_global(
        self, ctx: commands.Context, alert_style: Optional[AlertTypeConverter] = None
    ) -> None:
        """
        Toggle adventure notifications in all shared servers

        `alert_style` - Must be one of:
            - `adventure` (default)
            - `boss` or `dragon`
            - `cart`
            - `immortal`
            - `miniboss`
            - `possessed`
            - `ascended`
            - `transcended`
        """
        if alert_style is None:
            style = AlertTypes.adventure
        else:
            style = alert_style
        conf = style.get_user_global_config(self.config.user(ctx.author))
        cur_setting = await conf()
        await conf.set(not cur_setting)
        if cur_setting:
            await ctx.send(
                _("Removed from {style} alerts across all shared servers.").format(
                    style=style.get_name()
                )
            )
        else:
            await ctx.send(
                _("Added to {style} alerts across all shared servers.").format(
                    style=style.get_name()
                )
            )

    @adventurealert.command(name="removeuser")
    @checks.mod_or_permissions(manage_messages=True)
    async def adventure_removeusers(
        self,
        ctx: commands.Context,
        user_id: int,
        alert_style: Optional[AlertTypeConverter] = None,
    ) -> None:
        """
        Remove a specific user ID from adventure alerts

        `alert_style` - Must be one of:
            - `adventure` (default)
            - `boss` or `dragon`
            - `cart`
            - `immortal`
            - `miniboss`
            - `possessed`
            - `ascended`
            - `transcended`
        """
        if alert_style is None:
            style = AlertTypes.adventure
        else:
            style = alert_style
        conf = style.get_user_config(self.config.guild(ctx.guild))
        if user_id in await conf():
            async with conf() as data:
                data.remove(user_id)
            await ctx.send(
                _("{user_id} will no longer receive notifications on {style}.").format(
                    user_id=user_id, style=style.get_name()
                )
            )
        else:
            await ctx.send(
                _("{user_id} is not receiving notifications on {style}.").format(
                    user_id=user_id, style=style.get_name()
                )
            )
