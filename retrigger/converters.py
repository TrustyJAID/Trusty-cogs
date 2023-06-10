import asyncio
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Dict, List, Optional, Pattern, Tuple, Union

import discord
from discord.ext.commands.converter import Converter, IDConverter, RoleConverter
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


class ConfirmView(discord.ui.View):
    def __init__(self, ctx: Union[commands.Context, discord.Interaction], default: bool = False):
        super().__init__()
        self.result = default
        self.ctx = ctx

    @discord.ui.button(label=_("Yes"), style=discord.ButtonStyle.green)
    async def yes_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.result = True
        self.stop()
        await interaction.response.edit_message(view=None)

    @discord.ui.button(label=_("No"), style=discord.ButtonStyle.red)
    async def no_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.result = False
        self.stop()
        await interaction.response.edit_message(view=None)

    async def interaction_check(self, interaction: discord.Interaction):
        if isinstance(self.ctx, discord.Interaction):
            if interaction.user.id != self.ctx.user.id:
                return False
        else:
            if interaction.user.id != self.ctx.author.id:
                return False
        return True


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
            TriggerResponse.filter,
            TriggerResponse.delete,
            TriggerResponse.publish,
            TriggerResponse.react,
            TriggerResponse.rename,
            TriggerResponse.command,
            TriggerResponse.mock,
            TriggerResponse.delete,
            TriggerResponse.create_thread,
        }


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
    "create_thread",
]


class MultiResponse(Converter):
    """
    This will parse my defined multi response pattern and provide usable formats
    to be used in multiple reponses
    """

    async def convert(self, ctx: commands.Context, argument: str) -> Union[List[str], List[int]]:
        result = []
        match = re.split(r"(;)", argument)

        log.verbose("MultiResponse match: %s", match)
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
            view = ConfirmView(ctx, default=False)
            msg = await ctx.send(
                _(
                    "Mock commands can allow any user to run a command "
                    "as if you did, are you sure you want to add this?"
                ),
                view=view,
            )
            await view.wait()
            if not view.result:
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
                    log.error("Role `%s` not found.", r)
            result = [result[0]]
            for r_id in good_roles:
                result.append(r_id)
        if result[0] == "react":
            good_emojis: List[Union[discord.Emoji, str]] = []
            for r in result[1:]:
                try:
                    emoji = await ValidEmoji().convert(ctx, r)
                    good_emojis.append(str(emoji))
                except BadArgument:
                    log.error("Emoji `%s` not found.", r)
            log.verbose("MultiResponse good_emojis: %s", good_emojis)
            result = [result[0]] + good_emojis
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
        self.read_embeds: bool = kwargs.get("embeds", False)
        self.read_thread_title: bool = kwargs.get("read_thread_title", True)
        self.thread: TriggerThread = kwargs.get("thread", TriggerThread())
        self.remove_roles: List[int] = kwargs.get("remove_roles", [])
        self.add_roles: List[int] = kwargs.get("add_roles", [])
        self.reactions: List[discord.PartialEmoji] = kwargs.get("reactions", [])

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
            "read_embeds": self.read_embeds,
            "read_thread_title": self.read_thread_title,
            "thread": self.thread.to_json(),
            "remove_roles": self.remove_roles,
            "add_roles": self.add_roles,
            "reactions": [str(e) for e in self.reactions],
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
        thread = TriggerThread()
        if "thread" in data:
            thread = TriggerThread(**data.pop("thread"))
        remove_roles = data.pop("remove_roles", [])
        add_roles = data.pop("add_roles", [])
        reactions = data.pop("reactions", [])
        if TriggerResponse.remove_role in response_type and not remove_roles:
            if data["multi_payload"]:
                remove_roles = [
                    r for t in data["multi_payload"] for r in t[1:] if t[0] == "remove_role"
                ]
            else:
                remove_roles = data.get("text", [])
                data["text"] = None
            if remove_roles is None:
                remove_roles = []
        if TriggerResponse.add_role in response_type and not add_roles:
            if data["multi_payload"]:
                add_roles = [r for t in data["multi_payload"] for r in t[1:] if t[0] == "add_role"]
            else:
                add_roles = data.get("text", [])
                data["text"] = None
            if add_roles is None:
                add_roles = []
        if TriggerResponse.react in response_type and not reactions:
            if data["multi_payload"]:
                reactions = [r for t in data["multi_payload"] for r in t[1:] if t[0] == "react"]
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
            return cog.triggers[guild.id][argument]
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
