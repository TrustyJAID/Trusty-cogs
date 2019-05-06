import discord

from redbot.core import Config, checks, commands

listener = getattr(commands.Cog, "listener", None)  # red 3.0 backwards compatibility support

if listener is None:  # thanks Sinbad
    def listener(name=None):
        return lambda x: x


class Fenrir(commands.Cog):
    """
        Various unreasonable commands inspired by Fenrir
    """

    __version__ = "1.0.0"
    __author__ = "TrustyJAID"

    def __init__(self, bot):
        self.bot = bot
        self.kicks = []
        self.bans = []
        self.mutes = []
        self.feedback = {}
        # default_guild = {"kicks": [], "bans":[]}

        # self.config = Config.get_conf(self, 228492507124596736)
        # self.config.register_guild(**default_guild)

    @commands.command()
    @checks.admin_or_permissions(kick_members=True)
    @commands.guild_only()
    async def fenrirkick(self, ctx):
        """Create a reaction emoji to kick users"""
        msg = await ctx.send("React to this message to be kicked!")
        await msg.add_reaction("✅")
        await msg.add_reaction("❌")
        self.kicks.append(msg.id)

    @commands.command()
    @checks.admin_or_permissions(ban_members=True)
    @commands.guild_only()
    async def fenrirban(self, ctx):
        """Create a reaction emoji to ban users"""
        msg = await ctx.send("React to this message to be banned!")
        await msg.add_reaction("✅")
        await msg.add_reaction("❌")
        self.bans.append(msg.id)

    @commands.command()
    @checks.admin_or_permissions(ban_members=True)
    @commands.guild_only()
    @commands.check(lambda ctx: ctx.guild.id == 236313384100954113)
    async def fenrirmute(self, ctx):
        """Create a reaction emoji to mute users"""
        msg = await ctx.send("React to this message to be muted!")
        await msg.add_reaction("✅")
        await msg.add_reaction("❌")
        self.mutes.append(msg.id)

    @commands.command(aliases=["fenririnsult"])
    @checks.mod_or_permissions(manage_messages=True)
    @commands.guild_only()
    @commands.check(lambda ctx: ctx.bot.get_cog("Insult"))
    async def fenrirfeedback(self, ctx):
        """Create a reaction emoji to insult users"""
        msg = await ctx.send("React to this message to be insulted!")
        await msg.add_reaction("✅")
        await msg.add_reaction("❌")
        self.feedback[msg.id] = []

    async def is_mod_or_admin(self, member: discord.Member):
        guild = member.guild
        if member == guild.owner:
            return True
        if await self.bot.is_owner(member):
            return True
        if await self.bot.is_admin(member):
            return True
        if await self.bot.is_mod(member):
            return True
        if await self.bot.is_automod_immune(member):
            return True
        return False

    @listener()
    async def on_raw_reaction_add(self, payload):
        try:
            guild = self.bot.get_guild(payload.guild_id)
        except Exception as e:
            print(e)
            return
        if payload.message_id in self.kicks:
            member = guild.get_member(payload.user_id)
            if member is None:
                return
            if member.bot:
                return
            if await self.is_mod_or_admin(member):
                return
            try:
                await member.kick(reason="They asked for it.")
            except Exception:
                return
        if payload.message_id in self.bans:
            member = guild.get_member(payload.user_id)
            if member is None:
                return
            if member.bot:
                return
            if await self.is_mod_or_admin(member):
                return
            try:
                await member.ban(reason="They asked for it.")
            except Exception:
                return
        if payload.message_id in self.mutes:
            member = guild.get_member(payload.user_id)
            if member is None:
                return
            if member.bot:
                return
            if await self.is_mod_or_admin(member):
                return
            try:
                r = guild.get_role(241943133003317249)
                await member.add_roles(r, reason="They asked for it.")
            except Exception:
                return
        if payload.message_id in self.feedback:
            if payload.user_id in self.feedback[payload.message_id]:
                return
            member = guild.get_member(payload.user_id)
            if member is None:
                return
            if member.bot:
                return
            channel = guild.get_channel(payload.channel_id)
            msg = await channel.get_message(payload.message_id)
            ctx = await self.bot.get_context(msg)
            if await self.is_mod_or_admin(member) or str(payload.emoji) == "🐶":
                try:
                    compliment = self.bot.get_cog("Compliment").compliment
                except AttributeError:
                    compliment = self.bot.get_cog("Insult").insult
                await ctx.invoke(compliment, user=member)
            else:
                insult = self.bot.get_cog("Insult").insult
                await ctx.invoke(insult, user=member)
            self.feedback[payload.message_id].append(member.id)
