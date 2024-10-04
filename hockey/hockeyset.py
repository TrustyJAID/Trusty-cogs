import asyncio
import os
import re
from datetime import timedelta
from typing import Optional, Union

import aiohttp
import discord
from red_commons.logging import getLogger
from redbot.core import commands
from redbot.core.data_manager import cog_data_path
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import bold, humanize_list
from redbot.core.utils.views import ConfirmView

from .abc import HockeyMixin
from .constants import TEAMS
from .helper import StandingsFinder, StateFinder, TeamFinder
from .standings import Conferences, Divisions

_ = Translator("Hockey", __file__)

log = getLogger("red.trusty-cogs.Hockey")

hockeyset_commands = HockeyMixin.hockeyset_commands


class HockeySetCommands(HockeyMixin):
    """
    All the commands grouped under `[p]hockeyset`
    """

    @hockeyset_commands.command(name="settings")
    async def hockey_settings(self, ctx: commands.Context) -> None:
        """
        Show hockey settings for this server
        """
        if not ctx.guild:
            await ctx.send(_("This command can only work inside a server."))
            return
        await ctx.typing()
        guild: discord.Guild = ctx.guild
        standings_channel = guild.get_channel(await self.config.guild(guild).standings_channel())
        gdc_channels = (await self.config.guild(guild).gdc_chans()).values()
        gdt_channels = (await self.config.guild(guild).gdt_chans()).values()
        standings_chn = "None"
        standings_msg = "None"
        if gdc_channels is None:
            gdc_channels = []
        if standings_channel is not None:
            if ctx.channel.permissions_for(guild.me).embed_links:
                standings_chn = standings_channel.mention
            else:
                standings_chn = standings_channel.name
            standings_message = await self.config.guild(guild).standings_msg()
            if standings_message:
                try:
                    standings_msg = await standings_channel.fetch_message(standings_message)
                except (discord.errors.NotFound, discord.errors.Forbidden):
                    standings_msg = None
                    pass
            else:
                standings_msg = None
            if standings_msg is not None:
                standings_msg = standings_msg.jump_url
        channels = ""
        for channel in await self.config.all_channels():
            chn = guild.get_channel_or_thread(channel)
            if chn is not None:
                teams = humanize_list([t for t in await self.config.channel(chn).team()])
                is_gdc = "(GDC)" if chn.id in gdc_channels else ""
                is_gdt = "(GDT)" if chn.id in gdt_channels else ""
                game_states = await self.config.channel(chn).game_states()
                channels += f"{chn.mention}{is_gdc}{is_gdt}:\n"
                channels += _("Team(s): {teams}\n").format(teams=teams)
                if game_states:
                    channels += _("Game States: {game_states}\n").format(
                        game_states=humanize_list(game_states)
                    )

        if ctx.channel.permissions_for(guild.me).embed_links:
            em = discord.Embed(title=guild.name + _(" Hockey Settings"))
            em.colour = await self.bot.get_embed_colour(ctx.channel)
            em.description = channels
            em.add_field(name=_("Standings Settings"), value=f"{standings_msg}")
            await ctx.send(embed=em)
        else:
            msg = _(
                "{guild} Hockey Settings\n {channels}\nNotifications\n{notifications}"
                "\nStandings Settings\n{standings_chn}: {standings}\n"
            ).format(
                guild=guild.name,
                channels=channels,
                standings_chn=standings_chn,
                standings=standings_msg,
            )
            await ctx.send(msg)

    #######################################################################
    # All Hockey setup commands                                           #
    #######################################################################

    @commands.group(name="hockeyevents", aliases=["nhlevents"])
    @commands.bot_has_permissions(manage_events=True)
    @commands.admin_or_permissions(manage_guild=True)
    @commands.guild_only()
    async def hockey_events(self, ctx: commands.Context):
        """
        Commands for setting up discord guild events
        """

    @hockey_events.command(name="set")
    @commands.bot_has_permissions(manage_events=True)
    @commands.admin_or_permissions(manage_guild=True)
    @commands.guild_only()
    @commands.max_concurrency(1, commands.BucketType.guild)
    @commands.cooldown(1, 3600, commands.BucketType.guild)
    async def set_team_events(self, ctx: commands.Context, team: TeamFinder):
        """
        Create a scheduled server event for all games in the season for one team.

        This command can take a while to complete.
        """
        if not ctx.guild:
            await ctx.send(_("This command can only work inside a server."))
            return
        try:
            data = await self.api.club_schedule_season(team)
        except aiohttp.ClientConnectorError:
            await ctx.send(
                _("There's an issue accessing the NHL API at the moment. Try again later.")
            )
            log.exception("Error accessing NHL API")
            return
        games = data.remaining()
        number_of_games = str(len(games))
        view = ConfirmView(ctx.author)
        view.message = await ctx.send(
            _(
                "This will create {number_of_games} discord events for the remaining {team} games."
                "This can take a long time to complete. Are you sure you want to run this?"
            ).format(number_of_games=number_of_games, team=team),
            view=view,
        )
        await view.wait()
        if not view.result:
            ctx.command.reset_cooldown(ctx)
            await ctx.send(_("Okay I will not create the events."))
            return
        images_path = cog_data_path(self) / "teamlogos"
        if not os.path.isdir(images_path):
            os.mkdir(images_path)
        existing_events = {}
        for event in ctx.guild.scheduled_events:
            event_id = re.search(r"\n(\d{6,})", event.description)
            if event_id is not None:
                existing_events[event_id.group(1)] = event
        added = 0
        edited = 0
        async with ctx.typing():
            for game in games:
                start = game.game_start
                end = start + timedelta(hours=3)
                home = game.home_team
                away = game.away_team
                image_team = away if team == home else home
                image_file = images_path / f"{image_team}.png"
                image = None
                if not os.path.isfile(image_file) or os.path.getsize(image_file) == 0:
                    async with self.session.get(TEAMS[image_team]["logo"]) as resp:
                        image = await resp.read()
                    with image_file.open("wb") as outfile:
                        outfile.write(image)
                if os.path.getsize(image_file) != 0:
                    with open(image_file, "rb") as x:
                        image = x.read()

                name = f"{away} @ {home}"
                broadcasts = humanize_list([b.get("network", "Unknown") for b in game.broadcasts])
                description = name
                if broadcasts:
                    description += f"\nBroadcasts: {broadcasts}"
                game_id = str(game.id)
                description += f"\n\n{game_id}"
                if game_id in existing_events:
                    try:
                        if existing_events[game_id].start_time != start:
                            await existing_events[game_id].edit(
                                start_time=start, end_time=end, reason="Start time changed"
                            )
                            edited += 1
                        if existing_events[game_id].description != description:
                            await existing_events[game_id].edit(
                                description=description, reason="Description has changed"
                            )
                            edited += 1
                    except Exception:
                        # I don't care if these don't edit properly
                        pass
                    continue
                try:
                    await ctx.guild.create_scheduled_event(
                        name=f"{away} @ {home}",
                        description=description,
                        start_time=start,
                        location=game.venue,
                        end_time=end,
                        entity_type=discord.EntityType.external,
                        image=image or discord.utils.MISSING,
                        privacy_level=discord.PrivacyLevel.guild_only,
                    )
                    added += 1
                except Exception:
                    log.exception(
                        "Error creating scheduled event in %s for team %s", ctx.guild.id, team
                    )
                await asyncio.sleep(1)
        msg = f"Finished creating events for {added}/{number_of_games} games."
        if edited != 0:
            msg += f" Edited {edited} events with changed details."
        await ctx.send(msg)

    @hockeyset_commands.command(name="poststandings", aliases=["poststanding"])
    @commands.mod_or_permissions(manage_channels=True)
    async def post_standings(
        self,
        ctx: commands.Context,
        standings_type: StandingsFinder,
        channel: Union[discord.TextChannel, discord.Thread] = commands.CurrentChannel,
    ) -> None:
        """
        Posts automatic standings when all games for the day are done

        `<standings_type>` can be a division name or all
        `[channel]` The channel you want standings to be posted into, if not provided
        this will use the current channel.
        """
        if not ctx.guild:
            await ctx.send(_("This command can only work inside a server."))
            return
        await ctx.typing()
        guild = ctx.guild
        channel_perms = channel.permissions_for(guild.me)
        if not (
            channel_perms.send_messages
            and channel_perms.embed_links
            and channel_perms.read_message_history
        ):
            msg = _(
                "I require permission to send messages, embed "
                "links, and read message history in {channel}."
            ).format(channel=channel.mention)
            await ctx.send(msg)
            return
        valid_types = (
            ["all"] + [i.name.lower() for i in Divisions] + [i.name.lower() for i in Conferences]
        )
        if standings_type.lower() not in valid_types:
            msg = _("You must choose from: {standings_types}.").format(
                standings_types=humanize_list(valid_types)
            )
            await ctx.send(msg)
            return
        try:
            standings = await self.api.get_standings()
        except aiohttp.ClientConnectorError:
            await ctx.send(
                _("There's an issue accessing the NHL API at the moment. Try again later.")
            )
            log.exception("Error accessing NHL API")
            return
        if standings_type in [i.name.lower() for i in Divisions]:
            standing = Divisions(standings_type.title())
            em = await standings.make_division_standings_embed(standing)

        elif standings_type in [i.name.lower() for i in Conferences]:
            standing = Conferences(standings_type.title())
            em = await standings.make_conference_standings_embed(standing)
        else:
            em = await standings.all_standing_embed()
        await self.config.guild(guild).standings_type.set(standings_type)
        await self.config.guild(guild).standings_channel.set(channel.id)
        msg = _("Sending standings to {channel}").format(channel=channel.mention)
        await ctx.send(msg)
        message = await channel.send(embed=em)
        await self.config.guild(guild).standings_msg.set(message.id)
        msg = _(
            "{standings_type} standings will now be automatically updated in {channel}."
        ).format(standings_type=standings_type, channel=channel.mention)
        await ctx.send(msg)
        await self.config.guild(guild).post_standings.set(True)

    @hockeyset_commands.command()
    @commands.mod_or_permissions(manage_channels=True)
    async def togglestandings(self, ctx: commands.Context) -> None:
        """
        Toggles automatic standings updates

        This updates at the same time as the game day channels (usually 9AM PST)
        """
        if not ctx.guild:
            await ctx.send(_("This command can only work inside a server."))
            return
        await ctx.typing()
        guild = ctx.message.guild
        cur_state = not await self.config.guild(guild).post_standings()
        verb = _("will") if cur_state else _("won't")
        msg = _("Okay, standings ") + verb + _(" be updated automatically.")
        await self.config.guild(guild).post_standings.set(cur_state)
        await ctx.send(msg)

    @hockeyset_commands.command(name="countdown")
    @commands.mod_or_permissions(manage_channels=True)
    async def set_game_countdown_updates(
        self,
        ctx: commands.Context,
        channel: discord.TextChannel,
    ) -> None:
        """
        Toggle 60, 30, and 10 minute countdown updates for games in a specified channel
        """
        if not ctx.guild:
            await ctx.send(_("This command can only work inside a server."))
            return
        current = await self.config.channel(channel).countdown()
        await self.config.channel(channel).countdown.set(not current)
        if current:
            await ctx.send(
                _(
                    "60, 30, and 10 minute countdown messages have been disabled in {channel}"
                ).format(channel=channel.mention)
            )
        else:
            await ctx.send(
                _(
                    "60, 30, and 10 minute countdown messages have been enabled in {channel}"
                ).format(channel=channel.mention)
            )

    @hockeyset_commands.command(name="stateupdates")
    @commands.mod_or_permissions(manage_channels=True)
    async def set_game_state_updates(
        self,
        ctx: commands.Context,
        channel: discord.TextChannel,
        state: StateFinder,
    ) -> None:
        """
        Toggle specific updates from a designated channel

        `<channel>` is a text channel for the updates.
        `<state>` must be one of `preview`, `live`, `final`, `goal` and `periodrecap`.

        `preview` updates are the pre-game notifications 60, 30, and 10 minutes
        before the game starts and the pre-game notification at the start of the day.

        Note: This may disable pickems if it is not selected.
        `live` are the period start notifications.
        `final` is the final game update including 3 stars.
        `goal` is all goal updates.
        `periodrecap` is a recap of the period at the intermission.
        """
        if not ctx.guild:
            await ctx.send(_("This command can only work inside a server."))
            return
        await ctx.typing()
        cur_states = []
        added = []
        removed = []
        async with self.config.channel(channel).game_states() as game_states:
            if state.value in game_states:
                removed.append(state.value)
                game_states.remove(state.value)
            else:
                added.append(state.value)
                game_states.append(state.value)
            cur_states = game_states
        msg = _("{channel} game updates set to {states}").format(
            channel=channel.mention, states=humanize_list(cur_states) if cur_states else _("None")
        )
        if added:
            msg += "\n" + _("{states} was added.").format(states=bold(humanize_list(added)))
        if removed:
            msg += "\n" + _("{states} was removed.").format(states=bold(humanize_list(removed)))
        await ctx.send(msg)
        if not await self.config.channel(channel).team():
            await ctx.channel.send(
                _(
                    "You have not setup any team updates in {channel}. "
                    "You can do so with `{prefix}hockeyset add`."
                ).format(channel=channel.mention, prefix=ctx.prefix)
            )

    @hockeyset_commands.command(name="goalimage", hidden=True, with_app_command=False)
    @commands.mod_or_permissions(manage_channels=True)
    async def include_goal_image_toggle(
        self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None
    ):
        """
        Toggle including goal images when a goal is posted

        `[channel]` The channel you specifically want goal images enabled for.
        If channel is not provided the server-wide setting will be toggled instead.
        """
        if not ctx.guild:
            await ctx.send(_("This command can only work inside a server."))
            return
        await ctx.typing()
        if channel is None:
            current = not await self.config.guild(ctx.guild).include_goal_image()
            await self.config.guild(ctx.guild).include_goal_image.set(current)
            if current:
                await ctx.send(
                    _("I will include goal images whenever I post a goal embed in this server.")
                )
            else:
                await ctx.send(
                    _(
                        "I will not include goal images whenever I post a goal embed in this server."
                    )
                )
        else:
            current = not await self.config.channel(channel).include_goal_image()
            await self.config.channel(channel).include_goal_image.set(current)
            if current:
                await ctx.send(
                    _(
                        "I will include goal images whenever I post a goal embed in {channel}."
                    ).format(channel=channel.mention)
                )
            else:
                await ctx.send(
                    _(
                        "I will not include goal images whenever I post a goal embed in {channel}."
                    ).format(channel=channel.mention)
                )

    @hockeyset_commands.command(name="add", aliases=["addgoals"])
    @commands.mod_or_permissions(manage_channels=True)
    async def add_goals(
        self,
        ctx: commands.Context,
        team: TeamFinder,
        channel: Union[discord.TextChannel, discord.Thread] = commands.CurrentChannel,
    ) -> None:
        """
        Adds a hockey team goal updates to a channel do 'all' for all teams

        `<team>` needs to be all or part of an NHL team if more than one team
        match it will ask for the correct team.
        `[channel]` The channel to post updates into. Defaults to the current channel
        if not provided.
        """
        if not ctx.guild:
            await ctx.send(_("This command can only work inside a server."))
            return
        if not team:
            await ctx.send(_("You must provide a valid current team."))
            return
        # team_data = await self.get_team(team)
        async with ctx.typing():
            cur_teams = await self.config.channel(channel).team()
            cur_teams = [] if cur_teams is None else cur_teams
            if team in cur_teams:
                # await self.config.channel(channel).team.set([team])
                msg = _("{team} is already posting updates in {channel}").format(
                    team=team, channel=channel.mention
                )
            else:
                cur_teams.append(team)
                await self.config.channel(channel).team.set(cur_teams)
                msg = _("{team} goals will be posted in {channel}").format(
                    team=team, channel=channel.mention
                )
                if isinstance(channel, discord.Thread):
                    await self.config.channel(channel).parent.set(channel.parent.id)
        await ctx.send(msg)

    @hockeyset_commands.command(name="remove", aliases=["del", "rem", "delete"])
    @commands.mod_or_permissions(manage_channels=True)
    async def remove_goals(
        self,
        ctx: commands.Context,
        team: Optional[TeamFinder] = None,
        channel: Union[discord.TextChannel, discord.Thread] = commands.CurrentChannel,
    ) -> None:
        """
        Removes a teams goal updates from a channel
        defaults to the current channel
        """
        if not ctx.guild:
            await ctx.send(_("This command can only work inside a server."))
            return
        msg = _("No teams are currently being posted in {channel}.").format(
            channel=channel.mention
        )
        async with ctx.typing():
            cur_teams = await self.config.channel(channel).team()
            if team is None:
                await self.config.channel(channel).clear()
                msg = _("No game updates will be posted in {channel}.").format(
                    channel=channel.mention
                )

            if team is not None:
                # guild = ctx.message.guild
                if team in cur_teams:
                    cur_teams.remove(team)
                    if cur_teams == []:
                        await self.config.channel(channel).clear()
                        msg = _("No game updates will be posted in {channel}.").format(
                            channel=channel.mention
                        )
                    else:
                        await self.config.channel(channel).team.set(cur_teams)
                        msg = _("{team} goal updates removed from {channel}.").format(
                            team=team, channel=channel.mention
                        )
        await ctx.send(msg)
