import logging
from datetime import datetime
from typing import Dict, List, Literal, Optional, Sequence, Union

import discord
from discord.enums import InteractionType
from discord.app_commands import Choice
from redbot.core import commands
from redbot.core.i18n import Translator

from .abc import MixinMeta
from .constants import TEAMS
from .helper import DATE_RE

_ = Translator("Hockey", __file__)

log = logging.getLogger("red.trusty-cogs.Hockey")


class HockeySlash(MixinMeta):
    #######################################################################
    # Where parsing of slash commands happens                             #
    #######################################################################
    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        # log.debug(f"Interaction received {interaction.data['name']}")
        interaction_id = int(interaction.data.get("id", 0))
        guild = interaction.guild
        if guild and interaction.guild.id in self.slash_commands["guilds"]:
            if interaction_id in self.slash_commands["guilds"][interaction.guild.id]:
                if await self.pre_check_slash(interaction):
                    await self.slash_commands["guilds"][interaction.guild.id][interaction_id](
                        interaction
                    )
        if interaction_id in self.slash_commands:
            if await self.pre_check_slash(interaction):
                await self.slash_commands[interaction_id](interaction)

    @staticmethod
    def convert_slash_args(interaction: discord.Interaction, option: dict):
        convert_args = {
            3: lambda x: x,
            4: lambda x: int(x),
            5: lambda x: bool(x),
            6: lambda x: final_resolved[int(x)] or interaction.guild.get_member(int(x)),
            7: lambda x: final_resolved[int(x)] or interaction.guild.get_channel(int(x)),
            8: lambda x: final_resolved[int(x)] or interaction.guild.get_role(int(x)),
            9: lambda x: final_resolved[int(x)]
            or interaction.guild.get_role(int(x))
            or interaction.guild.get_member(int(x)),
            10: lambda x: float(x),
        }
        resolved = interaction.data.get("resolved", {})
        final_resolved = {}
        if resolved:
            resolved_users = resolved.get("users")
            if resolved_users:
                resolved_members = resolved.get("members")
                for _id, data in resolved_users.items():
                    if resolved_members:
                        member_data = resolved_members[_id]
                        member_data["user"] = data
                        member = discord.Member(
                            data=member_data, guild=interaction.guild, state=interaction._state
                        )
                        final_resolved[int(_id)] = member
                    else:
                        user = discord.User(data=data, state=interaction._state)
                        final_resolved[int(_id)] = user
            resolved_channels = resolved.get("channels")
            if resolved_channels:
                for _id, data in resolved_channels.items():
                    data["position"] = None
                    _cls, _ = discord.channel._guild_channel_factory(data["type"])
                    channel = _cls(state=interaction._state, guild=interaction.guild, data=data)
                    final_resolved[int(_id)] = channel
            resolved_messages = resolved.get("messages")
            if resolved_messages:
                for _id, data in resolved_messages.items():
                    msg = discord.Message(
                        state=interaction._state, channel=interaction.channel, data=data
                    )
                    final_resolved[int(_id)] = msg
            resolved_roles = resolved.get("roles")
            if resolved_roles:
                for _id, data in resolved_roles.items():
                    role = discord.Role(
                        guild=interaction.guild, state=interaction._state, data=data
                    )
                    final_resolved[int(_id)] = role
        return convert_args[option["type"]](option["value"])

    async def check_requires(self, func, interaction):
        fake_ctx = discord.Object(id=interaction.id)
        fake_ctx.author = interaction.user
        fake_ctx.guild = interaction.guild
        fake_ctx.bot = self.bot
        fake_ctx.cog = self
        fake_ctx.command = func
        fake_ctx.permission_state = commands.requires.PermState.NORMAL

        if isinstance(interaction.channel, discord.channel.PartialMessageable):
            channel = interaction.user.dm_channel or await interaction.user.create_dm()
        else:
            channel = interaction.channel

        fake_ctx.channel = channel
        resp = await func.requires.verify(fake_ctx)
        if not resp:
            await interaction.response.send_message(
                _("You are not authorized to use this command."), ephemeral=True
            )
        return resp

    async def pre_check_slash(self, interaction):
        if not await self.bot.allowed_by_whitelist_blacklist(interaction.user):
            await interaction.response.send_message(
                _("You are not allowed to run this command here."), ephemeral=True
            )
            return False
        fake_ctx = discord.Object(id=interaction.id)
        fake_ctx.author = interaction.user
        fake_ctx.guild = interaction.guild
        if isinstance(interaction.channel, discord.channel.PartialMessageable):
            channel = interaction.user.dm_channel or await interaction.user.create_dm()
        else:
            channel = interaction.channel

        fake_ctx.channel = channel
        if not await self.bot.ignored_channel_or_guild(fake_ctx):
            await interaction.response.send_message(
                _("Commands are not allowed in this channel or guild."), ephemeral=True
            )
            return False
        return True

    async def team_autocomplete(
        self, interaction: discord.Interaction, include_inactive: bool, include_all: bool
    ) -> Optional[dict]:
        if interaction.type is InteractionType.autocomplete:
            for cmd in interaction.data.get("options", []):
                if cmd.get("focused", False):
                    current_data = cmd.get("value", "")
                for group in cmd.get("options", []):
                    if group.get("focused", False):
                        current_data = group.get("value", "")
                    for sub in group.get("options", []):
                        if sub.get("focused", False):
                            current_data = sub.get("value", "")
            if include_all:
                team_choices = [Choice(name="All", value="all")]
            else:
                team_choices = []
            for t, d in TEAMS.items():
                if current_data.lower() in t.lower():
                    if not include_inactive and not d["active"]:
                        continue
                    team_choices.append(Choice(name=t, value=t))
            await interaction.response.autocomplete(team_choices[:25])
            return None

    async def parse_teams_and_date(self, interaction: discord.Interaction) -> Optional[dict]:
        if interaction.type is InteractionType.autocomplete:
            current_data = interaction.data["options"][0]["options"][0].get("value", "").lower()
            team_choices = [
                Choice(name=t, value=t) for t, d in TEAMS.items() if current_data in t.lower()
            ]
            await interaction.response.autocomplete(team_choices[:25])
            return None
        kwargs = {}
        kwargs["teams_and_date"] = {}
        for option in interaction.data["options"][0].get("options", []):
            name = option["name"]
            if name == "date":
                find = DATE_RE.search(option["value"])
                date_str = f"{find.group(1)}-{find.group(3)}-{find.group(4)}"
                kwargs["teams_and_date"][name] = datetime.strptime(date_str, "%Y-%m-%d")
            else:
                kwargs["teams_and_date"][name] = [option["value"]]
        return kwargs

    async def hockey_slash_commands(self, interaction: discord.Interaction) -> None:
        """
        Get information from NHL.com
        """
        command_mapping = {
            "standings": self.standings,
            "games": self.games,
            "heatmap": self.heatmap,
            "gameflow": self.gameflow,
            "schedule": self.schedule,
            "player": self.player,
            "roster": self.roster,
            "leaderboard": self.leaderboard,
            "otherdiscords": self.otherdiscords,
            "set": self.slash_hockey_set,
            "pickems": self.slash_pickems_commands,
            "gdt": self.slash_gdt_commands,
        }
        option = interaction.data["options"][0]["name"]
        func = command_mapping[option]

        if option in ["games", "schedule", "heatmap", "gameflow"]:
            kwargs = await self.parse_teams_and_date(interaction)
            if kwargs:
                await func(interaction, **kwargs)
            return
        if option == "otherdiscords" and interaction.type is InteractionType.autocomplete:
            await self.team_autocomplete(interaction, False, False)
            return
        if option == "roster" and interaction.type is InteractionType.autocomplete:
            await self.team_autocomplete(interaction, True, False)
            return
        if option == "player" and interaction.type is InteractionType.autocomplete:
            current_data = interaction.data["options"][0]["options"][0].get("value", "").lower()
            player_choices = await self.player_choices(current_data)
            await interaction.response.autocomplete(player_choices[:25])
            return
        if getattr(func, "requires", None):
            if not await self.check_requires(func, interaction):
                return
        try:
            kwargs = {}
            for option in interaction.data["options"][0].get("options", []):
                name = option["name"]
                kwargs[name] = self.convert_slash_args(interaction, option)
        except KeyError:
            kwargs = {}
            pass
        await func(interaction, **kwargs)
        pass

    async def slash_pickems_commands(self, interaction: discord.Interaction) -> None:
        """
        Get information from NHL.com
        """
        command_mapping = {
            "settings": self.pickems_settings,
            "basecredits": self.pickems_credits_base,
            "topcredits": self.pickems_credits_top,
            "winners": self.pickems_credits_amount,
            "message": self.set_pickems_message,
            "setup": self.setup_auto_pickems,
            "clear": self.delete_auto_pickems,
            "page": self.pickems_page,
            "votes": self.pickemsvotes,
        }
        option = interaction.data["options"][0]["options"][0]["name"]
        func = command_mapping[option]
        if getattr(func, "requires", None):
            if not await self.check_requires(func, interaction):
                return
        try:
            kwargs = {}
            for option in interaction.data["options"][0]["options"][0].get("options", []):
                name = option["name"]
                kwargs[name] = self.convert_slash_args(interaction, option)
        except KeyError:
            kwargs = {}
            pass
        await func(interaction, **kwargs)
        pass

    async def slash_gdt_commands(self, interaction: discord.Interaction) -> None:
        command_mapping = {
            "settings": self.gdt_settings,
            "delete": self.gdt_delete,
            "defaultstate": self.gdt_default_game_state,
            "create": self.gdt_create,
            "toggle": self.gdt_toggle,
            "channel": self.gdt_channel,
            "setup": self.gdt_setup,
        }
        option = interaction.data["options"][0]["options"][0]["name"]
        func = command_mapping[option]
        if option == "setup" and interaction.type is InteractionType.autocomplete:
            await self.team_autocomplete(interaction, False, True)
            return
        if getattr(func, "requires", None):
            if not await self.check_requires(func, interaction):
                return
        try:
            kwargs = {}
            for option in interaction.data["options"][0]["options"][0].get("options", []):
                name = option["name"]
                kwargs[name] = self.convert_slash_args(interaction, option)
        except KeyError:
            kwargs = {}
            pass
        await func(interaction, **kwargs)
        pass

    async def slash_hockey_set(self, interaction: discord.Interaction) -> None:
        """
        Get information from NHL.com
        """
        if not interaction.guild:
            await interaction.response.send_message(
                _("These commands are only available in a guild.")
            )
            return
        if not await self.slash_check_permissions(
            interaction, interaction.user, manage_messages=True
        ):
            await interaction.response.send_message(
                _("You are not authorized to use this command."), ephemeral=True
            )
            return
        command_mapping = {
            "settings": self.hockey_settings,
            "poststandings": self.post_standings,
            "add": self.add_goals,
            "remove": self.remove_goals,
            "stateupdates": self.set_game_state_updates,
        }
        option = interaction.data["options"][0]["options"][0]["name"]
        func = command_mapping[option]
        if option == "add" and interaction.type is InteractionType.autocomplete:
            await self.team_autocomplete(interaction, False, True)
            return
        if getattr(func, "requires", None):
            if not await self.check_requires(func, interaction):
                return
        try:
            kwargs = {}
            for option in interaction.data["options"][0]["options"][0].get("options", []):
                name = option["name"]
                kwargs[name] = self.convert_slash_args(interaction, option)
        except KeyError:
            kwargs = {}
            pass
        log.debug(kwargs)
        await func(interaction, **kwargs)
        pass
