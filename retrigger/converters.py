import discord
import logging
import asyncio
import re
from typing import List, Union, Tuple, Pattern

from discord.ext.commands.converter import Converter, IDConverter, RoleConverter
from discord.ext.commands.errors import BadArgument
from redbot.core.i18n import Translator
from redbot.core import commands
from redbot.core.utils.predicates import ReactionPredicate
from redbot.core.utils.menus import start_adding_reactions

log = logging.getLogger("red.trusty-cogs.ReTrigger")
_ = Translator("ReTrigger", __file__)


class TriggerExists(Converter):
    async def convert(self, ctx, argument):
        bot = ctx.bot
        guild = ctx.guild
        config = bot.get_cog("ReTrigger").config
        trigger_list = await config.guild(guild).trigger_list()
        result = None
        if argument in trigger_list:
            result = await Trigger.from_json(trigger_list[argument])
        else:
            result = argument
        return result


class ValidRegex(Converter):
    """
    This will check to see if the provided regex pattern is valid

    Guidance code on how to do this from:
    https://github.com/Rapptz/discord.py/blob/rewrite/discord/ext/commands/converter.py#L85
    https://github.com/Cog-Creators/Red-DiscordBot/blob/V3/develop/redbot/cogs/mod/mod.py#L24
    """

    async def convert(self, ctx: commands.Context, argument: str):
        try:
            re.compile(argument)
            result = argument
        except Exception as e:
            log.error("Retrigger conversion error")
            err_msg = _("`{arg}` is not a valid regex pattern. {e}").format(arg=argument, e=e)
            raise BadArgument(err_msg)
        return result


class MultiResponse(Converter):
    """
    This will parse my defined multi response pattern and provide usable formats
    to be used in multiple reponses
    """

    async def convert(self, ctx: commands.Context, argument: str) -> Union[List[str], List[int]]:
        result = []
        match = re.split(r"(;)", argument)
        valid_reactions = [
            "dm",
            "remove_role",
            "add_role",
            "ban",
            "kick",
            "text",
            "filter",
            "delete",
            "react",
            "command",
            "mock",
        ]
        log.debug(match)
        my_perms = ctx.channel.permissions_for(ctx.me)
        if match[0] not in valid_reactions:
            raise BadArgument(
                _("`{response}` is not a valid reaction type.").format(response=match[0])
            )
        for m in match:
            if m == ";":
                continue
            else:
                result.append(m)
        if result[0] == "filter":
            result[0] = "delete"
        if len(result) < 2 and result[0] not in ["delete", "ban", "kick"]:
            raise BadArgument(_("The provided multi response pattern is not valid."))
        if result[0] in ["add_role", "remove_role"] and not my_perms.manage_roles:
            raise BadArgument(_('I require "Manage Roles" permission to use that.'))
        if result[0] == "filter" and not my_perms.manage_messages:
            raise BadArgument(_('I require "Manage Messages" permission to use that.'))
        if result[0] == "ban" and not my_perms.ban_members:
            raise BadArgument(_('I require "Ban Members" permission to use that.'))
        if result[0] == "kick" and not my_perms.kick_members:
            raise BadArgument(_('I require "Kick Members" permission to use that.'))
        if result[0] == "react" and not my_perms.add_reactions:
            raise BadArgument(_('I require "Add Reactions" permission to use that.'))
        if result[0] == "mock":
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
                raise BadArgument(_("Not creating trigger."))
            if not pred.result:
                raise BadArgument(_("Not creating trigger."))
        if result[0] in ["add_role", "remove_role"]:
            good_roles = []
            for r in result[1:]:
                try:
                    role = await RoleConverter().convert(ctx, r)
                    if role < ctx.guild.me.top_role and role < ctx.author.top_role:
                        good_roles.append(role.id)
                except BadArgument:
                    log.error("Role `{}` not found.".format(r))
            result = [result[0]]
            for r_id in good_roles:
                result.append(r_id)
        if result[0] == "react":
            good_emojis = []
            for r in result[1:]:
                try:
                    emoji = await ValidEmoji().convert(ctx, r)
                    good_emojis.append(emoji)
                except BadArgument:
                    log.error("Emoji `{}` not found.".format(r))
            log.debug(good_emojis)
            result = [result[0]] + good_emojis
        return result


class ValidEmoji(IDConverter):
    """
    This is from discord.py rewrite, first we'll match the actual emoji
    then we'll match the emoji name if we can
    if all else fails we may suspect that it's a unicode emoji and check that later
    All lookups are done for the local guild first, if available. If that lookup
    fails, then it checks the client's global cache.
    The lookup strategy is as follows (in order):
    1. Lookup by ID.
    2. Lookup by extracting ID from the emoji.
    3. Lookup by name
    https://github.com/Rapptz/discord.py/blob/rewrite/discord/ext/commands/converter.py
    """

    async def convert(self, ctx: commands.Context, argument: str):
        match = self._get_id_match(argument) or re.match(
            r"<a?:[a-zA-Z0-9\_]+:([0-9]+)>$|(:[a-zA-z0-9\_]+:$)", argument
        )
        result = None
        bot = ctx.bot
        guild = ctx.guild
        if match is None:
            # Try to get the emoji by name. Try local guild first.
            if guild:
                result = discord.utils.get(guild.emojis, name=argument)

            if result is None:
                result = discord.utils.get(bot.emojis, name=argument)
        elif match.group(1):
            emoji_id = int(match.group(1))

            # Try to look up emoji by id.
            if guild:
                result = discord.utils.get(guild.emojis, id=emoji_id)

            if result is None:
                result = discord.utils.get(bot.emojis, id=emoji_id)
        else:
            emoji_name = str(match.group(2)).replace(":", "")

            if guild:
                result = discord.utils.get(guild.emojis, name=emoji_name)

            if result is None:
                result = discord.utils.get(bot.emojis, name=emoji_name)
        if type(result) is discord.Emoji:
            result = str(result)[1:-1]

        if result is None:
            try:
                await ctx.message.add_reaction(argument)
                result = argument
            except Exception:
                raise BadArgument(_("`{}` is not an emoji I can use.").format(argument))

        return result


class ChannelUserRole(IDConverter):
    """
    This will check to see if the provided argument is a channel, user, or role

    Guidance code on how to do this from:
    https://github.com/Rapptz/discord.py/blob/rewrite/discord/ext/commands/converter.py#L85
    https://github.com/Cog-Creators/Red-DiscordBot/blob/V3/develop/redbot/cogs/mod/mod.py#L24
    """

    async def convert(self, ctx: commands.Context, argument: str):
        guild = ctx.guild
        result = None
        id_match = self._get_id_match(argument)
        channel_match = re.match(r"<#([0-9]+)>$", argument)
        member_match = re.match(r"<@!?([0-9]+)>$", argument)
        role_match = re.match(r"<@&([0-9]+)>$", argument)
        for converter in ["channel", "role", "member"]:
            if converter == "channel":
                match = id_match or channel_match
                if match:
                    channel_id = match.group(1)
                    result = guild.get_channel(int(channel_id))
                else:
                    result = discord.utils.get(guild.text_channels, name=argument)
            if converter == "member":
                match = id_match or member_match
                if match:
                    member_id = match.group(1)
                    result = guild.get_member(int(member_id))
                else:
                    result = guild.get_member_named(argument)
            if converter == "role":
                match = id_match or role_match
                if match:
                    role_id = match.group(1)
                    result = guild.get_role(int(role_id))
                else:
                    result = discord.utils.get(guild._roles.values(), name=argument)
            if result:
                break
        if not result:
            msg = _("{arg} is not a valid channel, user or role.").format(arg=argument)
            raise BadArgument(msg)
        return result


class Trigger:
    """
        Trigger class to handle trigger objects
    """
    name: str
    regex: Pattern
    response_type: list
    author: int
    count: int
    image: Union[List[Union[int, str]], str, None]
    text: Union[List[Union[int, str]], str, None]
    whitelist: list
    blacklist: list
    cooldown: dict
    multi_payload: Union[List[MultiResponse], Tuple[MultiResponse, ...]]
    created: int
    ignore_commands: bool

    def __init__(
        self,
        name: str,
        regex: str,
        response_type: list,
        author: int,
        count: int,
        image: Union[List[Union[int, str]], str, None],
        text: Union[List[Union[int, str]], str, None],
        whitelist: list,
        blacklist: list,
        cooldown: dict,
        multi_payload: Union[List[MultiResponse], Tuple[MultiResponse, ...]],
        created_at: int,
        ignore_commands: bool = False,
    ):
        self.name = name
        self.regex = re.compile(regex)
        self.response_type = response_type
        self.author = author
        self.count = count
        self.image = image
        self.text = text
        self.whitelist = whitelist
        self.blacklist = blacklist
        self.cooldown = cooldown
        self.multi_payload = multi_payload
        self.created_at = created_at
        self.ignore_commands = ignore_commands

    def __str__(self):
        return self.name

    async def to_json(self) -> dict:
        return {
            "name": self.name,
            "regex": self.regex.pattern,
            "response_type": self.response_type,
            "author": self.author,
            "count": self.count,
            "image": self.image,
            "text": self.text,
            "whitelist": self.whitelist,
            "blacklist": self.blacklist,
            "cooldown": self.cooldown,
            "multi_payload": self.multi_payload,
            "created_at": self.created_at,
            "ignore_commands": self.ignore_commands
        }

    @classmethod
    async def from_json(cls, data: dict):
        cooldown: dict = {}
        multi_payload: List[MultiResponse] = []
        created_at: int = 0
        ignore_commands = False
        if "cooldown" in data:
            cooldown = data["cooldown"]
        if type(data["response_type"]) is str:
            response_type = [data["response_type"]]
        else:
            response_type = data["response_type"]
        if "multi_payload" in data:
            multi_payload = data["multi_payload"]
        if "created_at" in data:
            created_at = data["created_at"]
        if "ignore_commands" in data:
            ignore_commands = data["ignore_commands"]
        return cls(
            data["name"],
            data["regex"],
            response_type,
            data["author"],
            data["count"],
            data["image"],
            data["text"],
            data["whitelist"],
            data["blacklist"],
            cooldown,
            multi_payload,
            created_at,
            ignore_commands,
        )
