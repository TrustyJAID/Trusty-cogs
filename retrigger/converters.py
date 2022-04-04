import asyncio
import logging
from enum import Enum
from typing import Dict, List, Literal, Optional, Pattern, Tuple, Union

import discord
from discord.ext.commands.converter import Converter, IDConverter, RoleConverter
from discord.ext.commands.errors import BadArgument
from redbot import VersionInfo, version_info
from redbot.core import commands
from redbot.core.i18n import Translator
from redbot.core.utils.menus import start_adding_reactions
from redbot.core.utils.predicates import ReactionPredicate

log = logging.getLogger("red.trusty-cogs.ReTrigger")
_ = Translator("ReTrigger", __file__)

try:
    import regex as re
except ImportError:
    import re


class TriggerResponse(Enum):
    dm = "dm"
    dmme = "dmme"
    remove_role = "remove_role"
    add_role = "add_role"
    ban = "ban"
    kick = "kick"
    text = "text"
    filter = "delete"
    delete = "delete"
    publish = "publish"
    react = "react"
    rename = "rename"
    command = "command"
    mock = "mock"
    resize = "resize"
    randtext = "randtext"
    image = "image"
    randimage = "randimage"


MULTI_RESPONSES = [
    "dm",
    "dmme",
    "remove_role",
    "add_role",
    "ban",
    "kick",
    "text",
    "filter",
    "delete",
    "publish",
    "react",
    "rename",
    "command",
    "mock",
]


class MultiResponse(Converter):
    """
    This will parse my defined multi response pattern and provide usable formats
    to be used in multiple reponses
    """

    async def convert(self, ctx: commands.Context, argument: str) -> Union[List[str], List[int]]:
        result = []
        match = re.split(r"(;)", argument)

        log.debug(match)
        my_perms = ctx.channel.permissions_for(ctx.me)
        if match[0].lower() not in MULTI_RESPONSES:
            raise BadArgument(
                _("`{response}` is not a valid response type.").format(response=match[0])
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
        if result[0] == "publish" and not my_perms.manage_messages:
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

        def author_perms(ctx: commands.Context, role: discord.Role) -> bool:
            if (
                ctx.author.id == ctx.guild.owner_id
            ):  # handles case where guild is not chunked and calls for the ID thru the endpoint instead
                return True
            return role < ctx.author.top_role

        if result[0] in ["add_role", "remove_role"]:
            good_roles = []
            for r in result[1:]:
                try:
                    role = await RoleConverter().convert(ctx, r)
                    if role < ctx.guild.me.top_role and author_perms(ctx, role):
                        good_roles.append(role.id)
                except BadArgument:
                    log.error("Role `{}` not found.".format(r))
            result = [result[0]]
            for r_id in good_roles:
                result.append(r_id)
        if result[0] == "react":
            good_emojis: List[Union[discord.Emoji, str]] = []
            for r in result[1:]:
                try:
                    emoji = await ValidEmoji().convert(ctx, r)
                    good_emojis.append(emoji)
                except BadArgument:
                    log.error("Emoji `{}` not found.".format(r))
            log.debug(good_emojis)
            result = [result[0]] + good_emojis
        return result


class Trigger:
    """
    Trigger class to handle trigger objects
    """

    __slots__ = (
        "name",
        "regex",
        "response_type",
        "author",
        "enabled",
        "text",
        "count",
        "image",
        "whitelist",
        "blacklist",
        "cooldown",
        "multi_payload",
        "ignore_commands",
        "check_edits",
        "ocr_search",
        "delete_after",
        "read_filenames",
        "chance",
        "reply",
        "tts",
        "user_mention",
        "role_mention",
        "everyone_mention",
        "nsfw",
        "_created_at",
    )

    def __init__(
        self,
        name: str,
        regex: str,
        response_type: List[TriggerResponse],
        author: int,
        **kwargs,
    ):
        self.name: str = name
        try:
            self.regex: Pattern = re.compile(regex)
        except Exception:
            raise
        self.response_type: List[TriggerResponse] = response_type
        self.author: int = author
        self.enabled: bool = kwargs.get("enabled", True)
        self.count: int = kwargs.get("count", 0)
        self.image: Union[List[Union[int, str]], str, None] = kwargs.get("image", None)
        self.text: Union[List[Union[int, str]], str, None] = kwargs.get("text", None)
        self.whitelist: List[int] = kwargs.get("whitelist", [])
        self.blacklist: List[int] = kwargs.get("blacklist", [])
        self.cooldown: Dict[str, int] = kwargs.get("cooldown", {})
        self.multi_payload: Union[List[MultiResponse], Tuple[MultiResponse, ...]] = kwargs.get(
            "multi_payload", []
        )
        self._created_at: int = kwargs.get("created_at", 0)
        self.ignore_commands: bool = kwargs.get("ignore_commands", False)
        self.check_edits: bool = kwargs.get("check_edits", False)
        self.ocr_search: bool = kwargs.get("ocr_search", False)
        self.delete_after: int = kwargs.get("delete_after", None)
        self.read_filenames: bool = kwargs.get("read_filenames", False)
        self.chance: int = kwargs.get("chance", 0)
        self.reply: Optional[bool] = kwargs.get("reply", None)
        self.tts: bool = kwargs.get("tts", False)
        self.user_mention: bool = kwargs.get("user_mention", True)
        self.role_mention: bool = kwargs.get("role_mention", False)
        self.everyone_mention: bool = kwargs.get("everyone_mention", False)
        self.nsfw: bool = kwargs.get("nsfw", False)

    def enable(self):
        """Explicitly enable this trigger"""
        self.enabled = True

    def disable(self):
        """Explicitly disables this trigger"""
        self.enabled = False

    def toggle(self):
        """Toggle whether or not this trigger is enabled."""
        self.enabled = not self.enabled

    async def check_cooldown(self, message: discord.Message) -> bool:
        now = message.created_at.timestamp()
        if self.cooldown:
            if self.cooldown["style"] in ["guild", "server"]:
                last = self.cooldown["last"]
                time = self.cooldown["time"]
                if (now - last) > time:
                    self.cooldown["last"] = now
                    return False
                else:
                    return True
            else:
                style: str = self.cooldown["style"]
                snowflake = getattr(message, style)
                if snowflake.id not in [x["id"] for x in self.cooldown["last"]]:
                    self.cooldown["last"].append({"id": snowflake.id, "last": now})
                    return False
                else:
                    entity_list = self.cooldown["last"]
                    for entity in entity_list:
                        if entity["id"] == snowflake.id:
                            last = entity["last"]
                            time = self.cooldown["time"]
                            if (now - last) > time:
                                self.cooldown["last"].remove({"id": snowflake.id, "last": last})
                                self.cooldown["last"].append({"id": snowflake.id, "last": now})
                                return False
                            else:
                                return True
        return False

    async def check_bw_list(self, message: discord.Message) -> bool:
        can_run = True
        author: discord.Member = message.author
        channel: discord.TextChannel = message.channel
        if self.whitelist:
            can_run = False
            if channel.id in self.whitelist:
                can_run = True
            if channel.category_id and channel.category_id in self.whitelist:
                can_run = True
            if getattr(channel, "parent", None) and channel.parent in self.whitelist:
                # this is a thread
                can_run = True
            if message.author.id in self.whitelist:
                can_run = True
            for role in author.roles:
                if role.is_default():
                    continue
                if role.id in self.whitelist:
                    can_run = True
            return can_run
        else:
            if channel.id in self.blacklist:
                can_run = False
            if channel.category_id and channel.category_id in self.blacklist:
                can_run = False
            if getattr(channel, "parent", None) and channel.parent in self.blacklist:
                can_run = False
            if message.author.id in self.blacklist:
                can_run = False
            for role in author.roles:
                if role.is_default():
                    continue
                if role.id in self.blacklist:
                    can_run = False
        return can_run

    @property
    def created_at(self):
        return discord.utils.snowflake_time(self._created_at)

    @property
    def timestamp(self):
        return self.created_at.timestamp()

    def allowed_mentions(self):
        if version_info >= VersionInfo.from_str("3.4.6"):
            return discord.AllowedMentions(
                everyone=self.everyone_mention,
                users=self.user_mention,
                roles=self.role_mention,
                replied_user=self.reply if self.reply is not None else False,
            )
        else:
            return discord.AllowedMentions(
                everyone=self.everyone_mention, users=self.user_mention, roles=self.role_mention
            )

    def __repr__(self):
        return "<ReTrigger name={0.name} author={0.author} response={0.response_type} pattern={0.regex.pattern}>".format(
            self
        )

    def __str__(self):
        """This is defined moreso for debugging purposes but may prove useful for elaborating
        what is defined for each trigger individually"""
        info = _(
            "__Name__: **{name}** \n"
            "__Active__: **{enabled}**\n"
            "__Author__: {author}\n"
            "__Count__: **{count}**\n"
            "__Response__: **{response}**\n"
        ).format(
            name=self.name,
            enabled=self.enabled,
            author=self.author,
            count=self.count,
            response=self.response_type,
        )
        return info

    async def to_json(self) -> dict:
        return {
            "name": self.name,
            "regex": self.regex.pattern,
            "response_type": [t.value for t in self.response_type],
            "author": self.author,
            "enabled": self.enabled,
            "count": self.count,
            "image": self.image,
            "text": self.text,
            "whitelist": self.whitelist,
            "blacklist": self.blacklist,
            "cooldown": self.cooldown,
            "multi_payload": self.multi_payload,
            "created_at": self._created_at,
            "ignore_commands": self.ignore_commands,
            "check_edits": self.check_edits,
            "ocr_search": self.ocr_search,
            "delete_after": self.delete_after,
            "read_filenames": self.read_filenames,
            "chance": self.chance,
            "reply": self.reply,
            "tts": self.tts,
            "user_mention": self.user_mention,
            "everyone_mention": self.everyone_mention,
            "role_mention": self.role_mention,
            "nsfw": self.nsfw,
        }

    @classmethod
    async def from_json(cls, data: dict):
        # This should be used only for correcting improper types
        # All the defaults are handled in the class setup
        name = data.pop("name")
        regex = data.pop("regex")
        author = data.pop("author")
        response_type = data.pop("response_type", [])
        if isinstance(response_type, str):
            response_type = [data["response_type"]]
        response_type = [TriggerResponse(t) for t in response_type]
        if "delete" in response_type and isinstance(data["text"], bool):
            # replace old setting with new flag
            data["read_filenames"] = data["text"]
            data["text"] = None
        ignore_edits = data.get("ignore_edits", False)
        check_edits = data.get("check_edits")
        if check_edits is None and any(
            t.value in ["ban", "kick", "delete"] for t in response_type
        ):
            data["check_edits"] = not ignore_edits
        return cls(name, regex, response_type, author, **data)


class TriggerExists(Converter):
    async def convert(self, ctx: commands.Context, argument: str) -> Union[Trigger, str]:
        guild = ctx.guild
        result = None
        if ctx.guild.id not in ctx.cog.triggers:
            raise BadArgument(_("There are no triggers setup on this server."))
        if argument in ctx.cog.triggers[guild.id]:
            return ctx.cog.triggers[guild.id][argument]
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

    async def convert(self, ctx: commands.Context, argument: str) -> str:
        try:
            re.compile(argument)
            result = argument
        except Exception as e:
            log.error("Retrigger conversion error")
            err_msg = _("`{arg}` is not a valid regex pattern. {e}").format(arg=argument, e=e)
            raise BadArgument(err_msg)
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

    async def convert(self, ctx: commands.Context, argument: str) -> Union[discord.Emoji, str]:
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

    async def convert(
        self, ctx: commands.Context, argument: str
    ) -> Union[discord.TextChannel, discord.Member, discord.Role]:
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
