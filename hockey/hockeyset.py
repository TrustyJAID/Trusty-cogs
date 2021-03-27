import asyncio
import aiohttp
import logging
from typing import Optional
from datetime import datetime

import discord
from redbot.core import Config, checks, commands
from redbot.core.bot import Red
from redbot.core.i18n import Translator, cog_i18n
from redbot.core.utils.chat_formatting import humanize_list

from .constants import TEAMS
from .helper import HockeyStates, HockeyTeams

from .standings import Standings, DIVISIONS, CONFERENCES
from .game import Game
from .pickems import Pickems

_ = Translator("Hockey", __file__)

log = logging.getLogger("red.trusty-cogs.Hockey")


@cog_i18n(_)
class HockeySetCommands:
    """
    All the commands grouped under `[p]hockeyset`
    """

    bot: Red
    config: Config
    TEST_LOOP: bool
    all_pickems: dict
    save_pickems: bool
    pickems_save_lock: asyncio.Lock
    session: aiohttp.ClientSession

    def __init__(self, *args):
        self.bot
        self.config
        self.TEST_LOOP
        self.all_pickems
        self.save_pickems
        self.pickems_save_lock
        self.session

    @commands.group(name="hockeyset", aliases=["nhlset"])
    @commands.guild_only()
    @checks.mod_or_permissions(manage_channels=True)
    async def hockeyset_commands(self, ctx: commands.Context):
        """
        Setup Hockey commands for the server
        """

    @hockeyset_commands.command(name="settings")
    async def hockey_settings(self, ctx: commands.Context):
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
            if gdc_channels is None:
                gdc_channels = []
            if standings_channel is not None:
                if ctx.channel.permissions_for(guild.me).embed_links:
                    standings_chn = standings_channel.mention
                else:
                    standings_chn = standings_channel.name
                try:
                    standings_msg = await standings_channel.fetch_message(
                        await self.config.guild(guild).standings_msg()
                    )
                except (discord.errors.NotFound, discord.errors.Forbidden):
                    standings_msg = None
                    pass
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
                await ctx.send(embed=em)
            else:
                msg = (
                    f"```\n{guild.name} "
                    + _("Hockey Settings\n")
                    + f"{channels}\n"
                    + _("Notifications")
                    + notification_settings
                    + _("Standings Settings")
                    + "\n#{standings_chn}: {standings_msg}"
                )
                if standings_msg is not None:
                    await ctx.send(msg)
                else:
                    await ctx.send(msg + "```")

    #######################################################################
    # All Hockey setup commands                                           #
    #######################################################################

    @hockeyset_commands.command(hidden=True)
    @checks.admin_or_permissions(administrator=True)
    async def reset(self, ctx: commands.Context):
        """
        Restarts the hockey loop incase there are issues with the posts
        """
        msg = await ctx.send(_("Restarting..."))
        self.loop.cancel()
        await msg.edit(content=msg.content + _("loop closed..."))
        self.loop = self.bot.loop.create_task(self.game_check_loop())
        await msg.edit(content=msg.content + _("restarted"))
        # await ctx.send("Done.")

    @hockeyset_commands.command(hidden=True)
    async def leaderboardset(
        self,
        ctx: commands.Context,
        user: discord.Member,
        season: int,
        weekly: int = None,
        total: int = None,
    ):
        """
        Allows moderators to set a users points on the leaderboard
        """
        if weekly is None:
            weekly = season
        if total is None:
            total = season
        leaderboard = await self.config.guild(ctx.guild).leaderboard()
        if leaderboard == {} or leaderboard is None:
            await ctx.send(_("There is no current leaderboard for this server!"))
            return
        if str(user.id) not in leaderboard:
            leaderboard[str(user.id)] = {"season": season, "weekly": weekly, "total": total}
        else:
            del leaderboard[str(user.id)]
            leaderboard[str(user.id)] = {"season": season, "weekly": weekly, "total": total}
        await self.config.guild(ctx.guild).leaderboard.set(leaderboard)
        msg = _(
            "{user} now has {season} points on the season, "
            "{weekly} points for the week, and {total} votes overall."
        ).format(user=user.display_name, season=season, weekly=weekly, total=total)
        await ctx.send(msg)

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
    async def hockey_notifications(self, ctx: commands.Context):
        """
        Settings related to role notifications
        """
        pass

    @hockey_notifications.command(name="goal")
    @checks.mod_or_permissions(manage_roles=True)
    async def set_goal_notification_style(
        self, ctx: commands.Context, on_off: Optional[bool] = None
    ):
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
    @checks.mod_or_permissions(manage_roles=True)
    async def set_ot_notification_style(
        self, ctx: commands.Context, on_off: Optional[bool] = None
    ):
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
    @checks.mod_or_permissions(manage_roles=True)
    async def set_so_notification_style(
        self, ctx: commands.Context, on_off: Optional[bool] = None
    ):
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
    @checks.mod_or_permissions(manage_roles=True)
    async def set_game_start_notification_style(
        self, ctx: commands.Context, on_off: Optional[bool] = None
    ):
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
    @checks.mod_or_permissions(manage_roles=True)
    async def set_channel_goal_notification_style(
        self, ctx: commands.Context, channel: discord.TextChannel, on_off: Optional[bool] = None
    ):
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
    @checks.mod_or_permissions(manage_roles=True)
    async def set_channel_game_start_notification_style(
        self, ctx: commands.Context, channel: discord.TextChannel, on_off: Optional[bool] = None
    ):
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
        self, ctx: commands.Context, standings_type: str, channel: Optional[discord.TextChannel] = None
    ):
        """
        Posts automatic standings when all games for the day are done

        `<standings_type>` can be a division name or all
        `[channel]` The channel you want standings to be posted into, if not provided
        this will use the current channel.
        """
        guild = ctx.message.guild
        if channel is None:
            channel = ctx.message.channel

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
    async def togglestandings(self, ctx: commands.Context):
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
    ):
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
    @checks.is_owner()
    async def set_game_publish_updates(
        self, ctx: commands.Context, channel: discord.TextChannel, *state: HockeyStates
    ):
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
    ):
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
    ):
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

    @hockeyset_commands.group(name="pickems")
    @checks.admin_or_permissions(manage_channels=True)
    async def pickems_commands(self, ctx: commands.Context):
        """
        Commands for managing pickems
        """
        pass

    @pickems_commands.command(name="setup", aliases=["auto", "set"])
    @checks.admin_or_permissions(manage_channels=True)
    async def setup_auto_pickems(
        self, ctx: commands.Context, category: discord.CategoryChannel = None
    ):
        """
        Sets up automatically created pickems channels every week.

        `[category]` the channel category where pickems channels will be created.
        This must be the category ID. If not provided this will use the current
        channels category if it exists.
        """

        if category is None and not ctx.channel.category:
            return await ctx.send(_("A channel category is required."))
        elif category is None and ctx.channel.category is not None:
            category = ctx.channel.category

        if not category.permissions_for(ctx.me).manage_channels:
            await ctx.send(_("I don't have manage channels permission!"))
            return

        await self.config.guild(ctx.guild).pickems_category.set(category.id)
        existing_channels = await self.config.guild(ctx.guild).pickems_channels()
        if existing_channels:
            cant_delete = []
            for chan_id in existing_channels:
                channel = ctx.guild.get_channel(chan_id)
                if channel:
                    try:
                        await channel.delete()
                    except discord.errors.Forbidden:
                        cant_delete.append(chan_id)
                await self.config.guild(ctx.guild).pickems_channels.clear()
                if cant_delete:
                    chans = humanize_list([f"<#{_id}>" for _id in cant_delete])
                    await ctx.send(
                        _(
                            "I tried to delete the following channels without success:\n{chans}"
                        ).format(chans=chans)
                    )
        async with self.pickems_save_lock:
            log.debug("Locking save")
            await Pickems.create_weekly_pickems_pages(self.bot, [ctx.guild], Game)
        await ctx.send(_("I will now automatically create pickems pages every Sunday."))

    @pickems_commands.command(name="clear")
    @checks.admin_or_permissions(manage_channels=True)
    async def delete_auto_pickems(self, ctx: commands.Context):
        """
        Automatically delete all the saved pickems channels.
        """
        existing_channels = await self.config.guild(ctx.guild).pickems_channels()
        if existing_channels:
            cant_delete = []
            for chan_id in existing_channels:
                channel = ctx.guild.get_channel(chan_id)
                if channel:
                    try:
                        await channel.delete()
                    except discord.errors.Forbidden:
                        cant_delete.append(chan_id)
                await self.config.guild(ctx.guild).pickems_channels.clear()
                if cant_delete:
                    chans = humanize_list([f"<#{_id}>" for _id in cant_delete])
                    await ctx.send(
                        _(
                            "I tried to delete the following channels without success:\n{chans}"
                        ).format(chans=chans)
                    )
        await ctx.send(_("I have deleted existing pickems channels."))

    @pickems_commands.command(name="toggle")
    @checks.admin_or_permissions(manage_channels=True)
    async def toggle_auto_pickems(self, ctx: commands.Context):
        """
        Turn off automatic pickems page creation
        """
        await self.config.guild(ctx.guild).pickems_category.set(None)
        await ctx.tick()

    @pickems_commands.command(name="page")
    @checks.admin_or_permissions(manage_channels=True)
    async def pickems_page(self, ctx, date: str = None):
        """
        Generates a pickems page for voting on a specified day must be "YYYY-MM-DD"
        """
        if date is None:
            new_date = datetime.now()
        else:
            new_date = datetime.strptime(date, "%Y-%m-%d")
        msg = _(
            "**Welcome to our daily Pick'ems challenge!  Below you will see today's games!"
            "  Vote for who you think will win!  You get one point for each correct prediction."
            "  We will be tracking points over the course "
            "of the season and will be rewarding weekly,"
            " worst and full-season winners!**\n\n"
            "- Click the reaction for the team you think will win the day's match-up.\n"
            "- Anyone who votes for both teams will have their "
            "vote removed and will receive no points!\n\n\n\n"
        )
        games_list = await Game.get_games(None, new_date, new_date, session=self.session)
        await ctx.send(msg)
        async with self.pickems_save_lock:
            for game in games_list:
                new_msg = await ctx.send(
                    "__**{} {}**__ @ __**{} {}**__".format(
                        game.away_emoji, game.away_team, game.home_emoji, game.home_team
                    )
                )
                # Create new pickems object for the game

                await Pickems.create_pickem_object(self.bot, ctx.guild, new_msg, ctx.channel, game)
                if ctx.channel.permissions_for(ctx.guild.me).add_reactions:
                    try:
                        await new_msg.add_reaction(game.away_emoji[2:-1])
                        await new_msg.add_reaction(game.home_emoji[2:-1])
                    except Exception:
                        log.debug("Error adding reactions")

    @pickems_commands.command(name="remove")
    async def rempickem(self, ctx: commands.Context, true_or_false: bool):
        """
        Clears the servers current pickems object list

        `<true_or_false>` `True` if you're sure you want to clear the settings.
        """
        if true_or_false:
            await self.config.guild(ctx.guild).pickems.clear()
            try:
                del self.all_pickems[str(ctx.guild.id)]
            except KeyError:
                pass
            await ctx.send(_("All pickems removed on this server."))
        else:
            await ctx.send(_("I will not remove the current pickems on this server."))

    @pickems_commands.group(name="leaderboard")
    async def pickems_leaderboard_commands(self, ctx: commands.Context):
        """
        Settings for clearing/resetting pickems leaderboards
        """
        pass

    @pickems_leaderboard_commands.command(name="clear")
    async def clear_server_leaderboard(self, ctx: commands.Context, true_or_false: bool):
        """
        Clears the entire pickems leaderboard in the server.

        `<true_or_false>` `True` if you're sure you want to clear the settings.
        """
        if true_or_false:
            await self.config.guild(ctx.guild).leaderboard.clear()
            await ctx.send(_("Server leaderboard reset."))
        else:
            await ctx.send(_("I will not reset the pickems leaderboard in this server."))

    @pickems_leaderboard_commands.command(name="clearweekly")
    async def clear_weekly_leaderboard(self, ctx: commands.Context, true_or_false: bool):
        """
        Clears the weekly tracker on the current servers pickems

        `<true_or_false>` `True` if you're sure you want to clear the settings.
        """
        if true_or_false:
            leaderboard = await self.config.guild(ctx.guild).leaderboard()
            if leaderboard is None:
                leaderboard = {}
            for user in leaderboard:
                leaderboard[str(user)]["weekly"] = 0
            await self.config.guild(ctx.guild).leaderboard.set(leaderboard)
            await ctx.send(_("Servers weekly leaderboard reset."))
        else:
            await ctx.send(_("I will not reset the pickems weekly leaderboard in this server."))

    @pickems_leaderboard_commands.command(name="clearseason")
    async def clear_seasonal_leaderboard(self, ctx: commands.Context, true_or_false: bool):
        """
        Clears the weekly tracker on the current servers pickems

        `<true_or_false>` `True` if you're sure you want to clear the settings.
        """
        if true_or_false:
            leaderboard = await self.config.guild(ctx.guild).leaderboard()
            if leaderboard is None:
                leaderboard = {}
            for user in leaderboard:
                leaderboard[str(user)]["season"] = 0
            await self.config.guild(ctx.guild).leaderboard.set(leaderboard)
            await ctx.send(_("Servers weekly leaderboard reset."))
        else:
            await ctx.send(_("I will not reset the pickems seasonal leaderboard in this server."))
