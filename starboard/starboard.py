import discord
from redbot.core import Config
from redbot.core import checks
from redbot.core import commands
from .message_entry import StarboardMessage
from copy import copy

class Starboard(getattr(commands, "Cog", object)):
    """
        Create a starboard to *pin* those special comments
    """

    def __init__(self, bot):
        self.bot = bot
        default_guild = {"enabled": False, "channel": None, "emoji": None, 
                         "role":[], "messages":[], "ignore":[], "threshold": 0}
        self.config = Config.get_conf(self, 356488795)
        self.config.register_guild(**default_guild)
        self.message_list = []

    @commands.group(pass_context=True)
    @checks.admin_or_permissions(manage_channels=True)
    @commands.guild_only()
    async def starboard(self, ctx):
        """Commands for managing the starboard"""
        if ctx.invoked_subcommand is None:
            guild = ctx.guild
            if guild is None:
                return
            enabled = await self.config.guild(guild).enabled()
            if enabled:
                channel = self.bot.get_channel(await self.config.guild(guild).channel())
                if channel is None:
                    channel_mention = "None"
                else:
                    channel_mention = channel.mention
                emoji = await self.config.guild(guild).emoji()
                role = ", ".join(guild.get_role(r).name for r in await self.config.guild(guild).role())
                ignore = await self.config.guild(guild).ignore()
                if ignore != []:
                    ignored_channels = ", ".join(self.bot.get_channel(chn).mention for chn in ignore)
                    ignored_channels += ", {}".format(channel.mention) 
                else:
                    ignored_channels = channel.mention
                threshold = await self.config.guild(guild).threshold()
                if ctx.channel.permissions_for(ctx.guild.me).embed_links:
                    em = discord.Embed(title="Starboard settings for {}".format(ctx.guild.name))
                    em.add_field(name="Enabled", value=str(enabled))
                    em.add_field(name="Emoji", value=str(emoji))
                    em.add_field(name="Starboard Channel", value=channel_mention)
                    em.add_field(name="Roles Allowed", value=role)
                    em.add_field(name="Ignored Channels", value=ignored_channels)
                    em.add_field(name="Threshold", value=threshold)
                    await ctx.send(embed=em)
                else:
                    msg = f"Starboard Settings for {guild.name}\n"
                    msg += f"Enabled: {enabled}\n"
                    msg += f"Emoji: {str(emoji)}\n"
                    msg += f"Starboard Channel:{channel.mention}\n"
                    msg += f"Roles Allowed: {role}\n"
                    msg += f"Ignored Channels: {ignored_channels}\n"
                    msg += f"Threshold: {threshold}"
                    await ctx.send(msg)

    @starboard.group(pass_context=True, name="role", aliases=["roles"])
    async def _roles(self, ctx):
        """Add or remove roles allowed to add to the starboard"""
        pass

    async def get_everyone_role(self, guild):
        for role in guild.roles:
            if role.is_default():
                return role

    async def check_guild_emojis(self, guild, emoji):
        guild_emoji = None
        for emojis in guild.emojis:
            if str(emojis.id) in emoji:
                guild_emoji = emojis
        return guild_emoji

    @commands.command()
    @commands.guild_only()
    async def star(self, ctx, msg_id, channel:discord.TextChannel=None):
        """
            Manually star a message
        """
        if channel is None:
            channel = ctx.message.channel
        guild = channel.guild
        if guild is None:
            await ctx.send("This command can work in guilds only.")
            return
        try:
            msg = await channel.get_message(id=msg_id)
        except:
            return
        user = ctx.message.author
        if msg.channel.id in await self.config.guild(guild).ignore():
            return
        if msg.channel.id == await self.config.guild(guild).channel():
            return
        if not await self.config.guild(guild).enabled():
            return
        if not await self.check_roles(user, msg.author, guild):
            return
        emoji = await self.config.guild(guild).emoji()
        if await self.check_is_posted(guild, msg):
            channel = self.bot.get_channel(await self.config.guild(guild).channel())
            msg_id, count2 = await self.get_posted_message(guild, msg)
            if msg_id is not None:
                msg_edit = await channel.get_message(msg_id)
                await msg_edit.edit(content="{} **#{}**".format(emoji, count2))
                return
        count = 1
        channel2 = self.bot.get_channel(id=await self.config.guild(guild).channel())
        em = await self.build_embed(guild, msg)
        try:
            post_msg = await channel2.send("{} **#{}**".format(emoji, count), embed=em)
        except discord.errors.Forbidden:
            return await ctx.send("I don't have permissions to post in the starboard channel.")
        past_message_list = await self.config.guild(guild).messages()
        past_message_list.append(StarboardMessage(msg.id, post_msg.id, count).to_json())
        await self.config.guild(guild).messages.set(past_message_list)

    
    @starboard.command(pass_context=True, name="setup", aliases=["set"])
    async def setup_starboard(self, ctx, channel: discord.TextChannel=None, emoji="⭐", role:discord.Role=None):
        """
            Setup the starboard on this server

            Default channel is the current channel
            Default emoji is ⭐
            Default role is everyone
        """
        guild = ctx.message.guild
        if channel is None:
            channel = ctx.message.channel
        if "<" in emoji and ">" in emoji:
            emoji = await self.check_guild_emojis(guild, emoji)
            if emoji is None:
                await ctx.send("That emoji is not on this guild!")
                return
            else:
                emoji = "<:" + emoji.name + ":" + str(emoji.id) + ">"

        if not channel.permissions_for(guild.me).send_messages:
            await ctx.send("I don't have permission to post in {}".format(channel.mention))
            return

        if not channel.permissions_for(guild.me).embed_links:
            await ctx.send("I don't have permission to embed links in {}".format(channel.mention))
            return
        
        if role is None:
            role = await self.get_everyone_role(guild)
        await self.config.guild(ctx.guild).emoji.set(emoji)
        await self.config.guild(ctx.guild).channel.set(channel.id)
        await self.config.guild(ctx.guild).role.set([role.id])
        await self.config.guild(ctx.guild).enabled.set(True)
        await ctx.send("Starboard set to {}".format(channel.mention))

    @starboard.command(name="disable")
    async def disable_starboard(self, ctx):
        """Disables the starboard for this server."""
        await self.config.guild(ctx.guild).enabled.set(False)
        await ctx.send("Starboard disabled here!")

    @starboard.command(name="enable")
    async def enable_starboard(self, ctx):
        """Enables the starboard for this server."""
        await self.config.guild(ctx.guild).enabled.set(True)
        await ctx.send("Starboard enabled here!")

    @starboard.command(name="ignore")
    async def toggle_channel_ignore(self, ctx, channel:discord.TextChannel=None):
        """
            Toggles channel to be ignored by starboard
            
            The starboard channel is always ignored by default
        """
        if channel is None:
            channel = ctx.message.channel
        ignore_list = await self.config.guild(ctx.guild).ignore()
        if channel.id in ignore_list:
            ignore_list.remove(channel.id)
            await ctx.send("{} removed from the ignored channel list!".format(channel.mention))
        else:
            ignore_list.append(channel.id)
            await ctx.send("{} added to the ignored channel list!".format(channel.mention))
        await self.config.guild(ctx.guild).ignore.set(ignore_list)

    @starboard.command(pass_context=True, name="emoji")
    async def set_emoji(self, ctx, emoji="⭐"):
        """Set the emoji for the starboard defaults to ⭐"""
        guild = ctx.message.guild
        if not await self.config.guild(guild).enabled():
            await ctx.send("I am not setup for the starboard on this guild!\
                            \nuse `[p]starboard set` to set it up.")
            return
        is_guild_emoji = False
        if "<" in emoji and ">" in emoji:
            emoji = await self.check_guild_emojis(guild, emoji)
            if emoji is None:
                await ctx.send("That emoji is not on this guild!")
                return
            else:
                is_guild_emoji = True
                emoji = "<:" + emoji.name + ":" + str(emoji.id) + ">"
        await self.config.guild(guild).emoji.set(emoji)
        if is_guild_emoji:
            await ctx.send("Starboard emoji set to {}.".format(emoji))
        else:
            await ctx.send("Starboard emoji set to {}.".format(emoji))

    @starboard.command(pass_context=True, name="channel")
    async def set_channel(self, ctx, channel:discord.TextChannel=None):
        """Set the channel for the starboard"""
        guild = ctx.message.guild
        if not await self.config.guild(guild).enabled():
            await ctx.send("I am not setup for the starboard on this guild!\
                            \nuse `[p]starboard set` to set it up.")
            return
        if channel is None:
            channel = ctx.message.channel

        if not channel.permissions_for(guild.me).send_messages:
            await ctx.send("I don't have permission to post in {}".format(channel.mention))
            return

        if not channel.permissions_for(guild.me).embed_links:
            await ctx.send("I don't have permission to embed links in {}".format(channel.mention))
            return
        await self.config.guild(guild).channel.set(channel.id)
        await ctx.send("Starboard channel set to {}.".format(channel.mention))

    @starboard.command(pass_context=True, name="threshold")
    async def set_threshold(self, ctx, threshold:int=0):
        """Set the threshold before posting to the starboard"""
        guild = ctx.message.guild
        if not await self.config.guild(guild).enabled():
            await ctx.send(
                                        "I am not setup for the starboard on this guild!\
                                         \nuse `[p]starboard set` to set it up.")
            return
        await self.config.guild(guild).threshold.set(threshold)
        await ctx.send("Starboard threshold set to {}.".format(threshold))

    @_roles.command(pass_context=True, name="add")
    async def add_role(self, ctx, role:discord.Role=None):
        """Add a role allowed to add messages to the starboard defaults to @everyone"""
        guild = ctx.message.guild
        if not await self.config.guild(guild).enabled():
            await ctx.send("I am not setup for the starboard on this guild!\
                            \nuse starboard set to set it up.")
            return
        everyone_role = await self.get_everyone_role(guild)
        guild_roles = await self.config.guild(guild).role()
        if role is None:
            role = everyone_role
        if role.id in guild_roles:
            await ctx.send("{} can already add to the starboard!".format(role.name))
            return
        if everyone_role.id in guild_roles and role != everyone_role:
            guild_roles.remove(everyone_role.id)
        guild_roles.append(role.id)
        await self.config.guild(guild).role.set(guild_roles)
        await ctx.send("Starboard role set to {}.".format(role.name))

    @_roles.command(pass_context=True, name="remove", aliases=["del", "rem"])
    async def remove_role(self, ctx, role:discord.Role):
        """Remove a role allowed to add messages to the starboard"""
        guild = ctx.message.guild
        if not await self.config.guild(guild).enabled():
            await ctx.send("I am not setup for the starboard on this guild! use starboard set to set it up.")
            return
        everyone_role = await self.get_everyone_role(guild)
        guild_roles = await self.config.guild(guild).role()
        if role.id in guild_roles:
            guild_roles.remove(role.id)
        if guild_roles == []:
            guild_roles.append(everyone_role.id)
        await self.config.guild(guild).role.set(guild_roles)
        await ctx.send("{} removed from starboard.".format(role.name))

    async def check_roles(self, user, author, guild):
        """Checks if the user is allowed to add to the starboard
           Allows bot owner to always add messages for testing
           disallows users from adding their own messages"""
        has_role = False
        for role in user.roles:
            if role.id in await self.config.guild(guild).role():
                has_role = True
        if user is author:
            has_role = False
        if user.id == self.bot.owner_id:
            # Owner should always be allowed to add messages
            has_role = True
        return has_role

    async def check_is_posted(self, guild, message):
        is_posted = False
        for past_message in await self.config.guild(guild).messages():
            if message.id == past_message["original_message"]:
                is_posted = True
        if (guild.id, message.id) in self.message_list:
            is_posted = True
        return is_posted

    async def get_posted_message(self, guild, message):
        msg_list = await self.config.guild(guild).messages()
        msg = None
        for past_message in msg_list:
            if message.id == past_message["original_message"]:
                msg = past_message
        if msg is None:
            return
        msg_list.remove(msg)
        msg["count"] += 1
        msg_list.append(msg)
        await self.config.guild(guild).messages.set(msg_list)
        return msg["new_message"], msg["count"]

    async def build_embed(self, guild, msg):
        channel = msg.channel
        author = msg.author
        if msg.embeds != []:
            em = msg.embeds[0]
            if msg.content != "":
                if em.description != discord.Embed.Empty:
                    em.description = "{}\n\n{}".format(msg.content, em.description)
                else:
                    em.description = msg.content
                if not author.bot:
                    em.set_author(name=author.display_name, url=msg.jump_url, icon_url=author.avatar_url)
        else:
            em = discord.Embed(timestamp=msg.created_at)
            try:
                em.color = author.top_role.color
            except Exception as e:
                print(e)
                pass
            em.description = msg.content
            em.set_author(name=author.display_name, url=msg.jump_url, icon_url=author.avatar_url)
            if msg.attachments != []:
                em.set_image(url=msg.attachments[0].url)
        em.timestamp = msg.created_at
        em.description = em.description +"\n\n[Click Here to view context]({})".format(msg.jump_url)
        em.set_footer(text='{} | {}'.format(channel.guild.name, channel.name))
        return em

  
    async def on_raw_reaction_add(self, payload):
        channel = self.bot.get_channel(id=payload.channel_id)
        try:
            guild = channel.guild
        except:
            return
        try:
            msg = await channel.get_message(id=payload.message_id)
        except:
            return
        user = guild.get_member(payload.user_id)
        if msg.channel.id in await self.config.guild(guild).ignore():
            return
        if msg.channel.id == await self.config.guild(guild).channel():
            return
        if not await self.config.guild(guild).enabled():
            return
        if not await self.check_roles(user, msg.author, guild):
            return
        if user.bot:
            return
        react = await self.config.guild(guild).emoji()
        if str(react) == str(payload.emoji):
            threshold = await self.config.guild(guild).threshold()
            try:
                reaction = [r for r in msg.reactions if str(r.emoji) == str(payload.emoji)][0]
                count = reaction.count
            except IndexError:
                count = 0
            async for user in reaction.users():
                # This makes sure that the user cannot add their own count to the starboard threshold
                if msg.author.id == user.id and count != 0:
                    count -= 1
            if await self.check_is_posted(guild, msg):
                channel = self.bot.get_channel(await self.config.guild(guild).channel())
                msg_id, count2 = await self.get_posted_message(guild, msg)
                if msg_id is not None:
                    msg_edit = await channel.get_message(msg_id)
                    await msg_edit.edit(content="{} **#{}**".format(payload.emoji, count))
                    return

            self.message_list.append((guild.id, payload.message_id))
            if count < threshold:
                past_message_list = await self.config.guild(guild).messages()
                past_message_list.append(StarboardMessage(msg.id, None, count).to_json())
                await self.config.guild(guild).messages.set(past_message_list)
                self.message_list.remove((guild.id, payload.message_id))
                return
            
            channel2 = self.bot.get_channel(id=await self.config.guild(guild).channel())
            em = await self.build_embed(guild, msg)
            post_msg = await channel2.send("{} **#{}**".format(payload.emoji, count), embed=em)
            past_message_list = await self.config.guild(guild).messages()
            past_message_list.append(StarboardMessage(msg.id, post_msg.id, count).to_json())
            await self.config.guild(guild).messages.set(past_message_list)
            self.message_list.remove((guild.id, payload.message_id))