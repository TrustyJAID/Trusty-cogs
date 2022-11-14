import logging
from datetime import datetime
from typing import Optional

import discord
from redbot.core import commands
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import humanize_list

from .abc import MixinMeta
from .game import Game
from .helper import StateFinder, TeamFinder, get_chn_name

log = logging.getLogger("red.trusty-cogs.Hockey")

_ = Translator("Hockey", __file__)

hockey_commands = MixinMeta.hockey_commands


class GameDayThreads(MixinMeta):
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

    @gdt.command(name="settings")
    @commands.mod_or_permissions(manage_channels=True)
    async def gdt_settings(self, ctx: commands.Context) -> None:
        """
        Show the current Game Day Thread Settings
        """
        guild = ctx.guild
        create_threads = await self.config.guild(guild).create_threads()
        if create_threads is None:
            msg = _("Game Day Threads are not setup on this server.")
            await ctx.send(msg)
            return
        team = await self.config.guild(guild).gdt_team()
        if team is None:
            team = "None"
        threads = await self.config.guild(guild).gdt()
        channel = guild.get_channel(await self.config.guild(guild).gdt_channel())
        game_states = await self.config.guild(guild).gdt_state_updates()
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
                "Current Threads: {created_threads}\nDefault Game State: {game_states}\n```"
            ).format(
                guild=guild.name,
                create_threads=create_threads,
                gdt_update=update_gdt,
                team=team,
                created_threads=created_threads,
                game_states=humanize_list(game_states),
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
            await ctx.send(embed=em)

    @gdt.command(name="delete")
    @commands.mod_or_permissions(manage_channels=True)
    async def gdt_delete(self, ctx: commands.Context) -> None:
        """
        Delete all current game day threads for the server
        """
        await ctx.defer()
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
        cur_state = await self.config.guild(ctx.guild).gdt_state_updates()
        if state.value in cur_state:
            cur_state.remove(state.value)
        else:
            cur_state.append(state.value)
        await self.config.guild(ctx.guild).gdt_state_updates.set(cur_state)
        if cur_state:
            msg = _("GDT game updates set to {states}").format(
                states=humanize_list(list(set(cur_state)))
            )
            await ctx.send(msg)
        else:
            msg = _("GDT game updates not set")
            await ctx.send(msg)

    @gdt.command(name="updates")
    @commands.mod_or_permissions(manage_channels=True)
    async def gdt_update_start(self, ctx: commands.Context, update_start: bool) -> None:
        """
        Set whether or not the starting thread message will update as the game progresses.

        `<update_start>` either true or false.
        """
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
        await ctx.defer()
        if not await self.config.guild(ctx.guild).gdt_team():
            msg = _("No team was setup for game day threads in this server.")
            await ctx.send(msg)
        if await self.config.guild(ctx.guild).create_threads():
            await self.create_gdt(ctx.guild)
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
        guild = ctx.guild
        if await self.config.guild(guild).create_channels():
            msg = _(
                "You cannot have both game day channels and game day threads in the same server. "
                "Use `{prefix}gdc toggle` first to disable game day channels then try again."
            ).format(prefix=ctx.clean_prefix)
            await ctx.send(msg)
            return
        cur_setting = not await self.config.guild(guild).create_threads()
        verb = _("will") if cur_setting else _("won't")
        msg = _("Game day threads ") + verb + _(" be created on this server.")
        await self.config.guild(guild).create_threads.set(cur_setting)
        await ctx.send(msg)

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
        await self.check_new_gdt()
        await ctx.tick()

    @gdt.command(name="setup")
    @commands.guild_only()
    @commands.mod_or_permissions(manage_channels=True)
    async def gdt_setup(
        self,
        ctx: commands.Context,
        team: TeamFinder,
        channel: Optional[discord.TextChannel] = None,
    ) -> None:
        """
        Setup game day channels for a single team or all teams

        Required parameters:
        `<team>` must use quotes if a space is in the name will search for partial team name

        Optional Parameters:
        `[channel]` The channel that game day threads will be created in. If not provided will default
        to the current text channel.
        """
        await ctx.defer()
        guild = ctx.guild
        if await self.config.guild(guild).create_channels():
            msg = _(
                "You cannot have both game day channels and game day threads in the same server. "
                "Use `{prefix}gdc toggle` first to disable game day channels then try again."
            ).format(prefix=ctx.clean_prefix)
            await ctx.send(msg)
            return
        if team is None:
            msg = _("You must provide a valid current team.")
            await ctx.send(msg)
            return
        if channel is None:
            channel = ctx.channel
        if not channel.permissions_for(guild.me).create_public_threads:
            msg = _("I don't have permission to create public threads in this channel.")
            await ctx.send(msg)
            return
        await self.config.guild(guild).gdt_channel.set(channel.id)
        await self.config.guild(guild).gdt_team.set(team)
        await self.config.guild(guild).create_threads.set(True)
        if team.lower() != "all":
            await self.create_gdt(guild)
        else:
            game_list = await Game.get_games(session=self.session)
            for game in game_list:
                if game.game_state == "Postponed":
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
        game_list = await Game.get_games(
            session=self.session
        )  # Do this once so we don't spam the api
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
                next_games = await Game.get_games_list(team, datetime.now(), session=self.session)
                next_game = None
                if next_games != []:
                    next_game = await Game.from_url(next_games[0]["link"], session=self.session)
                if next_game is None:
                    continue
                chn_name = get_chn_name(next_game)
                try:
                    cur_channels = await self.config.guild(guild).gdt()
                    if cur_channels:
                        cur_channel = guild.get_thread(cur_channels[0])
                        if not cur_channel:
                            try:
                                cur_channel = await guild.fetch_channel(cur_channels[0])
                            except Exception:
                                cur_channel = None
                                await self.config.guild(guild).gdt.clear()
                                # clear the config data so that this always contains at most
                                # 1 game day thread when only one team is specified
                                # fetch_channel is used as a backup incase the thread
                                # becomes archived and bot restarts and needs its refernce
                    else:
                        cur_channel = None
                        # this is dumb but eh
                except Exception:
                    log.error("Error checking new GDT", exc_info=True)
                    cur_channel = None
                if cur_channel is None:
                    await self.create_gdt(guild)
                elif cur_channel.name != chn_name.lower():
                    await self.delete_gdt(guild)
                    await self.create_gdt(guild)

            else:
                await self.delete_gdt(guild)
                for game in game_list:
                    if game.game_state == "Postponed":
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
            log.info(
                f"Cannot create new GDT in {repr(guild)} due to too many missing permissions."
            )
            return
        # if len(category.channels) >= 50:
        #     log.info(
        #         f"Cannot create new GDC in {repr(guild)} due to too many channels in category."
        #     )
        #     return
        # may be relevant later not sure
        if game_data is None:
            team = await self.config.guild(guild).gdt_team()

            next_games = await Game.get_games_list(team, datetime.now(), session=self.session)
            if next_games != []:
                next_game = await Game.from_url(next_games[0]["link"], session=self.session)
                if next_game is None:
                    return
            else:
                # Return if no more games are playing for this team
                log.debug("No games playing")
                return
        else:
            team = game_data.home_team
            next_game = game_data

        time_string = f"<t:{next_game.timestamp}:F>"

        game_msg = (
            f"{next_game.away_team} {next_game.away_emoji} @ "
            f"{next_game.home_team} {next_game.home_emoji} {time_string}"
        )
        if channel.permissions_for(guild.me).embed_links:
            em = await next_game.game_state_embed()
            try:
                preview_msg = await channel.send(game_msg, embed=em)
            except Exception:
                log.error("Error posting game preview in GDT channel.")
                return
        else:
            try:
                preview_msg = await channel.send(
                    game_msg + "\n" + await next_game.game_state_text()
                )
            except Exception:
                log.error("Error posting game preview in GDT channel.")
                return

        chn_name = get_chn_name(next_game)
        try:
            new_chn = await channel.create_thread(name=chn_name, message=preview_msg)
        except discord.Forbidden:
            log.error(f"Error creating channel in {repr(guild)}")
            return
        except Exception:
            log.exception(f"Error creating channels in {repr(guild)}")
            return
        async with self.config.guild(guild).gdt() as current_gdc:
            current_gdc.append(new_chn.id)
        # await config.guild(guild).create_channels.set(True)
        update_gdt = await self.config.guild(guild).update_gdt()
        await self.config.channel(new_chn).team.set([team])
        await self.config.channel(new_chn).guild_id.set(guild.id)
        await self.config.channel(new_chn).parent.set(channel.id)
        await self.config.channel(new_chn).update.set(update_gdt)
        gdt_state_updates = await self.config.guild(guild).gdt_state_updates()
        await self.config.channel(new_chn).game_states.set(gdt_state_updates)
        # Gets the timezone to use for game day channel topic
        # timestamp = datetime.strptime(next_game.game_start, "%Y-%m-%dT%H:%M:%SZ")
        # guild_team = await config.guild(guild).gdc_team()

    async def delete_gdt(self, guild: discord.Guild) -> None:
        """
        Rather than delete the threads we will now purge our local data only
        since it's no longer necessary to keep and threads will be automatically
        archived
        """
        channels = await self.config.guild(guild).gdt()
        if channels is None:
            channels = []
        for channel in channels:
            chn = guild.get_thread(channel)
            if chn is None:
                await self.config.channel_from_id(channel).clear()
                continue
            try:
                await self.config.channel(chn).clear()
            except Exception:
                log.exception(f"Cannot delete GDT threads in {guild.id}")
        await self.config.guild(guild).gdt.clear()
