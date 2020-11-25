import logging
from typing import Literal, Optional, Union

import discord
from redbot import VersionInfo, version_info
from redbot.core import Config, VersionInfo, checks, commands, version_info
from redbot.core.utils.chat_formatting import humanize_list, pagify
from redbot.core.utils.menus import start_adding_reactions
from redbot.core.utils.predicates import ReactionPredicate

from .event_obj import Event, ValidImage

log = logging.getLogger("red.trusty-cogs.EventPoster")

EVENT_EMOJIS = [
    "\N{WHITE HEAVY CHECK MARK}",
    "\N{NEGATIVE SQUARED CROSS MARK}",
    "\N{WHITE QUESTION MARK ORNAMENT}",
]


class EventPoster(commands.Cog):
    """Create admin approved events/announcements"""

    __version__ = "1.6.1"
    __author__ = "TrustyJAID"

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=144014746356678656)
        default_guild = {
            "approval_channel": None,
            "announcement_channel": None,
            "ping": "",
            "events": {},
            "custom_links": {},
            "default_max": None,
            "auto_end_events": False,
            "publish": False,
        }
        default_user = {"player_class": ""}
        self.config.register_guild(**default_guild)
        self.config.register_member(**default_user)
        self.event_cache = {}
        self.bot.loop.create_task(self.initialize())
        if version_info >= VersionInfo.from_str("3.4.0"):
            self.sanitize = {
                "allowed_mentions": discord.AllowedMentions(everyone=True, roles=True)
            }
        else:
            self.sanitize = {}

    def format_help_for_context(self, ctx: commands.Context):
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
        all_guilds = await self.config.all_guilds()
        for guild_id, data in all_guilds.items():
            if str(user_id) in data["events"]:
                del data["events"][str(user_id)]
                await self.config.guild_from_id(guild_id).events.set(data["events"])
        all_members = await self.config.all_members()
        for guild_id, members in all_members.items():
            if user_id in members:
                await self.config.member_from_ids(guild_id, user_id).clear()

    async def initialize(self) -> None:
        if version_info >= VersionInfo.from_str("3.2.0"):
            await self.bot.wait_until_red_ready()
        else:
            await self.bot.wait_until_ready()
        try:
            for guild_id in await self.config.all_guilds():
                guild = self.bot.get_guild(int(guild_id))
                if guild_id not in self.event_cache:
                    self.event_cache[guild_id] = {}
                if guild is None:
                    continue
                data = await self.config.guild(guild).events()
                for user_id, event_data in data.items():
                    try:
                        event = await Event.from_json(event_data, guild)
                    except (TypeError, KeyError, discord.errors.Forbidden):
                        log.error("Error loading events", exc_info=True)
                        continue
                    if event is None:
                        return
                    self.event_cache[guild_id][event.message.id] = event
        except Exception as e:
            log.error("Error loading events", exc_info=e)

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent) -> None:
        """
        Checks for reactions to the event
        """
        if str(payload.emoji) not in EVENT_EMOJIS:
            # log.debug("Not a valid yes or no emoji")
            return
        if payload.guild_id not in self.event_cache:
            return
        if payload.message_id not in self.event_cache[payload.guild_id]:
            return

        guild = self.bot.get_guild(payload.guild_id)
        user = guild.get_member(payload.user_id)
        if user.bot:
            return
        if version_info >= VersionInfo.from_str("3.4.0"):
            if await self.bot.cog_disabled_in_guild(self, guild):
                return
        event = self.event_cache[payload.guild_id][payload.message_id]
        if str(payload.emoji) == "\N{WHITE HEAVY CHECK MARK}":
            await self.add_user_to_event(user, event)
        if str(payload.emoji) == "\N{WHITE QUESTION MARK ORNAMENT}":
            await self.add_user_to_maybe(user, event)
        if str(payload.emoji) == "\N{NEGATIVE SQUARED CROSS MARK}":
            if user == event.hoster:
                async with self.config.guild(guild).events() as events:
                    event = await Event.from_json(events[str(user.id)], guild)
                    await event.message.edit(content="This event has ended.")
                    del events[str(user.id)]
                    del self.event_cache[guild.id][event.message.id]
                return
            await self.remove_user_from_event(user, event)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent) -> None:
        """
        Checks for reactions to the event
        """
        if str(payload.emoji) not in EVENT_EMOJIS:
            # log.debug("Not a valid yes or no emoji")
            return
        if payload.guild_id not in self.event_cache:
            return
        if payload.message_id not in self.event_cache[payload.guild_id]:
            return

        guild = self.bot.get_guild(payload.guild_id)
        user = guild.get_member(payload.user_id)
        if user.bot:
            return
        event = self.event_cache[payload.guild_id][payload.message_id]
        event_members = [m[0] for m in event.members]
        if str(payload.emoji) == "\N{WHITE HEAVY CHECK MARK}":
            if user == event.hoster:
                return
            if user not in event.maybe:
                await self.remove_user_from_event(user, event)
        if str(payload.emoji) == "\N{WHITE QUESTION MARK ORNAMENT}":
            if user == event.hoster:
                return
            if user not in event_members:
                await self.remove_user_from_event(user, event)

    async def add_user_to_event(
        self, user: discord.Member, event: Event, player_class: Optional[str] = ""
    ) -> None:
        event_members = [m[0] for m in event.members]
        if user in event_members:
            return
        if event.max_slots and len(event_members) >= event.max_slots:
            return
        if not player_class:
            player_class = await self.config.member(user).player_class()
        event.members.append((user, player_class))
        if user in event.maybe:
            event.maybe.remove(user)
        ctx = await self.bot.get_context(event.message)
        em = await self.make_event_embed(ctx, event)
        await event.message.edit(embed=em)
        async with self.config.guild(ctx.guild).events() as cur_events:
            cur_events[str(event.hoster.id)] = event.to_json()
        self.event_cache[ctx.guild.id][event.message.id] = event
        return

    async def add_user_to_maybe(
        self, user: discord.Member, event: Event, player_class: Optional[str] = ""
    ) -> None:
        event_members = [m[0] for m in event.members]
        if user in event.maybe:
            return
        event.maybe.append(user)
        if user in event_members:
            if not player_class:
                player_class = await self.config.member(user).player_class()
            event.members.remove((user, player_class))
        ctx = await self.bot.get_context(event.message)
        em = await self.make_event_embed(ctx, event)
        await event.message.edit(embed=em)
        async with self.config.guild(ctx.guild).events() as cur_events:
            cur_events[str(event.hoster.id)] = event.to_json()
        self.event_cache[ctx.guild.id][event.message.id] = event
        return

    async def remove_user_from_event(self, user: discord.Member, event: Event) -> None:
        event_members = [m[0] for m in event.members]
        if user in event_members:
            for member, player_class in event.members:
                if member == user:
                    event.members.remove((member, player_class))
            ctx = await self.bot.get_context(event.message)
            em = await self.make_event_embed(ctx, event)
            await event.message.edit(embed=em)
            async with self.config.guild(ctx.guild).events() as cur_events:
                cur_events[str(event.hoster.id)] = event.to_json()
            self.event_cache[ctx.guild.id][event.message.id] = event
        if user in event.maybe:
            event.maybe.remove(user)
            ctx = await self.bot.get_context(event.message)
            em = await self.make_event_embed(ctx, event)
            await event.message.edit(embed=em)
            async with self.config.guild(ctx.guild).events() as cur_events:
                cur_events[str(event.hoster.id)] = event.to_json()
            self.event_cache[ctx.guild.id][event.message.id] = event

    @commands.command(name="event")
    @commands.guild_only()
    async def make_event(
        self,
        ctx: commands.Context,
        members: commands.Greedy[discord.Member],
        max_slots: Optional[int] = None,
        *,
        description: str,
    ) -> None:
        """
        Create an event

        `[members...]` Add members already in the event you want to host.
        `[max_slots=None]` Specify maximum number of Slots the event can have, default is no limit.
        `<description>` provide a description for the event you're hosting.
        With custom keyword links setup this will add an image to the events thumbnail
        after being approved by an admin.
        """
        approval_channel = ctx.guild.get_channel(
            await self.config.guild(ctx.guild).approval_channel()
        )
        announcement_channel = ctx.guild.get_channel(
            await self.config.guild(ctx.guild).announcement_channel()
        )
        if not approval_channel:
            return await ctx.send(
                "No admin channel has been setup on this server. Use `[p]eventset approvalchannel` to add one."
            )
        if not announcement_channel:
            return await ctx.send(
                "No announcement channel has been setup on this server. Use `[p]eventset channel` to add one."
            )
        if str(ctx.author.id) in await self.config.guild(ctx.guild).events():
            if not await self.check_clear_event(ctx):
                return
        if ctx.author not in members:
            members.insert(0, ctx.author)
        member_list = []
        for member in members:
            member_list.append((member, await self.config.member(member).player_class()))

        if not max_slots:

            max_slots = await self.config.guild(ctx.guild).default_max()
            # log.debug(f"using default {max_slots}")
        event = Event(
            hoster=ctx.author, members=list(member_list), event=description, max_slots=max_slots
        )
        em = await self.make_event_embed(ctx, event)
        admin_msg = await approval_channel.send(embed=em)
        start_adding_reactions(admin_msg, ReactionPredicate.YES_OR_NO_EMOJIS)
        pred = ReactionPredicate.yes_or_no(admin_msg)
        reaction, user = await ctx.bot.wait_for("reaction_add", check=pred)
        if pred.result:
            ping = await self.config.guild(ctx.guild).ping()
            publish = (
                await self.config.guild(ctx.guild).publish() and announcement_channel.is_news()
            )
            event.approver = user
            event.channel = announcement_channel
            em.set_footer(text=f"Approved by {user}", icon_url=user.avatar_url)
            posted_message = await announcement_channel.send(ping, embed=em, **self.sanitize)
            if publish:
                try:
                    await posted_message.publish()
                except (discord.errors.Forbidden, discord.errors.HTTPException):
                    log.debug("Event Channel is not a news channel.")
                    pass
            event.message = posted_message
            async with self.config.guild(ctx.guild).events() as cur_events:
                cur_events[str(event.hoster.id)] = event.to_json()
            if ctx.guild.id not in self.event_cache:
                self.event_cache[ctx.guild.id] = {}
            self.event_cache[ctx.guild.id][posted_message.id] = event
            try:
                start_adding_reactions(posted_message, EVENT_EMOJIS)
            except discord.errors.Forbidden:
                pass
        else:
            await ctx.send(f"{ctx.author.mention}, your event request was denied by an admin.")
            await admin_msg.delete()
            return

    @commands.command(name="clearevent", aliases=["endevent"])
    @commands.guild_only()
    @commands.bot_has_permissions(embed_links=True)
    async def clear_event(self, ctx: commands.Context, clear: bool = False) -> None:
        """
        Delete a stored event so you can create more

        `[clear]` yes/no to clear your current running event.
        """
        if str(ctx.author.id) not in await self.config.guild(ctx.guild).events():
            return await ctx.send("You don't have any events running.")
        elif not clear:
            event_data = await self.config.guild(ctx.guild).events()
            event = await Event.from_json(event_data[str(ctx.author.id)], ctx.guild)
            if not event:
                async with self.config.guild(ctx.guild).events() as events:
                    # clear the broken event
                    del events[str(ctx.author.id)]
                    del self.event_cache[ctx.guild.id][event.message.id]
                return await ctx.send("You don't have any events running.")
            em = await self.make_event_embed(ctx, event)
            return await ctx.send(
                (
                    f"{ctx.author.display_name}, you're currently hosting. "
                    f"Type `{ctx.prefix}clearevent yes` to clear it."
                ),
                embed=em,
            )
        else:
            async with self.config.guild(ctx.guild).events() as events:
                event = await Event.from_json(events[str(ctx.author.id)], ctx.guild)
                await event.message.edit(content="This event has ended.")
                del events[str(ctx.author.id)]
                del self.event_cache[ctx.guild.id][event.message.id]
            await ctx.tick()

    @commands.command(name="showevent")
    @commands.guild_only()
    @commands.bot_has_permissions(embed_links=True)
    async def show_event(self, ctx: commands.Context, member: discord.Member = None) -> None:
        """Show current event being run by a member"""
        if not member:
            member = ctx.author
        if str(member.id) not in await self.config.guild(ctx.guild).events():
            return await ctx.send(f"{member} does not have any events running.")
        event_data = await self.config.guild(ctx.guild).events()
        event = await Event.from_json(event_data[str(member.id)], ctx.guild)
        if not event:
            async with self.config.guild(ctx.guild).events() as events:
                # clear the broken event
                del events[str(ctx.author.id)]
                del self.event_cache[ctx.guild.id][event.message.id]
            return await ctx.send(f"{member.display_name} is not currently hosting an event.")
        em = await self.make_event_embed(ctx, event)
        await ctx.send(
            (
                f"{member.display_name} is currently hosting. "
                f"Type `{ctx.prefix}clearevent yes` to clear it."
            ),
            embed=em,
        )

    @commands.command(name="join")
    @commands.guild_only()
    async def join_event(
        self,
        ctx: commands.Context,
        hoster: discord.Member,
        *,
        player_class: Optional[str] = None,
    ) -> None:
        """Join an event being hosted"""
        if str(hoster.id) not in await self.config.guild(ctx.guild).events():
            return await ctx.send("That user is not currently hosting any events.")
        event_data = await self.config.guild(ctx.guild).events()
        event = await Event.from_json(event_data[str(hoster.id)], ctx.guild)
        if not event:
            async with self.config.guild(ctx.guild).events() as events:
                # clear the broken event
                del events[str(ctx.author.id)]
                del self.event_cache[ctx.guild.id][event.message.id]
            return await ctx.send("That user is not currently hosting any events.")
        event_members = [m[0] for m in event.members]
        if ctx.author in event_members:
            return await ctx.send("You're already participating in this event!")
        await self.add_user_to_event(ctx.author, event, player_class)
        await ctx.tick()

    @commands.command(name="leaveevent")
    @commands.guild_only()
    async def leave_event(self, ctx: commands.Context, hoster: discord.Member) -> None:
        """Leave an event being hosted"""
        if str(hoster.id) not in await self.config.guild(ctx.guild).events():
            return await ctx.send("That user is not currently hosting any events.")
        event_data = await self.config.guild(ctx.guild).events()
        event = await Event.from_json(event_data[str(hoster.id)], ctx.guild)
        if not event:
            async with self.config.guild(ctx.guild).events() as events:
                # clear the broken event
                del events[str(ctx.author.id)]
                del self.event_cache[ctx.guild.id][event.message.id]
            return await ctx.send("That user is not currently hosting any events.")
        event_members = [m[0] for m in event.members]
        if ctx.author not in event_members:
            return await ctx.send("You're not participating in this event!")
        await self.remove_user_from_event(ctx.author, event)
        await ctx.tick()

    @commands.command(name="removefromevent")
    @commands.guild_only()
    async def remove_from_event(
        self, ctx: commands.Context, member: discord.Member, hoster: discord.Member = None
    ) -> None:
        """
        Remove a user from an event you're hosting

        `<member>` The member to remove from your event
        `<hoster>` mod/admin only to specify whos event to remove a user from.
        """
        if hoster and not await self.is_mod_or_admin(ctx.author):
            return await ctx.send("You cannot remove a member from someone elses event")
        if not hoster:
            hoster = ctx.author
        if member is hoster:
            return await ctx.send("You cannot remove the hoster from this event.")
        if str(hoster.id) not in await self.config.guild(ctx.guild).events():
            return await ctx.send("You are not currently hosting any events.")
        event_data = await self.config.guild(ctx.guild).events()
        event = await Event.from_json(event_data[str(ctx.author.id)], ctx.guild)
        if not event:
            async with self.config.guild(ctx.guild).events() as events:
                # clear the broken event
                del events[str(ctx.author.id)]
                del self.event_cache[ctx.guild.id][event.message.id]
            return await ctx.send("That user is not currently hosting any events.")
        event_members = [m[0] for m in event.members]
        if member not in event_members:
            return await ctx.send("That member is not participating in that event!")
        await self.remove_from_event(member, event)
        await ctx.tick()

    async def is_mod_or_admin(self, member: discord.Member) -> bool:
        guild = member.guild
        if member == guild.owner:
            return True
        if await self.bot.is_owner(member):
            return True
        if await self.bot.is_admin(member):
            return True
        if await self.bot.is_mod(member):
            return True
        return False

    async def make_event_embed(self, ctx: commands.Context, event: Event) -> discord.Embed:
        em = discord.Embed(title=event.event)
        em.set_author(name=f"{event.hoster} is hosting", icon_url=event.hoster.avatar_url)
        try:
            prefixes = await self.bot.get_valid_prefixes(ctx.guild)
            prefix = prefixes[0]
        except AttributeError:
            prefixes = await self.bot.get_prefix(ctx.message)
            prefix = prefixes[0]
        max_slots_msg = ""
        if event.max_slots:
            slots = event.max_slots - len(event.members)
            if slots < 0:
                slots = 0
            max_slots_msg = f"**{slots} slots available.**"
        em.description = (
            f"To join this event type `{prefix}join {event.hoster}`" f"\n\n{max_slots_msg}"
        )
        player_list = ""
        for i, member in enumerate(event.members):
            player_class = ""
            if member[1]:
                player_class = f" - {member[1]}"
            player_list += f"**Slot {i+1}**\n{member[0].mention}{player_class}\n"
        for page in pagify(player_list, shorten_by=1024):
            em.add_field(name="Attendees", value=page)
        if event.maybe and len(em.fields) < 25:
            em.add_field(name="Maybe", value=humanize_list([m.mention for m in event.maybe]))
        if event.approver:
            em.set_footer(text=f"Approved by {event.approver}", icon_url=event.approver.avatar_url)
        thumbnails = await self.config.guild(ctx.guild).custom_links()
        for name, link in thumbnails.items():
            if name.lower() in event.event.lower():
                em.set_thumbnail(url=link)
        return em

    async def check_clear_event(self, ctx: commands.Context) -> bool:
        msg = await ctx.send("You already have an event running, would you like to cancel it?")
        start_adding_reactions(msg, ReactionPredicate.YES_OR_NO_EMOJIS)
        pred = ReactionPredicate.yes_or_no(msg, ctx.author)
        await ctx.bot.wait_for("reaction_add", check=pred)
        return pred.result

    @commands.group(name="eventset")
    @commands.guild_only()
    async def event_settings(self, ctx: commands.Context) -> None:
        """Manage server specific settings for events"""
        pass

    @event_settings.command(name="publish")
    @commands.guild_only()
    async def set_guild_publish(self, ctx: commands.Context, publish: bool):
        """
        Toggle publishing events in news channels.
        """
        announcement_channel = await self.config.guild(ctx.guild).announcement_channel()
        chan = ctx.guild.get_channel(announcement_channel)
        if chan and chan.is_news():
            await self.config.guild(ctx.guild).publish.set(publish)
            if publish:
                await ctx.send("I will now publish events posted in this server.")
            else:
                await ctx.send("I will not publish events posted in this server.")
        elif chan and not chan.is_news():
            await ctx.send("The announcement channel set is not a news channel I can publish in.")
        else:
            await ctx.send(
                "No announcement channel has been setup. Use `[p]eventset channel` to create an announcement channel."
            )

    @event_settings.command(name="playerclass")
    @commands.guild_only()
    async def set_default_player_class(
        self, ctx: commands.Context, *, player_class: str = ""
    ) -> None:
        """
        Set's the users default player class. If nothing is provided this will be rest.

        If the user has set this and does not provide a `player_class` in the join command,
        this setting will be used.
        """
        await self.config.member(ctx.author).player_class.set(player_class)
        if player_class:
            await ctx.send(
                "Your player class has been set to {player_class}".format(
                    player_class=player_class
                )
            )
        else:
            await ctx.send("Your player class has been reset.")

    @event_settings.command(name="defaultmax", aliases=["max"])
    @checks.mod_or_permissions(manage_messages=True)
    @commands.guild_only()
    async def set_default_max_slots(
        self, ctx: commands.Context, default_max: Optional[int] = None
    ) -> None:
        """
        Set's the servers default maximum slots

        This can be useful for defining the maximum number of slots allowed for an event.
        """
        await self.config.guild(ctx.guild).default_max.set(default_max)
        await ctx.send(
            "Default maximum slots for events set to {default_max} slots.".format(
                default_max=default_max
            )
        )

    @event_settings.command(name="channel")
    @checks.mod_or_permissions(manage_messages=True)
    @commands.guild_only()
    async def set_channel(
        self, ctx: commands.Context, channel: discord.TextChannel = None
    ) -> None:
        """
        Set the Announcement channel for events

        Providing no channel will clear the channel.
        """
        if channel and not channel.permissions_for(ctx.me).embed_links:
            return await ctx.send("I require `Embed Links` permission to use that channel.")
        save_channel = None
        reply = "Announcement channel "
        if channel:
            save_channel = channel.id
            reply += "set to {chan}".format(chan=channel.mention)
            await self.config.guild(ctx.guild).announcement_channel.set(save_channel)
        else:
            reply += "cleared."
            await self.config.guild(ctx.guild).announcement_channel.clear()
        await ctx.send(reply)

    @event_settings.command(name="approvalchannel", aliases=["adminchannel"])
    @checks.mod_or_permissions(manage_messages=True)
    @commands.guild_only()
    async def set_approval_channel(
        self, ctx: commands.Context, channel: discord.TextChannel = None
    ) -> None:
        """
        Set the admin approval channel

        Providing no channel will clear the channel.
        """
        if channel and not channel.permissions_for(ctx.me).embed_links:
            return await ctx.send("I require `Embed Links` permission to use that channel.")
        if channel and not channel.permissions_for(ctx.me).add_reactions:
            return await ctx.send("I require `Add Reactions` permission to use that channel.")
        save_channel = None
        reply = "Admin approval channel "
        if channel:
            save_channel = channel.id
            reply += "set to {chan}.".format(chan=channel.mention)
            await self.config.guild(ctx.guild).approval_channel.set(save_channel)
        else:
            await self.config.guild(ctx.guild).approval_channel.clear()
            reply += "cleared."

        await ctx.send(reply)

    @event_settings.command(name="links")
    @checks.mod_or_permissions(manage_messages=True)
    @commands.guild_only()
    async def set_custom_link(self, ctx: commands.Context, keyword: str, link: ValidImage) -> None:
        """
        Set the custom thumbnail for events

        `<keyword>` is the word that will be searched for in event titles.
        `<link>` needs to be an image link to be used for the thumbnail when the keyword
        is found in the event title.
        """
        async with self.config.guild(ctx.guild).custom_links() as custom_links:
            if keyword.lower() not in custom_links:
                custom_links[keyword.lower()] = link
        await ctx.tick()

    @event_settings.command(name="ping", aliases=["mention"])
    @checks.mod_or_permissions(manage_messages=True)
    @commands.guild_only()
    async def set_ping(self, ctx: commands.Context, *roles: Union[discord.Role, str]) -> None:
        """
        Set the ping to use when an event is announced

        `[roles...]` is a space separated list of roles to be pinged when an announcement
        is made. Use `here` or `everyone` if you want to ping that specific group of people.
        """
        msg = ", ".join(r.mention for r in roles if type(r) == discord.Role)
        msg += ", ".join(f"@{r}" for r in roles if r in ["here", "everyone"])
        await self.config.guild(ctx.guild).ping.set(msg)
        await ctx.tick()
