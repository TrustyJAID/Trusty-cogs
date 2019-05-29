import discord
import logging
import asyncio
import re

from multiprocessing.pool import Pool
from typing import Union, Optional


from redbot.core import commands, checks, Config
from redbot.core.i18n import Translator, cog_i18n
from redbot.core.utils.predicates import ReactionPredicate
from redbot.core.utils.menus import menu, DEFAULT_CONTROLS, start_adding_reactions
from redbot.core.utils.chat_formatting import humanize_list

from .converters import (
    Trigger,
    TriggerExists,
    ValidRegex,
    MultiResponse,
    ValidEmoji,
    ChannelUserRole,
)
from .triggerhandler import TriggerHandler


log = logging.getLogger("red.trusty-cogs.ReTrigger")
_ = Translator("ReTrigger", __file__)


@cog_i18n(_)
class ReTrigger(TriggerHandler, commands.Cog):
    """
        Trigger bot events using regular expressions
    """

    __author__ = "TrustyJAID"
    __version__ = "2.7.3"

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, 964565433247)
        default_guild = {
            "trigger_list": {},
            "allow_multiple": False,
            "modlog": "default",
            "ban_logs": False,
            "kick_logs": False,
            "add_role_logs": False,
            "remove_role_logs": False,
            "filter_logs": False,
            "bypass": False,
        }
        self.config.register_guild(**default_guild)
        self.re_pool = Pool(maxtasksperchild=2)
        self.triggers = {}
        self.save_triggers = self.bot.loop.create_task(self.save_loop())
        self.__unload = self.cog_unload

    def cog_unload(self):
        log.debug("Closing process pools.")
        self.re_pool.close()
        self.bot.loop.run_in_executor(None, self.re_pool.join)
        self.save_triggers.cancel()

    async def initialize(self):
        data = await self.config.all_guilds()
        for guild, settings in data.items():
            self.triggers[guild] = []
            for trigger in settings["trigger_list"].values():
                self.triggers[guild].append(await Trigger.from_json(trigger))

    async def save_loop(self):
        await self.bot.wait_until_ready()
        while self is self.bot.get_cog("ReTrigger"):
            for guild_id, triggers in self.triggers.items():
                guild = self.bot.get_guild(guild_id)
                if not guild:
                    continue
                async with self.config.guild(guild).trigger_list() as trigger_list:
                    for trigger in triggers:
                        try:
                            trigger_list[trigger.name]["count"] = trigger.count
                        except KeyError:
                            continue
                        await asyncio.sleep(0.1)
            await asyncio.sleep(120)

    @commands.group()
    @commands.guild_only()
    async def retrigger(self, ctx: commands.Context):
        """
            Setup automatic triggers based on regular expressions

            https://regex101.com/ is a good place to test regex
        """
        pass

    @retrigger.group()
    @checks.mod_or_permissions(manage_messages=True)
    async def blacklist(self, ctx: commands.Context):
        """
            Set blacklist options for retrigger

            blacklisting supports channels, users, or roles
        """
        pass

    @retrigger.group()
    @checks.mod_or_permissions(manage_messages=True)
    async def whitelist(self, ctx: commands.Context):
        """
            Set whitelist options for retrigger

            whitelisting supports channels, users, or roles
        """
        pass

    @retrigger.group(name="modlog")
    @checks.mod_or_permissions(manage_channels=True)
    async def _modlog(self, ctx: commands.Context):
        """
            Set which events to record in the modlog.
        """
        pass

    @retrigger.group(name="edit")
    @checks.mod_or_permissions(manage_channels=True)
    async def _edit(self, ctx: commands.Context):
        """
            Edit various settings in a set trigger.

            Note: Only the server owner, Bot owner, or original
            author can edit a saved trigger. Multi triggers
            cannot be edited.
        """
        pass

    @_modlog.command(name="settings", aliases=["list"])
    async def modlog_settings(self, ctx: commands.Context):
        """
            Show the current modlog settings for this server.
        """
        guild_data = await self.config.guild(ctx.guild).all()
        variables = {
            "ban_logs": _("Bans"),
            "kick_logs": _("Kicks"),
            "add_role_logs": _("Add Roles"),
            "remove_role_logs": _("Remove Roles"),
            "filter_logs": _("Filtered Messages"),
            "modlog": _("Channel"),
        }
        msg = ""
        for log, name in variables.items():
            msg += f"__**{name}**__: {guild_data[log]}\n"
        await ctx.maybe_send_embed(msg)

    @_modlog.command(name="bans", aliases=["ban"])
    @checks.mod_or_permissions(manage_channels=True)
    async def modlog_bans(self, ctx: commands.Context):
        """
            Toggle custom ban messages in the modlog
        """
        if await self.config.guild(ctx.guild).ban_logs():
            await self.config.guild(ctx.guild).ban_logs.set(False)
            msg = _("Custom ban events disabled.")
            # await ctx.send(msg)
        else:
            await self.config.guild(ctx.guild).ban_logs.set(True)
            msg = _("Custom ban events will now appear in the modlog if it's setup.")
        await ctx.send(msg)

    @_modlog.command(name="kicks", aliases=["kick"])
    @checks.mod_or_permissions(manage_channels=True)
    async def modlog_kicks(self, ctx: commands.Context):
        """
            Toggle custom kick messages in the modlog
        """
        if await self.config.guild(ctx.guild).kick_logs():
            await self.config.guild(ctx.guild).kick_logs.set(False)
            msg = _("Custom kick events disabled.")
            # await ctx.send(msg)
        else:
            await self.config.guild(ctx.guild).kick_logs.set(True)
            msg = _("Custom kick events will now appear in the modlog if it's setup.")
        await ctx.send(msg)

    @_modlog.command(name="filter", aliases=["delete", "filters", "deletes"])
    @checks.mod_or_permissions(manage_channels=True)
    async def modlog_filter(self, ctx: commands.Context):
        """
            Toggle custom filter messages in the modlog
        """
        if await self.config.guild(ctx.guild).filter_logs():
            await self.config.guild(ctx.guild).filter_logs.set(False)
            msg = _("Custom filter events disabled.")
            # await ctx.send(msg)
        else:
            await self.config.guild(ctx.guild).filter_logs.set(True)
            msg = _("Custom filter events will now appear in the modlog if it's setup.")
        await ctx.send(msg)

    @_modlog.command(name="addroles", aliases=["addrole"])
    @checks.mod_or_permissions(manage_channels=True)
    async def modlog_addroles(self, ctx: commands.Context):
        """
            Toggle custom add role messages in the modlog
        """
        if await self.config.guild(ctx.guild).add_role_logs():
            await self.config.guild(ctx.guild).add_role_logs.set(False)
            msg = _("Custom add role events disabled.")
            # await ctx.send(msg)
        else:
            await self.config.guild(ctx.guild).add_role_logs.set(True)
            msg = _("Custom add role events will now appear in the modlog if it's setup.")
        await ctx.send(msg)

    @_modlog.command(name="removeroles", aliases=["removerole", "remrole", "rolerem"])
    @checks.mod_or_permissions(manage_channels=True)
    async def modlog_removeroles(self, ctx: commands.Context):
        """
            Toggle custom add role messages in the modlog
        """
        if await self.config.guild(ctx.guild).remove_role_logs():
            await self.config.guild(ctx.guild).remove_role_logs.set(False)
            msg = _("Custom remove role events disabled.")
            # await ctx.send(msg)
        else:
            await self.config.guild(ctx.guild).remove_role_logs.set(True)
            msg = _("Custom remove role events will now appear in the modlog if it's setup.")
        await ctx.send(msg)

    @_modlog.command(name="channel")
    @checks.mod_or_permissions(manage_channels=True)
    async def modlog_channel(
        self, ctx: commands.Context, channel: Union[discord.TextChannel, str, None]
    ):
        """
            Set the modlog channel for filtered words

            `<channel>` The channel you would like filtered word notifications to go
            Use `none` or `clear` to not show any modlogs
            User `default` to use the built in modlog channel
        """
        if isinstance(channel, discord.TextChannel):
            await self.config.guild(ctx.guild).modlog.set(channel.id)
        else:
            if channel in ["none", "clear"]:
                channel = None
            elif channel in ["default"]:
                channel = "default"
            else:
                await ctx.send(_('Channel "{channel}" not found.').format(channel=channel))
                return
            await self.config.guild(ctx.guild).modlog.set(channel)
        await ctx.send(_("Modlog set to {channel}").format(channel=channel))

    @retrigger.command()
    @checks.mod_or_permissions(manage_messages=True)
    async def cooldown(
        self, ctx: commands.Context, trigger: TriggerExists, time: int, style="guild"
    ):
        """
            Set cooldown options for retrigger

            `<trigger>` is the name of the trigger
            `<time>` is a time in seconds until the trigger will run again
            set a time of 0 or less to remove the cooldown
            `[style=guild]` must be either `guild`, `server`, `channel`, `user`, or `member`
        """
        if type(trigger) is str:
            return await ctx.send(_("Trigger `{name}` doesn't exist.").format(name=trigger))
        if style not in ["guild", "server", "channel", "user", "member"]:
            msg = _("Style must be either `guild`, " "`server`, `channel`, `user`, or `member`.")
            await ctx.send(msg)
            return
        msg = _("Cooldown of {time}s per {style} set for Trigger `{name}`.")
        if style in ["user", "member"]:
            style = "author"
        if style in ["guild", "server"]:
            cooldown = {"time": time, "style": style, "last": 0}
        else:
            cooldown = {"time": time, "style": style, "last": []}
        if time <= 0:
            cooldown = {}
            msg = _("Cooldown for Trigger `{name}` reset.")
        trigger_list = await self.config.guild(ctx.guild).trigger_list()
        trigger.cooldown = cooldown
        trigger_list[trigger.name] = await trigger.to_json()
        await self.remove_trigger_from_cache(ctx.guild, trigger)
        self.triggers[ctx.guild.id].append(trigger)
        await self.config.guild(ctx.guild).trigger_list.set(trigger_list)
        await ctx.send(msg.format(time=time, style=style, name=trigger.name))

    @whitelist.command(name="add")
    @checks.mod_or_permissions(manage_messages=True)
    async def whitelist_add(
        self, ctx: commands.Context, trigger: TriggerExists, *channel_user_role: ChannelUserRole
    ):
        """
            Add a channel, user, or role to triggers whitelist

            `<trigger>` is the name of the trigger
            `[channel_user_role...]` is the channel, user or role to whitelist
            (You can supply more than one of any at a time)
        """
        if type(trigger) is str:
            return await ctx.send(_("Trigger `{name}` doesn't exist.").format(name=trigger))
        if len(channel_user_role) < 1:
            return await ctx.send(
                _("You must supply 1 or more channels users or roles to be whitelisted.")
            )
        for obj in channel_user_role:
            if obj.id not in trigger.whitelist:
                async with self.config.guild(ctx.guild).trigger_list() as trigger_list:
                    trigger.whitelist.append(obj.id)
                    trigger_list[trigger.name] = await trigger.to_json()
        await self.remove_trigger_from_cache(ctx.guild, trigger)
        self.triggers[ctx.guild.id].append(trigger)
        msg = _("Trigger {name} added `{list_type}` to its whitelist.")
        list_type = humanize_list([c.name for c in channel_user_role])
        await ctx.send(msg.format(list_type=list_type, name=trigger.name))

    @whitelist.command(name="remove", aliases=["rem", "del"])
    @checks.mod_or_permissions(manage_messages=True)
    async def whitelist_remove(
        self, ctx: commands.Context, trigger: TriggerExists, *channel_user_role: ChannelUserRole
    ):
        """
            Remove a channel, user, or role from triggers whitelist

            `<trigger>` is the name of the trigger
            `[channel_user_role...]` is the channel, user or role to remove from the whitelist
            (You can supply more than one of any at a time)
        """
        if type(trigger) is str:
            return await ctx.send(_("Trigger `{name}` doesn't exist.").format(name=trigger))
        if len(channel_user_role) < 1:
            return await ctx.send(
                _(
                    "You must supply 1 or more channels users "
                    "or roles to be removed from the whitelist"
                )
            )
        for obj in channel_user_role:
            if obj.id in trigger.whitelist:
                async with self.config.guild(ctx.guild).trigger_list() as trigger_list:
                    trigger.whitelist.remove(obj.id)
                    trigger_list[trigger.name] = await trigger.to_json()
        await self.remove_trigger_from_cache(ctx.guild, trigger)
        self.triggers[ctx.guild.id].append(trigger)
        msg = _("Trigger {name} removed `{list_type}` from its whitelist.")
        list_type = humanize_list([c.name for c in channel_user_role])
        await ctx.send(msg.format(list_type=list_type, name=trigger.name))

    @blacklist.command(name="add")
    @checks.mod_or_permissions(manage_messages=True)
    async def blacklist_add(
        self, ctx: commands.Context, trigger: TriggerExists, *channel_user_role: ChannelUserRole
    ):
        """
            Add a channel, user, or role to triggers blacklist

            `<trigger>` is the name of the trigger
            `[channel_user_role...]` is the channel, user or role to blacklist
            (You can supply more than one of any at a time)
        """
        if type(trigger) is str:
            return await ctx.send(_("Trigger `{name}` doesn't exist.").format(name=trigger))
        if len(channel_user_role) < 1:
            return await ctx.send(
                _("You must supply 1 or more channels users or roles to be blacklisted.")
            )
        for obj in channel_user_role:
            if obj.id not in trigger.blacklist:
                async with self.config.guild(ctx.guild).trigger_list() as trigger_list:
                    trigger.blacklist.append(obj.id)
                    trigger_list[trigger.name] = await trigger.to_json()
        await self.remove_trigger_from_cache(ctx.guild, trigger)
        self.triggers[ctx.guild.id].append(trigger)
        msg = _("Trigger {name} added `{list_type}` to its blacklist.")
        list_type = humanize_list([c.name for c in channel_user_role])
        await ctx.send(msg.format(list_type=list_type, name=trigger.name))

    @blacklist.command(name="remove", aliases=["rem", "del"])
    @checks.mod_or_permissions(manage_messages=True)
    async def blacklist_remove(
        self, ctx: commands.Context, trigger: TriggerExists, *channel_user_role: ChannelUserRole
    ):
        """
            Remove a channel, user, or role from triggers blacklist

            `<trigger>` is the name of the trigger
            `[channel_user_role...]` is the channel, user or role to remove from the blacklist
            (You can supply more than one of any at a time)
        """
        if type(trigger) is str:
            return await ctx.send(_("Trigger `{name}` doesn't exist.").format(name=trigger))
        if len(channel_user_role) < 1:
            return await ctx.send(
                _(
                    "You must supply 1 or more channels users or "
                    "roles to be removed from the blacklist."
                )
            )
        for obj in channel_user_role:
            if obj.id in trigger.blacklist:
                async with self.config.guild(ctx.guild).trigger_list() as trigger_list:
                    trigger.blacklist.remove(obj.id)
                    trigger_list[trigger.name] = await trigger.to_json()
        await self.remove_trigger_from_cache(ctx.guild, trigger)
        self.triggers[ctx.guild.id].append(trigger)
        msg = _("Trigger {name} removed `{list_type}` from its blacklist.")
        list_type = humanize_list([c.name for c in channel_user_role])
        await ctx.send(msg.format(list_type=list_type, name=trigger.name))

    @_edit.command(name="regex")
    @checks.mod_or_permissions(manage_messages=True)
    async def edit_regex(
        self, ctx: commands.Context, trigger: TriggerExists, *, regex: ValidRegex
    ):
        """
            Edit the regex of a saved trigger.

            `<trigger>` is the name of the trigger
            `<regex>` The new regex pattern to use.
        """
        if type(trigger) is str:
            return await ctx.send(_("Trigger `{name}` doesn't exist.").format(name=trigger))
        if not await self.can_edit(ctx.author, trigger):
            return await ctx.send(_("You are not authorized to edit this trigger."))
        trigger.regex = re.compile(regex)
        async with self.config.guild(ctx.guild).trigger_list() as trigger_list:
            trigger_list[trigger.name] = await trigger.to_json()
        await self.remove_trigger_from_cache(ctx.guild, trigger)
        self.triggers[ctx.guild.id].append(trigger)
        msg = _("Trigger {name} regex changed to ```bf\n{regex}\n```")
        await ctx.send(msg.format(name=trigger.name, regex=regex))

    @_edit.command(name="text", aliases=["msg"])
    @checks.mod_or_permissions(manage_messages=True)
    async def edit_text(
        self, ctx: commands.Context, trigger: TriggerExists, *, text: str
    ):
        """
            Edit the text of a saved trigger.

            `<trigger>` is the name of the trigger
            `<text>` The new regex pattern to use.
        """
        if type(trigger) is str:
            return await ctx.send(_("Trigger `{name}` doesn't exist.").format(name=trigger))
        if not await self.can_edit(ctx.author, trigger):
            return await ctx.send(_("You are not authorized to edit this trigger."))
        if trigger.multi_payload:
            return await ctx.send(_("You cannot edit multi triggers response."))
        if "text" not in trigger.response_type:
            return await ctx.send(_("That trigger cannot be edited this way."))
        trigger.text = text
        async with self.config.guild(ctx.guild).trigger_list() as trigger_list:
            trigger_list[trigger.name] = await trigger.to_json()
        await self.remove_trigger_from_cache(ctx.guild, trigger)
        self.triggers[ctx.guild.id].append(trigger)
        msg = _("Trigger {name} text changed to `{text}`")
        await ctx.send(msg.format(name=trigger.name, text=text))

    @_edit.command(name="ignorecommands")
    @checks.mod_or_permissions(manage_messages=True)
    async def edit_ignore_commands(
        self, ctx: commands.Context, trigger: TriggerExists
    ):
        """
            Toggle the trigger ignoring command messages entirely.

            `<trigger>` is the name of the trigger
        """
        if type(trigger) is str:
            return await ctx.send(_("Trigger `{name}` doesn't exist.").format(name=trigger))
        if not await self.can_edit(ctx.author, trigger):
            return await ctx.send(_("You are not authorized to edit this trigger."))
        trigger.ignore_commands = not trigger.ignore_commands
        async with self.config.guild(ctx.guild).trigger_list() as trigger_list:
            trigger_list[trigger.name] = await trigger.to_json()
        await self.remove_trigger_from_cache(ctx.guild, trigger)
        self.triggers[ctx.guild.id].append(trigger)
        msg = _("Trigger {name} ignoring commands set to `{text}`")
        await ctx.send(msg.format(name=trigger.name, text=trigger.ignore_commands))

    @_edit.command(name="command", aliases=["cmd"])
    @checks.mod_or_permissions(manage_messages=True)
    async def edit_command(
        self, ctx: commands.Context, trigger: TriggerExists, *, command: str
    ):
        """
            Edit the text of a saved trigger.

            `<trigger>` is the name of the trigger.
            `<command>` The new command for the trigger.
        """
        if type(trigger) is str:
            return await ctx.send(_("Trigger `{name}` doesn't exist.").format(name=trigger))
        if not await self.can_edit(ctx.author, trigger):
            return await ctx.send(_("You are not authorized to edit this trigger."))
        if trigger.multi_payload:
            return await ctx.send(_("You cannot edit multi triggers response."))
        cmd_list = command.split(" ")
        existing_cmd = self.bot.get_command(cmd_list[0])
        if existing_cmd is None:
            await ctx.send(command + _(" doesn't seem to be an available command."))
            return
        if "command" not in trigger.response_type:
            return await ctx.send(_("That trigger cannot be edited this way."))
        trigger.text = command
        async with self.config.guild(ctx.guild).trigger_list() as trigger_list:
            trigger_list[trigger.name] = await trigger.to_json()
        await self.remove_trigger_from_cache(ctx.guild, trigger)
        self.triggers[ctx.guild.id].append(trigger)
        msg = _("Trigger {name} command changed to `{command}`")
        await ctx.send(msg.format(name=trigger.name, command=command))

    @_edit.command(name="role", aliases=["roles"])
    @checks.mod_or_permissions(manage_roles=True)
    async def edit_roles(
        self, ctx: commands.Context, trigger: TriggerExists, *roles: discord.Role
    ):
        """
            Edit the added or removed roles of a saved trigger.

            `<trigger>` is the name of the trigger.
            `<roles>` space separated list of roles or ID's to edit on the trigger.
        """
        if type(trigger) is str:
            return await ctx.send(_("Trigger `{name}` doesn't exist.").format(name=trigger))
        if not await self.can_edit(ctx.author, trigger):
            return await ctx.send(_("You are not authorized to edit this trigger."))
        if trigger.multi_payload:
            return await ctx.send(_("You cannot edit multi triggers response."))
        for role in roles:
            if role >= ctx.me.top_role:
                return await ctx.send(_("I can't assign roles higher than my own."))
            if role >= ctx.author.top_role:
                return await ctx.send(
                    _("I can't assign roles higher than you are able to assign.")
                )
        role_ids = [r.id for r in roles]
        if not any([t for t in trigger.response_type if t in ["add_role", "remove_role"]]):
            return await ctx.send(_("That trigger cannot be edited this way."))
        trigger.text = role_ids
        async with self.config.guild(ctx.guild).trigger_list() as trigger_list:
            trigger_list[trigger.name] = await trigger.to_json()
        await self.remove_trigger_from_cache(ctx.guild, trigger)
        self.triggers[ctx.guild.id].append(trigger)
        msg = _("Trigger {name} role edits changed to `{roles}`")
        await ctx.send(msg.format(name=trigger.name, roles=humanize_list([r.name for r in roles])))

    @_edit.command(name="react", aliases=["emojis"])
    @checks.mod_or_permissions(manage_messages=True)
    async def edit_reactions(
        self, ctx: commands.Context, trigger: TriggerExists, *emojis: ValidEmoji
    ):
        """
            Edit the emoji reactions of a saved trigger.

            `<trigger>` is the name of the trigger.
            `<emojis>` The new emojis to be used in the trigger.
        """
        if type(trigger) is str:
            return await ctx.send(_("Trigger `{name}` doesn't exist.").format(name=trigger))
        if not await self.can_edit(ctx.author, trigger):
            return await ctx.send(_("You are not authorized to edit this trigger."))
        if "react" not in trigger.response_type:
            return await ctx.send(_("That trigger cannot be edited this way."))
        trigger.text = emojis
        async with self.config.guild(ctx.guild).trigger_list() as trigger_list:
            trigger_list[trigger.name] = await trigger.to_json()
        await self.remove_trigger_from_cache(ctx.guild, trigger)
        self.triggers[ctx.guild.id].append(trigger)
        msg = _("Trigger {name} reactions changed to {emojis}")
        emoji_s = [f"<{e}>" for e in emojis if len(e) > 5] + [e for e in emojis if len(e) < 5]
        await ctx.send(msg.format(name=trigger.name, emojis=humanize_list(emoji_s)))

    @retrigger.command(hidden=True)
    @checks.is_owner()
    async def bypass(self, ctx: commands.Context, bypass: bool):
        """Bypass patterns being kicked from memory until reload"""
        msg = await ctx.send(
            _(
                "Bypassing this could cause the bot to become unstable or allow "
                "bad regex patterns to continue to exist causing slow downs and "
                "even fatal crashes on the bot. Do you wish to continue?"
            )
        )
        start_adding_reactions(msg, ReactionPredicate.YES_OR_NO_EMOJIS)
        pred = ReactionPredicate.yes_or_no(msg, user=ctx.author)
        try:
            await ctx.bot.wait_for("reaction_add", check=pred, timeout=30)
        except asyncio.TimeoutError:
            return await ctx.send(_("Not bypassing regex pattern filtering."))
        if pred.result:
            await self.config.guild(ctx.guild).bypass.set(bypass)
            await ctx.tick()
        else:
            await ctx.send(_("Not bypassing regex pattern filtering."))

    @retrigger.command()
    async def list(self, ctx: commands.Context, trigger: TriggerExists = None):
        """
            List information about triggers

            `[trigger]` if supplied provides information about named trigger
        """
        trigger_dict = await self.config.guild(ctx.guild).trigger_list()
        trigger_list = [trigger_dict[name] for name in trigger_dict]
        if trigger_list == []:
            msg = _("There are no triggers setup on this server.")
            await ctx.send(msg)
            return
        if trigger:
            if type(trigger) is str:
                return await ctx.send(_("Trigger `{name}` doesn't exist.").format(name=trigger))
            for t in trigger_list:
                if t["name"] == trigger.name:
                    trigger_list.insert(0, trigger_list.pop(trigger_list.index(t)))
        triggers = await self.trigger_embed(ctx, trigger_list)
        await menu(ctx, triggers, DEFAULT_CONTROLS)

    @retrigger.command(aliases=["del", "rem", "delete"])
    @checks.mod_or_permissions(manage_messages=True)
    async def remove(self, ctx: commands.Context, trigger: TriggerExists):
        """
            Remove a specified trigger

            `<trigger>` is the name of the trigger
        """
        if type(trigger) is Trigger:
            await self.remove_trigger(ctx.guild, trigger.name)
            await self.remove_trigger_from_cache(ctx.guild, trigger)
            await ctx.send(_("Trigger `") + trigger.name + _("` removed."))
        else:
            await ctx.send(_("Trigger `") + str(trigger) + _("` doesn't exist."))

    @retrigger.command()
    @checks.mod_or_permissions(manage_messages=True)
    async def text(
        self, ctx: commands.Context, name: TriggerExists, regex: ValidRegex, *, text: str
    ):
        """
            Add a text response trigger

            `<name>` name of the trigger
            `<regex>` the regex that will determine when to respond
            `<text>` response of the trigger
            Text responses utilize regex groups for replacement so you can
            replace a group match in a specific area with `{#}`
            e.g. `[p]retrigger text tracer "(?i)(^I wanna be )([^.]*)" I'm already {2}`
            will replace the `{2}` in the text with the second capture group.
            See https://regex101.com/ for help building a regex pattern
            Example for simple search: `"\\bthis matches"` the whole phrase only
            For case insensitive searches add `(?i)` at the start of the regex
        """
        if type(name) != str:
            msg = _("{name} is already a trigger name").format(name=name.name)
            return await ctx.send(msg)
        guild = ctx.guild
        author = ctx.message.author.id
        new_trigger = Trigger(
            name, regex, ["text"], author, 0, None, text, [], [], {}, [], ctx.message.id
        )
        if ctx.guild.id not in self.triggers:
            self.triggers[ctx.guild.id] = []
        self.triggers[ctx.guild.id].append(new_trigger)
        trigger_list = await self.config.guild(guild).trigger_list()
        trigger_list[name] = await new_trigger.to_json()
        await self.config.guild(guild).trigger_list.set(trigger_list)
        await ctx.send(_("Trigger `{name}` set.").format(name=name))

    @retrigger.command(aliases=["randomtext", "rtext"])
    @checks.mod_or_permissions(manage_messages=True)
    async def random(self, ctx: commands.Context, name: TriggerExists, regex: ValidRegex):
        """
            Add a random text response trigger

            `<name>` name of the trigger
            `<regex>` the regex that will determine when to respond
            See https://regex101.com/ for help building a regex pattern
            Example for simple search: `"\\bthis matches"` the whole phrase only
            For case insensitive searches add `(?i)` at the start of the regex
        """
        if type(name) != str:
            msg = _("{name} is already a trigger name").format(name=name.name)
            return await ctx.send(msg)
        text = await self.wait_for_multiple_responses(ctx)
        if not text:
            await ctx.send(_("No responses supplied"))
            return
        guild = ctx.guild
        author = ctx.message.author.id
        new_trigger = Trigger(
            name, regex, ["randtext"], author, 0, None, text, [], [], {}, [], ctx.message.id
        )
        if ctx.guild.id not in self.triggers:
            self.triggers[ctx.guild.id] = []
        self.triggers[ctx.guild.id].append(new_trigger)
        trigger_list = await self.config.guild(guild).trigger_list()
        trigger_list[name] = await new_trigger.to_json()
        await self.config.guild(guild).trigger_list.set(trigger_list)
        await ctx.send(_("Trigger `{name}` set.").format(name=name))

    @retrigger.command()
    @checks.mod_or_permissions(manage_messages=True)
    async def dm(
        self, ctx: commands.Context, name: TriggerExists, regex: ValidRegex, *, text: str
    ):
        """
            Add a dm response trigger

            `<name>` name of the trigger
            `<regex>` the regex that will determine when to respond
            `<text>` response of the trigger
            Text responses utilize regex groups for replacement so you can
            replace a group match in a specific area with `{#}`
            e.g. `[p]retrigger text tracer "(?i)(^I wanna be )([^.]*)" I'm already {2}`
            will replace the `{2}` in the text with the second capture group.
            See https://regex101.com/ for help building a regex pattern
            Example for simple search: `"\\bthis matches"` the whole phrase only
            For case insensitive searches add `(?i)` at the start of the regex
        """
        if type(name) != str:
            msg = _("{name} is already a trigger name").format(name=name.name)
            return await ctx.send(msg)
        guild = ctx.guild
        author = ctx.message.author.id
        new_trigger = Trigger(
            name, regex, ["dm"], author, 0, None, text, [], [], {}, [], ctx.message.id
        )
        if ctx.guild.id not in self.triggers:
            self.triggers[ctx.guild.id] = []
        self.triggers[ctx.guild.id].append(new_trigger)
        trigger_list = await self.config.guild(guild).trigger_list()
        trigger_list[name] = await new_trigger.to_json()
        await self.config.guild(guild).trigger_list.set(trigger_list)
        await ctx.send(_("Trigger `{name}` set.").format(name=name))

    @retrigger.command()
    @checks.mod_or_permissions(manage_messages=True)
    @commands.bot_has_permissions(attach_files=True)
    async def image(
        self, ctx: commands.Context, name: TriggerExists, regex: ValidRegex, image_url: str = None
    ):
        """
            Add an image/file response trigger

            `<name>` name of the trigger
            `<regex>` the regex that will determine when to respond
            `image_url` optional image_url if none is provided the bot will ask to upload an image
            See https://regex101.com/ for help building a regex pattern
            Example for simple search: `"\\bthis matches"` the whole phrase only
            For case insensitive searches add `(?i)` at the start of the regex
        """
        if type(name) != str:
            msg = _("{name} is already a trigger name").format(name=name.name)
            return await ctx.send(msg)
        guild = ctx.guild
        author = ctx.message.author.id
        if ctx.message.attachments != []:
            attachment_url = ctx.message.attachments[0].url
            filename = await self.save_image_location(attachment_url, guild)
            if not filename:
                return await ctx.send(
                    _("That is not a valid file link.")
                )
        if image_url is not None:
            filename = await self.save_image_location(image_url, guild)
            if not filename:
                return await ctx.send(
                    _("That is not a valid file link.")
                )
        else:
            msg = await self.wait_for_image(ctx)
            if not msg or not msg.attachments:
                return
            image_url = msg.attachments[0].url
            filename = await self.save_image_location(image_url, guild)

        new_trigger = Trigger(
            name, regex, ["image"], author, 0, filename, None, [], [], {}, [], ctx.message.id
        )
        if ctx.guild.id not in self.triggers:
            self.triggers[ctx.guild.id] = []
        self.triggers[ctx.guild.id].append(new_trigger)
        trigger_list = await self.config.guild(guild).trigger_list()
        trigger_list[name] = await new_trigger.to_json()
        await self.config.guild(guild).trigger_list.set(trigger_list)
        await ctx.send(_("Trigger `{name}` set.").format(name=name))

    @retrigger.command(aliases=["randimage", "randimg", "rimage", "rimg"])
    @checks.mod_or_permissions(manage_messages=True)
    @commands.bot_has_permissions(attach_files=True)
    async def randomimage(self, ctx: commands.Context, name: TriggerExists, regex: ValidRegex):
        """
            Add a random image/file response trigger

            `<name>` name of the trigger
            `<regex>` the regex that will determine when to respond
            See https://regex101.com/ for help building a regex pattern
            Example for simple search: `"\\bthis matches"` the whole phrase only
            For case insensitive searches add `(?i)` at the start of the regex
        """
        if type(name) != str:
            msg = _("{name} is already a trigger name").format(name=name.name)
            return await ctx.send(msg)
        guild = ctx.guild
        author = ctx.message.author.id
        filename = await self.wait_for_multiple_images(ctx)

        new_trigger = Trigger(
            name, regex, ["randimage"], author, 0, filename, None, [], [], {}, [], ctx.message.id
        )
        if ctx.guild.id not in self.triggers:
            self.triggers[ctx.guild.id] = []
        self.triggers[ctx.guild.id].append(new_trigger)
        trigger_list = await self.config.guild(guild).trigger_list()
        trigger_list[name] = await new_trigger.to_json()
        await self.config.guild(guild).trigger_list.set(trigger_list)
        await ctx.send(_("Trigger `{name}` set.").format(name=name))

    @retrigger.command()
    @checks.mod_or_permissions(manage_messages=True)
    @commands.bot_has_permissions(attach_files=True)
    async def imagetext(
        self,
        ctx: commands.Context,
        name: TriggerExists,
        regex: ValidRegex,
        text: str,
        image_url: str = None,
    ):
        """
            Add an image/file response with text trigger

            `<name>` name of the trigger
            `<regex>` the regex that will determine when to respond
            `<text>` the triggered text response
            `[image_url]` optional image_url if none is provided the bot will ask to
            upload an image Text responses utilize regex groups for replacement so you can
            replace a group match in a specific area with `{#}`
            e.g. `[p]retrigger text tracer "(?i)(^I wanna be )([^.]*)" I'm already {2}`
            will replace the `{2}` in the text with the second capture group.
            See https://regex101.com/ for help building a regex pattern
            Example for simple search: `"\\bthis matches"` the whole phrase only
            For case insensitive searches add `(?i)` at the start of the regex
        """
        if type(name) != str:
            msg = _("{name} is already a trigger name").format(name=name.name)
            return await ctx.send(msg)
        guild = ctx.guild
        author = ctx.message.author.id
        if ctx.message.attachments != []:
            attachment_url = ctx.message.attachments[0].url
            filename = await self.save_image_location(attachment_url, guild)
        if image_url is not None:
            filename = await self.save_image_location(image_url, guild)
        else:
            msg = await self.wait_for_image(ctx)
            if not msg or not msg.attachments:
                return
            image_url = msg.attachments[0].url
            filename = await self.save_image_location(image_url, guild)

        new_trigger = Trigger(
            name, regex, ["image"], author, 0, filename, text, [], [], {}, [], ctx.message.id
        )
        if ctx.guild.id not in self.triggers:
            self.triggers[ctx.guild.id] = []
        self.triggers[ctx.guild.id].append(new_trigger)
        trigger_list = await self.config.guild(guild).trigger_list()
        trigger_list[name] = await new_trigger.to_json()
        await self.config.guild(guild).trigger_list.set(trigger_list)
        await ctx.send(_("Trigger `{name}` set.").format(name=name))

    @retrigger.command()
    @checks.mod_or_permissions(manage_messages=True)
    @commands.bot_has_permissions(attach_files=True)
    @commands.check(lambda ctx: TriggerHandler.ALLOW_RESIZE)
    async def resize(
        self, ctx: commands.Context, name: TriggerExists, regex: ValidRegex, image_url: str = None
    ):
        """
            Add an image to resize in response to a trigger
            this will attempt to resize the image based on length of matching regex

            `<name>` name of the trigger
            `<regex>` the regex that will determine when to respond
            `[image_url]` optional image_url if none is provided
            the bot will ask to upload an image
            See https://regex101.com/ for help building a regex pattern
            Example for simple search: `"\\bthis matches"` the whole phrase only
            For case insensitive searches add `(?i)` at the start of the regex
        """
        if type(name) != str:
            msg = _("{name} is already a trigger name").format(name=name.name)
            return await ctx.send(msg)
        guild = ctx.guild
        author = ctx.message.author.id
        if ctx.message.attachments != []:
            attachment_url = ctx.message.attachments[0].url
            filename = await self.save_image_location(attachment_url, guild)
        if image_url is not None:
            filename = await self.save_image_location(image_url, guild)
        else:
            msg = await self.wait_for_image(ctx)
            if not msg or not msg.attachments:
                return
            image_url = msg.attachments[0].url
            filename = await self.save_image_location(image_url, guild)

        new_trigger = Trigger(
            name, regex, ["resize"], author, 0, filename, None, [], [], {}, [], ctx.message.id
        )
        if ctx.guild.id not in self.triggers:
            self.triggers[ctx.guild.id] = []
        self.triggers[ctx.guild.id].append(new_trigger)
        trigger_list = await self.config.guild(guild).trigger_list()
        trigger_list[name] = await new_trigger.to_json()
        await self.config.guild(guild).trigger_list.set(trigger_list)
        await ctx.send(_("Trigger `{name}` set.").format(name=name))

    @retrigger.command()
    @checks.mod_or_permissions(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    async def ban(self, ctx: commands.Context, name: TriggerExists, regex: str):
        """
            Add a trigger to ban users for saying specific things found with regex
            This respects hierarchy so ensure the bot role is lower in the list
            than mods and admin so they don't get banned by accident

            `<name>` name of the trigger
            `<regex>` the regex that will determine when to respond
            See https://regex101.com/ for help building a regex pattern
            Example for simple search: `"\\bthis matches"` the whole phrase only
            For case insensitive searches add `(?i)` at the start of the regex
        """
        if type(name) != str:
            msg = _("{name} is already a trigger name").format(name=name.name)
            return await ctx.send(msg)
        guild = ctx.guild
        author = ctx.message.author.id
        new_trigger = Trigger(
            name, regex, ["ban"], author, 0, None, None, [], [], {}, [], ctx.message.id
        )
        if ctx.guild.id not in self.triggers:
            self.triggers[ctx.guild.id] = []
        self.triggers[ctx.guild.id].append(new_trigger)
        trigger_list = await self.config.guild(guild).trigger_list()
        trigger_list[name] = await new_trigger.to_json()
        await self.config.guild(guild).trigger_list.set(trigger_list)
        await ctx.send(_("Trigger `{name}` set.").format(name=name))

    @retrigger.command()
    @checks.mod_or_permissions(kick_members=True)
    @commands.bot_has_permissions(kick_members=True)
    async def kick(self, ctx: commands.Context, name: TriggerExists, regex: str):
        """
            Add a trigger to kick users for saying specific things found with regex
            This respects hierarchy so ensure the bot role is lower in the list
            than mods and admin so they don't get kicked by accident

            `<name>` name of the trigger
            `<regex>` the regex that will determine when to respond
            See https://regex101.com/ for help building a regex pattern
            Example for simple search: `"\\bthis matches"` the whole phrase only
            For case insensitive searches add `(?i)` at the start of the regex
        """
        if type(name) != str:
            msg = _("{name} is already a trigger name").format(name=name.name)
            return await ctx.send(msg)
        guild = ctx.guild
        author = ctx.message.author.id
        new_trigger = Trigger(
            name, regex, ["kick"], author, 0, None, None, [], [], {}, [], ctx.message.id
        )
        if ctx.guild.id not in self.triggers:
            self.triggers[ctx.guild.id] = []
        self.triggers[ctx.guild.id].append(new_trigger)
        trigger_list = await self.config.guild(guild).trigger_list()
        trigger_list[name] = await new_trigger.to_json()
        await self.config.guild(guild).trigger_list.set(trigger_list)
        await ctx.send(_("Trigger `{name}` set.").format(name=name))

    @retrigger.command()
    @checks.mod_or_permissions(manage_messages=True)
    @commands.bot_has_permissions(add_reactions=True)
    async def react(
        self, ctx: commands.Context, name: TriggerExists, regex: ValidRegex, *emojis: ValidEmoji
    ):
        """
            Add a reaction trigger

            `<name>` name of the trigger
            `<regex>` the regex that will determine when to respond
            `emojis` the emojis to react with when triggered separated by spaces
            See https://regex101.com/ for help building a regex pattern
            Example for simple search: `"\\bthis matches"` the whole phrase only
            For case insensitive searches add `(?i)` at the start of the regex
        """
        if type(name) != str:
            msg = _("{name} is already a trigger name").format(name=name.name)
            return await ctx.send(msg)
        guild = ctx.guild
        author = ctx.message.author.id
        new_trigger = Trigger(
            name, regex, ["react"], author, 0, None, emojis, [], [], {}, [], ctx.message.id
        )
        if ctx.guild.id not in self.triggers:
            self.triggers[ctx.guild.id] = []
        self.triggers[ctx.guild.id].append(new_trigger)
        trigger_list = await self.config.guild(guild).trigger_list()
        trigger_list[name] = await new_trigger.to_json()
        await self.config.guild(guild).trigger_list.set(trigger_list)
        await ctx.send(_("Trigger `{name}` set.").format(name=name))

    @retrigger.command(aliases=["cmd"])
    @checks.mod_or_permissions(manage_messages=True)
    async def command(
        self, ctx: commands.Context, name: TriggerExists, regex: ValidRegex, *, command: str
    ):
        """
            Add a command trigger

            `<name>` name of the trigger
            `<regex>` the regex that will determine when to respond
            `<command>` the command that will be triggered, do add [p] prefix
            See https://regex101.com/ for help building a regex pattern
            Example for simple search: `"\\bthis matches"` the whole phrase only
            For case insensitive searches add `(?i)` at the start of the regex
        """
        if type(name) != str:
            msg = _("{name} is already a trigger name").format(name=name.name)
            return await ctx.send(msg)
        cmd_list = command.split(" ")
        existing_cmd = self.bot.get_command(cmd_list[0])
        if existing_cmd is None:
            await ctx.send(command + _(" doesn't seem to be an available command."))
            return
        guild = ctx.guild
        author = ctx.message.author.id
        new_trigger = Trigger(
            name, regex, ["command"], author, 0, None, command, [], [], {}, [], ctx.message.id
        )
        if ctx.guild.id not in self.triggers:
            self.triggers[ctx.guild.id] = []
        self.triggers[ctx.guild.id].append(new_trigger)
        trigger_list = await self.config.guild(guild).trigger_list()
        trigger_list[name] = await new_trigger.to_json()
        await self.config.guild(guild).trigger_list.set(trigger_list)
        await ctx.send(_("Trigger `{name}` set.").format(name=name))

    @retrigger.command(aliases=["cmdmock"], hidden=True)
    @checks.admin_or_permissions(administrator=True)
    async def mock(
        self, ctx: commands.Context, name: TriggerExists, regex: ValidRegex, *, command: str
    ):
        """
            Add a trigger for command as if you used the command

            `<name>` name of the trigger
            `<regex>` the regex that will determine when to respond
            `<command>` the command that will be triggered, do add [p] prefix
            Warning: This function can let other users run a command on your behalf,
            use with caution.
        """
        msg = await ctx.send(
            _(
                "Mock commands can allow any user to run a command "
                "as if you did, are you sure you want to add this?"
            )
        )
        start_adding_reactions(msg, ReactionPredicate.YES_OR_NO_EMOJIS)
        pred = ReactionPredicate.yes_or_no(msg, ctx.author)
        try:
            await ctx.bot.wait_for("reaction_add", check=pred, timeout=15)
        except asyncio.TimeoutError:
            return await ctx.send(_("Not creating trigger."))
        if not pred.result:
            return await ctx.send(_("Not creating trigger."))
        if type(name) != str:
            msg = _("{name} is already a trigger name").format(name=name.name)
            return await ctx.send(msg)
        cmd_list = command.split(" ")
        existing_cmd = self.bot.get_command(cmd_list[0])
        if existing_cmd is None:
            await ctx.send(command + _(" doesn't seem to be an available command."))
            return
        guild = ctx.guild
        author = ctx.message.author.id
        new_trigger = Trigger(
            name, regex, ["mock"], author, 0, None, command, [], [], {}, [], ctx.message.id
        )
        if ctx.guild.id not in self.triggers:
            self.triggers[ctx.guild.id] = []
        self.triggers[ctx.guild.id].append(new_trigger)
        trigger_list = await self.config.guild(guild).trigger_list()
        trigger_list[name] = await new_trigger.to_json()
        await self.config.guild(guild).trigger_list.set(trigger_list)
        await ctx.send(_("Trigger `{name}` set.").format(name=name))

    @retrigger.command(aliases=["deletemsg"])
    @checks.mod_or_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True)
    async def filter(
        self,
        ctx: commands.Context,
        name: TriggerExists,
        check_filenames: Optional[bool] = False,
        *,
        regex: str,
    ):
        """
            Add a trigger to delete a message

            `<name>` name of the trigger
            `<regex>` the regex that will determine when to respond
            See https://regex101.com/ for help building a regex pattern
            Example for simple search: `"\\bthis matches"` the whole phrase only
            For case insensitive searches add `(?i)` at the start of the regex
        """
        if type(name) != str:
            msg = _("{name} is already a trigger name").format(name=name.name)
            return await ctx.send(msg)
        guild = ctx.guild
        author = ctx.message.author.id
        new_trigger = Trigger(
            name,
            regex,
            ["delete"],
            author,
            0,
            None,
            check_filenames,
            [],
            [],
            {},
            [],
            ctx.message.id,
        )
        if ctx.guild.id not in self.triggers:
            self.triggers[ctx.guild.id] = []
        self.triggers[ctx.guild.id].append(new_trigger)
        trigger_list = await self.config.guild(guild).trigger_list()
        trigger_list[name] = await new_trigger.to_json()
        await self.config.guild(guild).trigger_list.set(trigger_list)
        await ctx.send(_("Trigger `{name}` set.").format(name=name))

    @retrigger.command()
    @checks.mod_or_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def addrole(
        self, ctx: commands.Context, name: TriggerExists, regex: ValidRegex, *roles: discord.Role
    ):
        """
            Add a trigger to add a role

            `<name>` name of the trigger
            `<regex>` the regex that will determine when to respond
            `[role...]` the roles applied when the regex pattern matches space separated
            See https://regex101.com/ for help building a regex pattern
            Example for simple search: `"\\bthis matches"` the whole phrase only
            For case insensitive searches add `(?i)` at the start of the regex
        """
        if type(name) != str:
            msg = _("{name} is already a trigger name").format(name=name.name)
            return await ctx.send(msg)
        for role in roles:
            if role >= ctx.me.top_role:
                return await ctx.send(_("I can't assign roles higher than my own."))
            if role >= ctx.author.top_role:
                return await ctx.send(
                    _("I can't assign roles higher than you are able to assign.")
                )
        role_ids = [r.id for r in roles]
        guild = ctx.guild
        author = ctx.message.author.id
        new_trigger = Trigger(
            name, regex, ["add_role"], author, 0, None, role_ids, [], [], {}, [], ctx.message.id
        )
        if ctx.guild.id not in self.triggers:
            self.triggers[ctx.guild.id] = []
        self.triggers[ctx.guild.id].append(new_trigger)
        trigger_list = await self.config.guild(guild).trigger_list()
        trigger_list[name] = await new_trigger.to_json()
        await self.config.guild(guild).trigger_list.set(trigger_list)
        await ctx.send(_("Trigger `{name}` set.").format(name=name))

    @retrigger.command()
    @checks.mod_or_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def removerole(
        self, ctx: commands.Context, name: TriggerExists, regex: ValidRegex, *roles: discord.Role
    ):
        """
            Add a trigger to remove a role

            `<name>` name of the trigger
            `<regex>` the regex that will determine when to respond
            `[role...]` the roles applied when the regex pattern matches space separated
            See https://regex101.com/ for help building a regex pattern
            Example for simple search: `"\\bthis matches"` the whole phrase only
            For case insensitive searches add `(?i)` at the start of the regex
        """
        if type(name) != str:
            msg = _("{name} is already a trigger name").format(name=name.name)
            return await ctx.send(msg)
        for role in roles:
            if role >= ctx.me.top_role:
                return await ctx.send(_("I can't remove roles higher than my own."))
            if role >= ctx.author.top_role:
                return await ctx.send(
                    _("I can't remove roles higher than you are able to remove.")
                )
        role_ids = [r.id for r in roles]
        guild = ctx.guild
        author = ctx.message.author.id
        new_trigger = Trigger(
            name, regex, ["remove_role"], author, 0, None, role_ids, [], [], {}, [], ctx.message.id
        )
        if ctx.guild.id not in self.triggers:
            self.triggers[ctx.guild.id] = []
        self.triggers[ctx.guild.id].append(new_trigger)
        trigger_list = await self.config.guild(guild).trigger_list()
        trigger_list[name] = await new_trigger.to_json()
        await self.config.guild(guild).trigger_list.set(trigger_list)
        await ctx.send(_("Trigger `{name}` set.").format(name=name))

    @retrigger.command()
    @checks.admin_or_permissions(administrator=True)
    async def multi(
        self,
        ctx: commands.Context,
        name: TriggerExists,
        regex: ValidRegex,
        *multi_response: MultiResponse,
    ):
        """
            Add a multiple response trigger

            `<name>` name of the trigger
            `<regex>` the regex that will determine when to respond
            `[multi_response...]` the actions to perform when the trigger matches
            multiple responses start with the name of the action which must be one of:
            dm, text, filter, add_role, remove_role, ban, or kick
            followed by a `;` if there is a followup response and a space for the next
            trigger response. If you want to add or remove multiple roles those may be
            followed up with additional `;` separations.
            e.g. `[p]retrigger multi test \\btest\\b \"dm;You said a bad word!\" filter`
            Will attempt to DM the user and delete their message simultaneously.
        """
        # log.info(multi_response)
        # return
        if type(name) != str:
            msg = _("{name} is already a trigger name").format(name=name.name)
            return await ctx.send(msg)
        guild = ctx.guild
        author = ctx.message.author.id
        new_trigger = Trigger(
            name,
            regex,
            [i[0] for i in multi_response],
            author,
            0,
            None,
            None,
            [],
            [],
            {},
            multi_response,
            ctx.message.id,
        )
        if ctx.guild.id not in self.triggers:
            self.triggers[ctx.guild.id] = []
        self.triggers[ctx.guild.id].append(new_trigger)
        trigger_list = await self.config.guild(guild).trigger_list()
        trigger_list[name] = await new_trigger.to_json()
        await self.config.guild(guild).trigger_list.set(trigger_list)
        await ctx.send(_("Trigger `{name}` set.").format(name=name))
