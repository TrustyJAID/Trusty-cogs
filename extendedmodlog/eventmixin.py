import asyncio
import datetime
from collections import deque
from enum import Enum
from typing import Any, Deque, Dict, List, Optional, Sequence, Tuple, Union, cast

import discord
from discord.ext import tasks
from discord.ext.commands.converter import Converter
from discord.ext.commands.errors import BadArgument
from red_commons.logging import getLogger
from redbot.core import Config, commands, i18n, modlog
from redbot.core.bot import Red
from redbot.core.utils.chat_formatting import (
    box,
    format_perms_list,
    humanize_list,
    humanize_timedelta,
    inline,
    pagify,
)

_ = i18n.Translator("ExtendedModLog", __file__)
logger = getLogger("red.trusty-cogs.ExtendedModLog")


class MemberUpdateEnum(Enum):
    # map config keys to member attributes
    # using an enum just makes it easier to add more items down the road
    nicknames = "nick"
    roles = "roles"
    pending = "pending"
    timeout = "timed_out_until"
    avatar = "guild_avatar"
    flags = "flags"

    @staticmethod
    def names():
        return {
            MemberUpdateEnum.nicknames: _("Nickname"),
            MemberUpdateEnum.roles: _("Roles"),
            MemberUpdateEnum.pending: _("Pending"),
            MemberUpdateEnum.timeout: _("Timeout until"),
            MemberUpdateEnum.avatar: _("Guild Avatar"),
            MemberUpdateEnum.flags: _("Flags"),
        }

    def get_name(self) -> str:
        return self.names().get(self, _("Unknown"))


class CommandPrivs(Converter):
    """
    Converter for command privliges
    """

    async def convert(self, ctx: commands.Context, argument: str) -> str:
        levels = ["MOD", "ADMIN", "BOT_OWNER", "GUILD_OWNER", "NONE"]
        result = None
        if argument.upper() in levels:
            result = argument.upper()
        if argument == "all":
            result = "NONE"
        if not result:
            raise BadArgument(
                _("`{arg}` is not an available command permission.").format(arg=argument)
            )
        return result


class EventChooser(Converter):
    """
    Converter for command privliges
    """

    async def convert(self, ctx: commands.Context, argument: str) -> str:
        options = [
            "message_edit",
            "message_delete",
            "user_change",
            "role_change",
            "role_create",
            "role_delete",
            "voice_change",
            "user_join",
            "user_left",
            "channel_change",
            "channel_create",
            "channel_delete",
            "guild_change",
            "emoji_change",
            "stickers_change",
            "commands_used",
            "invite_created",
            "invite_deleted",
            "thread_create",
            "thread_delete",
            "thread_change",
        ]
        result = None
        if argument.startswith("member_"):
            argument = argument.replace("member_", "user_")
        if argument.lower() in options:
            result = argument.lower()
        if not result:
            raise BadArgument(
                _(
                    "`{arg}` is not an available event option. Please choose from {options}."
                ).format(arg=argument, options=humanize_list([f"`{i}`" for i in options]))
            )
        return result


class EventMixin:
    """
    Handles all the on_event data
    """

    config: Config
    bot: Red
    settings: Dict[int, Any]
    _ban_cache: Dict[int, List[int]]
    allowed_mentions: discord.AllowedMentions
    audit_log: Dict[int, Deque[discord.AuditLogEntry]]

    async def get_event_colour(
        self, guild: discord.Guild, event_type: str, changed_object: Optional[discord.Role] = None
    ) -> discord.Colour:
        if guild.text_channels:
            cmd_colour = await self.bot.get_embed_colour(guild.text_channels[0])
        else:
            cmd_colour = discord.Colour.red()
        defaults = {
            "message_edit": discord.Colour.orange(),
            "message_delete": discord.Colour.dark_red(),
            "user_change": discord.Colour.greyple(),
            "role_change": changed_object.colour if changed_object else discord.Colour.blue(),
            "role_create": discord.Colour.blue(),
            "role_delete": discord.Colour.dark_blue(),
            "voice_change": discord.Colour.magenta(),
            "user_join": discord.Colour.green(),
            "user_left": discord.Colour.dark_green(),
            "channel_change": discord.Colour.teal(),
            "channel_create": discord.Colour.teal(),
            "channel_delete": discord.Colour.dark_teal(),
            "guild_change": discord.Colour.blurple(),
            "emoji_change": discord.Colour.gold(),
            "stickers_change": discord.Colour.gold(),
            "commands_used": cmd_colour,
            "invite_created": discord.Colour.blurple(),
            "invite_deleted": discord.Colour.blurple(),
            "thread_change": discord.Colour.teal(),
            "thread_create": discord.Colour.teal(),
            "thread_delete": discord.Colour.dark_teal(),
        }
        colour = defaults[event_type]
        if self.settings[guild.id][event_type]["colour"] is not None:
            colour = discord.Colour(self.settings[guild.id][event_type]["colour"])
        return colour

    async def is_ignored_channel(
        self, guild: discord.Guild, channel: Union[discord.abc.GuildChannel, discord.Thread, int]
    ) -> bool:
        ignored_channels = self.settings[guild.id]["ignored_channels"]
        if isinstance(channel, int):
            # This is mainly here because you can have threads parent channel
            # deleted which would make the return of `thread.parent` be `None`.
            # The `thread.parent_id` will always be an `int` and we can use that to check if
            # we should be ignoring the event
            return channel in ignored_channels
        if channel.id in ignored_channels:
            return True
        if channel.category and channel.category.id in ignored_channels:
            return True
        if (
            isinstance(channel, discord.Thread)
            and channel.parent
            and channel.parent.id in ignored_channels
        ):
            return True
        return False

    async def modlog_channel(self, guild: discord.Guild, event: str) -> discord.TextChannel:
        channel = None
        settings = self.settings[guild.id].get(event)
        if "channel" in settings and settings["channel"]:
            channel = guild.get_channel(settings["channel"])
        if channel is None:
            try:
                channel = await modlog.get_modlog_channel(guild)
            except RuntimeError:
                raise RuntimeError("No Modlog set")
        if not channel.permissions_for(guild.me).send_messages:
            raise RuntimeError("No permission to send messages in channel")
        return channel

    @commands.Cog.listener()
    async def on_command(self, ctx: commands.Context) -> None:
        guild = ctx.guild
        if guild is None:
            return
        if guild.id not in self.settings:
            return
        if await self.bot.cog_disabled_in_guild(self, ctx.guild):
            return
        if not self.settings[guild.id]["commands_used"]["enabled"]:
            return
        if await self.is_ignored_channel(guild, ctx.channel):
            return
        if guild.me.is_timed_out():
            return
        try:
            channel = await self.modlog_channel(guild, "commands_used")
        except RuntimeError:
            return
        embed_links = (
            channel.permissions_for(guild.me).embed_links
            and self.settings[guild.id]["commands_used"]["embed"]
        )
        await i18n.set_contextual_locales_from_guild(self.bot, guild)
        # set guild level i18n

        time = ctx.message.created_at
        message = ctx.message
        can_run = await ctx.command.can_run(ctx, check_all_parents=True)
        can_see = await ctx.command.can_see(ctx)
        can_x = _("**See:** {can_see}\n**Run:** {can_run}").format(
            can_run=can_run, can_see=can_see
        )
        logger.verbose("on_command name: %s", ctx.command.qualified_name)
        if ctx.interaction:
            data = ctx.interaction.data
            com_id = data.get("id")
            root_command = data.get("name")
            sub_commands = ""
            arguments = ""
            for option in data.get("options", []):
                if option["type"] in (1, 2):
                    sub_commands += " " + option["name"]
                else:
                    option_name = option["name"]
                    option_value = option.get("value")
                    arguments += f"{option_name}: {option_value}"
                for sub_option in option.get("options", []):
                    if sub_option["type"] in (1, 2):
                        sub_commands += " " + sub_option["name"]
                    else:
                        sub_option_name = sub_option.get("name")
                        sub_option_value = sub_option.get("value")
                        arguments += f"{sub_option_name}: {sub_option_value}"
                    for arg in sub_option.get("options", []):
                        arg_option_name = arg.get("name")
                        arg_option_value = arg.get("value")
                        arguments += f"{arg_option_name}: {arg_option_value} "
            command_name = f"{root_command}{sub_commands}"
            com_str = f"</{command_name}:{com_id}> {arguments}"
        else:
            com_str = ctx.message.content
        try:
            com = ctx.command
            privs = com.requires.privilege_level
            user_perms = com.requires.user_perms or discord.Permissions.none()
            # If a subcommand requires only an exclusive privilege level check but its
            # parent checks either privilege level or permissions extendedmodlog could fail
            # to detect a commands required permissions and not log the usage.
            # This is fixed by setting the permission value to a default of None
            # then oring the values together to get the total requirements on the command.
            # This appears more prominently with owner only subcommands with a top level
            # command with permission requirements.
            my_perms = com.requires.bot_perms
            for p in com.parents:
                if p.requires.privilege_level is not None:
                    if (
                        privs is commands.PrivilegeLevel.NONE
                        and p.requires.privilege_level > privs
                    ):
                        # work our way up to the *first* priv level in the chain
                        # This should ideally be the most relevant one
                        privs = p.requires.privilege_level
                if p.requires.user_perms:
                    user_perms |= p.requires.user_perms
                if p.requires.bot_perms:
                    my_perms |= p.requires.bot_perms

        except Exception:
            logger.exception(
                "Something went wrong figuring out user and bot privileges on a command."
            )
            return
        if privs is None:
            privs = commands.PrivilegeLevel.NONE
            # apparently requires.privilege_level can be None
            # for me I will just consider it as PrivilegeLevel.NONE
        if privs.name not in self.settings[guild.id]["commands_used"]["privs"]:
            logger.debug("command not in list %s", privs.name)
            return

        if privs is commands.PrivilegeLevel.MOD:
            mod_role_list = await ctx.bot.get_mod_roles(guild)
            if mod_role_list != []:
                role = humanize_list([r.mention for r in mod_role_list]) + f"\n{privs.name}\n"
            else:
                role = _("Not Set\nMOD\n")
        elif privs is commands.PrivilegeLevel.ADMIN:
            admin_role_list = await ctx.bot.get_admin_roles(guild)
            if admin_role_list != []:
                role = humanize_list([r.mention for r in admin_role_list]) + f"\n{privs.name}\n"
            else:
                role = _("Not Set\nADMIN\n")
        elif privs is commands.PrivilegeLevel.BOT_OWNER:
            role = humanize_list([f"<@{_id}>" for _id in ctx.bot.owner_ids or []])
            role += f"\n{privs.name}\n"
        elif privs is commands.PrivilegeLevel.GUILD_OWNER:
            if guild.owner:
                role = guild.owner.mention + f"\n{privs.name}\n"
            else:
                role = _("Unknown Server Owner") + f"\n{privs.name}\n"
        else:
            role = f"everyone\n{privs.name}\n"
        if user_perms:
            role += format_perms_list(user_perms)
        i_require = None
        if my_perms:
            i_require = format_perms_list(my_perms)

        if embed_links:
            embed = discord.Embed(
                description=f">>> {com_str}",
                colour=await self.get_event_colour(guild, "commands_used"),
                timestamp=time,
            )
            embed.add_field(name=_("Channel"), value=message.channel.mention)
            embed.add_field(name=_("Author"), value=message.author.mention)
            embed.add_field(name=_("Can"), value=str(can_x))
            embed.add_field(name=_("Requires"), value=role)
            if i_require:
                embed.add_field(name=_("Bot Requires"), value=i_require)
            author_title = _("{member} ({m_id}) Used a Command").format(
                member=message.author, m_id=message.author.id
            )
            embed.set_author(name=author_title, icon_url=message.author.display_avatar)
            embed.add_field(name=_("Member ID"), value=box(str(message.author.id)))
            await channel.send(embed=embed, allowed_mentions=self.allowed_mentions)
        else:
            infomessage = _(
                "{emoji} {time} {author}(`{a_id}`) used the following command in {channel}\n> {com}"
            ).format(
                emoji=self.settings[guild.id]["commands_used"]["emoji"],
                time=message.created_at.strftime("%H:%M:%S"),
                author=message.author,
                a_id=message.author.id,
                channel=message.channel.mention,
                com=com_str,
            )
            await channel.send(infomessage[:2000], allowed_mentions=self.allowed_mentions)

    @commands.Cog.listener(name="on_raw_message_delete")
    async def on_raw_message_delete_listener(
        self, payload: discord.RawMessageDeleteEvent, *, check_audit_log: bool = True
    ) -> None:
        # custom name of method used, because this is only supported in Red 3.1+
        guild_id = payload.guild_id
        if guild_id is None:
            return
        guild = self.bot.get_guild(guild_id)
        if guild is None:
            return
        if guild.id not in self.settings:
            return
        if await self.bot.cog_disabled_in_guild(self, guild):
            return
        if guild.me.is_timed_out():
            return
        settings = self.settings[guild.id]["message_delete"]
        if not settings["enabled"]:
            return
        channel_id = payload.channel_id
        try:
            channel = await self.modlog_channel(guild, "message_delete")
        except RuntimeError:
            return
        message_channel = guild.get_channel_or_thread(channel_id)
        if message_channel is None:
            return
        if await self.is_ignored_channel(guild, message_channel):
            return
        embed_links = (
            channel.permissions_for(guild.me).embed_links
            and self.settings[guild.id]["message_delete"]["embed"]
        )
        await i18n.set_contextual_locales_from_guild(self.bot, guild)
        # set guild level i18n
        message = payload.cached_message
        if message is None:
            if settings["cached_only"]:
                return
            if embed_links:
                embed = discord.Embed(
                    description=_("*Message's content unknown.*"),
                    colour=await self.get_event_colour(guild, "message_delete"),
                )
                embed.add_field(name=_("Channel"), value=message_channel.mention)
                embed.set_author(name=_("Deleted Message"))
                embed.add_field(name=_("Message ID"), value=box(str(payload.message_id)))
                await channel.send(embed=embed, allowed_mentions=self.allowed_mentions)
            else:
                infomessage = _(
                    "{emoji} {time} A message ({message_id}) was deleted in {channel}"
                ).format(
                    emoji=settings["emoji"],
                    time=datetime.datetime.now(datetime.timezone.utc).strftime("%H:%M:%S"),
                    message_id=box(str(payload.message_id)),
                    channel=message_channel.mention,
                )
                await channel.send(
                    f"{infomessage}\n> *Message's content unknown.*",
                    allowed_mentions=self.allowed_mentions,
                )
            return
        await self._cached_message_delete(
            message, guild, settings, channel, check_audit_log=check_audit_log
        )

    async def _cached_message_delete(
        self,
        message: discord.Message,
        guild: discord.Guild,
        settings: dict,
        channel: discord.TextChannel,
        *,
        check_audit_log: bool = True,
    ) -> None:
        if message.author.bot and not settings["bots"]:
            # return to ignore bot accounts if enabled
            return
        if message.content == "" and message.attachments == []:
            return
        embed_links = (
            channel.permissions_for(guild.me).embed_links
            and self.settings[guild.id]["message_delete"]["embed"]
        )
        ctx = await self.bot.get_context(message)
        logger.trace("_cached_message_delete ctx.valid: %s", ctx.valid)
        if ctx.valid and self.settings[guild.id]["message_delete"]["ignore_commands"]:
            logger.debug("Ignoring valid command messages.")
            return
        time = message.created_at
        perp = None
        reason = None
        if channel.permissions_for(guild.me).view_audit_log and check_audit_log:
            action = discord.AuditLogAction.message_delete
            entry = await self.get_audit_log_entry(guild, message.author, action)
            perp = getattr(entry, "user", None)
            reason = getattr(entry, "reason", None)

        replying = ""
        if message.reference and message.reference.resolved:
            if isinstance(message.reference.resolved, discord.Message):
                ref_author = message.reference.resolved.author
                ref_jump = message.reference.resolved.jump_url
                replying = f"[{ref_author}]({ref_jump})"
            else:
                ref_guild = message.reference.resolved.guild_id
                ref_chan = message.reference.resolved.channel_id
                ref_msg = message.reference.resolved.id
                replying = f"https://discord.com/channels/{ref_guild}/{ref_chan}/{ref_msg}"
        message_channel = cast(discord.TextChannel, message.channel)
        author = message.author
        if perp is None:
            infomessage = _(
                "{emoji} {time} A message from **{author}** (`{a_id}`) was deleted in {channel}"
            ).format(
                emoji=settings["emoji"],
                time=discord.utils.format_dt(time),
                author=author,
                channel=message_channel.mention,
                a_id=author.id,
            )
        else:
            infomessage = _(
                "{emoji} {time} {perp} deleted a message from "
                "**{author}** (`{a_id}`) in {channel}"
            ).format(
                emoji=settings["emoji"],
                time=discord.utils.format_dt(time),
                perp=perp,
                author=author,
                a_id=author.id,
                channel=message_channel.mention,
            )
        if embed_links:
            content = f">>> {message.content}" if message.content else None
            embed = discord.Embed(
                description=content,
                colour=await self.get_event_colour(guild, "message_delete"),
                timestamp=time,
            )

            embed.add_field(name=_("Channel"), value=message_channel.mention)
            embed.add_field(name=_("Author"), value=message.author.mention)
            if perp:
                embed.add_field(name=_("Deleted by"), value=perp.mention)
            if reason:
                embed.add_field(name=_("Reason"), value=reason)
            if message.attachments:
                files = "\n".join(f"- {inline(a.filename)}" for a in message.attachments)
                embed.add_field(name=_("Attachments"), value=files[:1024])
            if replying:
                embed.add_field(name=_("Replying to:"), value=replying)

            embed.add_field(name=_("Message ID"), value=box(str(message.id)))
            embed.set_author(
                name=_("{member} ({m_id}) - Deleted Message").format(
                    member=author, m_id=author.id
                ),
                icon_url=message.author.display_avatar,
            )
            await channel.send(embed=embed, allowed_mentions=self.allowed_mentions)
        else:
            clean_msg = message.clean_content[: (1990 - len(infomessage))]
            await channel.send(
                f"{infomessage}\n>>> {clean_msg}", allowed_mentions=self.allowed_mentions
            )

    @commands.Cog.listener()
    async def on_raw_bulk_message_delete(self, payload: discord.RawBulkMessageDeleteEvent):
        guild_id = payload.guild_id
        if guild_id is None:
            return
        guild = self.bot.get_guild(guild_id)
        if guild is None:
            return
        if guild.id not in self.settings:
            return
        if await self.bot.cog_disabled_in_guild(self, guild):
            return
        if guild.me.is_timed_out():
            return
        settings = self.settings[guild.id]["message_delete"]
        if not settings["enabled"] or not settings["bulk_enabled"]:
            return
        channel_id = payload.channel_id
        message_channel = guild.get_channel_or_thread(channel_id)
        if message_channel is None:
            return
        try:
            channel = await self.modlog_channel(guild, "message_delete")
        except RuntimeError:
            return
        if await self.is_ignored_channel(guild, message_channel):
            return
        embed_links = (
            channel.permissions_for(guild.me).embed_links
            and self.settings[guild.id]["message_delete"]["embed"]
        )
        await i18n.set_contextual_locales_from_guild(self.bot, guild)
        # set guild level i18n
        message_amount = len(payload.message_ids)
        if embed_links:
            embed = discord.Embed(
                description=message_channel.mention,
                colour=await self.get_event_colour(guild, "message_delete"),
            )
            embed.set_author(
                name=_("Bulk message delete"),
                icon_url=guild.icon,
            )
            embed.add_field(name=_("Channel"), value=message_channel.mention)
            embed.add_field(name=_("Messages deleted"), value=str(message_amount))
            await channel.send(embed=embed, allowed_mentions=self.allowed_mentions)
        else:
            infomessage = _(
                "{emoji} {time} Bulk message delete in {channel}, {amount} messages deleted."
            ).format(
                emoji=settings["emoji"],
                time=datetime.datetime.now(datetime.timezone.utc).strftime("%H:%M:%S"),
                amount=message_amount,
                channel=message_channel.mention,
            )
            await channel.send(infomessage, allowed_mentions=self.allowed_mentions)
        if settings["bulk_individual"]:
            for message in payload.cached_messages:
                new_payload = discord.RawMessageDeleteEvent(
                    {"id": message.id, "channel_id": channel_id, "guild_id": guild_id}
                )
                new_payload.cached_message = message
                try:
                    await self.on_raw_message_delete_listener(new_payload, check_audit_log=False)
                except Exception:
                    pass

    @tasks.loop(seconds=300)
    async def invite_links_loop(self) -> None:
        """Check every 5 minutes for updates to the invite links"""
        for guild_id in self.settings.keys():
            guild = self.bot.get_guild(guild_id)
            if guild is None:
                continue
            if self.settings[guild_id]["user_join"]["enabled"]:
                await self.save_invite_links(guild)

    @invite_links_loop.before_loop
    async def before_invite_loop(self):
        await self.bot.wait_until_red_ready()

    async def save_invite_links(self, guild: discord.Guild) -> bool:
        invites = {}
        if not guild.me.guild_permissions.manage_guild:
            return False
        try:
            for invite in await guild.invites():
                created_at = getattr(
                    invite, "created_at", datetime.datetime.now(datetime.timezone.utc)
                )
                channel = getattr(invite, "channel", discord.Object(id=0))
                inviter = getattr(invite, "inviter", discord.Object(id=0))
                invites[invite.code] = {
                    "uses": getattr(invite, "uses", 0),
                    "max_age": getattr(invite, "max_age", None),
                    "created_at": created_at.timestamp(),
                    "max_uses": getattr(invite, "max_uses", None),
                    "temporary": getattr(invite, "temporary", False),
                    "inviter": getattr(inviter, "id", "Unknown"),
                    "channel": getattr(channel, "id", "Unknown"),
                }
        except discord.HTTPException:
            logger.error("Error saving invites for guild %s. Discord Server Error.", guild.id)
            return False
        except Exception:
            logger.exception("Error saving invites for guild %s.", guild.id)
            return False

        self.settings[guild.id]["invite_links"] = invites
        await self.save(guild)
        return True

    async def get_invite_link(self, member: discord.Member) -> str:
        guild = member.guild
        manage_guild = guild.me.guild_permissions.manage_guild
        invites = self.settings[guild.id]["invite_links"]
        possible_link = ""
        check_logs = manage_guild and guild.me.guild_permissions.view_audit_log
        if member.bot:
            if check_logs:
                action = discord.AuditLogAction.bot_add
                entry = await self.get_audit_log_entry(guild, member, action)
                if entry:
                    possible_link = _("Added by: {inviter}").format(inviter=str(entry.user))
            return possible_link
        if manage_guild and "VANITY_URL" in guild.features:
            try:
                possible_link = str(await guild.vanity_invite())
            except (discord.errors.NotFound, discord.errors.HTTPException):
                pass

        if invites and manage_guild:
            guild_invites = await guild.invites()
            for invite in guild_invites:
                if invite.code in invites:
                    uses = invites[invite.code]["uses"]
                    # we can't get accurate information if the uses is None
                    if invite.uses is None or uses is None:
                        continue
                    if invite.uses > uses:
                        possible_link = _(
                            "https://discord.gg/{code}\nInvited by: {inviter}"
                        ).format(
                            code=invite.code,
                            inviter=str(
                                getattr(invite.inviter, "mention", _("Widget Integration"))
                            ),
                        )

            if not possible_link:
                for code, data in invites.items():
                    try:
                        invite = await self.bot.fetch_invite(code)
                    except Exception:
                        logger.error("Error getting invite {code}".format(code=code))
                        invite = None
                        pass
                    if invite is None:
                        if (data["max_uses"] - data["uses"]) == 1:
                            # The invite link was on its last uses and subsequently
                            # deleted so we're fairly sure this was the one used
                            try:
                                inviter = guild.get_member(data["inviter"])
                                if inviter is None:
                                    inviter = await self.bot.fetch_user(data["inviter"])
                                if inviter is not None:
                                    inviter = inviter.mention
                            except (discord.errors.NotFound, discord.errors.Forbidden):
                                inviter = _("Unknown or deleted user ({inviter})").format(
                                    inviter=data["inviter"]
                                )
                            possible_link = _(
                                "https://discord.gg/{code}\nInvited by: {inviter}"
                            ).format(code=code, inviter=str(inviter))
            await self.save_invite_links(guild)  # Save all the invites again since they've changed
        if check_logs and not possible_link:
            action = discord.AuditLogAction.invite_create
            entry = await self.get_audit_log_entry(guild, None, action)
            if entry:
                possible_link = _("https://discord.gg/{code}\nInvited by: {inviter}").format(
                    code=entry.target.code,
                    inviter=getattr(entry.target.inviter, "mention", _("Unknown")),
                )
        return possible_link

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        guild = member.guild
        if guild.id not in self.settings:
            return
        if not self.settings[guild.id]["user_join"]["enabled"]:
            return
        if await self.bot.cog_disabled_in_guild(self, guild):
            return
        if guild.me.is_timed_out():
            return
        try:
            channel = await self.modlog_channel(guild, "user_join")
        except RuntimeError:
            return
        embed_links = (
            channel.permissions_for(guild.me).embed_links
            and self.settings[guild.id]["user_join"]["embed"]
        )
        await i18n.set_contextual_locales_from_guild(self.bot, guild)
        # set guild level i18n
        time = datetime.datetime.now(datetime.timezone.utc)
        users = len(guild.members)
        # https://github.com/Cog-Creators/Red-DiscordBot/blob/develop/cogs/general.py
        user_created = int(member.created_at.timestamp())

        created_on = "<t:{user_created}>\n(<t:{user_created}:R>)".format(user_created=user_created)

        possible_link = await self.get_invite_link(member)
        if embed_links:
            embed = discord.Embed(
                description=member,
                colour=await self.get_event_colour(guild, "user_join"),
                timestamp=member.joined_at
                if member.joined_at
                else datetime.datetime.now(datetime.timezone.utc),
            )
            embed.add_field(name=_("Member"), value=member.mention)
            embed.add_field(name=_("Member ID"), value=box(str(member.id)))
            embed.add_field(name=_("Total Users:"), value=str(users))
            embed.add_field(name=_("Account created on:"), value=created_on)
            embed.set_author(
                name=_("{member} ({m_id}) has joined the guild").format(
                    member=member, m_id=member.id
                ),
                url=member.display_avatar,
                icon_url=member.display_avatar,
            )
            if possible_link:
                embed.add_field(name=_("Invite Link"), value=possible_link)
            embed.set_thumbnail(url=member.display_avatar)
            await channel.send(embed=embed, allowed_mentions=self.allowed_mentions)
        else:
            time = datetime.datetime.now(datetime.timezone.utc)
            msg = _(
                "{emoji} {time} **{member}**(`{m_id}`) " "joined the guild. Total members: {users}"
            ).format(
                emoji=self.settings[guild.id]["user_join"]["emoji"],
                time=discord.utils.format_dt(time),
                member=member,
                m_id=member.id,
                users=users,
            )
            await channel.send(msg, allowed_mentions=self.allowed_mentions)

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, member: discord.Member):
        """
        This is only used to track that the user was banned and not kicked/removed
        """
        if guild.id not in self._ban_cache:
            self._ban_cache[guild.id] = [member.id]
        else:
            self._ban_cache[guild.id].append(member.id)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        guild = member.guild
        await asyncio.sleep(5)
        if guild.id in self._ban_cache and member.id in self._ban_cache[guild.id]:
            # was a ban so we can leave early
            return
        if guild.id not in self.settings:
            return
        if not self.settings[guild.id]["user_left"]["enabled"]:
            return
        if await self.bot.cog_disabled_in_guild(self, guild):
            return
        if guild.me.is_timed_out():
            return
        try:
            channel = await self.modlog_channel(guild, "user_left")
        except RuntimeError:
            return
        embed_links = (
            channel.permissions_for(guild.me).embed_links
            and self.settings[guild.id]["user_left"]["embed"]
        )
        await i18n.set_contextual_locales_from_guild(self.bot, guild)
        # set guild level i18n
        time = datetime.datetime.now(datetime.timezone.utc)
        entry = await self.get_audit_log_entry(guild, member, discord.AuditLogAction.kick)
        joined = member.joined_at
        member_time = None
        if joined is not None:
            m_date = discord.utils.format_dt(joined, "D")
            m_rel = discord.utils.format_dt(joined, "R")
            member_time = f"{m_date} ({m_rel})"

        perp = getattr(entry, "user", None)
        reason = getattr(entry, "reason", None)
        if embed_links:
            embed = discord.Embed(
                description=member,
                colour=await self.get_event_colour(guild, "user_left"),
                timestamp=time,
            )
            embed.add_field(name=_("Member"), value=member.mention)
            embed.add_field(name=_("Member ID"), value=box(str(member.id)))
            embed.add_field(name=_("Total Users:"), value=str(len(guild.members)))
            if member_time is not None:
                embed.add_field(name=_("Member since:"), value=member_time)

            if perp:
                embed.add_field(name=_("Kicked"), value=perp.mention)
            if reason:
                embed.add_field(name=_("Reason"), value=str(reason), inline=False)
            embed.set_author(
                name=_("{member} ({m_id}) has left the guild").format(
                    member=member, m_id=member.id
                ),
                url=member.display_avatar,
                icon_url=member.display_avatar,
            )
            embed.set_thumbnail(url=member.display_avatar)
            await channel.send(embed=embed, allowed_mentions=self.allowed_mentions)
        else:
            time = datetime.datetime.now(datetime.timezone.utc)
            msg = _(
                "{emoji} {time} **{member}**(`{m_id}`) left the guild. Total members: {users}"
            ).format(
                emoji=self.settings[guild.id]["user_left"]["emoji"],
                time=discord.utils.format_dt(time),
                member=member,
                m_id=member.id,
                users=len(guild.members),
            )
            if perp:
                msg = _(
                    "{emoji} {time} **{member}**(`{m_id}`) "
                    "was kicked by {perp}. Total members: {users}"
                ).format(
                    emoji=self.settings[guild.id]["user_left"]["emoji"],
                    time=discord.utils.format_dt(time),
                    member=member,
                    m_id=member.id,
                    perp=perp,
                    users=len(guild.members),
                )
            await channel.send(msg, allowed_mentions=self.allowed_mentions)

    async def get_permission_change(
        self, before: discord.abc.GuildChannel, after: discord.abc.GuildChannel, embed_links: bool
    ) -> str:
        p_msg = ""
        before_perms = {}
        after_perms = {}
        guild = before.guild
        for o, p in before.overwrites.items():
            before_perms[str(o.id)] = [i for i in p]
        for o, p in after.overwrites.items():
            after_perms[str(o.id)] = [i for i in p]
        for entity in before_perms:
            entity_obj = before.guild.get_role(int(entity))
            if not entity_obj:
                entity_obj = before.guild.get_member(int(entity))
            if entity_obj is not None:
                name = entity_obj.mention
            else:
                name = entity
            if entity not in after_perms:
                entry = await self.get_audit_log_entry(
                    guild, before, discord.AuditLogAction.overwrite_delete
                )
                perp = getattr(entry, "user", None)
                reason = getattr(entry, "reason", None)
                if perp:
                    p_msg += _("{name} Removed overwrites:\n").format(name=perp.mention)
                p_msg += _("{name} Overwrites removed:\n").format(name=name)

                lost_perms = set(before_perms[entity])
                for diff in lost_perms:
                    if diff[1] is None:
                        continue
                    p_msg += _("{name} {perm} Reset.\n").format(name=name, perm=diff[0])
                continue
            if after_perms[entity] != before_perms[entity]:
                entry = await self.get_audit_log_entry(
                    guild, before, discord.AuditLogAction.overwrite_update
                )
                perp = getattr(entry, "user", None)
                reason = getattr(entry, "reason", None)

                if perp:
                    p_msg += _("{name} Updated overwrites:\n").format(name=perp.mention)
                a = set(after_perms[entity])
                b = set(before_perms[entity])
                a_perms = list(a - b)
                for diff in a_perms:
                    p_msg += _("- {name} {perm} Set to {value}.\n").format(
                        name=name, perm=diff[0].replace("_", " ").title(), value=diff[1]
                    )
        for entity in after_perms:
            entity_obj = after.guild.get_role(int(entity))
            if not entity_obj:
                entity_obj = after.guild.get_member(int(entity))
            if entity_obj is not None:
                name = entity_obj.mention
            else:
                name = entity
            if entity not in before_perms:
                entry = await self.get_audit_log_entry(
                    guild, before, discord.AuditLogAction.overwrite_update
                )
                perp = getattr(entry, "user", None)
                reason = getattr(entry, "reason", None)
                if perp:
                    p_msg += _("{name} Added overwrites:\n").format(name=perp.mention)
                p_msg += _("{name} Overwrites added.\n").format(name=name)
                lost_perms = set(after_perms[entity])
                for diff in lost_perms:
                    if diff[1] is None:
                        continue
                    p_msg += _("- {name} {perm} Set to {value}.\n").format(
                        name=name, perm=diff[0].replace("_", " ").title(), value=diff[1]
                    )
                continue
        return p_msg

    @commands.Cog.listener()
    async def on_guild_channel_create(self, new_channel: discord.abc.GuildChannel) -> None:
        guild = new_channel.guild
        if guild.id not in self.settings:
            return
        if not self.settings[guild.id]["channel_create"]["enabled"]:
            return
        if await self.bot.cog_disabled_in_guild(self, guild):
            return
        if guild.me.is_timed_out():
            return
        if await self.is_ignored_channel(guild, new_channel):
            return
        try:
            channel = await self.modlog_channel(guild, "channel_create")
        except RuntimeError:
            return
        embed_links = (
            channel.permissions_for(guild.me).embed_links
            and self.settings[guild.id]["channel_create"]["embed"]
        )
        await i18n.set_contextual_locales_from_guild(self.bot, guild)
        # set guild level i18n
        time = datetime.datetime.now(datetime.timezone.utc)
        channel_type = str(new_channel.type).replace("_", " ").title()
        embed = discord.Embed(
            description=new_channel.name,
            timestamp=time,
            colour=await self.get_event_colour(guild, "channel_create"),
        )
        embed.set_author(
            name=_("{chan_type} Channel Created ({chan_id})").format(
                chan_type=channel_type, chan_id=new_channel.id
            )
        )
        # msg = _("Channel Created ") + str(new_channel.id) + "\n"
        entry = await self.get_audit_log_entry(
            guild, new_channel, discord.AuditLogAction.channel_create
        )
        perp = getattr(entry, "user", None)
        reason = getattr(entry, "reason", None)

        perp_msg = ""
        embed.add_field(name=_("Channel"), value=new_channel.mention)
        embed.add_field(name=_("Type"), value=channel_type)
        if perp:
            perp_msg = _("by {perp} (`{perp_id}`)").format(perp=perp, perp_id=perp.id)
            embed.add_field(name=_("Created by "), value=perp.mention)
        if reason:
            perp_msg += _(" Reason: {reason}").format(reason=reason)
            embed.add_field(name=_("Reason "), value=reason, inline=False)
        embed.add_field(name=_("Channel ID"), value=box(str(new_channel.id)))
        msg = _("{emoji} {time} {chan_type} channel created {perp_msg} {channel}").format(
            emoji=self.settings[guild.id]["channel_create"]["emoji"],
            time=discord.utils.format_dt(time),
            chan_type=channel_type,
            perp_msg=perp_msg,
            channel=new_channel.mention,
        )
        if embed_links:
            await channel.send(embed=embed, allowed_mentions=self.allowed_mentions)
        else:
            await channel.send(msg, allowed_mentions=self.allowed_mentions)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, old_channel: discord.abc.GuildChannel):
        guild = old_channel.guild
        if guild.id not in self.settings:
            return
        if not self.settings[guild.id]["channel_delete"]["enabled"]:
            return
        if await self.bot.cog_disabled_in_guild(self, guild):
            return
        if guild.me.is_timed_out():
            return
        if await self.is_ignored_channel(guild, old_channel):
            return
        try:
            channel = await self.modlog_channel(guild, "channel_delete")
        except RuntimeError:
            return
        embed_links = (
            channel.permissions_for(guild.me).embed_links
            and self.settings[guild.id]["channel_delete"]["embed"]
        )
        await i18n.set_contextual_locales_from_guild(self.bot, guild)
        # set guild level i18n
        channel_type = str(old_channel.type).replace("_", " ").title()
        time = datetime.datetime.now(datetime.timezone.utc)
        embed = discord.Embed(
            description=old_channel.name,
            timestamp=time,
            colour=await self.get_event_colour(guild, "channel_delete"),
        )
        embed.set_author(
            name=_("{chan_type} Channel Deleted ({chan_id})").format(
                chan_type=channel_type, chan_id=old_channel.id
            )
        )
        entry = await self.get_audit_log_entry(
            guild, old_channel, discord.AuditLogAction.channel_delete
        )
        perp = getattr(entry, "user", None)
        reason = getattr(entry, "reason", None)

        perp_msg = ""
        embed.add_field(name=_("Channel"), value=old_channel.mention)
        embed.add_field(name=_("Type"), value=channel_type)

        if perp:
            perp_msg = _("by {perp} (`{perp_id}`)").format(perp=perp, perp_id=perp.id)
            embed.add_field(name=_("Deleted by "), value=perp.mention)
        if reason:
            perp_msg += _(" Reason: {reason}").format(reason=reason)
            embed.add_field(name=_("Reason "), value=reason, inline=False)
        embed.add_field(name=_("Channel ID"), value=box(str(old_channel.id)))
        msg = _("{emoji} {time} {chan_type} channel deleted {perp_msg} {channel}").format(
            emoji=self.settings[guild.id]["channel_delete"]["emoji"],
            time=discord.utils.format_dt(time),
            chan_type=channel_type,
            perp_msg=perp_msg,
            channel=f"#{old_channel.name} ({old_channel.id})",
        )
        if embed_links:
            await channel.send(embed=embed, allowed_mentions=self.allowed_mentions)
        else:
            await channel.send(msg, allowed_mentions=self.allowed_mentions)

    @commands.Cog.listener()
    async def on_audit_log_entry_create(self, entry: discord.AuditLogEntry):
        if entry.guild.id not in self.audit_log:
            self.audit_log[entry.guild.id] = deque(maxlen=10)
        self.audit_log[entry.guild.id].append(entry)

    async def get_audit_log_entry(
        self,
        guild: discord.Guild,
        target: Union[
            discord.abc.GuildChannel,
            discord.Member,
            discord.User,
            discord.Role,
            discord.Invite,
            int,
            None,
        ],
        action: discord.AuditLogAction,
        *,
        extra: Optional[str] = None,
    ) -> Optional[discord.AuditLogEntry]:
        entry = None
        if isinstance(target, int) or target is None:
            target_id = target
        elif isinstance(target, discord.Invite):
            target_id = target.code
        else:
            target_id = target.id

        if guild.me.guild_permissions.view_audit_log:
            await asyncio.sleep(5)
            # wait 5 seconds incase the audit log entry is slow and we prioritize the cache
            if guild.id in self.audit_log:
                for log in self.audit_log[guild.id]:
                    if log.action != action:
                        continue
                    if extra is not None:
                        if getattr(log.after, extra, None) is None:
                            continue
                    if target_id == getattr(log.target, "id", None):
                        logger.trace("Found entry through cache")
                        entry = log
                    if target_id == getattr(log.target, "code", None):
                        logger.trace("Found invite code entry through cache")
                        entry = log

            if entry is None:
                async for log in guild.audit_logs(limit=5, action=action):
                    if extra is not None:
                        if getattr(log.after, extra, None) is None:
                            continue
                    if target_id == getattr(log.target, "id", None):
                        logger.trace("Found perp through fetch")
                        entry = log
                        break
                    if target_id == getattr(log.target, "code", None):
                        logger.trace("Found invite code entry through fetch")
                        entry = log
        return entry

    @commands.Cog.listener()
    async def on_guild_channel_update(
        self, before: discord.abc.GuildChannel, after: discord.abc.GuildChannel
    ) -> None:
        guild = before.guild
        if guild.id not in self.settings:
            return
        if await self.bot.cog_disabled_in_guild(self, guild):
            return
        if guild.me.is_timed_out():
            return
        if not self.settings[guild.id]["channel_change"]["enabled"]:
            return
        if await self.is_ignored_channel(guild, before):
            return
        try:
            channel = await self.modlog_channel(guild, "channel_change")
        except RuntimeError:
            return
        embed_links = (
            channel.permissions_for(guild.me).embed_links
            and self.settings[guild.id]["channel_change"]["embed"]
        )
        await i18n.set_contextual_locales_from_guild(self.bot, guild)
        # set guild level i18n
        channel_type = str(after.type).replace("_", " ").title()
        time = datetime.datetime.now(datetime.timezone.utc)
        embed = discord.Embed(
            description=after.mention,
            timestamp=time,
            colour=await self.get_event_colour(guild, "channel_change"),
        )
        embed.set_author(
            name=_("{chan_type} Channel Updated {chan_name} ({chan_id})").format(
                chan_type=channel_type, chan_name=before.name, chan_id=before.id
            )
        )
        msg = _("{emoji} {time} Updated channel {channel}\n").format(
            emoji=self.settings[guild.id]["channel_change"]["emoji"],
            time=discord.utils.format_dt(time),
            channel=before.name,
        )
        worth_updating = False
        perp = None
        reason = None
        channel_updates = {
            "name": _("Name:"),
            "topic": _("Topic:"),
            "category": _("Category:"),
            "slowmode_delay": _("Slowmode delay:"),
            "bitrate": _("Bitrate:"),
            "user_limit": _("User limit:"),
        }
        before_text = ""
        after_text = ""
        for attr, name in channel_updates.items():
            before_attr = getattr(before, attr, None)
            after_attr = getattr(after, attr, None)
            if before_attr != after_attr:
                worth_updating = True
                if before_attr == "":
                    before_attr = "None"
                if after_attr == "":
                    after_attr = "None"
                msg += _("Before ") + f"{name} {before_attr}\n"
                msg += _("After ") + f"{name} {after_attr}\n"
                before_text += f"- {name} {before_attr}\n"
                after_text += f"- {name} {after_attr}\n"
                # embed.add_field(name=_("Before ") + name, value=str(before_attr)[:1024])
                # embed.add_field(name=_("After ") + name, value=str(after_attr)[:1024])
                entry = await self.get_audit_log_entry(
                    guild, before, discord.AuditLogAction.channel_update
                )
                perp = getattr(entry, "user", None)
                reason = getattr(entry, "reason", None)

        if before.is_nsfw() != after.is_nsfw():  # type: ignore
            worth_updating = True
            msg += _("Before ") + f"NSFW {before.is_nsfw()}\n"
            msg += _("After ") + f"NSFW {after.is_nsfw()}\n"
            before_text += _("- Age Restricted: {value}").format(value=before.is_nsfw())
            after_text += _("- Age Restricted: {value}").format(value=after.is_nsfw())
            # embed.add_field(name=_("Before ") + "NSFW", value=str(before.is_nsfw()))
            # embed.add_field(name=_("After ") + "NSFW", value=str(after.is_nsfw()))
            entry = await self.get_audit_log_entry(
                guild, before, discord.AuditLogAction.channel_update
            )
            perp = getattr(entry, "user", None)
            reason = getattr(entry, "reason", None)
        if before_text and after_text:
            for page in pagify(before_text, page_length=1024):
                embed.add_field(name=_("Before"), value=page)
            for page in pagify(after_text, page_length=1024):
                embed.add_field(name=_("After"), value=page)
        p_msg = await self.get_permission_change(before, after, embed_links)
        if p_msg != "":
            worth_updating = True
            msg += _("Permissions Changed: ") + p_msg
            for page in pagify(p_msg, page_length=1024):
                embed.add_field(name=_("Permissions"), value=page)

        if perp:
            msg += _("Updated by ") + str(perp) + "\n"
            embed.add_field(name=_("Updated by "), value=perp.mention)
        if reason:
            msg += _("Reason ") + reason + "\n"
            embed.add_field(name=_("Reason "), value=reason, inline=False)
        embed.add_field(name=_("Channel ID"), value=box(str(after.id)))
        if not worth_updating:
            return
        if embed_links:
            await channel.send(embed=embed, allowed_mentions=self.allowed_mentions)
        else:
            await channel.send(msg, allowed_mentions=self.allowed_mentions)

    async def get_role_permission_change(self, before: discord.Role, after: discord.Role) -> str:
        p_msg = ""
        changed_perms = dict(after.permissions).items() - dict(before.permissions).items()

        for p, change in changed_perms:
            p_msg += _("- {permission} Set to **{change}**\n").format(
                permission=p.replace("_", " ").title(), change=change
            )
        return p_msg

    @commands.Cog.listener()
    async def on_guild_role_update(self, before: discord.Role, after: discord.Role) -> None:
        guild = before.guild
        if guild.id not in self.settings:
            return
        if await self.bot.cog_disabled_in_guild(self, guild):
            return
        if guild.me.is_timed_out():
            return
        if not self.settings[guild.id]["role_change"]["enabled"]:
            return
        try:
            channel = await self.modlog_channel(guild, "role_change")
        except RuntimeError:
            return
        entry = await self.get_audit_log_entry(guild, before, discord.AuditLogAction.role_update)
        perp = getattr(entry, "user", None)
        reason = getattr(entry, "reason", None)
        embed_links = (
            channel.permissions_for(guild.me).embed_links
            and self.settings[guild.id]["role_change"]["embed"]
        )
        await i18n.set_contextual_locales_from_guild(self.bot, guild)
        # set guild level i18n
        time = datetime.datetime.now(datetime.timezone.utc)
        embed = discord.Embed(description=after.name, colour=after.colour, timestamp=time)
        msg = _("{emoji} {time} Updated role **{role}**\n").format(
            emoji=self.settings[guild.id]["role_change"]["emoji"],
            time=discord.utils.format_dt(time),
            role=before.name,
        )
        if after is guild.default_role:
            embed.set_author(name=_("Updated role "))
        else:
            embed.set_author(name=_("Updated Role ({r_id})").format(r_id=before.id))
        embed.add_field(name=_("Role"), value=after.mention)
        if perp:
            msg += _("Updated by ") + str(perp) + "\n"
            embed.add_field(name=_("Updated by "), value=perp.mention)
        if reason:
            msg += _("Reason ") + reason + "\n"
            embed.add_field(name=_("Reason "), value=reason, inline=False)
        role_updates = {
            "name": _("Name:"),
            "color": _("Colour:"),
            "mentionable": _("Mentionable:"),
            "hoist": _("Is Hoisted:"),
            "display_icon": _("Icon:"),
        }
        worth_updating = False
        for attr, name in role_updates.items():
            before_attr = getattr(before, attr)
            after_attr = getattr(after, attr)
            if before_attr != after_attr:
                worth_updating = True
                if before_attr == "":
                    before_attr = "None"
                if after_attr == "":
                    after_attr = "None"
                msg += _("Before ") + f"{name} {before_attr}\n"
                msg += _("After ") + f"{name} {after_attr}\n"
                embed.add_field(name=_("Before ") + name, value=str(before_attr))
                embed.add_field(name=_("After ") + name, value=str(after_attr))
        if before.display_icon != after.display_icon:
            if isinstance(before.display_icon, discord.Asset):
                embed.set_image(url=before.display_icon)
            elif isinstance(before.display_icon, str):
                cdn_fmt = (
                    "https://cdnjs.cloudflare.com/ajax/libs/twemoji/14.0.2/72x72/{codepoint:x}.png"
                )
                url = cdn_fmt.format(codepoint=ord(str(before.display_icon)))
                embed.set_image(url=url)
        if isinstance(after.display_icon, discord.Asset):
            embed.set_thumbnail(url=after.display_icon)
        elif isinstance(after.display_icon, str):
            cdn_fmt = (
                "https://cdnjs.cloudflare.com/ajax/libs/twemoji/14.0.2/72x72/{codepoint:x}.png"
            )
            url = cdn_fmt.format(codepoint=ord(str(after.display_icon)))
            embed.set_thumbnail(url=url)

        p_msg = await self.get_role_permission_change(before, after)
        if p_msg != "":
            worth_updating = True
            msg += _("Permissions Changed: ") + p_msg
            embed.add_field(name=_("Permissions"), value=p_msg[:1024])
        embed.add_field(name=_("Role ID"), value=box(str(after.id)))
        if not worth_updating:
            return
        if embed_links:
            await channel.send(embed=embed, allowed_mentions=self.allowed_mentions)
        else:
            await channel.send(msg, allowed_mentions=self.allowed_mentions)

    @commands.Cog.listener()
    async def on_guild_role_create(self, role: discord.Role) -> None:
        guild = role.guild
        if guild.id not in self.settings:
            return
        if await self.bot.cog_disabled_in_guild(self, guild):
            return
        if guild.me.is_timed_out():
            return
        if not self.settings[guild.id]["role_create"]["enabled"]:
            return
        try:
            channel = await self.modlog_channel(guild, "role_create")
        except RuntimeError:
            return
        entry = await self.get_audit_log_entry(guild, role, discord.AuditLogAction.role_create)
        perp = getattr(entry, "user", None)
        reason = getattr(entry, "reason", None)
        embed_links = (
            channel.permissions_for(guild.me).embed_links
            and self.settings[guild.id]["role_create"]["embed"]
        )
        await i18n.set_contextual_locales_from_guild(self.bot, guild)
        # set guild level i18n
        time = datetime.datetime.now(datetime.timezone.utc)
        embed = discord.Embed(
            description=role.name,
            colour=await self.get_event_colour(guild, "role_create"),
            timestamp=time,
        )
        embed.set_author(name=_("Role created ({r_id})").format(r_id=role.id))
        msg = _("{emoji} {time} Role created {role}\n").format(
            emoji=self.settings[guild.id]["role_create"]["emoji"],
            time=discord.utils.format_dt(time),
            role=role.name,
        )
        embed.add_field(name=_("Role"), value=role.mention)
        if perp:
            embed.add_field(name=_("Created by"), value=perp.mention)
            msg += _("By ") + str(perp) + "\n"
        if reason:
            msg += _("Reason ") + reason + "\n"
            embed.add_field(name=_("Reason "), value=reason, inline=False)
        embed.add_field(name=_("Role ID"), value=box(str(role.id)))
        if embed_links:
            await channel.send(embed=embed, allowed_mentions=self.allowed_mentions)
        else:
            await channel.send(msg, allowed_mentions=self.allowed_mentions)

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role) -> None:
        guild = role.guild
        if guild.id not in self.settings:
            return
        if await self.bot.cog_disabled_in_guild(self, guild):
            return
        if guild.me.is_timed_out():
            return
        if not self.settings[guild.id]["role_delete"]["enabled"]:
            return
        try:
            channel = await self.modlog_channel(guild, "role_delete")
        except RuntimeError:
            return
        entry = await self.get_audit_log_entry(guild, role, discord.AuditLogAction.role_delete)
        perp = getattr(entry, "user", None)
        reason = getattr(entry, "reason", None)
        embed_links = (
            channel.permissions_for(guild.me).embed_links
            and self.settings[guild.id]["role_delete"]["embed"]
        )
        await i18n.set_contextual_locales_from_guild(self.bot, guild)
        # set guild level i18n
        time = datetime.datetime.now(datetime.timezone.utc)
        embed = discord.Embed(
            description=role.name,
            timestamp=time,
            colour=await self.get_event_colour(guild, "role_delete"),
        )
        embed.set_author(name=_("Role deleted ({r_id})").format(r_id=role.id))
        msg = _("{emoji} {time} Role deleted **{role}**\n").format(
            emoji=self.settings[guild.id]["role_delete"]["emoji"],
            time=discord.utils.format_dt(time),
            role=role.name,
        )
        embed.add_field(name=_("Role"), value=role.mention)
        if perp:
            embed.add_field(name=_("Deleted by"), value=perp.mention)
            msg += _("By ") + str(perp) + "\n"
        if reason:
            msg += _("Reason ") + reason + "\n"
            embed.add_field(name=_("Reason "), value=reason, inline=False)
        embed.add_field(name=_("Role ID"), value=box(str(role.id)))
        if embed_links:
            await channel.send(embed=embed, allowed_mentions=self.allowed_mentions)
        else:
            await channel.send(msg, allowed_mentions=self.allowed_mentions)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message) -> None:
        guild = before.guild
        if guild is None:
            return
        if guild.id not in self.settings:
            return
        if await self.bot.cog_disabled_in_guild(self, guild):
            return
        if guild.me.is_timed_out():
            return
        settings = self.settings[guild.id]["message_edit"]
        if not settings["enabled"]:
            return
        if before.author.bot and not settings["bots"]:
            return
        if before.content == after.content:
            return
        try:
            channel = await self.modlog_channel(guild, "message_edit")
        except RuntimeError:
            return
        if await self.is_ignored_channel(guild, after.channel):
            return
        embed_links = (
            channel.permissions_for(guild.me).embed_links
            and self.settings[guild.id]["message_edit"]["embed"]
        )
        await i18n.set_contextual_locales_from_guild(self.bot, guild)
        # set guild level i18n
        time = datetime.datetime.now(datetime.timezone.utc)
        fmt = "%H:%M:%S"
        replying = ""
        if before.reference and before.reference.resolved:
            if isinstance(before.reference.resolved, discord.Message):
                ref_author = before.reference.resolved.author
                ref_jump = before.reference.resolved.jump_url
                replying = f"[{ref_author}]({ref_jump})"
            else:
                ref_guild = before.reference.resolved.guild_id
                ref_chan = before.reference.resolved.channel_id
                ref_msg = before.reference.resolved.id
                replying = f"https://discord.com/channels/{ref_guild}/{ref_chan}/{ref_msg}"
        if embed_links:
            embed = discord.Embed(
                description=f">>> {before.content}",
                colour=await self.get_event_colour(guild, "message_edit"),
                timestamp=before.created_at,
            )
            # jump_url = f"[Click to see new message]({after.jump_url})"
            embed.add_field(name=_("After Edit"), value=after.jump_url)
            embed.add_field(name=_("Channel"), value=before.channel.jump_url)
            if replying:
                embed.add_field(name=_("Replying to:"), value=replying)
            embed.add_field(name=_("Author"), value=before.author.mention)
            embed.set_author(
                name=_("{member} ({m_id}) - Edited Message").format(
                    member=before.author, m_id=before.author.id
                ),
                icon_url=str(before.author.display_avatar),
            )
            embed.add_field(name=_("Message ID"), value=box(str(after.id)))
            await channel.send(embed=embed, allowed_mentions=self.allowed_mentions)
        else:
            msg = _(
                "{emoji} {time} **{author}** (`{a_id}`) edited a message "
                "in {channel}.\nBefore:\n> {before}\nAfter:\n> {after}"
            ).format(
                emoji=self.settings[guild.id]["message_edit"]["emoji"],
                time=time.strftime(fmt),
                author=before.author,
                a_id=before.author.id,
                channel=before.channel.mention,
                before=before.content,
                after=after.jump_url,
            )
            await channel.send(msg[:2000], allowed_mentions=self.allowed_mentions)

    @commands.Cog.listener()
    async def on_guild_update(self, before: discord.Guild, after: discord.Guild) -> None:
        guild = after
        if guild.id not in self.settings:
            return
        if await self.bot.cog_disabled_in_guild(self, guild):
            return
        if guild.me.is_timed_out():
            return
        if not self.settings[guild.id]["guild_change"]["enabled"]:
            return
        try:
            channel = await self.modlog_channel(guild, "guild_change")
        except RuntimeError:
            return
        embed_links = (
            channel.permissions_for(guild.me).embed_links
            and self.settings[guild.id]["guild_change"]["embed"]
        )
        await i18n.set_contextual_locales_from_guild(self.bot, guild)
        # set guild level i18n
        time = datetime.datetime.now(datetime.timezone.utc)
        embed = discord.Embed(
            timestamp=time, colour=await self.get_event_colour(guild, "guild_change")
        )
        embed.set_author(
            name=_("Updated Guild"),
            icon_url=guild.icon,
        )
        embed.set_thumbnail(url=guild.icon)
        msg = _("{emoji} {time} Guild updated\n").format(
            emoji=self.settings[guild.id]["guild_change"]["emoji"],
            time=discord.utils.format_dt(time),
        )
        guild_updates = {
            "name": _("Name:"),
            "afk_timeout": _("AFK Timeout:"),
            "afk_channel": _("AFK Channel:"),
            "icon": _("Server Icon:"),
            "owner": _("Server Owner:"),
            "splash": _("Splash Image:"),
            "system_channel": _("Welcome message channel:"),
            "verification_level": _("Verification Level:"),
        }
        worth_updating = False
        for attr, name in guild_updates.items():
            before_attr = getattr(before, attr)
            after_attr = getattr(after, attr)
            if before_attr != after_attr:
                worth_updating = True
                if attr == "icon":
                    embed.description = _("Server Icon Updated")
                    embed.set_image(url=after.icon)
                    continue
                msg += _("Before ") + f"{name} {before_attr}\n"
                msg += _("After ") + f"{name} {after_attr}\n"
                embed.add_field(name=_("Before ") + name, value=str(before_attr))
                embed.add_field(name=_("After ") + name, value=str(after_attr))
        if not worth_updating:
            return
        perp = None
        reason = None
        if channel.permissions_for(guild.me).view_audit_log:
            action = discord.AuditLogAction.guild_update
            entry = await self.get_audit_log_entry(guild, None, action)
            perp = getattr(entry, "user", None)
            reason = getattr(entry, "reason", None)

        if perp:
            embed.add_field(name=_("Updated by"), value=perp)
        if reason:
            embed.add_field(name=_("Reasons "), value=reason, inline=False)
        if embed_links:
            await channel.send(embed=embed, allowed_mentions=self.allowed_mentions)
        else:
            await channel.send(msg, allowed_mentions=self.allowed_mentions)

    @commands.Cog.listener()
    async def on_guild_emojis_update(
        self, guild: discord.Guild, before: Sequence[discord.Emoji], after: Sequence[discord.Emoji]
    ) -> None:
        if guild.id not in self.settings:
            return
        if await self.bot.cog_disabled_in_guild(self, guild):
            return
        if guild.me.is_timed_out():
            return
        if not self.settings[guild.id]["emoji_change"]["enabled"]:
            return
        try:
            channel = await self.modlog_channel(guild, "emoji_change")
        except RuntimeError:
            return
        embed_links = (
            channel.permissions_for(guild.me).embed_links
            and self.settings[guild.id]["emoji_change"]["embed"]
        )
        await i18n.set_contextual_locales_from_guild(self.bot, guild)
        # set guild level i18n
        perp = None

        time = datetime.datetime.now(datetime.timezone.utc)
        embed = discord.Embed(
            description="",
            timestamp=time,
            colour=await self.get_event_colour(guild, "emoji_change"),
        )
        embed.set_author(name=_("Updated Server Emojis"))
        msg = _("{emoji} {time} Updated Server Emojis").format(
            emoji=self.settings[guild.id]["emoji_change"]["emoji"],
            time=discord.utils.format_dt(time),
        )
        worth_updating = False
        b = set(before)
        a = set(after)
        added_emoji: Optional[discord.Emoji] = None
        removed_emoji: Optional[discord.Emoji] = None
        # discord.Emoji uses id for hashing so we use set difference to get added/removed emoji
        try:
            added_emoji = (a - b).pop()
        except KeyError:
            pass
        try:
            removed_emoji = (b - a).pop()
        except KeyError:
            pass
        # changed emojis have their name and/or allowed roles changed while keeping id unchanged
        if added_emoji is not None:
            to_iter = before + (added_emoji,)
        else:
            to_iter = before
        changed_emoji = set((e, e.name, tuple(e.roles)) for e in after)
        changed_emoji.difference_update((e, e.name, tuple(e.roles)) for e in to_iter)
        try:
            changed_emoji = changed_emoji.pop()[0]
        except KeyError:
            changed_emoji = None
        else:
            for old_emoji in before:
                if old_emoji.id == changed_emoji.id:
                    break
            else:
                # this shouldn't happen but it's here just in case
                changed_emoji = None
        action = None
        if removed_emoji is not None:
            worth_updating = True
            new_msg = _("`{emoji_name}` (ID: {emoji_id}) Removed from the guild\n").format(
                emoji_name=removed_emoji, emoji_id=removed_emoji.id
            )
            msg += new_msg
            embed.description += new_msg
            action = discord.AuditLogAction.emoji_delete
        elif added_emoji is not None:
            worth_updating = True
            new_emoji = f"{added_emoji} `{added_emoji}`"
            new_msg = _("{emoji} Added to the guild\n").format(emoji=new_emoji)
            msg += new_msg
            embed.description += new_msg
            action = discord.AuditLogAction.emoji_create
        elif changed_emoji is not None:
            worth_updating = True
            emoji_name = f"{changed_emoji} `{changed_emoji}`"
            if old_emoji.name != changed_emoji.name:
                new_msg = _("{emoji} Renamed from {old_emoji_name} to {new_emoji_name}\n").format(
                    emoji=emoji_name,
                    old_emoji_name=old_emoji.name,
                    new_emoji_name=changed_emoji.name,
                )
                # emoji_update shows only for renames and not for role restriction updates
                action = discord.AuditLogAction.emoji_update
                msg += new_msg
                embed.description += new_msg
            if old_emoji.roles != changed_emoji.roles:
                worth_updating = True
                if not changed_emoji.roles:
                    new_msg = _("{emoji} Changed to unrestricted.\n").format(emoji=emoji_name)
                    msg += new_msg
                    embed.description += new_msg
                elif not old_emoji.roles:
                    new_msg = _("{emoji} Restricted to roles: {roles}\n").format(
                        emoji=emoji_name,
                        roles=humanize_list(
                            [f"{role.name} ({role.id})" for role in changed_emoji.roles]
                        ),
                    )
                    msg += new_msg
                    embed.description += new_msg
                else:
                    new_msg = _(
                        "{emoji} Role restriction changed from\n {old_roles}\n To\n {new_roles}"
                    ).format(
                        emoji=emoji_name,
                        old_roles=humanize_list(
                            [f"{role.mention} ({role.id})" for role in old_emoji.roles]
                        ),
                        new_roles=humanize_list(
                            [f"{role.name} ({role.id})" for role in changed_emoji.roles]
                        ),
                    )
                    msg += new_msg
                    embed.description += new_msg
        perp = None
        reason = None
        if not worth_updating:
            return
        if channel.permissions_for(guild.me).view_audit_log:
            if action:
                entry = await self.get_audit_log_entry(guild, None, action)
                perp = getattr(entry, "user", None)
                reason = getattr(entry, "reason", None)
        if perp:
            embed.add_field(name=_("Updated by "), value=perp.mention)
            msg += _("Updated by ") + str(perp) + "\n"
        if reason:
            msg += _("Reason ") + reason + "\n"
            embed.add_field(name=_("Reason "), value=reason, inline=False)
        if embed_links:
            await channel.send(embed=embed, allowed_mentions=self.allowed_mentions)
        else:
            await channel.send(msg, allowed_mentions=self.allowed_mentions)

    @commands.Cog.listener()
    async def on_voice_state_update(
        self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState
    ) -> None:
        guild = member.guild
        if guild.id not in self.settings:
            return
        if await self.bot.cog_disabled_in_guild(self, guild):
            return
        if guild.me.is_timed_out():
            return
        if not self.settings[guild.id]["voice_change"]["enabled"]:
            return
        if member.bot and not self.settings[guild.id]["voice_change"]["bots"]:
            return
        try:
            channel = await self.modlog_channel(guild, "voice_change")
        except RuntimeError:
            return
        if after.channel is not None:
            if await self.is_ignored_channel(guild, after.channel):
                return
        if before.channel is not None:
            if await self.is_ignored_channel(guild, before.channel):
                return
        embed_links = (
            channel.permissions_for(guild.me).embed_links
            and self.settings[guild.id]["voice_change"]["embed"]
        )
        await i18n.set_contextual_locales_from_guild(self.bot, guild)
        # set guild level i18n
        time = datetime.datetime.now(datetime.timezone.utc)
        embed = discord.Embed(
            timestamp=time,
            colour=await self.get_event_colour(guild, "voice_change"),
        )
        msg = _("{emoji} {time} Updated Voice State for **{member}** (`{m_id}`)").format(
            emoji=self.settings[guild.id]["voice_change"]["emoji"],
            time=discord.utils.format_dt(time),
            member=member,
            m_id=member.id,
        )
        embed.set_author(
            name=_("{member} ({m_id}) Voice State Update").format(member=member, m_id=member.id)
        )
        change_type = None
        worth_updating = False
        if before.deaf != after.deaf:
            worth_updating = True
            change_type = "deaf"
            if after.deaf:
                chan_msg = _("{member} was deafened. ").format(member=member.mention)
                msg += chan_msg + "\n"
                embed.description = chan_msg
            else:
                chan_msg = _("{member} was undeafened. ").format(member=member.mention)
                msg += chan_msg + "\n"
                embed.description = chan_msg
        if before.mute != after.mute:
            worth_updating = True
            change_type = "mute"
            if after.mute:
                chan_msg = _("{member} was muted.").format(member=member.mention)
                msg += chan_msg + "\n"
                embed.description = chan_msg
            else:
                chan_msg = _("{member} was unmuted. ").format(member=member.mention)
                msg += chan_msg + "\n"
                embed.description = chan_msg
        if before.channel != after.channel:
            worth_updating = True
            change_type = "channel"
            if before.channel is None:
                channel_name = (
                    f"`{after.channel.name}` ({after.channel.id}) {after.channel.mention}"
                )
                chan_msg = _("{member} has joined {after_channel}").format(
                    member=member.mention, after_channel=channel_name
                )
                msg += chan_msg + "\n"
                embed.description = chan_msg
            elif after.channel is None:
                channel_name = (
                    f"`{before.channel.name}` ({before.channel.id}) {before.channel.mention}"
                )
                chan_msg = _("{member} has left {before_channel}").format(
                    member=member.mention, before_channel=channel_name
                )
                msg += chan_msg + "\n"
                embed.description = chan_msg
            else:
                after_chan = f"`{after.channel.name}` ({after.channel.id}) {after.channel.mention}"
                before_chan = (
                    f"`{before.channel.name}` ({before.channel.id}) {before.channel.mention}"
                )
                chan_msg = _("{member} has moved from {before_channel} to {after_channel}").format(
                    member=member.mention,
                    before_channel=before_chan,
                    after_channel=after_chan,
                )
                msg += chan_msg
                embed.description = chan_msg
        if not worth_updating:
            return
        perp = None
        reason = None
        if channel.permissions_for(guild.me).view_audit_log and change_type:
            action = discord.AuditLogAction.member_update
            entry = await self.get_audit_log_entry(guild, member, action, extra=change_type)
            if entry and getattr(entry.after, change_type, None) is not None:
                perp = getattr(entry, "user", None)
                reason = getattr(entry, "reason", None)
        if perp:
            embed.add_field(name=_("Updated by"), value=perp.mention)
        if reason:
            msg += _("Reason ") + reason + "\n"
            embed.add_field(name=_("Reason "), value=reason, inline=False)
        if embed_links:
            await channel.send(embed=embed, allowed_mentions=self.allowed_mentions)
        else:
            await channel.send(msg, allowed_mentions=self.allowed_mentions)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member) -> None:
        guild = before.guild
        if guild.id not in self.settings:
            return
        if await self.bot.cog_disabled_in_guild(self, guild):
            return
        if guild.me.is_timed_out():
            return
        if not self.settings[guild.id]["user_change"]["enabled"]:
            return
        if not self.settings[guild.id]["user_change"]["bots"] and after.bot:
            return
        try:
            channel = await self.modlog_channel(guild, "user_change")
        except RuntimeError:
            return
        embed_links = (
            channel.permissions_for(guild.me).embed_links
            and self.settings[guild.id]["user_change"]["embed"]
        )
        await i18n.set_contextual_locales_from_guild(self.bot, guild)
        # set guild level i18n
        time = datetime.datetime.now(datetime.timezone.utc)
        embed = discord.Embed(
            timestamp=time, colour=await self.get_event_colour(guild, "user_change")
        )
        msg = _("{emoji} {time} Member updated **{member}** (`{m_id}`)\n").format(
            emoji=self.settings[guild.id]["user_change"]["emoji"],
            time=discord.utils.format_dt(time),
            member=before,
            m_id=before.id,
        )
        embed.description = ""
        emb_msg = _("{member} ({m_id}) updated").format(member=before, m_id=before.id)
        embed.set_author(name=emb_msg, icon_url=before.display_avatar)
        perp = None
        reason = None
        worth_sending = False
        before_text = ""
        after_text = ""
        for update_type in MemberUpdateEnum:
            attr = update_type.value
            if not self.settings[guild.id]["user_change"][update_type.name]:
                continue
            before_attr = getattr(before, attr, None)
            after_attr = getattr(after, attr, None)
            if before_attr != after_attr:
                if attr == "roles":
                    b = set(before.roles)
                    a = set(after.roles)
                    before_roles = list(b - a)
                    after_roles = list(a - b)
                    logger.debug("on_member_update after_roles: %s", after_roles)
                    if before_roles:
                        for role in before_roles:
                            msg += _("{author} had the {role} role removed.").format(
                                author=after.name, role=role.name
                            )
                            embed.description += _(
                                "{author} had the {role} role removed.\n"
                            ).format(author=after.mention, role=role.mention)
                            worth_sending = True
                    if after_roles:
                        for role in after_roles:
                            msg += _("{author} had the {role} role applied.").format(
                                author=after.name, role=role.name
                            )
                            embed.description += _(
                                "{author} had the {role} role applied.\n"
                            ).format(author=after.mention, role=role.mention)
                            worth_sending = True
                    entry = await self.get_audit_log_entry(
                        guild, before, discord.AuditLogAction.member_role_update
                    )
                    perp = getattr(entry, "user", None)
                    reason = getattr(entry, "reason", None)
                elif attr == "flags":
                    changed_flags = [
                        key.replace("_", " ").title()
                        for key, value in dict(before.flags ^ after.flags).items()
                        if value
                    ]
                    flags_str = "\n".join(f"- {flag}" for flag in changed_flags)
                    add_str = _("{author} had the following flag changes:\n{flag_str}").format(
                        author=after.mention, flag_str=flags_str
                    )
                    msg += add_str
                    embed.description += add_str

                elif attr == "guild_avatar":
                    worth_sending = True
                    embed.set_image(url=after_attr)
                    if after_attr:
                        embed.description += _(
                            "- {author} changed their [guild avatar]({after_attr}).\n"
                        ).format(author=after.mention, after_attr=after_attr)
                    else:
                        embed.description += _("- {author} removed their guild avatar.\n").format(
                            author=after.mention, after_attr=after_attr
                        )

                else:
                    entry = await self.get_audit_log_entry(
                        guild, before, discord.AuditLogAction.member_update
                    )
                    perp = getattr(entry, "user", None)
                    reason = getattr(entry, "reason", None)
                    worth_sending = True
                    if isinstance(before_attr, datetime.datetime):
                        before_ts = discord.utils.format_dt(before_attr)
                        before_ts_rel = discord.utils.format_dt(before_attr, style="R")
                        before_attr = f"{before_ts} ({before_ts_rel})"
                    if isinstance(after_attr, datetime.datetime):
                        after_ts = discord.utils.format_dt(after_attr)
                        after_ts_rel = discord.utils.format_dt(after_attr, style="R")
                        after_attr = f"{after_ts} ({after_ts_rel})"
                    msg += _("Before ") + f"{update_type.get_name()} {before_attr}\n"
                    msg += _("After ") + f"{update_type.get_name()} {after_attr}\n"
                    embed.description = _("{author} has updated.").format(author=after.mention)
                    before_text += f"- {update_type.get_name()}: {before_attr}\n"
                    after_text += f"- {update_type.get_name()}: {after_attr}\n"
                    # embed.add_field(name=_("Before ") + name, value=str(before_attr)[:1024])
                    # embed.add_field(name=_("After ") + name, value=str(after_attr)[:1024])
        if before_text and after_text:
            for page in pagify(before_text, page_length=1024):
                embed.add_field(name=_("Before"), value=page)
            for page in pagify(after_text, page_length=1024):
                embed.add_field(name=_("After"), value=page)
        if not worth_sending:
            return
        if perp:
            msg += _("Updated by ") + f"{perp}\n"
            embed.add_field(name=_("Updated by "), value=perp.mention)
        if reason:
            msg += _("Reason: ") + f"{reason}\n"
            embed.add_field(name=_("Reason"), value=reason, inline=False)
        embed.add_field(name=_("Member ID"), value=box(str(after.id)))
        if embed_links:
            await channel.send(embed=embed, allowed_mentions=self.allowed_mentions)
        else:
            await channel.send(msg, allowed_mentions=self.allowed_mentions)

    @commands.Cog.listener()
    async def on_invite_create(self, invite: discord.Invite) -> None:
        """
        New in discord.py 1.3
        """
        if invite.guild is None:
            return
        guild = self.bot.get_guild(invite.guild.id)
        if guild is None:
            return
        if guild.id not in self.settings:
            return
        if await self.bot.cog_disabled_in_guild(self, guild):
            return
        if guild.me.is_timed_out():
            return
        if invite.code not in self.settings[guild.id]["invite_links"]:
            created_at = getattr(
                invite, "created_at", datetime.datetime.now(datetime.timezone.utc)
            )
            inviter = getattr(invite, "inviter", discord.Object(id=0))
            channel = getattr(invite, "channel", discord.Object(id=0))
            self.settings[guild.id]["invite_links"][invite.code] = {
                "uses": getattr(invite, "uses", 0),
                "max_age": getattr(invite, "max_age", None),
                "created_at": created_at.timestamp(),
                "max_uses": getattr(invite, "max_uses", None),
                "temporary": getattr(invite, "temporary", False),
                "inviter": getattr(inviter, "id", "Unknown"),
                "channel": channel.id,
            }
            await self.save(guild)
        if not self.settings[guild.id]["invite_created"]["enabled"]:
            return
        try:
            channel = await self.modlog_channel(guild, "invite_created")
        except RuntimeError:
            return
        embed_links = (
            channel.permissions_for(guild.me).embed_links
            and self.settings[guild.id]["invite_created"]["embed"]
        )
        await i18n.set_contextual_locales_from_guild(self.bot, guild)
        # set guild level i18n
        invite_attrs = {
            "code": _("Code:"),
            "inviter": _("Inviter:"),
            "channel": _("Channel:"),
            "max_uses": _("Max Uses:"),
            "max_age": _("Max Age:"),
            "temporary": _("Temporary:"),
            "scheduled_event": _("Scheduled Event:"),
        }
        invite_time = invite.created_at or datetime.datetime.now(datetime.timezone.utc)
        msg = _("{emoji} {time} Invite created ").format(
            emoji=self.settings[guild.id]["invite_created"]["emoji"],
            time=discord.utils.format_dt(invite_time),
        )
        embed = discord.Embed(
            title=_("Invite Created"),
            colour=await self.get_event_colour(guild, "invite_created"),
            timestamp=invite_time,
        )
        worth_updating = False

        if getattr(invite, "inviter", None):
            embed.description = _("{author} created an invite for {channel}.").format(
                author=getattr(invite.inviter, "mention", invite.inviter),
                channel=getattr(invite.channel, "mention", str(invite.channel)),
            )
        elif guild.widget_enabled and guild.widget_channel:
            embed.description = _("Widget in {channel} created a new invite.").format(
                channel=guild.widget_channel.mention
            )
        if embed.description is None:
            embed.description = invite.url
        else:
            embed.description += f"\n{invite.url}"
        for attr, name in invite_attrs.items():
            before_attr = getattr(invite, attr)
            if before_attr:
                if attr == "max_age":
                    before_attr = humanize_timedelta(seconds=before_attr)
                if attr == "channel":
                    before_attr = getattr(before_attr, "mention", before_attr)
                if attr == "inviter":
                    before_attr = getattr(before_attr, "mention", before_attr)
                if attr == "code":
                    before_attr = box(before_attr)
                if attr == "scheduled_event":
                    before_attr = getattr(invite.scheduled_event, "url", "")
                worth_updating = True
                msg += f"{name} {before_attr}\n"
                embed.add_field(name=name, value=str(before_attr))
        if not worth_updating:
            return
        if embed_links:
            await channel.send(embed=embed, allowed_mentions=self.allowed_mentions)
        else:
            await channel.send(msg, allowed_mentions=self.allowed_mentions)

    @commands.Cog.listener()
    async def on_invite_delete(self, invite: discord.Invite) -> None:
        """
        New in discord.py 1.3
        """
        if invite.guild is None:
            return
        guild = self.bot.get_guild(invite.guild.id)
        if guild is None:
            return
        if guild.id not in self.settings:
            return
        if await self.bot.cog_disabled_in_guild(self, guild):
            return
        if guild.me.is_timed_out():
            return
        if not self.settings[guild.id]["invite_deleted"]["enabled"]:
            return
        try:
            channel = await self.modlog_channel(guild, "invite_deleted")
        except RuntimeError:
            return
        embed_links = (
            channel.permissions_for(guild.me).embed_links
            and self.settings[guild.id]["invite_deleted"]["embed"]
        )
        await i18n.set_contextual_locales_from_guild(self.bot, guild)
        # set guild level i18n
        invite_attrs = {
            "code": _("Code: "),
            "inviter": _("Inviter: "),
            "channel": _("Channel: "),
            "max_uses": _("Max Uses: "),
            "uses": _("Used: "),
            "max_age": _("Max Age:"),
            "temporary": _("Temporary:"),
            "scheduled_event": _("Scheduled Event:"),
        }
        invite_time = invite.created_at or datetime.datetime.now(datetime.timezone.utc)
        msg = _("{emoji} {time} Invite deleted ").format(
            emoji=self.settings[guild.id]["invite_deleted"]["emoji"],
            time=discord.utils.format_dt(invite_time),
        )
        embed = discord.Embed(
            title=_("Invite Deleted"),
            colour=await self.get_event_colour(guild, "invite_deleted"),
            timestamp=invite_time,
        )
        if getattr(invite, "inviter", None):
            embed.description = _("{author} deleted or used up an invite for {channel}.").format(
                author=invite.inviter.mention, channel=invite.channel.mention
            )
        elif guild.widget_enabled and guild.widget_channel:
            embed.description = _("Widget in {channel} invite deleted or used up.").format(
                channel=guild.widget_channel.mention
            )
        if embed.description is None:
            embed.description = invite.url
        else:
            embed.description += f"\n{invite.url}"
        entry = await self.get_audit_log_entry(guild, invite, discord.AuditLogAction.invite_delete)
        perp = getattr(entry, "user", None)
        reason = getattr(entry, "reason", None)
        worth_updating = False
        for attr, name in invite_attrs.items():
            before_attr = getattr(invite, attr)
            if before_attr:
                if attr == "max_age":
                    before_attr = humanize_timedelta(seconds=before_attr)
                if attr == "channel":
                    before_attr = getattr(before_attr, "mention", before_attr)
                if attr == "inviter":
                    before_attr = getattr(before_attr, "mention", before_attr)
                if attr == "code":
                    before_attr = box(before_attr)
                if attr == "scheduled_event":
                    before_attr = getattr(invite.scheduled_event, "url", "")
                worth_updating = True
                msg += f"{name} {before_attr}\n"
                embed.add_field(name=name, value=str(before_attr))
        if perp:
            perp_str = getattr(perp, "mention", str(perp))
            msg += _("Deleted by") + f" {perp}.\n"
            embed.add_field(name=_("Deleted by"), value=perp_str)
        if reason:
            msg += _("Reason") + f": {perp}\n"
            embed.add_field(name=_("Reason"), value=reason)
        if not worth_updating:
            return
        if embed_links:
            await channel.send(embed=embed, allowed_mentions=self.allowed_mentions)
        else:
            await channel.send(msg, allowed_mentions=self.allowed_mentions)

    @commands.Cog.listener()
    async def on_thread_create(self, thread: discord.Thread) -> None:
        guild = thread.guild
        if guild.id not in self.settings:
            return
        if not self.settings[guild.id]["thread_create"]["enabled"]:
            return
        if await self.bot.cog_disabled_in_guild(self, guild):
            return
        if guild.me.is_timed_out():
            return
        if await self.is_ignored_channel(guild, thread.parent_id):
            return
        try:
            channel = await self.modlog_channel(guild, "thread_create")
        except RuntimeError:
            return
        embed_links = (
            channel.permissions_for(guild.me).embed_links
            and self.settings[guild.id]["thread_create"]["embed"]
        )
        await i18n.set_contextual_locales_from_guild(self.bot, guild)
        # set guild level i18n
        time = datetime.datetime.now(datetime.timezone.utc)
        channel_type = str(thread.type).replace("_", " ").title()
        embed = discord.Embed(
            description=thread.name,
            timestamp=time,
            colour=await self.get_event_colour(guild, "thread_create"),
        )

        embed.set_author(
            name=_("{chan_type} Thread Created ({chan_id})").format(
                chan_type=channel_type, chan_id=thread.id
            )
        )
        # msg = _("Channel Created ") + str(new_channel.id) + "\n"
        entry = await self.get_audit_log_entry(guild, thread, discord.AuditLogAction.thread_create)
        perp = getattr(entry, "user", None)
        reason = getattr(entry, "reason", None)
        if thread.owner:
            owner = thread.owner
        else:
            owner = await self.bot.fetch_user(thread.owner_id)
        embed.add_field(name=_("Thread"), value=thread.mention)
        embed.add_field(name=_("Type"), value=channel_type)
        perp_msg = _("by {perp} (`{perp_id}`)").format(perp=owner, perp_id=owner.id)
        embed.add_field(name=_("Created by "), value=owner.mention)
        if reason:
            perp_msg += _(" Reason: {reason}").format(reason=reason)
            embed.add_field(name=_("Reason "), value=reason, inline=False)
        embed.add_field(name=_("Thread ID"), value=box(str(thread.id)))
        msg = _("{emoji} {time} {chan_type} channel created {perp_msg} {channel}").format(
            emoji=self.settings[guild.id]["thread_create"]["emoji"],
            time=discord.utils.format_dt(time),
            chan_type=channel_type,
            perp_msg=perp_msg,
            channel=thread.mention,
        )
        if embed_links:
            await channel.send(embed=embed, allowed_mentions=self.allowed_mentions)
        else:
            await channel.send(msg, allowed_mentions=self.allowed_mentions)

    @commands.Cog.listener()
    async def on_raw_thread_delete(self, payload: discord.RawThreadDeleteEvent):
        guild = self.bot.get_guild(payload.guild_id)
        if guild is None:
            return
        if guild.id not in self.settings:
            return
        if not self.settings[guild.id]["thread_delete"]["enabled"]:
            return
        if await self.bot.cog_disabled_in_guild(self, guild):
            return
        if guild.me.is_timed_out():
            return
        if await self.is_ignored_channel(guild, payload.parent_id):
            return
        try:
            channel = await self.modlog_channel(guild, "thread_delete")
        except RuntimeError:
            return
        embed_links = (
            channel.permissions_for(guild.me).embed_links
            and self.settings[guild.id]["channel_delete"]["embed"]
        )
        await i18n.set_contextual_locales_from_guild(self.bot, guild)
        # set guild level i18n
        channel_type = str(payload.thread_type).replace("_", " ").title()
        time = datetime.datetime.now(datetime.timezone.utc)
        parent = guild.get_channel(payload.parent_id)
        description = _("Thread in {channel}").format(
            channel=parent.mention if parent else payload.parent_id
        )
        if payload.thread:
            description = _("{thread} thread in {channel}").format(
                thread=payload.thread.mention,
                channel=parent.mention if parent else payload.parent_id,
            )
        embed = discord.Embed(
            description=description,
            timestamp=time,
            colour=await self.get_event_colour(guild, "thread_delete"),
        )
        embed.set_author(
            name=_("{chan_type} Thread Deleted ({chan_id})").format(
                chan_type=channel_type, chan_id=payload.thread_id
            )
        )
        entry = await self.get_audit_log_entry(
            guild, payload.thread_id, discord.AuditLogAction.thread_delete
        )
        perp = getattr(entry, "user", None)
        reason = getattr(entry, "reason", None)

        perp_msg = ""
        embed.add_field(name=_("Type"), value=channel_type)
        if perp:
            perp_msg = _("by {perp} (`{perp_id}`)").format(perp=perp, perp_id=perp.id)
            embed.add_field(name=_("Deleted by "), value=perp.mention)
        if reason:
            perp_msg += _(" Reason: {reason}").format(reason=reason)
            embed.add_field(name=_("Reason "), value=reason, inline=False)
        embed.add_field(name=_("Thread ID"), value=box(str(payload.thread_id)))
        msg = _("{emoji} {time} {chan_type} channel deleted {perp_msg} {channel}").format(
            emoji=self.settings[guild.id]["thread_delete"]["emoji"],
            time=discord.utils.format_dt(time),
            chan_type=channel_type,
            perp_msg=perp_msg,
            channel=f"#{description} ({payload.thread_id})",
        )
        if embed_links:
            await channel.send(embed=embed, allowed_mentions=self.allowed_mentions)
        else:
            await channel.send(msg, allowed_mentions=self.allowed_mentions)

    @commands.Cog.listener()
    async def on_thread_update(self, before: discord.Thread, after: discord.Thread) -> None:
        guild = before.guild
        if guild.id not in self.settings:
            return
        if await self.bot.cog_disabled_in_guild(self, guild):
            return
        if guild.me.is_timed_out():
            return
        if not self.settings[guild.id]["thread_change"]["enabled"]:
            return
        if await self.is_ignored_channel(guild, before):
            return
        try:
            channel = await self.modlog_channel(guild, "thread_change")
        except RuntimeError:
            return
        embed_links = (
            channel.permissions_for(guild.me).embed_links
            and self.settings[guild.id]["thread_change"]["embed"]
        )
        await i18n.set_contextual_locales_from_guild(self.bot, guild)
        # set guild level i18n
        channel_type = str(after.type).title()
        time = datetime.datetime.now(datetime.timezone.utc)
        embed = discord.Embed(
            description=after.mention,
            timestamp=time,
            colour=await self.get_event_colour(guild, "thread_change"),
        )
        embed.set_author(
            name=_("{chan_type} Thread Updated {chan_name} ({chan_id})").format(
                chan_type=channel_type, chan_name=before.name, chan_id=before.id
            )
        )
        msg = _("{emoji} {time} Updated Thread {channel}\n").format(
            emoji=self.settings[guild.id]["thread_change"]["emoji"],
            time=discord.utils.format_dt(time),
            channel=before.name,
        )
        worth_updating = False
        perp = None
        reason = None
        text_updates = {
            "name": _("Name"),
            "slowmode_delay": _("Slowmode delay"),
            "auto_archive_duration": _("Archive Duration"),
            "locked": _("Locked"),
            "archived": _("Archived"),
        }
        before_changes = []
        after_changes = []
        for attr, name in text_updates.items():
            before_attr = getattr(before, attr)
            after_attr = getattr(after, attr)
            if before_attr != after_attr:
                worth_updating = True
                if before_attr == "":
                    before_attr = "None"
                if after_attr == "":
                    after_attr = "None"
                before_str = _("Before ") + f"{name}: {before_attr}\n"
                after_str = _("After ") + f"{name}: {after_attr}\n"
                msg += before_str + after_str
                before_changes.append(f"{name}: {before_attr}\n")
                after_changes.append(f"{name}: {after_attr}\n")
                entry = await self.get_audit_log_entry(
                    guild, before, discord.AuditLogAction.thread_update
                )
                perp = getattr(entry, "user", None)
                reason = getattr(entry, "reason", None)
        if before_changes or after_changes:
            embed.add_field(name=_("Before"), value="".join(i for i in before_changes))
            embed.add_field(name=_("After"), value="".join(i for i in after_changes))
        if before.archiver_id != after.archiver_id:
            worth_updating = True
            member = before.guild.get_member(after.archiver_id)
            embed.add_field(name=_("Archived by:"), value=f"{member.mention}")
            entry = await self.get_audit_log_entry(
                guild, before, discord.AuditLogAction.channel_update
            )
            perp = getattr(entry, "user", None)
            reason = getattr(entry, "reason", None)

        if perp:
            msg += _("Updated by ") + str(perp) + "\n"
            embed.add_field(name=_("Updated by "), value=perp.mention)
        if reason:
            msg += _("Reason ") + reason + "\n"
            embed.add_field(name=_("Reason "), value=reason, inline=False)
        embed.add_field(name=_("Thread ID"), value=box(str(after.id)))
        if not worth_updating:
            return
        if embed_links:
            await channel.send(embed=embed, allowed_mentions=self.allowed_mentions)
        else:
            await channel.send(msg, allowed_mentions=self.allowed_mentions)

    @commands.Cog.listener()
    async def on_guild_stickers_update(
        self, guild: discord.Guild, before: Sequence[discord.Emoji], after: Sequence[discord.Emoji]
    ) -> None:
        if guild.id not in self.settings:
            return
        if await self.bot.cog_disabled_in_guild(self, guild):
            return
        if guild.me.is_timed_out():
            return
        if not self.settings[guild.id]["stickers_change"]["enabled"]:
            return
        try:
            channel = await self.modlog_channel(guild, "stickers_change")
        except RuntimeError:
            return
        embed_links = (
            channel.permissions_for(guild.me).embed_links
            and self.settings[guild.id]["stickers_change"]["embed"]
        )
        await i18n.set_contextual_locales_from_guild(self.bot, guild)
        # set guild level i18n
        perp = None

        time = datetime.datetime.now(datetime.timezone.utc)
        embed = discord.Embed(
            description="",
            timestamp=time,
            colour=await self.get_event_colour(guild, "stickers_change"),
        )
        embed.set_author(name=_("Updated Server Stickers"))
        msg = _("{emoji} {time} Updated Server Stickers").format(
            emoji=self.settings[guild.id]["stickers_change"]["emoji"],
            time=discord.utils.format_dt(time),
        )
        worth_updating = False
        b = set(before)
        a = set(after)
        added_emoji: Optional[discord.GuildSticker] = None
        removed_emoji: Optional[discord.GuildSticker] = None
        # discord.Emoji uses id for hashing so we use set difference to get added/removed emoji
        try:
            added_emoji = (a - b).pop()
        except KeyError:
            pass
        try:
            removed_emoji = (b - a).pop()
        except KeyError:
            pass
        # changed emojis have their name and/or allowed roles changed while keeping id unchanged
        if added_emoji is not None:
            to_iter = before + (added_emoji,)
        else:
            to_iter = before
        changed_emoji = set((e, e.name) for e in after)
        changed_emoji.difference_update((e, e.name) for e in to_iter)
        try:
            changed_emoji = changed_emoji.pop()[0]
        except KeyError:
            changed_emoji = None
        else:
            for old_emoji in before:
                if old_emoji.id == changed_emoji.id:
                    break
            else:
                # this shouldn't happen but it's here just in case
                changed_emoji = None
        action = None
        if removed_emoji is not None:
            worth_updating = True
            new_msg = _("`{emoji_name}` (ID: {emoji_id}) Removed from the guild\n").format(
                emoji_name=removed_emoji, emoji_id=removed_emoji.id
            )
            msg += new_msg
            embed.description += new_msg
            action = discord.AuditLogAction.emoji_delete
            embed.set_image(url=removed_emoji.url)
        elif added_emoji is not None:
            worth_updating = True
            new_emoji = f"{added_emoji} `{added_emoji}`"
            new_msg = _("{emoji} Added to the guild\n").format(emoji=new_emoji)
            msg += new_msg
            embed.description += new_msg
            action = discord.AuditLogAction.emoji_create
            embed.set_image(url=added_emoji.url)
        elif changed_emoji is not None:
            worth_updating = True
            emoji_name = f"{changed_emoji} `{changed_emoji}`"
            embed.set_image(url=changed_emoji.url)
            if old_emoji.name != changed_emoji.name:
                new_msg = _("{emoji} Renamed from {old_emoji_name} to {new_emoji_name}\n").format(
                    emoji=emoji_name,
                    old_emoji_name=old_emoji.name,
                    new_emoji_name=changed_emoji.name,
                )
                # emoji_update shows only for renames and not for role restriction updates
                action = discord.AuditLogAction.emoji_update
                msg += new_msg
                embed.description += new_msg
            if old_emoji.emoji != changed_emoji.emoji:
                new_msg = _(
                    "{emoji} emoji changed from {old_emoji_name} to {new_emoji_name}\n"
                ).format(
                    emoji=emoji_name,
                    old_emoji_name=old_emoji.emoji,
                    new_emoji_name=changed_emoji.emoji,
                )
                # emoji_update shows only for renames and not for role restriction updates
                action = discord.AuditLogAction.sticker_update
                msg += new_msg
                embed.description += new_msg
            if old_emoji.description != changed_emoji.description:
                new_msg = _(
                    "{emoji} emoji changed from {old_emoji_name} to {new_emoji_name}\n"
                ).format(
                    emoji=emoji_name,
                    old_emoji_name=old_emoji.emoji,
                    new_emoji_name=changed_emoji.emoji,
                )
                # emoji_update shows only for renames and not for role restriction updates
                action = discord.AuditLogAction.sticker_update
                msg += new_msg
                embed.description += new_msg

        perp = None
        reason = None
        if not worth_updating:
            return
        if channel.permissions_for(guild.me).view_audit_log:
            if action:
                entry = await self.get_audit_log_entry(guild, None, action)
                perp = getattr(entry, "user", None)
                reason = getattr(entry, "reason", None)
        if perp:
            embed.add_field(name=_("Updated by "), value=perp.mention)
            msg += _("Updated by ") + str(perp) + "\n"
        if reason:
            msg += _("Reason ") + reason + "\n"
            embed.add_field(name=_("Reason "), value=reason, inline=False)
        if embed_links:
            await channel.send(embed=embed, allowed_mentions=self.allowed_mentions)
        else:
            await channel.send(msg, allowed_mentions=self.allowed_mentions)
