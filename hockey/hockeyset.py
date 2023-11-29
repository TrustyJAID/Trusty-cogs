import asyncio
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Optional

import aiohttp
import discord
from red_commons.logging import getLogger
from redbot.core import commands
from redbot.core.data_manager import cog_data_path
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import humanize_list

from .abc import HockeyMixin
from .constants import TEAMS
from .helper import StandingsFinder, StateFinder, TeamFinder
from .standings import Conferences, Divisions, Standings

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
        await ctx.defer()
        guild = ctx.guild
        standings_channel = guild.get_channel(await self.config.guild(guild).standings_channel())
        post_standings = _("On") if await self.config.guild(guild).post_standings() else _("Off")
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
                if ctx.channel.permissions_for(guild.me).embed_links:
                    standings_msg = (
                        _("[Standings") + f" {post_standings}]({standings_msg.jump_url})"
                    )
                else:
                    standings_msg = (
                        _("Standings") + f" {post_standings}```{standings_msg.jump_url}"
                    )
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

        notification_settings = _("Game Start: {game_start}\nGoals: {goals}\n").format(
            game_start=await self.config.guild(guild).game_state_notifications(),
            goals=await self.config.guild(guild).goal_notifications(),
        )
        if ctx.channel.permissions_for(guild.me).embed_links:
            em = discord.Embed(title=guild.name + _(" Hockey Settings"))
            em.colour = await self.bot.get_embed_colour(ctx.channel)
            em.description = channels
            em.add_field(name=_("Standings Settings"), value=f"{standings_chn}: {standings_msg}")
            em.add_field(name=_("Notifications"), value=notification_settings)
            await ctx.send(embed=em)
        else:
            msg = _(
                "{guild} Hockey Settings\n {channels}\nNotifications\n{notifications}"
                "\nStandings Settings\n{standings_chn}: {standings}\n"
            ).format(
                guild=guild.name,
                channels=channels,
                notifications=notification_settings,
                standings_chn=standings_chn,
                standings=standings_msg,
            )
            await ctx.send(msg)

    #######################################################################
    # All Hockey setup commands                                           #
    #######################################################################

    @commands.group(name="hockeyslash")
    async def hockey_slash(self, ctx: commands.Context):
        """
        commands for enabling/disabling slash commands
        """
        pass

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
    async def set_team_events(self, ctx: commands.Context, team: TeamFinder):
        """
        Create a scheduled server event for all games in the season for one team.

        This command can take a while to complete.
        """
        start = datetime.now()
        end = start + timedelta(days=350)
        try:
            data = await self.api.get_schedule(
                team, start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")
            )
        except aiohttp.ClientConnectorError:
            await ctx.send(
                _("There's an issue accessing the NHL API at the moment. Try again later.")
            )
            log.exception("Error accessing NHL API")
            return
        number_of_games = str(len(data.get("dates", [])))
        await ctx.send(f"Creating events for {number_of_games} games.")
        images_path = cog_data_path(self) / "teamlogos"
        if not os.path.isdir(images_path):
            os.mkdir(images_path)
        existing_events = {}
        for event in ctx.guild.scheduled_events:
            event_id = re.search(r"\n(\d{6,})", event.description)
            existing_events[event_id.group(1)] = event
        async with ctx.typing():
            for date in data["dates"]:
                for game in date["games"]:
                    start = datetime.strptime(game["gameDate"], "%Y-%m-%dT%H:%M:%SZ").replace(
                        tzinfo=timezone.utc
                    )
                    end = start + timedelta(hours=3)
                    away = game["teams"]["away"]["team"]["name"]
                    home = game["teams"]["home"]["team"]["name"]
                    image_team = away if team == home else home
                    image_file = images_path / f"{image_team}.png"
                    if not os.path.isfile(image_file):
                        async with self.session.get(TEAMS[image_team]["logo"]) as resp:
                            image = await resp.read()
                        with image_file.open("wb") as outfile:
                            outfile.write(image)
                    image = open(image_file, "rb")
                    name = f"{away} @ {home}"
                    broadcasts = humanize_list(
                        [b.get("name", "Unknown") for b in game.get("broadcasts", [])]
                    )
                    description = name
                    if broadcasts:
                        description += f"\nBroadcasts: {broadcasts}"
                    game_id = str(game["gamePk"])
                    description += f"\n\n{game_id}"
                    if game_id in existing_events:
                        try:
                            if existing_events[game_id].start_time != start:
                                await existing_events[game_id].edit(
                                    start_time=start, end_time=end, reason="Start time changed"
                                )
                            if existing_events[game_id].description != description:
                                await existing_events[game_id].edit(
                                    description=description, reason="Description has changed"
                                )
                        except Exception:
                            # I don't care if these don't edit properly
                            pass
                        continue
                    try:
                        await ctx.guild.create_scheduled_event(
                            name=f"{away} @ {home}",
                            description=description,
                            start_time=start,
                            location=game.get("venue", {}).get("name", "Unknown place"),
                            end_time=end,
                            entity_type=discord.EntityType.external,
                            image=image.read(),
                            privacy_level=discord.PrivacyLevel.guild_only,
                        )
                    except Exception:
                        log.exception(
                            "Error creating scheduled event in %s for team %s", ctx.guild.id, team
                        )
                    image.close()
                    await asyncio.sleep(1)
        await ctx.send(f"Finished creating events for {number_of_games} games.")

    @hockey_slash.command(name="global")
    @commands.is_owner()
    async def hockey_global_slash(self, ctx: commands.Context):
        """Toggle this cog to register slash commands"""
        current = await self.config.enable_slash()
        await self.config.enable_slash.set(not current)
        verb = _("enabled") if not current else _("disabled")
        await ctx.send(_("Slash commands are {verb}.").format(verb=verb))
        if not current:
            self.bot.tree.add_command(self.hockey_commands.app_command)
        else:
            self.bot.tree.remove_command("hockey")

    async def check_notification_settings(self, guild: discord.Guild) -> str:
        reply = ""
        mentionable_roles = []
        non_mention_roles = []
        no_role = []
        for team in TEAMS:
            role = discord.utils.get(guild.roles, name=team)
            if not role:
                no_role.append(team)
                continue
            mentionable = role.mentionable or guild.me.guild_permissions.mention_everyone
            if mentionable:
                mentionable_roles.append(role)
            if not mentionable:
                non_mention_roles.append(role)
        if mentionable_roles:
            reply += _("__The following team roles **are** mentionable:__ {teams}\n\n").format(
                teams=humanize_list([r.mention for r in mentionable_roles]),
            )
        if non_mention_roles:
            reply += _(
                "__The following team roles **are not** mentionable:__ {non_mention}\n\n"
            ).format(non_mention=humanize_list([r.mention for r in non_mention_roles]))
        if no_role:
            reply += _("__The following team roles could not be found:__ {non_role}\n\n").format(
                non_role=humanize_list(no_role)
            )
        return reply

    @commands.group(name="hockeynotifications", with_app_command=False)
    async def hockey_notifications(self, ctx: commands.Context) -> None:
        """
        Settings related to role notifications
        """
        pass

    @hockey_notifications.command(name="goal", with_app_command=False)
    @commands.mod_or_permissions(manage_roles=True)
    async def set_goal_notification_style(
        self, ctx: commands.Context, on_off: Optional[bool] = None
    ) -> None:
        """
        Set the servers goal notification style. Options are:

        `True` - The bot will try to find correct role names for each team and mention that role.
        `False` - The bot will not post any mention for roles.

        The role name must match exactly `@Team Name GOAL` to work. For example
        `@Edmonton Oilers GOAL` will be pinged but `@edmonton oilers goal` will not.

        If the role is mentionable by everyone when set to True this will ping the role.
        Alternatively, if the role is not mentionable by everyone but the bot has permission
        to mention everyone, setting this to True will allow the bot to ping.
        """
        if on_off is None:
            cur_setting = await self.config.guild(ctx.guild).goal_notifications()
            verb = _("On") if cur_setting else _("Off")
            reply = _("__Game State Notifications:__ **{verb}**\n\n").format(verb=verb)
            reply += await self.check_notification_settings(ctx.guild)
            reply += _(
                "No settings have been changed, run this command again "
                "followed by `on` or `off` to enable/disable this setting."
            )
            return await ctx.maybe_send_embed(reply)

        if on_off:
            await self.config.guild(ctx.guild).goal_notifications.set(on_off)
            reply = _("__Goal Notifications:__ **On**\n\n")
            reply += await self.check_notification_settings(ctx.guild)
            if reply:
                await ctx.maybe_send_embed(reply)
        else:
            await self.config.guild(ctx.guild).goal_notifications.clear()
            # Default is False
            await ctx.maybe_send_embed(_("Okay, I will not mention any goals in this server."))

    @hockey_notifications.command(name="otnotifications", with_app_command=False)
    @commands.mod_or_permissions(manage_roles=True)
    async def set_ot_notification_style(
        self, ctx: commands.Context, on_off: Optional[bool] = None
    ) -> None:
        """
        Set the servers Regular Season OT notification style. Options are:

        `True` - The bot will try to find correct role names for each team and mention that role.
        `False` - The bot will not post any mention for roles.

        The role name must match exactly `@Team Name GOAL` to work. For example
        `@Edmonton Oilers GOAL` will be pinged but `@edmonton oilers goal` will not.

        If the role is mentionable by everyone when set to True this will ping the role.
        Alternatively, if the role is not mentionable by everyone but the bot has permission
        to mention everyone, setting this to True will allow the bot to ping.
        """
        if on_off is None:
            cur_setting = await self.config.guild(ctx.guild).ot_notifications()
            verb = _("On") if cur_setting else _("Off")
            reply = _("__OT Notifications:__ **{verb}**\n\n").format(verb=verb)
            reply += await self.check_notification_settings(ctx.guild)
            reply += _(
                "No settings have been changed, run this command again "
                "followed by `on` or `off` to enable/disable this setting."
            )
            return await ctx.maybe_send_embed(reply)

        elif on_off:
            await self.config.guild(ctx.guild).ot_notifications.clear()
            # Deftault is True
            reply = _("__OT Notifications:__ **On**\n\n")
            reply += await self.check_notification_settings(ctx.guild)
            if reply:
                await ctx.maybe_send_embed(reply)
        else:
            await self.config.guild(ctx.guild).ot_notifications.set(on_off)
            await ctx.maybe_send_embed(
                _("Okay, I will not mention OT Period start in this server.")
            )

    @hockey_notifications.command(name="sonotifications", with_app_command=False)
    @commands.mod_or_permissions(manage_roles=True)
    async def set_so_notification_style(
        self, ctx: commands.Context, on_off: Optional[bool] = None
    ) -> None:
        """
        Set the servers Shootout notification style. Options are:

        `True` - The bot will try to find correct role names for each team and mention that role.
        `False` - The bot will not post any mention for roles.

        The role name must match exactly `@Team Name GOAL` to work. For example
        `@Edmonton Oilers GOAL` will be pinged but `@edmonton oilers goal` will not.

        If the role is mentionable by everyone when set to True this will ping the role.
        Alternatively, if the role is not mentionable by everyone but the bot has permission
        to mention everyone, setting this to True will allow the bot to ping.
        """
        if on_off is None:
            cur_setting = await self.config.guild(ctx.guild).so_notifications()
            verb = _("On") if cur_setting else _("Off")
            reply = _("__SO Period Notifications:__ **{verb}**\n\n").format(verb=verb)
            reply += await self.check_notification_settings(ctx.guild)
            reply += _(
                "No settings have been changed, run this command again "
                "followed by `on` or `off` to enable/disable this setting."
            )
            return await ctx.maybe_send_embed(reply)

        if on_off:
            await self.config.guild(ctx.guild).so_notifications.clear()
            # Deftault is True
            reply = _("__SO Period Notifications:__ **On**\n\n")
            reply += await self.check_notification_settings(ctx.guild)
            if reply:
                await ctx.maybe_send_embed(reply)
        else:
            await self.config.guild(ctx.guild).so_notifications.set(on_off)
            await ctx.maybe_send_embed(
                _("Okay, I will not notify SO Period start in this server.")
            )

    @hockey_notifications.command(name="game", with_app_command=False)
    @commands.mod_or_permissions(manage_roles=True)
    async def set_game_start_notification_style(
        self, ctx: commands.Context, on_off: Optional[bool] = None
    ) -> None:
        """
        Set the servers game start notification style. Options are:

        `True` - The bot will try to find correct role names for each team and mention that role.
        Server permissions can override this.
        `False` - The bot will not post any mention for roles.

        The role name must match exactly `@Team Name` to work. For example
        `@Edmonton Oilers` will be pinged but `@edmonton oilers` will not.

        If the role is mentionable by everyone when set to True this will ping the role.
        Alternatively, if the role is not mentionable by everyone but the bot has permission
        to mention everyone, setting this to True will allow the bot to ping.
        """
        if on_off is None:
            cur_setting = await self.config.guild(ctx.guild).game_state_notifications()
            verb = _("On") if cur_setting else _("Off")
            reply = _("__Game State Notifications:__ **{verb}**\n\n").format(verb=verb)
            reply += await self.check_notification_settings(ctx.guild)
            reply += _(
                "No settings have been changed, run this command again "
                "followed by `on` or `off` to enable/disable this setting."
            )
            return await ctx.maybe_send_embed(reply)
        await self.config.guild(ctx.guild).game_state_notifications.set(on_off)
        if on_off:
            reply = _("__Game State Notifications:__ **On**\n\n")
            reply += await self.check_notification_settings(ctx.guild)
            if reply:
                await ctx.maybe_send_embed(reply)
        else:
            await ctx.maybe_send_embed(_("Okay, I will not mention any goals in this server."))

    @hockey_notifications.command(name="goalchannel", with_app_command=False)
    @commands.mod_or_permissions(manage_roles=True)
    async def set_channel_goal_notification_style(
        self,
        ctx: commands.Context,
        channel: discord.TextChannel,
        on_off: Optional[bool] = None,
    ) -> None:
        """
        Set the specified channels goal notification style. Options are:

        `True` - The bot will try to find correct role names for each team and mention that role.
        `False` - The bot will not post any mention for roles.

        The role name must match exactly `@Team Name GOAL` to work. For example
        `@Edmonton Oilers GOAL` will be pinged but `@edmonton oilers goal` will not.

        If the role is mentionable by everyone when set to True this will ping the role.
        Alternatively, if the role is not mentionable by everyone but the bot has permission
        to mention everyone, setting this to True will allow the bot to ping.
        """
        if on_off is None:
            cur_setting = await self.config.channel(channel).game_state_notifications()
            verb = _("On") if cur_setting else _("Off")
            reply = _("__Game State Notifications:__ **{verb}**\n\n").format(verb=verb)
            reply += await self.check_notification_settings(ctx.guild)
            reply += _(
                "No settings have been changed, run this command again "
                "followed by `on` or `off` to enable/disable this setting."
            )
            return await ctx.maybe_send_embed(reply)
        await self.config.channel(channel).goal_notifications.set(on_off)
        if on_off:
            reply = _("__Goal Notifications:__ **On**\n\n")
            reply += await self.check_notification_settings(ctx.guild)
            if reply:
                await ctx.maybe_send_embed(reply)
        else:
            await ctx.maybe_send_embed(
                _(
                    "Okay, I will not mention any goals in {channel}.\n\n"
                    " Note: This does not affect server wide settings from "
                    "`[p]hockeyset notifications goals`"
                ).format(channel=channel.mention)
            )

    @hockey_notifications.command(name="gamechannel", with_app_command=False)
    @commands.mod_or_permissions(manage_roles=True)
    async def set_channel_game_start_notification_style(
        self,
        ctx: commands.Context,
        channel: discord.TextChannel,
        on_off: Optional[bool] = None,
    ) -> None:
        """
        Set the specified channels game start notification style. Options are:

        `True` - The bot will try to find correct role names for each team and mention that role.
        Server permissions can override this.
        `False` - The bot will not post any mention for roles.

        The role name must match exactly `@Team Name` to work. For example
        `@Edmonton Oilers` will be pinged but `@edmonton oilers` will not.

        If the role is mentionable by everyone when set to True this will ping the role.
        Alternatively, if the role is not mentionable by everyone but the bot has permission
        to mention everyone, setting this to True will allow the bot to ping.
        """
        if on_off is None:
            cur_setting = await self.config.channel(channel).goal_notifications()
            verb = _("On") if cur_setting else _("Off")
            reply = _("__Game State Notifications:__ **{verb}**\n\n").format(verb=verb)
            reply += await self.check_notification_settings(ctx.guild)
            reply += _(
                "No settings have been changed, run this command again "
                "followed by `on` or `off` to enable/disable this setting."
            )
            return await ctx.maybe_send_embed(reply)
        await self.config.channel(channel).game_state_notifications.set(on_off)
        if on_off:
            reply = _("__Game State Notifications:__ **On**\n\n")
            reply += await self.check_notification_settings(ctx.guild)
            if reply:
                await ctx.maybe_send_embed(reply)
        else:
            await ctx.maybe_send_embed(
                _(
                    "Okay, I will not mention any updates in {channel}.\n\n"
                    " Note: This does not affect server wide settings from "
                    "`[p]hockeyset notifications goals`"
                ).format(channel=channel.mention)
            )

    @hockeyset_commands.command(name="poststandings", aliases=["poststanding"])
    @commands.mod_or_permissions(manage_channels=True)
    async def post_standings(
        self,
        ctx: commands.Context,
        standings_type: StandingsFinder,
        channel: Optional[discord.TextChannel] = None,
    ) -> None:
        """
        Posts automatic standings when all games for the day are done

        `<standings_type>` can be a division name or all
        `[channel]` The channel you want standings to be posted into, if not provided
        this will use the current channel.
        """
        await ctx.defer()
        guild = ctx.guild
        if channel is None:
            channel = ctx.channel
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
        guild = ctx.message.guild
        cur_state = not await self.config.guild(guild).post_standings()
        verb = _("will") if cur_state else _("won't")
        msg = _("Okay, standings ") + verb + _(" be updated automatically.")
        await self.config.guild(guild).post_standings.set(cur_state)
        await ctx.send(msg)

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
        cur_states = []
        async with self.config.channel(channel).game_states() as game_states:
            if state.value in game_states:
                game_states.remove(state.value)
            else:
                game_states.append(state.value)
            cur_states = game_states
        msg = _("{channel} game updates set to {states}").format(
            channel=channel.mention, states=humanize_list(cur_states) if cur_states else _("None")
        )
        await ctx.send(msg)
        if not await self.config.channel(channel).team():
            await ctx.channel.send(
                _(
                    "You have not setup any team updates in {channel}. "
                    "You can do so with `{prefix}hockeyset add`."
                ).format(channel=channel.mention, prefix=ctx.prefix)
            )

    @hockeyset_commands.command(name="goalimage")
    @commands.mod_or_permissions(manage_channels=True)
    async def include_goal_image_toggle(
        self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None
    ):
        """
        Toggle including goal images when a goal is posted

        `[channel]` The channel you specifically want goal images enabled for.
        If channel is not provided the server-wide setting will be toggled instead.
        """
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
        channel: Optional[discord.TextChannel] = None,
    ) -> None:
        """
        Adds a hockey team goal updates to a channel do 'all' for all teams

        `<team>` needs to be all or part of an NHL team if more than one team
        match it will ask for the correct team.
        `[channel]` The channel to post updates into. Defaults to the current channel
        if not provided.
        """
        if not team:
            await ctx.send(_("You must provide a valid current team."))
            return
        # team_data = await self.get_team(team)
        async with ctx.typing():
            if channel is None:
                channel = ctx.channel
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
        await ctx.send(msg)

    @hockeyset_commands.command(name="remove", aliases=["del", "rem", "delete"])
    @commands.mod_or_permissions(manage_channels=True)
    async def remove_goals(
        self,
        ctx: commands.Context,
        team: Optional[TeamFinder] = None,
        channel: Optional[discord.TextChannel] = None,
    ) -> None:
        """
        Removes a teams goal updates from a channel
        defaults to the current channel
        """
        if channel is None:
            channel = ctx.channel
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
