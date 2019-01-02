from random import choice, randint
import discord
import asyncio
from redbot.core import commands
from redbot.core import checks, bank, Config
import datetime
import aiohttp
from io import BytesIO
from redbot.core.i18n import Translator, cog_i18n
from redbot.core.utils.chat_formatting import pagify, box
from redbot.core.utils.menus import DEFAULT_CONTROLS, menu
from typing import Union, Optional


_ = Translator("ServerStats", __file__)


class GuildNotFoundError(Exception):
    pass


@cog_i18n(_)
class ServerStats(getattr(commands, "Cog", object)):
    """
        Gather useful information about servers the bot is in
        A lot of commands are bot owner only
    """

    def __init__(self, bot):
        self.bot = bot
        default_global = {"join_channel":None}
        self.config = Config.get_conf(self, 54853421465543)
        self.config.register_global(**default_global)
        self.session = aiohttp.ClientSession(loop=self.bot.loop)

    async def on_guild_join(self, guild):
        """Build and send a message containing serverinfo when the bot joins a new server"""
        channel_id = await self.config.join_channel()
        if channel_id is None:
            return
        channel = self.bot.get_channel(channel_id)
        em = await self.guild_embed(guild)
        passed = (datetime.datetime.utcnow() - guild.created_at).days
        created_at = _("{bot} has joined a server!\n "
                       "That's {num} servers now! \n"
                       "Server created {since}. "
                       "That's over {passed} days ago!").format(
                        bot = channel.guild.me.mention,
                        num = len(self.bot.guilds),
                        since = guild.created_at.strftime("%d %b %Y %H:%M"),
                        passed = passed)
        em.description = created_at
        await channel.send(embed=em)

    async def guild_embed(self, guild):
        """
            Builds the guild embed information used throughout the cog
        """
        online = len([m.status for m in guild.members
                      if m.status == discord.Status.online or
                      m.status == discord.Status.idle])
        total_users = len(guild.members)
        text_channels = len([x for x in guild.text_channels])
        voice_channels = len([x for x in guild.voice_channels])
        passed = (datetime.datetime.utcnow() - guild.created_at).days
        created_at = _("Server created {since}. "
                       "That's over {passed} days ago!").format(
                        since = guild.created_at.strftime("%d %b %Y %H:%M"),
                        passed = passed)

        colour = guild.roles[-1].colour

        em = discord.Embed(
            description=created_at,
            colour=colour,
            timestamp=guild.created_at)
        em.add_field(name=_("Region"), value=str(guild.region))
        em.add_field(name=_("Users"), value="{}/{}".format(online, total_users))
        em.add_field(name=_("Text Channels"), value=text_channels)
        em.add_field(name=_("Voice Channels"), value=voice_channels)
        em.add_field(name=_("Roles"), value=len(guild.roles))
        em.add_field(name=_("Owner"), value="{} | {}".format(str(guild.owner), 
                                                             guild.owner.mention))
        if guild.features:
            em.add_field(name=_("Guild Features"), 
                         value=", ".join(feature for feature in guild.features))
        em.set_footer(text=_("Guild ID: ")+"{}".format(guild.id))
        em.set_author(name=guild.name, icon_url=guild.icon_url_as(format="png"))
        em.set_thumbnail(url=guild.icon_url_as(format="png"))
        return em

    async def on_guild_remove(self, guild):
        """Build and send a message containing serverinfo when the bot leaves a server"""
        channel_id = await self.config.join_channel()
        if channel_id is None:
            return
        channel = self.bot.get_channel(channel_id)
        em = await self.guild_embed(guild)
        passed = (datetime.datetime.utcnow() - guild.created_at).days
        created_at = _("{bot} has left a server!\n "
                       "That's {num} servers now! \n"
                       "Server created {since}. "
                       "That's over {passed} days ago!").format(
                        bot = channel.guild.me.mention,
                        num = len(self.bot.guilds),
                        since = guild.created_at.strftime("%d %b %Y %H:%M"),
                        passed = passed)
        em.description = created_at

        await channel.send(embed=em)

    @commands.command()
    async def emoji(self, ctx, emoji:Union[discord.Emoji, str]):
        """
            Post a large size emojis in chat
        """
        if type(emoji) is discord.Emoji:
            await ctx.channel.trigger_typing()
            emoji_name = emoji.name
            ext = emoji.url.split(".")[-1]
            async with self.session.get(emoji.url) as resp:
                data = await resp.read()
            file = discord.File(BytesIO(data),filename="{}.{}".format(emoji.name, ext))
            await ctx.send(file=file)
        else:
            emoji_id = emoji.split(":")[-1].replace(">", "")
            await ctx.channel.trigger_typing()
            if emoji.startswith("<a"):
                url = "https://cdn.discordapp.com/emojis/{}.gif?v=1".format(emoji_id)
                async with self.session.get(url) as resp:
                    data = await resp.read()
                file = discord.File(BytesIO(data),filename="{}.gif".format(emoji_id))
            elif emoji.startswith("<:"):
                url = "https://cdn.discordapp.com/emojis/{}.png?v=1".format(emoji_id)
                async with self.session.get(url) as resp:
                    data = await resp.read()
                file = discord.File(BytesIO(data),filename="{}.png".format(emoji_id))
            else:
                """https://github.com/glasnt/emojificate/blob/master/emojificate/filter.py"""
                cdn_fmt = "https://twemoji.maxcdn.com/2/72x72/{codepoint:x}.png"
                try:
                    url = cdn_fmt.format(codepoint=ord(emoji))
                    async with self.session.get(url) as resp:
                        data = await resp.read()
                    file = discord.File(BytesIO(data), filename="emoji.png")
                except:
                    await ctx.send(_("That doesn't appear to be a valid emoji"))
                    return
            await ctx.send(file=file)

    @commands.command()
    @checks.mod_or_permissions(manage_channels=True)
    async def topic(self, ctx, channel:Optional[discord.TextChannel], *, topic:str=""):
        """
            Sets a specified channels topic
            
            `channel` is optional and if not supplied will use the current channel
            Note: The maximum number of characters is 1024
        """
        if channel is None:
            channel = ctx.channel
        if not channel.permissions_for(ctx.author).manage_messages:
            return
        if not channel.permissions_for(ctx.me).manage_channels:
            await ctx.send(_("I require the \"Manage Channels\" permission to execute that command."))
            return
        await channel.edit(topic=topic[:1024])
        await ctx.tick()

    async def ask_for_invite(self, ctx):
        """
            Ask the user to provide an invite link
            if reinvite is True
        """
        check = lambda m: m.author == ctx.message.author
        msg_send = _("Please provide a reinvite link/message.\n"
                    "Type `exit` for no invite link/message.")
        invite_check = await ctx.send(msg_send)
        try:
            msg = await ctx.bot.wait_for("message", check=check, timeout=30)
        except asyncio.TimeoutError:
            await msg.edit(content=_("I Guess not."))
            return None
        if "exit" in msg.content:
            return None
        else:
            return msg.content

    @commands.command()
    @checks.mod_or_permissions(kick_members=True)
    @checks.bot_has_permissions(kick_members=True, add_reactions=True)
    async def pruneroles(self, ctx,  days:int, role:discord.Role=None, reinvite:bool=True):
        """
            Purge users from the server who have been inactive for x days
            
            `days` is the number of days since last seen talking in channels
            `role` is the specified role you would like to kick defaults to everyone
            `reinvite` True/False whether to try to send the user a message before kicking
            Note: This will only check if a user has talked in the past x days whereas 
            discords built in Prune checks online status
        """
        now = datetime.datetime.utcnow()
        after = now - datetime.timedelta(days=days)
        if role is not None and role >= ctx.me.top_role:
            msg = _("That role is higher than my "
                    "role so I can't kick those members.")
            await ctx.send(msg)
            return
        if role is None:
            member_list = [m for m in ctx.guild.members if m.top_role < ctx.me.top_role]
        else:
            member_list = [m for m in role.members if m.top_role < ctx.me.top_role]
        # for member in member_list:
        user_list = []
        for channel in ctx.guild.text_channels:
            if not channel.permissions_for(ctx.me).read_message_history:
                continue
            async for message in channel.history(limit=None, after=after):
                if message.author.id not in user_list:
                    user_list.append(message.author.id)
        for member in member_list:
            if member.id in user_list:
                member_list.remove(member)
        send_msg = str(len(member_list))+_(" estimated users to kick. "
                                            "Would you like to kick them?")
        msg = await ctx.send(send_msg)
        if ctx.channel.permissions_for(ctx.me).add_reactions:
            check = lambda r, u: u == ctx.message.author and r.emoji in ["✅", "❌"]
            await msg.add_reaction("✅")
            await msg.add_reaction("❌")

            try:
                reaction, user = await self.bot.wait_for("reaction_add", 
                                                         check=check, 
                                                         timeout=60)
            except asyncio.TimeoutError:
                await ctx.send(_("I guess not."))
            if reaction.emoji == "✅":
                link = await self.ask_for_invite(ctx)
                no_invite = []
                for member in member_list:
                    if link:
                        try:
                            await member.send(link)
                        except:
                            no_invite.append(member.id)
                    await member.kick(reason=_("Kicked due to inactivity."))
                if link and len(no_invite) > 0:
                    msg = (str(len(no_invite)) + 
                           _(" users could not be DM'd an invite link"))
                    await ctx.send(msg)
            else:
                await ctx.send("Not kicking users.")
                return

    @commands.command()
    @commands.bot_has_permissions(embed_links=True, add_reactions=True)
    async def avatar(self, ctx, member:Union[discord.Member, str]=None):
        """
            Display a users avatar in chat
        """
        member_list = []
        guild = ctx.message.guild
        if member is None:
            member = ctx.message.author
        if type(member) == str:
            for m in guild.members:
                if member.lower() in m.display_name.lower():
                    member_list.append(m)
                    continue
                if member.lower() in m.name.lower():
                    member_list.append(m)
                    continue
        else:
            member_list.append(member)
        embed_list = []
        for member in member_list:
            em = discord.Embed(title=_("**Avatar**"), colour=member.colour)
            if member.is_avatar_animated():
                url = member.avatar_url_as(format="gif")
            if not member.is_avatar_animated():
                url = member.avatar_url_as(static_format="png")
            em.set_image(url= url)
            em.set_author(name="{}#{}".format(member.name, member.discriminator), 
                          icon_url=url, 
                          url=url)
            embed_list.append(em)
        if not embed_list:
            await ctx.send(_("That user does not appear to exist on this server."))
            return
        if len(embed_list) > 1:
            await menu(ctx, embed_list, DEFAULT_CONTROLS)
        else:
            await ctx.send(embed=embed_list[0])

    @commands.command()
    @checks.is_owner()
    @commands.bot_has_permissions(embed_links=True)
    async def setguildjoin(self, ctx, channel:discord.TextChannel=None):
        """
            Set a channel to see new servers the bot is joining
        """
        if channel is None:
            channel = ctx.message.channel
        await self.config.join_channel.set(channel.id)
        msg = (_("Posting new servers and left servers in ") + 
               channel.mention)
        await ctx.send(msg)

    @commands.command()
    @checks.is_owner()
    async def removeguildjoin(self, ctx):
        """
            Stop bots join/leave server messages
        """
        await self.config.join_channel.set(None)
        await ctx.send(_("No longer posting joined or left servers."))

    @commands.command(hidden=True)
    @checks.is_owner()
    async def checkcheater(self, ctx, user_id:int):
        """
            Checks for possible cheaters abusing the global bank and server powers
        """
        is_cheater = False
        for guild in self.bot.guilds:
            print(guild.owner.id)
            if guild.owner.id == user_id:
                is_cheater = True
                msg = (guild.owner.mention + 
                       _(" is guild owner of ") + 
                       guild.name)
                await ctx.send(msg)
        if not is_cheater:
            await ctx.send(_("Not a cheater"))

    @commands.command(hidden=True)
    @checks.is_owner()
    async def whois(self, ctx, member:Union[int, discord.User]):
        """
            Display servers a user shares with the bot

            `member` can be a user ID or mention
        """
        if type(member) == int:
            try:
                member = await self.bot.get_user_info(member)
            except discord.errors.NotFound:
                await ctx.send(str(member) + _(" doesn't seem to be a discord user."))
                return
        guild_list = []
        for guild in self.bot.guilds:
            members = [member.id for member in guild.members]
            if member.id in members:
                guild_list.append(guild)
        if guild_list != []:
            msg = ("{} ({}) ".format(member, member.id) + _("is on:\n"))
            for guild in guild_list:
                msg += "{} ({})\n".format(guild.name, guild.id)
            for page in pagify(msg, ["\n"]):
                await ctx.send(page)
        else:
            msg = (f"{member} ({member.id}) "+
                   _("is not in any shared servers!"))
            await ctx.send(msg)

    @commands.command(hidden=True)
    @checks.is_owner()
    async def topservers(self, ctx):
        """
            Lists servers by number of users and shows number of users
        """
        owner = ctx.author
        guilds = sorted(list(self.bot.guilds),
                        key=lambda s: len(s.members), reverse=True)
        msg = ""
        for i, server in enumerate(guilds):
            msg += "{}: {}\n".format(server.name, len(server.members))

        for page in pagify(msg, ['\n']):
            await ctx.send(page)

    @commands.command(hidden=True)
    @checks.is_owner()
    async def newservers(self, ctx):
        """
            Lists servers by when the bot was added to the server
        """
        owner = ctx.author
        guilds = sorted(list(self.bot.guilds),
                        key=lambda s: s.me.joined_at)
        msg = ""
        for i, server in enumerate(guilds):
            msg += "{}: {} ({})\n".format(i, server.name, server.id)

        for page in pagify(msg, ['\n']):
            await ctx.send(page)

    @commands.command()
    @checks.mod_or_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def slowmode(self, ctx, time:int=0, channel:discord.TextChannel=None):
        """
            Set a channels slowmode setting

            `time` must be a number between 0 and 120
            `channel` is the channel you want to set slowmode on defaults to current channel
        """
        if channel is None:
            channel = ctx.channel
        if time < 0 or time > 120:
            await ctx.send(_("You can only set a number between 0 and 120"))
            return
        await channel.edit(slowmode_delay=time)
        msg = (_("Slowmode set to")+
               str(time)+ _("in") + channel.mention)
        await ctx.send(msg)

    @commands.command()
    @checks.mod_or_permissions(manage_messages=True)
    async def topmembers(self, ctx, number:Optional[int]=10, guild_name:Union[int, str]=None):
        """
            Lists top members on the server by join date

            `number` optional[int] number of members to display at a time maximum of 50
            `guild_name` can be either the server ID or partial name
        """
        guild = ctx.guild
        if guild_name is not None:
            try:
                guild = await self.get_guild_obj(guild_name)
            except GuildNotFoundError:
                await ctx.send(guild_name + _(" guild could not be found."))
                return
        if number > 50:
            number = 50
        if number < 10:
            number = 10
        member_list = sorted(guild.members, key=lambda m: m.joined_at)
        is_embed = ctx.channel.permissions_for(ctx.me).embed_links
        x = [member_list[i:i+number] for i in range(0, len(member_list), number)]
        msg_list = []
        for page in x:
            header_msg = ("__**"+_("First ")+str(number)+
                          _(" members of ")+f"{guild.name}**__\n")
            msg = ""
            for member in page:
                if is_embed:
                    msg += f"{member_list.index(member)+1}. {member.mention}\n"
                    
                else:
                    msg += f"{member_list.index(member)+1}. {member.name}\n"
            if is_embed:
                embed = discord.Embed(description=msg)
                embed.set_author(name=guild.name + _(" first members"), 
                                     icon_url=guild.icon_url)
                msg_list.append(embed)

            else:
                msg_list.append(header_msg+msg)
        await menu(ctx, msg_list, DEFAULT_CONTROLS)

    async def get_guild_obj(self, guild_name):
        if type(guild_name) == int:
            page_guild = [g for g in self.bot.guilds if int(guild_name) == g.id]
        if type(guild_name) == str:
            page_guild = [g for g in self.bot.guilds if guild_name.lower() in g.name.lower()]
        try:
            if guild_name is not None:
                guilds = [g for g in self.bot.guilds]
                guild = guilds[guilds.index(page_guild[0])]
        except IndexError as e:
            raise GuildNotFoundError
        return guild
    
    @commands.command()
    @checks.is_owner()
    async def listchannels(self, ctx, *, guild_name:Union[int, str]=None):
        """
            Lists channels and their position and ID for a server

            `guild_name` can be either the server ID or partial name
        """
        guild = ctx.guild
        if guild_name is not None:
            try:
                guild = await self.get_guild_obj(guild_name)
            except GuildNotFoundError:
                await ctx.send(guild_name + _(" guild could not be found."))
                return
        channels = {}
        msg = "__**{}({})**__\n".format(guild.name, guild.id)
        for category in guild.by_category():
            if category[0] is not None:
                word = _("Position")
                msg += "{0} ({1}): {2} {3}\n".format(category[0].mention, 
                                                     category[0].id, 
                                                     word,
                                                     category[0].position)
            for channel in category[1]:
                word = _("Position")
                msg += "{0} ({1}): {2} {3}\n".format(channel.mention, 
                                                     channel.id, 
                                                     word,
                                                     channel.position)
        for page in pagify(msg, ["\n"]):
            await ctx.send(page)

    async def guild_menu(self, ctx, post_list: list,
                         message: discord.Message=None,
                         page=0, timeout: int=30):
        """menu control logic for this taken from
           https://github.com/Lunar-Dust/Dusty-Cogs/blob/master/menu/menu.py"""

        guild = post_list[page]
        em = await self.guild_embed(guild)         
        
        if not message:
            message = await ctx.send(embed=em)
            await message.add_reaction("⬅")
            await message.add_reaction("❌")
            await message.add_reaction("➡")
        else:
            # message edits don't return the message object anymore lol
            await message.edit(embed=em)
        check = lambda react, user:user == ctx.message.author and react.emoji in ["➡", "⬅", "❌"] and react.message.id == message.id
        try:
            react, user = await self.bot.wait_for("reaction_add", check=check, timeout=timeout)
        except asyncio.TimeoutError:
            await message.remove_reaction("⬅", ctx.me)
            await message.remove_reaction("❌", ctx.me)
            await message.remove_reaction("➡", ctx.me)
            return None
        else:
            if react.emoji == "➡":
                next_page = 0
                if page == len(post_list) - 1:
                    next_page = 0  # Loop around to the first item
                else:
                    next_page = page + 1
                if ctx.channel.permissions_for(ctx.me).manage_messages:
                    await message.remove_reaction("➡", ctx.message.author)
                return await self.guild_menu(ctx, post_list, message=message,
                                             page=next_page, timeout=timeout)
            elif react.emoji == "⬅":
                next_page = 0
                if page == 0:
                    next_page = len(post_list) - 1  # Loop around to the last item
                else:
                    next_page = page - 1
                if ctx.channel.permissions_for(ctx.me).manage_messages:
                    await message.remove_reaction("⬅", ctx.message.author)
                return await self.guild_menu(ctx, post_list, message=message,
                                             page=next_page, timeout=timeout)
            else:
                return await message.delete()

    @commands.command()
    @checks.is_owner()
    @commands.bot_has_permissions(embed_links=True)
    async def getguild(self, ctx, *, guild_name:Union[int, str]=None):
        """
            Display info about servers the bot is on

            `guild_name` can be either the server ID or partial name
        """
        guilds = [guild for guild in self.bot.guilds]
        page = 0
        if guild_name:
            try:
                guild = await self.get_guild_obj(guild_name)
                page = guilds.index(guild)
            except GuildNotFoundError:
                await ctx.send(str(guild_name) + _(" guild could not be found."))
                return
            

        await self.guild_menu(ctx, guilds, None, page)

    
    @commands.command()
    @checks.mod_or_permissions(manage_messages=True)
    async def nummembers(self, ctx, *, guild_name:Union[int, str]=None):
        """
            Display number of users on a server

            `guild_name` can be either the server ID or partial name
        """
        guild = ctx.guild
        if guild_name is not None:
            try:
                guild = await self.get_guild_obj(guild_name)
            except GuildNotFoundError:
                await ctx.send(guild_name + _(" guild could not be found."))
                return

        await ctx.send("{} has {} members.".format(guild.name, len(guild.members)))

    @commands.command(aliases=["rolestats"])
    @checks.mod_or_permissions(manage_messages=True)
    async def getroles(self, ctx, *, guild_name:Union[int, str]=None):
        """
            Displays all roles their ID and number of members

            `guild_name` can be either the server ID or partial name
        """
        guild = ctx.guild
        if guild_name is not None:
            try:
                guild = await self.get_guild_obj(guild_name)
            except GuildNotFoundError:
                await ctx.send(guild_name + _(" guild could not be found."))
                return
        msg = ""
        for role in sorted(guild.roles, reverse=True):
            if ctx.channel.permissions_for(ctx.me).embed_links:
                msg += (f"{role.mention} ({role.id}): {len(role.members)}\n")
            else:
                msg += (f"{role.name} ({role.id}): {len(role.members)}\n")
        msg_list = []
        for page in pagify(msg, ["\n"]):
            if ctx.channel.permissions_for(ctx.me).embed_links:
                embed = discord.Embed()
                embed.description = page
                embed.set_author(name=guild.name + _("Roles"), icon_url=guild.icon_url)
                msg_list.append(embed)
            else:
                msg_list.append(page)
        await menu(ctx, msg_list, DEFAULT_CONTROLS)

    async def check_highest(self, data):
        highest = 0
        users = 0
        for user, value in data.items():
            if value > highest:
                highest = value
                users = user
        return highest, users

    @commands.command(name="getreactions", aliases=["getreaction"])
    @checks.mod_or_permissions(manage_messages=True)
    async def get_reactions(self, ctx, message_id:int, channel:discord.TextChannel=None):
        """
            Gets a list of all reactions from specified message and displays the user ID,
            Username, and Discriminator and the emoji name.
        """
        if channel is None:
            channel = ctx.message.channel
        msg = await channel.get_message(message_id)
        new_msg = ""
        for reaction in msg.reactions:
            async for user in reaction.users():
                if type(reaction.emoji) is not str:
                    new_msg += "{} {}#{} {}\n".format(user.id, user.name, user.discriminator, reaction.emoji.name)
                else:
                    new_msg += "{} {}#{} {}\n".format(user.id, user.name, user.discriminator, reaction.emoji)
        for page in pagify(new_msg, shorten_by=20):
            await ctx.send("```py\n{}\n```".format(page))


    @commands.command(aliases=["serverstats"])
    @checks.mod_or_permissions(manage_messages=True)
    async def server_stats(self, ctx, *, guild_name:Union[int, str]=None):
        """Gets total messages on the server and per-channel basis as well as most single user posts"""
        guild = ctx.guild
        if guild_name is not None:
            try:
                guild = await self.get_guild_obj(guild_name)
            except GuildNotFoundError:
                await ctx.send(guild_name + _(" guild could not be found."))
                return
        channel = ctx.message.channel
        total_msgs = 0
        msg = ""
        total_contribution = {}
        warning_msg = await ctx.send(_("This might take a while!"))
        async with ctx.channel.typing():
            for chn in guild.channels:
                channel_msgs = 0
                channel_contribution = {}
                try:
                    async for message in chn.history(limit=10000000):
                        author = message.author
                        channel_msgs += 1
                        total_msgs += 1
                        if author.id not in channel_contribution:
                            channel_contribution[author.id] = 1
                        else:
                            channel_contribution[author.id] += 1

                        if author.id not in total_contribution:
                            total_contribution[author.id] = 1
                        else:
                            total_contribution[author.id] += 1
                    highest, users = await self.check_highest(channel_contribution)
                    msg += (f"{chn.mention}: "+
                            ("Total Messages:") + f"**{channel_msgs}** "+
                            _("most user posts ") + f"**{highest}**\n")
                except discord.errors.Forbidden:
                    pass
                except AttributeError:
                    pass
            highest, users = await self.check_highest(total_contribution)
            new_msg = (f"__{guild.name}__: "+
                       _("Total Messages:")+f"**{total_msgs}** "+
                       _("Most user posts ")+f"**{highest}**\n{msg}")
            await warning_msg.delete()
            for page in pagify(new_msg, ["\n"]):
                await channel.send(page)


    @commands.command(aliases=["serveremojis"])
    @commands.bot_has_permissions(embed_links=True)
    async def guildemojis(self, ctx, *, guild_name:Union[int, str]=None):
        """
            Display all server emojis in a menu that can be scrolled through

            `guild_name` can be either the server ID or partial name
        """
        guild = ctx.guild
        if guild_name is not None:
            try:
                guild = await self.get_guild_obj(guild_name)
            except GuildNotFoundError:
                await ctx.send(guild_name + _(" guild could not be found."))
                return
        msg = ""
        embed = discord.Embed(timestamp=ctx.message.created_at)
        embed.set_author(name=guild.name, icon_url=guild.icon_url)
        regular = []
        for emoji in guild.emojis:
            regular.append(f"{emoji} = `:{emoji.name}:`\n")
        if regular != "":
            embed.description = regular
        x = [regular[i:i+10] for i in range(0, len(regular), 10)]
        emoji_embeds = []
        count = 1
        for page in x:
            em = discord.Embed(timestamp=ctx.message.created_at)
            em.set_author(name=guild.name + _(" Emojis"), 
                          icon_url=guild.icon_url)
            regular = []
            msg = ""
            for emoji in page:
                msg += emoji
            em.description = msg
            em.set_footer(text="Page {} of {}".format(count, len(x)))
            count += 1
            emoji_embeds.append(em)

        await menu(ctx, emoji_embeds, DEFAULT_CONTROLS)

    def __unload(self):
        self.bot.loop.create_task(self.session.close())
