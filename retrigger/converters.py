from dataclasses import dataclass
from enum import Enum
from typing import (
    TYPE_CHECKING,
    Any,
    Dict,
    List,
    NamedTuple,
    Optional,
    Pattern,
    Tuple,
    Union,
)

import discord
from discord.ext.commands.converter import Converter, IDConverter
from discord.ext.commands.errors import BadArgument
from red_commons.logging import getLogger
from redbot.core import commands
from redbot.core.i18n import Translator

log = getLogger("red.trusty-cogs.ReTrigger")
_ = Translator("ReTrigger", __file__)

try:
    import regex as re
except ImportError:
    import re

if TYPE_CHECKING:
    from .abc import ReTriggerMixin


class TriggerResponse(Enum):
    dm = "dm"
    dmme = "dmme"
    remove_role = "remove_role"
    add_role = "add_role"
    ban = "ban"
    kick = "kick"
    text = "text"
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
    create_thread = "create_thread"

    def __str__(self):
        return str(self.value)

    @property
    def is_automod(self) -> bool:
        return self in {
            TriggerResponse.delete,
            TriggerResponse.kick,
            TriggerResponse.ban,
            TriggerResponse.add_role,
            TriggerResponse.remove_role,
        }

    @property
    def permissions(self) -> discord.Permissions:
        """
        Map Response Types to specific discord permissions.

        This is a lazy approach but generally speaking all triggers
        require the manage messages permission as a default. Other
        response types require elevated permissions.

        These are also based on actual required permissions for the action.
        e.g. reaction management requires manage_messages permission not
        add_reactions permission. So this is to enable more loose editing
        allowing mods to disable specific triggers.
        """
        return {
            TriggerResponse.remove_role: discord.Permissions(manage_roles=True),
            TriggerResponse.add_role: discord.Permissions(manage_roles=True),
            TriggerResponse.ban: discord.Permissions(ban_members=True),
            TriggerResponse.kick: discord.Permissions(kick_members=True),
            TriggerResponse.rename: discord.Permissions(manage_nicknames=True),
            TriggerResponse.create_thread: discord.Permissions(manage_threads=True),
        }.get(self, discord.Permissions(manage_messages=True))

    @property
    def required_perms(self) -> discord.Permissions:
        return {
            TriggerResponse.remove_role: discord.Permissions(manage_roles=True),
            TriggerResponse.add_role: discord.Permissions(manage_roles=True),
            TriggerResponse.ban: discord.Permissions(ban_members=True),
            TriggerResponse.kick: discord.Permissions(kick_members=True),
            TriggerResponse.rename: discord.Permissions(manage_nicknames=True),
            TriggerResponse.create_thread: discord.Permissions(manage_threads=True),
            TriggerResponse.delete: discord.Permissions(manage_messages=True),
            TriggerResponse.image: discord.Permissions(attach_files=True),
            TriggerResponse.randimage: discord.Permissions(attach_files=True),
            TriggerResponse.resize: discord.Permissions(attach_files=True),
            TriggerResponse.text: discord.Permissions(send_messages=True),
            TriggerResponse.publish: discord.Permissions(manage_messages=True),
        }.get(self, discord.Permissions(0))

    @property
    def is_role_change(self) -> bool:
        return self in {
            TriggerResponse.add_role,
            TriggerResponse.remove_role,
        }

    @property
    def multi_allowed(self) -> bool:
        return self in {
            TriggerResponse.dm,
            TriggerResponse.dmme,
            TriggerResponse.remove_role,
            TriggerResponse.add_role,
            TriggerResponse.ban,
            TriggerResponse.kick,
            TriggerResponse.text,
            TriggerResponse.delete,
            TriggerResponse.publish,
            TriggerResponse.react,
            TriggerResponse.rename,
            TriggerResponse.command,
            TriggerResponse.mock,
            TriggerResponse.delete,
        }


class MultiResponse(NamedTuple):
    action: TriggerResponse
    response: Union[int, str, bool]

    def to_json(self):
        return [self.action.value, self.response]

    @classmethod
    def from_json(cls, data: Tuple[str, Union[int, str, bool]]):
        action = TriggerResponse(data[0])
        if len(data) == 1:
            return cls(action, True)
        else:
            return cls(action, data[1])


class MultiFlags(commands.FlagConverter):
    text: Optional[str] = commands.flag(name="text", default=None)
    dm: Optional[str] = commands.flag(name="dm", default=None)
    dmme: Optional[str] = commands.flag(name="dmme", default=None)
    remove_role: Tuple[discord.Role, ...] = commands.flag(
        name="remove", aliases=["remove_role"], default=()
    )
    add_role: Tuple[discord.Role, ...] = commands.flag(
        name="add", aliases=["add_role"], default=()
    )
    ban: Optional[bool] = commands.flag(name="ban", default=None)
    kick: Optional[bool] = commands.flag(name="kick", default=None)
    text: Optional[str] = commands.flag(name="text", default=None)
    delete: Optional[bool] = commands.flag(name="delete", aliases=["filter"], default=None)
    react: Tuple[Union[discord.PartialEmoji, str], ...] = commands.flag(
        name="react", aliases=["emoji"], default=()
    )
    rename: Optional[str] = commands.flag(name="rename", default=None)
    command: Optional[str] = commands.flag(name="command", default=None)
    mock: Optional[str] = commands.flag(name="mock", default=None)
    publish: Optional[bool] = commands.flag(name="publish", default=None)

    async def payload(self, ctx: commands.Context) -> List[MultiResponse]:
        result = []
        required_perms = discord.Permissions()
        for r in TriggerResponse:
            if not r.multi_allowed:
                continue
            value = getattr(self, r.value, None)
            if value in ((), None):
                continue
            required_perms |= r.required_perms
            if r in [TriggerResponse.add_role, TriggerResponse.remove_role]:
                for role in value:
                    if role >= ctx.me.top_role:
                        continue
                    result.append(MultiResponse(r, role.id))
            elif r is TriggerResponse.react:
                for e in value:
                    try:
                        emoji = await ValidEmoji().convert(ctx, str(e))
                        result.append(MultiResponse(r, str(emoji)))
                    except BadArgument:
                        log.error("Emoji `%s` not found.", r)
            else:
                result.append(MultiResponse(r, value))
        bot_perms = ctx.bot_permissions
        if not (bot_perms.administrator or bot_perms >= required_perms):
            missing_perms = discord.Permissions(required_perms.value & ~bot_perms.value)
            raise commands.BotMissingPermissions(missing=missing_perms)
        return result


@dataclass
class TriggerThread:
    name: Optional[str] = None
    public: Optional[bool] = None
    invitable: bool = True

    def format_str(self):
        if self.public is None:
            return _("None")
        elif self.public is True:
            return _("\n- Public Thread created\n- Thread Name: `{name}`").format(name=self.name)
        else:
            return _(
                "\n- Private Thread created\n- Invitable: {invitable}\n- Thread Name: `{name}`"
            ).format(name=self.name, invitable=self.invitable)

    def to_json(self) -> dict:
        return {
            "name": self.name,
            "public": self.public,
            "invitable": self.invitable,
        }


class Trigger:
    """
    Trigger class to handle trigger objects
    """

    __slots__ = (
        "name",
        "regex",
        "_raw_regex",
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
        "read_embeds",
        "read_thread_title",
        "_created_at",
        "thread",
        "remove_roles",
        "add_roles",
        "reactions",
        "_last_modified_by",
        "_last_modified_at",
        "_last_modified",
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
        self._raw_regex = regex
        try:
            self.regex: Pattern = re.compile(self._raw_regex)
        except Exception:
            self.regex: Optional[Pattern] = None
            pass
        self.response_type: List[TriggerResponse] = response_type
        self.author: int = author
        self.enabled: bool = kwargs.get("enabled", True)
        self.count: int = kwargs.get("count", 0)
        self.image: Union[List[Union[int, str]], str, None] = kwargs.get("image", None)
        self.text: Optional[str] = kwargs.get("text", None)
        self.whitelist: List[int] = kwargs.get("whitelist", [])
        self.blacklist: List[int] = kwargs.get("blacklist", [])
        self.cooldown: Dict[str, int] = kwargs.get("cooldown", {})
        self.multi_payload: List[MultiResponse] = kwargs.get("multi_payload", [])
        self._created_at: int = kwargs.get("created_at", 0)
        self.ignore_commands: bool = kwargs.get("ignore_commands", False)
        self.check_edits: bool = kwargs.get("check_edits", False)
        self.ocr_search: bool = kwargs.get("ocr_search", False)
        self.delete_after: Optional[int] = kwargs.get("delete_after", None)
        self.read_filenames: bool = kwargs.get("read_filenames", False)
        self.chance: int = kwargs.get("chance", 0)
        self.reply: Optional[bool] = kwargs.get("reply", None)
        self.tts: bool = kwargs.get("tts", False)
        self.user_mention: bool = kwargs.get("user_mention", True)
        self.role_mention: bool = kwargs.get("role_mention", False)
        self.everyone_mention: bool = kwargs.get("everyone_mention", False)
        self.nsfw: bool = kwargs.get("nsfw", False)
        self.read_embeds: bool = kwargs.get("read_embeds", False)
        self.read_thread_title: bool = kwargs.get("read_thread_title", True)
        self.thread: TriggerThread = kwargs.get("thread", TriggerThread())
        self.remove_roles: List[int] = kwargs.get("remove_roles", [])
        self.add_roles: List[int] = kwargs.get("add_roles", [])
        self.reactions: List[discord.PartialEmoji] = kwargs.get("reactions", [])
        self._last_modified_by: Optional[int] = kwargs.get("_last_modified_by", None)
        self._last_modified_at: Optional[int] = kwargs.get("_last_modified_at", None)
        self._last_modified: Optional[str] = kwargs.get("_last_modified", None)

    def enable(self):
        """Explicitly enable this trigger"""
        self.enabled = True

    def disable(self):
        """Explicitly disables this trigger"""
        self.enabled = False

    def toggle(self):
        """Toggle whether or not this trigger is enabled."""
        self.enabled = not self.enabled

    def compile(self):
        self.regex: Pattern = re.compile(self._raw_regex)

    def get_permissions(self):
        perms = discord.Permissions()
        for resp in self.response_type:
            perms |= resp.permissions
        return perms

    @property
    def last_modified_by(self):
        return self._last_modified_by

    @property
    def last_modified_at(self):
        if self._last_modified_at is None:
            return None
        return discord.utils.snowflake_time(self._last_modified_at)

    @property
    def last_modified(self):
        return self._last_modified

    def last_modified_str(self, ctx: commands.Context) -> str:
        msg = ""
        if not any([self.last_modified_by, self.last_modified_at, self.last_modified]):
            return msg
        msg = _("__Last Modified__:\n")
        if self.last_modified_by:
            user = ctx.guild.get_member(self.last_modified_by)
            if user is None:
                user_str = _("Unknown user (`{user_id}`)\n").format(user_id=self.last_modified_by)
            else:
                user_str = user.mention
            msg += _("- By: {user}\n").format(user=user_str)
        if self.last_modified_at:
            msg += "- " + discord.utils.format_dt(self.last_modified_at, "R") + "\n"
        if self.last_modified:
            msg += _("- Changes: {changes}\n").format(changes=self.last_modified)
        return msg

    def modify(
        self, attr: str, value: Any, author: Union[discord.Member, discord.User], message_id: int
    ):
        setattr(self, attr, value)
        self._last_modified_by = author.id
        self._last_modified_at = message_id
        self._last_modified = _("{attr} set to {value}.").format(attr=attr, value=value)

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

    async def check_bw_list(
        self, author: Optional[discord.Member], channel: discord.abc.GuildChannel
    ) -> bool:
        can_run = True
        # author: discord.Member = message.author
        # channel: discord.abc.GuildChannel = message.channel
        if self.whitelist:
            can_run = False
            if channel.id in self.whitelist:
                can_run = True
            if channel.category_id and channel.category_id in self.whitelist:
                can_run = True
            if isinstance(channel, (discord.Thread, discord.ForumChannel)):
                if channel.parent.id in self.whitelist:
                    # this is a thread
                    can_run = True
            if author is not None:
                if author.id in self.whitelist:
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
            if isinstance(channel, (discord.Thread, discord.ForumChannel)):
                if channel.parent.id in self.blacklist:
                    # this is a thread
                    can_run = False
            if author is not None:
                if author.id in self.blacklist:
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

    def allowed_mentions(self) -> discord.AllowedMentions:
        return discord.AllowedMentions(
            everyone=self.everyone_mention,
            users=self.user_mention,
            roles=self.role_mention,
            replied_user=self.reply if self.reply is not None else False,
        )

    def __repr__(self):
        return "<ReTrigger name={0.name} author={0.author} response={0.response_type} pattern={0._raw_regex}>".format(
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
            "regex": self.regex.pattern if self.regex else self._raw_regex,
            "response_type": [t.value for t in self.response_type],
            "author": self.author,
            "enabled": self.enabled,
            "count": self.count,
            "image": self.image,
            "text": self.text,
            "whitelist": self.whitelist,
            "blacklist": self.blacklist,
            "cooldown": self.cooldown,
            "multi_payload": [i.to_json() for i in self.multi_payload],
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
            "read_embeds": self.read_embeds,
            "read_thread_title": self.read_thread_title,
            "thread": self.thread.to_json(),
            "remove_roles": self.remove_roles,
            "add_roles": self.add_roles,
            "reactions": [str(e) for e in self.reactions],
            "_last_modified_by": self._last_modified_by,
            "_last_modified_at": self._last_modified_at,
            "_last_modified": self._last_modified,
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
        response_type = [
            TriggerResponse(t) if t != "filter" else TriggerResponse.delete for t in response_type
        ]
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
        thread = TriggerThread()
        if "thread" in data:
            thread = TriggerThread(**data.pop("thread"))
        remove_roles = data.pop("remove_roles", [])
        add_roles = data.pop("add_roles", [])
        reactions = data.pop("reactions", [])
        multi_data = data.pop("multi_payload", [])
        multi_payload = []
        for response in multi_data:
            if len(response) <= 2:
                multi_payload.append(MultiResponse.from_json(response))
            else:
                # incase we have multiple roles or emojis inside one "response"
                for item in response[1:]:
                    multi_payload.append(MultiResponse.from_json((response[0], item)))

        if TriggerResponse.remove_role in response_type and not remove_roles:
            if multi_payload:
                remove_roles = [
                    r.response for r in multi_payload if r.action is TriggerResponse.remove_role
                ]
            else:
                remove_roles = data.get("text", [])
                data["text"] = None
            if remove_roles is None:
                remove_roles = []
        if TriggerResponse.add_role in response_type and not add_roles:
            if multi_payload:
                remove_roles = [
                    r.response for r in multi_payload if r.action is TriggerResponse.add_role
                ]
            else:
                add_roles = data.get("text", [])
                data["text"] = None
            if add_roles is None:
                add_roles = []
        if TriggerResponse.react in response_type and not reactions:
            if multi_payload:
                remove_roles = [
                    r.response for r in multi_payload if r.action is TriggerResponse.react
                ]
            else:
                reactions = data.get("text", [])
                data["text"] = None
            if reactions is None:
                reactions = []

        reactions = [discord.PartialEmoji.from_str(e) for e in reactions]

        return cls(
            name,
            regex,
            response_type,
            author,
            multi_payload=multi_payload,
            add_roles=add_roles,
            remove_roles=remove_roles,
            reactions=reactions,
            thread=thread,
            **data,
        )


class TriggerExists(Converter[Trigger]):
    async def convert(self, ctx: commands.Context, argument: str) -> Trigger:
        guild = ctx.guild
        if guild is None:
            raise BadArgument()
        cog: ReTriggerMixin = ctx.bot.get_cog("ReTrigger")
        if guild.id not in cog.triggers:
            raise BadArgument(_("There are no triggers setup on this server."))
        if argument in cog.triggers[guild.id]:
            ret = cog.triggers[guild.id][argument]
            if ctx.command in [cog.disable_trigger, cog.enable_trigger]:
                # This allows anyone to enable or disable triggers
                # while allowing only the author guild owner and bot owner to
                # edit individual parts of a trigger.
                if await cog.can_enable_or_disable(ctx.author, ret):
                    return ret
            if ctx.command in [cog.remove]:
                return ret
            if not await cog.can_edit(ctx.author, ret):
                raise BadArgument(_("You are not authorized to edit this trigger."))
            return ret
        else:
            raise BadArgument(
                _("Trigger with name `{name}` does not exist.").format(name=argument)
            )


class TriggerStarExists(Converter[Trigger]):
    async def convert(self, ctx: commands.Context, argument: str) -> List[Trigger]:
        guild = ctx.guild
        if guild is None:
            raise BadArgument()
        cog: ReTriggerMixin = ctx.bot.get_cog("ReTrigger")
        if guild.id not in cog.triggers:
            raise BadArgument(_("There are no triggers setup on this server."))
        if argument in cog.triggers[guild.id]:
            return [cog.triggers[guild.id][argument]]
        elif argument == "*":
            return [t for t in cog.triggers[guild.id].values()]
        else:
            raise BadArgument(
                _("Trigger with name `{name}` does not exist.").format(name=argument)
            )


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

    async def convert(self, ctx: commands.Context, argument: str) -> discord.PartialEmoji:
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
        if isinstance(result, discord.Emoji):
            result = discord.PartialEmoji.from_str(str(result))

        if result is None:
            try:
                await ctx.message.add_reaction(argument)
                result = discord.PartialEmoji.from_str(argument)
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
                    result = guild.get_channel_or_thread(int(channel_id))
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
