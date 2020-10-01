import logging
import random
import string
from typing import Optional, cast

import discord
from redbot import VersionInfo, version_info
from redbot.core import Config, checks, commands
from redbot.core.i18n import Translator, cog_i18n

default_settings = {
    "ENABLED": False,
    "ROLE": [],
    "AGREE_CHANNEL": None,
    "AGREE_MSG": None,
    "AGREE_KEY": None,
    "DELETE_KEY": False,
}

log = logging.getLogger("red.Trusty-cogs.autorole")

_ = Translator("Autorole", __file__)
listener = getattr(commands.Cog, "listener", None)  # red 3.0 backwards compatibility support

if listener is None:  # thanks Sinbad

    def listener(name=None):
        return lambda x: x


@cog_i18n(_)
class Autorole(commands.Cog):
    """
    Autorole commands. Rewritten for V3 from
    https://github.com/Lunar-Dust/Dusty-Cogs/blob/master/autorole/autorole.py
    """

    __author__ = ["Lunar-Dust", "TrustyJAID"]
    __version__ = "1.3.2"

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, 45463543548)
        self.config.register_guild(**default_settings)
        self.users = {}

    def format_help_for_context(self, ctx: commands.Context) -> str:
        """
        Thanks Sinbad!
        """
        pre_processed = super().format_help_for_context(ctx)
        return f"{pre_processed}\n\nCog Version: {self.__version__}"

    async def red_delete_data_for_user(self, **kwargs):
        """
        Nothing to delete
        """
        return

    async def _no_perms(self, channel: Optional[discord.TextChannel] = None) -> None:
        m = _(
            "It appears that you haven't given this "
            "bot enough permissions to use autorole. "
            'The bot requires the "Manage Roles" and '
            'the "Manage Messages" permissions in'
            "order to use autorole. You can change the "
            'permissions in the "Roles" tab of the '
            "guild settings."
        )
        if channel is None:
            log.info(m)
            return
        if channel.permissions_for(channel.guild.me).send_messages:
            await channel.send(m)
        else:
            log.info(m + _("\n I also don't have permission to speak in #") + channel.name)

    async def get_colour(self, channel: discord.TextChannel) -> discord.Colour:
        try:
            return await self.bot.get_embed_colour(channel)
        except AttributeError:
            if await self.bot.db.guild(channel.guild).use_bot_color():
                return channel.guild.me.colour
            else:
                return await self.bot.db.color()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        guild = message.guild
        if not guild:
            return

        if version_info >= VersionInfo.from_str("3.4.0"):
            if await self.bot.cog_disabled_in_guild(self, guild):
                return
        user = cast(discord.Member, message.author)
        channel = message.channel
        agree_channel = cast(
            discord.TextChannel, guild.get_channel(await self.config.guild(guild).AGREE_CHANNEL())
        )
        if guild is None:
            return
        if agree_channel is None:
            return
        if channel.id != agree_channel.id:
            return
        if user.bot:
            return

        if user.id in self.users:
            if not guild.me.guild_permissions.manage_roles:
                await self._no_perms(agree_channel)
                return
            if self.users[user.id]["key"].lower() in message.content.lower():
                perms = agree_channel.permissions_for(guild.me)
                roles_id = await self.config.guild(guild).ROLE()
                roles = [role for role in guild.roles if role.id in roles_id]
                for role in roles:
                    await user.add_roles(role, reason=_("Agreed to the rules"))
                if perms.manage_messages and await self.config.guild(guild).DELETE_KEY():
                    try:
                        await message.delete()
                    except Exception:
                        pass
                    if self.users[user.id]["message"].guild:
                        try:
                            await self.users[user.id]["message"].delete()
                        except Exception:
                            pass
                elif perms.add_reactions:
                    await message.add_reaction("✅")
                del self.users[user.id]

    async def _agree_maker(self, member: discord.Member) -> None:
        guild = member.guild
        self.last_guild = guild
        # await self._verify_json(None)
        key = await self.config.guild(guild).AGREE_KEY()
        if key is None:
            key = "".join(random.choice(string.ascii_uppercase + string.digits) for _ in range(6))
            # <3 Stackoverflow http://stackoverflow.com/questions/2257441/random-string-generation-with-upper-case-letters-and-digits-in-python/23728630#23728630

        ch = cast(
            discord.TextChannel, guild.get_channel(await self.config.guild(guild).AGREE_CHANNEL())
        )
        msg = await self.config.guild(guild).AGREE_MSG()
        if msg is None:
            msg = "{mention} please enter {key} in {channel}"
        try:
            msg = msg.format(
                key=key,
                member=member,
                name=member.name,
                mention=member.mention,
                guild=guild.name,
                channel=ch.mention,
            )
        except Exception:
            log.error("Error formatting agreement message", exc_info=True)

        try:
            msg = await member.send(msg)
        except discord.Forbidden:
            msg = await ch.send(msg)
        except discord.HTTPException:
            return
        self.users[member.id] = {"key": key, "message": msg}

    async def _auto_give(self, member: discord.Member) -> None:
        guild = member.guild
        roles_id = await self.config.guild(guild).ROLE()
        roles = [role for role in guild.roles if role.id in roles_id]
        if not guild.me.guild_permissions.manage_roles:
            await self._no_perms()
            return
        for role in roles:
            await member.add_roles(role, reason=_("Joined the server"))

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        guild = member.guild
        if await self.config.guild(guild).ENABLED():
            if await self.config.guild(guild).AGREE_CHANNEL() is not None:
                await self._agree_maker(member)
            else:  # Immediately give the new user the role
                await self._auto_give(member)

    @commands.guild_only()
    @commands.group(name="autorole")
    @commands.bot_has_permissions(manage_roles=True)
    async def autorole(self, ctx: commands.Context) -> None:
        """
        Change settings for autorole

        Requires the manage roles permission
        """
        pass

    @autorole.command(name="info")
    async def autorole_info(self, ctx: commands.Context) -> None:
        """
        Display current autorole info
        """
        guild = ctx.message.guild
        enabled = await self.config.guild(guild).ENABLED()
        roles = await self.config.guild(guild).ROLE()
        msg = await self.config.guild(guild).AGREE_MSG()
        key = await self.config.guild(guild).AGREE_KEY()
        ch_id = await self.config.guild(guild).AGREE_CHANNEL()
        delete = await self.config.guild(guild).DELETE_KEY()
        channel = guild.get_channel(ch_id)
        chn_name = channel.name if channel is not None else "None"
        chn_mention = channel.mention if channel is not None else "None"
        role_name_str = ", ".join(role.mention for role in guild.roles if role.id in roles)
        if not role_name_str:
            role_name_str = "None"
        if ctx.channel.permissions_for(ctx.me).embed_links:
            embed = discord.Embed(colour=await self.get_colour(ctx.channel))
            embed.set_author(name=_("Autorole settings for ") + guild.name)
            embed.add_field(name=_("Current autorole state: "), value=str(enabled))
            embed.add_field(name=_("Current Roles: "), value=str(role_name_str))
            if msg:
                embed.add_field(name=_("Agreement message: "), value=str(msg))
            if key:
                embed.add_field(name=_("Agreement key: "), value=str(key))
            if channel:
                embed.add_field(name=_("Agreement channel: "), value=str(chn_mention))
            await ctx.send(embed=embed)
        else:
            send_msg = (
                "```"
                + _("Current autorole state: ")
                + f"{enabled}\n"
                + _("Current Roles: ")
                + f"{role_name_str}\n"
                + _("Agreement message: ")
                + f"{msg}\n"
                + _("Agreement key: ")
                + f"{key}\n"
                + _("Delete Agreement: ")
                + f"{delete}\n"
                + _("Agreement channel: ")
                + f"{chn_name}"
                + "```"
            )
            await ctx.send(send_msg)

    @autorole.command()
    @checks.admin_or_permissions(manage_roles=True)
    async def toggle(self, ctx: commands.Context) -> None:
        """
        Enables/Disables autorole
        """
        guild = ctx.message.guild
        if await self.config.guild(guild).ROLE() is None:
            msg = _("You haven't set a " "role to give to new users!")
            await ctx.send(msg)
        else:
            if await self.config.guild(guild).ENABLED():
                await self.config.guild(guild).ENABLED.set(False)
                await ctx.send(_("Autorole is now disabled."))
            else:
                await self.config.guild(guild).ENABLED.set(True)
                await ctx.send(_("Autorole is now enabled."))

    @autorole.command(name="add", aliases=["role"])
    @checks.admin_or_permissions(manage_roles=True)
    async def role(self, ctx: commands.Context, *, role: discord.Role) -> None:
        """
        Add a role for autorole to assign.

        You can use this command multiple times to add multiple roles.
        """
        guild = ctx.message.guild
        roles = await self.config.guild(guild).ROLE()
        if ctx.author.top_role < role:
            msg = _(
                " is higher than your highest role. "
                "You can't assign autoroles higher than your own"
            )
            await ctx.send(role.name + msg)
        if role.id in roles:
            await ctx.send(role.name + _(" is already in the autorole list."))
            return
        if guild.me.top_role < role:
            msg = _(" is higher than my highest role" " in the Discord hierarchy.")
            await ctx.send(role.name + msg)
            return
        roles.append(role.id)
        await self.config.guild(guild).ROLE.set(roles)
        await ctx.send(role.name + _(" role added to the autorole."))

    @autorole.command()
    @checks.admin_or_permissions(manage_roles=True)
    async def remove(self, ctx: commands.Context, *, role: discord.Role) -> None:
        """
        Remove a role from the autorole.
        """
        guild = ctx.message.guild
        roles = await self.config.guild(guild).ROLE()
        if role.id not in roles:
            await ctx.send(role.name + _(" is not in the autorole list."))
            return
        roles.remove(role.id)
        await self.config.guild(guild).ROLE.set(roles)
        await ctx.send(role.name + _(" role removed from the autorole."))

    @autorole.group()
    @checks.admin_or_permissions(manage_roles=True)
    async def agreement(self, ctx: commands.Context) -> None:
        """
        Set the channel and message that will be used for accepting the rules.

        `channel` is the channel they must type the key in to get the role.
        `key` is the message they must type to gain access and must be in quotes.
        `msg` is the message DM'd to them when they join.

        `{key}` must be included in the message so a user knows what to type in the channel.

        Optional additions to the message include:
        `{channel}` Mentions the channel where they must include the agreement message.
        `{mention}` Mentions the user incase they have DM permissions turned off this should be used.
        `{name}` Says the member name if you don't want to ping them.
        `{guild}` Says the servers current name.

        Entering nothing will disable these.
        """
        pass

    @agreement.command(name="channel")
    @checks.admin_or_permissions(manage_roles=True)
    async def set_agreement_channel(
        self, ctx: commands.Context, channel: discord.TextChannel = None
    ) -> None:
        """
        Set the agreement channel

        Entering nothing will clear this.
        """
        guild = ctx.message.guild
        if await self.config.guild(guild).ROLE() == []:
            await ctx.send(_("No roles have been set for autorole."))
            return
        if not await self.config.guild(guild).ENABLED():
            await ctx.send(_("Autorole has been disabled, enable it first."))
            return
        if channel is None:
            await self.config.guild(guild).AGREE_CHANNEL.set(None)
            await ctx.send(_("Agreement channel cleared"))
        else:
            await self.config.guild(guild).AGREE_CHANNEL.set(channel.id)
            await ctx.send(_("Agreement channel set to ") + channel.mention)

    @agreement.command(name="delete")
    @checks.admin_or_permissions(manage_roles=True)
    async def set_agreement_delete(self, ctx: commands.Context) -> None:
        """
        Toggle automatically deleting the agreement message.
        """
        delete_key = await self.config.guild(ctx.guild).DELETE_KEY()
        await self.config.guild(ctx.guild).DELETE_KEY.set(not delete_key)
        if delete_key:
            await ctx.send(_("No longer automatically deleting agreement key."))
        else:
            await ctx.send(_("Automatically deleting agreement key."))

    @agreement.command(name="key")
    @checks.admin_or_permissions(manage_roles=True)
    async def set_agreement_key(self, ctx: commands.Context, *, key: str = None) -> None:
        """
        Set the agreement key

        Entering nothing will clear this.
        """

        guild = ctx.message.guild
        if await self.config.guild(guild).ROLE() == []:
            await ctx.send(_("No roles have been set for autorole."))
            return
        if not await self.config.guild(guild).ENABLED():
            await ctx.send(_("Autorole has been disabled, enable it first."))
            return
        if key is None:
            await self.config.guild(guild).AGREE_KEY.set(None)
            await ctx.send(_("Agreement key cleared"))
        else:
            await self.config.guild(guild).AGREE_KEY.set(key)
            await ctx.send(_("Agreement key set to ") + key)

    @agreement.command(name="message", aliases=["msg"])
    @checks.admin_or_permissions(manage_roles=True)
    async def set_agreement_msg(self, ctx: commands.Context, *, message: str = None) -> None:
        """
        Set the agreement message
        `{key}` must be included in the message so a user knows what to type in the channel.

        Optional additions to the message include:
        `{channel}` Mentions the channel where they must include the agreement message.
        `{mention}` Mentions the user incase they have DM permissions turned off this should be used.
        `{name}` Says the member name if you don't want to ping them.
        `{guild}` Says the servers current name.

        Entering nothing will clear this.
        """
        guild = ctx.message.guild
        if await self.config.guild(guild).ROLE() == []:
            await ctx.send(_("No roles have been set for autorole."))
            return
        if not await self.config.guild(guild).ENABLED():
            await ctx.send(_("Autorole has been disabled, enable it first."))
            return
        if message is None:
            await self.config.guild(guild).AGREE_MSG.set(None)
            await ctx.send(_("Agreement message cleared"))
        else:
            await self.config.guild(guild).AGREE_MSG.set(message)
            await ctx.send(_("Agreement message set to ") + message)

    @agreement.command(name="setup")
    @checks.admin_or_permissions(manage_roles=True)
    async def agreement_setup(
        self,
        ctx: commands.Context,
        channel: discord.TextChannel = None,
        key: str = None,
        *,
        msg: str = None,
    ) -> None:
        """
        Set the channel and message that will be used for accepting the rules.

        `channel` is the channel they must type the key in to get the role.
        `key` is the message they must type to gain access and must be in quotes.
        `msg` is the message DM'd to them when they join.

        `{key}` must be included in the message so a user knows what to type in the channel.

        Optional additions to the message include:
        `{channel}` Mentions the channel where they must include the agreement message.
        `{mention}` Mentions the user incase they have DM permissions turned off this should be used.
        `{name}` Says the member name if you don't want to ping them.
        `{guild}` Says the servers current name.

        Entering nothing will disable this.
        """
        guild = ctx.message.guild
        if await self.config.guild(guild).ROLE() == []:
            await ctx.send(_("No roles have been set for autorole."))
            return
        if not await self.config.guild(guild).ENABLED():
            await ctx.send(_("Autorole has been disabled, enable it first."))
            return
        if channel is None:
            await self.config.guild(guild).AGREE_CHANNEL.set(None)
            await self.config.guild(guild).AGREE_MSG.set(None)
            await self.config.guild(guild).AGREE_KEY.set(None)
            await ctx.send(_("Agreement channel cleared"))
        else:
            await self.config.guild(guild).AGREE_CHANNEL.set(channel.id)
            await self.config.guild(guild).AGREE_MSG.set(msg)
            await self.config.guild(guild).AGREE_KEY.set(key)
            await ctx.send(_("Agreement channel set to ") + channel.mention)
