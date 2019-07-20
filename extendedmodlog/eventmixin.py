import datetime
import discord
import asyncio
import logging

from discord.ext.commands.converter import Converter
from discord.ext.commands.errors import BadArgument

from redbot.core.bot import Red
from redbot.core import commands, Config, modlog
from redbot.core.i18n import Translator, cog_i18n

_ = Translator("ExtendedModLog", __file__)
logger = logging.getLogger("red.trusty-cogs.ExtendedModLog")
listener = getattr(commands.Cog, "listener", None)  # red 3.0 backwards compatibility support
below_red31 = False

if listener is None:  # thanks Sinbad
    below_red31 = True
    def listener(name=None):
        return lambda x: x


class CommandPrivs(Converter):
    """
        Converter for command privliges
    """
    async def convert(self, ctx, argument):
        levels = [
            "MOD",
            "ADMIN",
            "BOT_OWNER",
            "GUILD_OWNER",
            "NONE"
        ]
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


@cog_i18n(_)
class EventMixin:
    """
        Handles all the on_event data
    """

    def __init__(self, *args):
        self.config: Config
        self.bot: Red

    async def get_colour(self, guild):
        if await self.bot.db.guild(guild).use_bot_color():
            return guild.me.colour
        else:
            return await self.bot.db.color()

    async def member_can_run(self, ctx):
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

    async def modlog_channel(self, guild: discord.Guild, event: str):
        channel = None
        settings = await self.config.guild(guild).get_raw(event)
        if settings["channel"]:
            channel = guild.get_channel(settings["channel"])
        if channel is None:
            try:
                channel = await modlog.get_modlog_channel(guild)
            except RuntimeError:
                raise RuntimeError("No Modlog set")
        return channel

    @listener()
    async def on_command(self, ctx: commands.Context):
        guild = ctx.guild
        if guild is None:
            return
        if not await self.config.guild(guild).commands_used.enabled():
            return
        if ctx.channel.id in await self.config.guild(guild).ignored_channels():
            return
        try:
            channel = await self.modlog_channel(guild, "commands_used")
        except RuntimeError:
            return
        time = ctx.message.created_at
        message = ctx.message
        can_run = await self.member_can_run(ctx)
        command = ctx.message.content.replace(ctx.prefix, "")
        com = command.split(" ")[0]
        try:
            privs = self.bot.get_command(command).requires.privilege_level.name
        except Exception:
            return
        if privs not in await self.config.guild(guild).commands_used.privs():
            logger.debug(f"command not in list {privs}")
            return

        if privs == "MOD":
            mod_role_id = await ctx.bot.db.guild(guild).mod_role()
            if mod_role_id is not None:
                role = guild.get_role(mod_role_id).mention + f"\n{privs}"
            else:
                role = _("Not Set\nMOD")
        elif privs == "ADMIN":
            admin_role_id = await ctx.bot.db.guild(guild).admin_role()
            if admin_role_id is not None:
                role = guild.get_role(admin_role_id).mention + f"\n{privs}"
            else:
                role = _("Not Set\nADMIN")
        elif privs == "BOT_OWNER":
            role = f"<@!{ctx.bot.owner_id}>\n{privs}"
        elif privs == "GUILD_OWNER":
            role = guild.owner.mention + f"\n{privs}"
        else:
            role = f"everyone\n{privs}"

        infomessage = (
            f"{message.author.name}#{message.author.discriminator}"
            + _(" used ")
            + com
            + " in "
            + message.channel.name
        )
        if channel.permissions_for(guild.me).embed_links:
            name = f"{message.author.name}#{message.author.discriminator}"

            embed = discord.Embed(
                title=infomessage,
                description=message.content,
                colour=await self.get_colour(guild),
                timestamp=time,
            )
            embed.add_field(name=_("Channel"), value=message.channel.mention)
            embed.add_field(name=_("Can Run"), value=str(can_run))
            embed.add_field(name=_("Required Role"), value=role)
            embed.set_footer(text=_("User ID: ") + str(message.author.id))
            author_title = name + _(" - Used a Command")
            embed.set_author(name=author_title, icon_url=message.author.avatar_url)
            await channel.send(embed=embed)
        else:
            clean_msg = f"{infomessage}\n`{message.clean_content}`"
            await channel.send(clean_msg[:2000])

    @listener(name="on_raw_message_delete")
    async def on_raw_message_delete_listener(self, payload, *, check_audit_log=True):
        # custom name of method used, because this is only supported in Red 3.1+
        guild_id = payload.guild_id
        if guild_id is None:
            return
        guild = self.bot.get_guild(guild_id)
        settings = await self.config.guild(guild).message_delete()
        if not settings["enabled"]:
            return
        channel_id = payload.channel_id
        if channel_id in await self.config.guild(guild).ignored_channels():
            return
        try:
            channel = await self.modlog_channel(guild, "message_delete")
        except RuntimeError:
            return
        message = payload.cached_message
        if message is None:
            if settings["cached_only"]:
                return
            message_channel = guild.get_channel(channel_id)
            if channel.permissions_for(guild.me).embed_links:
                embed = discord.Embed(
                    description=_("*Message's content unknown.*"), colour=discord.Colour.dark_red()
                )
                embed.add_field(name=_("Channel"), value=message_channel.mention)
                embed.set_author(name=_("Deleted Message"))
                await channel.send(embed=embed)
            else:
                infomessage = _("Message was deleted in ") + message_channel.mention
                await channel.send(f"{infomessage}\n*Message's content unknown.*")
            return
        await self._cached_message_delete(
            message, guild, settings, channel, check_audit_log=check_audit_log
        )

    async def on_message_delete(self, message):
        # listener decorator isn't used here because cached messages
        # are handled by on_raw_message_delete event in Red 3.1+
        guild = message.guild
        if guild is None:
            return
        settings = await self.config.guild(guild).message_delete()
        if not settings["enabled"]:
            return
        if message.channel.id in await self.config.guild(guild).ignored_channels():
            return
        try:
            channel = await self.modlog_channel(guild, "message_delete")
        except RuntimeError:
            return
        await self._cached_message_delete(message, guild, settings, channel)

    async def _cached_message_delete(
        self, message, guild, settings, channel, *, check_audit_log=True
    ):
        if message.author.bot and not settings["bots"]:
            # return to ignore bot accounts if enabled
            return
        if message.content == "" and message.attachments == []:
            return
        time = message.created_at
        perp = None
        if channel.permissions_for(guild.me).view_audit_log and check_audit_log:
            action = discord.AuditLogAction.message_delete
            async for log in guild.audit_logs(limit=2, action=action):
                same_chan = log.extra.channel.id == message.channel.id
                if log.target.id == message.author.id and same_chan:
                    perp = log.user
                    break
        author = message.author
        if perp is None:
            infomessage = (
                _("A message from ") + str(author) + _(" was deleted in ") + message.channel.name
            )
        else:
            infomessage = str(perp) + _(" Deleted a message ") + _(" in ") + message.channel.name
        if channel.permissions_for(guild.me).embed_links:
            embed = discord.Embed(
                description=message.content, colour=discord.Colour.dark_red(), timestamp=time
            )

            embed.add_field(name=_("Channel"), value=message.channel.mention)
            if perp:
                embed.add_field(name=_("Deleted by"), value=perp.mention)
            if message.attachments:
                files = ", ".join(a.filename for a in message.attachments)
                if len(message.attachments) > 1:
                    files = files[:-2]
                embed.add_field(name=_("Attachments"), value=files)
            embed.set_footer(text=_("User ID: ") + str(message.author.id))
            embed.set_author(
                name=str(author) + _(" - Deleted Message"), icon_url=message.author.avatar_url
            )
            await channel.send(embed=embed)
        else:
            clean_msg = f"{infomessage}\n`{message.clean_content}`"
            await channel.send(clean_msg[:2000])

    @listener()
    async def on_raw_bulk_message_delete(self, payload):
        guild_id = payload.guild_id
        if guild_id is None:
            return
        guild = self.bot.get_guild(guild_id)
        settings = await self.config.guild(guild).message_delete()
        if not settings["enabled"] or not settings["bulk_enabled"]:
            return
        channel_id = payload.channel_id
        if channel_id in await self.config.guild(guild).ignored_channels():
            return
        message_channel = guild.get_channel(channel_id)
        try:
            channel = await self.modlog_channel(guild, "message_delete")
        except RuntimeError:
            return
        message_amount = len(payload.message_ids)
        if channel.permissions_for(guild.me).embed_links:
            embed = discord.Embed(
                description=message_channel.mention, colour=discord.Colour.dark_red()
            )
            embed.set_author(name=_("Bulk message delete"), icon_url=guild.icon_url)
            embed.add_field(name=_("Channel"), value=message_channel.mention)
            embed.add_field(name=_("Messages deleted"), value=message_amount)
            await channel.send(embed=embed)
        else:
            infomessage = (
                _("Bulk message delete in ")
                + f"{message_channel.mention}, {message_amount}"
                + _("messages deleted.")
            )
            await channel.send(infomessage)
        if not below_red31 and settings["bulk_individual"]:
            for message in payload.cached_messages:
                payload = discord.RawMessageDeleteEvent(
                    {"id": message.id, "channel_id": channel_id, "guild_id": guild_id}
                )
                payload.cached_message = message
                try:
                    await self.on_raw_message_delete_listener(payload, check_audit_log=False)
                except Exception:
                    pass

    async def invite_links_loop(self):
        """Check every 5 minutes for updates to the invite links"""
        await self.bot.wait_until_ready()
        while self is self.bot.get_cog("ExtendedModLog"):
            for guild_id in await self.config.all_guilds():
                guild = self.bot.get_guild(guild_id)
                if guild is None:
                    # Let's remove missing guilds
                    await self.config.clear_scope(Config.GUILD, str(guild_id))
                if await self.config.guild(guild).user_join.enabled():
                    await self.save_invite_links(guild)
            await asyncio.sleep(300)

    async def save_invite_links(self, guild):
        invites = {}
        if not guild.me.guild_permissions.manage_guild:
            return False
        for invite in await guild.invites():
            try:
                invites[invite.code] = {
                    "uses": invite.uses,
                    "max_age": invite.max_age,
                    "created_at": invite.created_at.timestamp(),
                    "max_uses": invite.max_uses,
                    "temporary": invite.temporary,
                    "inviter": invite.inviter.id,
                    "channel": invite.channel.id,
                }
            except Exception:
                pass
        await self.config.guild(guild).invite_links.set(invites)
        return True

    async def get_invite_link(self, guild):
        manage_guild = guild.me.guild_permissions.manage_guild
        invites = await self.config.guild(guild).invite_links()
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
                            "https://discord.gg/{code}\n" "Invited by: {inviter}"
                        ).format(code=invite.code, inviter=str(invite.inviter))

            if not possible_link:
                for code, data in invites.items():
                    try:
                        invite = await self.bot.get_invite(code)
                    except (discord.errors.NotFound, discord.errors.HTTPException, Exception):
                        logger.error("Error getting invite ".format(code))
                        invite = None
                        pass
                    if not invite:
                        if (data["max_uses"] - data["uses"]) == 1:
                            # The invite link was on its last uses and subsequently
                            # deleted so we're fairly sure this was the one used
                            inviter = await self.bot.get_user_info(data["inviter"])
                            possible_link = _(
                                "https://discord.gg/{code}\n" "Invited by: {inviter}"
                            ).format(code=code, inviter=str(inviter))
            await self.save_invite_links(guild)  # Save all the invites again since they've changed
        if check_logs and not possible_link:
            action = discord.AuditLogAction.invite_create
            async for log in guild.audit_logs(action=action):
                if log.target.code not in invites:
                    possible_link = _(
                        "https://discord.gg/{code}\n" "Invited by: {inviter}"
                    ).format(code=log.target.code, inviter=str(log.target.inviter))
                    break
        return possible_link

    @listener()
    async def on_member_join(self, member):
        guild = member.guild

        if not await self.config.guild(guild).user_join.enabled():
            return
        try:
            channel = await self.modlog_channel(guild, "user_join")
        except RuntimeError:
            return
        time = datetime.datetime.utcnow()
        users = len(guild.members)
        # https://github.com/Cog-Creators/Red-DiscordBot/blob/develop/cogs/general.py
        since_created = (time - member.created_at).days
        user_created = member.created_at.strftime("%d %b %Y %H:%M")

        created_on = "{}\n({} days ago)".format(user_created, since_created)

        possible_link = await self.get_invite_link(guild)
        if channel.permissions_for(guild.me).embed_links:
            name = member
            embed = discord.Embed(
                description=member.mention,
                colour=discord.Colour.green(),
                timestamp=member.joined_at,
            )
            embed.add_field(name=_("Total Users:"), value=str(users))
            embed.add_field(name=_("Account created on:"), value=created_on)
            embed.set_footer(text=_("User ID: ") + str(member.id))
            embed.set_author(
                name=name.display_name + _(" has joined the guild"),
                url=member.avatar_url,
                icon_url=member.avatar_url,
            )
            if possible_link:
                embed.add_field(name=_("Invite Link"), value=possible_link)
            embed.set_thumbnail(url=member.avatar_url)
            await channel.send(embed=embed)
        else:
            msg = (
                f":white_check_mark: **{member}** "
                + _("joined the guild. Total members: ")
                + str(users)
                + "\n"
                + possible_link
            )
            await channel.send(msg)

    @listener()
    async def on_member_remove(self, member):
        guild = member.guild

        if not await self.config.guild(guild).user_left.enabled():
            return
        try:
            channel = await self.modlog_channel(guild, "user_left")
        except RuntimeError:
            return
        if channel is None:
            return
        time = datetime.datetime.utcnow()
        perp = None
        reason = None
        if channel.permissions_for(guild.me).view_audit_log:
            action = discord.AuditLogAction.kick
            async for log in guild.audit_logs(limit=5, action=action):
                if log.target.id == member.id:
                    perp = log.user
                    reason = log.reason
                    break
        if channel.permissions_for(guild.me).embed_links:
            embed = discord.Embed(
                description=member.mention, colour=discord.Colour.dark_green(), timestamp=time
            )
            embed.add_field(name=_("Total Users:"), value=str(len(guild.members)))
            if perp:
                embed.add_field(name=_("Kicked"), value=perp.mention)
            if reason:
                embed.add_field(name=_("Reason"), value=str(reason))
            embed.set_footer(text=_("User ID: ") + str(member.id))
            embed.set_author(
                name=str(member) + _(" has left the guild"),
                url=member.avatar_url,
                icon_url=member.avatar_url,
            )
            embed.set_thumbnail(url=member.avatar_url)
            await channel.send(embed=embed)
        else:
            msg = (
                f":x:**{member}** "
                + _("has left the guild. Total users: ")
                + str(len(guild.members))
            )
            if perp:
                msg = (
                    f":x:**{member}** "
                    + _("was kicked by ")
                    + str(perp)
                    + _(". Total users: ")
                    + str(len(guild.members))
                )
            await channel.send(msg)

    async def get_permission_change(self, before, after, embed_links):
        p_msg = ""
        before_perms = {}
        after_perms = {}
        for o, p in before.overwrites.items():
            before_perms[str(o.id)] = [i for i in p]
        for o, p in after.overwrites.items():
            after_perms[str(o.id)] = [i for i in p]
        for entity in before_perms:
            entity_obj = before.guild.get_role(int(entity))
            if entity_obj is None:
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
            if entity_obj is None:
                entity_obj = after.guild.get_member(int(entity))
            if entity not in before_perms:
                if not embed_links:
                    p_msg += f"{entity_obj.name} Overwrites added.\n"
                else:
                    p_msg += f"{entity_obj.mention} Overwrites added.\n"
                continue
        return p_msg

    @listener()
    async def on_guild_channel_create(self, new_channel):
        guild = new_channel.guild
        if not await self.config.guild(guild).channel_change.enabled():
            return
        try:
            channel = await self.modlog_channel(guild, "channel_change")
        except RuntimeError:
            return
        if channel is None:
            return
        embed_links = channel.permissions_for(guild.me).embed_links
        time = datetime.datetime.utcnow()
        embed = discord.Embed(
            description=new_channel.mention, timestamp=time, colour=discord.Colour.teal()
        )
        embed.set_author(name=_("Channel Created ") + str(new_channel.id))
        msg = _("Channel Created ") + str(new_channel.id) + "\n"
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
        if type(new_channel) == discord.TextChannel:
            msg += _("Text Channel Created")
            embed.add_field(name=_("Type"), value=_("Text"))
        if type(new_channel) == discord.CategoryChannel:
            msg += _("Category Channel Created")
            embed.add_field(name=_("Type"), value=_("Category"))
        if type(new_channel) == discord.VoiceChannel:
            msg += _("Voice Channel Created")
            embed.add_field(name=_("Type"), value=_("Voice"))
        if perp:
            msg += _("Created by ") + str(perp)
            embed.add_field(name=_("Created by "), value=perp.mention)
        if reason:
            msg += _("Reason ") + reason + "\n"
            embed.add_field(name=_("Reason "), value=reason)
        if embed_links:
            await channel.send(embed=embed)
        else:
            await channel.send(msg)

    @listener()
    async def on_guild_channel_delete(self, old_channel):
        guild = old_channel.guild
        if not await self.config.guild(guild).channel_change.enabled():
            return
        try:
            channel = await self.modlog_channel(guild, "channel_change")
        except RuntimeError:
            return
        if channel is None:
            return
        embed_links = channel.permissions_for(guild.me).embed_links
        time = datetime.datetime.utcnow()
        embed = discord.Embed(
            description=old_channel.name, timestamp=time, colour=discord.Colour.dark_teal()
        )
        embed.set_author(name=_("Channel Deleted ") + str(old_channel.id))
        msg = _("Channel Deleted ") + str(old_channel.id) + "\n"
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
        if type(old_channel) == discord.TextChannel:
            msg += _("Text Channel Deleted")
            embed.add_field(name=_("Type"), value=_("Text"))
        if type(old_channel) == discord.CategoryChannel:
            msg += _("Category Channel Deleted")
            embed.add_field(name=_("Type"), value=_("Category"))
        if type(old_channel) == discord.VoiceChannel:
            msg += _("Voice Channel Deleted")
            embed.add_field(name=_("Type"), value=_("Voice"))
        if perp:
            msg += _("Deleted by ") + str(perp)
            embed.add_field(name=_("Deleted by "), value=perp.mention)
        if reason:
            msg += _("Reason ") + reason + "\n"
            embed.add_field(name=_("Reason "), value=reason)
        if embed_links:
            await channel.send(embed=embed)
        else:
            await channel.send(msg)

    @listener()
    async def on_guild_channel_update(self, before, after):
        guild = before.guild
        if not await self.config.guild(guild).channel_change.enabled():
            return
        try:
            channel = await self.modlog_channel(guild, "channel_change")
        except RuntimeError:
            return
        if channel is None:
            return
        embed_links = channel.permissions_for(guild.me).embed_links
        time = datetime.datetime.utcnow()
        embed = discord.Embed(
            description=after.mention, timestamp=time, colour=discord.Colour.teal()
        )
        embed.set_author(name=_("Updated channel ") + str(before.id))
        msg = _("Updated channel ") + str(before.id) + "\n"
        perp = None
        reason = None
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
                    if before_attr == "":
                        before_attr = "None"
                    if after_attr == "":
                        after_attr = "None"
                    msg += _("Before ") + f"{name} {before_attr}\n"
                    msg += _("After ") + f"{name} {after_attr}\n"
                    embed.add_field(name=_("Before ") + name, value=str(before_attr)[:1024])
                    embed.add_field(name=_("After ") + name, value=str(after_attr)[:1024])
            if before.is_nsfw() != after.is_nsfw():
                msg += _("Before ") + f"NSFW {before.is_nsfw()}\n"
                msg += _("After ") + f"NSFW {after.is_nsfw()}\n"
                embed.add_field(name=_("Before ") + "NSFW", value=str(before.is_nsfw()))
                embed.add_field(name=_("After ") + "NSFW", value=str(after.is_nsfw()))
            p_msg = await self.get_permission_change(before, after, embed_links)
            if p_msg != "":
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
                    msg += _("Before ") + f"{name} {before_attr}\n"
                    msg += _("After ") + f"{name} {after_attr}\n"
                    embed.add_field(name=_("Before ") + name, value=str(before_attr))
                    embed.add_field(name=_("After ") + name, value=str(after_attr))
            p_msg = await self.get_permission_change(before, after, embed_links)
            if p_msg != "":
                msg += _("Permissions Changed: ") + p_msg
                embed.add_field(name=_("Permissions"), value=p_msg[:1024])

        if perp:
            msg += _("Updated by ") + str(perp) + "\n"
            embed.add_field(name=_("Updated by "), value=perp.mention)
        if reason:
            msg += _("Reason ") + reason + "\n"
            embed.add_field(name=_("Reason "), value=reason)
        if len(embed.fields) == 0:
            return
        if channel.permissions_for(guild.me).embed_links:
            await channel.send(embed=embed)
        else:
            await channel.send(msg)

    async def get_role_permission_change(self, before, after):
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

    @listener()
    async def on_guild_role_update(self, before, after):
        guild = before.guild
        if not await self.config.guild(guild).role_change.enabled():
            return
        try:
            channel = await self.modlog_channel(guild, "role_change")
        except RuntimeError:
            return
        if channel is None:
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
        embed_links = channel.permissions_for(guild.me).embed_links
        time = datetime.datetime.utcnow()
        embed = discord.Embed(description=after.mention, colour=after.colour, timestamp=time)

        if after is guild.default_role:
            embed.set_author(name=_("Updated Everyone role "), icon_url=guild.icon_url)
            msg = _("Updated Everyone role ") + "\n"
        else:
            embed.set_author(name=_("Updated role ") + str(before.id), icon_url=guild.icon_url)
            msg = _("Updated role ") + str(before.id) + "\n"
        if perp:
            msg += _("Updated by ") + str(perp) + "\n"
            embed.add_field(name=_("Updated by "), value=perp.mention)
        if reason:
            msg += _("Reason ") + reason + "\n"
            embed.add_field(name=_("Reason "), value=reason)
        role_updates = {
            "name": _("Name:"),
            "color": _("Colour:"),
            "mentionable": _("Mentionable:"),
            "hoist": _("Is Hoisted:"),
        }

        for attr, name in role_updates.items():
            before_attr = getattr(before, attr)
            after_attr = getattr(after, attr)
            if before_attr != after_attr:
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
            msg += _("Permissions Changed: ") + p_msg
            embed.add_field(name=_("Permissions"), value=p_msg[:1024])
        if len(embed.fields) == 0:
            return
        if embed_links:
            await channel.send(embed=embed)
        else:
            await channel.send(msg)

    @listener()
    async def on_guild_role_create(self, role):
        guild = role.guild
        if not await self.config.guild(guild).role_change.enabled():
            return
        try:
            channel = await self.modlog_channel(guild, "role_change")
        except RuntimeError:
            return
        if channel is None:
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
        embed_links = channel.permissions_for(guild.me).embed_links
        time = datetime.datetime.utcnow()
        embed = discord.Embed(
            description=role.mention, colour=discord.Colour.blue(), timestamp=time
        )
        embed.set_author(name=_("Role created ") + str(role.id), icon_url=guild.icon_url)
        msg = _("Role created ") + str(role.id) + "\n"
        msg += role.name
        if perp:
            embed.add_field(name=_("Created by"), value=perp.mention)
            msg += _("By ") + str(perp) + "\n"
        if reason:
            msg += _("Reason ") + reason + "\n"
            embed.add_field(name=_("Reason "), value=reason)
        if embed_links:
            await channel.send(embed=embed)
        else:
            await channel.send(msg)

    @listener()
    async def on_guild_role_delete(self, role):
        guild = role.guild
        if not await self.config.guild(guild).role_change.enabled():
            return
        try:
            channel = await self.modlog_channel(guild, "role_change")
        except RuntimeError:
            return
        if channel is None:
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
        embed_links = channel.permissions_for(guild.me).embed_links
        time = datetime.datetime.utcnow()
        embed = discord.Embed(
            description=role.name, timestamp=time, colour=discord.Colour.dark_blue()
        )
        embed.set_author(name=_("Role deleted ") + str(role.id))
        msg = _("Role deleted ") + str(role.id) + "\n"
        msg += role.name
        if perp:
            embed.add_field(name=_("Deleted by"), value=perp.mention)
            msg += _("By ") + str(perp) + "\n"
        if reason:
            msg += _("Reason ") + reason + "\n"
            embed.add_field(name=_("Reason "), value=reason)
        if embed_links:
            await channel.send(embed=embed)
        else:
            await channel.send(msg)

    @listener()
    async def on_message_edit(self, before, after):
        guild = before.guild
        if guild is None:
            return
        settings = await self.config.guild(guild).message_edit()
        if not settings["enabled"]:
            return
        if before.author.bot and not settings["bots"]:
            return
        if before.channel.id in await self.config.guild(guild).ignored_channels():
            return
        if before.content == after.content:
            return
        try:
            channel = await self.modlog_channel(guild, "message_edit")
        except RuntimeError:
            return
        if channel is None:
            return
        time = datetime.datetime.utcnow()
        fmt = "%H:%M:%S"
        if channel.permissions_for(guild.me).embed_links:
            name = before.author
            name = " ~ ".join((name.name, name.nick)) if name.nick else name.name
            embed = discord.Embed(
                description=before.content,
                colour=discord.Colour.orange(),
                timestamp=before.created_at,
            )
            jump_url = f"[Click to see new message]({after.jump_url})"
            embed.add_field(name=_("After Message:"), value=jump_url)
            embed.add_field(name=_("Channel:"), value=before.channel.mention)
            embed.set_footer(text=_("User ID: ") + str(before.author.id))
            embed.set_author(name=name + _(" - Edited Message"), icon_url=before.author.avatar_url)
            await channel.send(embed=embed)
        else:
            msg = (
                f":pencil: `{time.strftime(fmt)}` **"
                + _("Channel")
                + f"**{before.channel.mention}"
                + f" **{before.author.name}#{before.author.discriminator}'s** "
                + _("message has been edited.\nBefore: ")
                + before.clean_content
                + _("\nAfter: ")
                + after.clean_content
            )
            await channel.send(msg[:2000])

    @listener()
    async def on_guild_update(self, before, after):
        guild = after
        if not await self.config.guild(guild).guild_change.enabled():
            return
        try:
            channel = await self.modlog_channel(guild, "guild_change")
        except RuntimeError:
            return
        if channel is None:
            return

        time = datetime.datetime.utcnow()
        embed = discord.Embed(timestamp=time, colour=discord.Colour.blurple())
        embed.set_author(name=_("Updated Guild ") + str(before.id), icon_url=guild.icon_url)
        embed.set_thumbnail(url=guild.icon_url)
        msg = _("Updated Guild ") + str(before.id) + "\n"
        guild_updates = {
            "name": _("Name:"),
            "region": _("Region:"),
            "afk_timeout": _("AFK Timeout:"),
            "afk_channel": _("AFK Channel:"),
            "icon_url": _("Server Icon:"),
            "owner": _("Server Owner:"),
            "splash": _("Splash Image:"),
            "system_channel": _("Welcome message channel:"),
            "verification_level": _("Verification Level:")
        }
        for attr, name in guild_updates.items():
            before_attr = getattr(before, attr)
            after_attr = getattr(after, attr)
            if before_attr != after_attr:
                msg += _("Before ") + f"{name} {before_attr}\n"
                msg += _("After ") + f"{name} {after_attr}\n"
                embed.add_field(name=_("Before ") + name, value=str(before_attr))
                embed.add_field(name=_("After ") + name, value=str(after_attr))
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
            reasons = ", ".join(str(r) for r in reasons)
            msg += _("Reasons ") + f"{reasons}\n"
            embed.add_field(name=_("Reasons "), value=reasons)
        if channel.permissions_for(guild.me).embed_links:
            await channel.send(embed=embed)
        else:
            await channel.send(msg)

    @listener()
    async def on_guild_emojis_update(self, guild, before, after):
        if not await self.config.guild(guild).emoji_change.enabled():
            return
        try:
            channel = await self.modlog_channel(guild, "emoji_change")
        except RuntimeError:
            return
        if channel is None:
            return
        perp = None

        time = datetime.datetime.utcnow()
        embed = discord.Embed(description="", timestamp=time, colour=discord.Colour.gold())
        embed.set_author(name=_("Updated Server Emojis"), icon_url=guild.icon_url)
        msg = _("Updated Server Emojis") + "\n"
        before_str = [str(e.name) for e in before]
        after_str = [str(e.name) for e in after]
        b = set(before_str)
        a = set(after_str)
        added_emoji = [list(a - b)][0]
        removed_emoji = [list(b - a)][0]
        changed_emoji = [list(set([e.name for e in after]) - set([e.name for e in before]))][0]
        action = None
        for emoji in removed_emoji:
            new_msg = f"`{emoji}`" + _(" Removed from the guild\n")
            msg += new_msg
            embed.description += new_msg
            action = discord.AuditLogAction.emoji_delete
        for emoji in added_emoji:
            new_msg = f"{emoji} `{emoji}`" + _(" Added to the guild\n")
            msg += new_msg
            embed.description += new_msg
            action = discord.AuditLogAction.emoji_create
        for emoji in changed_emoji:
            for emojis in after:
                if emojis.name == emoji:
                    e = emojis
            new_msg = f"{e} `{e}`" + _(" Emoji changed\n")
            msg += new_msg
            embed.description += new_msg
            action = discord.AuditLogAction.emoji_update
        perp = None
        reason = None

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
            embed.add_field(name=_("Reason "), value=reason)
        if channel.permissions_for(guild.me).embed_links:
            await channel.send(embed=embed)
        else:
            await channel.send(msg)

    @listener()
    async def on_voice_state_update(self, member, before, after):
        guild = member.guild
        if not await self.config.guild(guild).voice_change.enabled():
            return
        if member.bot:
            return
        try:
            channel = await self.modlog_channel(guild, "voice_change")
        except RuntimeError:
            return
        if channel is None:
            return
        time = datetime.datetime.utcnow()
        embed = discord.Embed(
            timestamp=time, icon_url=guild.icon_url, colour=discord.Colour.magenta()
        )
        msg = f"{member} " + _("Updated Voice State") + "\n"
        embed.set_author(name=msg)
        change_type = None
        if before.deaf != after.deaf:
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
            change_type = "channel"
            if before.channel is None:
                chan_msg = member.mention + _(" has joined ") + after.channel.mention
                msg += chan_msg + "\n"
                embed.description = chan_msg
            elif after.channel is None:
                chan_msg = member.mention + _(" has left ") + before.channel.mention
                msg += chan_msg + "\n"
                embed.description = chan_msg
            else:
                chan_msg = (
                    member.mention
                    + _(" has moved from ")
                    + before.channel.mention
                    + _(" to ")
                    + after.channel.mention
                )
                msg += chan_msg
                embed.description = chan_msg
        if not change_type:
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
            embed.add_field(name=_("Reason "), value=reason)
        if channel.permissions_for(guild.me).embed_links:
            await channel.send(embed=embed)
        else:
            await channel.send(msg.replace(member.mention, str(member)))

    @listener()
    async def on_member_update(self, before, after):
        guild = before.guild
        if not await self.config.guild(guild).user_change.enabled():
            return
        try:
            channel = await self.modlog_channel(guild, "user_change")
        except RuntimeError:
            return
        if channel is None:
            return
        embed_links = channel.permissions_for(guild.me).embed_links
        time = datetime.datetime.utcnow()
        embed = discord.Embed(timestamp=time, colour=discord.Colour.greyple())
        msg = f"{before.name}#{before.discriminator} " + _("Updated") + "\n"
        org_len = len(msg)
        embed.set_author(name=msg, icon_url=before.avatar_url)
        member_updates = {"nick": _("Nickname:"), "roles": _("Roles:")}
        perp = None
        reason = None
        for attr, name in member_updates.items():
            before_attr = getattr(before, attr)
            after_attr = getattr(after, attr)
            if before_attr != after_attr:
                if attr == "roles":
                    b = set(before.roles)
                    a = set(after.roles)
                    before_roles = [list(b - a)][0]
                    after_roles = [list(a - b)][0]
                    if before_roles:
                        for role in before_roles:
                            msg += role.name + _(" Role Removed.")
                            embed.description = role.mention + _(" Role Removed.")
                    if after_roles:
                        for role in after_roles:
                            msg += role.name + _(" Role Applied.")
                            embed.description = role.mention + _(" Role Applied.")
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
                    msg += _("Before ") + f"{name} {before_attr}\n"
                    msg += _("After ") + f"{name} {after_attr}\n"
                    embed.add_field(name=_("Before ") + name, value=str(before_attr)[:1024])
                    embed.add_field(name=_("After ") + name, value=str(after_attr)[:1024])
        if len(msg) == org_len:
            return
        if perp:
            msg += _("Updated by ") + f"{perp}\n"
            embed.add_field(name=_("Updated by "), value=perp.mention)
        if reason:
            msg += _("Reason: ") + f"{reason}\n"
            embed.add_field(name=_("Reason"), value=reason)
        if embed_links:
            await channel.send(embed=embed)
        else:
            await channel.send(msg)
