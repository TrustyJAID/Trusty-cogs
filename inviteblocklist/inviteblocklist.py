import discord
import logging
import re

from typing import Union, Pattern, List

from discord.ext.commands.converter import InviteConverter, IDConverter
from discord.ext.commands.errors import BadArgument

from redbot.core import commands, Config, version_info, VersionInfo
from redbot.core.i18n import Translator, cog_i18n
from redbot.core.utils.chat_formatting import humanize_list, pagify

log = logging.getLogger("red.trusty-cogs.inviteblocklist")

_ = Translator("ExtendedModLog", __file__)

INVITE_RE: Pattern = re.compile(
    r"(?:https?\:\/\/)?discord(?:\.gg|(?:app)?\.com\/invite)\/(.+)", re.I
)
# https://github.com/Rapptz/discord.py/blob/master/discord/utils.py#L448


class ValidServerID(IDConverter):
    async def convert(self, ctx: commands.Context, argument: str):
        match = self._get_id_match(argument)
        if not match:
            raise BadArgument("The ID provided does not appear to be valid.")
        guild_id = int(match.group(1))
        return guild_id


class InviteBlocklist(commands.Cog):

    __author__ = ["TrustyJAID"]
    __version__ = "1.0.0"

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=218773382617890828)
        self.config.register_guild(blacklist=[], whitelist=[], all_invites=False)

    async def red_delete_data_for_user(self, **kwargs):
        """
        Nothing to delete
        """
        return

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        if not message.guild:
            return
        await self._handle_message_search(message)

    @commands.Cog.listener()
    async def on_raw_message_edit(self, payload: discord.RawMessageUpdateEvent):
        """
        Handle messages edited with links
        """
        if payload.cached_message:
            await self._handle_message_search(payload.cached_message)
            return
        chan = self.bot.get_channel(payload.channel_id)
        try:
            msg = await chan.fetch_message(payload.message_id)
        except discord.errors.Forbidden:
            return
        await self._handle_message_search(msg)

    async def _handle_message_search(self, message: discord.Message):
        if await self.bot.is_automod_immune(message.author):
            return
        if version_info >= VersionInfo.from_str("3.4.0"):
            if await self.bot.cog_disabled_in_guild(self, message.guild):
                return

        find = INVITE_RE.findall(message.clean_content)
        guild = message.guild
        if find and await self.config.guild(message.guild).all_invites():
            try:
                await message.delete()
            except discord.errors.Forbidden:
                log.error(
                    _(
                        "I tried to delete an invite link posted in {guild} "
                        "but lacked the permission to do so"
                    ).format(guild=guild.name)
                )
            return
        if whitelist := await self.config.guild(message.guild).whitelist():
            for i in find:
                invite = await self.bot.fetch_invite(i)
                if invite.guild.id == message.guild.id:
                    continue
                if invite.guild.id not in whitelist:
                    try:
                        await message.delete()
                    except discord.errors.Forbidden:
                        log.error(
                            _(
                                "I tried to delete an invite link posted in {guild} "
                                "but lacked the permission to do so"
                            ).format(guild=guild.name)
                        )
                    return
            return
        if blacklist := await self.config.guild(message.guild).blacklist():
            for i in find:
                invite = await self.bot.fetch_invite(i)
                if invite.guild.id == message.guild.id:
                    continue
                if invite.guild.id in blacklist:
                    try:
                        await message.delete()
                    except discord.errors.Forbidden:
                        log.error(
                            _(
                                "I tried to delete an invite link posted in {guild} "
                                "but lacked the permission to do so"
                            ).format(guild=guild.name)
                        )
                    return
            return

    @commands.group(name="inviteblock", aliases=["ibl", "inviteblocklist"])
    @commands.mod_or_permissions(manage_messages=True)
    async def invite_block(self, ctx: commands.Context):
        """
        Settings for managing invite link blocking
        """
        pass

    @invite_block.group(name="blocklist", aliases=["blacklist", "bl"])
    async def invite_blocklist(self, ctx: commands.Context):
        """
        Commands for setting the blocklist
        """
        pass

    @invite_block.group(name="allowlist", aliases=["whitelist", "wl", "al"])
    async def invite_allowlist(self, ctx: commands.Context):
        """
        Commands for setting the blocklist
        """
        pass

    @invite_block.command()
    @commands.mod_or_permissions(manage_messages=True)
    async def blockall(self, ctx: commands.Context, set_to: bool):
        """
        Automatically remove all invites regardless of their destination
        """
        await self.config.guild(ctx.guild).all_invites.set(set_to)
        if set_to:
            await ctx.send(_("Okay, I will delete all invite links posted."))
        else:
            await ctx.send(
                _(
                    "Okay I will only delete invites if the server "
                    "destination is in my blocklist or allowlist."
                )
            )

    @invite_blocklist.command(name="add")
    async def add_to_blocklist(
        self, ctx: commands.Context, *invite_or_guild_id: Union[InviteConverter, ValidServerID]
    ):
        """
        Add a guild ID to the blocklist, providing an invite link will also work

        `[invite_or_guild_id]` The guild ID or invite to the guild you want to have
        invite links blocked from.
        """
        guilds_blocked = []
        async with self.config.guild(ctx.guild).blacklist() as blacklist:
            for i in invite_or_guild_id:
                if isinstance(i, int):
                    if i not in blacklist:
                        blacklist.append(i)
                        guilds_blocked.append(str(i))
                else:
                    if i.guild and i.guild.id not in blacklist:
                        blacklist.append(i.guild.id)
                        guilds_blocked.append(f"{i.guild.name} - {i.guild.id}")
        if guilds_blocked:
            await ctx.send(
                _("Now blocking invites from {guild}.").format(guild=humanize_list(guilds_blocked))
            )
        else:
            await ctx.send(_("None of the provided invite links or guild ID's are new."))

    @invite_blocklist.command(name="info")
    async def blocklist_info(self, ctx: commands.Context):
        """
        Show what guild ID's are in the invite link blocklist
        """
        blacklist = await self.config.guild(ctx.guild).blacklist()
        msg = _("__Guild ID's Blocked__:\n{guilds}").format(
            guilds="\n".join(str(g) for g in blacklist)
        )

        for page in pagify(msg):
            await ctx.maybe_send_embed(page)

    @invite_blocklist.command(name="remove", aliases=["del", "rem"])
    async def remove_from_blocklist(
        self, ctx: commands.Context, *invite_or_guild_id: Union[InviteConverter, ValidServerID]
    ):
        """
        Add a guild ID to the blocklist, providing an invite link will also work

        `[invite_or_guild_id]` The guild ID or invite to the guild you not longer want to have
        invite links blocked from.
        """
        guilds_blocked = []
        async with self.config.guild(ctx.guild).blacklist() as blacklist:
            for i in invite_or_guild_id:
                if isinstance(i, int):
                    if i in blacklist:
                        blacklist.remove(i)
                        guilds_blocked.append(str(i))
                else:
                    if i.guild and i.guild.id in blacklist:
                        guilds_blocked.append(f"{i.guild.name} - {i.guild.id}")
                        blacklist.remove(i.guild.id)
        if guilds_blocked:
            await ctx.send(
                _("Removed {guild} from blocklist.").format(guild=humanize_list(guilds_blocked))
            )
        else:
            await ctx.send(_("None of the provided invite links or guild ID's are being blocked."))

    @invite_allowlist.command(name="add")
    async def add_to_allowlist(
        self, ctx: commands.Context, *invite_or_guild_id: Union[InviteConverter, ValidServerID]
    ):
        """
        Add a guild ID to the allowlist, providing an invite link will also work

        `[invite_or_guild_id]` The guild ID or invite to the guild you want to have
        invites allowed from.
        """
        guilds_blocked = []
        async with self.config.guild(ctx.guild).whitelist() as whitelist:
            for i in invite_or_guild_id:
                if isinstance(i, int):
                    if i not in whitelist:
                        whitelist.append(i)
                        guilds_blocked.append(str(i))
                else:
                    if i.guild and i.guild.id not in whitelist:
                        whitelist.append(i.guild.id)
                        guilds_blocked.append(f"{i.guild.name} - {i.guild.id}")
        if guilds_blocked:
            await ctx.send(
                _("Now Allowing invites from {guild}.").format(guild=humanize_list(guilds_blocked))
            )
        else:
            await ctx.send(_("None of the provided invite links or ID's are new."))

    @invite_allowlist.command(name="info")
    async def allowlist_info(self, ctx: commands.Context):
        """
        Show what guild ID's are in the invite link allowlist
        """
        whitelist = await self.config.guild(ctx.guild).whitelist()
        msg = _("__Guild ID's Allowed__:\n{guilds}").format(
            guilds="\n".join(str(g) for g in whitelist)
        )
        for page in pagify(msg):
            await ctx.maybe_send_embed(page)

    @invite_allowlist.command(name="remove", aliases=["del", "rem"])
    async def remove_from_allowlist(
        self, ctx: commands.Context, *invite_or_guild_id: Union[InviteConverter, ValidServerID]
    ):
        """
        Add a guild ID to the allowlist, providing an invite link will also work

        `[invite_or_guild_id]` The guild ID or invite to the guild you not longer want to have
        invites allowed from.
        """
        guilds_blocked = []
        async with self.config.guild(ctx.guild).whitelist() as whitelist:
            for i in invite_or_guild_id:
                if isinstance(i, int):
                    if i in whitelist:
                        whitelist.remove(i)
                        guilds_blocked.append(str(i))
                else:
                    if i.guild and i.guild.id in whitelist:
                        guilds_blocked.append(f"{i.guild.name} - {i.guild.id}")
                        whitelist.remove(i.guild.id)
        if guilds_blocked:
            await ctx.send(
                _("Removed {guild} from allowlist.").format(guild=humanize_list(guilds_blocked))
            )
        else:
            await ctx.send(
                _("None of the provided invite links or guild ID's are currently allowed.")
            )
