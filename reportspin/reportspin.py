import logging
import asyncio
import contextlib
import discord
import re

from typing import Union, List
from datetime import timedelta
from copy import copy
from discord.ext.commands.converter import IDConverter
from discord.ext.commands.errors import BadArgument

from redbot.core import Config, checks, commands
from redbot.core.utils.chat_formatting import pagify, box
from redbot.core.utils.antispam import AntiSpam
from redbot.core.bot import Red
from redbot.core.i18n import Translator, cog_i18n
from redbot.core.utils.predicates import MessagePredicate
from redbot.core.utils.tunnel import Tunnel


_ = Translator("Reports", __file__)

log = logging.getLogger("red.trusty-cogs.reports")


class ValidEmoji(IDConverter):
    """
    This is from discord.py rewrite, first we'll match the actual emoji
    then we'll match the emoji name if we can
    if all else fails we may suspect that it's a unicode emoji and check that later
    All lookups are done for the local guild first, if available. If that lookup
    fails, then it checks the client's global cache.
    The lookup strategy is as follows (in order):
    1. Lookup by ID.
    2. Lookup by extracting ID from the emoji.
    3. Lookup by name
    https://github.com/Rapptz/discord.py/blob/rewrite/discord/ext/commands/converter.py
    """

    async def convert(self, ctx: commands.Context, argument: str) -> Union[discord.Emoji, str]:
        match = self._get_id_match(argument) or re.match(
            r"<a?:[a-zA-Z0-9\_]+:([0-9]+)>$|(:[a-zA-z0-9\_]+:$)", argument
        )
        result = None
        bot = ctx.bot
        guild = ctx.guild
        if match is None:
            # Try to get the emoji by name. Try local guild first.
            if guild:
                result = discord.utils.get(guild.emojis, name=argument)

            if result is None:
                result = discord.utils.get(bot.emojis, name=argument)
        elif match.group(1):
            emoji_id = int(match.group(1))

            # Try to look up emoji by id.
            if guild:
                result = discord.utils.get(guild.emojis, id=emoji_id)

            if result is None:
                result = discord.utils.get(bot.emojis, id=emoji_id)
        else:
            emoji_name = str(match.group(2)).replace(":", "")

            if guild:
                result = discord.utils.get(guild.emojis, name=emoji_name)

            if result is None:
                result = discord.utils.get(bot.emojis, name=emoji_name)
        if type(result) is discord.Emoji:
            result = str(result)[1:-1]

        if result is None:
            try:
                await ctx.message.add_reaction(argument)
                result = argument
            except Exception:
                raise BadArgument(_("`{}` is not an emoji I can use.").format(argument))

        return result


@cog_i18n(_)
class Reports(commands.Cog):
    """
        Redbot Core's default reports cog with some modifications
    """

    default_guild_settings = {
        "output_channel": None,
        "active": False,
        "next_ticket": 1,
        "report_emoji": None,
    }

    default_report = {"report": {}}

    # This can be made configureable later if it
    # becomes an issue.
    # Intervals should be a list of tuples in the form
    # (period: timedelta, max_frequency: int)
    # see redbot/core/utils/antispam.py for more details

    intervals = [
        (timedelta(seconds=5), 1),
        (timedelta(minutes=5), 3),
        (timedelta(hours=1), 10),
        (timedelta(days=1), 24),
    ]

    def __init__(self, bot: Red):
        super().__init__()
        self.bot = bot
        self.config = Config.get_conf(self, 78631113035100160, force_registration=True)
        self.config.register_guild(**self.default_guild_settings)
        self.config.init_custom("REPORT", 2)
        self.config.register_custom("REPORT", **self.default_report)
        self.antispam = {}
        self.user_cache = []
        self.tunnel_store = {}
        # (guild, ticket#):
        #   {'tun': Tunnel, 'msgs': List[int]}

    @property
    def tunnels(self):
        return [x["tun"] for x in self.tunnel_store.values()]

    @checks.admin_or_permissions(manage_guild=True)
    @commands.guild_only()
    @commands.group(name="reportset")
    async def reportset(self, ctx: commands.Context):
        """Manage Reports."""
        pass

    @checks.admin_or_permissions(manage_guild=True)
    @reportset.command(name="output")
    async def reportset_output(self, ctx: commands.Context, channel: discord.TextChannel):
        """Set the channel where reports will be sent."""
        await self.config.guild(ctx.guild).output_channel.set(channel.id)
        await ctx.send(_("The report channel has been set."))

    @checks.admin_or_permissions(manage_guild=True)
    @reportset.command(name="emoji")
    async def reportset_emoji(self, ctx: commands.Context, emoji: ValidEmoji):
        """Set the emoji used to report a message."""
        await self.config.guild(ctx.guild).report_emoji.set(emoji)
        await ctx.send(_("The reporting emoji has been set."))

    @checks.admin_or_permissions(manage_guild=True)
    @reportset.command(name="toggle", aliases=["toggleactive"])
    async def reportset_toggle(self, ctx: commands.Context):
        """Enable or Disable reporting for this server."""
        active = await self.config.guild(ctx.guild).active()
        active = not active
        await self.config.guild(ctx.guild).active.set(active)
        if active:
            await ctx.send(_("Reporting is now enabled"))
        else:
            await ctx.send(_("Reporting is now disabled."))

    async def internal_filter(self, m: discord.Member, mod=False, perms=None):
        if perms and m.guild_permissions >= perms:
            return True
        if mod and await self.bot.is_mod(m):
            return True
        # The following line is for consistency with how perms are handled
        # in Red, though I'm not sure it makse sense to use here.
        if await self.bot.is_owner(m):
            return True

    async def discover_guild(
        self,
        author: discord.User,
        *,
        mod: bool = False,
        permissions: Union[discord.Permissions, dict] = None,
        prompt: str = "",
    ):
        """
        discovers which of shared guilds between the bot
        and provided user based on conditions (mod or permissions is an or)
        prompt is for providing a user prompt for selection
        """
        shared_guilds = []
        if permissions is None:
            perms = discord.Permissions()
        elif isinstance(permissions, discord.Permissions):
            perms = permissions
        else:
            perms = discord.Permissions(**permissions)

        for guild in self.bot.guilds:
            x = guild.get_member(author.id)
            if x is not None:
                if await self.internal_filter(x, mod, perms):
                    shared_guilds.append(guild)
        if len(shared_guilds) == 0:
            raise ValueError("No Qualifying Shared Guilds")
        if len(shared_guilds) == 1:
            return shared_guilds[0]
        output = ""
        guilds = sorted(shared_guilds, key=lambda g: g.name)
        for i, guild in enumerate(guilds, 1):
            output += "{}: {}\n".format(i, guild.name)
        output += "\n{}".format(prompt)

        for page in pagify(output, delims=["\n"]):
            await author.send(box(page))

        try:
            message = await self.bot.wait_for(
                "message",
                check=MessagePredicate.same_context(channel=author.dm_channel, user=author),
                timeout=45,
            )
        except asyncio.TimeoutError:
            await author.send(_("You took too long to select. Try again later."))
            return None

        try:
            message = int(message.content.strip())
            guild = guilds[message - 1]
        except (ValueError, IndexError):
            await author.send(_("That wasn't a valid choice."))
            return None
        else:
            return guild

    async def send_report(self, msg: discord.Message, guild: discord.Guild):

        author = guild.get_member(msg.author.id)
        report = msg.clean_content

        channel_id = await self.config.guild(guild).output_channel()
        channel = guild.get_channel(channel_id)
        if channel is None:
            return None

        files: List[discord.File] = await Tunnel.files_from_attatch(msg)

        ticket_number = await self.config.guild(guild).next_ticket()
        await self.config.guild(guild).next_ticket.set(ticket_number + 1)

        if await self.bot.embed_requested(channel, author):
            em = discord.Embed(description=report)
            em.set_author(
                name=_("Report from {author}{maybe_nick}").format(
                    author=author, maybe_nick=(f" ({author.nick})" if author.nick else "")
                ),
                icon_url=author.avatar_url,
            )
            em.set_footer(text=_("Report #{}").format(ticket_number))
            send_content = None
        else:
            em = None
            send_content = _("Report from {author.mention} (Ticket #{number})").format(
                author=author, number=ticket_number
            )
            send_content += "\n" + report

        try:
            report_msg = await Tunnel.message_forwarder(
                destination=channel, content=send_content, embed=em, files=files
            )
        except (discord.Forbidden, discord.HTTPException):
            return None
        cur_pins = reversed(await channel.pins())
        if len(await channel.pins()) == 50:
            for pin in cur_pins:
                if pin.author == guild.me:
                    await pin.unpin()
                    break
        try:
            await report_msg[0].pin()
        except (discord.Forbidden, discord.HTTPException):
            # pass in this instance since pinning isn't required
            pass

        await self.config.custom("REPORT", guild.id, ticket_number).report.set(
            {"user_id": author.id, "report": report}
        )
        return ticket_number

    @commands.group(name="report", invoke_without_command=True)
    async def report(self, ctx: commands.Context, *, _report: str = ""):
        """Send a report.
        Use without arguments for interactive reporting, or do
        `[p]report <text>` to use it non-interactively.
        """
        author = ctx.author
        guild = ctx.guild
        if guild is None:
            guild = await self.discover_guild(
                author, prompt=_("Select a server to make a report in by number.")
            )
        if guild is None:
            return
        g_active = await self.config.guild(guild).active()
        if not g_active:
            return await author.send(_("Reporting has not been enabled for this server"))
        if guild.id not in self.antispam:
            self.antispam[guild.id] = {}
        if author.id not in self.antispam[guild.id]:
            self.antispam[guild.id][author.id] = AntiSpam(self.intervals)
        if self.antispam[guild.id][author.id].spammy:
            return await author.send(
                _(
                    "You've sent too many reports recently. "
                    "Please contact a server admin if this is important matter, "
                    "or please wait and try again later."
                )
            )
        if author.id in self.user_cache:
            return await author.send(
                _(
                    "Please finish making your prior report before trying to make an "
                    "additional one!"
                )
            )
        self.user_cache.append(author.id)

        if _report:
            _m = copy(ctx.message)
            _m.content = _report
            _m.content = _m.clean_content
            val = await self.send_report(_m, guild)
        else:
            try:
                await author.send(
                    _(
                        "Please respond to this message with your Report."
                        "\nYour report should be a single message"
                    )
                )
            except discord.Forbidden:
                return await ctx.send(_("This requires DMs enabled."))

            try:
                message = await self.bot.wait_for(
                    "message",
                    check=MessagePredicate.same_context(ctx, channel=author.dm_channel),
                    timeout=180,
                )
            except asyncio.TimeoutError:
                return await author.send(_("You took too long. Try again later."))
            else:
                val = await self.send_report(message, guild)

        with contextlib.suppress(discord.Forbidden, discord.HTTPException):
            if val is None:
                await author.send(
                    _("There was an error sending your report, please contact a server admin.")
                )
            else:
                await author.send(_("Your report was submitted. (Ticket #{})").format(val))
                self.antispam[guild.id][author.id].stamp()

    @report.after_invoke
    async def report_cleanup(self, ctx: commands.Context):
        """
        The logic is cleaner this way
        """
        if ctx.author.id in self.user_cache:
            self.user_cache.remove(ctx.author.id)
        if ctx.guild and ctx.invoked_subcommand is None:
            if ctx.channel.permissions_for(ctx.guild.me).manage_messages:
                try:
                    await ctx.message.delete()
                except discord.NotFound:
                    pass

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        """
        oh dear....
        """
        guild = self.bot.get_guild(payload.guild_id)
        report_emoji = await self.config.guild(guild).report_emoji()
        if report_emoji in str(payload.emoji):
            reporter = guild.get_member(payload.user_id)
            if reporter.bot:
                return
            channel = guild.get_channel(payload.channel_id)
            try:
                message = await channel.fetch_message(payload.message_id)
                await message.remove_reaction(payload.emoji, reporter)
            except Exception:
                print("errror")
                return

            report_channel_id = await self.config.guild(guild).output_channel()
            report_channel = guild.get_channel(report_channel_id)
            if report_channel.permissions_for(guild.me).embed_links:
                em = await self._build_embed(reporter, message)
                await report_channel.send(embed=em)
            else:
                msg = (
                    f"{reporter} has reported {message.author}\n"
                    f"> {message.content}"
                )[:len(message.jump_url)+5]
                await report_channel.send(msg + f"\n\n{message.jump_url}")

        if not str(payload.emoji) == "\N{NEGATIVE SQUARED CROSS MARK}":
            return

        _id = payload.message_id
        t = next(filter(lambda x: _id in x[1]["msgs"], self.tunnel_store.items()), None)

        if t is None:
            return
        tun = t[1]["tun"]
        if payload.user_id in [x.id for x in tun.members]:
            await tun.react_close(
                uid=payload.user_id, message=_("{closer} has closed the correspondence")
            )
            self.tunnel_store.pop(t[0], None)

    async def _build_embed(self, reporter: discord.Member, message: discord.Message) -> discord.Embed:
        channel = message.channel
        author = message.author
        em = discord.Embed(timestamp=message.created_at)
        em.description = message.content
        em.set_author(
            name=f"{reporter} has reported {author}",
            url=message.jump_url,
            icon_url=str(author.avatar_url)
        )
        if message.attachments != []:
            em.set_image(url=message.attachments[0].url)
        em.timestamp = message.created_at
        jump_link = _("\n\n[Click Here to view message]({link})").format(link=message.jump_url)
        if em.description:
            em.description = f"{em.description}{jump_link}"
        else:
            em.description = jump_link
        em.set_footer(text=f"{channel.guild.name} | #{channel.name}")
        return em

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        for k, v in self.tunnel_store.items():
            topic = _("Re: ticket# {1} in {0.name}").format(*k)
            # Tunnels won't forward unintended messages, this is safe
            msgs = await v["tun"].communicate(message=message, topic=topic)
            if msgs:
                self.tunnel_store[k]["msgs"] = msgs

    @commands.guild_only()
    @checks.mod_or_permissions(manage_roles=True)
    @report.command(name="interact")
    async def response(self, ctx, ticket_number: int):
        """Open a message tunnel.
        This tunnel will forward things you say in this channel
        to the ticket opener's direct messages.
        Tunnels do not persist across bot restarts.
        """

        guild = ctx.guild
        rec = await self.config.custom("REPORT", guild.id, ticket_number).report()

        try:
            user = guild.get_member(rec.get("user_id"))
        except KeyError:
            return await ctx.send(_("That ticket doesn't seem to exist"))

        if user is None:
            return await ctx.send(_("That user isn't here anymore."))

        tun = Tunnel(recipient=user, origin=ctx.channel, sender=ctx.author)

        if tun is None:
            return await ctx.send(
                _(
                    "Either you or the user you are trying to reach already "
                    "has an open communication."
                )
            )

        big_topic = _(
            " Anything you say or upload here "
            "(8MB file size limitation on uploads) "
            "will be forwarded to them until the communication is closed.\n"
            "You can close a communication at any point by reacting with "
            "the \N{NEGATIVE SQUARED CROSS MARK} to the last message recieved.\n"
            "Any message succesfully forwarded will be marked with "
            "\N{WHITE HEAVY CHECK MARK}.\n"
            "Tunnels are not persistent across bot restarts."
        )
        topic = (
            _(
                "A moderator in the server `{guild.name}` has opened a 2-way communication about "
                "ticket number {ticket_number}."
            ).format(guild=guild, ticket_number=ticket_number)
            + big_topic
        )
        try:
            m = await tun.communicate(message=ctx.message, topic=topic, skip_message_content=True)
        except discord.Forbidden:
            await ctx.send(_("That user has DMs disabled."))
        else:
            self.tunnel_store[(guild, ticket_number)] = {"tun": tun, "msgs": m}
            await ctx.send(
                _(
                    "You have opened a 2-way communication about ticket number {ticket_number}."
                ).format(ticket_number=ticket_number)
                + big_topic
            )
