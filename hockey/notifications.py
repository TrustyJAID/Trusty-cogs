from typing import Optional, Union

import discord
from red_commons.logging import getLogger
from redbot.core import commands
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import humanize_list

from .abc import HockeyMixin
from .constants import TEAMS

_ = Translator("Hockey", __file__)

log = getLogger("red.trusty-cogs.Hockey")

hockey_commands = HockeyMixin.hockey_commands


class HockeyNotifications(HockeyMixin):
    async def check_notification_settings(self, guild: discord.Guild, goal: bool = False) -> str:
        reply = ""
        mentionable_roles = []
        non_mention_roles = []
        no_role = []
        for team in TEAMS:
            team_name = team if not goal else f"{team} GOAL"
            role = discord.utils.get(guild.roles, name=team_name)
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

    @hockey_commands.group(name="notifications", aliases=["pings"], with_app_command=False)
    @commands.guild_only()
    async def hockey_notifications(self, ctx: commands.Context) -> None:
        """
        Settings related to role notifications
        """
        pass

    @hockey_notifications.command(name="defaultstart", with_app_command=False)
    @commands.mod_or_permissions(manage_roles=True)
    async def set_game_start_notification_style(
        self, ctx: commands.Context, *roles: discord.Role
    ) -> None:
        """
        Set the role(s) to be notified when a game starts.
        This setting applies to all automatically created channels/threads.

        `<roles...>` The roles which you want to be pinged when a game starts.
        """
        async with self.config.guild(ctx.guild).start_roles() as existing:
            for role in roles:
                if role.id in existing:
                    existing.remove(role.id)
                else:
                    existing.append(role.id)
            final_roles = [
                ctx.guild.get_role(r) for r in existing if ctx.guild.get_role(r) is not None
            ]
        await ctx.send(
            _("The following roles will be pinged when a game starts.\n{roles}").format(
                roles=humanize_list([r.mention for r in final_roles])
            )
        )

    @hockey_notifications.command(name="defaultgoal", with_app_command=False)
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
            reply = _("__Goal Notifications:__ **{verb}**\n\n").format(verb=verb)
            reply += await self.check_notification_settings(ctx.guild, goal=True)
            reply += _(
                "No settings have been changed, run this command again "
                "followed by `on` or `off` to enable/disable this setting."
            )
            await ctx.maybe_send_embed(reply)
            return

        if on_off:
            await self.config.guild(ctx.guild).goal_notifications.set(on_off)
            reply = _("__Goal Notifications:__ **On**\n\n")
            reply += await self.check_notification_settings(ctx.guild, goal=True)
            if reply:
                await ctx.maybe_send_embed(reply)
        else:
            await self.config.guild(ctx.guild).goal_notifications.clear()
            # Default is False
            await ctx.maybe_send_embed(_("Okay, I will not mention any goals in this server."))

    @hockey_notifications.command(
        name="overtime", aliases=["otnotifications", "ot"], with_app_command=False
    )
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
            await ctx.maybe_send_embed(reply)
            return

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

    @hockey_notifications.command(
        name="shootout", aliases=["so", "sonotifications"], with_app_command=False
    )
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
            await ctx.maybe_send_embed(reply)
            return

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

    @hockey_notifications.command(
        name="defaultgame", aliases=["gamestate", "state"], with_app_command=False
    )
    @commands.mod_or_permissions(manage_roles=True)
    async def set_game_state_notification_style(
        self, ctx: commands.Context, on_off: Optional[bool] = None
    ) -> None:
        """
        Set the servers game state notification style.
        This will notify for all period starts in the game.

        Options are:
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

    @hockey_notifications.command(name="gamestart", aliases=["start"], with_app_command=False)
    @commands.mod_or_permissions(manage_roles=True)
    async def set_game_start_notification_channel(
        self,
        ctx: commands.Context,
        channel: Union[discord.TextChannel, discord.Thread, discord.ForumChannel],
        *roles: discord.Role,
    ) -> None:
        """
        Set the role(s) to be notified when a game starts.
        This applies only to the specified channel.

        `<roles...>` The roles which you want to be pinged when a game starts.
        """
        async with self.config.channel(channel).start_roles() as existing:
            for role in roles:
                if role.id in existing:
                    existing.remove(role.id)
                else:
                    existing.append(role.id)
            final_roles = [
                ctx.guild.get_role(r) for r in existing if ctx.guild.get_role(r) is not None
            ]
        await ctx.send(
            _(
                "The following roles will be pinged in {channel} when a game starts.\n{roles}"
            ).format(
                roles=humanize_list([r.mention for r in final_roles]), channel=channel.mention
            )
        )

    @hockey_notifications.command(name="goal", with_app_command=False)
    @commands.mod_or_permissions(manage_roles=True)
    async def set_channel_goal_notification_style(
        self,
        ctx: commands.Context,
        channel: Union[discord.TextChannel, discord.Thread],
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

    @hockey_notifications.command(name="game", with_app_command=False)
    @commands.mod_or_permissions(manage_roles=True)
    async def set_channel_game_state_notification_style(
        self,
        ctx: commands.Context,
        channel: Union[discord.TextChannel, discord.Thread],
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
