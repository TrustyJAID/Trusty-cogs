import datetime
import discord
import asyncio
import logging

from discord.ext.commands.converter import Converter
from discord.ext.commands.errors import BadArgument

from redbot.core import commands, Config, modlog, VersionInfo, version_info
from redbot.core.bot import Red
from redbot.core.i18n import Translator, cog_i18n
from redbot.core.utils.chat_formatting import humanize_list, inline, escape

from typing import Union, cast, Sequence

_ = Translator("ExtendedModLog", __file__)
logger = logging.getLogger("red.trusty-cogs.ExtendedModLog")


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
            "commands_used",
            "invite_created",
            "invite_deleted",
        ]
        result = None
        if argument.lower() in options:
            result = argument.lower()
        if not result:
            raise BadArgument(_("`{arg}` is not an available event option.").format(arg=argument))
        return result


@cog_i18n(_)
class EventMixin:
    """
    Handles all the on_event data
    """

    def __init__(self, *args):
        self.config: Config
        self.bot: Red
        self.settings: dict

    async def get_colour(self, channel: discord.TextChannel) -> discord.Colour:
        try:
            if await self.bot.db.guild(channel.guild).use_bot_color():
                return channel.guild.me.colour
            else:
                return await self.bot.db.color()
        except AttributeError:
            return await self.bot.get_embed_colour(channel)

    async def get_event_colour(
        self, guild: discord.Guild, event_type: str, changed_object: Union[discord.Role] = None
    ) -> discord.Colour:
        if guild.text_channels:
            cmd_colour = await self.get_colour(guild.text_channels[0])
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
            "commands_used": cmd_colour,
            "invite_created": discord.Colour.blurple(),
            "invite_deleted": discord.Colour.blurple(),
        }
        colour = defaults[event_type]
        if self.settings[guild.id][event_type]["colour"] is not None:
            colour = discord.Colour(self.settings[guild.id][event_type]["colour"])
        return colour

    async def is_ignored_channel(self, guild: discord.Guild, channel: discord.abc.GuildChannel):
        ignored_channels = self.settings[guild.id]["ignored_channels"]
        if channel.id in ignored_channels:
            return True
        if channel.category and channel.category.id in ignored_channels:
            return True
        return False

    async def member_can_run(self, ctx: commands.Context) -> bool:
        """Check if a user can run a command.
        This will take the current context into account, such as the
        server and text channel.
        https://github.com/Cog-Creators/Red-DiscordBot/blob/V3/release/3.0.0/redbot/cogs/permissions/permissions.py
        """
        command = ctx.message.content.replace(ctx.prefix, "")
        com = ctx.bot.get_command(command)
        if com is None:
            return False
        else:
            try:
                testcontext = await ctx.bot.get_context(ctx.message, cls=commands.Context)
                to_check = [*reversed(com.parents)] + [com]
                can = False
                for cmd in to_check:
                    can = await cmd.can_run(testcontext)
                    if can is False:
                        break
            except commands.CheckFailure:
                can = False
        return can

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
        if version_info >= VersionInfo.from_str("3.4.0"):
            if await self.bot.cog_disabled_in_guild(self, ctx.guild):
                return
        if guild.id not in self.settings:
            return
        if not self.settings[guild.id]["commands_used"]["enabled"]:
            return
        if await self.is_ignored_channel(ctx.guild, ctx.channel):
            return
        try:
            channel = await self.modlog_channel(guild, "commands_used")
        except RuntimeError:
            return
        embed_links = (
            channel.permissions_for(guild.me).embed_links
            and self.settings[guild.id]["commands_used"]["embed"]
        )
        time = ctx.message.created_at
        message = ctx.message
        can_run = await self.member_can_run(ctx)
        command = ctx.message.content.replace(ctx.prefix, "")
        try:
            privs = self.bot.get_command(command).requires.privilege_level.name
        except Exception:
            return
        if privs not in self.settings[guild.id]["commands_used"]["privs"]:
            logger.debug(f"command not in list {privs}")
            return

        if privs == "MOD":
            try:
                mod_role_list = await ctx.bot.db.guild(guild).mod_role()
            except AttributeError:
                mod_role_list = await ctx.bot.get_mod_roles(guild)
            if mod_role_list != []:
                good_mod_roles = [guild.get_role(mr) for mr in mod_role_list]
                role = ", ".join(r.mention for r in good_mod_roles if r is not None) + f"\n{privs}"
            else:
                role = _("Not Set\nMOD")
        elif privs == "ADMIN":
            try:
                admin_role_list = await ctx.bot.db.guild(guild).admin_role()
            except AttributeError:
                admin_role_list = await ctx.bot.get_admin_roles(guild)
            if admin_role_list != []:
                good_admin_roles = [guild.get_role(ar) for ar in admin_role_list]
                role = (
                    ", ".join(r.mention for r in good_admin_roles if r is not None) + f"\n{privs}"
                )
            else:
                role = _("Not Set\nADMIN")
        elif privs == "BOT_OWNER":
            role = humanize_list([f"<@!{_id}>" for _id in ctx.bot.owner_ids])
            role += f"\n{privs}"
        elif privs == "GUILD_OWNER":
            role = guild.owner.mention + f"\n{privs}"
        else:
            role = f"everyone\n{privs}"

        infomessage = _(
            "{emoji} `{time}` {author}(`{a_id}`) used the following command in {channel}\n> {com}"
        ).format(
            emoji=self.settings[guild.id]["commands_used"]["emoji"],
            time=message.created_at.strftime("%H:%M:%S"),
            author=message.author,
            a_id=message.author.id,
            channel=message.channel.mention,
            com=message.content,
        )
        if embed_links:
            embed = discord.Embed(
                description=f"{ctx.author.mention} {message.content}",
                colour=await self.get_event_colour(guild, "commands_used"),
                timestamp=time,
            )
            embed.add_field(name=_("Channel"), value=message.channel.mention)
            embed.add_field(name=_("Can Run"), value=str(can_run))
            embed.add_field(name=_("Requires"), value=role)
            author_title = _("{member} ({m_id})- Used a Command").format(
                member=message.author, m_id=message.author.id
            )
            embed.set_author(name=author_title, icon_url=message.author.avatar_url)
            await channel.send(embed=embed)
        else:
            await channel.send(infomessage[:2000])

    @commands.Cog.listener(name="on_raw_message_delete")
    async def on_raw_message_delete_listener(
        self, payload: discord.RawMessageDeleteEvent, *, check_audit_log: bool = True
    ) -> None:
        # custom name of method used, because this is only supported in Red 3.1+
        guild_id = payload.guild_id
        if guild_id is None:
            return
        guild = self.bot.get_guild(guild_id)
        if guild.id not in self.settings:
            return
        if version_info >= VersionInfo.from_str("3.4.0"):
            if await self.bot.cog_disabled_in_guild(self, guild):
                return
        # settings = await self.config.guild(guild).message_delete()
        settings = self.settings[guild.id]["message_delete"]
        if not settings["enabled"]:
            return
        channel_id = payload.channel_id
        try:
            channel = await self.modlog_channel(guild, "message_delete")
        except RuntimeError:
            return
        if await self.is_ignored_channel(guild, guild.get_channel(channel_id)):
            return
        embed_links = (
            channel.permissions_for(guild.me).embed_links
            and self.settings[guild.id]["message_delete"]["embed"]
        )
        message = payload.cached_message
        if message is None:
            if settings["cached_only"]:
                return
            message_channel = guild.get_channel(channel_id)
            if embed_links:
                embed = discord.Embed(
                    description=_("*Message's content unknown.*"),
                    colour=await self.get_event_colour(guild, "message_delete"),
                )
                embed.add_field(name=_("Channel"), value=message_channel.mention)
                embed.set_author(name=_("Deleted Message"))
                await channel.send(embed=embed)
            else:
                infomessage = _("{emoji} `{time}` A message was deleted in {channel}").format(
                    emoji=settings["emoji"],
                    time=datetime.datetime.utcnow().strftime("%H:%M:%S"),
                    channel=message_channel.mention,
                )
                await channel.send(f"{infomessage}\n> *Message's content unknown.*")
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
        time = message.created_at
        perp = None
        if channel.permissions_for(guild.me).view_audit_log and check_audit_log:
            action = discord.AuditLogAction.message_delete
            async for log in guild.audit_logs(limit=2, action=action):
                same_chan = log.extra.channel.id == message.channel.id
                if log.target.id == message.author.id and same_chan:
                    perp = f"{log.user}({log.user.id})"
                    break
        message_channel = cast(discord.TextChannel, message.channel)
        author = message.author
        if perp is None:
            infomessage = _(
                "{emoji} `{time}` A message from **{author}** (`{a_id}`) was deleted in {channel}"
            ).format(
                emoji=settings["emoji"],
                time=time.strftime("%H:%M:%S"),
                author=author,
                channel=message_channel.mention,
                a_id=author.id,
            )
        else:
            infomessage = _(
                "{emoji} `{time}` {perp} deleted a message from "
                "**{author}** (`{a_id}`) in {channel}"
            ).format(
                emoji=settings["emoji"],
                time=time.strftime("%H:%M:%S"),
                perp=perp,
                author=author,
                a_id=author.id,
                channel=message_channel.mention,
            )
        if embed_links:
            embed = discord.Embed(
                description=f"{message.author.mention}: {message.content}",
                colour=await self.get_event_colour(guild, "message_delete"),
                timestamp=time,
            )

            embed.add_field(name=_("Channel"), value=message_channel.mention)
            if perp:
                embed.add_field(name=_("Deleted by"), value=perp)
            if message.attachments:
                files = ", ".join(a.filename for a in message.attachments)
                if len(message.attachments) > 1:
                    files = files[:-2]
                embed.add_field(name=_("Attachments"), value=files)
            embed.set_author(
                name=_("{member} ({m_id})- Deleted Message").format(member=author, m_id=author.id),
                icon_url=str(message.author.avatar_url),
            )
            await channel.send(embed=embed)
        else:
            clean_msg = escape(message.clean_content, mass_mentions=True)[
                : (1990 - len(infomessage))
            ]
            await channel.send(f"{infomessage}\n>>> {clean_msg}")

    @commands.Cog.listener()
    async def on_raw_bulk_message_delete(self, payload: discord.RawBulkMessageDeleteEvent):
        guild_id = payload.guild_id
        if guild_id is None:
            return
        guild = self.bot.get_guild(guild_id)
        if guild.id not in self.settings:
            return
        if version_info >= VersionInfo.from_str("3.4.0"):
            if await self.bot.cog_disabled_in_guild(self, guild):
                return
        settings = self.settings[guild.id]["message_delete"]
        if not settings["enabled"] or not settings["bulk_enabled"]:
            return
        channel_id = payload.channel_id
        message_channel = guild.get_channel(channel_id)
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
        message_amount = len(payload.message_ids)
        if embed_links:
            embed = discord.Embed(
                description=message_channel.mention,
                colour=await self.get_event_colour(guild, "message_delete"),
            )
            embed.set_author(name=_("Bulk message delete"), icon_url=guild.icon_url)
            embed.add_field(name=_("Channel"), value=message_channel.mention)
            embed.add_field(name=_("Messages deleted"), value=str(message_amount))
            await channel.send(embed=embed)
        else:
            infomessage = _(
                "{emoji} `{time}` Bulk message delete in {channel}, {amount} messages deleted."
            ).format(
                emoji=settings["emoji"],
                time=datetime.datetime.utcnow().strftime("%H:%M:%S"),
                amount=message_amount,
                channel=message_channel.mention,
            )
            await channel.send(infomessage)
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

    async def invite_links_loop(self) -> None:
        """Check every 5 minutes for updates to the invite links"""
        if version_info >= VersionInfo.from_str("3.2.0"):
            await self.bot.wait_until_red_ready()
        else:
            await self.bot.wait_until_ready()
        while self is self.bot.get_cog("ExtendedModLog"):
            for guild_id in self.settings:
                guild = self.bot.get_guild(guild_id)
                if guild is None:
                    continue
                if self.settings[guild_id]["user_join"]["enabled"]:
                    await self.save_invite_links(guild)
            await asyncio.sleep(300)

    async def save_invite_links(self, guild: discord.Guild) -> bool:
        invites = {}
        if not guild.me.guild_permissions.manage_guild:
            return False
        for invite in await guild.invites():
            try:

                created_at = getattr(invite, "created_at", datetime.datetime.utcnow())
                channel = getattr(invite, "channel", discord.Object(id=0))
                inviter = getattr(invite, "inviter", discord.Object(id=0))
                invites[invite.code] = {
                    "uses": getattr(invite, "uses", 0),
                    "max_age": getattr(invite, "max_age", None),
                    "created_at": created_at.timestamp(),
                    "max_uses": getattr(invite, "max_uses", None),
                    "temporary": getattr(invite, "temporary", False),
                    "inviter": getattr(inviter, "id", "Unknown"),
                    "channel": channel.id,
                }
            except Exception:
                logger.exception("Error saving invites.")
                pass
        await self.config.guild(guild).invite_links.set(invites)
        return True

    async def get_invite_link(self, guild: discord.Guild) -> str:
        manage_guild = guild.me.guild_permissions.manage_guild
        # invites = await self.config.guild(guild).invite_links()
        invites = self.settings[guild.id]["invite_links"]
        possible_link = ""
        check_logs = manage_guild and guild.me.guild_permissions.view_audit_log
        if manage_guild and "VANITY_URL" in guild.features:
            possible_link = str(await guild.vanity_invite())
        if invites and manage_guild:
            guild_invites = await guild.invites()
            for invite in guild_invites:
                if invite.code in invites:
                    uses = invites[invite.code]["uses"]
                    # logger.info(f"{invite.code}: {invite.uses} - {uses}")
                    if invite.uses > uses:
                        possible_link = _(
                            "https://discord.gg/{code}\nInvited by: {inviter}"
                        ).format(
                            code=invite.code,
                            inviter=str(getattr(invite, "inviter", _("Widget Integration"))),
                        )

            if not possible_link:
                for code, data in invites.items():
                    try:
                        invite = await self.bot.fetch_invite(code)
                    except (
                        discord.errors.NotFound,
                        discord.errors.HTTPException,
                        Exception,
                    ):
                        logger.error("Error getting invite {code}".format(code=code))
                        invite = None
                        pass
                    if not invite:
                        if (data["max_uses"] - data["uses"]) == 1:
                            # The invite link was on its last uses and subsequently
                            # deleted so we're fairly sure this was the one used
                            try:
                                inviter = await self.bot.fetch_user(data["inviter"])
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
            async for log in guild.audit_logs(action=action):
                if log.target.code not in invites:
                    possible_link = _("https://discord.gg/{code}\nInvited by: {inviter}").format(
                        code=log.target.code, inviter=str(log.target.inviter)
                    )
                    break
        return possible_link

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        guild = member.guild
        if guild.id not in self.settings:
            return
        if not self.settings[guild.id]["user_join"]["enabled"]:
            return
        # if not await self.config.guild(guild).user_join.enabled():
        # return
        if version_info >= VersionInfo.from_str("3.4.0"):
            if await self.bot.cog_disabled_in_guild(self, guild):
                return
        try:
            channel = await self.modlog_channel(guild, "user_join")
        except RuntimeError:
            return
        embed_links = (
            channel.permissions_for(guild.me).embed_links
            and self.settings[guild.id]["user_join"]["embed"]
        )
        time = datetime.datetime.utcnow()
        users = len(guild.members)
        # https://github.com/Cog-Creators/Red-DiscordBot/blob/develop/cogs/general.py
        since_created = (time - member.created_at).days
        user_created = member.created_at.strftime("%d %b %Y %H:%M")

        created_on = "{}\n({} days ago)".format(user_created, since_created)

        possible_link = await self.get_invite_link(guild)
        if embed_links:
            embed = discord.Embed(
                description=member.mention,
                colour=await self.get_event_colour(guild, "user_join"),
                timestamp=member.joined_at if member.joined_at else datetime.datetime.utcnow(),
            )
            embed.add_field(name=_("Total Users:"), value=str(users))
            embed.add_field(name=_("Account created on:"), value=created_on)
            embed.set_author(
                name=_("{member} ({m_id}) has joined the guild").format(
                    member=member, m_id=member.id
                ),
                url=member.avatar_url,
                icon_url=member.avatar_url,
            )
            if possible_link:
                embed.add_field(name=_("Invite Link"), value=possible_link)
            embed.set_thumbnail(url=member.avatar_url)
            await channel.send(embed=embed)
        else:
            time = datetime.datetime.utcnow()
            msg = _(
                "{emoji} `{time}` **{member}**(`{m_id}`) "
                "joined the guild. Total members: {users}"
            ).format(
                emoji=self.settings[guild.id]["user_join"]["emoji"],
                time=time.strftime("%H:%M:%S"),
                member=member,
                m_id=member.id,
                users=users,
            )
            await channel.send(msg)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        guild = member.guild
        if guild.id not in self.settings:
            return
        if not self.settings[guild.id]["user_left"]["enabled"]:
            return
        if version_info >= VersionInfo.from_str("3.4.0"):
            if await self.bot.cog_disabled_in_guild(self, guild):
                return
        try:
            channel = await self.modlog_channel(guild, "user_left")
        except RuntimeError:
            return
        embed_links = (
            channel.permissions_for(guild.me).embed_links
            and self.settings[guild.id]["user_left"]["embed"]
        )
        time = datetime.datetime.utcnow()
        check_after = time + datetime.timedelta(minutes=-30)
        perp = None
        reason = None
        if channel.permissions_for(guild.me).view_audit_log:
            action = discord.AuditLogAction.kick
            async for log in guild.audit_logs(limit=5, after=check_after, action=action):
                if log.target.id == member.id:
                    perp = log.user
                    reason = log.reason
                    break
        if embed_links:
            embed = discord.Embed(
                description=member.mention,
                colour=await self.get_event_colour(guild, "user_left"),
                timestamp=time,
            )
            embed.add_field(name=_("Total Users:"), value=str(len(guild.members)))
            if perp:
                embed.add_field(name=_("Kicked"), value=perp.mention)
            if reason:
                embed.add_field(name=_("Reason"), value=str(reason), inline=False)
            embed.set_author(
                name=_("{member} ({m_id}) has left the guild").format(
                    member=member, m_id=member.id
                ),
                url=member.avatar_url,
                icon_url=member.avatar_url,
            )
            embed.set_thumbnail(url=member.avatar_url)
            await channel.send(embed=embed)
        else:
            time = datetime.datetime.utcnow()
            msg = _(
                "{emoji} `{time}` **{member}**(`{m_id}`) left the guild. Total members: {users}"
            ).format(
                emoji=self.settings[guild.id]["user_left"]["emoji"],
                time=time.strftime("%H:%M:%S"),
                member=member,
                m_id=member.id,
                users=len(guild.members),
            )
            if perp:
                msg = _(
                    "{emoji} `{time}` **{member}**(`{m_id}`) "
                    "was kicked by {perp}. Total members: {users}"
                ).format(
                    emoji=self.settings[guild.id]["user_left"]["emoji"],
                    time=time.strftime("%H:%M:%S"),
                    member=member,
                    m_id=member.id,
                    perp=perp,
                    users=len(guild.members),
                )
            await channel.send(msg)

    async def get_permission_change(
        self, before: discord.abc.GuildChannel, after: discord.abc.GuildChannel, embed_links: bool
    ) -> str:
        p_msg = ""
        before_perms = {}
        after_perms = {}
        for o, p in before.overwrites.items():
            before_perms[str(o.id)] = [i for i in p]
        for o, p in after.overwrites.items():
            after_perms[str(o.id)] = [i for i in p]
        for entity in before_perms:
            entity_obj = before.guild.get_role(int(entity))
            if not entity_obj:
                entity_obj = before.guild.get_member(int(entity))
            if entity not in after_perms:
                if not embed_links:
                    p_msg += f"{entity_obj.name} Overwrites removed.\n"
                else:
                    p_msg += f"{entity_obj.mention} Overwrites removed.\n"
                continue
            if after_perms[entity] != before_perms[entity]:
                a = set(after_perms[entity])
                b = set(before_perms[entity])
                a_perms = list(a - b)
                for diff in a_perms:
                    if not embed_links:
                        p_msg += f"{entity_obj.name} {diff[0]} Set to {diff[1]}\n"
                    else:
                        p_msg += f"{entity_obj.mention} {diff[0]} Set to {diff[1]}\n"
        for entity in after_perms:
            entity_obj = after.guild.get_role(int(entity))
            if not entity_obj:
                entity_obj = after.guild.get_member(int(entity))
            if entity not in before_perms:
                if not embed_links:
                    p_msg += f"{entity_obj.name} Overwrites added.\n"
                else:
                    p_msg += f"{entity_obj.mention} Overwrites added.\n"
                continue
        return p_msg

    @commands.Cog.listener()
    async def on_guild_channel_create(self, new_channel: discord.abc.GuildChannel) -> None:
        guild = new_channel.guild
        if guild.id not in self.settings:
            return
        if not self.settings[guild.id]["channel_create"]["enabled"]:
            return
        if version_info >= VersionInfo.from_str("3.4.0"):
            if await self.bot.cog_disabled_in_guild(self, guild):
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
        time = datetime.datetime.utcnow()
        channel_type = str(new_channel.type).title()
        embed = discord.Embed(
            description=f"{new_channel.mention} {new_channel.name}",
            timestamp=time,
            colour=await self.get_event_colour(guild, "channel_create"),
        )
        embed.set_author(
            name=_("{chan_type} Channel Created {chan_name} ({chan_id})").format(
                chan_type=channel_type, chan_name=new_channel.name, chan_id=new_channel.id
            )
        )
        # msg = _("Channel Created ") + str(new_channel.id) + "\n"
        perp = None
        reason = None
        if channel.permissions_for(guild.me).view_audit_log:
            action = discord.AuditLogAction.channel_create
            async for log in guild.audit_logs(limit=2, action=action):
                if log.target.id == new_channel.id:
                    perp = log.user
                    if log.reason:
                        reason = log.reason
                    break

        perp_msg = ""
        embed.add_field(name=_("Type"), value=channel_type)
        if perp:
            perp_msg = _("by {perp} (`{perp_id}`)").format(perp=perp, perp_id=perp.id)
            embed.add_field(name=_("Created by "), value=perp.mention)
        if reason:
            perp_msg += _(" Reason: {reason}").format(reason=reason)
            embed.add_field(name=_("Reason "), value=reason, inline=False)
        msg = _("{emoji} `{time}` {chan_type} channel created {perp_msg} {channel}").format(
            emoji=self.settings[guild.id]["channel_create"]["emoji"],
            time=time.strftime("%H:%M:%S"),
            chan_type=channel_type,
            perp_msg=perp_msg,
            channel=new_channel.mention,
        )
        if embed_links:
            await channel.send(embed=embed)
        else:
            await channel.send(msg)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, old_channel: discord.abc.GuildChannel):
        guild = old_channel.guild
        if guild.id not in self.settings:
            return
        if not self.settings[guild.id]["channel_delete"]["enabled"]:
            return
        if version_info >= VersionInfo.from_str("3.4.0"):
            if await self.bot.cog_disabled_in_guild(self, guild):
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
        channel_type = str(old_channel.type).title()
        time = datetime.datetime.utcnow()
        embed = discord.Embed(
            description=old_channel.name,
            timestamp=time,
            colour=await self.get_event_colour(guild, "channel_delete"),
        )
        embed.set_author(
            name=_("{chan_type} Channel Deleted {chan_name} ({chan_id})").format(
                chan_type=channel_type, chan_name=old_channel.name, chan_id=old_channel.id
            )
        )
        perp = None
        reason = None
        if channel.permissions_for(guild.me).view_audit_log:
            action = discord.AuditLogAction.channel_delete
            async for log in guild.audit_logs(limit=2, action=action):
                if log.target.id == old_channel.id:
                    perp = log.user
                    if log.reason:
                        reason = log.reason
                    break
        perp_msg = ""
        embed.add_field(name=_("Type"), value=channel_type)
        if perp:
            perp_msg = _("by {perp} (`{perp_id}`)").format(perp=perp, perp_id=perp.id)
            embed.add_field(name=_("Deleted by "), value=perp.mention)
        if reason:
            perp_msg += _(" Reason: {reason}").format(reason=reason)
            embed.add_field(name=_("Reason "), value=reason, inline=False)
        msg = _("{emoji} `{time}` {chan_type} channel deleted {perp_msg} {channel}").format(
            emoji=self.settings[guild.id]["channel_delete"]["emoji"],
            time=time.strftime("%H:%M:%S"),
            chan_type=channel_type,
            perp_msg=perp_msg,
            channel=f"#{old_channel.name} ({old_channel.id})",
        )
        if embed_links:
            await channel.send(embed=embed)
        else:
            await channel.send(msg)

    @commands.Cog.listener()
    async def on_guild_channel_update(
        self, before: discord.abc.GuildChannel, after: discord.abc.GuildChannel
    ) -> None:
        guild = before.guild
        if guild.id not in self.settings:
            return
        if version_info >= VersionInfo.from_str("3.4.0"):
            if await self.bot.cog_disabled_in_guild(self, guild):
                return
        if not self.settings[guild.id]["channel_change"]["enabled"]:
            return
        if await self.is_ignored_channel(guild, message_channel):
            return
        try:
            channel = await self.modlog_channel(guild, "channel_change")
        except RuntimeError:
            return
        embed_links = (
            channel.permissions_for(guild.me).embed_links
            and self.settings[guild.id]["channel_change"]["embed"]
        )
        channel_type = str(after.type).title()
        time = datetime.datetime.utcnow()
        embed = discord.Embed(
            description=after.mention,
            timestamp=time,
            colour=await self.get_event_colour(guild, "channel_create"),
        )
        embed.set_author(
            name=_("{chan_type} Channel Updated {chan_name} ({chan_id})").format(
                chan_type=channel_type, chan_name=before.name, chan_id=before.id
            )
        )
        msg = _("{emoji} `{time}` Updated channel {channel}\n").format(
            emoji=self.settings[guild.id]["channel_change"]["emoji"],
            time=time.strftime("%H:%M:%S"),
            channel=before.name,
        )
        perp = None
        reason = None
        worth_updating = False
        if channel.permissions_for(guild.me).view_audit_log:
            action = discord.AuditLogAction.channel_update
            async for log in guild.audit_logs(limit=5, action=action):
                if log.target.id == before.id:
                    perp = log.user
                    if log.reason:
                        reason = log.reason
                    break
        if type(before) == discord.TextChannel:
            text_updates = {
                "name": _("Name:"),
                "topic": _("Topic:"),
                "category": _("Category:"),
                "slowmode_delay": _("Slowmode delay:"),
            }

            for attr, name in text_updates.items():
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
                    embed.add_field(name=_("Before ") + name, value=str(before_attr)[:1024])
                    embed.add_field(name=_("After ") + name, value=str(after_attr)[:1024])
            if before.is_nsfw() != after.is_nsfw():
                worth_updating = True
                msg += _("Before ") + f"NSFW {before.is_nsfw()}\n"
                msg += _("After ") + f"NSFW {after.is_nsfw()}\n"
                embed.add_field(name=_("Before ") + "NSFW", value=str(before.is_nsfw()))
                embed.add_field(name=_("After ") + "NSFW", value=str(after.is_nsfw()))
            p_msg = await self.get_permission_change(before, after, embed_links)
            if p_msg != "":
                worth_updating = True
                msg += _("Permissions Changed: ") + p_msg
                embed.add_field(name=_("Permissions"), value=p_msg[:1024])

        if type(before) == discord.VoiceChannel:
            voice_updates = {
                "name": _("Name:"),
                "position": _("Position:"),
                "category": _("Category:"),
                "bitrate": _("Bitrate:"),
                "user_limit": _("User limit:"),
            }
            for attr, name in voice_updates.items():
                before_attr = getattr(before, attr)
                after_attr = getattr(after, attr)
                if before_attr != after_attr:
                    worth_updating = True
                    msg += _("Before ") + f"{name} {before_attr}\n"
                    msg += _("After ") + f"{name} {after_attr}\n"
                    embed.add_field(name=_("Before ") + name, value=str(before_attr))
                    embed.add_field(name=_("After ") + name, value=str(after_attr))
            p_msg = await self.get_permission_change(before, after, embed_links)
            if p_msg != "":
                worth_updating = True
                msg += _("Permissions Changed: ") + p_msg
                embed.add_field(name=_("Permissions"), value=p_msg[:1024])

        if perp:
            msg += _("Updated by ") + str(perp) + "\n"
            embed.add_field(name=_("Updated by "), value=perp.mention)
        if reason:
            msg += _("Reason ") + reason + "\n"
            embed.add_field(name=_("Reason "), value=reason, inline=False)
        if not worth_updating:
            return
        if embed_links:
            await channel.send(embed=embed)
        else:
            await channel.send(escape(msg, mass_mentions=True))

    async def get_role_permission_change(self, before: discord.Role, after: discord.Role) -> str:
        permission_list = [
            "create_instant_invite",
            "kick_members",
            "ban_members",
            "administrator",
            "manage_channels",
            "manage_guild",
            "add_reactions",
            "view_audit_log",
            "priority_speaker",
            "read_messages",
            "send_messages",
            "send_tts_messages",
            "manage_messages",
            "embed_links",
            "attach_files",
            "read_message_history",
            "mention_everyone",
            "external_emojis",
            "connect",
            "speak",
            "mute_members",
            "deafen_members",
            "move_members",
            "use_voice_activation",
            "change_nickname",
            "manage_nicknames",
            "manage_roles",
            "manage_webhooks",
            "manage_emojis",
        ]
        p_msg = ""
        for p in permission_list:
            if getattr(before.permissions, p) != getattr(after.permissions, p):
                change = getattr(after.permissions, p)
                p_msg += f"{p} Set to {change}\n"
        return p_msg

    @commands.Cog.listener()
    async def on_guild_role_update(self, before: discord.Role, after: discord.Role) -> None:
        guild = before.guild
        if guild.id not in self.settings:
            return
        if version_info >= VersionInfo.from_str("3.4.0"):
            if await self.bot.cog_disabled_in_guild(self, guild):
                return
        if not self.settings[guild.id]["role_change"]["enabled"]:
            return
        try:
            channel = await self.modlog_channel(guild, "role_change")
        except RuntimeError:
            return
        perp = None
        reason = None
        if channel.permissions_for(guild.me).view_audit_log:
            action = discord.AuditLogAction.role_update
            async for log in guild.audit_logs(limit=5, action=action):
                if log.target.id == before.id:
                    perp = log.user
                    if log.reason:
                        reason = log.reason
                    break
        embed_links = (
            channel.permissions_for(guild.me).embed_links
            and self.settings[guild.id]["role_change"]["embed"]
        )
        time = datetime.datetime.utcnow()
        embed = discord.Embed(description=after.mention, colour=after.colour, timestamp=time)
        msg = _("{emoji} `{time}` Updated role **{role}**\n").format(
            emoji=self.settings[guild.id]["role_change"]["emoji"],
            time=time.strftime("%H:%M:%S"),
            role=before.name,
        )
        if after is guild.default_role:
            embed.set_author(name=_("Updated @everyone role "))
        else:
            embed.set_author(
                name=_("Updated {role} ({r_id}) role ").format(role=before.name, r_id=before.id)
            )
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
        p_msg = await self.get_role_permission_change(before, after)
        if p_msg != "":
            worth_updating = True
            msg += _("Permissions Changed: ") + p_msg
            embed.add_field(name=_("Permissions"), value=p_msg[:1024])
        if not worth_updating:
            return
        if embed_links:
            await channel.send(embed=embed)
        else:
            await channel.send(msg)

    @commands.Cog.listener()
    async def on_guild_role_create(self, role: discord.Role) -> None:
        guild = role.guild
        if guild.id not in self.settings:
            return
        if version_info >= VersionInfo.from_str("3.4.0"):
            if await self.bot.cog_disabled_in_guild(self, guild):
                return
        if not self.settings[guild.id]["role_create"]["enabled"]:
            return
        try:
            channel = await self.modlog_channel(guild, "role_change")
        except RuntimeError:
            return
        perp = None
        reason = None
        if channel.permissions_for(guild.me).view_audit_log:
            action = discord.AuditLogAction.role_create
            async for log in guild.audit_logs(limit=5, action=action):
                if log.target.id == role.id:
                    perp = log.user
                    if log.reason:
                        reason = log.reason
                    break
        embed_links = (
            channel.permissions_for(guild.me).embed_links
            and self.settings[guild.id]["role_create"]["embed"]
        )
        time = datetime.datetime.utcnow()
        embed = discord.Embed(
            description=role.mention,
            colour=await self.get_event_colour(guild, "role_create"),
            timestamp=time,
        )
        embed.set_author(
            name=_("Role created {role} ({r_id})").format(role=role.name, r_id=role.id)
        )
        msg = _("{emoji} `{time}` Role created {role}\n").format(
            emoji=self.settings[guild.id]["role_create"]["emoji"],
            time=time.strftime("%H:%M:%S"),
            role=role.name,
        )
        if perp:
            embed.add_field(name=_("Created by"), value=perp.mention)
            msg += _("By ") + str(perp) + "\n"
        if reason:
            msg += _("Reason ") + reason + "\n"
            embed.add_field(name=_("Reason "), value=reason, inline=False)
        if embed_links:
            await channel.send(embed=embed)
        else:
            await channel.send(escape(msg, mass_mentions=True))

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role) -> None:
        guild = role.guild
        if guild.id not in self.settings:
            return
        if version_info >= VersionInfo.from_str("3.4.0"):
            if await self.bot.cog_disabled_in_guild(self, guild):
                return
        if not self.settings[guild.id]["role_delete"]["enabled"]:
            return
        try:
            channel = await self.modlog_channel(guild, "role_change")
        except RuntimeError:
            return
        perp = None
        reason = None
        if channel.permissions_for(guild.me).view_audit_log:
            action = discord.AuditLogAction.role_delete
            async for log in guild.audit_logs(limit=5, action=action):
                if log.target.id == role.id:
                    perp = log.user
                    if log.reason:
                        reason = log.reason
                    break
        embed_links = (
            channel.permissions_for(guild.me).embed_links
            and self.settings[guild.id]["role_delete"]["embed"]
        )
        time = datetime.datetime.utcnow()
        embed = discord.Embed(
            description=role.name,
            timestamp=time,
            colour=await self.get_event_colour(guild, "role_delete"),
        )
        embed.set_author(
            name=_("Role deleted {role} ({r_id})").format(role=role.name, r_id=role.id)
        )
        msg = _("{emoji} `{time}` Role deleted **{role}**\n").format(
            emoji=self.settings[guild.id]["role_create"]["emoji"],
            time=time.strftime("%H:%M:%S"),
            role=role.name,
        )
        if perp:
            embed.add_field(name=_("Deleted by"), value=perp.mention)
            msg += _("By ") + str(perp) + "\n"
        if reason:
            msg += _("Reason ") + reason + "\n"
            embed.add_field(name=_("Reason "), value=reason, inline=False)
        if embed_links:
            await channel.send(embed=embed)
        else:
            await channel.send(escape(msg, mass_mentions=True))

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message) -> None:
        guild = before.guild
        if guild is None:
            return
        if guild.id not in self.settings:
            return
        if version_info >= VersionInfo.from_str("3.4.0"):
            if await self.bot.cog_disabled_in_guild(self, guild):
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
        time = datetime.datetime.utcnow()
        fmt = "%H:%M:%S"
        if embed_links:
            embed = discord.Embed(
                description=f"{before.author.mention}: {before.content}",
                colour=await self.get_event_colour(guild, "message_edit"),
                timestamp=before.created_at,
            )
            jump_url = f"[Click to see new message]({after.jump_url})"
            embed.add_field(name=_("After Message:"), value=jump_url)
            embed.add_field(name=_("Channel:"), value=before.channel.mention)
            embed.set_author(
                name=_("{member} ({m_id}) - Edited Message").format(
                    member=before.author, m_id=before.author.id
                ),
                icon_url=str(before.author.avatar_url),
            )
            await channel.send(embed=embed)
        else:
            msg = _(
                "{emoji} `{time}` **{author}** (`{a_id}`) edited a message "
                "in {channel}.\nBefore:\n> {before}\nAfter:\n> {after}"
            ).format(
                emoji=self.settings[guild.id]["message_edit"]["emoji"],
                time=time.strftime(fmt),
                author=before.author,
                a_id=before.author.id,
                channel=before.channel.mention,
                before=escape(before.content, mass_mentions=True),
                after=escape(after.content, mass_mentions=True),
            )
            await channel.send(msg[:2000])

    @commands.Cog.listener()
    async def on_guild_update(self, before: discord.Guild, after: discord.Guild) -> None:
        guild = after
        if guild.id not in self.settings:
            return
        if version_info >= VersionInfo.from_str("3.4.0"):
            if await self.bot.cog_disabled_in_guild(self, guild):
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
        time = datetime.datetime.utcnow()
        embed = discord.Embed(
            timestamp=time, colour=await self.get_event_colour(guild, "guild_change")
        )
        embed.set_author(name=_("Updated Guild"), icon_url=str(guild.icon_url))
        embed.set_thumbnail(url=str(guild.icon_url))
        msg = _("{emoji} `{time}` Guild updated\n").format(
            emoji=self.settings[guild.id]["guild_change"]["emoji"],
            time=time.strftime("%H:%M:%S"),
        )
        guild_updates = {
            "name": _("Name:"),
            "region": _("Region:"),
            "afk_timeout": _("AFK Timeout:"),
            "afk_channel": _("AFK Channel:"),
            "icon_url": _("Server Icon:"),
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
                msg += _("Before ") + f"{name} {before_attr}\n"
                msg += _("After ") + f"{name} {after_attr}\n"
                embed.add_field(name=_("Before ") + name, value=str(before_attr))
                embed.add_field(name=_("After ") + name, value=str(after_attr))
        if not worth_updating:
            return
        perps = []
        reasons = []
        if channel.permissions_for(guild.me).view_audit_log:
            action = discord.AuditLogAction.guild_update
            async for log in guild.audit_logs(limit=int(len(embed.fields) / 2), action=action):
                perps.append(log.user)
                if log.reason:
                    reasons.append(log.reason)
        if perps:
            perp_s = ", ".join(str(p) for p in perps)
            msg += _("Update by ") + f"{perp_s}\n"
            perp_m = ", ".join(p.mention for p in perps)
            embed.add_field(name=_("Updated by"), value=perp_m)
        if reasons:
            s_reasons = ", ".join(str(r) for r in reasons)
            msg += _("Reasons ") + f"{reasons}\n"
            embed.add_field(name=_("Reasons "), value=s_reasons, inline=False)
        if embed_links:
            await channel.send(embed=embed)
        else:
            await channel.send(msg)

    @commands.Cog.listener()
    async def on_guild_emojis_update(
        self, guild: discord.Guild, before: Sequence[discord.Emoji], after: Sequence[discord.Emoji]
    ) -> None:
        if guild.id not in self.settings:
            return
        if version_info >= VersionInfo.from_str("3.4.0"):
            if await self.bot.cog_disabled_in_guild(self, guild):
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
        perp = None

        time = datetime.datetime.utcnow()
        embed = discord.Embed(
            description="",
            timestamp=time,
            colour=await self.get_event_colour(guild, "emoji_change"),
        )
        embed.set_author(name=_("Updated Server Emojis"))
        msg = _("{emoji} `{time}` Updated Server Emojis").format(
            emoji=self.settings[guild.id]["emoji_change"]["emoji"], time=time.strftime("%H:%M:%S")
        )
        worth_updating = False
        b = set(before)
        a = set(after)
        # discord.Emoji uses id for hashing so we use set difference to get added/removed emoji
        try:
            added_emoji = (a - b).pop()
        except KeyError:
            added_emoji = None
        try:
            removed_emoji = (b - a).pop()
        except KeyError:
            removed_emoji = None
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
            new_msg = f"`{removed_emoji}` (ID: {removed_emoji.id})" + _(
                " Removed from the guild\n"
            )
            msg += new_msg
            embed.description += new_msg
            action = discord.AuditLogAction.emoji_delete
        elif added_emoji is not None:
            worth_updating = True
            new_msg = f"{added_emoji} `{added_emoji}`" + _(" Added to the guild\n")
            msg += new_msg
            embed.description += new_msg
            action = discord.AuditLogAction.emoji_create
        elif changed_emoji is not None:
            worth_updating = True
            new_msg = f"{changed_emoji} `{changed_emoji}`"
            if old_emoji.name != changed_emoji.name:
                new_msg += (
                    _(" Renamed from ") + old_emoji.name + _(" to ") + f"{changed_emoji.name}\n"
                )
                # emoji_update shows only for renames and not for role restriction updates
                action = discord.AuditLogAction.emoji_update
            msg += new_msg
            embed.description += new_msg
            if old_emoji.roles != changed_emoji.roles:
                worth_updating = True
                if not changed_emoji.roles:
                    new_msg = _(" Changed to unrestricted.\n")
                    msg += new_msg
                    embed.description += new_msg
                elif not old_emoji.roles:
                    msg += (
                        _(" Restricted to roles: ")
                        + humanize_list(
                            [f"{role.name} ({role.id})" for role in changed_emoji.roles]
                        )
                        + "\n"
                    )
                    embed.description += _(" Restricted to roles: ") + humanize_list(
                        [role.mention for role in changed_emoji.roles]
                    )
                else:
                    msg += (
                        _(" Role restriction changed from ")
                        + humanize_list([f"{role.name} ({role.id})" for role in old_emoji.roles])
                        + _(" to ")
                        + humanize_list(
                            [f"{role.name} ({role.id})" for role in changed_emoji.roles]
                        )
                        + "\n"
                    )
                    embed.description += (
                        _(" Role restriction changed from ")
                        + humanize_list([role.mention for role in old_emoji.roles])
                        + _(" to ")
                        + humanize_list([role.mention for role in changed_emoji.roles])
                    )
        perp = None
        reason = None
        if not worth_updating:
            return
        if channel.permissions_for(guild.me).view_audit_log:
            if action:
                async for log in guild.audit_logs(limit=1, action=action):
                    perp = log.user
                    if log.reason:
                        reason = log.reason
                    break
        if perp:
            embed.add_field(name=_("Updated by "), value=perp.mention)
            msg += _("Updated by ") + str(perp) + "\n"
        if reason:
            msg += _("Reason ") + reason + "\n"
            embed.add_field(name=_("Reason "), value=reason, inline=False)
        if embed_links:
            await channel.send(embed=embed)
        else:
            await channel.send(msg)

    @commands.Cog.listener()
    async def on_voice_state_update(
        self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState
    ) -> None:
        guild = member.guild
        if guild.id not in self.settings:
            return
        if version_info >= VersionInfo.from_str("3.4.0"):
            if await self.bot.cog_disabled_in_guild(self, guild):
                return
        if not self.settings[guild.id]["voice_change"]["enabled"]:
            return
        if member.bot:
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
        time = datetime.datetime.utcnow()
        embed = discord.Embed(
            timestamp=time,
            colour=await self.get_event_colour(guild, "voice_change"),
        )
        msg = _("{emoji} `{time}` Updated Voice State for **{member}** (`{m_id}`)").format(
            emoji=self.settings[guild.id]["voice_change"]["emoji"],
            time=time.strftime("%H:%M:%S"),
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
                chan_msg = member.mention + _(" was deafened. ")
                msg += chan_msg + "\n"
                embed.description = chan_msg
            else:
                chan_msg = member.mention + _(" was undeafened. ")
                msg += chan_msg + "\n"
                embed.description = chan_msg
        if before.mute != after.mute:
            worth_updating = True
            change_type = "mute"
            if after.mute:
                chan_msg = member.mention + _(" was muted. ")
                msg += chan_msg + "\n"
                embed.description = chan_msg
            else:
                chan_msg = member.mention + _(" was unmuted. ")
                msg += chan_msg + "\n"
                embed.description = chan_msg
        if before.channel != after.channel:
            worth_updating = True
            change_type = "channel"
            if before.channel is None:
                chan_msg = member.mention + _(" has joined ") + inline(after.channel.name)
                msg += chan_msg + "\n"
                embed.description = chan_msg
            elif after.channel is None:
                chan_msg = member.mention + _(" has left ") + inline(before.channel.name)
                msg += chan_msg + "\n"
                embed.description = chan_msg
            else:
                chan_msg = (
                    member.mention
                    + _(" has moved from ")
                    + inline(before.channel.name)
                    + _(" to ")
                    + inline(after.channel.name)
                )
                msg += chan_msg
                embed.description = chan_msg
        if not worth_updating:
            return
        perp = None
        reason = None
        if channel.permissions_for(guild.me).view_audit_log and change_type:
            action = discord.AuditLogAction.member_update
            async for log in guild.audit_logs(limit=5, action=action):
                is_change = getattr(log.after, change_type, None)
                if log.target.id == member.id and is_change:
                    perp = log.user
                    if log.reason:
                        reason = log.reason
                    break
        if perp:
            embed.add_field(name=_("Updated by"), value=perp.mention)
        if reason:
            msg += _("Reason ") + reason + "\n"
            embed.add_field(name=_("Reason "), value=reason, inline=False)
        if embed_links:
            await channel.send(embed=embed)
        else:
            await channel.send(escape(msg, mass_mentions=True))

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member) -> None:
        guild = before.guild
        if guild.id not in self.settings:
            return
        if version_info >= VersionInfo.from_str("3.4.0"):
            if await self.bot.cog_disabled_in_guild(self, guild):
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
        time = datetime.datetime.utcnow()
        embed = discord.Embed(
            timestamp=time, colour=await self.get_event_colour(guild, "user_change")
        )
        msg = _("{emoji} `{time}` Member updated **{member}** (`{m_id}`)\n").format(
            emoji=self.settings[guild.id]["user_change"]["emoji"],
            time=time.strftime("%H:%M:%S"),
            member=before,
            m_id=before.id,
        )
        emb_msg = _("{member} ({m_id}) updated").format(member=before, m_id=before.id)
        embed.set_author(name=emb_msg, icon_url=before.avatar_url)
        member_updates = {"nick": _("Nickname:"), "roles": _("Roles:")}
        perp = None
        reason = None
        worth_sending = False
        for attr, name in member_updates.items():
            if attr == "nick" and not self.settings[guild.id]["user_change"]["nicknames"]:
                continue
            before_attr = getattr(before, attr)
            after_attr = getattr(after, attr)
            if before_attr != after_attr:
                if attr == "roles":
                    b = set(before.roles)
                    a = set(after.roles)
                    before_roles = list(b - a)
                    after_roles = list(a - b)
                    if before_roles:
                        for role in before_roles:
                            msg += _("{author} had the {role} role removed.").format(
                                author=after.name, role=role.name
                            )
                            embed.description = _("{author} had the {role} role removed.").format(
                                author=after.mention, role=role.mention
                            )
                            worth_sending = True
                    if after_roles:
                        for role in after_roles:
                            msg += _("{author} had the {role} role applied.").format(
                                author=after.name, role=role.name
                            )
                            embed.description = _("{author} had the {role} role applied.").format(
                                author=after.mention, role=role.mention
                            )
                            worth_sending = True
                    if channel.permissions_for(guild.me).view_audit_log:
                        action = discord.AuditLogAction.member_role_update
                        async for log in guild.audit_logs(limit=5, action=action):
                            if log.target.id == before.id:
                                perp = log.user
                                if log.reason:
                                    reason = log.reason
                                break
                else:
                    if channel.permissions_for(guild.me).view_audit_log:
                        action = discord.AuditLogAction.member_update
                        async for log in guild.audit_logs(limit=5, action=action):
                            if log.target.id == before.id:
                                perp = log.user
                                if log.reason:
                                    reason = log.reason
                                break
                    worth_sending = True
                    msg += _("Before ") + f"{name} {before_attr}\n"
                    msg += _("After ") + f"{name} {after_attr}\n"
                    embed.description = _("{author} changed their nickname.").format(
                        author=after.mention
                    )
                    embed.add_field(name=_("Before ") + name, value=str(before_attr)[:1024])
                    embed.add_field(name=_("After ") + name, value=str(after_attr)[:1024])
        if not worth_sending:
            return
        if perp:
            msg += _("Updated by ") + f"{perp}\n"
            embed.add_field(name=_("Updated by "), value=perp.mention)
        if reason:
            msg += _("Reason: ") + f"{reason}\n"
            embed.add_field(name=_("Reason"), value=reason, inline=False)
        if embed_links:
            await channel.send(embed=embed)
        else:
            await channel.send(msg)

    @commands.Cog.listener()
    async def on_invite_create(self, invite: discord.Invite) -> None:
        """
        New in discord.py 1.3
        """
        guild = invite.guild
        if guild.id not in self.settings:
            return
        if version_info >= VersionInfo.from_str("3.4.0"):
            if await self.bot.cog_disabled_in_guild(self, guild):
                return
        if invite.code not in self.settings[guild.id]["invite_links"]:
            created_at = getattr(invite, "created_at", datetime.datetime.utcnow())
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
            await self.config.guild(guild).invite_links.set(
                self.settings[guild.id]["invite_links"]
            )
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
        invite_attrs = {
            "code": _("Code:"),
            "inviter": _("Inviter:"),
            "channel": _("Channel:"),
            "max_uses": _("Max Uses:"),
        }
        try:
            invite_time = invite.created_at.strftime("%H:%M:%S")
        except AttributeError:
            invite_time = datetime.datetime.utcnow().strftime("%H:%M:%S")
        msg = _("{emoji} `{time}` Invite created ").format(
            emoji=self.settings[guild.id]["invite_created"]["emoji"],
            time=invite_time,
        )
        embed = discord.Embed(
            title=_("Invite Created"), colour=await self.get_event_colour(guild, "invite_created")
        )
        worth_updating = False
        if getattr(invite, "inviter", None):
            embed.description = _("{author} created an invite for {channel}.").format(
                author=invite.inviter.mention, channel=invite.channel.mention
            )
        for attr, name in invite_attrs.items():
            before_attr = getattr(invite, attr)
            if before_attr:
                worth_updating = True
                msg += f"{name} {before_attr}\n"
                embed.add_field(name=name, value=str(before_attr))
        if not worth_updating:
            return
        if embed_links:
            await channel.send(embed=embed)
        else:
            await channel.send(escape(msg, mass_mentions=True))

    @commands.Cog.listener()
    async def on_invite_delete(self, invite: discord.Invite) -> None:
        """
        New in discord.py 1.3
        """
        guild = invite.guild
        if guild.id not in self.settings:
            return
        if version_info >= VersionInfo.from_str("3.4.0"):
            if await self.bot.cog_disabled_in_guild(self, guild):
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
        invite_attrs = {
            "code": _("Code: "),
            "inviter": _("Inviter: "),
            "channel": _("Channel: "),
            "max_uses": _("Max Uses: "),
            "uses": _("Used: "),
        }
        try:
            invite_time = invite.created_at.strftime("%H:%M:%S")
        except AttributeError:
            invite_time = datetime.datetime.utcnow().strftime("%H:%M:%S")
        msg = _("{emoji} `{time}` Invite deleted ").format(
            emoji=self.settings[guild.id]["invite_deleted"]["emoji"],
            time=invite_time,
        )
        embed = discord.Embed(
            title=_("Invite Deleted"), colour=await self.get_event_colour(guild, "invite_deleted")
        )
        if getattr(invite, "inviter", None):
            embed.description = _("{author} deleted or used up an invite for {channel}.").format(
                author=invite.inviter.mention, channel=invite.channel.mention
            )
        worth_updating = False
        for attr, name in invite_attrs.items():
            before_attr = getattr(invite, attr)
            if before_attr:
                worth_updating = True
                msg += f"{name} {before_attr}\n"
                embed.add_field(name=name, value=str(before_attr))
        if not worth_updating:
            return
        if embed_links:
            await channel.send(embed=embed)
        else:
            await channel.send(escape(msg, mass_mentions=True))
