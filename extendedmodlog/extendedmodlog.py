from redbot.core import commands, checks, Config, modlog
import datetime
import discord
import asyncio
from random import choice, randint
from redbot.core.i18n import Translator, cog_i18n

inv_settings = {
    "message_edit": False, 
    "message_delete": False, 
    "user_change": False,
    "role_change": False,
    "voice_change": False,
    "user_join": False, 
    "user_left": False, 
    "channel_change": False,
    "guild_change": False,
    "emoji_change": False,
    "commands_used":False,
    "ignored_channels":[]
            }

_ = Translator("ExtendedModLog", __file__)


@cog_i18n(_)
class ExtendedModLog(getattr(commands, "Cog", object)):
    """
        Extended modlogs
        Works with core modlogset channel
    """

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, 154457677895)
        self.config.register_guild(**inv_settings, force_registration=True)

    @checks.admin_or_permissions(manage_channels=True)
    @commands.group(aliases=["modlogtoggle"])
    @commands.guild_only()
    async def modlogtoggles(self, ctx):
        """
            Toggle various extended modlog notifications

            Requires the channel to be setup with `[p]modlogset modlog #channel` first
        """
        if await self.config.guild(ctx.message.guild).settings() == {}:
            await self.config.guild(ctx.message.guild).set(inv_settings)
        if ctx.invoked_subcommand is None:
            guild = ctx.message.guild
            try:
                modlog_channel = await modlog.get_modlog_channel(guild)
            except:
                await ctx.send(_("You need to setup a channel with `[p]modlogset modlog #channel` first."))
                return
            cur_settings = {"message_edit": _("Message edits"), 
                            "message_delete": _("Message delete"), 
                            "user_change": _("Member changes"),
                            "role_change": _("Role changes"),
                            "voice_change": _("Voice changes"),
                            "user_join": _("User join"), 
                            "user_left": _("Member left"), 
                            "channel_change": _("Channel changes"),
                            "guild_change": _("Guild changes"),
                            "emoji_change": _("Emoji changes"),
                            "commands_used": _("Mod/Admin Commands")}
            msg = _("Setting for ") + guild.name + "\n"
            e = discord.Embed(title=_("Setting for ") + guild.name)
            e.colour = await self.get_colour(ctx.guild)
            e.description = _("ModLogs channel set to ") + modlog_channel.mention
            ignored_channels = await self.config.guild(guild).ignored_channels()
            enabled = ""
            disabled = ""
            for setting, name in cur_settings.items():
                if await self.config.guild(ctx.guild).get_raw(setting):
                    enabled += name + ", "
                else:
                    disabled += name + ", "
            if enabled == "":
                enabled = _("None  ")
            if disabled == "":
                disabled = _("None  ")
            msg += _("Enabled") + ": " + enabled + "\n"
            msg += _("Disabled") + ": " + disabled + "\n"
            e.add_field(name=_("Enabled"), value=enabled[:-2])
            e.add_field(name=_("Disabled"), value=disabled[:-2])
            if ignored_channels:
                chans = ", ".join(guild.get_channel(c).mention for c in ignored_channels)
                if len(ignored_channels) > 1:
                    chans = chans[:-2]
                msg += _("Ignored Channels") + ": " + chans
                e.add_field(name=_("Ignored Channels"), value=chans)
            
            e.set_thumbnail(url=guild.icon_url)
            if ctx.channel.permissions_for(ctx.me).embed_links:
                await ctx.send(embed=e)
            else:
                await ctx.send(msg)


    @modlogtoggles.command()
    async def edit(self, ctx):
        """
            Toggle message edit notifications
        """
        guild = ctx.message.guild
        msg = _("Edit messages ")
        if not await self.config.guild(guild).message_edit():
            await self.config.guild(guild).message_edit.set(True)
            verb = _("enabled")
        else:
            await self.config.guild(guild).message_edit.set(False)
            verb = _("disabled")
        await ctx.send(msg+verb)

    @modlogtoggles.command()
    async def join(self, ctx):
        """
            Toggle member join notifications
        """
        guild = ctx.message.guild
        msg = _("Join message logs ")
        if not await self.config.guild(guild).user_join():
            await self.config.guild(guild).user_join.set(True)
            verb = _("enabled")
        else:
            await self.config.guild(guild).user_join.set(False)
            verb = _("disabled")
        await ctx.send(msg+verb)

    @modlogtoggles.command()
    async def guild(self, ctx):
        """
            Toggle guild change notifications

            Shows changes to name, region, afk timeout, and afk channel
        """
        guild = ctx.message.guild
        msg = _("Guild logs ")
        if not await self.config.guild(guild).guild_change():
            await self.config.guild(guild).guild_change.set(True)
            verb = _("enabled")
        else:
            await self.config.guild(guild).guild_change.set(False)
            verb = _("disabled")
        await ctx.send(msg+verb)

    @modlogtoggles.command(aliases=["channels"])
    async def channel(self, ctx):
        """
            Toggle channel edit notifications

            Shows changes to name, topic, slowmode, and NSFW
        """
        guild = ctx.message.guild
        msg = _("Channel logs ")
        if not await self.config.guild(guild).channel_change():
            await self.config.guild(guild).channel_change.set(True)
            verb = _("enabled")
        else:
            await self.config.guild(guild).channel_change.set(False)
            verb = _("disabled")
        await ctx.send(msg+verb)

    @modlogtoggles.command()
    async def leave(self, ctx):
        """
            Toggle member leave notifications
        """
        guild = ctx.message.guild
        msg = _("Leave logs ")
        if not await self.config.guild(guild).user_left():
            await self.config.guild(guild).user_left.set(True)
            verb = _("enabled")
        else:
            await self.config.guild(guild).user_left.set(False)
            verb = _("disabled")
        await ctx.send(msg+verb)

    @modlogtoggles.command()
    async def delete(self, ctx):
        """
            Toggle message delete notifications
        """
        guild = ctx.message.guild
        msg = _("Message delete logs ")
        if not await self.config.guild(guild).message_delete():
            await self.config.guild(guild).message_delete.set(True)
            verb = _("enabled")
        else:
            await self.config.guild(guild).message_delete.set(False)
            verb = _("disabled")
        await ctx.send(msg+verb)

    @modlogtoggles.command(aliases=["member"])
    async def user(self, ctx):
        """
            Toggle member change notifications

            Shows changes to roles and nicknames
        """
        guild = ctx.message.guild
        msg = _("Profile logs ")
        if not await self.config.guild(guild).user_change():
            await self.config.guild(guild).user_change.set(True)
            verb = _("enabled")
        else:
            await self.config.guild(guild).user_change.set(False)
            verb = _("disabled")
        await ctx.send(msg+verb)

    @modlogtoggles.command(aliases=["roles"])
    async def role(self, ctx):
        """
            Toggle role change notifications

            Shows new roles, deleted roles, and permission changes
        """
        guild = ctx.message.guild
        msg = _("Role logs ")
        if not await self.config.guild(guild).role_change():
            await self.config.guild(guild).role_change.set(True)
            verb = _("enabled")
        else:
            await self.config.guild(guild).role_change.set(False)
            verb = _("disabled")
        await ctx.send(msg+verb)

    @modlogtoggles.command()
    async def voice(self, ctx):
        """
            Toggle voice state notifications

            Shows changes to mute, deafen, self mute, self deafen, afk, and channel
        """
        guild = ctx.message.guild
        msg = _("Voice logs ")
        if not await self.config.guild(guild).voice_change():
            await self.config.guild(guild).voice_change.set(True)
            verb = _("enabled")
        else:
            await self.config.guild(guild).voice_change.set(False)
            verb = _("disabled")
        await ctx.send(msg+verb)

    @modlogtoggles.command(aliases=["emojis"])
    async def emoji(self, ctx):
        """
            Toggle emoji change notifications
        """
        guild = ctx.message.guild
        msg = _("Emoji logs ")
        if not await self.config.guild(guild).emoji_change():
            await self.config.guild(guild).emoji_change.set(True)
            verb = _("enabled")
        else:
            await self.config.guild(guild).emoji_change.set(False)
            verb = _("disabled")
        await ctx.send(msg+verb)

    @modlogtoggles.command(aliases=["commands"])
    async def command(self, ctx):
        """
            Toggle mod/admin command usage
        """
        guild = ctx.message.guild
        msg = _("Command logs ")
        if not await self.config.guild(guild).commands_used():
            await self.config.guild(guild).commands_used.set(True)
            verb = _("enabled")
        else:
            await self.config.guild(guild).commands_used.set(False)
            verb = _("disabled")
        await ctx.send(msg+verb)

    @modlogtoggles.command()
    async def ignore(self, ctx, channel:discord.TextChannel=None):
        """
            Ignore a channel from message delete/edit events and bot commands

            `channel` the channel to ignore message delete/edit events
            defaults to current channel
        """
        guild = ctx.message.guild
        if channel is None:
            channel = ctx.channel
        cur_ignored = await self.config.guild(guild).ignored_channels()
        if channel.id not in cur_ignored:
            cur_ignored.append(channel.id)
            await self.config.guild(guild).ignored_channels.set(cur_ignored)
            await ctx.send(_(" Now ignoring messages edited and deleted in ") + channel.mention)
        else:
            await ctx.send(channel.mention + _(" is already being ignored."))

    @modlogtoggles.command()
    async def unignore(self, ctx, channel:discord.TextChannel=None):
        """
            Unignore a channel from message delete/edit events and bot commands

            `channel` the channel to unignore message delete/edit events
            defaults to current channel
        """
        guild = ctx.message.guild
        if channel is None:
            channel = ctx.channel
        cur_ignored = await self.config.guild(guild).ignored_channels()
        if channel.id in cur_ignored:
            cur_ignored.remove(channel.id)
            await self.config.guild(guild).ignored_channels.set(cur_ignored)
            await ctx.send(_(" now tracking edited and deleted messages in ") + channel.mention)
        else:
            await ctx.send(channel.mention + _(" is not being ignored."))

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

    async def on_command(self, ctx:commands.Context):
        guild = ctx.guild
        if guild is None:
            return
        if not await self.config.guild(guild).commands_used():
            return
        if ctx.channel.id in await self.config.guild(guild).ignored_channels():
            return
        try:
            channel = await modlog.get_modlog_channel(guild)
        except:
            return
        time = ctx.message.created_at
        cleanmsg = ctx.message.content
        message = ctx.message
        can_run = await self.member_can_run(ctx)
        command = ctx.message.content.replace(ctx.prefix, "")
        com = command.split(" ")[0]
        try:
            privs = self.bot.get_command(command).requires.privilege_level.name
        except:
            return
        if privs not in ["MOD", "ADMIN", "BOT_OWNER", "GUILD_OWNER"]:
            return
        if privs == "MOD":
            mod_role_id = await ctx.bot.db.guild(guild).mod_role()
            if mod_role_id is not None:
                role = guild.get_role(mod_role_id).mention + f"\n{privs}"
            else:
                role = _("Not Set\nMOD")
        if privs == "ADMIN":
            admin_role_id = await ctx.bot.db.guild(guild).admin_role()
            if admin_role_id != None:
                role = guild.get_role(admin_role_id).mention + f"\n{privs}"
            else:
                role = _("Not Set\nADMIN")
        if privs == "BOT_OWNER":
            role = guild.get_member(ctx.bot.owner_id).mention + f"\n{privs}"
        if privs == "GUILD_OWNER":
            role = guild.owner.mention + f"\n{privs}"
        
        for i in ctx.message.mentions:
            cleanmsg = cleanmsg.replace(i.mention, str(i))
        infomessage = (f"{message.author.name}#{message.author.discriminator}"+
                       _(" used ") + com + " in "+
                            message.channel.name)
        if channel.permissions_for(guild.me).embed_links:
            name = f"{message.author.name}#{message.author.discriminator}"
            
            embed = discord.Embed(title=infomessage,
                                  description=f"`{message.content}`",
                                  colour=await self.get_colour(guild),
                                  timestamp=time)
            embed.add_field(name=_("Channel"), value=message.channel.mention)
            embed.add_field(name=_("Can Run"), value=str(can_run))
            embed.add_field(name=_("Required Role"), value=role)
            embed.set_footer(text=_("User ID: ")+ str(message.author.id))
            author_title = name + _(" - Used a MOD/ADMIN Command")
            embed.set_author(name=author_title, 
                             icon_url=message.author.avatar_url)
            await channel.send(embed=embed)
        else:
            clean_msg = (f"{infomessage}\n`{cleanmsg}`")
            await channel.send(clean_msg)

    async def on_message_delete(self, message):
        guild = message.guild
        if guild is None:
            return
        if not await self.config.guild(guild).message_delete():
            return
        if message.channel.id in await self.config.guild(guild).ignored_channels():
            return
        try:
            channel = await modlog.get_modlog_channel(guild)
        except:
            return
        if message.content == "" and message.attachments == []:
            return
        time = message.created_at
        cleanmsg = message.content
        for i in message.mentions:
            cleanmsg = cleanmsg.replace(i.mention, str(i))
        fmt = "%H:%M"
        perp = None
        if channel.permissions_for(guild.me).view_audit_log:
            action = discord.AuditLogAction.message_delete
            async for log in guild.audit_logs(limit=2, action=action):
                same_chan = log.extra.channel.id == message.channel.id
                if log.target.id == message.author.id and same_chan:
                    perp = log.user
                    break
        author = message.author
        if perp is None:
            infomessage = (_("A message by ") + str(author) +
                           _(" was deleted in ")+
                           message.channel.name)
        else:
            infomessage = (str(perp) + _(" Deleted a message ")  +
                           _(" in ") + message.channel.name)
        if channel.permissions_for(guild.me).embed_links:
            embed = discord.Embed(description=message.content,
                                  colour=discord.Colour.dark_red(),
                                  timestamp=time)

            embed.add_field(name=_("Channel"), value=message.channel.mention)
            if perp:
                embed.add_field(name=_("Deleted by"), value=perp.mention)
            if message.attachments:
                files = ", ".join(a.filename for a in message.attachments)
                if len(message.attachments) > 1:
                    files = files[:-2]
                embed.add_field(name=_("Attachments"), value=files)
            embed.set_footer(text=_("User ID: ")+ str(message.author.id))
            embed.set_author(name=str(author) + _(" - Deleted Message"), 
                             icon_url=message.author.avatar_url)
            await channel.send(embed=embed)
        else:
            await channel.send(infomessage)

    async def on_member_join(self, member):
        guild = member.guild
        
        if not await self.config.guild(guild).user_join():
            return
        try:
            channel = await modlog.get_modlog_channel(guild)
        except:
            return
        time = datetime.datetime.utcnow()
        users = len(guild.members)
        # https://github.com/Cog-Creators/Red-DiscordBot/blob/develop/cogs/general.py
        since_created = (time - member.created_at).days
        user_created = member.created_at.strftime("%d %b %Y %H:%M")
        member_number = sorted(guild.members,
                               key=lambda m: m.joined_at).index(member) + 1

        created_on = "{}\n({} days ago)".format(user_created, since_created)
        if channel.permissions_for(guild.me).embed_links:
            name = member
            embed = discord.Embed(description=member.mention, 
                                  colour=discord.Colour.green(), 
                                  timestamp=member.created_at)
            embed.add_field(name=_("Total Users:"), value=str(users))
            embed.add_field(name=_("Account created on:"), value=created_on)
            embed.set_footer(text=_("User ID: ") + str(member.id) + _(" Created on"))
            embed.set_author(name=name.display_name + _(" has joined the guild"),
                               url=member.avatar_url, icon_url=member.avatar_url)
            embed.set_thumbnail(url=member.avatar_url)
            await channel.send(embed=embed)
        else:
            msg = (f":white_check_mark: **{member.name}#{member.discriminator}** "+
                   _("joined the guild. Total users: ") + str(users))
            await channel.send(msg)

    async def on_member_remove(self, member):
        guild = member.guild

        if not await self.config.guild(guild).user_left():
            return
        try:
            channel = await modlog.get_modlog_channel(guild)
        except:
            return
        if channel is None:
            return
        time = datetime.datetime.utcnow()
        fmt = "%H:%M:%S"
        perp = None
        reason = None
        if channel.permissions_for(guild.me).embed_links:
            if channel.permissions_for(guild.me).view_audit_log:
                action = discord.AuditLogAction.kick
                async for log in guild.audit_logs(limit=5, action=action):
                    if log.target.id == member.id:
                        perp = log.user
                        reason = log.reason
                        break
            embed = discord.Embed(description=member.mention, 
                                    colour=discord.Colour.dark_green(), 
                                    timestamp=time)
            embed.add_field(name=_("Total Users:"), 
                            value=str(len(guild.members)))
            if perp:
                embed.add_field(name=_("Kicked"), value=perp.mention)
            if reason:
                embed.add_field(name=_("Reason"), value=str(reason))
            embed.set_footer(text=_("User ID: ") + str(member.id))
            embed.set_author(name=str(member) + _(" has left the guild"),
                             url=member.avatar_url, 
                             icon_url=member.avatar_url)
            embed.set_thumbnail(url=member.avatar_url)
            await channel.send(embed=embed)
        else:
            msg = (f":x:**{member}** "+
                   _("has left the guild. Total users: ") + str(len(guild.members)))
            if perp:
                msg = (f":x:**{member}** "+
                       _("was kicked by ")+ str(perp)+
                       _(". Total users: ") + 
                       str(len(guild.members)))
            await channel.send(msg)

    async def get_permission_change(self, before, after, embed_links):
        p_msg = ""
        before_perms = {}
        after_perms = {}
        for o in before.overwrites:
            before_perms[str(o[0].id)] = [i for i in o[1]]
        for o in after.overwrites:
            after_perms[str(o[0].id)] = [i for i in o[1]]
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
                a_perms = list(a-b)
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

    async def on_guild_channel_create(self, new_channel):
        guild = new_channel.guild
        if not await self.config.guild(guild).channel_change():
            return
        try:
            channel = await modlog.get_modlog_channel(guild)
        except:
            return
        if channel is None:
            return
        embed_links = channel.permissions_for(guild.me).embed_links
        time = datetime.datetime.utcnow()
        embed = discord.Embed(description=channel.mention,
                              timestamp=time,
                              colour=discord.Colour.teal())
        embed.set_author(name=_("Channel Created ") + str(new_channel.id))
        msg = _("Channel Created ") + str(new_channel.id) + "\n"
        perp = None
        if channel.permissions_for(guild.me).view_audit_log:
            action = discord.AuditLogAction.channel_create
            async for log in guild.audit_logs(limit=5, action=action):
                if log.target.id == new_channel.id:
                    perp = log.user
                    break
        if type(new_channel) == discord.TextChannel:
            msg += _("Text Channel Created")
            embed.add_field(name=_("Type"), value=_("Text"))
        if type(new_channel) == discord.CategoryChannel:
            msg += _("Category Channel Created")
            embed.add_field(name=_("Type"), value=_("Text"))
        if type(new_channel) == discord.VoiceChannel:
            msg += _("Voice Channel Created")
            embed.add_field(name=_("Type"), value=_("Voice"))
        if perp:
            msg +=_("Created by ") + str(perp)
            embed.add_field(name=_("Created by "), value=perp.mention)
        if embed_links:
            await channel.send(embed=embed)
        else:
            await channel.send(msg)

    async def on_guild_channel_delete(self, old_channel):
        guild = old_channel.guild
        if not await self.config.guild(guild).channel_change():
            return
        try:
            channel = await modlog.get_modlog_channel(guild)
        except:
            return
        if channel is None:
            return
        embed_links = channel.permissions_for(guild.me).embed_links
        time = datetime.datetime.utcnow()
        embed = discord.Embed(description=channel.mention,
                              timestamp=time,
                              colour=discord.Colour.dark_teal())
        embed.set_author(name=_("Channel Deleted ") + str(old_channel.id))
        msg = _("Channel Deleted ") + str(old_channel.id) + "\n"
        perp = None
        if channel.permissions_for(guild.me).view_audit_log:
            action = discord.AuditLogAction.channel_delete
            async for log in guild.audit_logs(limit=5, action=action):
                if log.target.id == old_channel.id:
                    perp = log.user
                    break
        if type(old_channel) == discord.TextChannel:
            msg += _("Text Channel Deleted")
            embed.add_field(name=_("Type"), value=_("Text"))
        if type(old_channel) == discord.CategoryChannel:
            msg += _("Category Channel Deleted")
            embed.add_field(name=_("Type"), value=_("Text"))
        if type(old_channel) == discord.VoiceChannel:
            msg += _("Voice Channel Deleted")
            embed.add_field(name=_("Type"), value=_("Voice"))
        if perp:
            msg +=_("Deleted by ") + str(perp)
            embed.add_field(name=_("Deleted by "), value=perp.mention)
        if embed_links:
            await channel.send(embed=embed)
        else:
            await channel.send(msg)

    async def on_guild_channel_update(self, before, after):
        guild = before.guild
        if not await self.config.guild(guild).channel_change():
            return
        try:
            channel = await modlog.get_modlog_channel(guild)
        except:
            return
        if channel is None:
            return
        embed_links = channel.permissions_for(guild.me).embed_links
        time = datetime.datetime.utcnow()
        embed = discord.Embed(description=after.mention, 
                              timestamp=time,
                              colour=discord.Colour.teal())
        embed.set_author(name=_("Updated channel ") + str(before.id))
        msg = _("Updated channel ") + str(before.id) + "\n"
        perp = None
        if channel.permissions_for(guild.me).view_audit_log:
            action = discord.AuditLogAction.channel_update
            async for log in guild.audit_logs(limit=5, action=action):
                if log.target.id == before.id:
                    perp = log.user
                    break
        if type(before) == discord.TextChannel:
            text_updates = {"name":_("Name:"), 
                            "topic":_("Topic:"), 
                            "category":_("Category:"), 
                            "slowmode_delay":_("Slowmode delay:"),
                            }

            for attr, name in text_updates.items():
                before_attr = getattr(before, attr)
                after_attr = getattr(after, attr)
                if before_attr != after_attr:
                    if before_attr == "":
                        before_attr = "None"
                    if after_attr == "":
                        after_attr = "None"
                    msg += (_("Before ") + f"{name} {before_attr}\n")
                    msg += (_("After ") + f"{name} {after_attr}\n")
                    embed.add_field(name=_("Before ") + name, value=str(before_attr)[:1024])
                    embed.add_field(name=_("After ") + name, value=str(after_attr)[:1024])
            if before.is_nsfw() != after.is_nsfw():
                msg += (_("Before ") + f"NSFW {before.is_nsfw()}\n")
                msg += (_("After ") + f"NSFW {after.is_nsfw()}\n")
                embed.add_field(name=_("Before ") + "NSFW", value=str(before.is_nsfw()))
                embed.add_field(name=_("After ") + "NSFW", value=str(after.is_nsfw()))
            p_msg = await self.get_permission_change(before, after, embed_links)
            if p_msg != "":
                msg += _("Permissions Changed: ") + p_msg
                embed.add_field(name=_("Permissions"), value=p_msg[:1024])
            if perp:
                msg += _("Updated by ") + str(perp)
                embed.add_field(name=_("Updated by "), value=perp.mention)
            if len(embed.fields) == 0:
                return
            if embed_links:
                await channel.send(embed=embed)
            else:
                await channel.send(msg)

        if type(before) == discord.VoiceChannel:
            voice_updates = {"name":_("Name:"), 
                            "position":_("Position:"), 
                            "category":_("Category:"), 
                            "bitrate":_("Bitrate:"),
                            "user_limit":_("User limit:")
                            }
            for attr, name in voice_updates.items():
                before_attr = getattr(before, attr)
                after_attr = getattr(after, attr)
                if before_attr != after_attr:
                    msg += (_("Before ") + f"{name} {before_attr}\n")
                    msg += (_("After ") + f"{name} {after_attr}\n")
                    embed.add_field(name=_("Before ") + name, value=str(before_attr))
                    embed.add_field(name=_("After ") + name, value=str(after_attr))
            p_msg = await self.get_permission_change(before, after, embed_links)
            if p_msg != "":
                msg += _("Permissions Changed: ") + p_msg
                embed.add_field(name=_("Permissions"), value=p_msg[:1024])
            if perp:
                msg += _("Updated by ") + str(perp)
                embed.add_field(name=_("Updated by "), value=perp.mention)
            if len(embed.fields) == 0:
                return
            if channel.permissions_for(guild.me).embed_links:
                await channel.send(embed=embed)
            else:
                await channel.send(msg)

    async def get_role_permission_change(self, before, after):
        permission_list = ["create_instant_invite",
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
                           "manage_emojis"]
        p_msg = ""
        for p in permission_list:
            if getattr(before.permissions, p) != getattr(after.permissions, p):
                change = getattr(after.permissions, p)
                p_msg += f"{p} Set to {change}\n"
        return p_msg

    async def on_guild_role_update(self, before, after):
        guild = before.guild
        if not await self.config.guild(guild).role_change():
            return
        try:
            channel = await modlog.get_modlog_channel(guild)
        except:
            return
        if channel is None:
            return
        perp = None
        if channel.permissions_for(guild.me).view_audit_log:
            action = discord.AuditLogAction.role_update
            async for log in guild.audit_logs(limit=5, action=action):
                if log.target.id == before.id:
                    perp = log.user
                    break
        embed_links = channel.permissions_for(guild.me).embed_links
        time = datetime.datetime.utcnow()
        embed = discord.Embed(description=after.mention, 
                              colour=after.colour,
                              timestamp=time)
        
        if after is guild.default_role:
            embed.set_author(name=_("Updated Everyone role "),
                             icon_url=guild.icon_url)
            msg = _("Updated Everyone role ") + "\n"    
        else:
            embed.set_author(name=_("Updated role ") + str(before.id),
                             icon_url=guild.icon_url)
            msg = _("Updated role ") + str(before.id) + "\n"
        if perp:
            msg += (_("Updated by ") + f"{perp}\n")
            embed.add_field(name=_("Updated by"), value=perp.mention)
        role_updates = {"name":_("Name:"), 
                        "color":_("Colour:"), 
                        "mentionable":_("Mentionable:"), 
                        "hoist":_("Is Hoisted:"),
                        }

        for attr, name in role_updates.items():
            before_attr = getattr(before, attr)
            after_attr = getattr(after, attr)
            if before_attr != after_attr:
                if before_attr == "":
                    before_attr = "None"
                if after_attr == "":
                    after_attr = "None"
                msg += (_("Before ") + f"{name} {before_attr}\n")
                msg += (_("After ") + f"{name} {after_attr}\n")
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

    async def on_guild_role_create(self, role):
        guild = role.guild
        if not await self.config.guild(guild).role_change():
            return
        try:
            channel = await modlog.get_modlog_channel(guild)
        except:
            return
        if channel is None:
            return
        perp = None
        if channel.permissions_for(guild.me).view_audit_log:
            action = discord.AuditLogAction.role_create
            async for log in guild.audit_logs(limit=5, action=action):
                if log.target.id == role.id:
                    perp = log.user
                    break
        embed_links = channel.permissions_for(guild.me).embed_links
        time = datetime.datetime.utcnow()
        embed = discord.Embed(description=role.mention,
                              colour=discord.Colour.blue(),
                              timestamp=time)
        embed.set_author(name=_("Role created ") + str(role.id),
                         icon_url=guild.icon_url)
        msg = _("Role created ") + str(role.id) + "\n"
        msg += role.name
        if perp:
            embed.add_field(name=_("Created by"), value=perp.mention)
            msg += _("By ") + str(perp) + "\n"        
        if embed_links:
            await channel.send(embed=embed)
        else:
            await channel.send(msg)

    async def on_guild_role_delete(self, role):
        guild = role.guild
        if not await self.config.guild(guild).role_change():
            return
        try:
            channel = await modlog.get_modlog_channel(guild)
        except:
            return
        if channel is None:
            return
        perp = None
        if channel.permissions_for(guild.me).view_audit_log:
            action = discord.AuditLogAction.role_delete
            async for log in guild.audit_logs(limit=5, action=action):
                if log.target.id == role.id:
                    perp = log.user
                    break
        embed_links = channel.permissions_for(guild.me).embed_links
        time = datetime.datetime.utcnow()
        embed = discord.Embed(description=role.name,
                              timestamp=time,
                              colour=discord.Colour.dark_blue())
        embed.set_author(name=_("Role deleted ") + str(role.id))
        msg = _("Role deleted ") + str(role.id) + "\n"
        msg += role.name
        if perp:
            embed.add_field(name=_("Deleted by"), value=perp.mention)
            msg += _("By ") + str(perp) + "\n"   
        if embed_links:
            await channel.send(embed=embed)
        else:
            await channel.send(msg)

    async def on_message_edit(self, before, after):
        guild = before.guild
        if guild is None:
            return
        if before.author.bot:
            return
        if not await self.config.guild(guild).message_edit():
            return
        if before.channel.id in await self.config.guild(guild).ignored_channels():
            return
        if before.content == after.content:
            return
        cleanbefore = before.content
        for i in before.mentions:
            cleanbefore = cleanbefore.replace(i.mention, str(i))
        cleanafter = after.content
        for i in after.mentions:
            cleanafter = cleanafter.replace(i.mention, str(i))
        try:
            channel = await modlog.get_modlog_channel(guild)
        except:
            return
        if channel is None:
            return
        time = datetime.datetime.utcnow()
        fmt = "%H:%M:%S"
        if channel.permissions_for(guild.me).embed_links:
            name = before.author
            name = " ~ ".join((name.name, name.nick)) if name.nick else name.name
            
            infomessage = (_("A message by ")+
                           f"{before.author}"+
                           _(" was edited in ")+ before.channel.name)
            embed = discord.Embed(description=before.content, 
                                  colour=discord.Colour.orange(), 
                                  timestamp=before.created_at)
            jump_url = f"[Click to see new message]({after.jump_url})"
            embed.add_field(name=_("After Message:"), value=jump_url)
            embed.add_field(name=_("Channel:"), value=before.channel.mention)
            embed.set_footer(text=_("User ID: ")+str(before.author.id))
            embed.set_author(name=name + _(" - Edited Message"), 
                             icon_url=before.author.avatar_url)
            await channel.send( embed=embed)
        else:
            msg = (f":pencil: `{time.strftime(fmt)}` **"+
                   _("Channel") + f"**{before.channel.mention}"+
                   f" **{before.author.name}#{before.author.discriminator}'s** "+
                   _("message has been edited.\nBefore: ")+cleanbefore+
                   _("\nAfter: ")+cleanafter)
            await channel.send(msg)

    async def on_guild_update(self, before, after):
        guild = after
        
        if not await self.config.guild(guild).guild_change():
            return
        try:
            channel = await modlog.get_modlog_channel(guild)
        except:
            return
        if channel is None:
            return
        
        time = datetime.datetime.utcnow()
        embed = discord.Embed(timestamp=time,
                              colour=discord.Colour.blurple())
        embed.set_author(name=_("Updated Guild ") + str(before.id),
                         icon_url=guild.icon_url)
        embed.set_thumbnail(url=guild.icon_url)
        msg = _("Updated Guild ") + str(before.id) + "\n"
        guild_updates = {"name":_("Name:"), 
                        "region":_("Region:"), 
                        "afk_timeout":_("AFK Timeout:"), 
                        "afk_channel":_("AFK Channel:"),
                        "icon_url": _("Server Icon:"),
                        "owner": _("Server Owner:"),
                        "splash": _("Splash Image:"),
                        "system_channel": _("Welcome message channel:")
                        }
        for attr, name in guild_updates.items():
            before_attr = getattr(before, attr)
            after_attr = getattr(after, attr)
            if before_attr != after_attr:
                msg += (_("Before ") + f"{name} {before_attr}\n")
                msg += (_("After ") + f"{name} {after_attr}\n")
                embed.add_field(name=_("Before ") + name, value=str(before_attr))
                embed.add_field(name=_("After ") + name, value=str(after_attr))
        perp = []
        if channel.permissions_for(guild.me).view_audit_log:
            action = discord.AuditLogAction.guild_update
            async for log in guild.audit_logs(limit=int(len(embed.fields)/2), action=action):
                perp.append(log.user)
        if perp:
            perps = ", ".join(str(p) for p in perp)
            msg += (_("Update by ") + f"{perps}\n")
            perps = ", ".join(p.mention for p in perp)
            embed.add_field(name=_("Updated by"), value=perps)
        if channel.permissions_for(guild.me).embed_links:
            await channel.send(embed=embed)
        else:
            await channel.send(msg)

    async def on_guild_emojis_update(self, guild, before, after):
        if not await self.config.guild(guild).guild_change():
            return
        try:
            channel = await modlog.get_modlog_channel(guild)
        except:
            return
        if channel is None:
            return
        perp = None
        
        time = datetime.datetime.utcnow()
        embed = discord.Embed(description= "", 
                              timestamp=time,
                              colour=discord.Colour.gold())
        embed.set_author(name=_("Updated Server Emojis"), 
                         icon_url=guild.icon_url)
        msg = _("Updated Server Emojis") + "\n"
        b = set(before)
        a = set(after)
        added_emoji = [list(a-b)][0]
        removed_emoji = [list(b-a)][0]
        changed_emoji = [list(set([e.name for e in after]) - set([e.name for e in before]))][0]
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
        if channel.permissions_for(guild.me).view_audit_log:
            async for log in guild.audit_logs(limit=1, action=action):
                perp = log.user
                break
        if perp:
            embed.add_field(name=_("Updated by "), value=perp.mention)
            msg += _("Updated by ") + str(perp)
        if channel.permissions_for(guild.me).embed_links:
            await channel.send(embed=embed)
        else:
            await channel.send(msg)


    async def on_voice_state_update(self, member, before, after):
        guild = member.guild
        if not await self.config.guild(guild).voice_change():
            return
        if member.bot:
            return
        try:
            channel = await modlog.get_modlog_channel(guild)
        except:
            return
        if channel is None:
            return
        time = datetime.datetime.utcnow()
        embed = discord.Embed(timestamp=time, 
                              icon_url=guild.icon_url,
                              colour=discord.Colour.magenta())
        msg = (f"{member} " +
               _("Updated Voice State") + "\n")
        embed.set_author(name=msg)
        change_type = None
        if before.deaf != after.deaf:
            change_type = "deaf"
            if after.deaf:
                chan_msg = (member.mention + _(" was deafened. "))
                msg += chan_msg + "\n"
                embed.description = chan_msg
            else:
                chan_msg = (member.mention + _(" was undeafened. "))
                msg += chan_msg + "\n"
                embed.description = chan_msg
        if before.mute != after.mute:
            change_type = "mute"
            if after.mute:
                chan_msg = (member.mention + _(" was muted. "))
                msg += chan_msg + "\n"
                embed.description = chan_msg
            else:
                chan_msg = (member.mention + _(" was unmuted. "))
                msg += chan_msg + "\n"
                embed.description = chan_msg
        if before.channel != after.channel:
            change_type = "channel"
            if before.channel is None:
                chan_msg = (member.mention + _(" has joined ") + 
                            after.channel.mention)
                msg += chan_msg + "\n"
                embed.description = chan_msg
            elif after.channel is None:
                chan_msg = (member.mention + _(" has left ") + 
                            before.channel.mention)
                msg += chan_msg + "\n"
                embed.description = chan_msg
            else:
                chan_msg = (member.mention + _(" has moved from ") + 
                            before.channel.mention + _(" to ") + 
                            after.channel.mention)
                msg += chan_msg
                embed.description = chan_msg
        perp = None
        if channel.permissions_for(guild.me).view_audit_log and change_type:
            action = discord.AuditLogAction.member_update
            async for log in guild.audit_logs(limit=5, action=action):
                is_change = getattr(log.after, change_type, None)
                if log.target.id == member.id and is_change:
                    perp = log.user
                    break
        if perp:
            embed.add_field(name=_("Updated by"), value=perp.mention)
        if channel.permissions_for(guild.me).embed_links:
            await channel.send(embed=embed)
        else:
            await channel.send(msg.replace(member.mention, str(member)))


    async def on_member_update(self, before, after):
        guild = before.guild
        if not await self.config.guild(guild).user_change():
            return
        try:
            channel = await modlog.get_modlog_channel(guild)
        except:
            return
        if channel is None:
            return
        embed_links = channel.permissions_for(guild.me).embed_links
        time = datetime.datetime.utcnow()
        embed = discord.Embed(timestamp=time,
                              colour=discord.Colour.greyple())
        msg = f"{before.name}#{before.discriminator} " + _("Updated") + "\n"
        org_len = len(msg)
        embed.set_author(name=msg, icon_url=before.avatar_url)
        member_updates = {"nick":_("Nickname:"), 
                          "roles":_("Roles:"),
                         }
        perp = None
        for attr, name in member_updates.items():
            before_attr = getattr(before, attr)
            after_attr = getattr(after, attr)
            if before_attr != after_attr:
                if attr == "roles":
                    b = set(before.roles)
                    a = set(after.roles)
                    before_roles = [list(b-a)][0]
                    after_roles = [list(a-b)][0]
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
                                break
                else:
                    if channel.permissions_for(guild.me).view_audit_log:
                        action = discord.AuditLogAction.member_update
                        async for log in guild.audit_logs(limit=5, action=action):
                            if log.target.id == before.id:
                                perp = log.user
                                break
                    msg += (_("Before ") + f"{name} {before_attr}\n")
                    msg += (_("After ") + f"{name} {after_attr}\n")
                    embed.add_field(name=_("Before ") + name, value=str(before_attr)[:1024])
                    embed.add_field(name=_("After ") + name, value=str(after_attr)[:1024])
        if len(msg) == org_len:
            return
        if perp:
            msg += (_("Updated by ") + f"{perp}\n")
            embed.add_field(name=_("Updated by "), value=perp.mention)
        if embed_links:
            await channel.send(embed=embed)
        else:
            await channel.send(msg)

