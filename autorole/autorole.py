import discord
from redbot.core import commands, checks, Config
import random
import string


default_settings = {
            "ENABLED": False,
            "ROLE": [],
            "AGREE_CHANNEL": None,
            "AGREE_MSG": None,
            "AGREE_KEY": None
        }

class Autorole(getattr(commands, "Cog", object)):
    """
        Autorole commands. Rewritten for V3 from 
        https://github.com/Lunar-Dust/Dusty-Cogs/blob/master/autorole/autorole.py
    """

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, 45463543548)
        self.config.register_guild(**default_settings)
        self.users = {}

    async def _no_perms(self, channel=None):
        m = ("It appears that you haven't given this "
             "bot enough permissions to use autorole. "
             "The bot requires the \"Manage Roles\" and "
             "the \"Manage Messages\" permissions in"
             "order to use autorole. You can change the "
             "permissions in the \"Roles\" tab of the "
             "guild settings.")
        if channel is None:
            print(m)
            return
        if channel.permissions_for(channel.guild.me).send_messages:
            await channel.send(m)
        else:
            print(m + f"\n I also don't have permission to speak in #{channel.name}")

    async def on_message(self, message):
        guild = message.guild
        user = message.author
        channel = message.channel
        try:
            agree_channel = guild.get_channel(await self.config.guild(guild).AGREE_CHANNEL())
        except:
            return
        if guild is None:
            return
        if agree_channel is None:
            return
        if channel.id != agree_channel.id:
            return
        if user.bot:
            return

        if user.id in self.users:
            if not guild.me.guild_permissions.manage_roles:
                await self._no_perms(agree_channel)
                return
            if  self.users[user.id].lower() in message.content.lower():
                roles_id = await self.config.guild(guild).ROLE()
                del self.users[user.id]
                roles = [role for role in guild.roles if role.id in roles_id]
                for role in roles:
                    await user.add_roles(role, reason="Agreed to the rules")
                if agree_channel.permissions_for(guild.me).add_reactions:
                    await message.add_reaction("✅")

    async def _agree_maker(self, member):
        guild = member.guild
        self.last_guild = guild
        # await self._verify_json(None)
        key = await self.config.guild(guild).AGREE_KEY()
        if key is None:
            key = ''.join(random.choice(string.ascii_uppercase +
                                        string.digits) for _ in range(6))
            # <3 Stackoverflow http://stackoverflow.com/questions/2257441/random-string-generation-with-upper-case-letters-and-digits-in-python/23728630#23728630
            

        self.users[member.id] = key

        ch = guild.get_channel(await self.config.guild(guild).AGREE_CHANNEL())
        msg = await self.config.guild(guild).AGREE_MSG()
        if msg is None:
            msg = "{mention} please enter {key} in {channel}"
        try:
            msg = msg.format(key=key,
                             member=member,
                             name=member.name,
                             mention=member.mention,
                             guild=guild.name,
                             channel=ch.mention)
        except Exception as e:
            print(e)

        try:
            msg = await member.send(msg)
        except discord.Forbidden:
            msg = await ch.send(msg)
        except discord.HTTPException:
            return

    async def _auto_give(self, member):
        guild = member.guild
        roles_id = await self.config.guild(guild).ROLE()
        roles = [role for role in guild.roles if role.id in roles_id]
        if not guild.me.guild_permissions.manage_roles:
            await self._no_perms()
            return
        for role in roles:
            await member.add_roles(role, reason="Joined the server")

    async def on_member_join(self, member):
        guild = member.guild
        if await self.config.guild(guild).ENABLED():
            if await self.config.guild(guild).AGREE_CHANNEL() is not None:
                await self._agree_maker(member)
            else:  # Immediately give the new user the role
                await self._auto_give(member)


    @commands.group(name="autorole", no_pm=True)
    async def autorole(self, ctx):
        """
            Change settings for autorole

            Requires the manage roles permission
        """
        if ctx.invoked_subcommand is None:
            guild = ctx.message.guild
            enabled = await self.config.guild(guild).ENABLED()
            roles = await self.config.guild(guild).ROLE()
            msg = await self.config.guild(guild).AGREE_MSG()
            key = await self.config.guild(guild).AGREE_KEY()
            channel = await self.config.guild(guild).AGREE_CHANNEL()
            chn_mention = guild.get_channel(channel).name if channel is not None else "None"
            role_name = []
            role_name_str = ", ".join(role.name for role in guild.roles if role.id in roles)
            send_msg = ("```Current autorole state: {}\nCurrent Roles:{}\n"
                        "Agreement message: {}\n"
                        "Agreement key: {}\n"
                        "Agreement channel: {}```")
            await ctx.send(send_msg.format(enabled, role_name_str, msg, key, chn_mention))

    @autorole.command(no_pm=True)
    @checks.admin_or_permissions(manage_roles=True)
    async def toggle(self, ctx):
        """
            Enables/Disables autorole
        """
        guild = ctx.message.guild
        if await self.config.guild(guild).ROLE() is None:
            await ctx.send("You haven't set a role to give to new users! "
                               "Use `{}autorole role \"role\"` to set it!"
                               .format(ctx.prefix))
        else:
            if await self.config.guild(guild).ENABLED():
                await self.config.guild(guild).ENABLED.set(False)
                await ctx.send("Autorole is now disabled.")
            else:
                await self.config.guild(guild).ENABLED.set(True)
                await ctx.send("Autorole is now enabled.")

    @autorole.command(no_pm=True, name="add", aliases=["role"])
    @checks.admin_or_permissions(manage_roles=True)
    async def role(self, ctx, *, role: discord.Role):
        """
            Add a role for autorole to assign.
        
            You can use this command multiple times to add multiple roles.
        """
        guild = ctx.message.guild
        roles = await self.config.guild(guild).ROLE()
        if not guild.me.guild_permissions.manage_roles:
            await ctx.send("I don't have the manage roles permission to use these features!")
            return
        if role.id in roles:
            await ctx.send("{} is already in the autorole list.".format(role.name))
            return
        if guild.me.top_role < role:
            await ctx.send("{} is higher than my highest role in the Discord hierarchy.".format(role.name))
            return
        roles.append(role.id)
        await self.config.guild(guild).ROLE.set(roles)
        await ctx.send(f"Added the role `{role.name}` to the autorole.")
            
    @autorole.command(no_pm=True)
    @checks.admin_or_permissions(manage_roles=True)
    async def remove(self, ctx, *, role: discord.Role):
        """
            Remove a role from the autorole.
        """
        guild = ctx.message.guild
        roles = await self.config.guild(guild).ROLE()
        if role.id not in roles:
            await ctx.send("{} is not in the autorole list.".format(role.name))
            return
        roles.remove(role.id)
        await self.config.guild(guild).ROLE.set(roles)
        await ctx.send(f"Removed the role `{role.name}` from the autorole.")


    @autorole.group(no_pm=True)
    @checks.admin_or_permissions(manage_roles=True)
    async def agreement(self, ctx):
        """
            Set the channel and message that will be used for accepting the rules.
            
            `channel` is the channel they must type the key in to get the role.
            `key` is the message they must type to gain access and must be in quotes.
            `msg` is the message DM'd to them when they join.

            `{key}` must be included in the message so a user knows what to type in the channel.
            
            Optional additions to the message include:
            `{channel}` Mentions the channel where they must include the agreement message.
            `{mention}` Mentions the user incase they have DM permissions turned off this should be used.
            `{name}` Says the member name if you don't want to ping them.
            `{guild}` Says the servers current name.
            
            Entering nothing will disable these.
        """


    @agreement.command(no_pm=True, name="channel")
    @checks.admin_or_permissions(manage_roles=True)
    async def set_agreement_channel(self, ctx, channel: discord.TextChannel=None):
        """
            Set the agreement channel

            Entering nothing will clear this.
        """
        guild = ctx.message.guild
        if await self.config.guild(guild).ROLE() == []:
            await ctx.send("No roles have been set for autorole.")
            return
        if not await self.config.guild(guild).ENABLED():
            await ctx.send("Autorole has been disabled, enable it first.")
            return
        if channel is None:
            await self.config.guild(guild).AGREE_CHANNEL.set(None)
            await ctx.send("Agreement channel cleared")
        else:
            await self.config.guild(guild).AGREE_CHANNEL.set(channel.id)
            await ctx.send(f"Agreement channel set to {channel.mention}")

    @agreement.command(no_pm=True, name="key")
    @checks.admin_or_permissions(manage_roles=True)
    async def set_agreement_key(self, ctx, *, key: str=None):
        """
            Set the agreement key

            Entering nothing will clear this.
        """

        guild = ctx.message.guild
        if await self.config.guild(guild).ROLE() == []:
            await ctx.send("No roles have been set for autorole.")
            return
        if not await self.config.guild(guild).ENABLED():
            await ctx.send("Autorole has been disabled, enable it first.")
            return
        if key is None:
            await self.config.guild(guild).AGREE_KEY.set(None)
            await ctx.send("Agreement key cleared")
        else:
            await self.config.guild(guild).AGREE_KEY.set(key)
            await ctx.send(f"Agreement key set to {key}")

    @agreement.command(no_pm=True, name="message", aliases=["msg"])
    @checks.admin_or_permissions(manage_roles=True)
    async def set_agreement_msg(self, ctx, *, message: str=None):
        """
            Set the agreement message
            `{key}` must be included in the message so a user knows what to type in the channel.

            Optional additions to the message include:
            `{channel}` Mentions the channel where they must include the agreement message.
            `{mention}` Mentions the user incase they have DM permissions turned off this should be used.
            `{name}` Says the member name if you don't want to ping them.
            `{guild}` Says the servers current name.

            Entering nothing will clear this.
        """
        guild = ctx.message.guild
        if await self.config.guild(guild).ROLE() == []:
            await ctx.send("No roles have been set for autorole.")
            return
        if not await self.config.guild(guild).ENABLED():
            await ctx.send("Autorole has been disabled, enable it first.")
            return
        if message is None:
            await self.config.guild(guild).AGREE_MSG.set(None)
            await ctx.send("Agreement message cleared")
        else:
            await self.config.guild(guild).AGREE_MSG.set(message)
            await ctx.send(f"Agreement key set to {message}")

    @agreement.command(no_pm=True, name="setup")
    @checks.admin_or_permissions(manage_roles=True)
    async def agreement_setup(self, ctx, channel: discord.TextChannel=None, key: str=None, *, msg: str=None):
        """
            Set the channel and message that will be used for accepting the rules.
            
            `channel` is the channel they must type the key in to get the role.
            `key` is the message they must type to gain access and must be in quotes.
            `msg` is the message DM'd to them when they join.

            `{key}` must be included in the message so a user knows what to type in the channel.
            
            Optional additions to the message include:
            `{channel}` Mentions the channel where they must include the agreement message.
            `{mention}` Mentions the user incase they have DM permissions turned off this should be used.
            `{name}` Says the member name if you don't want to ping them.
            `{guild}` Says the servers current name.
            
            Entering nothing will disable this.
        """
        guild = ctx.message.guild
        if await self.config.guild(guild).ROLE() == []:
            await ctx.send("No roles have been set for autorole.")
            return
        if not await self.config.guild(guild).ENABLED():
            await ctx.send("Autorole has been disabled, enable it first.")
            return
        if channel is None:
            await self.config.guild(guild).AGREE_CHANNEL.set(None)
            await self.config.guild(guild).AGREE_MSG.set(None)
            await self.config.guild(guild).AGREE_KEY.set(None)
            await ctx.send("Agreement channel cleared")
        else:
            await self.config.guild(guild).AGREE_CHANNEL.set(channel.id)
            await self.config.guild(guild).AGREE_MSG.set(msg)
            await self.config.guild(guild).AGREE_KEY.set(key)
            await ctx.send("Agreement channel set to {}".format(channel.mention))
