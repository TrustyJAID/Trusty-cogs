from datetime import datetime, timedelta, timezone
from typing import Optional

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


class GameDayChannels(HockeyMixin):
    """
    All the commands grouped under `[p]gdc`
    """

    #######################################################################
    # GDC Commands                                                        #
    #######################################################################

    @hockey_commands.group(with_app_command=False)
    @commands.mod_or_permissions(manage_channels=True)
    @commands.guild_only()
    async def gdc(self, ctx: commands.Context) -> None:
        """
        Game Day Channel setup for the server

        You can setup only a single team or all teams for the server
        Game day channels are deleted and created on the day after the game is played
        usually around 9AM PST
        """

    @gdc.command(name="settings")
    async def gdc_settings(self, ctx: commands.Context) -> None:
        """
        Show the current Game Day Channel Settings
        """
        if not ctx.guild:
            await ctx.send(_("This command can only work inside a server."))
            return
        async with ctx.typing():
            guild = ctx.message.guild
            create_channels = await self.config.guild(guild).create_channels()
            if create_channels is None:
                return
            team = await self.config.guild(guild).gdc_team()
            if team is None:
                team = "None"
            channels = (await self.config.guild(guild).gdc_chans()).values()
            category = guild.get_channel(await self.config.guild(guild).category())
            delete_gdc = await self.config.guild(guild).delete_gdc()
            game_states = await self.config.guild(guild).gdc_state_updates()
            countdown = await self.config.guild(guild).gdc_countdown()
            if category is not None:
                category = category.name
            if channels is not None:
                created_channels = ""
                for channel in channels:
                    chn = guild.get_channel(channel)
                    if chn is not None:
                        created_channels += chn.mention
                    else:
                        created_channels += "<#{}>\n".format(channel)
                if len(channels) == 0:
                    created_channels = "None"
            else:
                created_channels = "None"
            if not ctx.channel.permissions_for(guild.me).embed_links:
                msg = _(
                    "```GDC settings for {guild}\nCreate Game Day Channels: {create_channels}"
                    "\nDelete Game Day Channels: {delete_gdc}\nTeam: {team}\n"
                    "Current Threads: {created_threads}\nDefault Game State: {game_states}\n"
                    "Game Start Countdown: {countdown}\n```"
                ).format(
                    guild=guild.name,
                    create_channels=create_channels,
                    delete_gdc=delete_gdc,
                    team=team,
                    created_channels=created_channels,
                    game_states=humanize_list(game_states),
                    countdown=countdown,
                )

                await ctx.send(msg)
            if ctx.channel.permissions_for(guild.me).embed_links:
                em = discord.Embed(title=_("GDC settings for ") + guild.name)
                em.colour = await ctx.embed_colour()
                em.add_field(name=_("Create Game Day Channels"), value=str(create_channels))
                em.add_field(name=_("Delete Game Day Channels"), value=str(delete_gdc))
                em.add_field(name=_("Team"), value=str(team))
                em.add_field(name=_("Current Channels"), value=created_channels[:1024])
                if not game_states:
                    game_states = ["None"]
                em.add_field(name=_("Default Game States"), value=humanize_list(game_states))
                em.add_field(name=_("Game Start Countdown"), value=str(countdown))
                await ctx.send(embed=em)

    @gdc.command(name="delete")
    async def gdc_delete(self, ctx: commands.Context) -> None:
        """
        Delete all current game day channels for the server
        """
        if not ctx.guild:
            await ctx.send(_("This command can only work inside a server."))
            return
        await self.delete_gdc(ctx.guild)
        await ctx.send(_("Game day channels deleted."))

    @gdc.command(name="defaultstate")
    async def gdc_default_game_state(self, ctx: commands.Context, state: StateFinder) -> None:
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
            msg = _("GDC game updates not set")
            await ctx.send(msg)

    @gdc.command(name="countdown")
    @commands.mod_or_permissions(manage_channels=True)
    async def set_gdc_countdown_updates(
        self,
        ctx: commands.Context,
    ) -> None:
        """
        Toggle 60, 30, and 10 minute countdown updates in game day channels
        """
        if not ctx.guild:
            await ctx.send(_("This command can only work inside a server."))
            return
        current = await self.config.guild(ctx.guild).gdc_countdown()
        await self.config.guild(ctx.guild).gdc_countdown.set(not current)
        if current:
            await ctx.send(
                _(
                    "60, 30, and 10 minute countdown messages have been disabled in future game day channels."
                )
            )
        else:
            await ctx.send(
                _(
                    "60, 30, and 10 minute countdown messages have been enabled in future game day channels."
                )
            )

    @gdc.command(name="create")
    async def gdc_create(self, ctx: commands.Context) -> None:
        """
        Creates the next gdc for the server
        """
        if not ctx.guild:
            await ctx.send(_("This command can only work inside a server."))
            return
        if not await self.config.guild(ctx.guild).gdc_team():
            await ctx.send(_("No team was setup for game day channels in this server."))
            return
        if await self.config.guild(ctx.guild).create_channels():
            try:
                await self.create_gdc(ctx.guild)
            except aiohttp.ClientConnectorError:
                await ctx.send(
                    _("There's an issue accessing the NHL API at the moment. Try again later.")
                )
                log.exception("Error accessing NHL API")
                return
        else:
            await ctx.send(
                _("You need to first toggle channel creation with `{prefix}gdc toggle`.").format(
                    prefix=ctx.clean_prefix
                )
            )
            return
        await ctx.send(_("Game day channels created."))

    @gdc.command(name="toggle")
    async def gdc_toggle(self, ctx: commands.Context) -> None:
        """
        Toggles the game day channel creation on this server
        """
        if not ctx.guild:
            await ctx.send(_("This command can only work inside a server."))
            return
        guild = ctx.message.guild
        if await self.config.guild(guild).create_threads():
            await ctx.send(
                _(
                    "You cannot have both game day channels and game day threads in the same server. "
                    "Use `{prefix}{command}` first to disable game day threads then try again."
                ).format(prefix=ctx.clean_prefix, command=self.gdt_toggle.qualified_name)
            )
            return
        cur_setting = not await self.config.guild(guild).create_channels()
        verb = _("will") if cur_setting else _("won't")
        msg = _("Game day channels ") + verb + _(" be created on this server.")
        await self.config.guild(guild).create_channels.set(cur_setting)
        await ctx.send(msg)

    @gdc.command(name="category")
    async def gdc_category(self, ctx: commands.Context, category: discord.CategoryChannel) -> None:
        """
        Change the category for channel creation. Channel is case sensitive.
        """
        if not ctx.guild:
            await ctx.send(_("This command can only work inside a server."))
            return
        guild = ctx.message.guild

        # cur_setting = await self.config.guild(guild).category()

        msg = _("Game day channels will be created in ")
        await self.config.guild(guild).category.set(category.id)
        await ctx.send(msg + category.name)

    @gdc.command(name="autodelete")
    async def gdc_autodelete(self, ctx: commands.Context) -> None:
        """
        Toggle's auto deletion of game day channels.
        """
        if not ctx.guild:
            await ctx.send(_("This command can only work inside a server."))
            return
        guild = ctx.message.guild

        cur_setting = await self.config.guild(guild).delete_gdc()
        verb = _("won't") if cur_setting else _("will")
        msg = _(
            "Game day channels {verb} be deleted on this server.\n"
            "Note, this may not happen until the next set of games."
        ).format(verb=verb)
        await self.config.guild(guild).delete_gdc.set(not cur_setting)
        await ctx.send(msg)

    @gdc.command(name="test", with_app_command=False)
    @commands.is_owner()
    async def test_gdc(self, ctx: commands.Context) -> None:
        """
        Test checking for new game day channels
        """
        if not ctx.guild:
            await ctx.send(_("This command can only work inside a server."))
            return
        await self.check_new_gdc()
        await ctx.tick()

    @gdc.command(name="setup")
    @commands.guild_only()
    async def gdc_setup(
        self,
        ctx: commands.Context,
        team: TeamFinder,
        category: discord.CategoryChannel = None,
        delete_gdc: bool = True,
    ) -> None:
        """
        Setup game day channels for a single team or all teams

        Required parameters:
        `<team>` must use quotes if a space is in the name will search for partial team name

        Optional Parameters:
        `[category]` You must use the category ID or use this command in a channel already in the
        desired category

        `[delete_gdc=True]` will tell the bot whether or not to delete game day channels automatically
        must be either `True` or `False`. Defaults to `True` if not provided.
        """
        if not ctx.guild:
            await ctx.send(_("This command can only work inside a server."))
            return
        guild = ctx.message.guild
        if await self.config.guild(guild).create_threads():
            await ctx.send(
                _(
                    "You cannot have both game day channels and game day threads in the same server. "
                    "Use `{prefix}{command}` first to disable game day threads then try again."
                ).format(prefix=ctx.clean_prefix, command=self.gdt_toggle.qualified_name)
            )
            return
        if team is None:
            await ctx.send(_("You must provide a valid current team."))
            return
        if category is None and ctx.channel.category is not None:
            category = guild.get_channel(ctx.channel.category_id)
        if category is None:
            await ctx.send(
                _("You must specify a channel category for game day channels to be created under.")
            )
            return
        if not category.permissions_for(guild.me).manage_channels:
            await ctx.send(_("I don't have manage channels permission!"))
            return
        await self.clear_gdc(guild)
        await self.config.guild(guild).category.set(category.id)
        await self.config.guild(guild).gdc_team.set(team)
        await self.config.guild(guild).delete_gdc.set(delete_gdc)
        await self.config.guild(guild).create_channels.set(True)
        if team.lower() != "all":
            try:
                await self.create_gdc(guild)
            except aiohttp.ClientConnectorError:
                await ctx.send(
                    _("There's an issue accessing the NHL API at the moment. Try again later.")
                )
                log.exception("Error accessing NHL API")
                return
        else:
            game_list = await self.api.get_games()
            for game in game_list:
                if (game.game_start - datetime.now(timezone.utc)) > timedelta(days=7):
                    continue
                try:
                    await self.create_gdc(guild, game)
                except aiohttp.ClientConnectorError:
                    await ctx.send(
                        _("There's an issue accessing the NHL API at the moment. Try again later.")
                    )
                    log.exception("Error accessing NHL API")
                    return
        await ctx.send(_("Game Day Channels for ") + team + _(" setup in ") + category.name)

    #######################################################################
    # GDC logic                                                           #
    #######################################################################

    async def check_new_gdc(self) -> None:
        game_list = await self.api.get_games()  # Do this once so we don't spam the api
        for guilds in await self.config.all_guilds():
            guild = self.bot.get_guild(guilds)
            if guild is None:
                continue
            if not await self.config.guild(guild).create_channels():
                continue
            if guild.me.is_timed_out():
                continue
            team = await self.config.guild(guild).gdc_team()
            if team != "all":
                next_games = await self.api.get_games(team, datetime.now())
                next_game = None
                if next_games != []:
                    next_game = next_games[0]
                if next_game is None:
                    continue
                if (next_game.game_start - datetime.now(timezone.utc)) > timedelta(days=7):
                    continue
                cur_channels = await self.config.guild(guild).gdc_chans()
                cur_channel = guild.get_channel(cur_channels.get(str(next_game.game_id)))
                if cur_channel is None:
                    await self.delete_gdc(guild)
                    await self.create_gdc(guild)

            else:
                await self.delete_gdc(guild)
                for game in game_list:
                    if game.game_state == "Postponed":
                        continue
                    if (game.game_start - datetime.now(timezone.utc)) > timedelta(days=7):
                        continue
                    await self.create_gdc(guild, game)

    async def create_gdc(self, guild: discord.Guild, game_data: Optional[Game] = None) -> None:
        """
        Creates a game day channel for the given game object
        if no game object is passed it looks for the set team for the guild
        returns None if not setup
        """
        category_id = await self.config.guild(guild).category()
        if not category_id:
            return
        category = self.bot.get_channel(category_id)
        if category is None:
            # Return none if there's no category to create the channel
            return
        if not category.permissions_for(guild.me).manage_channels:
            log.info("Cannot create new GDC in %r due to too many missing permissions.", guild)
            return
        if len(category.channels) >= 50:
            log.info("Cannot create new GDC in %r due to too many channels in category.", guild)
            return
        if game_data is None:
            team = await self.config.guild(guild).gdc_team()

            next_games = await self.api.get_games(team, datetime.now())
            if next_games != []:
                next_game = next_games[0]
                if next_game is None:
                    return
                if (next_game.game_start - datetime.now(timezone.utc)) > timedelta(days=7):
                    return
            else:
                # Return if no more games are playing for this team
                return
        else:
            team = game_data.home_team
            next_game = game_data

        chn_name = get_chn_name(next_game)
        try:
            new_chn = await guild.create_text_channel(chn_name, category=category)
        except discord.Forbidden:
            log.error("Error creating channel in %r", guild)
            return
        except Exception:
            log.exception(f"Error creating channels in {repr(guild)}")
            return
        async with self.config.guild(guild).gdc_chans() as current_gdc:
            current_gdc[str(next_game.game_id)] = new_chn.id
        # await config.guild(guild).create_channels.set(True)
        await self.config.channel(new_chn).team.set([team])
        await self.config.channel(new_chn).guild_id.set(guild.id)
        delete_gdc = await self.config.guild(guild).delete_gdc()
        await self.config.channel(new_chn).to_delete.set(delete_gdc)
        gdc_state_updates = await self.config.guild(guild).gdc_state_updates()
        await self.config.channel(new_chn).game_states.set(gdc_state_updates)
        gdc_countdown = await self.config.guild(guild).gdc_countdown()
        await self.config.channel(new_chn).countdown.set(gdc_countdown)

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
        time_string = f"<t:{next_game.timestamp}:F>"
        home_role = get_team_role(guild, next_game.home_team)
        away_role = get_team_role(guild, next_game.away_team)
        home_role_mention = next_game.home_team
        away_role_mention = next_game.away_team
        if home_role:
            home_role_mention = home_role.mention
        if away_role:
            away_role_mention = away_role.mention

        game_msg = (
            f"{away_role_mention} {next_game.away_emoji} @ "
            f"{home_role_mention} {next_game.home_emoji} {time_string}"
        )
        try:
            await new_chn.edit(topic=game_msg)
        except discord.errors.Forbidden:
            log.error("Error editing the channel topic")
        if new_chn.permissions_for(guild.me).embed_links:
            em = await next_game.game_state_embed()
            try:
                preview_msg = await new_chn.send(game_msg, embed=em)
            except Exception:
                log.error("Error posting game preview in GDC channel.")
        else:
            try:
                game_text = await next_game.game_state_text()
                text_message = f"{game_msg}\n{game_text}"
                preview_msg = await new_chn.send(text_message)
            except Exception:
                log.error("Error posting game preview in GDC channel.")
                return

        if new_chn.permissions_for(guild.me).manage_messages:
            await preview_msg.pin()

    async def clear_gdc(self, guild: discord.Guild) -> None:
        """
        Rather than delete the threads we will now purge our local data only
        since it's no longer necessary to keep and threads will be automatically
        archived
        """
        channels = await self.config.guild(guild).gdc_chans()
        for channel in channels.values():
            await self.config.channel_from_id(channel).clear()
        await self.config.guild(guild).gdc_chans.clear()

    async def delete_gdc(self, guild: discord.Guild) -> None:
        """
        Deletes all game day channels in a given guild
        """
        channels = await self.config.guild(guild).gdc_chans()
        if channels is None:
            channels = {}
        for channel in channels.values():
            if await self.config.channel_from_id(channel).to_delete():
                chn = guild.get_channel(channel)
                if chn is not None:
                    try:
                        await chn.delete()
                    except discord.errors.Forbidden:
                        log.error(
                            "Cannot delete GDC channels in %s due to permissions issue.", guild.id
                        )
                    except Exception:
                        log.exception(f"Cannot delete GDC channels in {guild.id}")
            await self.config.channel_from_id(channel).clear()
        await self.config.guild(guild).gdc_chans.clear()
