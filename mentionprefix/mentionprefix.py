from __future__ import annotations

import asyncio
import re
from datetime import timedelta
from typing import Dict, Optional, Set

import discord
from discord.ext.commands.view import StringView
from red_commons.logging import getLogger
from redbot.core import Config, commands
from redbot.core.bot import Red
from redbot.core.commands import Context
from redbot.core.utils.antispam import AntiSpam
from redbot.core.utils.chat_formatting import humanize_list

log = getLogger("red.Trusty-Cogs.mentionprefix")

HELP_RE = re.compile(r"^.*help$", flags=re.I)

_ = lambda s: s


class MentionPrefix(commands.Cog):
    """Ping the bot to see its prefixes."""

    intervals = [
        (timedelta(seconds=30), 1),
        (timedelta(minutes=5), 2),
        (timedelta(hours=1), 10),
        (timedelta(days=1), 24),
    ]
    __version__ = "1.1.0"
    __author__ = ["Draper", "TrustyJAID"]

    def __init__(self, bot: Red) -> None:
        self.bot = bot
        self.mention_regex: Optional[re.Pattern] = None
        self.antispam: Dict[Optional[int], Dict[int, AntiSpam]] = {}
        self._event = asyncio.Event()
        self.config = Config.get_conf(self, identifier=208903205982044161, force_registration=True)
        self.config.register_global(disabled_in=[])
        self.disable_in: Set[int] = set()

    async def red_delete_data_for_user(self, **kwargs):
        """
        Nothing to delete
        """
        return

    async def initialize(self):
        await self.bot.wait_until_red_ready()
        self.mention_regex = re.compile(rf"^<@!?{self.bot.user.id}>$")
        self.disable_in = set(await self.config.disabled_in())
        self._event.set()

    @commands.command(name="mentiontoggle")
    @commands.guild_only()
    @commands.admin_or_permissions(manage_guild=True)
    async def commands_mentiontoggle(self, ctx: commands.Context):
        """Toggle whether mentioning the bot will send a help message."""
        if ctx.guild.id in self.disable_in:
            self.disable_in.discard(ctx.guild.id)
            await ctx.send(_("Mentioning the bot will trigger it to send a help message."))
        else:
            self.disable_in.add(ctx.guild.id)
            await ctx.send(_("Mentioning the bot will no longer cause it to send a help message."))
        await self.config.disabled_in.set(list(self.disable_in))

    def handle_dm_help(self, message: discord.Message) -> bool:
        if message.author.bot:
            return False
        if isinstance(message.channel, discord.DMChannel):
            return HELP_RE.match(message.content) is not None
        return False

    @commands.Cog.listener()
    async def on_message_without_command(self, message: discord.Message):
        if (not self._event.is_set()) or self.mention_regex is None:
            return
        if not self.mention_regex.match(message.content) and not self.handle_dm_help(message):
            return
        channel = message.channel
        author = message.author
        guild = message.guild
        guild_id = guild.id if guild else None
        if author.bot:
            return
        if guild_id in self.disable_in:
            return
        if guild_id not in self.antispam:
            self.antispam[guild_id] = {}
        if author.id not in self.antispam[guild_id]:
            self.antispam[guild_id][author.id] = AntiSpam(self.intervals)
        if self.antispam[guild_id][author.id].spammy:
            return
        if guild:
            if (
                not channel.permissions_for(guild.me).send_messages
                or (await self.bot.cog_disabled_in_guild(self, guild))
                or not (await self.bot.ignored_channel_or_guild(message))
            ):
                return
        if not (await self.bot.allowed_by_whitelist_blacklist(author)):
            return

        self.antispam[guild_id][author.id].stamp()
        prefixes = await self.bot.get_valid_prefixes(guild=guild)
        prefixes = sorted(prefixes, key=len)
        counter = 0
        prefix_list = [
            pf
            for p in prefixes
            if (pf := f"`{p}`")
            and len(pf) < 1800
            and ((counter + len(pf)) < 1800)
            and (counter := counter + len(pf))
        ]
        if not prefix_list:
            return
        prefixes_string = humanize_list(prefix_list)
        single_prefix = prefix_list[0][1:-1]
        destination = channel if guild else author
        help_command = self.bot.get_command("help")
        verb = _("my prefix here is") if len(prefix_list) == 1 else _("my prefixes here are")
        if help_command:
            view = StringView(message.content)
            ctx: Context = Context(prefix=None, view=view, bot=self.bot, message=message)
            if not await help_command.can_run(ctx):
                return await destination.send(
                    _("Hey there, {verb} the following:\n{p_list}").format(
                        p_list=prefixes_string, verb=verb
                    )
                )
            else:
                return await destination.send(
                    _(
                        "Hey there, {verb} the following:\n{p_list}\n"
                        "Why don't you try `{p}{command}` to see everything I can do."
                    ).format(
                        p_list=prefixes_string,
                        p=single_prefix,
                        command=help_command.qualified_name,
                        verb=verb,
                    )
                )
        else:
            return await destination.send(
                _("Hey there, {verb} the following:\n{p_list}").format(
                    p_list=prefixes_string, verb=verb
                )
            )
