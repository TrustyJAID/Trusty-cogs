from redbot.core import commands
from redbot.core import checks
from redbot.core import Config
import datetime
import discord
import asyncio
import os
from random import choice, randint

inv_settings = {"embed": False, "Channel": None, "toggleedit": False, "toggledelete": False, "toggleuser": False,
                "toggleroles": False,
                "togglevoice": False,
                "toggleban": False, "togglejoin": False, "toggleleave": False, "togglechannel": False,
                "toggleguild": False}


class ModLogs(getattr(commands, "Cog", object)):
    """
        Custom modlogs with embeds
    """

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, 154457677895)
        self.config.register_guild(**inv_settings)

    @checks.admin_or_permissions(administrator=True)
    @commands.group(name='modlogtoggle', )
    async def modlogtoggles(self, ctx):
        """toggle which guild activity to log"""
        if await self.config.guild(ctx.message.guild).settings() == {}:
            await self.config.guild(ctx.message.guild).set(inv_settings)
        if ctx.invoked_subcommand is None:
            guild = ctx.message.guild
            
            try:
                e = discord.Embed(title="Setting for {}".format(guild.name), colour=discord.Colour.blue())
                e.description = "ModLogs channel set to {}".format(self.bot.get_channel(id=await self.config.guild(guild).Channel()).mention)
                e.add_field(name="Delete", value=str(await self.config.guild(guild).toggledelete()))
                e.add_field(name="Edit", value=str(await self.config.guild(guild).toggleedit()))
                e.add_field(name="Roles", value=str(await self.config.guild(guild).toggleroles()))
                e.add_field(name="User", value=str(await self.config.guild(guild).toggleuser()))
                e.add_field(name="Voice", value=str(await self.config.guild(guild).togglevoice()))
                e.add_field(name="Ban", value=str(await self.config.guild(guild).toggleban()))
                e.add_field(name="Join", value=str(await self.config.guild(guild).togglejoin()))
                e.add_field(name="Leave", value=str(await self.config.guild(guild).toggleleave()))
                e.add_field(name="Channel", value=str(await self.config.guild(guild).togglechannel()))
                e.add_field(name="guild", value=str(await self.config.guild(guild).toggleguild()))
                e.set_thumbnail(url=guild.icon_url)
                await ctx.send(embed=e)
            except Exception as e:
                print(e)
                return

    @checks.admin_or_permissions(administrator=True)
    @commands.group()
    async def modlogsetup(self, ctx):
        """Change modlog settings"""
        pass

    @modlogsetup.command(name='channel')
    async def _channel(self, ctx):
        """Set the channel to send notifications too"""
        guild = ctx.message.guild
        # print(guild)
        if ctx.message.guild.me.permissions_in(ctx.message.channel).send_messages:
            # print(await self.config.guild(guild).Channel())
            if await self.config.guild(guild).Channel() is not None:
                await self.config.guild(guild).Channel.set(ctx.message.channel.id)
                await ctx.send("Channel changed.")
                return
            else:
                await self.config.guild(guild).Channel.set(ctx.message.channel.id)
                await ctx.send("I will now send toggled modlog notifications here")
        else:
            return

    @modlogsetup.command()
    async def embed(self, ctx):
        """Enables or disables embed modlog."""
        guild = ctx.message.guild
        if await self.config.guild(guild).embed() == False:
            await self.config.guild(guild).embed.set(True)
            
            await ctx.send("Enabled embed modlog.")
        elif await self.config.guild(guild).embed() == True:
            await self.config.guild(guild).embed.set(False)
            
            await ctx.send("Disabled embed modlog.")

    @modlogsetup.command()
    async def disable(self, ctx):
        """disables the modlog"""
        guild = ctx.message.guild
        
        if await self.config.guild(guild).Channel() is None:
            await ctx.send("guild not found, use modlogsetup to set a channnel")
            return
        await self.config.guild(guild).Channel.set(None)
        
        await ctx.send("I will no longer send modlog notifications here")

    @modlogtoggles.command()
    async def edit(self, ctx):
        """toggle notifications when a member edits their message"""
        guild = ctx.message.guild
        
        if await self.config.guild(guild).toggleedit() == False:
            await self.config.guild(guild).toggleedit.set(True)
            
            await ctx.send("Edit messages enabled")
        elif await self.config.guild(guild).toggleedit() == True:
            await self.config.guild(guild).toggleedit.set(False)
            
            await ctx.send("Edit messages disabled")

    @modlogtoggles.command()
    async def join(self, ctx):
        """toggles notofications when a member joins the guild."""
        guild = ctx.message.guild
        
        if await self.config.guild(guild).togglejoin() == False:
            await self.config.guild(guild).togglejoin.set(True)
            
            await ctx.send("Enabled join logs.")
        elif await self.config.guild(guild).togglejoin() == True:
            await self.config.guild(guild).togglejoin.set(False)
            
            await ctx.send("Disabled join logs.")

    @modlogtoggles.command()
    async def guild(self, ctx):
        """toggles notofications when the guild updates."""
        guild = ctx.message.guild
        
        if await self.config.guild(guild).toggleguild() == False:
            await self.config.guild(guild).toggleguild.set(True)
            
            await ctx.send("Enabled guild logs.")
        elif await self.config.guild(guild).toggleguild() == True:
            await self.config.guild(guild).toggleguild.set(False)
            
            await ctx.send("Disabled guild logs.")

    @modlogtoggles.command()
    async def channel(self, ctx):
        """toggles channel update logging for the guild."""
        guild = ctx.message.guild
        
        if await self.config.guild(guild).togglechannel() == False:
            await self.config.guild(guild).togglechannel.set(True)
            
            await ctx.send("Enabled channel logs.")
        elif await self.config.guild(guild).togglechannel() == True:
            await self.config.guild(guild).togglechannel.set(False)
            
            await ctx.send("Disabled channel logs.")

    @modlogtoggles.command()
    async def leave(self, ctx):
        """toggles notofications when a member leaves the guild."""
        guild = ctx.message.guild
        
        if await self.config.guild(guild).toggleleave() == False:
            await self.config.guild(guild).toggleleave.set(True)
            
            await ctx.send("Enabled leave logs.")
        elif await self.config.guild(guild).toggleleave() == True:
            await self.config.guild(guild).toggleleave.set(False)
            
            await ctx.send("Disabled leave logs.")

    @modlogtoggles.command()
    async def delete(self, ctx):
        """toggle notifications when a member delete theyre message"""
        guild = ctx.message.guild
        
        if await self.config.guild(guild).toggledelete() == False:
            await self.config.guild(guild).toggledelete.set(True)
            
            await ctx.send("Delete messages enabled")
        elif await self.config.guild(guild).toggledelete() == True:
            await self.config.guild(guild).toggledelete.set(False)
            
            await ctx.send("Delete messages disabled")

    @modlogtoggles.command()
    async def user(self, ctx):
        """toggle notifications when a user changes their profile"""
        guild = ctx.message.guild
        
        if await self.config.guild(guild).toggleuser() == False:
            await self.config.guild(guild).toggleuser.set(True)
            
            await ctx.send("User messages enabled")
        elif await self.config.guild(guild).toggleuser() == True:
            await self.config.guild(guild).toggleuser.set(False)
            
            await ctx.send("User messages disabled")

    @modlogtoggles.command()
    async def roles(self, ctx):
        """toggle notifications when roles change"""
        guild = ctx.message.guild
        
        if await self.config.guild(guild).toggleroles() == False:
            await self.config.guild(guild).toggleroles.set(True)
            await ctx.send("Role messages enabled")
        elif await self.config.guild(guild).toggleroles() == True:
            await self.config.guild(guild).toggleroles.set(False)
            await ctx.send("Role messages disabled")

    @modlogtoggles.command()
    async def voice(self, ctx):
        """toggle notifications when voice status change"""
        guild = ctx.message.guild
        
        if await self.config.guild(guild).togglevoice() == False:
            await self.config.guild(guild).togglevoice.set(True)
            await ctx.send("Voice messages enabled")
        elif await self.config.guild(guild).togglevoice() == True:
            await self.config.guild(guild).togglevoice.set(False)
            await ctx.send("Voice messages disabled")

    @modlogtoggles.command()
    async def ban(self, ctx):
        """toggle notifications when a user is banned"""
        guild = ctx.message.guild
        
        if await self.config.guild(guild).toggleban() == False:
            await self.config.guild(guild).toggleban.set(True)
            
            await ctx.send("Ban messages enabled")
        elif await self.config.guild(guild).toggleban() == True:
            await self.config.guild(guild).toggleban.set(False)
            
            await ctx.send("Ban messages disabled")

    async def on_message_delete(self, message):
        guild = message.guild
        
        if await self.config.guild(guild).Channel() is None:
            return
        if await self.config.guild(guild).toggledelete() == False:
            return
        if message.author is message.author.bot:
            pass
        channel = await self.config.guild(guild).Channel()
        if channel is None:
            return
        time = datetime.datetime.utcnow()
        cleanmsg = message.content
        for i in message.mentions:
            cleanmsg = cleanmsg.replace(i.mention, str(i))
        fmt = '%H:%M:%S'
        if await self.config.guild(guild).embed() == True:
            name = message.author
            name = " ~ ".join((name.name, name.nick)) if name.nick else name.name
            infomessage = "A message by {}, was deleted in {}".format(message.author.mention, message.channel.mention)
            delmessage = discord.Embed(description=infomessage, colour=discord.Color.purple(), timestamp=time)
            delmessage.add_field(name="Message:", value=cleanmsg)
            delmessage.set_footer(text="User ID: {}".format(message.author.id), icon_url=message.author.avatar_url)
            delmessage.set_author(name=name + " - Deleted Message", url="http://i.imgur.com/fJpAFgN.png", icon_url=message.author.avatar_url)
            delmessage.set_thumbnail(url="http://i.imgur.com/fJpAFgN.png")
            try:
                await guild.get_channel(channel).send( embed=delmessage)
            except:
                pass
        else:
            msg = ":pencil: `{}` **Channel** {} **{}'s** message has been deleted. Content: {}".format(
                time.strftime(fmt), message.channel.mention, message.author, cleanmsg)
            await guild.get_channel(channel).send(
                                        msg)

    async def on_member_join(self, member):
        guild = member.guild
        
        if await self.config.guild(guild).togglejoin() == False:
            return
        channel = await self.config.guild(guild).Channel()
        if channel is None:
            return
        time = datetime.datetime.utcnow()
        fmt = '%H:%M:%S'
        users = len([e.name for e in guild.members])
        if await self.config.guild(guild).embed() == True:
            name = member
            # name = " ~ ".join((name.name, name.nick)) if name.nick else name.name
            joinmsg = discord.Embed(description=member.mention, colour=discord.Color.red(), timestamp=member.joined_at)
            # infomessage = "Total Users: {}".format(users)
            joinmsg.add_field(name="Total Users:", value=str(users), inline=True)
            joinmsg.set_footer(text="User ID: {}".format(member.id), icon_url=member.avatar_url)
            joinmsg.set_author(name=name.display_name + " has joined the guild",url=member.avatar_url, icon_url=member.avatar_url)
            joinmsg.set_thumbnail(url=member.avatar_url)
            try:
                await guild.get_channel(channel).send( embed=joinmsg)
            except:
                pass
        if await self.config.guild(guild).embed() == False:
            msg = ":white_check_mark: `{}` **{}** join the guild. Total users: {}.".format(time.strftime(fmt),
                                                                                            member.name, users)
            await guild.get_channel(channel).send( msg)

    async def on_member_remove(self, member):
        guild = member.guild

        if await self.config.guild(guild).toggleleave() == False:
            return
        channel = await self.config.guild(guild).Channel()
        if channel is None:
            return
        time = datetime.datetime.utcnow()
        fmt = "%H:%M:%S"
        users = len([e.name for e in guild.members])
        if await self.config.guild(guild).embed() == True:
            name = member
            # name = " ~ ".join((name.name, name.nick)) if name.nick else name.name
            joinmsg = discord.Embed(description=member.mention, colour=discord.Color.red(), timestamp=time)
            # infomessage = "Total Users: {}".format(users)
            joinmsg.add_field(name="Total Users:", value=str(users), inline=True)
            joinmsg.set_footer(text="User ID: {}".format(member.id), icon_url=member.avatar_url)
            joinmsg.set_author(name=name.display_name + " has left the guild",url=member.avatar_url, icon_url=member.avatar_url)
            joinmsg.set_thumbnail(url=member.avatar_url)
            try:
                await guild.get_channel(channel).send( embed=joinmsg)
            except:
                pass
        if await self.config.guild(guild).embed() == False:
            msg = ":x: `{}` **{}** has left the guild or was kicked. Total members {}.".format(time.strftime(fmt),
                                                                                                member.name, users)
            await guild.get_channel(channel).send( msg)

    async def on_channel_update(self, before, after):
        guild = before.guild
    
        if await self.config.guild(guild).togglechannel() == False:
            return
        channel = await self.config.guild(guild).Channel()
        if channel is None:
            return
        time = datetime.datetime.utcnow()
        fmt = "%H:%M:%S"
        msg = ""
        if before.name != after.name:
            if before.type == discord.ChannelType.voice:
                if await self.config.guild(guild).embed() == True:
                    fmt = "%H:%M:%S"
                    voice1 = discord.Embed(colour=discord.Color.blue(), timestamp=time)
                    infomessage = ":loud_sound: Voice channel name update. Before: **{}** After: **{}**.".format(
                        before.name, after.name)
                    voice1.add_field(name="Info:", value=infomessage, inline=False)
                    voice1.set_author(name=time.strftime(fmt) + " - Voice Channel Update",
                                      icon_url="http://www.hey.fr/fun/emoji/twitter/en/icon/twitter/565-emoji_twitter_speaker_with_three_sound_waves.png")
                    voice1.set_thumbnail(
                        url="http://www.hey.fr/fun/emoji/twitter/en/icon/twitter/565-emoji_twitter_speaker_with_three_sound_waves.png")
                    try:
                        await guild.get_channel(channel).send( embed=voice1)
                    except:
                        pass
                else:
                    fmt = "%H:%M:%S"
                    await guild.get_channel(channel).send(
                                                ":loud_sound: `{}` Voice channel name update. Before: **{}** After: **{}**.".format(
                                                    time.strftime(fmt), before.name, after.name))
            if before.type == discord.ChannelType.text:
                if await self.config.guild(guild).embed() == True:
                    fmt = "%H:%M:%S"
                    text1 = discord.Embed(colour=discord.Color.blue(), timestamp=time)
                    infomessage = ":loud_sound: Text channel name update. Before: **{}** After: **{}**.".format(
                        before.name, after.name)
                    text1.add_field(name="Info:", value=infomessage, inline=False)
                    text1.set_author(name=time.strftime(fmt) + " - Voice Channel Update",
                                     icon_url="https://s-media-cache-ak0.pinimg.com/originals/27/18/77/27187782801d15f756a27156105d1233.png")
                    text1.set_thumbnail(
                        url="https://s-media-cache-ak0.pinimg.com/originals/27/18/77/27187782801d15f756a27156105d1233.png")
                    await guild.get_channel(channel).send( embed=text1)
                else:
                    fmt = "%H:%M:%S"
                    await guild.get_channel(channel).send(
                                                ":page_facing_up: `{}` Text channel name update. Before: **{}** After: **{}**.".format(
                                                    time.strftime(fmt), before.name, after.name))
        if before.topic != after.topic:
            if await self.config.guild(guild).embed() == True:
                fmt = "%H:%M:%S"
                topic = discord.Embed(colour=discord.Colour.blue(), timestamp=time)
                infomessage = ":page_facing_up: `{}` Channel topic has been updated.\n**Before:** {}\n**After:** {}".format(
                    time.strftime(fmt), before.topic, after.topic)
                topic.add_field(name="Info:", value=infomessage, inline=False)
                topic.set_author(name=time.strftime(fmt) + " - Channel Topic Update",
                                 icon_url="https://s-media-cache-ak0.pinimg.com/originals/27/18/77/27187782801d15f756a27156105d1233.png")
                topic.set_thumbnail(
                    url="https://s-media-cache-ak0.pinimg.com/originals/27/18/77/27187782801d15f756a27156105d1233.png")
                try:
                    await self.send_message(guild.get_channel(channel), embed=topic)
                except:
                    pass
            else:
                fmt = "%H:%M:%S"
                await guild.get_channel(channel).send(
                                            ":page_facing_up: `{}` Channel topic has been updated.\n**Before:** {}\n**After:** {}".format(
                                                time.strftime(fmt), before.topic, after.topic))
        if before.position != after.position:
            if before.type == discord.ChannelType.voice:
                if await self.config.guild(guild).embed() == True:
                    fmt = "%H:%M:%S"
                    voice2 = discord.Embed(colour=discord.Colour.blue(), timestamp=time)
                    voice2.set_thumbnail(
                        url="http://www.hey.fr/fun/emoji/twitter/en/icon/twitter/565-emoji_twitter_speaker_with_three_sound_waves.png")
                    voice2.set_author(name=time.strftime(fmt) + " Voice Channel Position Update",
                                      icon_url="http://www.hey.fr/fun/emoji/twitter/en/icon/twitter/565-emoji_twitter_speaker_with_three_sound_waves.png")
                    infomsg = ":loud_sound: Voice channel position update. Channel: **{}** Before: **{}** After: **{}**.".format(
                        before.name, before.position, after.position)
                    voice2.add_field(name="Info:", value=infomsg, inline=False)
                    try:
                        await guild.get_channel(channel).send( embed=voice2)
                    except:
                        pass
                else:
                    fmt = "%H:%M:%S"
                    await guild.get_channel(channel).send(
                                                ":loud_sound: `{}` Voice channel position update. Channel: **{}** Before: **{}** After: **{}**.".format(
                                                    time.strftime(fmt), before.name, before.position, after.position))
            if before.type == discord.ChannelType.text:
                if await self.config.guild(guild).embed() == True:
                    fmt = "%H:%M:%S"
                    text2 = discord.Embed(colour=discord.Colour.blue(), timestamp=time)
                    text2.set_thumbnail(
                        url="https://s-media-cache-ak0.pinimg.com/originals/27/18/77/27187782801d15f756a27156105d1233.png")
                    text2.set_author(name=time.strftime(fmt) + " Text Channel Position Update",
                                     icon_url="https://s-media-cache-ak0.pinimg.com/originals/27/18/77/27187782801d15f756a27156105d1233.png")
                    infomsg = ":page_facing_up: Text channel position update. Before: **{}** After: **{}**.".format(
                        before.position, after.position)
                    text2.add_field(name="Info:", value=infomsg, inline=False)
                    try:
                        await guild.get_channel(channel).send( embed=text2)
                    except:
                        pass
                else:
                    fmt = "%H:%M:%S"
                    await guild.get_channel(channel).send(
                                                ":page_facing_up: `{}` Text channel position update. Channel: **{}** Before: **{}** After: **{}**.".format(
                                                    time.strftime(fmt), before.name, before.position, after.position))
        if before.bitrate != after.bitrate:
            if await self.config.guild(guild).embed() == True:
                fmt = "%H:%M:%S"
                bitrate = discord.Embed(colour=discord.Colour.blue(), timestamp=time)
                bitrate.set_author(name=time.strftime(fmt) + " Voice Channel Bitrate Update",
                                   icon_url="http://www.hey.fr/fun/emoji/twitter/en/icon/twitter/565-emoji_twitter_speaker_with_three_sound_waves.png")
                bitrate.set_thumbnail(
                    url="http://www.hey.fr/fun/emoji/twitter/en/icon/twitter/565-emoji_twitter_speaker_with_three_sound_waves.png")
                infomsg = ":loud_sound: Voice Channel bitrate update. Before: **{}** After: **{}**.".format(
                    before.bitrate, after.bitrate)
                bitrate.add_field(name="Info:", value=infomsg, inline=False)
                try:
                    await sef.bot.send_message(guild.get_channel(channel), embed=bitrate)
                except:
                    pass
            else:
                await guild.get_channel(channel).send(
                                            ":loud_sound: `{}` Channel bitrate update. Before: **{}** After: **{}**.".format(
                                                time.strftime(fmt), before.bitrate, after.bitrate))

    async def on_message_edit(self, before, after):
        guild = before.guild
        
        if before.author.bot:
            return
        if await self.config.guild(guild).toggleedit() == False:
            return
        if before.content == after.content:
            return
        cleanbefore = before.content
        for i in before.mentions:
            cleanbefore = cleanbefore.replace(i.mention, str(i))
        cleanafter = after.content
        for i in after.mentions:
            cleanafter = cleanafter.replace(i.mention, str(i))
        channel = await self.config.guild(guild).Channel()
        if channel is None:
            return
        time = datetime.datetime.utcnow()
        fmt = '%H:%M:%S'
        if await self.config.guild(guild).embed() == True:
            name = before.author
            name = " ~ ".join((name.name, name.nick)) if name.nick else name.name
            
            infomessage = "A message by {}, was edited in {}".format(before.author.mention, before.channel.mention)
            delmessage = discord.Embed(description=infomessage, colour=discord.Color.green(), timestamp=after.created_at)
            delmessage.add_field(name="Before Message:", value=cleanbefore, inline=False)
            delmessage.add_field(name="After Message:", value=cleanafter)
            delmessage.set_footer(text="User ID: {}".format(before.author.id), icon_url=before.author.avatar_url)
            delmessage.set_author(name=name + " - Edited Message", url="http://i.imgur.com/Q8SzUdG.png", icon_url=before.author.avatar_url)
            delmessage.set_thumbnail(url="http://i.imgur.com/Q8SzUdG.png")
            try:
                await guild.get_channel(channel).send( embed=delmessage)
            except:
                pass
        else:
            msg = ":pencil: `{}` **Channel**: {} **{}'s** message has been edited.\nBefore: {}\nAfter: {}".format(
                time.strftime(fmt), before.channel.mention, before.author, cleanbefore, cleanafter)
            await guild.get_channel(channel).send(msg)

    async def on_guild_update(self, before, after):
        guild = before
        
        if await self.config.guild(guild).toggleguild() == False:
            return
        channel = await self.config.guild(guild).Channel()
        if channel is None:
            return
        time = datetime.datetime.utcnow()
        fmt = '%H:%M:%S'
        if before.name != after.name:
            msg = ":globe_with_meridians: `{}` guild name update. Before: **{}** After: **{}**.".format(
                time.strftime(fmt), before.name, after.name)
        if before.region != after.region:
            msg = ":globe_with_meridians: `{}` guild region update. Before: **{}** After: **{}**.".format(
                time.strftime(fmt), before.region, after.region)
        await guild.get_channel(channel).send(msg)

    async def on_voice_state_update(self, member, before, after):
        try:
            guild = before.channel.guild
        except:
            guild = after.channel.guild

        if await self.config.guild(guild).togglevoice() == False:
            return
        if member.bot:
            return
        channel = await self.config.guild(guild).Channel()
        if channel is None:
            return
        time = datetime.datetime.utcnow()
        fmt = '%H:%M:%S'
        if await self.config.guild(guild).embed() == True:
            name = member
            name = " ~ ".join((name.name, name.nick)) if name.nick else name.name
            updmessage = discord.Embed(description=name, colour=discord.Color.blue(), timestamp=time)
            infomessage = "__{}__'s voice status has changed".format(member.name)
            updmessage.add_field(name="Info:", value=infomessage, inline=False)
            updmessage.add_field(name="Voice Channel Before:", value=before.channel)
            updmessage.add_field(name="Voice Channel After:", value=after.channel)
            updmessage.set_footer(text="User ID: {}".format(member.id))
            updmessage.set_author(name=time.strftime(fmt) + " - Voice Channel Changed",
                                  url="http://i.imgur.com/8gD34rt.png")
            updmessage.set_thumbnail(url="http://i.imgur.com/8gD34rt.png")
            try:
                await guild.get_channel(channel).send( embed=updmessage)
            except:
                pass
        else:
            await guild.get_channel(channel).send(
                                        ":person_with_pouting_face::skin-tone-3: `{}` **{}'s** voice status has updated. **Channel**: {}\n**Local Mute:** {} **Local Deaf:** {} **guild Mute:** {} **guild Deaf:** {}".format(
                                            time.strftime(fmt), after.name, after.voice_channel, after.self_mute,
                                            after.self_deaf, after.mute, after.deaf))


    async def on_member_update(self, before, after):
        guild = before.guild
        
        channel = await self.config.guild(guild).Channel()
        if channel is None:
            return
        time = datetime.datetime.utcnow()
        fmt = '%H:%M:%S'
        if not before.roles == after.roles and await self.config.guild(guild).toggleroles():
            if await self.config.guild(guild).embed() == True:
                name = after
                name = " ~ ".join((name.name, name.nick)) if name.nick else name.name
                role = discord.Embed(colour=discord.Color.red(), timestamp=time)
                role.add_field(name="Roles Before:", value=" ,".join(role.name for role in before.roles), inline=False)
                role.add_field(name="Roles After:", value=" ,".join(role.name for role in after.roles), inline=False)
                role.set_footer(text="User ID: {}".format(after.id), icon_url=after.avatar_url)
                role.set_author(name=name + " - Updated Roles", icon_url=after.avatar_url)
                # role.set_thumbnail(after)
                try:
                    await guild.get_channel(channel).send( embed=role)
                except:
                    pass
            if await self.config.guild(guild).embed() == False:
                msg = ":person_with_pouting_face::skin-tone-3: `{}` **{}'s** roles have changed. Old: `{}` New: `{}`".format(
                    time.strftime(fmt), before.name, ", ".join([r.name for r in before.roles]),
                    ", ".join([r.name for r in after.roles]))
                await guild.get_channel(channel).send(
                                            msg)
        if not before.nick == after.nick and await self.config.guild(guild).toggleuser():
            if await self.config.guild(guild).embed() == True:
                name = before
                name = " ~ ".join((name.name, name.nick)) if name.nick else name.name
                infomessage = "{}'s nickname has changed".format(before.mention)
                updmessage = discord.Embed(description=infomessage, colour=discord.Color.orange(), timestamp=time)
                updmessage.add_field(name="Nickname Before:", value=before.nick)
                updmessage.add_field(name="Nickname After:", value=after.nick)
                updmessage.set_footer(text="User ID: {}".format(before.id), icon_url=after.avatar_url)
                updmessage.set_author(name=name + " - Nickname Changed", icon_url=after.avatar_url)
                # updmessage.set_thumbnail(url="http://i.imgur.com/I5q71rj.png")
                try:
                    await guild.get_channel(channel).send( embed=updmessage)
                except:
                    pass
            else:
                await guild.get_channel(channel).send(
                                            ":person_with_pouting_face::skin-tone-3: `{}` **{}** changed their nickname from **{}** to **{}**".format(
                                                time.strftime(fmt), before.name, before.nick, after.nick))

    async def on_member_ban(self, guild, member):
        
        if await self.config.guild(guild).toggleban() == False:
            return
        channel = await self.config.guild(guild).Channel()
        if channel is None:
            return
        time = datetime.datetime.utcnow()
        fmt = '%H:%M:%S'
        if await self.config.guild(guild).embed() == True:
            name = member
            name = " ~ ".join((name.name, name.nick)) if name.nick else name.name
            
            infomessage = "{} has been banned from the guild.".format(member.mention)
            banmessage = discord.Embed(description=infomessage, colour=discord.Color.red(), timestamp=time)
            banmessage.add_field(name="Info:", value=infomessage, inline=False)
            banmessage.set_footer(text="User ID: {}".format(member.id), icon_url=member.avatar_url)
            banmessage.set_author(name=name + " - Banned User", icon_url=member.avatar_url)
            banmessage.set_thumbnail(url=member.avatar_url)
            try:
                await guild.get_channel(channel).send( embed=banmessage)
            except:
                await guild.get_channel(channel).send(
                                            "How is embed modlog going to work when I don't have embed links permissions?")
        else:
            msg = ":hammer: `{}` {}({}) has been banned!".format(time.strftime(fmt), member, member.id)
            await guild.get_channel(channel).send(msg)
