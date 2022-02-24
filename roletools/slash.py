import logging

import discord
from redbot.core import Config, commands
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import humanize_timedelta

from .abc import RoleToolsMixin

_ = Translator("ReTrigger", __file__)
log = logging.getLogger("red.trusty-cogs.ReTrigger")


class RoleToolsSlash(RoleToolsMixin):
    def __init__(self, *args):
        self.config: Config
        self.slash_commands: dict

    async def load_slash(self):
        all_guilds = await self.config.all_guilds()
        for guild_id, data in all_guilds.items():
            if data["commands"]:
                self.slash_commands["guilds"][guild_id] = {}
                for command, command_id in data["commands"].items():
                    if command == "roletools":
                        self.slash_commands["guilds"][guild_id][command_id] = self.roletools
        commands = await self.config.commands()
        for command_name, command_id in commands.items():
            if command_name == "roletools":
                self.slash_commands[command_id] = self.roletools

    async def role_hierarchy_options(self, interaction: discord.Interaction):
        guild = interaction.guild
        roles = guild.roles
        user = interaction.user
        cur_data = ""
        for options in interaction.data.get("options", []):
            if options.get("focused", False):
                cur_data = options.get("value", "")
            for sub_options in options.get("options", []):
                if sub_options.get("focused", False):
                    cur_data = sub_option.get("value", "")
                for op in sub_options.get("options", []):
                    if op.get("focused", False):
                        cur_data = op.get("value", "")

        options = [
            {"name": f"@{r.name}", "value": f"{r.id}"}
            for r in roles
            if r < user.top_role and cur_data in r.name
        ]
        return options

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

    async def check_requires(self, func, interaction: discord.Interaction):
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

    async def check_cooldowns(self, func, interaction: discord.Interaction):
        fake_ctx = discord.Object(id=interaction.id)
        fake_ctx.author = interaction.user
        fake_ctx.guild = interaction.guild
        fake_ctx.bot = self.bot
        fake_ctx.cog = self
        fake_ctx.command = func
        fake_ctx.permission_state = commands.requires.PermState.NORMAL
        fake_message = discord.Object(id=interaction.id)
        fake_message.edited_at = None
        fake_ctx.message = fake_message
        try:
            func._prepare_cooldowns(fake_ctx)
        except commands.CommandOnCooldown as e:
            await interaction.response.send_message(
                _("This command is still on cooldown. Try again in {time}.").format(
                    time=humanize_timedelta(seconds=e.retry_after)
                )
            )
            return False
        return True

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

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        # log.debug(f"Interaction received {interaction.data['name']}")
        interaction_id = int(interaction.data.get("id", 0))
        guild = interaction.guild
        if guild and guild.id in self.slash_commands["guilds"]:
            if interaction_id in self.slash_commands["guilds"][guild.id]:
                if await self.pre_check_slash(interaction):
                    await self.slash_commands["guilds"][guild.id][interaction_id](interaction)
        if interaction_id in self.slash_commands:
            if await self.pre_check_slash(interaction):
                await self.slash_commands[interaction_id](interaction)
                await self.slash_commands[interaction_id](interaction)
