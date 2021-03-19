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
        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return
        if await self.bot.cog_disabled_in_guild(self, guild):
            return
        if guild.id not in self.settings:
            return
        if getattr(payload.emoji, "id", None):
            key = f"{payload.channel_id}-{payload.message_id}-{payload.emoji.id}"
        else:
            emoji = str(payload.emoji).strip("\N{VARIATION SELECTOR-16}")
            key = f"{payload.channel_id}-{payload.message_id}-{emoji}"
        guild_settings = self.settings[guild.id]["reaction_roles"]
        if key in guild_settings:
            # add roles

            role = guild.get_role(guild_settings[key])
            if not await self.config.role(role).selfassignable():
                return
            member = guild.get_member(payload.user_id)
            if not role or not member:
                return
            if member.bot:
                return
            if await self.check_guild_verification(member, guild):
                log.debug("Ignoring user due to verification check.")
                return
            if getattr(member, "pending", False):
                return
            log.debug(f"Adding role to {member.name} in {member.guild}")
            await self.give_roles(member, [role], _("Reaction Role"))

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return
        if await self.bot.cog_disabled_in_guild(self, guild):
            return
        if guild.id not in self.settings:
            return
        if getattr(payload.emoji, "id", None):
            key = f"{payload.channel_id}-{payload.message_id}-{payload.emoji.id}"
        else:
            emoji = str(payload.emoji).strip("\N{VARIATION SELECTOR-16}")
            key = f"{payload.channel_id}-{payload.message_id}-{emoji}"
        guild_settings = self.settings[guild.id]["reaction_roles"]
        if key in guild_settings:
            # add roles
            role = guild.get_role(guild_settings[key])
            if not await self.config.role(role).selfremovable():
                return

            member = guild.get_member(payload.user_id)
            if not role or not member:
                return
            if member.bot:
                return
            log.debug(f"Removing role from {member.name} in {member.guild}")
            await self.remove_roles(member, [role], _("Reaction Role"))

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if await self.bot.cog_disabled_in_guild(self, before.guild):
            return
        before_pending = getattr(before, "pending", False)
        after_pending = getattr(after, "pending", False)
        if before_pending != after_pending:
            await self._auto_give(after)
        removed_roles = list(set(before.roles) - set(after.roles))
        added_roles = list(set(after.roles) - set(before.roles))
        for role in added_roles:
            if await self.config.role(role).sticky():
                async with self.config.member(after).sticky_roles() as roles:
                    if role.id not in roles:
                        roles.append(role.id)
        for role in removed_roles:
            if await self.config.role(role).sticky():
                async with self.config.member(after).sticky_roles() as roles:
                    if role.id in roles:
                        roles.remove(role.id)

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
        if getattr(member, "pending", False):
            return
        await self._auto_give(member)

    async def check_guild_verification(
        self, member: discord.Member, guild: discord.Guild
    ) -> Union[bool, int]:
        if member.roles:
            return False
        allowed_discord = datetime.utcnow() - member.created_at
        # since discords check for verification level 2 is actually discord age not join age
        allowed_server = (
            (datetime.utcnow() - member.joined_at) if member.joined_at else timedelta(minutes=10)
        )
        if guild.verification_level.value >= 2 and allowed_discord <= timedelta(minutes=5):
            log.debug(f"Waiting 5 minutes for {member.name} in {guild}")
            return 300 - int(allowed_discord.total_seconds())
        elif guild.verification_level.value >= 3 and allowed_server <= timedelta(minutes=10):
            log.debug(f"Waiting 10 minutes for {member.name} in {guild}")
            return 600 - int(allowed_server.total_seconds())
        return False

    async def wait_for_verification(self, member: discord.Member, guild: discord.Guild) -> None:
        wait = await self.check_guild_verification(member, guild)
        if wait:
            log.debug(
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
        to_add = []
        for role in roles:
            if role is None or role >= guild.me.top_role:
                continue
            if required := await self.config.role(role).required():
                has_required = True
                for role_id in required:
                    r = guild.get_role(role_id)
                    if not r:
                        continue
                    if r not in member.roles:
                        has_required = False
                if not has_required:
                    continue
            if inclusive := await self.config.role(role).inclusive_with():
                inclusive_roles = []
                for role_id in inclusive:
                    log.debug(role_id)
                    r = guild.get_role(role_id)
                    if r and await self.config.role(r).selfassignable():
                        inclusive_roles.append(r)
                await member.add_roles(*inclusive_roles, reason=_("Inclusive Roles"))
            if exclusive := await self.config.role(role).exclusive_to():
                exclusive_roles = []
                skip_role_assign = False
                for role_id in exclusive:
                    r = guild.get_role(role_id)
                    if r in member.roles:
                        if await self.config.role(r).selfremovable():
                            exclusive_roles.append(r)
                        else:
                            # we want to only remove the role (and assign the new one)
                            # if the current role is self-removable
                            # If the role is not self-removable we don't want
                            # to apply the initial role to begin with
                            skip_role_assign = True
                if skip_role_assign:
                    # we want to skip assigning the role which means the continue
                    # needs to be here
                    # I don't think we should be removing roles at all if this
                    # is the case but if required this can be adjusted in the future
                    continue
                await self.remove_roles(member, exclusive_roles, _("Exclusive Roles"))
            to_add.append(role)
        await member.add_roles(*to_add, reason=reason)

    async def remove_roles(
        self, member: discord.Member, roles: List[discord.Role], reason: Optional[str] = None
    ):
        """
        Handles all the logic for removing roles from a user
        """
        if not member.guild.get_member(member.id):
            return
        guild = member.guild
        if not guild.me.guild_permissions.manage_roles:
            return
        for role in roles:
            if role is None or role.position >= guild.me.top_role.position:
                continue
            if inclusive := await self.config.role(role).inclusive_with():
                inclusive_roles = []
                for role_id in inclusive:
                    r = guild.get_role(role_id)
                    if not r:
                        continue
                    if r in member.roles and await self.config.role(r).selfremovable():
                        inclusive_roles.append(r)
                await member.remove_roles(*inclusive_roles, reason=_("Inclusive Roles"))
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
        to_reapply = await self.config.member(member).sticky_roles()
        save = False
        for role in member.roles:
            if not await self.config.role(role).sticky():
                continue
            if role.id not in to_reapply:
                to_reapply.append(role.id)
                save = True

        if save:
            await self.config.member(member).sticky_roles.set(to_reapply)

    async def _sticky_join(self, member: discord.Member):
        guild = member.guild
        if await self.bot.cog_disabled_in_guild(self, guild):
            return
        to_reapply = await self.config.member(member).sticky_roles()
        if not to_reapply:
            return

        to_add = []

        for role_id in to_reapply:
            role = guild.get_role(role_id)
            if role and role < guild.me.top_role:
                to_add.append(role)

        if to_add:
            # use this to prevent issues with inclusive/exclusive roles
            # That may have previously been assigned manually
            await member.add_roles(*to_add, reason=_("Sticky Roles"))
