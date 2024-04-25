from typing import Union

import discord
from red_commons.logging import getLogger
from redbot.core import commands
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import humanize_list, pagify
from redbot.core.utils.views import SimpleMenu

from .abc import HockeyMixin
from .helper import TeamFinder

_ = Translator("Hockey", __file__)

log = getLogger("red.trusty-cogs.Hockey")

hockey_commands = HockeyMixin.hockey_commands


class HockeyNotifications(HockeyMixin):
    def get_role_info(self, guild: discord.Guild, data: dict) -> str:
        ret = ""
        for name, role_ids in data.items():
            ret += f"- {name}\n"
            for role_id in role_ids:
                if role := guild.get_role(role_id):
                    ret += f" - {role.mention}\n"
                else:
                    ret += f" - Deleted Role ({role_id})\n"
        return ret

    async def check_channel_notification_settings(self, channel: discord.TextChannel) -> str:
        reply = ""
        start = await self.config.channel(channel).game_start_roles()
        state = await self.config.channel(channel).game_state_roles()
        goals = await self.config.channel(channel).game_goal_roles()
        if start:
            reply += _("Game Start:\n{info}").format(info=self.get_role_info(channel.guild, start))
        if state:
            reply += _("Period Start:\n{info}").format(
                info=self.get_role_info(channel.guild, state)
            )
        if goals:
            reply += _("Goals:\n{info}").format(info=self.get_role_info(channel.guild, goals))

        return reply

    async def check_default_notification_settings(self, guild: discord.Guild) -> str:
        reply = ""
        default_start = await self.config.guild(guild).default_start_roles()
        default_state = await self.config.guild(guild).default_state_roles()
        default_goals = await self.config.guild(guild).default_goal_roles()
        ot = await self.config.guild(guild).ot_notifications()
        so = await self.config.guild(guild).so_notifications()
        if default_start:
            reply += _("Game Start:\n{info}").format(info=self.get_role_info(guild, default_start))
        if default_state:
            reply += _("Period Start:\n{info}").format(
                info=self.get_role_info(guild, default_state)
            )
            if ot:
                reply += _("Overtime Notifications: Enabled\n")
            if so:
                reply += _("Shootout Notifications: Enabled\n")
        if default_goals:
            reply += _("Goals:\n{info}").format(info=self.get_role_info(guild, default_goals))

        return reply

    @hockey_commands.group(name="notifications", aliases=["pings"], with_app_command=False)
    @commands.guild_only()
    async def hockey_notifications(self, ctx: commands.Context) -> None:
        """
        Settings related to role notifications
        """
        pass

    @hockey_notifications.command(name="info", aliases=["settings"], with_app_command=False)
    @commands.mod_or_permissions(manage_roles=True)
    @commands.bot_has_permissions(embed_links=True)
    async def hockey_notification_settings(self, ctx: commands.Context) -> None:
        """
        Show Notification Settings for the server.
        """
        defaults = await self.check_default_notification_settings(ctx.guild)
        channels = {}
        for channel_id, info in (await self.config.all_channels()).items():
            if channel := ctx.guild.get_channel_or_thread(channel_id):
                if channel_info := await self.check_channel_notification_settings(channel):
                    channels[channel] = channel_info
        embeds = []
        em = discord.Embed(colour=await self.bot.get_embed_colour(ctx))
        em.description = _("Default Settings:\n{defaults}").format(
            defaults=defaults or _("No Defaults Set.")
        )
        for channel, info in channels.items():
            if len(em) >= 4000 or len(em.fields) > 5:
                embeds.append(em)
                em = discord.Embed(colour=await self.bot.get_embed_colour(ctx))
            for page in pagify(info, page_length=1024):
                if len(em) >= 4000 or len(em.fields) > 5:
                    embeds.append(em)
                    em = discord.Embed(colour=await self.bot.get_embed_colour(ctx))
                em.add_field(name=channel.mention, value=page)
        embeds.append(em)
        await SimpleMenu(embeds, use_select_menu=True).start(ctx)

    @hockey_notifications.command(name="defaultstart", with_app_command=False)
    @commands.mod_or_permissions(manage_roles=True)
    async def set_default_game_start_notification_style(
        self, ctx: commands.Context, team: TeamFinder, *roles: discord.Role
    ) -> None:
        """
        Set the default role(s) to be notified when a game starts.
        This setting applies to all automatically created channels/threads.

        `<team>` The team playing to notify this role. Can be `all`.
        `<roles...>` The roles which you want to be pinged when a game starts.
        If a role is already set and included in this command it will be removed.
        """
        async with self.config.guild(ctx.guild).default_start_roles() as existing:
            if team not in existing:
                existing[team] = []
            for role in roles:
                if role.id in existing[team]:
                    existing[team].remove(role.id)
                else:
                    existing[team].append(role.id)
            if len(existing[team]) == 0:
                del existing[team]
            final_roles = []
            if team in existing:
                final_roles = [
                    ctx.guild.get_role(r)
                    for r in existing[team]
                    if ctx.guild.get_role(r) is not None
                ]
        await ctx.send(
            _("The following roles will be pinged when a game starts for {team}.\n{roles}").format(
                roles=humanize_list([r.mention for r in final_roles]), team=team
            )
        )

    @hockey_notifications.command(
        name="defaultgoal", aliases=["defaultgoals"], with_app_command=False
    )
    @commands.mod_or_permissions(manage_roles=True)
    async def set_default_goal_notification_style(
        self, ctx: commands.Context, team: TeamFinder, *roles: discord.Role
    ) -> None:
        """
        Set the default role(s) to be notified when a goal occurs.
        This setting applies to all automatically created channels/threads.

        `<team>` The team playing to notify this role. Can be `all`.
        `<roles...>` The roles which you want to be pinged when a game starts.
        If a role is already set and included in this command it will be removed.
        """
        async with self.config.guild(ctx.guild).default_goal_roles() as existing:
            if team not in existing:
                existing[team] = []
            for role in roles:
                if role.id in existing[team]:
                    existing[team].remove(role.id)
                else:
                    existing[team].append(role.id)
            if len(existing[team]) == 0:
                del existing[team]
            final_roles = []
            if team in existing:
                final_roles = [
                    ctx.guild.get_role(r)
                    for r in existing[team]
                    if ctx.guild.get_role(r) is not None
                ]
        await ctx.send(
            _(
                "The following roles will be pinged when a goal is scored for {team}.\n{roles}"
            ).format(roles=humanize_list([r.mention for r in final_roles]), team=team)
        )

    @hockey_notifications.command(name="defaultperiod", with_app_command=False)
    @commands.mod_or_permissions(manage_roles=True)
    async def set_default_state_notification_style(
        self, ctx: commands.Context, team: TeamFinder, *roles: discord.Role
    ) -> None:
        """
        Set the default role(s) to be notified for all period starts.
        This setting applies to all automatically created channels/threads.

        `<team>` The team playing to notify this role. Can be `all`.
        `<roles...>` The roles which you want to be pinged when a game starts.
        If a role is already set and included in this command it will be removed.
        """
        async with self.config.guild(ctx.guild).default_state_roles() as existing:
            if team not in existing:
                existing[team] = []
            for role in roles:
                if role.id in existing[team]:
                    existing[team].remove(role.id)
                else:
                    existing[team].append(role.id)
            if len(existing[team]) == 0:
                del existing[team]
            final_roles = []
            if team in existing:
                final_roles = [
                    ctx.guild.get_role(r)
                    for r in existing[team]
                    if ctx.guild.get_role(r) is not None
                ]
        await ctx.send(
            _(
                "The following roles will be pinged when a period starts for {team}.\n{roles}"
            ).format(roles=humanize_list([r.mention for r in final_roles]), team=team)
        )

    @hockey_notifications.command(name="start", with_app_command=False)
    @commands.mod_or_permissions(manage_roles=True)
    async def set_game_start_notification_style(
        self,
        ctx: commands.Context,
        channel: Union[discord.TextChannel, discord.Thread],
        team: TeamFinder,
        *roles: discord.Role,
    ) -> None:
        """
        Set the default role(s) to be notified when a game starts.

        `<channel>` The channel or thread you want notifications in.
        `<team>` The team playing to notify this role. Can be `all`.
        `<roles...>` The roles which you want to be pinged when a game starts.
        If a role is already set and included in this command it will be removed.
        """
        async with self.config.channel(channel).game_start_roles() as existing:
            if team not in existing:
                existing[team] = []
            for role in roles:
                if role.id in existing[team]:
                    existing[team].remove(role.id)
                else:
                    existing[team].append(role.id)
            if len(existing[team]) == 0:
                del existing[team]
            final_roles = []
            if team in existing:
                final_roles = [
                    ctx.guild.get_role(r)
                    for r in existing[team]
                    if ctx.guild.get_role(r) is not None
                ]
        await ctx.send(
            _(
                "The following roles will be pinged when a game starts for {team} in {channel}.\n{roles}"
            ).format(
                roles=humanize_list([r.mention for r in final_roles]),
                team=team,
                channel=channel.mention,
            )
        )

    @hockey_notifications.command(name="goal", aliases=["goals"], with_app_command=False)
    @commands.mod_or_permissions(manage_roles=True)
    async def set_goal_notification_style(
        self,
        ctx: commands.Context,
        channel: Union[discord.TextChannel, discord.Thread],
        team: TeamFinder,
        *roles: discord.Role,
    ) -> None:
        """
        Set the role(s) to be notified when a goal is scored.

        `<channel>` The channel or thread you want notifications in.
        `<team>` The team playing to notify this role. Can be `all`.
        `<roles...>` The roles which you want to be pinged when a game starts.
        If a role is already set and included in this command it will be removed.
        """
        async with self.config.channel(channel).game_goal_roles() as existing:
            if team not in existing:
                existing[team] = []
            for role in roles:
                if role.id in existing[team]:
                    existing[team].remove(role.id)
                else:
                    existing[team].append(role.id)
            if len(existing[team]) == 0:
                del existing[team]
            final_roles = []
            if team in existing:
                final_roles = [
                    ctx.guild.get_role(r)
                    for r in existing[team]
                    if ctx.guild.get_role(r) is not None
                ]
        await ctx.send(
            _(
                "The following roles will be pinged when a goal is scored for {team} in {channel}.\n{roles}"
            ).format(
                roles=humanize_list([r.mention for r in final_roles]),
                team=team,
                channel=channel.mention,
            )
        )

    @hockey_notifications.command(name="period", with_app_command=False)
    @commands.mod_or_permissions(manage_roles=True)
    async def set_state_notification_style(
        self,
        ctx: commands.Context,
        channel: Union[discord.TextChannel, discord.Thread],
        team: TeamFinder,
        *roles: discord.Role,
    ) -> None:
        """
        Set the default role(s) to be notified when all periods start.

        `<channel>` The channel or thread you want notifications in.
        `<team>` The team playing to notify this role. Can be `all`.
        `<roles...>` The roles which you want to be pinged when a game starts.
        If a role is already set and included in this command it will be removed.
        """
        async with self.config.channel(channel).game_state_roles() as existing:
            if team not in existing:
                existing[team] = []
            for role in roles:
                if role.id in existing[team]:
                    existing[team].remove(role.id)
                else:
                    existing[team].append(role.id)
            if len(existing[team]) == 0:
                del existing[team]
            final_roles = []
            if team in existing:
                final_roles = [
                    ctx.guild.get_role(r)
                    for r in existing[team]
                    if ctx.guild.get_role(r) is not None
                ]
        await ctx.send(
            _(
                "The following roles will be pinged when a period starts for {team} in {channel}.\n{roles}"
            ).format(
                roles=humanize_list([r.mention for r in final_roles]),
                team=team,
                channel=channel.mention,
            )
        )

    @hockey_notifications.command(
        name="overtime", aliases=["otnotifications", "ot"], with_app_command=False
    )
    @commands.mod_or_permissions(manage_roles=True)
    async def set_ot_notification_style(self, ctx: commands.Context, on_off: bool) -> None:
        """
        Set the servers Regular Season OT notification style. Options are:

        `True` - All Overtime Period start notifications will be enabled.
        `False` - All Overtime Period start notifications will be disabled.
        """
        if on_off:
            await self.config.guild(ctx.guild).ot_notifications.clear()
            # Deftault is True
            reply = _("Overtime Period Notifications: **Enabled**\n\n")
            await ctx.maybe_send_embed(reply)
        else:
            await self.config.guild(ctx.guild).ot_notifications.set(on_off)
            await ctx.maybe_send_embed(
                _("Okay, I will not mention Overtime Period start in this server.")
            )

    @hockey_notifications.command(
        name="shootout", aliases=["so", "sonotifications"], with_app_command=False
    )
    @commands.mod_or_permissions(manage_roles=True)
    async def set_so_notification_style(self, ctx: commands.Context, on_off: bool) -> None:
        """
        Set the servers Shootout notification style. Options are:

        `True` - All Shootout Period start notifications will be enabled.
        `False` - All Shootout Period start notifications will be disabled.
        """
        if on_off:
            await self.config.guild(ctx.guild).so_notifications.clear()
            # Deftault is True
            reply = _("Shootout Period Notifications: **On**\n\n")
            await ctx.maybe_send_embed(reply)
        else:
            await self.config.guild(ctx.guild).so_notifications.set(on_off)
            await ctx.maybe_send_embed(
                _("Okay, I will not notify Shootout Period start in this server.")
            )
