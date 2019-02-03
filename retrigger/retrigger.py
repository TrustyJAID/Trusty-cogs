import discord
from redbot.core import commands, checks, Config, modlog
from redbot.core.data_manager import cog_data_path
from redbot.core.i18n import Translator, cog_i18n
from typing import Union
import logging
import os

from .converters import *
from .triggerhandler import TriggerHandler
from multiprocessing.pool import Pool

log = logging.getLogger("red.ReTrigger")
_ = Translator("ReTrigger", __file__)


@cog_i18n(_)
class ReTrigger(TriggerHandler, commands.Cog):
    """
        Trigger bot events using regular expressions
    """

    __author__ = "TrustyJAID"
    __version__ = "2.0.3"

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, 964565433247)
        default_guild = {"trigger_list": {}, "allow_multiple": False, "modlog": "default"}
        self.config.register_guild(**default_guild)
        self.re_pool = Pool()

    def __unload(self):
        self.re_pool.close()

    @commands.group()
    @commands.guild_only()
    async def retrigger(self, ctx):
        """
            Setup automatic triggers based on regular expressions

            https://regex101.com/ is a good place to test regex
        """
        pass

    async def initialize(self):
        """
            Force fixup triggers to the new data scheme on load
        """
        for guild_id in await self.config.all_guilds():
            guild = self.bot.get_guild(int(guild_id))
            if guild is None:
                await self.config._clear_scope(Config.GUILD, str(guild_id))
                continue
            triggers = await self.config.guild(guild).trigger_list()
            for trigger in await self.config.guild(guild).trigger_list():
                try:
                    t = Trigger.from_json(triggers[trigger])
                except Exception as e:
                    log.error(
                        _("Removing {trigger} from {guild} ({guild.id})").format(
                            trigger=trigger, guild=guild
                        ),
                        exc_info=True,
                    )
                    if triggers[trigger]["image"] is not None:
                        image = triggers[trigger]["image"]
                        path = str(cog_data_path(self)) + f"/{guild.id}/{image}"
                        try:
                            os.remove(path)
                        except Exception as e:
                            msg = _("Error deleting saved image in {guild}").format(guild=guild.id)
                            log.error(msg, exc_info=True)
                            pass
                    del triggers[trigger]
                    continue
                triggers[t.name] = t.to_json()
            await self.config.guild(guild).trigger_list.set(triggers)

    @retrigger.group()
    @checks.mod_or_permissions(manage_messages=True)
    async def blacklist(self, ctx):
        """
            Set blacklist options for retrigger
        """
        pass

    @retrigger.group()
    @checks.mod_or_permissions(manage_messages=True)
    async def whitelist(self, ctx):
        """
            Set whitelist options for retrigger
        """
        pass

    @retrigger.command(hidden=True)
    @checks.mod_or_permissions(administrator=True)
    async def allowmultiple(self, ctx):
        """
            Toggle multiple triggers to respond at once
        """
        if await self.config.guild(ctx.guild).allow_multiple():
            await self.config.guild(ctx.guild).allow_multiple.set(False)
            msg = _("Multiple responses disabled, " "only the first trigger will happen.")
            await ctx.send(msg)
        else:
            await self.config.guild(ctx.guild).allow_multiple.set(True)
            msg = _("Multiple responses enabled, " "all triggers will occur.")
            await ctx.send(msg)

    @retrigger.command()
    @checks.mod_or_permissions(manage_channels=True)
    async def modlog(self, ctx, channel: Union[discord.TextChannel, str]):
        """
            Set the modlog channel for filtered words

            `channel` The channel you would like filtered word notifications to go
            Use `none` or `clear` to not show any modlogs
            User `default` to use the built in modlog channel
        """
        if type(channel) is str:
            if channel.lower() in ["none", "clear"]:
                channel = None
            elif channel.lower() in ["default"]:
                channel = "default"
            else:
                await ctx.send(_('Channel "{channel}" not found.').format(channel=channel))
                return
            await self.config.guild(ctx.guild).modlog.set(channel)
        else:
            await self.config.guild(ctx.guild).modlog.set(channel.id)
        await ctx.send(_("Modlog set to {channel}").format(channel=channel))

    @retrigger.command()
    @checks.mod_or_permissions(manage_messages=True)
    async def cooldown(self, ctx, trigger: TriggerExists, time: int, style="guild"):
        """
            Set cooldown options for retrigger

            `trigger` is the name of the trigger
            `time` is a time in seconds until the trigger will run again
            set a time of 0 or less to remove the cooldown
            `style` must be either `guild`, `server`, `channel`, `user`, or `member`
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
            msg = _("Cooldown for Trigger `") + name + _("` reset.")
        trigger_list = await self.config.guild(ctx.guild).trigger_list()
        trigger.cooldown = cooldown
        trigger_list[trigger.name] = trigger.to_json()
        await self.config.guild(ctx.guild).trigger_list.set(trigger_list)
        await ctx.send(msg.format(time=time, style=style, name=trigger.name))

    @whitelist.command(name="add")
    @checks.mod_or_permissions(manage_messages=True)
    async def whitelist_add(self, ctx, trigger: TriggerExists, channel_user_role: ChannelUserRole):
        """
            Add channel to triggers whitelist

            `trigger` is the name of the trigger
            `channel_user_role` is the channel, user or role to whitelist
        """
        if type(trigger) is str:
            return await ctx.send(_("Trigger `{name}` doesn't exist.").format(name=trigger))
        if channel_user_role.id not in trigger.whitelist:
            trigger_list = await self.config.guild(ctx.guild).trigger_list()
            trigger.whitelist.append(channel_user_role.id)
            trigger_list[trigger.name] = trigger.to_json()
            await self.config.guild(ctx.guild).trigger_list.set(trigger_list)
            msg = _("Trigger {name} added `{list_type}` to its whitelist.")
        else:
            msg = _("Trigger `{name}` already has {list_type} whitelisted.")
        await ctx.send(msg.format(list_type=channel_user_role.name, name=trigger.name))

    @whitelist.command(name="remove", aliases=["rem", "del"])
    @checks.mod_or_permissions(manage_messages=True)
    async def whitelist_remove(
        self, ctx, trigger: TriggerExists, channel_user_role: ChannelUserRole
    ):
        """
            Remove channel from triggers whitelist

            `trigger` is the name of the trigger
            `channel_user_role` is the channel, user or role to remove from the whitelist
        """
        if type(trigger) is str:
            return await ctx.send(_("Trigger `{name}` doesn't exist.").format(name=trigger))
        if channel_user_role.id in trigger.whitelist:
            trigger_list = await self.config.guild(ctx.guild).trigger_list()
            trigger.whitelist.remove(channel_user_role.id)
            trigger_list[trigger.name] = trigger.to_json()
            await self.config.guild(ctx.guild).trigger_list.set(trigger_list)
            msg = _("Trigger {name} removed `{list_type}` from its whitelist.")
        else:
            msg = _("Trigger `{name}` does not have {list_type} whitelisted.")
        await ctx.send(msg.format(list_type=channel_user_role.name, name=trigger.name))

    @blacklist.command(name="add")
    @checks.mod_or_permissions(manage_messages=True)
    async def blacklist_add(self, ctx, trigger: TriggerExists, channel_user_role: ChannelUserRole):
        """
            Add channel to triggers blacklist

            `trigger` is the name of the trigger
            `channel_user_role` is the channel, user or role to blacklist
        """
        if type(trigger) is str:
            return await ctx.send(_("Trigger `{name}` doesn't exist.").format(name=trigger))
        if channel_user_role.id not in trigger.blacklist:
            trigger_list = await self.config.guild(ctx.guild).trigger_list()
            trigger.blacklist.append(channel_user_role.id)
            trigger_list[trigger.name] = trigger.to_json()
            await self.config.guild(ctx.guild).trigger_list.set(trigger_list)
            msg = _("Trigger {name} added `{list_type}` to its blacklist.")
        else:
            msg = _("Trigger `{name}` already has {list_type} blacklisted.")
        await ctx.send(msg.format(list_type=channel_user_role.name, name=trigger.name))

    @blacklist.command(name="remove", aliases=["rem", "del"])
    @checks.mod_or_permissions(manage_messages=True)
    async def blacklist_remove(
        self, ctx, trigger: TriggerExists, channel_user_role: ChannelUserRole
    ):
        """
            Remove channel from triggers blacklist

            `trigger` is the name of the trigger
            `channel_user_role` is the channel, user or role to remove from the blacklist
        """
        if type(trigger) is str:
            return await ctx.send(_("Trigger `{name}` doesn't exist.").format(name=trigger))
        if channel_user_role.id in trigger.blacklist:
            trigger_list = await self.config.guild(ctx.guild).trigger_list()
            trigger.blacklist.remove(channel_user_role.id)
            trigger_list[trigger.name] = trigger.to_json()
            await self.config.guild(ctx.guild).trigger_list.set(trigger_list)
            msg = _("Trigger {name} removed `{list_type}` from its blacklist.")
        else:
            msg = _("Trigger `{name}` does not have {list_type} blacklisted.")
        await ctx.send(msg.format(list_type=channel_user_role.name, name=trigger.name))

    @retrigger.command()
    async def list(self, ctx, trigger: TriggerExists = None):
        """
            List information about triggers

            `trigger` if supplied provides information about named trigger
        """
        if trigger:
            if type(trigger) is str:
                return await ctx.send(_("Trigger `{name}` doesn't exist.").format(name=trigger))
            else:
                return await self.trigger_menu(ctx, [[trigger.to_json()]])
        trigger_dict = await self.config.guild(ctx.guild).trigger_list()
        trigger_list = [trigger_dict[name] for name in trigger_dict]
        if trigger_list == []:
            msg = _("There are no triggers setup on this server.")
            await ctx.send(msg)
            return
        post_list = [trigger_list[i : i + 10] for i in range(0, len(trigger_list), 10)]
        await self.trigger_menu(ctx, post_list)

    @retrigger.command(aliases=["del", "rem", "delete"])
    @checks.mod_or_permissions(manage_messages=True)
    async def remove(self, ctx, trigger: TriggerExists):
        """
            Remove a specified trigger

            `trigger` is the name of the trigger
        """
        if type(trigger) is Trigger:
            await self.remove_trigger(ctx.guild, trigger.name)
            await ctx.send(_("Trigger `") + trigger.name + _("` removed."))
        else:
            await ctx.send(_("Trigger `") + trigger + _("` doesn't exist."))

    @retrigger.command()
    @checks.mod_or_permissions(manage_messages=True)
    async def text(self, ctx, name: TriggerExists, regex: ValidRegex, *, text: str):
        """
            Add a text response trigger

            `name` name of the trigger
            `regex` the regex that will determine when to respond
            `text` response of the trigger
            See https://regex101.com/ for help building a regex pattern
            Example for simple search: `"\\bthis matches"` the whole phrase only
            For case insensitive searches add `(?i)` at the start of the regex
        """
        if type(name) != str:
            msg = _("{name} is already a trigger name").format(name=name.name)
            return await ctx.send(msg)
        guild = ctx.guild
        author = ctx.message.author.id
        new_trigger = Trigger(name, regex, ["text"], author, 0, None, text, [], [], {}, [])
        trigger_list = await self.config.guild(guild).trigger_list()
        trigger_list[name] = new_trigger.to_json()
        await self.config.guild(guild).trigger_list.set(trigger_list)
        await ctx.send(_("Trigger `{name}` set.").format(name=name))

    @retrigger.command()
    @checks.mod_or_permissions(manage_messages=True)
    async def dm(self, ctx, name: TriggerExists, regex: ValidRegex, *, text: str):
        """
            Add a dm response trigger

            `name` name of the trigger
            `regex` the regex that will determine when to respond
            `text` response of the trigger
            See https://regex101.com/ for help building a regex pattern
            Example for simple search: `"\\bthis matches"` the whole phrase only
            For case insensitive searches add `(?i)` at the start of the regex
        """
        if type(name) != str:
            msg = _("{name} is already a trigger name").format(name=name.name)
            return await ctx.send(msg)
        guild = ctx.guild
        author = ctx.message.author.id
        new_trigger = Trigger(name, regex, ["dm"], author, 0, None, text, [], [], {}, [])
        trigger_list = await self.config.guild(guild).trigger_list()
        trigger_list[name] = new_trigger.to_json()
        await self.config.guild(guild).trigger_list.set(trigger_list)
        await ctx.send(_("Trigger `{name}` set.").format(name=name))

    @retrigger.command()
    @checks.mod_or_permissions(manage_messages=True)
    @commands.bot_has_permissions(attach_files=True)
    async def image(self, ctx, name: TriggerExists, regex: ValidRegex, image_url: str = None):
        """
            Add an image/file response trigger

            `name` name of the trigger
            `regex` the regex that will determine when to respond
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
            image_url = ctx.message.attachments[0].url
            filename = await self.save_image_location(image_url, guild)
        if image_url is not None:
            filename = await self.save_image_location(image_url, guild)
        else:
            msg = await self.wait_for_image(ctx)
            if not msg or not msg.attachments:
                return
            image_url = msg.attachments[0].url
            filename = await self.save_image_location(image_url, guild)

        new_trigger = Trigger(name, regex, ["image"], author, 0, filename, None, [], [], {}, [])
        trigger_list = await self.config.guild(guild).trigger_list()
        trigger_list[name] = new_trigger.to_json()
        await self.config.guild(guild).trigger_list.set(trigger_list)
        await ctx.send(_("Trigger `{name}` set.").format(name=name))

    @retrigger.command()
    @checks.mod_or_permissions(manage_messages=True)
    @commands.bot_has_permissions(attach_files=True)
    async def imagetext(
        self, ctx, name: TriggerExists, regex: ValidRegex, text: str, image_url: str = None
    ):
        """
            Add an image/file response with text trigger

            `name` name of the trigger
            `regex` the regex that will determine when to respond
            `text` the triggered text response
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
            image_url = ctx.message.attachments[0].url
            filename = await self.save_image_location(image_url, guild)
        if image_url is not None:
            filename = await self.save_image_location(image_url, guild)
        else:
            msg = await self.wait_for_image(ctx)
            if not msg or not msg.attachments:
                return
            image_url = msg.attachments[0].url
            filename = await self.save_image_location(image_url, guild)

        new_trigger = Trigger(name, regex, ["kick"], author, 0, filename, text, [], [], {}, [])
        trigger_list = await self.config.guild(guild).trigger_list()
        trigger_list[name] = new_trigger.to_json()
        await self.config.guild(guild).trigger_list.set(trigger_list)
        await ctx.send(_("Trigger `{name}` set.").format(name=name))

    @retrigger.command()
    @checks.mod_or_permissions(manage_messages=True)
    @commands.bot_has_permissions(attach_files=True)
    async def resize(self, ctx, name: TriggerExists, regex: ValidRegex, image_url: str = None):
        """
            Add an image to resize in response to a trigger
            this will attempt to resize the image based on length of matching regex

            `name` name of the trigger
            `regex` the regex that will determine when to respond
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
            image_url = ctx.message.attachments[0].url
            filename = await self.save_image_location(image_url, guild)
        if image_url is not None:
            filename = await self.save_image_location(image_url, guild)
        else:
            msg = await self.wait_for_image(ctx)
            if not msg or not msg.attachments:
                return
            image_url = msg.attachments[0].url
            filename = await self.save_image_location(image_url, guild)

        new_trigger = Trigger(name, regex, ["resize"], author, 0, filename, None, [], [], {}, [])
        trigger_list = await self.config.guild(guild).trigger_list()
        trigger_list[name] = new_trigger.to_json()
        await self.config.guild(guild).trigger_list.set(trigger_list)
        await ctx.send(_("Trigger `{name}` set.").format(name=name))

    @retrigger.command()
    @checks.mod_or_permissions(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    async def ban(self, ctx, name: TriggerExists, regex: str):
        """
            Add a trigger to ban users for saying specific things found with regex
            This respects hierarchy so ensure the bot role is lower in the list
            than mods and admin so they don't get banned by accident

            `name` name of the trigger
            `regex` the regex that will determine when to respond
            See https://regex101.com/ for help building a regex pattern
            Example for simple search: `"\\bthis matches"` the whole phrase only
            For case insensitive searches add `(?i)` at the start of the regex
        """
        if type(name) != str:
            msg = _("{name} is already a trigger name").format(name=name.name)
            return await ctx.send(msg)
        guild = ctx.guild
        author = ctx.message.author.id
        new_trigger = Trigger(name, regex, ["ban"], author, 0, None, None, [], [], {}, [])
        trigger_list = await self.config.guild(guild).trigger_list()
        trigger_list[name] = new_trigger.to_json()
        await self.config.guild(guild).trigger_list.set(trigger_list)
        await ctx.send(_("Trigger `{name}` set.").format(name=name))

    @retrigger.command()
    @checks.mod_or_permissions(kick_members=True)
    @commands.bot_has_permissions(kick_members=True)
    async def kick(self, ctx, name: TriggerExists, regex: str):
        """
            Add a trigger to kick users for saying specific things found with regex
            This respects hierarchy so ensure the bot role is lower in the list
            than mods and admin so they don't get kicked by accident

            `name` name of the trigger
            `regex` the regex that will determine when to respond
            See https://regex101.com/ for help building a regex pattern
            Example for simple search: `"\\bthis matches"` the whole phrase only
            For case insensitive searches add `(?i)` at the start of the regex
        """
        if type(name) != str:
            msg = _("{name} is already a trigger name").format(name=name.name)
            return await ctx.send(msg)
        guild = ctx.guild
        author = ctx.message.author.id
        new_trigger = Trigger(name, regex, ["kick"], author, 0, None, None, [], [], {}, [])
        trigger_list = await self.config.guild(guild).trigger_list()
        trigger_list[name] = new_trigger.to_json()
        await self.config.guild(guild).trigger_list.set(trigger_list)
        await ctx.send(_("Trigger `{name}` set.").format(name=name))

    @retrigger.command()
    @checks.mod_or_permissions(manage_messages=True)
    @commands.bot_has_permissions(add_reactions=True)
    async def react(self, ctx, name: TriggerExists, regex: ValidRegex, *emojis: ValidEmoji):
        """
            Add a reaction trigger

            `name` name of the trigger
            `regex` the regex that will determine when to respond
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
        new_trigger = Trigger(name, regex, ["react"], author, 0, None, emojis, [], [], {}, [])
        trigger_list = await self.config.guild(guild).trigger_list()
        trigger_list[name] = new_trigger.to_json()
        await self.config.guild(guild).trigger_list.set(trigger_list)
        await ctx.send(_("Trigger `{name}` set.").format(name=name))

    @retrigger.command(aliases=["cmd"])
    @checks.mod_or_permissions(manage_messages=True)
    async def command(self, ctx, name: TriggerExists, regex: ValidRegex, *, command: str):
        """
            Add a command trigger

            `name` name of the trigger
            `regex` the regex that will determine when to respond
            `command` the command that will be triggered, do add [p] prefix
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
        new_trigger = Trigger(name, regex, ["command"], author, 0, None, command, [], [], {}, [])
        trigger_list = await self.config.guild(guild).trigger_list()
        trigger_list[name] = new_trigger.to_json()
        await self.config.guild(guild).trigger_list.set(trigger_list)
        await ctx.send(_("Trigger `{name}` set.").format(name=name))

    @retrigger.command(aliases=["cmdmock"], hidden=True)
    @checks.is_owner()
    async def mock(self, ctx, name: TriggerExists, regex: ValidRegex, *, command: str):
        """
            Add a trigger for command as if you used the command

            `name` name of the trigger
            `regex` the regex that will determine when to respond
            `command` the command that will be triggered, do add [p] prefix
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
        new_trigger = Trigger(name, regex, ["mock"], author, 0, None, command, [], [], {}, [])
        trigger_list = await self.config.guild(guild).trigger_list()
        trigger_list[name] = new_trigger.to_json()
        await self.config.guild(guild).trigger_list.set(trigger_list)
        await ctx.send(_("Trigger `{name}` set.").format(name=name))

    @retrigger.command(aliases=["deletemsg"])
    @checks.mod_or_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True)
    async def filter(self, ctx, name: TriggerExists, regex: str):
        """
            Add a trigger to delete a message

            `name` name of the trigger
            `regex` the regex that will determine when to respond
            See https://regex101.com/ for help building a regex pattern
            Example for simple search: `"\\bthis matches"` the whole phrase only
            For case insensitive searches add `(?i)` at the start of the regex
        """
        if type(name) != str:
            msg = _("{name} is already a trigger name").format(name=name.name)
            return await ctx.send(msg)
        guild = ctx.guild
        author = ctx.message.author.id
        new_trigger = Trigger(name, regex, ["delete"], author, 0, None, None, [], [], {}, [])
        trigger_list = await self.config.guild(guild).trigger_list()
        trigger_list[name] = new_trigger.to_json()
        await self.config.guild(guild).trigger_list.set(trigger_list)
        await ctx.send(_("Trigger `{name}` set.").format(name=name))

    @retrigger.command()
    @checks.mod_or_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def addrole(self, ctx, name: TriggerExists, regex: ValidRegex, *roles: discord.Role):
        """
            Add a trigger to add a role

            `name` name of the trigger
            `regex` the regex that will determine when to respond
            `role` the role applied when the regex pattern matches
            See https://regex101.com/ for help building a regex pattern
            Example for simple search: `"\\bthis matches"` the whole phrase only
            For case insensitive searches add `(?i)` at the start of the regex
        """
        if type(name) != str:
            msg = _("{name} is already a trigger name").format(name=name.name)
            return await ctx.send(msg)
        for role in roles:
            if role >= ctx.me.top_role:
                await ctx.send(_("I can't assign roles higher than my own."))
                return
        roles = [r.id for r in roles]
        guild = ctx.guild
        author = ctx.message.author.id
        new_trigger = Trigger(name, regex, ["add_role"], author, 0, None, roles, [], [], {}, [])
        trigger_list = await self.config.guild(guild).trigger_list()
        trigger_list[name] = new_trigger.to_json()
        await self.config.guild(guild).trigger_list.set(trigger_list)
        await ctx.send(_("Trigger `{name}` set.").format(name=name))

    @retrigger.command()
    @checks.mod_or_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def removerole(self, ctx, name: TriggerExists, regex: ValidRegex, *roles: discord.Role):
        """
            Add a trigger to remove a role

            `name` name of the trigger
            `regex` the regex that will determine when to respond
            `role` the role applied when the regex pattern matches
            See https://regex101.com/ for help building a regex pattern
            Example for simple search: `"\\bthis matches"` the whole phrase only
            For case insensitive searches add `(?i)` at the start of the regex
        """
        if type(name) != str:
            msg = _("{name} is already a trigger name").format(name=name.name)
            return await ctx.send(msg)
        for role in roles:
            if role >= ctx.me.top_role:
                await ctx.send(_("I can't remove roles higher than my own."))
                return
        roles = [r.id for r in roles]
        guild = ctx.guild
        author = ctx.message.author.id
        new_trigger = Trigger(name, regex, ["remove_role"], author, 0, None, roles, [], [], {}, [])
        trigger_list = await self.config.guild(guild).trigger_list()
        trigger_list[name] = new_trigger.to_json()
        await self.config.guild(guild).trigger_list.set(trigger_list)
        await ctx.send(_("Trigger `{name}` set.").format(name=name))

    @retrigger.command()
    @checks.admin_or_permissions(administrator=True)
    async def multi(
        self, ctx, name: TriggerExists, regex: ValidRegex, *multi_response: MultiResponse
    ):
        """
            Add a multiple response trigger

            `name` name of the trigger
            `regex` the regex that will determine when to respond
            `multi_response` the actions to perform when the trigger matches
            multiple responses start with the name of the action which must be one of:
            dm, text, filter, add_role, remove_role, ban, or kick
            followed by a `;` if there is a followup response and a space for the next 
            trigger response. If you want to add or remove multiple roles those may be
            followed up with additional `;` separations.
            e.g. `[p]retrigger multi test \\btest\\b \"dm;You said a bad word!\" filter`
            Will attempt to DM the user and delete their message simultaneously.
        """
        # log.debug(multi_response)
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
        )
        trigger_list = await self.config.guild(guild).trigger_list()
        trigger_list[name] = new_trigger.to_json()
        await self.config.guild(guild).trigger_list.set(trigger_list)
        await ctx.send(_("Trigger `{name}` set.").format(name=name))
