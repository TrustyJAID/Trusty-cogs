import logging
from datetime import datetime
from typing import Optional

import discord
from redbot.core import commands
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import humanize_list
from redbot.core.utils.menus import start_adding_reactions

from .abc import MixinMeta
from .constants import TEAMS
from .game import Game
from .helper import HockeyStates, HockeyTeams, utc_to_local

log = logging.getLogger("red.trusty-cogs.Hockey")

_ = Translator("Hockey", __file__)


class GameDayChannels(MixinMeta):
    """
    All the commands grouped under `[p]gdc`
    """

    #######################################################################
    # GDC Commands                                                        #
    #######################################################################

    @commands.group()
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
        async with ctx.typing():
            guild = ctx.message.guild
            create_channels = await self.config.guild(guild).create_channels()
            if create_channels is None:
                return
            team = await self.config.guild(guild).gdc_team()
            if team is None:
                team = "None"
            channels = await self.config.guild(guild).gdc()
            category = guild.get_channel(await self.config.guild(guild).category())
            delete_gdc = await self.config.guild(guild).delete_gdc()
            game_states = await self.config.guild(guild).gdc_state_updates()
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
                    "Current Channels: {created_channels}\nDefault Game State: {game_states}\n```"
                ).format(
                    guild=guild.name,
                    create_channels=create_channels,
                    delete_gdc=delete_gdc,
                    team=team,
                    created_channels=created_channels,
                    game_states=humanize_list(game_states),
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
                await ctx.send(embed=em)

    @gdc.command(name="delete")
    async def gdc_delete(self, ctx: commands.Context) -> None:
        """
        Delete all current game day channels for the server
        """
        await self.delete_gdc(ctx.guild)
        await ctx.send(_("Game day channels deleted."))

    @gdc.command(name="defaultstate")
    async def gdc_default_game_state(self, ctx: commands.Context, *state: HockeyStates) -> None:
        """
        Set the default game state updates for Game Day Channels.

        `<state>` must be any combination of `preview`, `live`, `final`, and `goal`.

        `preview` updates are the pre-game notifications 60, 30, and 10 minutes before the game starts.
        `live` are the period start notifications.
        `final` is the final game update including 3 stars.
        `goal` is all the goal updates.
        """
        await self.config.guild(ctx.guild).gdc_state_updates.set(list(set(state)))
        if state:
            await ctx.send(
                _("GDC game updates set to {states}").format(
                    states=humanize_list(list(set(state)))
                )
            )
        else:
            await ctx.send(_("GDC game updates not set"))

    @gdc.command(name="create")
    async def gdc_create(self, ctx: commands.Context) -> None:
        """
        Creates the next gdc for the server
        """
        if not await self.config.guild(ctx.guild).gdc_team():
            return await ctx.send(_("No team was setup for game day channels in this server."))
        if await self.config.guild(ctx.guild).create_channels():
            await self.create_gdc(ctx.guild)
        else:
            return await ctx.send(
                _("You need to first toggle channel creation with `{prefix}gdc toggle`.").format(
                    prefix=ctx.clean_prefix
                )
            )
        await ctx.send(_("Game day channels created."))

    @gdc.command(name="toggle")
    async def gdc_toggle(self, ctx: commands.Context) -> None:
        """
        Toggles the game day channel creation on this server
        """
        guild = ctx.message.guild
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
        guild = ctx.message.guild

        cur_setting = await self.config.guild(guild).delete_gdc()
        verb = _("won't") if cur_setting else _("will")
        msg = _(
            "Game day channels {verb} be deleted on this server.\n"
            "Note, this may not happen until the next set of games."
        ).format(verb=verb)
        await self.config.guild(guild).delete_gdc.set(not cur_setting)
        await ctx.send(msg)

    @gdc.command(name="test")
    @commands.is_owner()
    async def test_gdc(self, ctx: commands.Context) -> None:
        """
        Test checking for new game day channels
        """
        await self.check_new_gdc()
        await ctx.tick()

    @gdc.command(name="setup")
    @commands.guild_only()
    async def gdc_setup(
        self,
        ctx: commands.Context,
        team: HockeyTeams,
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
        guild = ctx.message.guild
        if team is None:
            return await ctx.send(_("You must provide a valid current team."))
        if category is None and ctx.channel.category is not None:
            category = guild.get_channel(ctx.channel.category_id)
        else:
            return await ctx.send(
                _("You must specify a channel category for game day channels to be created under.")
            )
        if not category.permissions_for(guild.me).manage_channels:
            await ctx.send(_("I don't have manage channels permission!"))
            return
        await self.config.guild(guild).category.set(category.id)
        await self.config.guild(guild).gdc_team.set(team)
        await self.config.guild(guild).delete_gdc.set(delete_gdc)
        await self.config.guild(guild).create_channels.set(True)
        if team.lower() != "all":
            await self.create_gdc(guild)
        else:
            game_list = await Game.get_games(session=self.session)
            for game in game_list:
                await self.create_gdc(guild, game)
        await ctx.send(_("Game Day Channels for ") + team + _(" setup in ") + category.name)

    #######################################################################
    # GDC logic                                                           #
    #######################################################################

    async def get_chn_name(self, game: Game) -> str:
        """
        Creates game day channel name
        """
        timestamp = utc_to_local(game.game_start)
        chn_name = "{}-vs-{}-{}-{}-{}".format(
            game.home_abr, game.away_abr, timestamp.year, timestamp.month, timestamp.day
        )
        return chn_name.lower()

    async def check_new_gdc(self) -> None:
        game_list = await Game.get_games(
            session=self.session
        )  # Do this once so we don't spam the api
        for guilds in await self.config.all_guilds():
            guild = self.bot.get_guild(guilds)
            if guild is None:
                continue
            if not await self.config.guild(guild).create_channels():
                continue
            team = await self.config.guild(guild).gdc_team()
            if team != "all":
                next_games = await Game.get_games_list(team, datetime.now(), session=self.session)
                next_game = None
                if next_games != []:
                    next_game = await Game.from_url(next_games[0]["link"], session=self.session)
                if next_game is None:
                    continue
                chn_name = await self.get_chn_name(next_game)
                try:
                    cur_channels = await self.config.guild(guild).gdc()
                    if cur_channels:
                        cur_channel = self.bot.get_channel(cur_channels[0])
                    else:
                        cur_channel = None
                        # this is dumb but eh
                except Exception:
                    log.error("Error checking new GDC", exc_info=True)
                    cur_channel = None
                if cur_channel is None:
                    await self.create_gdc(guild)
                elif cur_channel.name != chn_name.lower():
                    await self.delete_gdc(guild)
                    await self.create_gdc(guild)

            else:
                await self.delete_gdc(guild)
                for game in game_list:
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
            log.info(
                f"Cannot create new GDC in {repr(guild)} due to too many missing permissions."
            )
            return
        if len(category.channels) >= 50:
            log.info(
                f"Cannot create new GDC in {repr(guild)} due to too many channels in category."
            )
            return
        if game_data is None:
            team = await self.config.guild(guild).gdc_team()

            next_games = await Game.get_games_list(team, datetime.now(), session=self.session)
            if next_games != []:
                next_game = await Game.from_url(next_games[0]["link"], session=self.session)
                if next_game is None:
                    return
            else:
                # Return if no more games are playing for this team
                return
        else:
            team = game_data.home_team
            next_game = game_data

        chn_name = await self.get_chn_name(next_game)
        try:
            new_chn = await guild.create_text_channel(chn_name, category=category)
        except discord.Forbidden:
            log.error(f"Error creating channel in {repr(guild)}")
        except Exception:
            log.exception(f"Error creating channels in {repr(guild)}")
            return
        async with self.config.guild(guild).gdc() as current_gdc:
            current_gdc.append(new_chn.id)
        # await config.guild(guild).create_channels.set(True)
        await self.config.channel(new_chn).team.set([team])
        await self.config.channel(new_chn).guild_id.set(guild.id)
        delete_gdc = await self.config.guild(guild).delete_gdc()
        await self.config.channel(new_chn).to_delete.set(delete_gdc)
        gdc_state_updates = await self.config.guild(guild).gdc_state_updates()
        await self.config.channel(new_chn).game_states.set(gdc_state_updates)
        # Gets the timezone to use for game day channel topic
        # timestamp = datetime.strptime(next_game.game_start, "%Y-%m-%dT%H:%M:%SZ")
        # guild_team = await config.guild(guild).gdc_team()
        channel_team = team if team != "all" else next_game.home_team
        timezone = (
            await self.config.guild(guild).timezone() or TEAMS[channel_team]["timezone"]
            if channel_team in TEAMS
            else TEAMS[next_game.away_team]["timezone"]
        )
        time_string = utc_to_local(next_game.game_start, timezone).strftime(
            "%A %B %d, %Y at %I:%M %p %Z"
        )

        game_msg = (
            f"{next_game.away_team} {next_game.away_emoji} @ "
            f"{next_game.home_team} {next_game.home_emoji} {time_string}"
        )
        try:
            await new_chn.edit(topic=game_msg)
        except discord.errors.Forbidden:
            log.error("Error editing the channel topic")
        if new_chn.permissions_for(guild.me).embed_links:
            em = await next_game.game_state_embed()
            try:
                preview_msg = await new_chn.send(embed=em)
            except Exception:
                log.error("Error posting game preview in GDC channel.")
        else:
            try:
                preview_msg = await new_chn.send(await next_game.game_state_text())
            except Exception:
                log.error("Error posting game preview in GDC channel.")
                return

        # Create new pickems object for the game
        try:
            await self.create_pickem_object(guild, preview_msg, new_chn, next_game)
        except Exception:
            log.error("Error creating pickems object in GDC channel.")

        if new_chn.permissions_for(guild.me).manage_messages:
            await preview_msg.pin()
        if new_chn.permissions_for(guild.me).add_reactions:
            start_adding_reactions(
                preview_msg, [next_game.away_emoji[2:-1], next_game.home_emoji[2:-1]]
            )

    async def delete_gdc(self, guild: discord.Guild) -> None:
        """
        Deletes all game day channels in a given guild
        """
        channels = await self.config.guild(guild).gdc()
        if channels is None:
            channels = []
        for channel in channels:
            chn = guild.get_channel(channel)
            if chn is None:
                await self.config.channel_from_id(channel).clear()
                continue
            if not await self.config.channel(chn).to_delete():
                continue
            try:
                await self.config.channel(chn).clear()
                await chn.delete()
            except discord.errors.Forbidden:
                log.error(f"Cannot delete GDC channels in {guild.id} due to permissions issue.")
            except Exception:
                log.exception(f"Cannot delete GDC channels in {guild.id}")
        await self.config.guild(guild).gdc.clear()
