from typing import Optional, Union

import discord
from red_commons.logging import getLogger
from redbot.core import commands
from redbot.core.commands import Context
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import pagify

from .abc import RoleToolsMixin
from .converter import RoleEmojiConverter, RoleHierarchyConverter
from .menus import BaseMenu, ReactRolePages

roletools = RoleToolsMixin.roletools

log = getLogger("red.Trusty-cogs.RoleTools")
_ = Translator("RoleTools", __file__)


class RoleToolsReactions(RoleToolsMixin):
    """This class contains commands related to reaction roles."""

    @roletools.group(name="reaction", aliases=["react", "reactions"])
    async def react_coms(self, ctx: Context) -> None:
        """Reaction role settings"""
        pass

    @react_coms.command(with_app_command=False)
    @commands.admin_or_permissions(manage_roles=True)
    async def cleanup(self, ctx: Context) -> None:
        """
        Cleanup old/missing reaction roles and settings.

        Note: This will also clear out reaction roles if the bot is just
        missing permissions to see the reactions.
        """
        guild = ctx.guild
        async with ctx.typing():
            async with self.config.guild(ctx.guild).reaction_roles() as cur_settings:
                to_remove = []
                for key, role_id in cur_settings.items():
                    chan_id, message_id, emoji = key.split("-")
                    channel = guild.get_channel(int(chan_id))
                    if not channel:
                        to_remove.append((key, role_id))
                        continue
                    my_perms = channel.permissions_for(guild.me)
                    if not my_perms.read_messages and not my_perms.read_message_history:
                        to_remove.append((key, role_id))
                        continue
                    try:
                        await channel.fetch_message(int(message_id))
                    except Exception:
                        to_remove.append((key, role_id))
                        continue
                    role = guild.get_role(int(role_id))
                    if not role:
                        to_remove.append((key, role_id))
                for key, role_id in to_remove:
                    del cur_settings[key]
                    try:
                        del self.settings[guild.id]["reaction_roles"][key]
                    except KeyError:
                        pass
                    async with self.config.role_from_id(role_id).reactions() as reactions:
                        reactions.remove(key)
        msg = _("I am finished deleting old settings.")
        await ctx.send(msg)

    @react_coms.command(hidden=True, with_app_command=False)
    @commands.is_owner()
    @commands.cooldown(1, 86400, commands.BucketType.default)
    async def ownercleanup(self, ctx: Context) -> None:
        """
        Cleanup old/missing reaction roles and settings on the bot.

        Note: This will also clear out reaction roles if the bot is just
        missing permissions to see the reactions.
        """
        async with ctx.typing():
            for guild_id in self.settings:
                guild = self.bot.get_guild(guild_id)
                if not guild:
                    continue
                async with self.config.guild(ctx.guild).reaction_roles() as cur_settings:
                    to_remove = []
                    for key, role_id in cur_settings.items():
                        chan_id, message_id, emoji = key.split("-")
                        channel = guild.get_channel(int(chan_id))
                        if not channel:
                            to_remove.append((key, role_id))
                            continue
                        my_perms = channel.permissions_for(guild.me)
                        if not my_perms.read_messages and not my_perms.read_message_history:
                            to_remove.append((key, role_id))
                            continue
                        try:
                            message = await channel.fetch_message(int(message_id))
                        except Exception:
                            to_remove.append((key, role_id))
                            continue
                        if not message:
                            to_remove.append((key, role_id))
                            continue
                        role = guild.get_role(int(role_id))
                        if not role:
                            to_remove.append((key, role_id))
                    for key, role_id in to_remove:
                        del cur_settings[key]
                        try:
                            del self.settings[guild.id]["reaction_roles"][key]
                        except KeyError:
                            pass
                        async with self.config.role_from_id(role_id).reactions() as reactions:
                            reactions.remove(key)
        await ctx.send(_("I am finished deleting old settings."))

    @react_coms.command(aliases=["reactionroles", "reactrole"])
    @commands.admin_or_permissions(manage_roles=True)
    @commands.bot_has_permissions(read_message_history=True, add_reactions=True)
    async def reactroles(self, ctx: Context) -> None:
        """
        View current bound roles in the server
        """
        if ctx.guild.id not in self.settings:
            msg = _("There are no bound roles in this server.")
            await ctx.send(msg)
            return
        msg = _("Reaction Roles in {guild}\n").format(guild=ctx.guild.name)
        for key, role_id in self.settings[ctx.guild.id]["reaction_roles"].items():
            channel_id, msg_id, emoji = key.split("-")
            if emoji.isdigit():
                emoji = self.bot.get_emoji(int(emoji))
            if not emoji:
                emoji = _("Emoji from another server")
            role = ctx.guild.get_role(role_id)
            channel = ctx.guild.get_channel(int(channel_id))
            if channel:
                # This can be potentially a very expensive operation
                # so instead we fake the message link unless the channel is missing
                # this way they can check themselves without rate limitng
                # the bot trying to fetch something constantly that is broken.
                message = f"https://discord.com/channels/{ctx.guild.id}/{channel_id}/{msg_id}"
            else:
                message = None
            msg += _("{emoji} - {role} [Reaction Message]({message})\n").format(
                role=role.mention if role else _("None"),
                emoji=emoji,
                message=message if message else _("None"),
            )
        pages = list(pagify(msg))
        await BaseMenu(
            source=ReactRolePages(
                pages=pages,
            ),
            delete_message_after=False,
            clear_reactions_after=True,
            timeout=60,
            cog=self,
            page_start=0,
        ).start(ctx=ctx)

    @react_coms.command(aliases=["clearreacts"], with_app_command=False)
    @commands.admin_or_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_messages=True)
    async def clearreact(
        self,
        ctx: Context,
        message: discord.Message,
        *emojis: Optional[Union[discord.Emoji, str]],
    ) -> None:
        """
        Clear the reactions for reaction roles. This will remove
        all reactions and then re-apply the bots reaction for you.

        `<message>` The message you want to clear reactions on.
        `[emojis...]` Optional emojis you want to specifically remove.
        If no emojis are provided this will clear all the reaction role
        emojis the bot has for the message provided.

        Note: This will only clear reactions which have a corresponding
        reaction role on it.
        """
        if not message.channel.permissions_for(ctx.guild.me).manage_messages:
            msg = _("I require manage messages in order to clear other people's reactions.")
            await ctx.send(msg)
            return
        if emojis:
            for emoji in emojis:
                final_key = str(getattr(emoji, "id", emoji)).strip("\N{VARIATION SELECTOR-16}")
                key = f"{message.channel.id}-{message.id}-{final_key}"
                if key in self.settings[ctx.guild.id]["reaction_roles"]:
                    __, __, emoji = key.split("-")
                    if emoji.isdigit():
                        emoji = self.bot.get_emoji(int(emoji))
                    try:
                        await message.clear_reaction(emoji)
                    except discord.Forbidden:
                        pass
                    await message.add_reaction(emoji)
        else:
            try:
                await message.clear_reactions()
            except discord.HTTPException:
                msg = _("There was an error clearing reactions on that message.")
                await ctx.send(msg)
                return
            for key in self.settings[ctx.guild.id]["reaction_roles"].keys():
                if f"{message.channel.id}-{message.id}" in key:
                    __, __, emoji = key.split("-")
                    if emoji.isdigit():
                        emoji = self.bot.get_emoji(int(emoji))
                    if emoji is None:
                        continue
                    try:
                        await message.add_reaction(emoji)
                    except discord.HTTPException:
                        pass
        await ctx.send(_("Finished clearing reactions on that message."))

    @react_coms.command(name="create", aliases=["make", "setup"], with_app_command=False)
    @commands.admin_or_permissions(manage_roles=True)
    async def make_react(
        self,
        ctx: Context,
        message: discord.Message,
        emoji: Union[discord.Emoji, str],
        *,
        role: RoleHierarchyConverter,
    ) -> None:
        """
        Create a reaction role

        `<message>` can be the channel_id-message_id pair
        from copying message ID while holding SHIFT or a message link
        `<emoji>` The emoji you want people to react with to get the role.
        `<role>` The role you want people to receive for reacting.
        """
        if not message.guild or message.guild.id != ctx.guild.id:
            msg = _("You cannot add a Reaction Role to a message not in this guild.")
            await ctx.send(msg)
            return
        async with self.config.guild(ctx.guild).reaction_roles() as cur_setting:
            if isinstance(emoji, discord.Emoji):
                use_emoji = str(emoji.id)
            else:
                use_emoji = str(emoji).strip("\N{VARIATION SELECTOR-16}")
            key = f"{message.channel.id}-{message.id}-{use_emoji}"
            send_to_react = False
            try:
                await message.add_reaction(str(emoji).strip("\N{VARIATION SELECTOR-16}"))
            except discord.HTTPException:
                send_to_react = True
            if ctx.guild.id not in self.settings:
                self.settings[ctx.guild.id] = await self.config.guild(ctx.guild).all()
            self.settings[ctx.guild.id]["reaction_roles"][key] = role.id
            cur_setting[key] = role.id
        async with self.config.role(role).reactions() as reactions:
            reactions.append(key)
        msg = _("Created the reaction role {role} to {emoji} on {message}").format(
            role=role.name, emoji=emoji, message=message.jump_url
        )
        await ctx.send(msg)
        if send_to_react:
            await ctx.channel.send(
                _(
                    "I couldn't add the emoji to the message. Please make "
                    "sure to add the emoji to the message for this to work."
                )
            )
        await self.confirm_selfassignable(ctx, [role])

    @react_coms.command(name="remove", aliases=["rem"], with_app_command=False)
    @commands.admin_or_permissions(manage_roles=True)
    async def remreact(
        self,
        ctx: Context,
        message: discord.Message,
        *,
        role_or_emoji: Union[RoleHierarchyConverter, discord.Emoji, str],
    ) -> None:
        """
        Remove a reaction role

        `<message>` can be the channel_id-message_id pair
        from copying message ID while holding SHIFT or a message link
        `<emoji>` The emoji you want people to react with to get the role.
        `<role>` The role you want people to receive for reacting.

        Note: This will not remove the emoji reactions on the message.
        """
        if not message.guild or message.guild.id != ctx.guild.id:
            msg = _("You cannot remove a Reaction Role from a message not in this guild.")
            await ctx.send(msg)
            return
        if ctx.guild.id not in self.settings:
            msg = _("There are no roletools settings on this server.")
            await ctx.send(msg)
            return
        if not self.settings[ctx.guild.id]["reaction_roles"]:
            msg = _("There are no reaction roles setup for this guild.")
            await ctx.send(msg)
            return
        found = False
        if isinstance(role_or_emoji, discord.Role):
            for keys, role_ids in self.settings[ctx.guild.id]["reaction_roles"].items():
                if role_or_emoji.id == role_ids and f"{message.channel.id}-{message.id}" in keys:
                    key = keys
                    found = True
                    role_id = role_ids
        else:
            final_key = str(getattr(role_or_emoji, "id", role_or_emoji)).strip(
                "\N{VARIATION SELECTOR-16}"
            )
            key = f"{message.channel.id}-{message.id}-{final_key}"
            if key in self.settings[ctx.guild.id]["reaction_roles"]:
                found = True
                role_id = self.settings[ctx.guild.id]["reaction_roles"][key]
        if found:
            channel, message_id, emoji = key.split("-")
            if emoji.isdigit():
                emoji = self.bot.get_emoji(int(emoji))
            async with self.config.guild(ctx.guild).reaction_roles() as cur_setting:
                role = ctx.guild.get_role(cur_setting[key])
                try:
                    del self.settings[ctx.guild.id]["reaction_roles"][key]
                except KeyError:
                    pass
                del cur_setting[key]
                async with self.config.role_from_id(role_id).reactions() as reactions:
                    reactions.remove(key)
            try:
                await message.clear_reaction(emoji)
            except Exception:
                pass

            msg = _("Removed role reaction on {role} to {emoji} on {message}").format(
                role=role, emoji=emoji, message=message.jump_url
            )
            await ctx.send(msg)
        else:
            msg = _(
                "I could not find a reaction role on that message or for that role/emoji combination."
            )
            await ctx.send(msg)

    @react_coms.command(name="bulk", aliases=["bulkcreate", "bulkmake"], with_app_command=False)
    @commands.admin_or_permissions(manage_roles=True)
    async def bulkreact(
        self,
        ctx: Context,
        message: discord.Message,
        *role_emoji: RoleEmojiConverter,
    ) -> None:
        """
        Create multiple roles reactions for a single message

        `<message>` can be the channel_id-message_id pair
        from copying message ID while holding SHIFT or a message link
        `[role_emoji...]` Must be a role-emoji pair separated by either `;`, `,`, `|`, or `-`.

        Note: Any spaces will be considered a new set of role-emoji pairs, if you
        want to specify a role with a space in it without pinging it enclose
        the full role-emoji pair in quotes.

        e.g. `[p]roletools bulkreact 461417772115558410-821105109097644052 @member-:smile:`
        `[p]roletools bulkreact 461417772115558410-821105109097644052 "Super Member-:frown:"`
        """
        if not message.guild or message.guild.id != ctx.guild.id:
            await ctx.send(_("You cannot add a Reaction Role to a message not in this guild."))
            return
        added = []
        not_added = []
        send_to_react = False
        async with self.config.guild(ctx.guild).reaction_roles() as cur_setting:
            for role, emoji in role_emoji:
                log.verbose("bulkreact emoji: %s", type(emoji))
                if isinstance(emoji, discord.PartialEmoji):
                    use_emoji = str(emoji.id)
                else:
                    use_emoji = str(emoji).strip("\N{VARIATION SELECTOR-16}")
                key = f"{message.channel.id}-{message.id}-{use_emoji}"
                if key not in cur_setting:
                    try:
                        await message.add_reaction(
                            str(emoji).strip().strip("\N{VARIATION SELECTOR-16}")
                        )
                    except discord.HTTPException:
                        send_to_react = True
                        log.exception("could not add reaction to message")
                        pass
                    if ctx.guild.id not in self.settings:
                        self.settings[ctx.guild.id] = await self.config.guild(ctx.guild).all()
                    self.settings[ctx.guild.id]["reaction_roles"][key] = role.id
                    cur_setting[key] = role.id
                    added.append((key, role))
                    async with self.config.role(role).reactions() as reactions:
                        reactions.append(key)

                else:
                    not_added.append((key, role))
        ask_to_modify = False
        if added:
            msg = _("__The following Reaction Roles were created__\n")

            if any(
                [
                    m is False
                    for m in [await self.config.role(r).selfassignable() for x, r in added]
                ]
            ):
                ask_to_modify = True
            for item, role in added:
                channel, message_id, emoji = item.split("-")
                if emoji.isdigit():
                    emoji = self.bot.get_emoji(int(emoji))
                msg += _("{role} - {emoji} on {message}\n").format(
                    role=role.name, emoji=emoji, message=message.jump_url
                )
            for page in pagify(msg):
                await ctx.send(page)
            if send_to_react:
                await ctx.send(
                    _(
                        "I couldn't add an emoji to the message. Please make "
                        "sure to add the missing emojis to the message for this to work."
                    )
                )
        if not_added:
            msg = _("__The following Reaction Roles could not be created__\n")
            for item, role in not_added:
                channel, message_id, emoji = item.split("-")
                if emoji.isdigit():
                    emoji = self.bot.get_emoji(int(emoji))
                msg += _("{role} - {emoji} on {message}\n").format(
                    role=role.name, emoji=emoji, message=message.jump_url
                )
            await ctx.send(msg)

        if ask_to_modify:
            await self.confirm_selfassignable(ctx, [r[1] for r in added])
