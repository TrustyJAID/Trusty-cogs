import asyncio
import logging
from abc import ABC
from multiprocessing.pool import Pool
from pathlib import Path
from typing import Dict, Optional, Union

import discord
from discord.ext import tasks
from redbot.core import Config, checks, commands, modlog
from redbot.core.commands import TimedeltaConverter
from redbot.core.i18n import Translator, cog_i18n

# from redbot.core.utils import menus
from redbot.core.utils.chat_formatting import humanize_list, pagify
from redbot.core.utils.menus import start_adding_reactions
from redbot.core.utils.predicates import ReactionPredicate

from .converters import (
    ChannelUserRole,
    MultiResponse,
    Trigger,
    TriggerExists,
    TriggerResponse,
    ValidEmoji,
    ValidRegex,
)
from .menus import BaseMenu, ExplainReTriggerPages, ReTriggerMenu, ReTriggerPages
from .slash import ReTriggerSlash
from .triggerhandler import TriggerHandler

log = logging.getLogger("red.trusty-cogs.ReTrigger")
_ = Translator("ReTrigger", __file__)

try:
    from PIL import Image, ImageSequence

    try:
        import pytesseract

        ALLOW_OCR = True
    except ImportError:
        ALLOW_OCR = False

    ALLOW_RESIZE = True
except ImportError:
    ALLOW_RESIZE = False
    ALLOW_OCR = False

try:
    import regex as re
except ImportError:
    import re


class CompositeMetaClass(type(commands.Cog), type(ABC)):
    """
    This allows the metaclass used for proper type detection to
    coexist with discord.py's metaclass
    """

    pass


@cog_i18n(_)
@discord.app_commands.default_permissions(manage_messages=True)
@discord.app_commands.guild_only()
class ReTrigger(
    TriggerHandler,
    ReTriggerSlash,
    commands.GroupCog,
    metaclass=CompositeMetaClass,
):
    """
    Trigger bot events using regular expressions
    """

    __author__ = ["TrustyJAID"]
    __version__ = "2.21.1"

    def __init__(self, bot):
        super().__init__()
        self.bot = bot
        self.config = Config.get_conf(self, 964565433247, force_registration=True)
        self.config.register_guild(
            trigger_list={},
            allow_multiple=False,
            modlog="default",
            ban_logs=False,
            kick_logs=False,
            add_role_logs=False,
            remove_role_logs=False,
            filter_logs=False,
            bypass=False,
        )
        self.config.register_global(trigger_timeout=1, enable_slash=False)
        self.re_pool = Pool()
        self.triggers: Dict[int, Dict[str, Trigger]] = {}
        self.trigger_timeout = 1
        self.save_loop.start()
        self.ALLOW_OCR = ALLOW_OCR
        self.ALLOW_RESIZE = ALLOW_RESIZE

    def format_help_for_context(self, ctx: commands.Context) -> str:
        """
        Thanks Sinbad!
        """
        pre_processed = super().format_help_for_context(ctx)
        return f"{pre_processed}\n\nCog Version: {self.__version__}"

    async def cog_unload(self):
        if 218773382617890828 in self.bot.owner_ids:
            try:
                self.bot.remove_dev_env_value("retrigger")
            except Exception:
                log.exception("Error removing retrigger from dev environment.")
        log.debug("Closing process pools.")
        self.re_pool.close()
        loop = asyncio.get_running_loop()
        loop.run_in_executor(None, self.re_pool.join)
        self.save_loop.cancel()

    async def save_all_triggers(self):
        for guild_id, triggers in self.triggers.items():
            guild = self.bot.get_guild(guild_id)
            if not guild:
                continue
            async with self.config.guild(guild).trigger_list() as trigger_list:
                for trigger in triggers.values():
                    try:
                        trigger_list[trigger.name] = await trigger.to_json()
                    except KeyError:
                        continue
                    await asyncio.sleep(0.1)

    @tasks.loop(seconds=120)
    async def save_loop(self):
        await self.save_all_triggers()

    @save_loop.after_loop
    async def after_save_loop(self):
        if self.save_loop.is_being_cancelled():
            await self.save_all_triggers()

    @save_loop.before_loop
    async def before_save_loop(self):
        if 218773382617890828 in self.bot.owner_ids:
            # This doesn't work on bot startup but that's fine
            try:
                self.bot.add_dev_env_value("retrigger", lambda x: self)
            except Exception:
                log.error("Error adding retrigger to dev environment.")
        self.trigger_timeout = await self.config.trigger_timeout()
        data = await self.config.all_guilds()
        for guild, settings in data.items():
            self.triggers[guild] = {}
            for trigger in settings["trigger_list"].values():
                try:
                    new_trigger = await Trigger.from_json(trigger)
                except Exception:
                    log.exception("Error trying to compile regex pattern.")
                    continue
                    # I might move this to DM the author of the trigger
                    # before this becomes actually breaking
                self.triggers[guild][new_trigger.name] = new_trigger

    async def _not_authorized(self, ctx: Union[commands.Context, discord.Interaction]):
        msg = _("You are not authorized to edit this trigger.")
        if isinstance(ctx, discord.Interaction):
            if ctx.response.is_done():
                await ctx.followup.send(msg)
            else:
                await ctx.response.send_message(msg)
        else:
            await ctx.send(msg)
        return

    async def _no_multi(self, ctx: Union[commands.Context, discord.Interaction]):
        msg = _("You cannot edit multi triggers response.")
        if isinstance(ctx, discord.Interaction):
            if ctx.response.is_done():
                await ctx.followup.send(msg)
            else:
                await ctx.response.send_message(msg)
        else:
            await ctx.send(msg)

    async def _no_edit(self, ctx: Union[commands.Context, discord.Interaction]):
        msg = _("That trigger cannot be edited this way.")
        if isinstance(ctx, discord.Interaction):
            if ctx.response.is_done():
                await ctx.followup.send(msg)
            else:
                await ctx.response.send_message(msg)
        else:
            await ctx.send(msg)

    async def _no_trigger(self, ctx: Union[commands.Context, discord.Interaction], trigger: str):
        msg = _("Trigger `{name}` doesn't exist.").format(name=trigger)
        if isinstance(ctx, discord.Interaction):
            if ctx.response.is_done():
                await ctx.followup.send(msg)
            else:
                await ctx.response.send_message(msg)
        else:
            await ctx.send(msg)

    async def _already_exists(self, ctx: Union[commands.Context, discord.Interaction], name: str):
        msg = _("{name} is already a trigger name.").format(name=name)
        if isinstance(ctx, discord.Interaction):
            if ctx.response.is_done():
                await ctx.followup.send(msg)
            else:
                await ctx.response.send_message(msg)
        else:
            await ctx.send(msg)

    async def _trigger_set(self, ctx: Union[commands.Context, discord.Interaction], name: str):
        msg = _("Trigger `{name}` set.").format(name=name)
        if isinstance(ctx, discord.Interaction):
            if ctx.response.is_done():
                await ctx.followup.send(msg)
            else:
                await ctx.response.send_message(msg)
        else:
            await ctx.send(msg)

    async def _find_good_emojis(self, interaction: discord.Interaction, option: dict):
        option["value"].split(" ")
        list_emojis = [
            discord.PartialEmoji.from_str(e.strip()) for e in option["value"].split(" ")
        ]
        good_emojis = []
        log.debug(option["value"])
        log.debug(list_emojis)
        if any([e.is_unicode_emoji() for e in list_emojis]):
            await interaction.response.send_message(
                "Some emojis were not found, attempting to find unicode emojis."
            )
            msg = await interaction.original_response()
            for emoji in list_emojis:
                if emoji.is_unicode_emoji():
                    try:
                        await msg.add_reaction(emoji)
                        good_emojis.append(str(emoji))
                    except Exception:
                        pass
                else:
                    good_emojis.append(str(emoji)[1:-1])
        else:
            good_emojis = [str(emoji)[1:-1] for emoji in list_emojis]
        return good_emojis

    @commands.group()
    @commands.guild_only()
    async def retrigger(self, ctx: commands.Context) -> None:
        """
        Setup automatic triggers based on regular expressions

        See https://regex101.com/ for help building a regex pattern.
        See `[p]retrigger explain` or click the link below for more details.
        [For more details click here.](https://github.com/TrustyJAID/Trusty-cogs/blob/master/retrigger/README.md)
        """

    @checks.is_owner()
    @retrigger.command()
    async def deleteallbyuser(self, ctx: commands.Context, user_id: int):
        """
        Delete all triggers created by a specified user ID.

        See https://regex101.com/ for help building a regex pattern.
        See `[p]retrigger explain` or click the link below for more details.
        [For more details click here.](https://github.com/TrustyJAID/Trusty-cogs/blob/master/retrigger/README.md)
        """
        await self.red_delete_data_for_user(requester="owner", user_id=user_id)
        await ctx.tick()

    @retrigger.group(name="blocklist", aliases=["blacklist"])
    @checks.mod_or_permissions(manage_messages=True)
    async def blacklist(self, ctx: commands.Context) -> None:
        """
        Set blocklist options for retrigger

        blocklisting supports channels, users, or roles

        See https://regex101.com/ for help building a regex pattern.
        See `[p]retrigger explain` or click the link below for more details.
        [For more details click here.](https://github.com/TrustyJAID/Trusty-cogs/blob/master/retrigger/README.md)
        """

    @retrigger.group(name="allowlist", aliases=["whitelist"])
    @checks.mod_or_permissions(manage_messages=True)
    async def whitelist(self, ctx: commands.Context) -> None:
        """
        Set allowlist options for retrigger

        allowlisting supports channels, users, or roles

        See https://regex101.com/ for help building a regex pattern.
        See `[p]retrigger explain` or click the link below for more details.
        [For more details click here.](https://github.com/TrustyJAID/Trusty-cogs/blob/master/retrigger/README.md)
        """

    @retrigger.group(name="modlog")
    @checks.mod_or_permissions(manage_channels=True)
    async def _modlog(self, ctx: commands.Context) -> None:
        """
        Set which events to record in the modlog.

        See https://regex101.com/ for help building a regex pattern.
        See `[p]retrigger explain` or click the link below for more details.
        [For more details click here.](https://github.com/TrustyJAID/Trusty-cogs/blob/master/retrigger/README.md)
        """

    @retrigger.group(name="edit")
    @checks.mod_or_permissions(manage_channels=True)
    async def _edit(self, ctx: commands.Context) -> None:
        """
        Edit various settings in a set trigger.

        Note: Only the server owner, Bot owner, or original
        author can edit a saved trigger. Multi triggers
        cannot be edited.

        See https://regex101.com/ for help building a regex pattern.
        See `[p]retrigger explain` or click the link below for more details.
        [For more details click here.](https://github.com/TrustyJAID/Trusty-cogs/blob/master/retrigger/README.md)
        """

    @_modlog.command(name="settings", aliases=["list"])
    async def modlog_settings(self, ctx: commands.Context) -> None:
        """
        Show the current modlog settings for this server.

        See https://regex101.com/ for help building a regex pattern.
        See `[p]retrigger explain` or click the link below for more details.
        [For more details click here.](https://github.com/TrustyJAID/Trusty-cogs/blob/master/retrigger/README.md)
        """
        async with ctx.typing():
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
    async def modlog_bans(self, ctx: commands.Context) -> None:
        """
        Toggle custom ban messages in the modlog

        See https://regex101.com/ for help building a regex pattern.
        See `[p]retrigger explain` or click the link below for more details.
        [For more details click here.](https://github.com/TrustyJAID/Trusty-cogs/blob/master/retrigger/README.md)
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
    async def modlog_kicks(self, ctx: commands.Context) -> None:
        """
        Toggle custom kick messages in the modlog

        See https://regex101.com/ for help building a regex pattern.
        See `[p]retrigger explain` or click the link below for more details.
        [For more details click here.](https://github.com/TrustyJAID/Trusty-cogs/blob/master/retrigger/README.md)
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
    async def modlog_filter(self, ctx: commands.Context) -> None:
        """
        Toggle custom filter messages in the modlog

        See https://regex101.com/ for help building a regex pattern.
        See `[p]retrigger explain` or click the link below for more details.
        [For more details click here.](https://github.com/TrustyJAID/Trusty-cogs/blob/master/retrigger/README.md)
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
    async def modlog_addroles(self, ctx: commands.Context) -> None:
        """
        Toggle custom add role messages in the modlog

        See https://regex101.com/ for help building a regex pattern.
        See `[p]retrigger explain` or click the link below for more details.
        [For more details click here.](https://github.com/TrustyJAID/Trusty-cogs/blob/master/retrigger/README.md)
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
    async def modlog_removeroles(self, ctx: commands.Context) -> None:
        """
        Toggle custom add role messages in the modlog

        See https://regex101.com/ for help building a regex pattern.
        See `[p]retrigger explain` or click the link below for more details.
        [For more details click here.](https://github.com/TrustyJAID/Trusty-cogs/blob/master/retrigger/README.md)
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
    ) -> None:
        """
        Set the modlog channel for filtered words

        `<channel>` The channel you would like filtered word notifications to go
        Use `none` or `clear` to not show any modlogs
        User `default` to use the built in modlog channel

        See https://regex101.com/ for help building a regex pattern.
        See `[p]retrigger explain` or click the link below for more details.
        [For more details click here.](https://github.com/TrustyJAID/Trusty-cogs/blob/master/retrigger/README.md)
        """
        if isinstance(channel, discord.TextChannel):
            await self.config.guild(ctx.guild).modlog.set(channel.id)
        else:
            if channel in ["none", "clear"]:
                channel = None
            elif channel in ["default"]:
                channel = "default"
                try:
                    channel = await modlog.get_modlog_channel()
                except RuntimeError:
                    msg = _(
                        "No modlog channel has been setup yet. "
                        "Do `[p]modlogset modlog #channel` to setup the default modlog channel"
                    )
                    await ctx.send(msg)
                    return
            else:
                await ctx.send(_('Channel "{channel}" not found.').format(channel=channel))
                return
            await self.config.guild(ctx.guild).modlog.set(channel)
        msg = _("Modlog set to {channel}").format(channel=channel)
        await ctx.send(msg)

    @_edit.command()
    @checks.mod_or_permissions(manage_messages=True)
    async def cooldown(
        self, ctx: commands.Context, trigger: TriggerExists, time: int, style="guild"
    ) -> None:
        """
        Set cooldown options for retrigger

        `<trigger>` is the name of the trigger.
        `<time>` is a time in seconds until the trigger will run again
        set a time of 0 or less to remove the cooldown
        `[style=guild]` must be either `guild`, `server`, `channel`, `user`, or `member`

        See https://regex101.com/ for help building a regex pattern.
        See `[p]retrigger explain` or click the link below for more details.
        [For more details click here.](https://github.com/TrustyJAID/Trusty-cogs/blob/master/retrigger/README.md)
        """
        if type(trigger) is str:
            return await self._no_trigger(ctx, trigger)
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
        # await self.remove_trigger_from_cache(ctx.guild.id, trigger)
        # self.triggers[ctx.guild.id].append(trigger)
        await self.config.guild(ctx.guild).trigger_list.set(trigger_list)
        msg = msg.format(time=time, style=style, name=trigger.name)
        await ctx.send(msg)

    @whitelist.command(name="add")
    @checks.mod_or_permissions(manage_messages=True)
    async def whitelist_add(
        self,
        ctx: commands.Context,
        trigger: TriggerExists,
        channel_user_role: commands.Greedy[ChannelUserRole],
    ) -> None:
        """
        Add a channel, user, or role to triggers allowlist

        `<trigger>` is the name of the trigger.
        `[channel_user_role...]` is the channel, user or role to allowlist
        (You can supply more than one of any at a time)

        See https://regex101.com/ for help building a regex pattern.
        See `[p]retrigger explain` or click the link below for more details.
        [For more details click here.](https://github.com/TrustyJAID/Trusty-cogs/blob/master/retrigger/README.md)
        """
        if not isinstance(channel_user_role, list):
            channel_user_role = (channel_user_role,)
        if type(trigger) is str:
            return await self._no_trigger(ctx, trigger)
        if len(channel_user_role) < 1:
            await ctx.send(_("You must supply 1 or more channels users or roles to be allowed"))
            return
        for obj in channel_user_role:
            if obj.id not in trigger.whitelist:
                async with self.config.guild(ctx.guild).trigger_list() as trigger_list:
                    trigger.whitelist.append(obj.id)
                    trigger_list[trigger.name] = await trigger.to_json()
        # await self.remove_trigger_from_cache(ctx.guild.id, trigger)
        # self.triggers[ctx.guild.id].append(trigger)
        msg = _("Trigger {name} added `{list_type}` to its allowlist.")
        list_type = humanize_list([c.name for c in channel_user_role])
        msg = msg.format(list_type=list_type, name=trigger.name)

        await ctx.send(msg)

    @whitelist.command(name="remove", aliases=["rem", "del"])
    @checks.mod_or_permissions(manage_messages=True)
    async def whitelist_remove(
        self,
        ctx: commands.Context,
        trigger: TriggerExists,
        channel_user_role: commands.Greedy[ChannelUserRole],
    ) -> None:
        """
        Remove a channel, user, or role from triggers allowlist

        `<trigger>` is the name of the trigger.
        `[channel_user_role...]` is the channel, user or role to remove from the allowlist
        (You can supply more than one of any at a time)

        See https://regex101.com/ for help building a regex pattern.
        See `[p]retrigger explain` or click the link below for more details.
        [For more details click here.](https://github.com/TrustyJAID/Trusty-cogs/blob/master/retrigger/README.md)
        """
        if not isinstance(channel_user_role, list):
            channel_user_role = (channel_user_role,)
        if type(trigger) is str:
            return await self._no_trigger(ctx, trigger)
        if len(channel_user_role) < 1:
            await ctx.send(
                _(
                    "You must supply 1 or more channels users "
                    "or roles to be removed from the allowlist."
                )
            )
            return
        for obj in channel_user_role:
            if obj.id in trigger.whitelist:
                async with self.config.guild(ctx.guild).trigger_list() as trigger_list:
                    trigger.whitelist.remove(obj.id)
                    trigger_list[trigger.name] = await trigger.to_json()
        # await self.remove_trigger_from_cache(ctx.guild.id, trigger)
        # self.triggers[ctx.guild.id].append(trigger)
        msg = _("Trigger {name} removed `{list_type}` from its allowlist.")
        list_type = humanize_list([c.name for c in channel_user_role])
        msg = msg.format(list_type=list_type, name=trigger.name)
        await ctx.send(msg)

    @blacklist.command(name="add")
    @checks.mod_or_permissions(manage_messages=True)
    async def blacklist_add(
        self,
        ctx: commands.Context,
        trigger: TriggerExists,
        channel_user_role: commands.Greedy[ChannelUserRole],
    ) -> None:
        """
        Add a channel, user, or role to triggers blocklist

        `<trigger>` is the name of the trigger.
        `[channel_user_role...]` is the channel, user or role to blocklist
        (You can supply more than one of any at a time)

        See https://regex101.com/ for help building a regex pattern.
        See `[p]retrigger explain` or click the link below for more details.
        [For more details click here.](https://github.com/TrustyJAID/Trusty-cogs/blob/master/retrigger/README.md)
        """
        if not isinstance(channel_user_role, list):
            channel_user_role = (channel_user_role,)
        if type(trigger) is str:
            return await self._no_trigger(ctx, trigger)
        if len(channel_user_role) < 1:
            await ctx.send(_("You must supply 1 or more channels users or roles to be blocked."))
            return
        for obj in channel_user_role:
            if obj.id not in trigger.blacklist:
                async with self.config.guild(ctx.guild).trigger_list() as trigger_list:
                    trigger.blacklist.append(obj.id)
                    trigger_list[trigger.name] = await trigger.to_json()
        # await self.remove_trigger_from_cache(ctx.guild.id, trigger)
        # self.triggers[ctx.guild.id].append(trigger)
        msg = _("Trigger {name} added `{list_type}` to its blocklist.")
        list_type = humanize_list([c.name for c in channel_user_role])
        msg = msg.format(list_type=list_type, name=trigger.name)
        await ctx.send(msg)

    @blacklist.command(name="remove", aliases=["rem", "del"])
    @checks.mod_or_permissions(manage_messages=True)
    async def blacklist_remove(
        self,
        ctx: commands.Context,
        trigger: TriggerExists,
        channel_user_role: commands.Greedy[ChannelUserRole],
    ) -> None:
        """
        Remove a channel, user, or role from triggers blocklist

        `<trigger>` is the name of the trigger.
        `[channel_user_role...]` is the channel, user or role to remove from the blocklist
        (You can supply more than one of any at a time)

        See https://regex101.com/ for help building a regex pattern.
        See `[p]retrigger explain` or click the link below for more details.
        [For more details click here.](https://github.com/TrustyJAID/Trusty-cogs/blob/master/retrigger/README.md)
        """
        if not isinstance(channel_user_role, list):
            channel_user_role = (channel_user_role,)
        if type(trigger) is str:
            return await self._no_trigger(ctx, trigger)
        if len(channel_user_role) < 1:
            await ctx.send(
                _(
                    "You must supply 1 or more channels users or "
                    "roles to be removed from the blocklist."
                )
            )
            return
        for obj in channel_user_role:
            if obj.id in trigger.blacklist:
                async with self.config.guild(ctx.guild).trigger_list() as trigger_list:
                    trigger.blacklist.remove(obj.id)
                    trigger_list[trigger.name] = await trigger.to_json()
        # await self.remove_trigger_from_cache(ctx.guild.id, trigger)
        # self.triggers[ctx.guild.id].append(trigger)
        msg = _("Trigger {name} removed `{list_type}` from its blocklist.")
        list_type = humanize_list([c.name for c in channel_user_role])
        msg = msg.format(list_type=list_type, name=trigger.name)
        await ctx.send(msg)

    @_edit.command(name="regex")
    @checks.mod_or_permissions(manage_messages=True)
    async def edit_regex(
        self, ctx: commands.Context, trigger: TriggerExists, *, regex: ValidRegex
    ) -> None:
        """
        Edit the regex of a saved trigger.

        `<trigger>` is the name of the trigger.
        `<regex>` The new regex pattern to use.

        See https://regex101.com/ for help building a regex pattern.
        See `[p]retrigger explain` or click the link below for more details.
        [For more details click here.](https://github.com/TrustyJAID/Trusty-cogs/blob/master/retrigger/README.md)
        """
        if type(trigger) is str:
            return await self._no_trigger(ctx, trigger)
        if not await self.can_edit(ctx.author, trigger):
            return await self._not_authorized(ctx)
        trigger.regex = re.compile(regex)
        async with self.config.guild(ctx.guild).trigger_list() as trigger_list:
            trigger_list[trigger.name] = await trigger.to_json()
        # await self.remove_trigger_from_cache(ctx.guild.id, trigger)
        # self.triggers[ctx.guild.id].append(trigger)
        msg = _("Trigger {name} regex changed to ```bf\n{regex}\n```")
        msg = msg.format(name=trigger.name, regex=regex)
        await ctx.send(msg)

    @_edit.command(name="ocr")
    @commands.check(lambda ctx: ctx.command.cog.ALLOW_OCR)
    @checks.mod_or_permissions(manage_messages=True)
    async def toggle_ocr_search(self, ctx: commands.Context, trigger: TriggerExists) -> None:
        """
        Toggle whether to use Optical Character Recognition to search for text within images.
        `<trigger>` is the name of the trigger.

        See https://regex101.com/ for help building a regex pattern.
        See `[p]retrigger explain` or click the link below for more details.
        [For more details click here.](https://github.com/TrustyJAID/Trusty-cogs/blob/master/retrigger/README.md)
        """
        if type(trigger) is str:
            return await self._no_trigger(ctx, trigger)
        if not await self.can_edit(ctx.author, trigger):
            return await self._not_authorized(ctx)
        trigger.ocr_search = not trigger.ocr_search
        async with self.config.guild(ctx.guild).trigger_list() as trigger_list:
            trigger_list[trigger.name] = await trigger.to_json()
        # await self.remove_trigger_from_cache(ctx.guild.id, trigger)
        # self.triggers[ctx.guild.id].append(trigger)
        msg = _("Trigger {name} OCR Search set to: {ocr_search}").format(
            name=trigger.name, ocr_search=trigger.ocr_search
        )
        await ctx.send(msg)

    @_edit.command(name="nsfw")
    @checks.mod_or_permissions(manage_messages=True)
    async def toggle_nsfw(self, ctx: commands.Context, trigger: TriggerExists) -> None:
        """
        Toggle whether a trigger is considered NSFW.
        This will prevent the trigger from activating in non-NSFW channels.
        `<trigger>` is the name of the trigger.

        See https://regex101.com/ for help building a regex pattern.
        See `[p]retrigger explain` or click the link below for more details.
        [For more details click here.](https://github.com/TrustyJAID/Trusty-cogs/blob/master/retrigger/README.md)
        """
        if type(trigger) is str:
            return await self._no_trigger(ctx, trigger)
        if not await self.can_edit(ctx.author, trigger):
            return await self._not_authorized(ctx)
        trigger.nsfw = not trigger.nsfw
        async with self.config.guild(ctx.guild).trigger_list() as trigger_list:
            trigger_list[trigger.name] = await trigger.to_json()
        # await self.remove_trigger_from_cache(ctx.guild.id, trigger)
        # self.triggers[ctx.guild.id].append(trigger)
        msg = _("Trigger {name} NSFW set to: {nsfw}").format(name=trigger.name, nsfw=trigger.nsfw)
        await ctx.send(msg)

    @_edit.command(name="readfilenames", aliases=["filenames"])
    @checks.mod_or_permissions(manage_messages=True)
    async def toggle_filename_search(self, ctx: commands.Context, trigger: TriggerExists) -> None:
        """
        Toggle whether to search message attachment filenames.

        Note: This will append all attachments in a message to the message content. This **will not**
        download and read file content using regex.

        `<trigger>` is the name of the trigger.

        See https://regex101.com/ for help building a regex pattern.
        See `[p]retrigger explain` or click the link below for more details.
        [For more details click here.](https://github.com/TrustyJAID/Trusty-cogs/blob/master/retrigger/README.md)
        """
        if type(trigger) is str:
            return await self._no_trigger(ctx, trigger)
        if not await self.can_edit(ctx.author, trigger):
            return await self._not_authorized(ctx)
        trigger.read_filenames = not trigger.read_filenames
        async with self.config.guild(ctx.guild).trigger_list() as trigger_list:
            trigger_list[trigger.name] = await trigger.to_json()
        # await self.remove_trigger_from_cache(ctx.guild.id, trigger)
        # self.triggers[ctx.guild.id].append(trigger)
        msg = _("Trigger {name} read filenames set to: {read_filenames}").format(
            name=trigger.name, read_filenames=trigger.read_filenames
        )
        await ctx.send(msg)

    @_edit.command(name="reply", aliases=["replies"])
    @checks.mod_or_permissions(manage_messages=True)
    async def set_reply(
        self, ctx: commands.Context, trigger: TriggerExists, set_to: Optional[bool] = None
    ) -> None:
        """
        Set whether or not to reply to the triggered message

        `<trigger>` is the name of the trigger.
        `[set_to]` `True` will reply with a notificaiton, `False` will reply without a notification,
        leaving this blank will clear replies entirely.

        Note: This is only availabe for Red 3.4.6/discord.py 1.6.0 or greater.

        See https://regex101.com/ for help building a regex pattern.
        See `[p]retrigger explain` or click the link below for more details.
        [For more details click here.](https://github.com/TrustyJAID/Trusty-cogs/blob/master/retrigger/README.md)
        """
        if type(trigger) is str:
            return await self._no_trigger(ctx, trigger)
        if not await self.can_edit(ctx.author, trigger):
            return await self._not_authorized(ctx)
        trigger.reply = set_to
        async with self.config.guild(ctx.guild).trigger_list() as trigger_list:
            trigger_list[trigger.name] = await trigger.to_json()
        # await self.remove_trigger_from_cache(ctx.guild.id, trigger)
        # self.triggers[ctx.guild.id].append(trigger)
        msg = _("Trigger {name} replies set to: {set_to}").format(
            name=trigger.name, set_to=trigger.reply
        )
        await ctx.send(msg)

    @_edit.command(name="tts", aliases=["texttospeech", "text-to-speech"])
    @checks.mod_or_permissions(manage_messages=True)
    async def set_tts(self, ctx: commands.Context, trigger: TriggerExists, set_to: bool) -> None:
        """
        Set whether or not to send the message with text-to-speech

        `<trigger>` is the name of the trigger.
        `[set_to]` either `true` or `false` on whether to send the text
        reply with text-to-speech enabled.

        See https://regex101.com/ for help building a regex pattern.
        See `[p]retrigger explain` or click the link below for more details.
        [For more details click here.](https://github.com/TrustyJAID/Trusty-cogs/blob/master/retrigger/README.md)
        """
        if type(trigger) is str:
            return await self._no_trigger(ctx, trigger)
        if not await self.can_edit(ctx.author, trigger):
            return await self._not_authorized(ctx)
        trigger.tts = set_to
        async with self.config.guild(ctx.guild).trigger_list() as trigger_list:
            trigger_list[trigger.name] = await trigger.to_json()
        # await self.remove_trigger_from_cache(ctx.guild.id, trigger)
        # self.triggers[ctx.guild.id].append(trigger)
        msg = _("Trigger {name} text-to-speech set to: {set_to}").format(
            name=trigger.name, set_to=trigger.tts
        )
        await ctx.send(msg)

    @_edit.command(name="usermention", aliases=["userping"])
    @checks.mod_or_permissions(manage_messages=True)
    async def set_user_mention(
        self, ctx: commands.Context, trigger: TriggerExists, set_to: bool
    ) -> None:
        """
        Set whether or not this trigger can mention users

        `<trigger>` is the name of the trigger.
        `[set_to]` either `true` or `false` on whether to allow this trigger
        to actually ping the users in the message.

        See https://regex101.com/ for help building a regex pattern.
        See `[p]retrigger explain` or click the link below for more details.
        [For more details click here.](https://github.com/TrustyJAID/Trusty-cogs/blob/master/retrigger/README.md)
        """
        if type(trigger) is str:
            return await self._no_trigger(ctx, trigger)
        if not await self.can_edit(ctx.author, trigger):
            return await self._not_authorized(ctx)
        trigger.user_mention = set_to
        async with self.config.guild(ctx.guild).trigger_list() as trigger_list:
            trigger_list[trigger.name] = await trigger.to_json()
        # await self.remove_trigger_from_cache(ctx.guild.id, trigger)
        # self.triggers[ctx.guild.id].append(trigger)
        msg = _("Trigger {name} user mentions set to: {set_to}").format(
            name=trigger.name, set_to=trigger.user_mention
        )
        await ctx.send(msg)

    @_edit.command(name="everyonemention", aliases=["everyoneping"])
    @checks.mod_or_permissions(manage_messages=True, mention_everyone=True)
    async def set_everyone_mention(
        self, ctx: commands.Context, trigger: TriggerExists, set_to: bool
    ) -> None:
        """
        Set whether or not to send this trigger can mention everyone

        `<trigger>` is the name of the trigger.
        `[set_to]` either `true` or `false` on whether to allow this trigger
        to actually ping everyone if the bot has correct permissions.

        See https://regex101.com/ for help building a regex pattern.
        See `[p]retrigger explain` or click the link below for more details.
        [For more details click here.](https://github.com/TrustyJAID/Trusty-cogs/blob/master/retrigger/README.md)
        """

        if type(trigger) is str:
            return await self._no_trigger(ctx, trigger)
        if not await self.can_edit(ctx.author, trigger):
            return await self._not_authorized(ctx)
        trigger.everyone_mention = set_to
        async with self.config.guild(ctx.guild).trigger_list() as trigger_list:
            trigger_list[trigger.name] = await trigger.to_json()
        # await self.remove_trigger_from_cache(ctx.guild.id, trigger)
        # self.triggers[ctx.guild.id].append(trigger)
        msg = _("Trigger {name} everyone mentions set to: {set_to}").format(
            name=trigger.name, set_to=trigger.everyone_mention
        )
        await ctx.send(msg)

    @_edit.command(name="rolemention", aliases=["roleping"])
    @checks.mod_or_permissions(manage_messages=True, mention_everyone=True)
    async def set_role_mention(
        self, ctx: commands.Context, trigger: TriggerExists, set_to: bool
    ) -> None:
        """
        Set whether or not to send this trigger will allow role mentions

        `<trigger>` is the name of the trigger.
        `[set_to]` either `true` or `false` on whether to allow this trigger
        to actually ping roles if the bot has correct permissions.

        See https://regex101.com/ for help building a regex pattern.
        See `[p]retrigger explain` or click the link below for more details.
        [For more details click here.](https://github.com/TrustyJAID/Trusty-cogs/blob/master/retrigger/README.md)
        """
        if type(trigger) is str:
            return await self._no_trigger(ctx, trigger)
        if not await self.can_edit(ctx.author, trigger):
            return await self._not_authorized(ctx)
        trigger.role_mention = set_to
        async with self.config.guild(ctx.guild).trigger_list() as trigger_list:
            trigger_list[trigger.name] = await trigger.to_json()
        # await self.remove_trigger_from_cache(ctx.guild.id, trigger)
        # self.triggers[ctx.guild.id].append(trigger)
        msg = _("Trigger {name} role mentions set to: {set_to}").format(
            name=trigger.name, set_to=trigger.role_mention
        )
        await ctx.send(msg)

    @_edit.command(name="edited")
    @checks.mod_or_permissions(manage_messages=True)
    async def toggle_check_edits(self, ctx: commands.Context, trigger: TriggerExists) -> None:
        """
        Toggle whether the bot will listen to edited messages as well as on_message for
        the specified trigger.

        `<trigger>` is the name of the trigger.

        See https://regex101.com/ for help building a regex pattern.
        See `[p]retrigger explain` or click the link below for more details.
        [For more details click here.](https://github.com/TrustyJAID/Trusty-cogs/blob/master/retrigger/README.md)
        """

        if type(trigger) is str:
            return await self._no_trigger(ctx, trigger)
        if not await self.can_edit(ctx.author, trigger):
            return await self._not_authorized(ctx)
        trigger.check_edits = not trigger.check_edits
        async with self.config.guild(ctx.guild).trigger_list() as trigger_list:
            trigger_list[trigger.name] = await trigger.to_json()
        # await self.remove_trigger_from_cache(ctx.guild.id, trigger)
        # self.triggers[ctx.guild.id].append(trigger)
        msg = _("Trigger {name} check edits set to: {ignore_edits}").format(
            name=trigger.name, ignore_edits=trigger.check_edits
        )
        await ctx.send(msg)

    @_edit.command(name="text", aliases=["msg"])
    @checks.mod_or_permissions(manage_messages=True)
    async def edit_text(self, ctx: commands.Context, trigger: TriggerExists, *, text: str) -> None:
        """
        Edit the text of a saved trigger.

        `<trigger>` is the name of the trigger.
        `<text>` The new text to respond with.

        See https://regex101.com/ for help building a regex pattern.
        See `[p]retrigger explain` or click the link below for more details.
        [For more details click here.](https://github.com/TrustyJAID/Trusty-cogs/blob/master/retrigger/README.md)
        """
        if type(trigger) is str:
            return await self._no_trigger(ctx, trigger)
        if not await self.can_edit(ctx.author, trigger):
            return await self._not_authorized(ctx)
        if trigger.multi_payload:
            return await self._no_multi(ctx)
        if "text" not in trigger.response_type:
            return await self._no_edit(ctx)
        trigger.text = text
        async with self.config.guild(ctx.guild).trigger_list() as trigger_list:
            trigger_list[trigger.name] = await trigger.to_json()
        # await self.remove_trigger_from_cache(ctx.guild.id, trigger)
        # self.triggers[ctx.guild.id].append(trigger)
        msg = _("Trigger {name} text changed to `{text}`").format(name=trigger.name, text=text)
        await ctx.send(msg)

    @_edit.command(name="chance", aliases=["chances"])
    @checks.mod_or_permissions(manage_messages=True)
    async def edit_chance(
        self, ctx: commands.Context, trigger: TriggerExists, chance: int
    ) -> None:
        """
        Edit the chance a trigger will execute.

        `<trigger>` is the name of the trigger.
        `<chance>` The chance the trigger will execute in form of 1 in chance.

        Set the `chance` to 0 to remove the chance and always perform the trigger.

        See https://regex101.com/ for help building a regex pattern.
        See `[p]retrigger explain` or click the link below for more details.
        [For more details click here.](https://github.com/TrustyJAID/Trusty-cogs/blob/master/retrigger/README.md)
        """
        if type(trigger) is str:
            return await self._no_trigger(ctx, trigger)
        if not await self.can_edit(ctx.author, trigger):
            return await self._not_authorized(ctx)
        if chance < 0:
            chance = 0
        trigger.chance = chance
        async with self.config.guild(ctx.guild).trigger_list() as trigger_list:
            trigger_list[trigger.name] = await trigger.to_json()
        # await self.remove_trigger_from_cache(ctx.guild.id, trigger)
        # self.triggers[ctx.guild.id].append(trigger)
        if chance:
            msg = _("Trigger {name} chance changed to `1 in {chance}`").format(
                name=trigger.name, chance=str(chance)
            )
        else:
            msg = _("Trigger {name} chance changed to always.").format(name=trigger.name)
        await ctx.send(msg)

    @_edit.command(name="deleteafter", aliases=["autodelete", "delete"])
    @checks.mod_or_permissions(manage_messages=True)
    async def edit_delete_after(
        self,
        ctx: commands.Context,
        trigger: TriggerExists,
        *,
        delete_after: TimedeltaConverter = None,
    ) -> None:
        """
        Edit the delete_after parameter of a saved text trigger.

        `<trigger>` is the name of the trigger.
        `<delete_after>` The time until the message is deleted must include units.
        Example: `[p]retrigger edit deleteafter trigger 2 minutes`

        See https://regex101.com/ for help building a regex pattern.
        See `[p]retrigger explain` or click the link below for more details.
        [For more details click here.](https://github.com/TrustyJAID/Trusty-cogs/blob/master/retrigger/README.md)
        """
        if type(trigger) is str:
            return await self._no_trigger(ctx, trigger)
        if not await self.can_edit(ctx.author, trigger):
            return await self._not_authorized(ctx)
        if "text" not in trigger.response_type:
            return await self._no_edit(ctx)
        if delete_after:
            if delete_after.total_seconds() > 0:
                delete_after_seconds = delete_after.total_seconds()
            if delete_after.total_seconds() < 1:
                msg = _("`delete_after` must be greater than 1 second.")
                await ctx.send(msg)
                return
        else:
            delete_after_seconds = None
        trigger.delete_after = delete_after_seconds
        async with self.config.guild(ctx.guild).trigger_list() as trigger_list:
            trigger_list[trigger.name] = await trigger.to_json()
        # await self.remove_trigger_from_cache(ctx.guild.id, trigger)
        # self.triggers[ctx.guild.id].append(trigger)
        msg = _("Trigger {name} will now delete after `{time}` seconds.").format(
            name=trigger.name, time=delete_after_seconds
        )
        await ctx.send(msg)

    @_edit.command(name="ignorecommands")
    @checks.mod_or_permissions(manage_messages=True)
    async def edit_ignore_commands(self, ctx: commands.Context, trigger: TriggerExists) -> None:
        """
        Toggle the trigger ignoring command messages entirely.

        `<trigger>` is the name of the trigger.

        See https://regex101.com/ for help building a regex pattern.
        See `[p]retrigger explain` or click the link below for more details.
        [For more details click here.](https://github.com/TrustyJAID/Trusty-cogs/blob/master/retrigger/README.md)
        """

        if type(trigger) is str:
            return await self._no_trigger(ctx, trigger)
        if not await self.can_edit(ctx.author, trigger):
            return await self._not_authorized(ctx)
        trigger.ignore_commands = not trigger.ignore_commands
        async with self.config.guild(ctx.guild).trigger_list() as trigger_list:
            trigger_list[trigger.name] = await trigger.to_json()
        # await self.remove_trigger_from_cache(ctx.guild.id, trigger)
        # self.triggers[ctx.guild.id].append(trigger)
        msg = _("Trigger {name} ignoring commands set to `{text}`").format(
            name=trigger.name, text=trigger.ignore_commands
        )
        await ctx.send(msg)

    @_edit.command(name="command", aliases=["cmd"])
    @checks.mod_or_permissions(manage_messages=True)
    async def edit_command(
        self, ctx: commands.Context, trigger: TriggerExists, *, command: str
    ) -> None:
        """
        Edit the text of a saved trigger.

        `<trigger>` is the name of the trigger.
        `<command>` The new command for the trigger.

        See https://regex101.com/ for help building a regex pattern.
        See `[p]retrigger explain` or click the link below for more details.
        [For more details click here.](https://github.com/TrustyJAID/Trusty-cogs/blob/master/retrigger/README.md)
        """

        if type(trigger) is str:
            return await self._no_trigger(ctx, trigger)
        if not await self.can_edit(ctx.author, trigger):
            return await self._not_authorized(ctx)
        if trigger.multi_payload:
            return await self._no_multi(ctx)
        cmd_list = command.split(" ")
        existing_cmd = self.bot.get_command(cmd_list[0])
        if existing_cmd is None:
            msg = _("`{command}` doesn't seem to be an available command.").format(command=command)
            await ctx.send(msg)
            return
        if "command" not in trigger.response_type:
            return await self._no_edit(ctx)
        trigger.text = command
        async with self.config.guild(ctx.guild).trigger_list() as trigger_list:
            trigger_list[trigger.name] = await trigger.to_json()
        # await self.remove_trigger_from_cache(ctx.guild.id, trigger)
        # self.triggers[ctx.guild.id].append(trigger)
        msg = _("Trigger {name} command changed to `{command}`").format(
            name=trigger.name, command=command
        )
        await ctx.send(msg)

    @_edit.command(name="role", aliases=["roles"])
    @checks.mod_or_permissions(manage_roles=True)
    async def edit_roles(
        self, ctx: commands.Context, trigger: TriggerExists, roles: commands.Greedy[discord.Role]
    ) -> None:
        """
        Edit the added or removed roles of a saved trigger.

        `<trigger>` is the name of the trigger.
        `<roles>` space separated list of roles or ID's to edit on the trigger.

        See https://regex101.com/ for help building a regex pattern.
        See `[p]retrigger explain` or click the link below for more details.
        [For more details click here.](https://github.com/TrustyJAID/Trusty-cogs/blob/master/retrigger/README.md)
        """
        if not isinstance(roles, tuple):
            roles = (roles,)

        if type(trigger) is str:
            return await self._no_trigger(ctx, trigger)
        if not await self.can_edit(ctx.author, trigger):
            return await self._not_authorized(ctx)
        if trigger.multi_payload:
            return await self._no_multi(ctx)
        if not any([t for t in trigger.response_type if t in ["add_role", "remove_role"]]):
            return await self._no_edit(ctx)
        for role in roles:
            if role >= ctx.me.top_role:
                msg = _("I can't assign roles higher than my own.")
                await ctx.send(msg)
                return
            if ctx.author.id == ctx.guild.owner_id:
                continue
            if role >= ctx.author.top_role:
                msg = _("I can't assign roles higher than you are able to assign.")
                await ctx.send(msg)
                return
        for role in roles:
            if role.id in trigger.text:
                trigger.text.remove(role.id)
            else:
                trigger.text.append(role.id)
        async with self.config.guild(ctx.guild).trigger_list() as trigger_list:
            trigger_list[trigger.name] = await trigger.to_json()
        # await self.remove_trigger_from_cache(ctx.guild.id, trigger)
        # self.triggers[ctx.guild.id].append(trigger)
        msg = _("Trigger {name} role edits changed to `{roles}`").format(
            name=trigger.name, roles=humanize_list([r.name for r in roles])
        )
        await ctx.send(msg)

    @_edit.command(name="react", aliases=["emojis"])
    @checks.mod_or_permissions(manage_messages=True)
    async def edit_reactions(
        self, ctx: commands.Context, trigger: TriggerExists, emojis: commands.Greedy[ValidEmoji]
    ) -> None:
        """
        Edit the emoji reactions of a saved trigger.

        `<trigger>` is the name of the trigger.
        `<emojis>` The new emojis to be used in the trigger.

        See https://regex101.com/ for help building a regex pattern.
        See `[p]retrigger explain` or click the link below for more details.
        [For more details click here.](https://github.com/TrustyJAID/Trusty-cogs/blob/master/retrigger/README.md)
        """

        if type(trigger) is str:
            return await self._no_trigger(ctx, trigger)
        if not await self.can_edit(ctx.author, trigger):
            return await self._not_authorized(ctx)
        if "react" not in trigger.response_type:
            return await self._no_edit(ctx)
        for emoji in emojis:
            if emoji in trigger.text:
                trigger.text.remove(emoji)
            else:
                trigger.text.append(emoji)
        async with self.config.guild(ctx.guild).trigger_list() as trigger_list:
            trigger_list[trigger.name] = await trigger.to_json()
        # await self.remove_trigger_from_cache(ctx.guild.id, trigger)
        # self.triggers[ctx.guild.id].append(trigger)
        emoji_s = [f"<{e}>" for e in emojis if len(e) > 5] + [e for e in emojis if len(e) < 5]
        msg = _("Trigger {name} reactions changed to {emojis}").format(
            name=trigger.name, emojis=humanize_list(emoji_s)
        )
        await ctx.send(msg)

    @_edit.command(name="enable")
    @checks.mod_or_permissions(manage_messages=True)
    async def enable_trigger(self, ctx: commands.Context, trigger: TriggerExists) -> None:
        """
        Enable a trigger

        `<trigger>` is the name of the trigger.

        See https://regex101.com/ for help building a regex pattern.
        See `[p]retrigger explain` or click the link below for more details.
        [For more details click here.](https://github.com/TrustyJAID/Trusty-cogs/blob/master/retrigger/README.md)
        """
        if type(trigger) is str:
            return await self._no_trigger(ctx, trigger)
        trigger.enabled = True
        async with self.config.guild(ctx.guild).trigger_list() as trigger_list:
            trigger_list[trigger.name] = await trigger.to_json()
        # await self.remove_trigger_from_cache(ctx.guild.id, trigger)
        # self.triggers[ctx.guild.id].append(trigger)
        msg = _("Trigger {name} has been enabled.").format(name=trigger.name)
        await ctx.send(msg)

    @_edit.command(name="disable")
    @checks.mod_or_permissions(manage_messages=True)
    async def disable_trigger(self, ctx: commands.Context, trigger: TriggerExists) -> None:
        """
        Disable a trigger

        `<trigger>` is the name of the trigger.

        See https://regex101.com/ for help building a regex pattern.
        See `[p]retrigger explain` or click the link below for more details.
        [For more details click here.](https://github.com/TrustyJAID/Trusty-cogs/blob/master/retrigger/README.md)
        """
        log.debug(trigger)
        if type(trigger) is str:
            return await self._no_trigger(ctx, trigger)
        trigger.enabled = False
        async with self.config.guild(ctx.guild).trigger_list() as trigger_list:
            trigger_list[trigger.name] = await trigger.to_json()
        # await self.remove_trigger_from_cache(ctx.guild.id, trigger)
        msg = _("Trigger {name} has been disabled.").format(name=trigger.name)
        await ctx.send(msg)

    @retrigger.command(hidden=True)
    @checks.is_owner()
    async def timeout(self, ctx: commands.Context, timeout: int) -> None:
        """
        Set the timeout period for searching triggers

        `<timeout>` is number of seconds until regex searching is kicked out.

        See https://regex101.com/ for help building a regex pattern.
        See `[p]retrigger explain` or click the link below for more details.
        [For more details click here.](https://github.com/TrustyJAID/Trusty-cogs/blob/master/retrigger/README.md)
        """
        if timeout > 1:
            msg = await ctx.send(
                _(
                    "Increasing this could cause the bot to become unstable or allow "
                    "bad regex patterns to continue to exist causing slow downs and "
                    "even fatal crashes on the bot. Do you wish to continue?"
                )
            )
            start_adding_reactions(msg, ReactionPredicate.YES_OR_NO_EMOJIS)
            pred = ReactionPredicate.yes_or_no(msg, user=ctx.author)
            try:
                await ctx.bot.wait_for("reaction_add", check=pred, timeout=30)
            except asyncio.TimeoutError:
                await ctx.send(_("Not changing regex timeout time."))
                return
            if pred.result:
                await self.config.trigger_timeout.set(timeout)
                self.trigger_timeout = timeout
                await ctx.tick()
            else:
                await ctx.send(_("Not changing regex timeout time."))
        elif timeout > 10:
            await ctx.send(
                _(
                    "{timeout} seconds is too long, you may want to look at `{prefix}retrigger bypass`"
                ).format(timeout=timeout, prefix=ctx.clean_prefix)
            )
            return
        else:
            if timeout < 1:
                timeout = 1
            await self.config.trigger_timeout.set(timeout)
            self.trigger_timeout = timeout
            await ctx.send(_("Regex search timeout set to {timeout}").format(timeout=timeout))

    @retrigger.command(hidden=True)
    @checks.is_owner()
    async def bypass(self, ctx: commands.Context, bypass: bool) -> None:
        """
        Bypass patterns being kicked from memory until reload

        **Warning:** Enabling this can allow mods and admins to create triggers
        that cause catastrophic backtracking which can lead to the bot crashing
        unexpectedly. Only enable in servers where you trust the admins not to
        mess with the bot.

        See https://regex101.com/ for help building a regex pattern.
        See `[p]retrigger explain` or click the link below for more details.
        [For more details click here.](https://github.com/TrustyJAID/Trusty-cogs/blob/master/retrigger/README.md)
        """
        if bypass:
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
                await ctx.send(_("Not bypassing safe Regex search."))
                return
            if pred.result:
                await self.config.guild(ctx.guild).bypass.set(bypass)
                await ctx.tick()
            else:
                await ctx.send(_("Not bypassing safe Regex search."))
        else:
            await self.config.guild(ctx.guild).bypass.set(bypass)
            await ctx.send(_("Safe Regex search re-enabled."))

    @retrigger.command(usage="[trigger]")
    @commands.bot_has_permissions(read_message_history=True, add_reactions=True)
    async def list(
        self, ctx: commands.Context, guild_id: Optional[int] = None, trigger: TriggerExists = None
    ) -> None:
        """
        List information about triggers.

        `[trigger]` if supplied provides information about named trigger.
        \N{BLACK RIGHT-POINTING TRIANGLE WITH DOUBLE VERTICAL BAR}\N{VARIATION SELECTOR-16} will toggle the displayed triggers active setting
        \N{NEGATIVE SQUARED CROSS MARK} will toggle the displayed trigger to be not active
        \N{WHITE HEAVY CHECK MARK} will toggle the displayed trigger to be active
        \N{PUT LITTER IN ITS PLACE SYMBOL} will delete the displayed trigger

        See https://regex101.com/ for help building a regex pattern.
        See `[p]retrigger explain` or click the link below for more details.
        [For more details click here.](https://github.com/TrustyJAID/Trusty-cogs/blob/master/retrigger/README.md)
        """
        if isinstance(ctx, discord.Interaction):
            await ctx.response.defer()
            author = ctx.user
        else:
            author = ctx.author
        guild = ctx.guild
        if guild_id and await self.bot.is_owner(author):
            guild = self.bot.get_guild(int(guild_id))
            if not guild:
                guild = ctx.guild
        index = 0
        if guild.id not in self.triggers or not self.triggers[guild.id]:
            msg = _("There are no triggers setup on this server.")
            await ctx.send(msg)
            return
        if trigger:
            if type(trigger) is str:
                return await self._no_trigger(ctx, trigger)
            for t in self.triggers[guild.id].values():
                if t.name == trigger.name:
                    index = list(self.triggers[guild.id].values()).index(t)
        await ReTriggerMenu(
            source=ReTriggerPages(
                triggers=list(self.triggers[guild.id].values()),
                guild=guild,
            ),
            delete_message_after=False,
            clear_reactions_after=True,
            timeout=60,
            cog=self,
            page_start=index,
        ).start(ctx=ctx)

    @retrigger.command(aliases=["del", "rem", "delete"])
    @checks.mod_or_permissions(manage_messages=True)
    async def remove(self, ctx: commands.Context, trigger: TriggerExists) -> None:
        """
        Remove a specified trigger

        `<trigger>` is the name of the trigger.

        See https://regex101.com/ for help building a regex pattern.
        See `[p]retrigger explain` or click the link below for more details.
        [For more details click here.](https://github.com/TrustyJAID/Trusty-cogs/blob/master/retrigger/README.md)
        """
        if type(trigger) is Trigger:
            await self.remove_trigger(ctx.guild.id, trigger.name)
            # await self.remove_trigger_from_cache(ctx.guild.id, trigger)
            msg = _("Trigger `{trigger}` removed.").format(trigger=trigger.name)
            await ctx.send(msg)
        else:
            await self._no_trigger(ctx, trigger)

    @retrigger.command()
    async def explain(self, ctx: commands.Context, page_num: Optional[int] = 1) -> None:
        """
        Explain how to use retrigger

        See https://regex101.com/ for help building a regex pattern.
        See `[p]retrigger explain` or click the link below for more details.
        [For more details click here.](https://github.com/TrustyJAID/Trusty-cogs/blob/master/retrigger/README.md)
        """
        if isinstance(ctx, discord.Interaction):
            await ctx.response.defer()
            prefix = r"\\"
        else:
            prefix = ctx.clean_prefix
        with open(Path(__file__).parent / "README.md", "r", encoding="utf8") as infile:
            data = infile.read()
        pages = []
        for page in pagify(data, ["\n\n\n", "\n\n", "\n"], priority=True):
            pages.append(re.sub(r"\[p\]", prefix, page))
        if page_num and (page_num > len(pages) or page_num < 0):
            page_num = 1
        await BaseMenu(
            source=ExplainReTriggerPages(
                pages=pages,
            ),
            delete_message_after=False,
            clear_reactions_after=True,
            timeout=60,
            cog=self,
            page_start=int(page_num) - 1,
        ).start(ctx=ctx)

    @retrigger.command()
    @checks.mod_or_permissions(manage_messages=True)
    async def text(
        self,
        ctx: commands.Context,
        name: str,
        regex: ValidRegex,
        delete_after: Optional[TimedeltaConverter] = None,
        *,
        text: str,
    ) -> None:
        """
        Add a text response trigger

        `<name>` name of the trigger.
        `<regex>` the regex that will determine when to respond.
        `[delete_after]` Optionally have the text autodelete must include units e.g. 2m.
        `<text>` response of the trigger.

        See https://regex101.com/ for help building a regex pattern.
        See `[p]retrigger explain` or click the link below for more details.
        [For more details click here.](https://github.com/TrustyJAID/Trusty-cogs/blob/master/retrigger/README.md)
        """
        if ctx.guild.id in self.triggers and name in self.triggers[ctx.guild.id]:
            return await self._already_exists(ctx, name)
        guild = ctx.guild
        author = ctx.author.id if isinstance(ctx, commands.Context) else ctx.user.id
        if delete_after:
            if delete_after.total_seconds() > 0:
                delete_after_seconds = delete_after.total_seconds()
            if delete_after.total_seconds() < 1:
                await ctx.send(_("`delete_after` must be greater than 1 second."))
                return
        else:
            delete_after_seconds = None
        new_trigger = Trigger(
            name,
            regex,
            [TriggerResponse.text],
            author,
            text=text,
            created_at=ctx.message.id if isinstance(ctx, commands.Context) else ctx.id,
            delete_after=delete_after_seconds,
        )
        if ctx.guild.id not in self.triggers:
            self.triggers[ctx.guild.id] = {}
        self.triggers[ctx.guild.id][new_trigger.name] = new_trigger
        trigger_list = await self.config.guild(guild).trigger_list()
        trigger_list[name] = await new_trigger.to_json()
        await self.config.guild(guild).trigger_list.set(trigger_list)
        await self._trigger_set(ctx, name)

    @retrigger.command(aliases=["randomtext", "rtext"])
    @checks.mod_or_permissions(manage_messages=True)
    async def random(self, ctx: commands.Context, name: str, regex: ValidRegex) -> None:
        """
        Add a random text response trigger

        `<name>` name of the trigger
        `<regex>` the regex that will determine when to respond

        See https://regex101.com/ for help building a regex pattern.
        See `[p]retrigger explain` or click the link below for more details.
        [For more details click here.](https://github.com/TrustyJAID/Trusty-cogs/blob/master/retrigger/README.md)
        """
        if ctx.guild.id in self.triggers and name in self.triggers[ctx.guild.id]:
            return await self._already_exists(ctx, name)
        text = await self.wait_for_multiple_responses(ctx)
        if not text:
            await ctx.send(_("No responses supplied"))
            return
        guild = ctx.guild
        author = ctx.author.id if isinstance(ctx, commands.Context) else ctx.user.id
        new_trigger = Trigger(
            name,
            regex,
            [TriggerResponse.randtext],
            author,
            text=text,
            created_at=ctx.message.id if isinstance(ctx, commands.Context) else ctx.id,
        )
        if ctx.guild.id not in self.triggers:
            self.triggers[ctx.guild.id] = {}
        self.triggers[ctx.guild.id][new_trigger.name] = new_trigger
        trigger_list = await self.config.guild(guild).trigger_list()
        trigger_list[name] = await new_trigger.to_json()
        await self.config.guild(guild).trigger_list.set(trigger_list)
        await self._trigger_set(ctx, name)

    @retrigger.command()
    @checks.mod_or_permissions(manage_messages=True)
    async def dm(self, ctx: commands.Context, name: str, regex: ValidRegex, *, text: str) -> None:
        """
        Add a dm response trigger

        `<name>` name of the trigger
        `<regex>` the regex that will determine when to respond
        `<text>` response of the trigger

        See https://regex101.com/ for help building a regex pattern.
        See `[p]retrigger explain` or click the link below for more details.
        [For more details click here.](https://github.com/TrustyJAID/Trusty-cogs/blob/master/retrigger/README.md)
        """
        if ctx.guild.id in self.triggers and name in self.triggers[ctx.guild.id]:
            return await self._already_exists(ctx, name)
        guild = ctx.guild
        author = ctx.author.id if isinstance(ctx, commands.Context) else ctx.user.id
        new_trigger = Trigger(
            name,
            regex,
            [TriggerResponse.dm],
            author,
            text=text,
            created_at=ctx.message.id if isinstance(ctx, commands.Context) else ctx.id,
        )
        if ctx.guild.id not in self.triggers:
            self.triggers[ctx.guild.id] = {}
        self.triggers[ctx.guild.id][new_trigger.name] = new_trigger
        trigger_list = await self.config.guild(guild).trigger_list()
        trigger_list[name] = await new_trigger.to_json()
        await self.config.guild(guild).trigger_list.set(trigger_list)
        await self._trigger_set(ctx, name)

    @retrigger.command()
    @checks.mod_or_permissions(manage_messages=True)
    async def dmme(
        self, ctx: commands.Context, name: str, regex: ValidRegex, *, text: str
    ) -> None:
        """
        Add trigger to DM yourself

        `<name>` name of the trigger
        `<regex>` the regex that will determine when to respond
        `<text>` response of the trigger

        See https://regex101.com/ for help building a regex pattern.
        See `[p]retrigger explain` or click the link below for more details.
        [For more details click here.](https://github.com/TrustyJAID/Trusty-cogs/blob/master/retrigger/README.md)
        """
        if ctx.guild.id in self.triggers and name in self.triggers[ctx.guild.id]:
            return await self._already_exists(ctx, name)
        guild = ctx.guild
        author = ctx.author.id if isinstance(ctx, commands.Context) else ctx.user.id
        new_trigger = Trigger(
            name,
            regex,
            [TriggerResponse.dmme],
            author,
            text=text,
            created_at=ctx.message.id if isinstance(ctx, commands.Context) else ctx.id,
        )
        if ctx.guild.id not in self.triggers:
            self.triggers[ctx.guild.id] = {}
        self.triggers[ctx.guild.id][new_trigger.name] = new_trigger
        trigger_list = await self.config.guild(guild).trigger_list()
        trigger_list[name] = await new_trigger.to_json()
        await self.config.guild(guild).trigger_list.set(trigger_list)
        await self._trigger_set(ctx, name)

    @retrigger.command()
    @checks.mod_or_permissions(manage_nicknames=True)
    @checks.bot_has_permissions(manage_nicknames=True)
    async def rename(
        self, ctx: commands.Context, name: str, regex: ValidRegex, *, text: str
    ) -> None:
        """
        Add trigger to rename users

        `<name>` name of the trigger.
        `<regex>` the regex that will determine when to respond.
        `<text>` new users nickanme.

        See https://regex101.com/ for help building a regex pattern.
        See `[p]retrigger explain` or click the link below for more details.
        [For more details click here.](https://github.com/TrustyJAID/Trusty-cogs/blob/master/retrigger/README.md)
        """
        if ctx.guild.id in self.triggers and name in self.triggers[ctx.guild.id]:
            return await self._already_exists(ctx, name)
        guild = ctx.guild
        author = ctx.author.id if isinstance(ctx, commands.Context) else ctx.user.id
        new_trigger = Trigger(
            name,
            regex,
            [TriggerResponse.rename],
            author,
            text=text,
            created_at=ctx.message.id if isinstance(ctx, commands.Context) else ctx.id,
        )
        if ctx.guild.id not in self.triggers:
            self.triggers[ctx.guild.id] = {}
        self.triggers[ctx.guild.id][new_trigger.name] = new_trigger
        trigger_list = await self.config.guild(guild).trigger_list()
        trigger_list[name] = await new_trigger.to_json()
        await self.config.guild(guild).trigger_list.set(trigger_list)
        await self._trigger_set(ctx, name)

    @retrigger.command()
    @checks.mod_or_permissions(manage_messages=True)
    @commands.bot_has_permissions(attach_files=True)
    async def image(
        self, ctx: commands.Context, name: str, regex: ValidRegex, image_url: str = None
    ) -> None:
        """
        Add an image/file response trigger

        `<name>` name of the trigger
        `<regex>` the regex that will determine when to respond
        `image_url` optional image_url if none is provided the bot will ask to upload an image

        See https://regex101.com/ for help building a regex pattern.
        See `[p]retrigger explain` or click the link below for more details.
        [For more details click here.](https://github.com/TrustyJAID/Trusty-cogs/blob/master/retrigger/README.md)
        """
        if ctx.guild.id in self.triggers and name in self.triggers[ctx.guild.id]:
            return await self._already_exists(ctx, name)
        guild = ctx.guild
        author = ctx.author.id if isinstance(ctx, commands.Context) else ctx.user.id
        if ctx.message.attachments != []:
            attachment_url = ctx.message.attachments[0].url
            filename = await self.save_image_location(attachment_url, guild)
            if not filename:
                await ctx.send(_("That is not a valid file link."))
                return
        elif image_url is not None:
            filename = await self.save_image_location(image_url, guild)
            if not filename:
                await ctx.send(_("That is not a valid file link."))
                return
        else:
            msg = await self.wait_for_image(ctx)
            if not msg or not msg.attachments:
                return
            image_url = msg.attachments[0].url
            filename = await self.save_image_location(image_url, guild)
            if not filename:
                await ctx.send(_("That is not a valid file link."))
                return
        new_trigger = Trigger(
            name,
            regex,
            [TriggerResponse.image],
            author,
            image=filename,
            created_at=ctx.message.id if isinstance(ctx, commands.Context) else ctx.id,
        )
        if ctx.guild.id not in self.triggers:
            self.triggers[ctx.guild.id] = {}
        self.triggers[ctx.guild.id][new_trigger.name] = new_trigger
        trigger_list = await self.config.guild(guild).trigger_list()
        trigger_list[name] = await new_trigger.to_json()
        await self.config.guild(guild).trigger_list.set(trigger_list)
        await self._trigger_set(ctx, name)

    @retrigger.command(aliases=["randimage", "randimg", "rimage", "rimg"])
    @checks.mod_or_permissions(manage_messages=True)
    @commands.bot_has_permissions(attach_files=True)
    async def randomimage(self, ctx: commands.Context, name: str, regex: ValidRegex) -> None:
        """
        Add a random image/file response trigger

        `<name>` name of the trigger
        `<regex>` the regex that will determine when to respond

        See https://regex101.com/ for help building a regex pattern.
        See `[p]retrigger explain` or click the link below for more details.
        [For more details click here.](https://github.com/TrustyJAID/Trusty-cogs/blob/master/retrigger/README.md)
        """
        if ctx.guild.id in self.triggers and name in self.triggers[ctx.guild.id]:
            return await self._already_exists(ctx, name)
        guild = ctx.guild
        author = ctx.author.id if isinstance(ctx, commands.Context) else ctx.user.id
        filename = await self.wait_for_multiple_images(ctx)

        new_trigger = Trigger(
            name,
            regex,
            [TriggerResponse.randimage],
            author,
            image=filename,
            created_at=ctx.message.id if isinstance(ctx, commands.Context) else ctx.id,
        )
        if ctx.guild.id not in self.triggers:
            self.triggers[ctx.guild.id] = {}
        self.triggers[ctx.guild.id][new_trigger.name] = new_trigger
        trigger_list = await self.config.guild(guild).trigger_list()
        trigger_list[name] = await new_trigger.to_json()
        await self.config.guild(guild).trigger_list.set(trigger_list)
        await self._trigger_set(ctx, name)

    @retrigger.command()
    @checks.mod_or_permissions(manage_messages=True)
    @commands.bot_has_permissions(attach_files=True)
    async def imagetext(
        self,
        ctx: commands.Context,
        name: str,
        regex: ValidRegex,
        text: str,
        image_url: str = None,
    ) -> None:
        """
        Add an image/file response with text trigger

        `<name>` name of the trigger
        `<regex>` the regex that will determine when to respond
        `<text>` the triggered text response
        `[image_url]` optional image_url if none is provided the bot will ask to upload an image

        See https://regex101.com/ for help building a regex pattern.
        See `[p]retrigger explain` or click the link below for more details.
        [For more details click here.](https://github.com/TrustyJAID/Trusty-cogs/blob/master/retrigger/README.md)
        """
        if ctx.guild.id in self.triggers and name in self.triggers[ctx.guild.id]:
            return await self._already_exists(ctx, name)
        guild = ctx.guild
        author = ctx.author.id if isinstance(ctx, commands.Context) else ctx.user.id
        if ctx.message.attachments != []:
            attachment_url = ctx.message.attachments[0].url
            filename = await self.save_image_location(attachment_url, guild)
        if image_url is not None:
            filename = await self.save_image_location(image_url, guild)
            if not filename:
                await ctx.send(_("That is not a valid file link."))
                return
        else:
            msg = await self.wait_for_image(ctx)
            if not msg or not msg.attachments:
                return
            image_url = msg.attachments[0].url
            filename = await self.save_image_location(image_url, guild)
            if not filename:
                await ctx.send(_("That is not a valid file link."))
                return
        new_trigger = Trigger(
            name,
            regex,
            [TriggerResponse.image],
            author,
            image=filename,
            text=text,
            created_at=ctx.message.id if isinstance(ctx, commands.Context) else ctx.id,
        )
        if ctx.guild.id not in self.triggers:
            self.triggers[ctx.guild.id] = {}
        self.triggers[ctx.guild.id][new_trigger.name] = new_trigger
        trigger_list = await self.config.guild(guild).trigger_list()
        trigger_list[name] = await new_trigger.to_json()
        await self.config.guild(guild).trigger_list.set(trigger_list)
        await self._trigger_set(ctx, name)

    @retrigger.command()
    @checks.mod_or_permissions(manage_messages=True)
    @commands.bot_has_permissions(attach_files=True)
    @commands.check(lambda ctx: ctx.command.cog.ALLOW_RESIZE)
    async def resize(
        self, ctx: commands.Context, name: str, regex: ValidRegex, image_url: str = None
    ) -> None:
        """
        Add an image to resize in response to a trigger
        this will attempt to resize the image based on length of matching regex

        `<name>` name of the trigger
        `<regex>` the regex that will determine when to respond
        `[image_url]` optional image_url if none is provided the bot will ask to upload an image

        See https://regex101.com/ for help building a regex pattern.
        See `[p]retrigger explain` or click the link below for more details.
        [For more details click here.](https://github.com/TrustyJAID/Trusty-cogs/blob/master/retrigger/README.md)
        """
        if ctx.guild.id in self.triggers and name in self.triggers[ctx.guild.id]:
            return await self._already_exists(ctx, name)
        guild = ctx.guild
        author = ctx.author.id if isinstance(ctx, commands.Context) else ctx.user.id
        if ctx.message.attachments != []:
            attachment_url = ctx.message.attachments[0].url
            filename = await self.save_image_location(attachment_url, guild)
            if not filename:
                await ctx.send(_("That is not a valid file link."))
                return
        elif image_url is not None:
            filename = await self.save_image_location(image_url, guild)
            if not filename:
                await ctx.send(_("That is not a valid file link."))
                return
        else:
            msg = await self.wait_for_image(ctx)
            if not msg or not msg.attachments:
                return
            image_url = msg.attachments[0].url
            filename = await self.save_image_location(image_url, guild)
            if not filename:
                await ctx.send(_("That is not a valid file link."))
                return
        new_trigger = Trigger(
            name,
            regex,
            [TriggerResponse.resize],
            author,
            image=filename,
            created_at=ctx.message.id if isinstance(ctx, commands.Context) else ctx.id,
        )
        if ctx.guild.id not in self.triggers:
            self.triggers[ctx.guild.id] = {}
        self.triggers[ctx.guild.id][new_trigger.name] = new_trigger
        trigger_list = await self.config.guild(guild).trigger_list()
        trigger_list[name] = await new_trigger.to_json()
        await self.config.guild(guild).trigger_list.set(trigger_list)
        await self._trigger_set(ctx, name)

    @retrigger.command()
    @checks.mod_or_permissions(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    async def ban(self, ctx: commands.Context, name: str, regex: ValidRegex) -> None:
        """
        Add a trigger to ban users for saying specific things found with regex
        This respects hierarchy so ensure the bot role is lower in the list
        than mods and admin so they don't get banned by accident

        `<name>` name of the trigger
        `<regex>` the regex that will determine when to respond

        See https://regex101.com/ for help building a regex pattern.
        See `[p]retrigger explain` or click the link below for more details.
        [For more details click here.](https://github.com/TrustyJAID/Trusty-cogs/blob/master/retrigger/README.md)
        """
        if ctx.guild.id in self.triggers and name in self.triggers[ctx.guild.id]:
            return await self._already_exists(ctx, name)
        guild = ctx.guild
        author = ctx.author.id if isinstance(ctx, commands.Context) else ctx.user.id
        new_trigger = Trigger(
            name,
            regex,
            [TriggerResponse.ban],
            author,
            created_at=ctx.message.id if isinstance(ctx, commands.Context) else ctx.id,
            check_edits=True,
        )
        if ctx.guild.id not in self.triggers:
            self.triggers[ctx.guild.id] = {}
        self.triggers[ctx.guild.id][new_trigger.name] = new_trigger
        trigger_list = await self.config.guild(guild).trigger_list()
        trigger_list[name] = await new_trigger.to_json()
        await self.config.guild(guild).trigger_list.set(trigger_list)
        await self._trigger_set(ctx, name)

    @retrigger.command()
    @checks.mod_or_permissions(kick_members=True)
    @commands.bot_has_permissions(kick_members=True)
    async def kick(self, ctx: commands.Context, name: str, regex: ValidRegex) -> None:
        """
        Add a trigger to kick users for saying specific things found with regex
        This respects hierarchy so ensure the bot role is lower in the list
        than mods and admin so they don't get kicked by accident

        `<name>` name of the trigger
        `<regex>` the regex that will determine when to respond

        See https://regex101.com/ for help building a regex pattern.
        See `[p]retrigger explain` or click the link below for more details.
        [For more details click here.](https://github.com/TrustyJAID/Trusty-cogs/blob/master/retrigger/README.md)
        """
        if ctx.guild.id in self.triggers and name in self.triggers[ctx.guild.id]:
            return await self._already_exists(ctx, name)
        guild = ctx.guild
        author = ctx.author.id if isinstance(ctx, commands.Context) else ctx.user.id
        new_trigger = Trigger(
            name,
            regex,
            [TriggerResponse.kick],
            author,
            created_at=ctx.message.id if isinstance(ctx, commands.Context) else ctx.id,
            check_edits=True,
        )
        if ctx.guild.id not in self.triggers:
            self.triggers[ctx.guild.id] = {}
        self.triggers[ctx.guild.id][new_trigger.name] = new_trigger
        trigger_list = await self.config.guild(guild).trigger_list()
        trigger_list[name] = await new_trigger.to_json()
        await self.config.guild(guild).trigger_list.set(trigger_list)
        await self._trigger_set(ctx, name)

    @retrigger.command()
    @checks.mod_or_permissions(manage_messages=True)
    @commands.bot_has_permissions(add_reactions=True)
    async def react(
        self,
        ctx: commands.Context,
        name: str,
        regex: ValidRegex,
        emojis: commands.Greedy[ValidEmoji],
    ) -> None:
        """
        Add a reaction trigger

        `<name>` name of the trigger
        `<regex>` the regex that will determine when to respond
        `emojis` the emojis to react with when triggered separated by spaces

        See https://regex101.com/ for help building a regex pattern.
        See `[p]retrigger explain` or click the link below for more details.
        [For more details click here.](https://github.com/TrustyJAID/Trusty-cogs/blob/master/retrigger/README.md)
        """
        if ctx.guild.id in self.triggers and name in self.triggers[ctx.guild.id]:
            return await self._already_exists(ctx, name)
        guild = ctx.guild
        author = ctx.author.id if isinstance(ctx, commands.Context) else ctx.user.id
        new_trigger = Trigger(
            name,
            regex,
            [TriggerResponse.react],
            author,
            text=emojis,
            created_at=ctx.message.id if isinstance(ctx, commands.Context) else ctx.id,
        )
        if ctx.guild.id not in self.triggers:
            self.triggers[ctx.guild.id] = {}
        self.triggers[ctx.guild.id][new_trigger.name] = new_trigger
        trigger_list = await self.config.guild(guild).trigger_list()
        trigger_list[name] = await new_trigger.to_json()
        await self.config.guild(guild).trigger_list.set(trigger_list)
        await self._trigger_set(ctx, name)

    @retrigger.command()
    @checks.mod_or_permissions(manage_messages=True)
    @commands.bot_has_permissions(add_reactions=True)
    async def publish(self, ctx: commands.Context, name: str, regex: ValidRegex) -> None:
        """
        Add a trigger to automatically publish content in news channels.

        `<name>` name of the trigger
        `<regex>` the regex that will determine when to respond

        See https://regex101.com/ for help building a regex pattern.
        See `[p]retrigger explain` or click the link below for more details.
        [For more details click here.](https://github.com/TrustyJAID/Trusty-cogs/blob/master/retrigger/README.md)
        """
        if ctx.guild.id in self.triggers and name in self.triggers[ctx.guild.id]:
            return await self._already_exists(ctx, name)
        guild = ctx.guild
        author = ctx.author.id if isinstance(ctx, commands.Context) else ctx.user.id
        new_trigger = Trigger(
            name,
            regex,
            [TriggerResponse.publish],
            author,
            created_at=ctx.message.id if isinstance(ctx, commands.Context) else ctx.id,
        )
        if ctx.guild.id not in self.triggers:
            self.triggers[ctx.guild.id] = {}
        self.triggers[ctx.guild.id][new_trigger.name] = new_trigger
        trigger_list = await self.config.guild(guild).trigger_list()
        trigger_list[name] = await new_trigger.to_json()
        await self.config.guild(guild).trigger_list.set(trigger_list)
        await self._trigger_set(ctx, name)

    @retrigger.command(aliases=["cmd"])
    @checks.mod_or_permissions(manage_messages=True)
    async def command(
        self, ctx: commands.Context, name: str, regex: ValidRegex, *, command: str
    ) -> None:
        """
        Add a command trigger

        `<name>` name of the trigger
        `<regex>` the regex that will determine when to respond
        `<command>` the command that will be triggered, do not add [p] prefix

        See https://regex101.com/ for help building a regex pattern.
        See `[p]retrigger explain` or click the link below for more details.
        [For more details click here.](https://github.com/TrustyJAID/Trusty-cogs/blob/master/retrigger/README.md)
        """
        if ctx.guild.id in self.triggers and name in self.triggers[ctx.guild.id]:
            return await self._already_exists(ctx, name)
        cmd_list = command.split(" ")
        existing_cmd = self.bot.get_command(cmd_list[0])
        if existing_cmd is None:
            await ctx.send(command + _(" doesn't seem to be an available command."))
            return
        guild = ctx.guild
        author = ctx.author.id if isinstance(ctx, commands.Context) else ctx.user.id
        new_trigger = Trigger(
            name,
            regex,
            [TriggerResponse.command],
            author,
            text=command,
            created_at=ctx.message.id if isinstance(ctx, commands.Context) else ctx.id,
        )
        if ctx.guild.id not in self.triggers:
            self.triggers[ctx.guild.id] = {}
        self.triggers[ctx.guild.id][new_trigger.name] = new_trigger
        trigger_list = await self.config.guild(guild).trigger_list()
        trigger_list[name] = await new_trigger.to_json()
        await self.config.guild(guild).trigger_list.set(trigger_list)
        await self._trigger_set(ctx, name)

    @retrigger.command(aliases=["cmdmock"], hidden=True)
    @checks.admin_or_permissions(administrator=True)
    async def mock(
        self, ctx: commands.Context, name: str, regex: ValidRegex, *, command: str
    ) -> None:
        """
        Add a trigger for command as if you used the command

        `<name>` name of the trigger
        `<regex>` the regex that will determine when to respond
        `<command>` the command that will be triggered, do not add [p] prefix
        **Warning:** This function can let other users run a command on your behalf,
        use with caution.

        See https://regex101.com/ for help building a regex pattern.
        See `[p]retrigger explain` or click the link below for more details.
        [For more details click here.](https://github.com/TrustyJAID/Trusty-cogs/blob/master/retrigger/README.md)
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
            await ctx.send(_("Not creating trigger."))
            return
        if not pred.result:
            await ctx.send(_("Not creating trigger."))
            return
        if ctx.guild.id in self.triggers and name in self.triggers[ctx.guild.id]:
            return await self._already_exists(ctx, name)
        cmd_list = command.split(" ")
        existing_cmd = self.bot.get_command(cmd_list[0])
        if existing_cmd is None:
            await ctx.send(command + _(" doesn't seem to be an available command."))
            return
        guild = ctx.guild
        author = ctx.author.id if isinstance(ctx, commands.Context) else ctx.user.id
        new_trigger = Trigger(
            name,
            regex,
            [TriggerResponse.mock],
            author,
            text=command,
            created_at=ctx.message.id if isinstance(ctx, commands.Context) else ctx.id,
        )
        if ctx.guild.id not in self.triggers:
            self.triggers[ctx.guild.id] = {}
        self.triggers[ctx.guild.id][new_trigger.name] = new_trigger
        trigger_list = await self.config.guild(guild).trigger_list()
        trigger_list[name] = await new_trigger.to_json()
        await self.config.guild(guild).trigger_list.set(trigger_list)
        await self._trigger_set(ctx, name)

    @retrigger.command(aliases=["deletemsg"])
    @checks.mod_or_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True)
    async def filter(
        self,
        ctx: commands.Context,
        name: str,
        check_filenames: Optional[bool] = False,
        *,
        regex: str,
    ) -> None:
        """
        Add a trigger to delete a message

        `<name>` name of the trigger
        `<regex>` the regex that will determine when to respond

        See https://regex101.com/ for help building a regex pattern.
        See `[p]retrigger explain` or click the link below for more details.
        [For more details click here.](https://github.com/TrustyJAID/Trusty-cogs/blob/master/retrigger/README.md)
        """
        if ctx.guild.id in self.triggers and name in self.triggers[ctx.guild.id]:
            return await self._already_exists(ctx, name)
        guild = ctx.guild
        author = ctx.author.id if isinstance(ctx, commands.Context) else ctx.user.id
        new_trigger = Trigger(
            name,
            regex,
            [TriggerResponse.delete],
            author,
            read_filenames=check_filenames,
            created_at=ctx.message.id if isinstance(ctx, commands.Context) else ctx.id,
            check_edits=True,
        )
        if ctx.guild.id not in self.triggers:
            self.triggers[ctx.guild.id] = {}
        self.triggers[ctx.guild.id][new_trigger.name] = new_trigger
        trigger_list = await self.config.guild(guild).trigger_list()
        trigger_list[name] = await new_trigger.to_json()
        await self.config.guild(guild).trigger_list.set(trigger_list)
        await self._trigger_set(ctx, name)

    @retrigger.command()
    @checks.mod_or_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def addrole(
        self,
        ctx: commands.Context,
        name: str,
        regex: ValidRegex,
        roles: commands.Greedy[discord.Role],
    ) -> None:
        """
        Add a trigger to add a role

        `<name>` name of the trigger
        `<regex>` the regex that will determine when to respond
        `[role...]` the roles applied when the regex pattern matches space separated

        See https://regex101.com/ for help building a regex pattern.
        See `[p]retrigger explain` or click the link below for more details.
        [For more details click here.](https://github.com/TrustyJAID/Trusty-cogs/blob/master/retrigger/README.md)
        """
        if ctx.guild.id in self.triggers and name in self.triggers[ctx.guild.id]:
            return await self._already_exists(ctx, name)
        for role in roles:
            if role >= ctx.me.top_role:
                await ctx.send(_("I can't assign roles higher than my own."))
                return
            if ctx.author.id == ctx.guild.owner_id:
                continue
            if role >= ctx.author.top_role:
                await ctx.send(_("I can't assign roles higher than you are able to assign."))
                return
        role_ids = [r.id for r in roles]
        guild = ctx.guild
        author = ctx.author.id if isinstance(ctx, commands.Context) else ctx.user.id
        new_trigger = Trigger(
            name,
            regex,
            [TriggerResponse.add_role],
            author,
            text=role_ids,
            created_at=ctx.message.id if isinstance(ctx, commands.Context) else ctx.id,
        )
        if ctx.guild.id not in self.triggers:
            self.triggers[ctx.guild.id] = {}
        self.triggers[ctx.guild.id][new_trigger.name] = new_trigger
        trigger_list = await self.config.guild(guild).trigger_list()
        trigger_list[name] = await new_trigger.to_json()
        await self.config.guild(guild).trigger_list.set(trigger_list)
        await self._trigger_set(ctx, name)

    @retrigger.command()
    @checks.mod_or_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def removerole(
        self,
        ctx: commands.Context,
        name: str,
        regex: ValidRegex,
        roles: commands.Greedy[discord.Role],
    ) -> None:
        """
        Add a trigger to remove a role

        `<name>` name of the trigger
        `<regex>` the regex that will determine when to respond
        `[role...]` the roles applied when the regex pattern matches space separated

        See https://regex101.com/ for help building a regex pattern.
        See `[p]retrigger explain` or click the link below for more details.
        [For more details click here.](https://github.com/TrustyJAID/Trusty-cogs/blob/master/retrigger/README.md)
        """
        if ctx.guild.id in self.triggers and name in self.triggers[ctx.guild.id]:
            return await self._already_exists(ctx, name)
        for role in roles:
            if role >= ctx.me.top_role:
                await ctx.send(_("I can't remove roles higher than my own."))
                return
            if ctx.author.id == ctx.guild.owner_id:
                continue
            if role >= ctx.author.top_role:
                await ctx.send(_("I can't remove roles higher than you are able to remove."))
                return
        role_ids = [r.id for r in roles]
        guild = ctx.guild
        author = ctx.author.id if isinstance(ctx, commands.Context) else ctx.user.id
        new_trigger = Trigger(
            name,
            regex,
            [TriggerResponse.remove_role],
            author,
            text=role_ids,
            created_at=ctx.message.id if isinstance(ctx, commands.Context) else ctx.id,
        )
        if ctx.guild.id not in self.triggers:
            self.triggers[ctx.guild.id] = {}
        self.triggers[ctx.guild.id][new_trigger.name] = new_trigger
        trigger_list = await self.config.guild(guild).trigger_list()
        trigger_list[name] = await new_trigger.to_json()
        await self.config.guild(guild).trigger_list.set(trigger_list)
        await self._trigger_set(ctx, name)

    @retrigger.command()
    @checks.admin_or_permissions(administrator=True)
    async def multi(
        self,
        ctx: commands.Context,
        name: str,
        regex: ValidRegex,
        multi_response: commands.Greedy[MultiResponse],
    ) -> None:
        """
        Add a multiple response trigger

        `<name>` name of the trigger
        `<regex>` the regex that will determine when to respond
        `[multi_response...]` the list of actions the bot will perform

        Multiple responses start with the name of the action which
        must be one of the listed options below, followed by a `;`
        if there is a followup response add a space for the next trigger response.
        If you want to add or remove multiple roles those may be
        followed up with additional `;` separations.
        e.g. `[p]retrigger multi test \\btest\\b \"dm;You said a bad word!\"
        filter "remove_role;Regular Member" add_role;Timeout`
        Will attempt to DM the user, delete their message, remove their
        `@Regular Member` role and add the `@Timeout` role simultaneously.

        Available options:
        dm
        dmme
        remove_role
        add_role
        ban
        kick
        text
        filter or delete
        react
        rename
        command

        See https://regex101.com/ for help building a regex pattern.
        See `[p]retrigger explain` or click the link below for more details.
        """
        # log.info(multi_response)
        # return
        if ctx.guild.id in self.triggers and name in self.triggers[ctx.guild.id]:
            return await self._already_exists(ctx, name)
        guild = ctx.guild
        author = ctx.author.id if isinstance(ctx, commands.Context) else ctx.user.id
        if not [i[0] for i in multi_response]:
            await ctx.send(_("You have no actions provided for this trigger."))
            return
        new_trigger = Trigger(
            name,
            regex,
            [i[0] for i in multi_response],
            author,
            multi_payload=multi_response,
            created_at=ctx.message.id if isinstance(ctx, commands.Context) else ctx.id,
        )
        if ctx.guild.id not in self.triggers:
            self.triggers[ctx.guild.id] = {}
        self.triggers[ctx.guild.id][new_trigger.name] = new_trigger
        trigger_list = await self.config.guild(guild).trigger_list()
        trigger_list[name] = await new_trigger.to_json()
        await self.config.guild(guild).trigger_list.set(trigger_list)
        await self._trigger_set(ctx, name)
