from datetime import datetime, timedelta, timezone
from typing import Optional, Union

import aiohttp
import discord
from red_commons.logging import getLogger
from redbot.core import commands
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import bold, humanize_list

from .abc import HockeyMixin
from .game import Game
from .helper import StateFinder, TeamFinder, get_chn_name, get_team_role

log = getLogger("red.trusty-cogs.Hockey")

_ = Translator("Hockey", __file__)

hockey_commands = HockeyMixin.hockey_commands


class GameDayThreads(HockeyMixin):
    """
    All the commands grouped under `[p]gdc`
    """

    #######################################################################
    # GDC Commands                                                        #
    #######################################################################

    @hockey_commands.group()
    @commands.mod_or_permissions(manage_channels=True)
    @commands.guild_only()
    async def gdt(self, ctx: commands.Context) -> None:
        """
        Game Day Thread setup for the server

        You can setup only a single team or all teams for the server
        Game day channels are deleted and created on the day after the game is played
        usually around 9AM PST
        """

    @gdt.command(name="settings", aliases=["info"])
    @commands.mod_or_permissions(manage_channels=True)
    async def gdt_settings(self, ctx: commands.Context) -> None:
        """
        Show the current Game Day Thread Settings
        """
        if not ctx.guild:
            await ctx.send(_("This command can only work inside a server."))
            return
        guild = ctx.guild
        create_threads = await self.config.guild(guild).create_threads()
        if create_threads is None:
            msg = _("Game Day Threads are not setup on this server.")
            await ctx.send(msg)
            return
        team = await self.config.guild(guild).gdt_team()
        if team is None:
            team = "None"
        threads = (await self.config.guild(guild).gdt_chans()).values()
        channel = guild.get_channel(await self.config.guild(guild).gdt_channel())
        game_states = await self.config.guild(guild).gdt_state_updates()
        countdown = await self.config.guild(guild).gdt_countdown()
        if channel is not None:
            channel = channel.name
        if threads is not None:
            created_threads = ""
            for channel in threads:
                chn = guild.get_thread(channel)
                if chn is not None:
                    created_threads += f"{chn.mention}\n"
                else:
                    created_threads += "<#{}>\n".format(channel)
            if len(threads) == 0:
                created_threads = "None"
        else:
            created_threads = "None"
        update_gdt = await self.config.guild(guild).update_gdt()
        if not ctx.channel.permissions_for(guild.me).embed_links:
            msg = _(
                "```GDT settings for {guild}\nCreate Game Day Threads: {create_threads}\n"
                "Edit Start Message: {gdt_update}\nTeam: {team}\n"
                "Current Threads: {created_threads}\nDefault Game State: {game_states}\n"
                "Game Start Countdown: {countdown}\n```"
            ).format(
                guild=guild.name,
                create_threads=create_threads,
                gdt_update=update_gdt,
                team=team,
                created_threads=created_threads,
                game_states=humanize_list(game_states),
                countdown=countdown,
            )
            await ctx.send(msg)
        if ctx.channel.permissions_for(guild.me).embed_links:
            em = discord.Embed(title=_("GDT settings for ") + guild.name)
            em.colour = await self.bot.get_embed_colour(ctx.channel)
            em.add_field(name=_("Create Game Day Threads"), value=str(create_threads))
            em.add_field(name=_("Update GDT"), value=str(update_gdt))
            em.add_field(name=_("Team"), value=str(team))
            em.add_field(name=_("Current Threads"), value=created_threads[:1024])
            if not game_states:
                game_states = ["None"]
            em.add_field(name=_("Default Game States"), value=humanize_list(game_states))
            em.add_field(name=_("Game Start Countdown"), value=str(countdown))
            await ctx.send(embed=em)

    @gdt.command(name="delete")
    @commands.mod_or_permissions(manage_channels=True)
    async def gdt_delete(self, ctx: commands.Context) -> None:
        """
        Delete all current game day threads for the server
        """
        if not ctx.guild:
            await ctx.send(_("This command can only work inside a server."))
            return
        await ctx.typing()
        await self.delete_gdt(ctx.guild)
        msg = _("Game day Threads cleared.")
        await ctx.send(msg)

    @gdt.command(name="defaultstate")
    @commands.mod_or_permissions(manage_channels=True)
    async def gdt_default_game_state(self, ctx: commands.Context, state: StateFinder) -> None:
        """
        Set the default game state updates for Game Day Channels.

        `<state>` must be any combination of `preview`, `live`, `final`, and `goal`.

        `preview` updates are the pre-game notifications 60, 30, and 10 minutes before the game starts.
        `live` are the period start notifications.
        `final` is the final game update including 3 stars.
        `goal` is all the goal updates.
        """
        if not ctx.guild:
            await ctx.send(_("This command can only work inside a server."))
            return
        cur_state = await self.config.guild(ctx.guild).gdt_state_updates()
        added = []
        removed = []
        if state.value in cur_state:
            removed.append(state.value)
            cur_state.remove(state.value)
        else:
            added.append(state.value)
            cur_state.append(state.value)
        await self.config.guild(ctx.guild).gdt_state_updates.set(cur_state)
        if cur_state:
            msg = _("GDT game updates set to {states}").format(
                states=humanize_list(list(set(cur_state)))
            )
            if added:
                msg += "\n" + _("{states} was added.").format(states=bold(humanize_list(added)))
            if removed:
                msg += "\n" + _("{states} was removed.").format(
                    states=bold(humanize_list(removed))
                )
            await ctx.send(msg)
        else:
            msg = _("GDT game updates not set")
            await ctx.send(msg)

    @gdt.command(name="countdown")
    @commands.mod_or_permissions(manage_channels=True)
    async def set_gdt_countdown_updates(
        self,
        ctx: commands.Context,
    ) -> None:
        """
        Toggle 60, 30, and 10 minute countdown updates in game day threads
        """
        if not ctx.guild:
            await ctx.send(_("This command can only work inside a server."))
            return
        current = await self.config.guild(ctx.guild).gdt_countdown()
        await self.config.guild(ctx.guild).gdt_countdown.set(not current)
        if current:
            await ctx.send(
                _(
                    "60, 30, and 10 minute countdown messages have been disabled in future game day threads."
                )
            )
        else:
            await ctx.send(
                _(
                    "60, 30, and 10 minute countdown messages have been enabled in future game day threads."
                )
            )

    @gdt.command(name="updates")
    @commands.mod_or_permissions(manage_channels=True)
    async def gdt_update_start(self, ctx: commands.Context, update_start: bool) -> None:
        """
        Set whether or not the starting thread message will update as the game progresses.

        `<update_start>` either true or false.
        """
        if not ctx.guild:
            await ctx.send(_("This command can only work inside a server."))
            return
        await self.config.guild(ctx.guild).update_gdt.set(update_start)
        if update_start:
            msg = _("Game day threads will update as the game progresses.")
        else:
            msg = _("Game day threads will not update as the game progresses.")
        await ctx.send(msg)

    @gdt.command(name="create")
    @commands.mod_or_permissions(manage_channels=True)
    async def gdt_create(self, ctx: commands.Context) -> None:
        """
        Creates the next gdt for the server
        """
        if not ctx.guild:
            await ctx.send(_("This command can only work inside a server."))
            return
        await ctx.typing()
        if not await self.config.guild(ctx.guild).gdt_team():
            msg = _("No team was setup for game day threads in this server.")
            await ctx.send(msg)
        if await self.config.guild(ctx.guild).create_threads():
            try:
                await self.create_gdt(ctx.guild)
            except aiohttp.ClientConnectorError:
                await ctx.send(
                    _("There's an issue accessing the NHL API at the moment. Try again later.")
                )
                log.exception("Error accessing NHL API")
                return
        else:
            msg = _("You need to first toggle thread creation with `{prefix}gdt toggle`.").format(
                prefix=ctx.clean_prefix
            )
            await ctx.send(msg)
            return
        msg = _("Game day threads created.")
        await ctx.send(msg)

    @gdt.command(name="toggle")
    @commands.mod_or_permissions(manage_channels=True)
    async def gdt_toggle(self, ctx: commands.Context) -> None:
        """
        Toggles the game day channel creation on this server
        """
        if not ctx.guild:
            await ctx.send(_("This command can only work inside a server."))
            return
        await ctx.typing()
        guild = ctx.guild
        if await self.config.guild(guild).create_channels():
            msg = _(
                "You cannot have both game day channels and game day threads in the same server. "
                "Use `{prefix}{command}` first to disable game day channels then try again."
            ).format(prefix=ctx.clean_prefix, command=self.gdc_toggle.qualified_name)
            await ctx.send(msg)
            return
        cur_setting = not await self.config.guild(guild).create_threads()
        verb = _("will") if cur_setting else _("won't")
        msg = _("Game day threads ") + verb + _(" be created on this server.")
        await self.config.guild(guild).create_threads.set(cur_setting)
        await ctx.send(msg)

    @gdt.command(name="role")
    @commands.mod_or_permissions(manage_channels=True)
    async def gdt_role(
        self,
        ctx: commands.Context,
        team_name: Optional[bool] = False,
        *,
        role: Optional[discord.Role] = None,
    ) -> None:
        """
        Set the role that will be pinged when a new thread is created automatically
        letting users join the thread.

        `[team_name=False]` If this is true the bot will search for existing team Roles and
        ping both if they exist.
        `[role]` If this is set only that role will be pinged when all game day threads
        are created in the server.

        Note: This is limited to 100 members at once due to a discord limitation.
        """
        if not ctx.guild:
            await ctx.send(_("This command can only work inside a server."))
            return
        await ctx.typing()
        if role is None and not team_name:
            await self.config.guild(ctx.guild).gdt_role.clear()
            await ctx.send(_("I will not notify any role when a new thread is created."))
        else:
            if team_name:
                await self.config.guild(ctx.guild).gdt_role.set("team")
                await ctx.send(
                    _(
                        "I will now notify each team's role when a new thread is created if the role exists."
                    )
                )
            elif role:
                await self.config.guild(ctx.guild).gdt_role.set(role.id)
                await ctx.send(
                    _("I will now notify {role} when a new thread is created.").format(
                        role=role.mention
                    )
                )
            else:
                current = await self.config.guild(ctx.guild).gdt_role()
                if current == "team":
                    await ctx.send(
                        _("I will continue to notify each team's role when GDT's are created.")
                    )
                elif current:
                    if role := ctx.guild.get_role(current):
                        await ctx.send(
                            _(
                                "I will continue to notify {role} role when GDT's are created."
                            ).format(role=role.mention)
                        )
                    else:
                        await ctx.send(
                            _(
                                "The previously designated role could not be found so I will not notify anyone."
                            )
                        )
                else:
                    await ctx.send(_("I will not notify any role when a new thread is created."))

    # @gdt.command(name="channel")
    # @commands.mod_or_permissions(manage_channels=True)
    async def gdt_channel(self, ctx: commands.Context, channel: discord.TextChannel) -> None:
        """
        Change the category for channel creation. Channel is case sensitive.
        """
        msg = _("Game day threads will be created in {channel}.").format(channel=channel.mention)
        await self.config.guild(ctx.guild).gdt_channel.set(channel.id)
        await ctx.send(msg)

    @gdt.command(name="test", with_app_command=False)
    @commands.is_owner()
    async def test_gdt(self, ctx: commands.Context) -> None:
        """
        Test checking for new game day channels
        """
        if not ctx.guild:
            await ctx.send(_("This command can only work inside a server."))
            return
        await self.check_new_gdt()
        await ctx.tick()

    @gdt.command(name="setup")
    @commands.guild_only()
    @commands.mod_or_permissions(manage_channels=True)
    async def gdt_setup(
        self,
        ctx: commands.Context,
        team: TeamFinder,
        channel: Optional[
            Union[discord.TextChannel, discord.ForumChannel]
        ] = commands.CurrentChannel,
    ) -> None:
        """
        Setup game day channels for a single team or all teams

        Required parameters:
        `<team>` must use quotes if a space is in the name will search for partial team name

        Optional Parameters:
        `[channel]` The channel that game day threads will be created in. If not provided will default
        to the current text channel.
        """
        if not ctx.guild:
            await ctx.send(_("This command can only work inside a server."))
            return
        await ctx.typing()
        guild: discord.Guild = ctx.guild
        if await self.config.guild(guild).create_channels():
            msg = _(
                "You cannot have both game day channels and game day threads in the same server. "
                "Use `{prefix}{command}` first to disable game day channels then try again."
            ).format(prefix=ctx.clean_prefix, command=self.gdc_toggle.qualified_name)
            await ctx.send(msg)
            return
        if team is None:
            msg = _("You must provide a valid current team.")
            await ctx.send(msg)
            return
        if not isinstance(channel, (discord.TextChannel, discord.ForumChannel)):
            await ctx.send(
                _(
                    "I can only create game day threads in a regular Text Channel or a Forum Channel."
                )
            )
            return
        if not channel.permissions_for(guild.me).create_public_threads:
            msg = _("I don't have permission to create public threads in this channel.")
            await ctx.send(msg)
            return
        await self.delete_gdt(guild)
        await self.config.guild(guild).gdt_channel.set(channel.id)
        await self.config.guild(guild).gdt_team.set(team)
        await self.config.guild(guild).create_threads.set(True)
        if team.lower() != "all":
            try:
                await self.create_gdt(guild)
            except aiohttp.ClientConnectorError:
                await ctx.send(
                    _("There's an issue accessing the NHL API at the moment. Try again later.")
                )
                log.exception("Error accessing NHL API")
                return
        else:
            try:
                game_list = await self.api.get_games()
            except aiohttp.ClientConnectorError:
                await ctx.send(
                    _("There's an issue accessing the NHL API at the moment. Try again later.")
                )
                log.exception("Error accessing NHL API")
                return
            for game in game_list:
                if game.game_state == "Postponed":
                    continue
                if (game.game_start - datetime.now(timezone.utc)) > timedelta(days=7):
                    continue
                await self.create_gdt(guild, game)
        msg = _("Game Day threads for {team} setup in {channel}").format(
            team=team, channel=channel.mention
        )
        await ctx.send(msg)

    #######################################################################
    # GDT logic                                                           #
    #######################################################################

    async def check_new_gdt(self) -> None:
        game_list = await self.api.get_games()  # Do this once so we don't spam the api
        for guilds in await self.config.all_guilds():
            guild = self.bot.get_guild(guilds)
            if guild is None:
                continue
            if not await self.config.guild(guild).create_threads():
                continue
            if guild.me.is_timed_out():
                continue
            team = await self.config.guild(guild).gdt_team()
            if team != "all":
                next_games = await self.api.get_games(team, datetime.now())
                next_game = None
                if next_games != []:
                    next_game = next_games[0]
                if next_game is None:
                    continue
                if (next_game.game_start - datetime.now(timezone.utc)) > timedelta(days=7):
                    continue
                cur_channel = None
                cur_channels = await self.config.guild(guild).gdt_chans()
                if cur_channels and str(next_game.game_id) in cur_channels:
                    chan_id = cur_channels[str(next_game.game_id)]
                    cur_channel = guild.get_thread(chan_id)
                    if not cur_channel:
                        try:
                            cur_channel = await guild.fetch_channel(chan_id)
                        except Exception:
                            cur_channel = None
                            await self.config.guild(guild).gdt_chans.clear()
                            # clear the config data so that this always contains at most
                            # 1 game day thread when only one team is specified
                            # fetch_channel is used as a backup incase the thread
                            # becomes archived and bot restarts and needs its reference
                if cur_channel is None:
                    await self.delete_gdt(guild)
                    await self.create_gdt(guild)

            else:
                await self.delete_gdt(guild)
                for game in game_list:
                    if game.game_state == "Postponed":
                        continue
                    if (game.game_start - datetime.now(timezone.utc)) > timedelta(days=7):
                        continue
                    await self.create_gdt(guild, game)

    async def create_gdt(self, guild: discord.Guild, game_data: Optional[Game] = None) -> None:
        """
        Creates a game day channel for the given game object
        if no game object is passed it looks for the set team for the guild
        returns None if not setup
        """
        channel_id = await self.config.guild(guild).gdt_channel()
        if not channel_id:
            log.debug("Not channel ID")
            return
        channel = guild.get_channel(channel_id)
        if channel is None:
            # Return none if there's no category to create the channel
            log.debug("Not channel")
            return
        if guild.me.is_timed_out():
            return
        if not channel.permissions_for(guild.me).create_public_threads:
            log.info("Cannot create new GDT in %r due to too many missing permissions.", guild)
            return
        # if len(category.channels) >= 50:
        #     log.info(
        #         f"Cannot create new GDC in {repr(guild)} due to too many channels in category."
        #     )
        #     return
        # may be relevant later not sure

        if game_data is None:
            team = await self.config.guild(guild).gdt_team()

            next_games = await self.api.get_games_list(team, datetime.now())
            if next_games != []:
                next_game = next_games[0]
                if next_game is None:
                    return
                if (next_game.game_start - datetime.now(timezone.utc)) > timedelta(days=7):
                    return
            else:
                # Return if no more games are playing for this team
                log.debug("No games playing")
                return
        else:
            team = game_data.home_team
            next_game = game_data

        time_string = f"<t:{next_game.timestamp}:F>"
        gdt_role_id = await self.config.guild(guild).gdt_role()
        role_mention = ""
        home_role = get_team_role(guild, next_game.home_team)
        away_role = get_team_role(guild, next_game.away_team)
        home_role_mention = next_game.home_team
        away_role_mention = next_game.away_team
        allowed_roles = []
        if home_role:
            home_role_mention = home_role.mention
        if away_role:
            away_role_mention = away_role.mention

        if gdt_role_id == "team":
            if away_role:
                allowed_roles.append(away_role)
            if home_role:
                allowed_roles.append(home_role)

        else:
            gdt_role = guild.get_role(gdt_role_id)
            if gdt_role is not None:
                allowed_roles.append(gdt_role)
                role_mention = gdt_role.mention

        game_msg = (
            f"{away_role_mention} {next_game.away_emoji} @ "
            f"{home_role_mention} {next_game.home_emoji} {time_string}"
        )

        chn_name = get_chn_name(next_game)
        em = await next_game.game_state_embed()
        game_text = await next_game.game_state_text()
        am = discord.AllowedMentions(roles=allowed_roles)
        new_chn = None

        if isinstance(channel, discord.ForumChannel):
            if role_mention:
                game_msg = f"{role_mention}\n{game_msg}"
            tags = []
            for tag in channel.available_tags:
                if next_game.away_team in tag.name:
                    tags.append(tag)
                if next_game.home_team in tag.name:
                    tags.append(tag)
            if not tags and channel.permissions_for(guild.me).manage_channels:
                if not any([next_game.home_team in t.name for t in tags]):
                    try:
                        tags.append(await channel.create_tag(name=next_game.home_team))
                    except Exception:
                        log.exception("Error creating tag for %s", next_game.home_team)
                        pass
                if not any([next_game.away_team in t.name for t in tags]):
                    try:
                        tags.append(await channel.create_tag(name=next_game.away_team))
                    except Exception:
                        log.exception("Error creating tag for %s", next_game.away_team)
                        pass
            try:
                if channel.permissions_for(guild.me).embed_links:
                    thread_with_message = await channel.create_thread(
                        name=chn_name,
                        content=game_msg,
                        embed=em,
                        allowed_mentions=am,
                        applied_tags=tags,
                    )
                else:
                    thread_with_message = await channel.create_thread(
                        name=chn_name,
                        content=f"{game_msg}\n{game_text}",
                        allowed_mentions=am,
                        applied_tags=tags,
                    )
                new_chn = thread_with_message[0]
            except discord.Forbidden:
                log.error("Error creating thread in %r", guild)
            except Exception:
                log.exception("Error creating thread in %r", guild)

        elif isinstance(channel, discord.TextChannel):
            try:
                if channel.permissions_for(guild.me).embed_links:
                    preview_msg = await channel.send(game_msg, embed=em)
                else:
                    preview_msg = await channel.send(f"{game_msg}\n{game_text}")
                new_chn = await channel.create_thread(name=chn_name, message=preview_msg)
                if role_mention:
                    await new_chn.send(role_mention, allowed_mentions=am)
            except discord.Forbidden:
                log.error("Error creating thread in %r", guild)
                return
            except Exception:
                log.exception("Error creating thread in %r", guild)
                return
        if new_chn is None:
            return

        async with self.config.guild(guild).gdt_chans() as current_gdt:
            current_gdt[str(next_game.game_id)] = new_chn.id
        # current_gdc.append(new_chn.id)
        # await config.guild(guild).create_channels.set(True)
        update_gdt = await self.config.guild(guild).update_gdt()
        await self.config.channel(new_chn).team.set([team])
        await self.config.channel(new_chn).guild_id.set(guild.id)
        await self.config.channel(new_chn).parent.set(channel.id)
        await self.config.channel(new_chn).update.set(update_gdt)
        gdt_state_updates = await self.config.guild(guild).gdt_state_updates()
        await self.config.channel(new_chn).game_states.set(gdt_state_updates)
        gdt_countdown = await self.config.guild(guild).gdt_countdown()
        await self.config.channel(new_chn).countdown.set(gdt_countdown)

        # Set default notification settings on the newly created channel
        start_roles = await self.config.guild(guild).default_start_roles()
        await self.config.channel(new_chn).game_start_roles.set(start_roles)
        state_roles = await self.config.guild(guild).default_state_roles()
        await self.config.channel(new_chn).game_state_roles.set(state_roles)
        goal_roles = await self.config.guild(guild).default_goal_roles()
        await self.config.channel(new_chn).game_goal_roles.set(goal_roles)
        # Gets the timezone to use for game day channel topic
        # timestamp = datetime.strptime(next_game.game_start, "%Y-%m-%dT%H:%M:%SZ")
        # guild_team = await config.guild(guild).gdc_team()

    async def delete_gdt(self, guild: discord.Guild) -> None:
        """
        Rather than delete the threads we will now purge our local data only
        since it's no longer necessary to keep and threads will be automatically
        archived
        """
        channels = await self.config.guild(guild).gdt_chans()
        for channel in channels.values():
            await self.config.channel_from_id(channel).clear()
        await self.config.guild(guild).gdt_chans.clear()
