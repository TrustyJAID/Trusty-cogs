from __future__ import annotations

import enum
from datetime import timedelta
from typing import List, Optional, Tuple

import discord
from discord.ext.commands import Converter, FlagConverter, flag
from redbot.core import commands
from redbot.core.commands.converter import get_timedelta_converter

TimedeltaConverter = get_timedelta_converter(
    maximum=timedelta(days=28), allowed_units=["minutes", "seconds", "weeks", "days", "hours"]
)


class EnumConverter(Converter):
    _enum: enum.Enum

    async def convert(self, ctx: commands.Context, argument: str):
        for e in self._enum:
            if e.name.lower() == argument.lower():
                return e
        valid_choices = "\n".join(f"- {e.name}" for e in self._enum)
        raise commands.BadArgument(f"`{argument}` is not valid. Choose from:\n{valid_choices}")


class AutoModRuleConverter(EnumConverter):
    _enum = discord.AutoModRuleEventType


class StrListTransformer(discord.app_commands.Transformer):
    async def convert(self, ctx: commands.Context, argument: str) -> List[str]:
        return argument.split(" ")

    async def transform(self, interaction: discord.Interaction, argument: str) -> List[str]:
        return argument.split(" ")


class RoleListTransformer(discord.app_commands.Transformer):
    async def convert(self, ctx: commands.Context, argument: str) -> List[discord.Role]:
        possible_roles = argument.split(" ")
        roles = []
        for role in possible_roles:
            if not role:
                continue
            try:
                r = await commands.RoleConverter().convert(ctx, role.strip())
                roles.append(r)
            except commands.BadArgument:
                raise
        return roles

    async def transform(
        self, interaction: discord.Interaction, argument: str
    ) -> List[discord.Role]:
        ctx = await interaction.client.get_context(interaction)
        return await self.convert(ctx, argument)


class ChannelListTransformer(discord.app_commands.Transformer):
    async def convert(
        self, ctx: commands.Context, argument: str
    ) -> List[discord.abc.GuildChannel]:
        possible_channels = argument.split(" ")
        channels = []
        for channel in possible_channels:
            if not channel:
                continue
            try:
                c = await commands.GuildChannelConverter().convert(ctx, channel.strip())
                channels.append(c)
            except commands.BadArgument:
                raise
        return channels

    async def transform(
        self, interaction: discord.Interaction, argument: str
    ) -> List[discord.abc.GuildChannel]:
        ctx = await interaction.client.get_context(interaction)
        return await self.convert(ctx, argument)


class AutoModTriggerConverter(discord.app_commands.Transformer):
    async def convert(self, ctx: commands.Context, argument: str) -> discord.AutoModTrigger:
        cog = ctx.bot.get_cog("AutoMod")
        async with cog.config.guild(ctx.guild).triggers() as triggers:
            if argument.lower() in triggers:
                kwargs = triggers[argument.lower()].copy()

                passed_args = {}
                if kwargs.get("presets") is not None:
                    # as far as I can tell this is the sanest way to manage
                    # this until d.py adds a better method of dealing with
                    # these awful flags
                    presets = discord.AutoModPresets.none()
                    saved_presets = kwargs.pop("presets", []) or []
                    for p in saved_presets:
                        presets.value |= p
                    passed_args["presets"] = presets
                for key, value in kwargs.items():
                    if value is not None:
                        passed_args[key] = value
                return discord.AutoModTrigger(**kwargs)
            else:
                raise commands.BadArgument(
                    ("Trigger with name `{name}` does not exist.").format(name=argument.lower())
                )

    async def transform(
        self, interaction: discord.Interaction, argument: str
    ) -> discord.AutoModTrigger:
        ctx = await interaction.client.get_context(interaction)
        return await self.convert(ctx, argument)

    async def autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> List[discord.app_commands.Choice]:
        cog = interaction.client.get_cog("AutoMod")
        choices = []
        async with cog.config.guild(interaction.guild).triggers() as triggers:
            for t in triggers.keys():
                choices.append(discord.app_commands.Choice(name=t, value=t))
        return [t for t in choices if current.lower() in t.name.lower()][:25]


class AutoModActionConverter(discord.app_commands.Transformer):
    async def convert(
        self, ctx: commands.Context, argument: str
    ) -> List[discord.AutoModRuleAction]:
        cog = ctx.bot.get_cog("AutoMod")
        ret = []
        actions = await cog.config.guild(ctx.guild).actions()
        for a in argument.split(" "):
            if a.lower() in actions:
                action_args = actions[a.lower()]
                duration = action_args.pop("duration", None)
                if duration:
                    duration = timedelta(seconds=duration)
                ret.append(discord.AutoModRuleAction(**action_args, duration=duration))
        if not ret:
            raise commands.BadArgument(
                ("Action with name `{name}` does not exist.").format(name=argument.lower())
            )
        ret.append(discord.AutoModRuleAction())
        return ret

    async def transform(
        self, interaction: discord.Interaction, argument: str
    ) -> List[discord.AutoModRuleAction]:
        ctx = await interaction.client.get_context(interaction)
        return await self.convert(ctx, argument)

    async def autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> List[discord.app_commands.Choice]:
        cog = interaction.client.get_cog("AutoMod")
        ret = []
        supplied_actions = ""
        new_action = ""
        actions = await cog.config.guild(interaction.guild).actions()
        for sup in current.lower().split(" "):
            if sup in actions:
                supplied_actions += f"{sup} "
            else:
                new_action = sup
        ret = [
            discord.app_commands.Choice(
                name=f"{supplied_actions} {g}", value=f"{supplied_actions} {g}"
            )
            for g in actions.keys()
            if new_action in g
        ]
        if supplied_actions:
            ret.insert(
                0, discord.app_commands.Choice(name=supplied_actions, value=supplied_actions)
            )
        return ret[:25]


class AutoModRuleFlags(FlagConverter, case_insensitive=True):
    """AutoMod Rule converter"""

    """
    # remove the event_type for now since there's only one possible option
    event_type: Optional[AutoModRuleConverter] = flag(
        name="event",
        aliases=[],
        default=discord.AutoModRuleEventType.message_send,
        description="",
    )
    """
    trigger: Optional[AutoModTriggerConverter] = flag(
        name="trigger",
        aliases=[],
        default=None,
        description="The name of the trigger you have setup.",
    )
    actions: AutoModActionConverter = flag(
        name="actions",
        aliases=[],
        default=[],
        description="The name(s) of the action(s) you have setup.",
    )
    enabled: bool = flag(
        name="enabled",
        aliases=[],
        default=False,
        description="Wheter to immediately enable this rule.",
    )
    exempt_roles: RoleListTransformer = flag(
        name="roles",
        aliases=["exempt_roles"],
        default=[],
        description="The roles to be exempt from this rule.",
    )
    exempt_channels: ChannelListTransformer = flag(
        name="channels",
        aliases=[],
        default=[],
        description="The channels to be exempt from this rule.",
    )
    reason: Optional[str] = flag(
        name="reason",
        aliases=[],
        default=None,
        description="The reason for creating this rule.",
    )

    def to_str(self):
        ret = ""
        for k, v in self.to_json().items():
            if v is None:
                continue
            if k == "presets" and self.presets:
                v = "\n".join(f" - {k}" for k, v in dict(self.presets).items() if v)
                ret += f"- {k}:\n{v}\n"
                continue
            ret += f"- {k}: {v}\n"
        return ret

    def to_args(self):
        actions = self.actions
        if not actions:
            actions = [discord.AutoModRuleAction()]
        return {
            "event_type": discord.AutoModRuleEventType.message_send,
            "trigger": self.trigger,
            "actions": actions,
            "enabled": self.enabled,
            "exempt_roles": self.exempt_roles,
            "exempt_channels": self.exempt_channels,
            "reason": self.reason,
        }


class AutoModPresetsConverter(discord.app_commands.Transformer):
    async def convert(self, ctx: commands.Context, argument: str) -> discord.AutoModPresets:
        ret = discord.AutoModPresets.none()
        for possible in argument.lower().split(" "):
            if possible in dict(discord.AutoModPresets.all()):
                ret |= discord.AutoModPresets(**{possible.lower(): True})
        if ret is discord.AutoModPresets.none():
            valid_choices = "\n".join(f"- {e}" for e in dict(discord.AutoModPresets.all()).keys())
            raise commands.BadArgument(f"`{argument}` is not valid. Choose from:\n{valid_choices}")
        return ret

    async def transform(
        self, interaction: discord.Interaction, argument: str
    ) -> discord.AutoModPresets:
        ctx = await interaction.client.get_context(interaction)
        return await self.convert(ctx, argument)


class AutoModTriggerFlags(FlagConverter, case_insensitive=True):
    allow_list: List[str] = flag(
        name="allows",
        aliases=[],
        default=None,
        converter=StrListTransformer,
        description="A space separated list of words to allow.",
    )
    keyword_filter: List[str] = flag(
        name="keywords",
        aliases=[],
        default=None,
        converter=StrListTransformer,
        description="A space separated list of words to filter.",
    )
    mention_limit: Optional[commands.Range[int, 0, 50]] = flag(
        name="mentions",
        aliases=[],
        default=None,
        description="The number of mentions to allow (0-50).",
    )
    presets: Optional[discord.AutoModPresets] = flag(
        name="presets",
        aliases=[],
        default=None,
        converter=AutoModPresetsConverter,
        description="Use any combination of discords default presets.",
    )
    regex_patterns: List[str] = flag(
        name="regex",
        aliases=[],
        default=None,
        converter=StrListTransformer,
        description="A space separated list of regex patterns to include.",
    )

    def to_str(self):
        ret = ""
        for k, v in self.to_json().items():
            if v is None:
                continue
            if k == "presets" and self.presets:
                v = "\n".join(f" - {k}" for k, v in dict(self.presets).items() if v)
                ret += f"- {k}:\n{v}\n"
                continue
            ret += f"- {k}: {v}\n"
        return ret

    def to_json(self):
        return {
            "allow_list": self.allow_list,
            "keyword_filter": self.keyword_filter,
            "mention_limit": self.mention_limit,
            "regex_patterns": self.regex_patterns,
            "presets": self.presets.to_array() if self.presets else None,
        }

    def get_trigger(self):
        return discord.AutoModTrigger(
            keyword_filter=self.keyword_filter,
            presets=self.presets,
            allow_list=self.allow_list,
            mention_limit=self.mention_limit,
            regex_patterns=self.regex_patterns,
        )


class AutoModActionFlags(FlagConverter, case_insensitive=True):
    custom_message: Optional[commands.Range[str, 1, 150]] = flag(
        name="message",
        aliases=[],
        default=None,
        description="A custom message to send to the user.",
    )
    channel_id: Optional[discord.TextChannel] = flag(
        name="channel",
        aliases=[],
        default=None,
        description="The channel to send a notification to.",
    )
    duration: Optional[timedelta] = flag(
        name="duration",
        aliases=[],
        default=None,
        description="How long to timeout the user for.",
        converter=TimedeltaConverter,
    )

    def to_str(self):
        ret = ""
        for k, v in self.to_json().items():
            if v is None:
                continue
            ret += f"- {k}: {v}\n"
        return ret

    def to_json(self):
        return {
            "custom_message": self.custom_message,
            "channel_id": self.channel_id.id if self.channel_id else None,
            "duration": int(self.duration.total_seconds()) if self.duration else None,
        }

    def get_action(self):
        return discord.AutoModRuleAction(
            custom_message=self.custom_message,
            channel_id=self.channel_id.id if self.channel_id else None,
            duration=self.duration,
        )
