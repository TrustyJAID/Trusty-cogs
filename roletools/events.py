import asyncio
import logging
from typing import List, Optional, Union
from datetime import datetime, timedelta

import discord
from redbot.core import Config, commands
from redbot.core.bot import Red
from redbot.core.i18n import Translator

log = logging.getLogger("red.trusty-cogs.roletools")

_ = Translator("Roletools", __file__)


class RoleEvents:

    bot: Red
    config: Config
    settings: dict

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        channel = self.bot.get_channel(payload.channel_id)
        guild = getattr(channel, "guild", None)
        if not guild:
            return
        if await self.bot.cog_disabled_in_guild(self, guild):
            return
        if guild.id not in self.settings:
            return
        if getattr(payload.emoji, "id"):
            key = f"{payload.channel_id}-{payload.message_id}-{payload.emoji.id}"
        else:
            key = f"{payload.channel_id}-{payload.message_id}-{payload.emoji}"
        guild_settings = self.settings[guild.id]["reaction_roles"]
        if key in guild_settings:
            # add roles

            role = guild.get_role(guild_settings[key])
            if not await self.config.role(role).selfassignable():
                return
            log.debug("Adding role")
            member = guild.get_member(payload.user_id)
            if not role or not member:
                return
            if member.bot:
                return
            await self.give_roles(member, [role], _("Reaction Role"))

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        channel = self.bot.get_channel(payload.channel_id)
        guild = getattr(channel, "guild", None)
        if not guild:
            return
        if await self.bot.cog_disabled_in_guild(self, guild):
            return
        if guild.id not in self.settings:
            return
        if getattr(payload.emoji, "id"):
            key = f"{payload.channel_id}-{payload.message_id}-{payload.emoji.id}"
        else:
            key = f"{payload.channel_id}-{payload.message_id}-{payload.emoji}"
        guild_settings = self.settings[guild.id]["reaction_roles"]
        key = f"{payload.channel_id}-{payload.message_id}-{payload.emoji}"
        if key in guild_settings:
            # add roles
            role = guild.get_role(guild_settings[key])
            if not await self.config.role(role).selfremoveable():
                return
            log.debug("Removing role")
            member = guild.get_member(payload.user_id)
            if not role or not member:
                return
            if member.bot:
                return
            await self.remove_roles(member, [role], _("Reaction Role"))

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        if await self.bot.cog_disabled_in_guild(self, member.guild):
            return
        await self._sticky_remove(member)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if await self.bot.cog_disabled_in_guild(self, member.guild):
            return
        await self._sticky_join(member)
        await self._auto_give(member)

    async def check_guild_verification(
        self, member: discord.Member, guild: discord.Guild
    ) -> Union[bool, int]:
        allowed_discord = datetime.utcnow() - member.created_at
        # since discords check for verification level 2 is actually discord age not join age
        allowed_server = (
            (datetime.utcnow() - member.joined_at) if member.joined_at else timedelta(minutes=10)
        )
        if guild.verification_level.value >= 2 and allowed_discord <= timedelta(minutes=5):
            return 300 - int(allowed_discord.total_seconds())
        elif guild.verification_level.value >= 3 and allowed_server <= timedelta(minutes=10):
            return 600 - int(allowed_server.total_seconds())
        return False

    async def wait_for_verification(self, member: discord.Member, guild: discord.Guild) -> None:
        wait = await self.check_guild_verification(member, guild)
        if not member.roles or wait:
            log.info(
                f"Waiting {wait} seconds before allowing the user to have a role"
            )
            await asyncio.sleep(int(wait))

    async def give_roles(
        self, member: discord.Member, roles: List[discord.Role], reason: Optional[str] = None
    ):
        """
        Handles all the logic for applying roles to a user
        """
        if not member.guild.get_member(member.id):
            return
        guild = member.guild
        if not guild.me.guild_permissions.manage_roles:
            return
        for role in roles:
            if role is None or role > guild.me.top_role:
                continue
            await member.add_roles(role, reason=reason)

    async def remove_roles(
        self, member: discord.Member, roles: List[discord.Role], reason: Optional[str] = None
    ):
        """
        Handles all the logic for applying roles to a user
        """
        if not member.guild.get_member(member.id):
            return
        guild = member.guild
        if not guild.me.guild_permissions.manage_roles:
            return
        for role in roles:
            if role is None or role > guild.me.top_role:
                if role is None:
                    log.debug("A role could not be found.")
                if role > guild.me.top_role:
                    log.debug("A role was tried to be added that is higher than my own roles.")
                continue
            await member.remove_roles(role, reason=reason)

    async def _auto_give(self, member: discord.Member) -> None:
        guild = member.guild
        if guild.id not in self.settings:
            return
        await self.wait_for_verification(member, guild)
        roles_ids = self.settings[guild.id]["auto_roles"]
        roles = [guild.get_role(role) for role in roles_ids]
        await self.give_roles(member, roles, _("Automatic Roles"))

    async def _sticky_remove(self, member: discord.Member):
        guild = member.guild
        if await self.bot.cog_disabled_in_guild(self, guild):
            return
        sticky_roles = await self.config.guild(guild).sticky_roles()
        to_reapply = await self.config.member(member).sticky_roles()
        if not sticky_roles:
            return

        save = False

        for role in member.roles:
            if role.id in sticky_roles:
                if role.id not in to_reapply:
                    to_reapply.append(role.id)
                    save = True

        if save:
            await self.config.member(member).to_reapply.set(to_reapply)

    async def _sticky_join(self, member: discord.Member):
        guild = member.guild
        if await self.bot.cog_disabled_in_guild(self, guild):
            return
        sticky_roles = await self.config.guild(guild).sticky_roles()
        to_reapply = await self.config.member(member).to_reapply()
        if not to_reapply:
            return

        to_add = []

        for role_id in to_reapply:
            if role_id not in sticky_roles:
                continue
            role = guild.get_role(role_id)
            if role:
                to_add.append(role)

        if to_add:
            await self.give_roles(member, to_add, _("Sticky Roles"))
