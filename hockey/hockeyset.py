import logging
import pytz
from typing import Optional

import discord
from redbot.core import commands
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import humanize_list, pagify

from .abc import MixinMeta
from .constants import TEAMS
from .helper import HockeyStates, HockeyTeams, TimezoneFinder
from .menu import BaseMenu, SimplePages
from .standings import CONFERENCES, DIVISIONS, Standings

_ = Translator("Hockey", __file__)

log = logging.getLogger("red.trusty-cogs.Hockey")

hockeyset_commands = MixinMeta.hockeyset_commands


class HockeySetCommands(MixinMeta):
    """
    All the commands grouped under `[p]hockeyset`
    """

    @hockeyset_commands.command(name="settings")
    async def hockey_settings(self, ctx: commands.Context) -> None:
        """
        Show hockey settings for this server
        """
        async with ctx.typing():
            guild = ctx.message.guild
            standings_channel = guild.get_channel(
                await self.config.guild(guild).standings_channel()
            )
            post_standings = (
                _("On") if await self.config.guild(guild).post_standings() else _("Off")
            )
            gdc_channels = await self.config.guild(guild).gdc()
            timezone = await self.config.guild(guild).timezone() or _("Home Teams Timezone")
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
            else:
                standings_chn = "None"
                standings_msg = "None"
            channels = ""
            for channel in await self.config.all_channels():
                chn = guild.get_channel(channel)
                if chn is not None:
                    teams = ", ".join(t for t in await self.config.channel(chn).team())
                    is_gdc = "(GDC)" if chn.id in gdc_channels else ""
                    game_states = await self.config.channel(chn).game_states()
                    channels += f"{chn.mention}{is_gdc}: {teams}\n"

                    if len(game_states) != 4:
                        channels += _("Game States: ") + ", ".join(s for s in game_states)
                        channels += "\n"

            notification_settings = _("Game Start: {game_start}\nGoals: {goals}\n").format(
                game_start=await self.config.guild(guild).game_state_notifications(),
                goals=await self.config.guild(guild).goal_notifications(),
            )
            if ctx.channel.permissions_for(guild.me).embed_links:
                em = discord.Embed(title=guild.name + _(" Hockey Settings"))
                em.colour = await ctx.embed_colour()
                em.description = channels
                em.add_field(
                    name=_("Standings Settings"), value=f"{standings_chn}: {standings_msg}"
                )
                em.add_field(name=_("Notifications"), value=notification_settings)
                em.add_field(name=_("Timezone"), value=timezone)
                await ctx.send(embed=em)
            else:
                msg = _(
                    "{guild} Hockey Settings\n {channels}\nNotifications\n{notifications}"
                    "\nStandings Settings\n{standings_chn}: {standings}\n"
                    "Timezone: {timezone}"
                ).format(
                    guild=guild.name,
                    channels=channels,
                    notifications=notification_settings,
                    standings_chn=standings_chn,
                    standings=standings_msg,
                    timezone=timezone,
                )
                await ctx.send(msg)

    #######################################################################
    # All Hockey setup commands                                           #
    #######################################################################

    @hockeyset_commands.group(
        name="timezone", aliases=["timezones", "tz"], invoke_without_command=True
    )
    async def set_hockey_timezone(
        self, ctx: commands.Context, timezone: Optional[TimezoneFinder] = None
    ) -> None:
        """
        Customize the servers timezone

        This is utilized in `[p]hockey schedule` and game day channel creation

        `[timezone]` The full name of the timezone you want to set. For a list of
        available timezone names use `[p]hockeyset timezone list`
        defaults to Home Teams Tmezone if not provided
        """
        if ctx.invoked_subcommand is None:
            if timezone is not None:
                await self.config.guild(ctx.guild).timezone.set(timezone)
            else:
                await self.config.guild(ctx.guild).timezone.clear()
                timezone = _("Home Teams Timezone")
            msg = _("Server Timezone set to {timezone}").format(timezone=timezone)
            await ctx.send(msg)

    @set_hockey_timezone.command(name="list")
    async def list_hockey_timezones(self, ctx: commands.Context) -> None:
        """
        List the available timezones for pickems messages
        """
        msg = "\n".join(tz for tz in pytz.common_timezones)
        msgs = []
        embeds = ctx.channel.permissions_for(ctx.me).embed_links
        for page in pagify(msg, page_length=512):
            if embeds:
                msgs.append(discord.Embed(title=_("Timezones Available"), description=page))
            else:
                msgs.append(page)
        await BaseMenu(
            source=SimplePages(pages=msgs),
            delete_message_after=False,
            clear_reactions_after=True,
            timeout=60,
        ).start(ctx=ctx)

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

    @hockeyset_commands.group(name="notifications")
    async def hockey_notifications(self, ctx: commands.Context) -> None:
        """
        Settings related to role notifications
        """
        pass

    @hockey_notifications.command(name="goal")
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

    @hockey_notifications.command(name="otnotifications")
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

    @hockey_notifications.command(name="sonotifications")
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

    @hockey_notifications.command(name="game")
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

    @hockey_notifications.command(name="goalchannel")
    @commands.mod_or_permissions(manage_roles=True)
    async def set_channel_goal_notification_style(
        self, ctx: commands.Context, channel: discord.TextChannel, on_off: Optional[bool] = None
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

    @hockey_notifications.command(name="gamechannel")
    @commands.mod_or_permissions(manage_roles=True)
    async def set_channel_game_start_notification_style(
        self, ctx: commands.Context, channel: discord.TextChannel, on_off: Optional[bool] = None
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
    async def post_standings(
        self,
        ctx: commands.Context,
        standings_type: str,
        channel: Optional[discord.TextChannel] = None,
    ) -> None:
        """
        Posts automatic standings when all games for the day are done

        `<standings_type>` can be a division name or all
        `[channel]` The channel you want standings to be posted into, if not provided
        this will use the current channel.
        """
        guild = ctx.message.guild
        if channel is None:
            channel = ctx.message.channel
        channel_perms = channel.permissions_for(ctx.me)
        if not (
            channel_perms.send_messages
            and channel_perms.embed_links
            and channel_perms.read_message_history
        ):
            return await ctx.send(
                _(
                    "I require permission to send messages, embed "
                    "links, and read message history in {channel}."
                ).format(channel=channel.mention)
            )
        if standings_type.lower() not in DIVISIONS + CONFERENCES + ["all"]:
            await ctx.send(
                _("You must choose from: {standings_types}.").format(
                    standings_types=humanize_list(DIVISIONS + CONFERENCES + ["all"])
                )
            )
            return

        standings, page = await Standings.get_team_standings(
            standings_type.lower(), session=self.session
        )
        if standings_type.lower() != "all":
            em = await Standings.build_standing_embed(standings, page)
        else:
            em = await Standings.all_standing_embed(standings)
        await self.config.guild(guild).standings_type.set(standings_type)
        await self.config.guild(guild).standings_channel.set(channel.id)
        await ctx.send(_("Sending standings to {channel}").format(channel=channel.mention))
        message = await channel.send(embed=em)
        await self.config.guild(guild).standings_msg.set(message.id)
        await ctx.send(
            _("{standings_type} standings will now be automatically updated in {channel}.").format(
                standings_type=standings_type, channel=channel.mention
            )
        )
        await self.config.guild(guild).post_standings.set(True)

    @hockeyset_commands.command()
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
    async def set_game_state_updates(
        self, ctx: commands.Context, channel: discord.TextChannel, *state: HockeyStates
    ) -> None:
        """
        Set what type of game updates to be posted in the designated channel.

        `<channel>` is a text channel for the updates.
        `<state>` must be any combination of `preview`, `live`, `final`, `goal` and `periodrecap`.

        `preview` updates are the pre-game notifications 60, 30, and 10 minutes
        before the game starts and the pre-game notification at the start of the day.

        Note: This may disable pickems if it is not selected.
        `live` are the period start notifications.
        `final` is the final game update including 3 stars.
        `goal` is all goal updates.
        `periodrecap` is a recap of the period at the intermission.
        """
        await self.config.channel(channel).game_states.set(list(set(state)))
        await ctx.send(
            _("{channel} game updates set to {states}").format(
                channel=channel.mention, states=humanize_list(list(set(state)))
            )
        )
        if not await self.config.channel(channel).team():
            await ctx.send(
                _(
                    "You have not setup any team updates in {channel}. "
                    "You can do so with `{prefix}hockeyset add`."
                ).format(channel=channel.mention, prefix=ctx.prefix)
            )

    @hockeyset_commands.command(name="publishupdates", hidden=True)
    @commands.is_owner()
    async def set_game_publish_updates(
        self, ctx: commands.Context, channel: discord.TextChannel, *state: HockeyStates
    ) -> None:
        """
        Set what type of game updates will be published in the designated news channel.

        Note: Discord has a limit on the number of published messages per hour.
        This does not error on the bot and can lead to waiting forever for it to update.

        `<channel>` is a text channel for the updates.
        `<state>` must be any combination of `preview`, `live`, `final`, and `periodrecap`.

        `preview` updates are the pre-game notifications 60, 30, and 10 minutes
        before the game starts and the pre-game notification at the start of the day.

        Note: This may disable pickems if it is not selected.
        `live` are the period start notifications.
        `final` is the final game update including 3 stars.
        `periodrecap` is a recap of the period at the intermission.
        """
        if not channel.is_news():
            return await ctx.send(
                _("The designated channel is not a news channel that I can publish in.")
            )
        await self.config.channel(channel).publish_states.set(list(set(state)))
        await ctx.send(
            _("{channel} game updates set to publish {states}").format(
                channel=channel.mention, states=humanize_list(list(set(state)))
            )
        )
        if not await self.config.channel(channel).team():
            await ctx.send(
                _(
                    "You have not setup any team updates in {channel}. "
                    "You can do so with `{prefix}hockeyset add`."
                ).format(channel=channel.mention, prefix=ctx.prefix)
            )

    @hockeyset_commands.command(name="add", aliases=["addgoals"])
    async def add_goals(
        self, ctx: commands.Context, team: HockeyTeams, channel: Optional[discord.TextChannel]
    ) -> None:
        """
        Adds a hockey team goal updates to a channel do 'all' for all teams

        `<team>` needs to be all or part of an NHL team if more than one team
        match it will ask for the correct team.
        `[channel]` The channel to post updates into. Defaults to the current channel
        if not provided.
        """
        if team is None:
            return await ctx.send(_("You must provide a valid current team."))
        # team_data = await self.get_team(team)
        if channel is None:
            channel = ctx.message.channel
        cur_teams = await self.config.channel(channel).team()
        cur_teams = [] if cur_teams is None else cur_teams
        if team in cur_teams:
            # await self.config.channel(channel).team.set([team])
            return await ctx.send(
                _("{team} is already posting updates in {channel}").format(
                    team=team, channel=channel.mention
                )
            )
        else:
            cur_teams.append(team)
            await self.config.channel(channel).team.set(cur_teams)
        await ctx.send(
            _("{team} goals will be posted in {channel}").format(
                team=team, channel=channel.mention
            )
        )

    @hockeyset_commands.command(name="del", aliases=["remove", "rem"])
    async def remove_goals(
        self,
        ctx: commands.Context,
        team: Optional[HockeyTeams] = None,
        channel: Optional[discord.TextChannel] = None,
    ) -> None:
        """
        Removes a teams goal updates from a channel
        defaults to the current channel
        """
        if channel is None:
            channel = ctx.message.channel
        cur_teams = await self.config.channel(channel).team()
        if not cur_teams:
            await ctx.send(
                _("No teams are currently being posted in {channel}.").format(
                    channel=channel.mention
                )
            )
            return
        if team is None:
            await self.config.channel(channel).clear()
            await ctx.send(
                _("No game updates will be posted in {channel}.").format(channel=channel.mention)
            )
            return
        if team is not None:
            # guild = ctx.message.guild
            if team in cur_teams:
                cur_teams.remove(team)
                if cur_teams == []:
                    await self.config.channel(channel).clear()
                    await ctx.send(
                        _("No game updates will be posted in {channel}.").format(
                            channel=channel.mention
                        )
                    )
                else:
                    await self.config.channel(channel).team.set(cur_teams)
                    await ctx.send(
                        _("{team} goal updates removed from {channel}.").format(
                            team=team, channel=channel.mention
                        )
                    )
