import discord

from typing import Union

from redbot.core import commands, checks, Config
from redbot.core.utils.predicates import ReactionPredicate
from redbot.core.utils.menus import start_adding_reactions

from .event_obj import Event, ValidImage


class EventPoster(commands.Cog):
    """Create admin approved events/announcements"""

    __version__ = "1.2.2"
    __author__ = "TrustyJAID"

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=144014746356678656)
        default_guild = {
            "approval_channel": None,
            "announcement_channel": None,
            "ping": "@everyone",
            "events": {},
            "custom_links": {},
        }
        self.config.register_guild(**default_guild)

    @commands.command(name="event")
    @commands.guild_only()
    async def make_event(
        self, ctx: commands.Context, members: commands.Greedy[discord.Member], *, description: str
    ):
        """
            Create an event

            `[members...]` Add members already in the event you want to host.
            `<description>` provide a description for the event you're hosting.
            With custom keyword links setup this will add an image to the events thumbnail
            after being approved by an admin.
        """
        if not await self.config.guild(ctx.guild).approval_channel():
            return await ctx.send("No admin channel has been setup on this server.")
        if not await self.config.guild(ctx.guild).announcement_channel():
            return await ctx.send("No announcement channel has been setup on this server.")
        if str(ctx.author.id) in await self.config.guild(ctx.guild).events():
            if not await self.check_clear_event(ctx):
                return
        if ctx.author not in members:
            members.insert(0, ctx.author)
        channel = self.bot.get_channel(await self.config.guild(ctx.guild).approval_channel())
        event = Event(ctx.author, list(members), description)
        em = await self.make_event_embed(ctx, event)
        admin_msg = await channel.send(embed=em)
        start_adding_reactions(admin_msg, ReactionPredicate.YES_OR_NO_EMOJIS)
        pred = ReactionPredicate.yes_or_no(admin_msg)
        reaction, user = await ctx.bot.wait_for("reaction_add", check=pred)
        if pred.result:
            ping = await self.config.guild(ctx.guild).ping()
            new_channel = self.bot.get_channel(
                await self.config.guild(ctx.guild).announcement_channel()
            )
            event.approver = user
            event.channel = new_channel
            em.set_footer(text=f"Approved by {user}", icon_url=user.avatar_url)
            posted_message = await new_channel.send(ping, embed=em)
            event.message = posted_message
            async with self.config.guild(ctx.guild).events() as cur_events:
                cur_events[str(event.hoster.id)] = event.to_json()
        else:
            await ctx.send(f"{ctx.author.mention}, your event request was denied by an admin.")
            await admin_msg.delete()
            return

    @commands.command(name="clearevent", aliases=["endevent"])
    @commands.guild_only()
    @commands.bot_has_permissions(embed_links=True)
    async def clear_event(self, ctx, clear: bool = False):
        """
            Delete a stored event so you can create more

            `[clear]` yes/no to clear your current running event.
        """
        if str(ctx.author.id) not in await self.config.guild(ctx.guild).events():
            return await ctx.send("You don't have any events running.")
        elif not clear:
            event_data = await self.config.guild(ctx.guild).events()
            event = await Event.from_json(event_data[str(ctx.author.id)], ctx.guild)
            em = await self.make_event_embed(ctx, event)
            return await ctx.send(
                (
                    f"{ctx.author.display_name}, you're currently hosting. "
                    f"Type `{ctx.prefix}clearevent yes` to clear it."
                ),
                embed=em,
            )
        async with self.config.guild(ctx.guild).events() as events:
            event = await Event.from_json(events[str(ctx.author.id)], ctx.guild)
            await event.message.edit(content="This event has ended.")
            del events[str(ctx.author.id)]
        await ctx.tick()

    @commands.command(name="showevent")
    @commands.guild_only()
    @commands.bot_has_permissions(embed_links=True)
    async def show_event(self, ctx, member: discord.Member = None):
        """Show current event being run by a member"""
        if not member:
            member = ctx.author
        if str(member.id) not in await self.config.guild(ctx.guild).events():
            return await ctx.send(f"{member} does not have any events running.")
        event_data = await self.config.guild(ctx.guild).events()
        event = await Event.from_json(event_data[str(member.id)], ctx.guild)
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
    async def join_event(self, ctx, *, hoster: discord.Member):
        """Join an event being hosted"""
        if str(hoster.id) not in await self.config.guild(ctx.guild).events():
            return await ctx.send("That user is not currently hosting any events.")
        event_data = await self.config.guild(ctx.guild).events()
        event = await Event.from_json(event_data[str(hoster.id)], ctx.guild)
        if ctx.author in event.members:
            return await ctx.send("You're already participating in this event!")
        event.members.append(ctx.author)
        em = await self.make_event_embed(ctx, event)
        await event.message.edit(embed=em)
        async with self.config.guild(ctx.guild).events() as cur_events:
            cur_events[str(event.hoster.id)] = event.to_json()
        await ctx.tick()

    @commands.command(name="leaveevent")
    @commands.guild_only()
    async def leave_event(self, ctx, hoster: discord.Member):
        """Leave an event being hosted"""
        if str(hoster.id) not in await self.config.guild(ctx.guild).events():
            return await ctx.send("That user is not currently hosting any events.")
        event_data = await self.config.guild(ctx.guild).events()
        event = await Event.from_json(event_data[str(hoster.id)], ctx.guild)
        if ctx.author not in event.members:
            return await ctx.send("You're not participating in this event!")
        event.members.remove(ctx.author)
        em = await self.make_event_embed(ctx, event)
        await event.message.edit(embed=em)
        async with self.config.guild(ctx.guild).events() as cur_events:
            cur_events[str(event.hoster.id)] = event.to_json()
        await ctx.tick()

    @commands.command(name="removefromevent")
    @commands.guild_only()
    async def remove_from_event(self, ctx, member: discord.Member, hoster: discord.Member = None):
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
        if member not in event.members:
            return await ctx.send("That member is not participating in that event!")
        event.members.remove(member)
        em = await self.make_event_embed(ctx, event)
        await event.message.edit(embed=em)
        async with self.config.guild(ctx.guild).events() as cur_events:
            cur_events[str(event.hoster.id)] = event.to_json()
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

    async def make_event_embed(self, ctx, event):
        em = discord.Embed(title=event.event)
        em.set_author(name=f"{event.hoster} is hosting", icon_url=event.hoster.avatar_url)
        em.description = f"To join this event type `{ctx.prefix}join {event.hoster}`"
        for i, member in enumerate(event.members):
            em.add_field(name=f"Slot {i+1}", value=member.mention, inline=False)
        if event.approver:
            em.set_footer(text=f"Approved by {event.approver}", icon_url=event.approver.avatar_url)
        thumbnails = await self.config.guild(ctx.guild).custom_links()
        for name, link in thumbnails.items():
            if name.lower() in event.event.lower():
                em.set_thumbnail(url=link)
        return em

    async def check_clear_event(self, ctx):
        msg = await ctx.send("You already have an event running, would you like to cancel it?")
        start_adding_reactions(msg, ReactionPredicate.YES_OR_NO_EMOJIS)
        pred = ReactionPredicate.yes_or_no(msg, ctx.author)
        await ctx.bot.wait_for("reaction_add", check=pred)
        return pred.result

    @commands.group(name="eventset")
    @checks.mod_or_permissions(manage_messages=True)
    @commands.guild_only()
    async def event_settings(self, ctx: commands.Context):
        """Manage server specific settings for events"""
        pass

    @event_settings.command(name="channel")
    @commands.guild_only()
    async def set_channel(self, ctx: commands.Context, channel: discord.TextChannel = None):
        """Set the Announcement channel for events"""
        if not channel.permissions_for(ctx.me).embed_links:
            return await ctx.send("I require `Embed Links` permission to use that channel.")
        save_channel = None
        if channel:
            save_channel = channel.id
        await self.config.guild(ctx.guild).announcement_channel.set(save_channel)
        await ctx.tick()

    @event_settings.command(name="approvalchannel")
    @commands.guild_only()
    async def set_approval_channel(
        self, ctx: commands.Context, channel: discord.TextChannel = None
    ):
        """Set the admin approval channel"""
        if not channel.permissions_for(ctx.me).embed_links:
            return await ctx.send("I require `Embed Links` permission to use that channel.")
        if not channel.permissions_for(ctx.me).add_reactions:
            return await ctx.send("I require `Add Reactions` permission to use that channel.")
        save_channel = None
        if channel:
            save_channel = channel.id
        await self.config.guild(ctx.guild).approval_channel.set(save_channel)
        await ctx.tick()

    @event_settings.command(name="links")
    @commands.guild_only()
    async def set_custom_link(self, ctx: commands.Context, keyword: str, link: ValidImage):
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

    @event_settings.command(name="ping")
    @commands.guild_only()
    async def set_ping(self, ctx: commands.Context, *roles: Union[discord.Role, str]):
        """
            Set the ping to use when an event is announced

            `[roles...]` is a space separated list of roles to be pinged when an announcement
            is made. Use `here` or `everyone` if you want to ping that specific group of people.
        """
        msg = ", ".join(r.mention for r in roles if type(r) == discord.Role)
        msg += ", ".join(f"@{r}" for r in roles if r in ["here", "everyone"])
        await self.config.guild(ctx.guild).ping.set(msg)
        await ctx.tick()
