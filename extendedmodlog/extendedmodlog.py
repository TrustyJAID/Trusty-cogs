from redbot.core import commands, checks, Config, modlog
import datetime
import discord
import asyncio
from random import choice, randint
from redbot.core.i18n import Translator, cog_i18n

inv_settings = {"message_edit": False, 
                "message_delete": False, 
                "user_change": False,
                "voice_change": False,
                "user_join": False, 
                "user_left": False, 
                "channel_change": False,
                "guild_change": False,
                "emoji_change": False}

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
        self.config.register_guild(**inv_settings)

    @checks.admin_or_permissions(manage_channels=True)
    @commands.group(name="modlogtoggles")
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
                            "voice_change": _("Voice changes"),
                            "user_join": _("User join"), 
                            "user_left": _("Member left"), 
                            "channel_change": _("Channel changes"),
                            "guild_change": _("Guild changes"),
                            "emoji_change": _("Emoji changes")}
            try:
                e = discord.Embed(title=_("Setting for ") + guild.name)
                e.colour = await self.get_colour(ctx.guild)
                e.description = _("ModLogs channel set to ") + modlog_channel.mention
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
                e.add_field(name=_("Enabled"), value=enabled[:-2])
                e.add_field(name=_("Disabled"), value=disabled[:-2])
                e.set_thumbnail(url=guild.icon_url)
                await ctx.send(embed=e)
            except Exception as e:
                print(e)
                return

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

    @modlogtoggles.command()
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

    @modlogtoggles.command()
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

    @modlogtoggles.command()
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

    async def get_colour(self, guild):
        if await self.bot.db.guild(guild).use_bot_color():
            return guild.me.colour
        else:
            return await self.bot.db.color()

    async def on_message_delete(self, message):
        guild = message.guild
        if guild is None:
            return
        if not await self.config.guild(guild).message_delete():
            return
        if message.author is message.author.bot:
            pass
        try:
            channel = await modlog.get_modlog_channel(guild)
        except:
            return
        time = message.created_at
        cleanmsg = message.content
        for i in message.mentions:
            cleanmsg = cleanmsg.replace(i.mention, str(i))
        fmt = "%H:%M:%S"
        if channel.permissions_for(guild.me).embed_links:
            name = message.author
            name = " ~ ".join((name.name, name.nick)) if name.nick else name.name
            infomessage = (_("A message by ")+
                           message.author.mention+
                           _(", was deleted in ")+
                            message.channel.mention)
            delmessage = discord.Embed(description=infomessage, colour=await self.get_colour(guild), timestamp=time)
            delmessage.add_field(name=_("Message:"), value=cleanmsg)
            delmessage.set_footer(text=_("User ID: ")+ str(message.author.id), 
                                  icon_url=message.author.avatar_url)
            delmessage.set_author(name=name + _(" - Deleted Message"), 
                                  url="http://i.imgur.com/fJpAFgN.png", 
                                  icon_url=message.author.avatar_url)
            delmessage.set_thumbnail(url="http://i.imgur.com/fJpAFgN.png")
            await channel.send(embed=delmessage)
        else:
            msg = (":pencil: `"+time.strftime(fmt)+"` **"+
                   _("Channel") + "**" +message.channel.mention+
                   " **"+message.author+"'s** "+
                    _("message has been deleted. Content: ")+
                   cleanmsg)
            await channel.send(msg)

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
        if channel.permissions_for(guild.me).embed_links:
            name = member
            joinmsg = discord.Embed(description=member.mention, colour=await self.get_colour(guild), 
                                    timestamp=member.joined_at)
            joinmsg.add_field(name=_("Total Users:"), value=str(users), inline=True)
            joinmsg.set_footer(text=_("User ID: ") + str(member.id), icon_url=member.avatar_url)
            joinmsg.set_author(name=name.display_name + _(" has joined the guild"),
                               url=member.avatar_url, icon_url=member.avatar_url)
            joinmsg.set_thumbnail(url=member.avatar_url)
            await channel.send(embed=joinmsg)
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
        users = len([e.name for e in guild.members])
        if channel.permissions_for(guild.me).embed_links:
            name = member
            joinmsg = discord.Embed(description=member.mention, colour=await self.get_colour(guild), timestamp=time)
            joinmsg.add_field(name=_("Total Users:"), value=str(users), inline=True)
            joinmsg.set_footer(text=_("User ID: ") + str(member.id), icon_url=member.avatar_url)
            joinmsg.set_author(name=name.display_name + _(" has left the guild"),
                               url=member.avatar_url, icon_url=member.avatar_url)
            joinmsg.set_thumbnail(url=member.avatar_url)
            await channel.send( embed=joinmsg)
        else:
            msg = (f":x:**{member.name}#{member.discriminator}** "+
                   _("has left the guild or was kicked. Total users: ") + str(users))
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
        embed = discord.Embed(description=after.mention, timestamp=time)
        embed.colour = await self.get_colour(guild)
        embed.set_author(name=_("Updated channel ") + str(before.id))
        msg = _("Updated channel ") + str(before.id) + "\n"
        if type(before) == discord.TextChannel:
            text_updates = {"name":_("Name:"), 
                            "topic":_("Topic:"), 
                            "position":_("Position:"), 
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
                    embed.add_field(name=_("Before ") + name, value=str(before_attr))
                    embed.add_field(name=_("After ") + name, value=str(after_attr))
            if before.is_nsfw() != after.is_nsfw():
                msg += (_("Before ") + f"NSFW {before.is_nsfw()}\n")
                msg += (_("After ") + f"NSFW {after.is_nsfw()}\n")
                embed.add_field(name=_("Before ") + "NSFW", value=str(before.is_nsfw()))
                embed.add_field(name=_("After ") + "NSFW", value=str(after.is_nsfw()))
            p_msg = await self.get_permission_change(before, after, embed_links)
            if p_msg != "":
                msg += _("Permissions Changed: ") + p_msg
                embed.add_field(name=_("Permissions"), value=p_msg[:1024])
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
            if channel.permissions_for(guild.me).embed_links:
                await channel.send(embed=embed)
            else:
                await channel.send(msg)      

    async def on_message_edit(self, before, after):
        guild = before.guild
        
        if before.author.bot:
            return
        if not await self.config.guild(guild).message_edit():
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
            
            infomessage = (_("A message by ")+before.author.mention+
                           _(", was edited in ")+ before.channel.mention)
            delmessage = discord.Embed(description=infomessage, 
                                       colour=await self.get_colour(guild), 
                                       timestamp=before.created_at)
            delmessage.add_field(name=_("Before Message:"), value=cleanbefore, inline=False)
            delmessage.add_field(name=_("After Message:"), value=cleanafter)
            delmessage.set_footer(text=_("User ID: ")+str(before.author.id), icon_url=before.author.avatar_url)
            delmessage.set_author(name=name + _(" - Edited Message"), 
                                  url="http://i.imgur.com/Q8SzUdG.png", 
                                  icon_url=before.author.avatar_url)
            delmessage.set_thumbnail(url="http://i.imgur.com/Q8SzUdG.png")
            await channel.send( embed=delmessage)
        else:
            msg = (f":pencil: `{time.strftime(fmt)}` **"+
                   _("Channel") + f"**{message.channel.mention}"+
                   f" **{before.author.name}#{before.author.discriminator}'s** "+
                   _("message has been edited.\nBefore: ")+cleanbefore+
                   _("\nAfter: ")+cleanafter)
            await channel.send(msg)

    async def on_guild_update(self, before, after):
        guild = before
        
        if not await self.config.guild(guild).guild_change():
            return
        try:
            channel = await modlog.get_modlog_channel(guild)
        except:
            return
        if channel is None:
            return
        time = datetime.datetime.utcnow()
        embed = discord.Embed(timestamp=time)
        embed.colour = await self.get_colour(guild)
        embed.set_author(name=_("Updated Guild ") + str(before.id),
                         icon_url=guild.icon_url)
        msg = _("Updated Guild ") + str(before.id) + "\n"
        guild_updates = {"name":_("Name:"), 
                        "region":_("Region:"), 
                        "afk_timeout":_("AFK Timeout:"), 
                        "afk_channel":_("AFK Channel:")
                        }
        for attr, name in guild_updates.items():
            before_attr = getattr(before, attr)
            after_attr = getattr(after, attr)
            if before_attr != after_attr:
                msg += (_("Before ") + f"{name} {before_attr}\n")
                msg += (_("After ") + f"{name} {after_attr}\n")
                embed.add_field(name=_("Before ") + name, value=str(before_attr))
                embed.add_field(name=_("After ") + name, value=str(after_attr))
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
        time = datetime.datetime.utcnow()
        embed = discord.Embed(description= "", timestamp=time)
        embed.colour = await self.get_colour(guild)
        embed.set_author(name=_("Updated Server Emojis"), icon_url=guild.icon_url)
        msg = _("Updated Server Emojis") + "\n"
        for emoji in before:
            if emoji not in after:
                new_msg = str(emoji) + _(" Removed from the guild\n")
                msg += new_msg
                embed.description += new_msg
        for emoji in after:
            if emoji not in before:
                new_msg = str(emoji) + _(" Added to the guild\n")
                msg += new_msg
                embed.description += new_msg
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
        embed = discord.Embed(timestamp=time, icon_url=guild.icon_url)
        embed.colour = await self.get_colour(guild)
        msg = f"{member.name}#{member.discriminator} " + _("Updated Voice State") + "\n"
        embed.set_author(name=msg)
        voice_updates = {"deaf":_("Deaf:"), 
                        "mute":_("Mute:"), 
                        "self_deaf":_("Self Deaf:"), 
                        "self_mute":_("Self Mute:"),
                        "afk":_("AFK:"),
                        "channel":_("Channel:")
                        }
        for attr, name in voice_updates.items():
            before_attr = getattr(before, attr)
            after_attr = getattr(after, attr)
            if before_attr != after_attr:
                msg += (_("Before ") + f"{name} {before_attr}\n")
                msg += (_("After ") + f"{name} {after_attr}\n")
                embed.add_field(name=_("Before ") + name, value=str(before_attr))
                embed.add_field(name=_("After ") + name, value=str(after_attr))
        if channel.permissions_for(guild.me).embed_links:
            await channel.send(embed=embed)
        else:
            await channel.send(msg)


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
        embed = discord.Embed(timestamp=time)
        embed.colour = await self.get_colour(guild)
        msg = f"{before.name}#{before.discriminator} " + _("Updated") + "\n"
        org_len = len(msg)
        embed.set_author(name=msg, icon_url=before.avatar_url)
        member_updates = {"nick":_("Nickname:"), 
                          "roles":_("Roles:"),
                         }
        for attr, name in member_updates.items():
            before_attr = getattr(before, attr)
            after_attr = getattr(after, attr)
            if before_attr != after_attr:
                if attr == "roles":
                    for role in before.roles:
                        if role not in after.roles:
                            msg += role.name + _(" Role Applied.")
                            if embed_links:
                                embed.description = role.mention + _(" Role Applied.")
                            else:
                                embed.description = msg
                    for role in after.roles:
                        if role not in before.roles:
                            msg += role.name + _(" Role Removed.")
                            if embed_links:
                                embed.description = role.mention + _(" Role Removed.")
                            else:
                                embed.description = msg
                else:
                    msg += (_("Before ") + f"{name} {before_attr}\n")
                    msg += (_("After ") + f"{name} {after_attr}\n")
                    embed.add_field(name=_("Before ") + name, value=str(before_attr)[:1024])
                    embed.add_field(name=_("After ") + name, value=str(after_attr)[:1024])
        if len(msg) == org_len:
            return
        if embed_links:
            await channel.send(embed=embed)
        else:
            await channel.send(msg)

