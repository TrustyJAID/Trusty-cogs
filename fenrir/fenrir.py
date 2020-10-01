import discord
from redbot import VersionInfo, version_info
from redbot.core import Config, checks, commands
from redbot.core.bot import Red


class Fenrir(commands.Cog):
    """
    Various unreasonable commands inspired by Fenrir
    """

    __version__ = "1.0.3"
    __author__ = ["TrustyJAID"]

    def __init__(self, bot):
        self.bot: Red = bot
        self.kicks: list = []
        self.bans: list = []
        self.mutes: list = []
        self.feedback: dict = {}
        default_guild: dict = {"mute_role": None}

        self.config: Config = Config.get_conf(self, 228492507124596736)
        self.config.register_guild(**default_guild)

    def format_help_for_context(self, ctx: commands.Context) -> str:
        """
        Thanks Sinbad!
        """
        pre_processed = super().format_help_for_context(ctx)
        return f"{pre_processed}\n\nCog Version: {self.__version__}"

    async def red_delete_data_for_user(self, **kwargs):
        """
        Nothing to delete
        """
        return

    @commands.command()
    @checks.admin_or_permissions(kick_members=True)
    @commands.guild_only()
    async def fenrirkick(self, ctx: commands.Context) -> None:
        """Create a reaction emoji to kick users"""
        msg = await ctx.send("React to this message to be kicked!")
        await msg.add_reaction("✅")
        await msg.add_reaction("❌")
        self.kicks.append(msg.id)

    @commands.command()
    @checks.admin_or_permissions(manage_roles=True)
    @commands.guild_only()
    async def fenrirset(self, ctx: commands.Context, *, role: discord.Role = None) -> None:
        """
        Sets the mute role for fenrirmute to work

        if no role is provided it will disable the command
        """
        if role:
            await self.config.guild(ctx.guild).mute_role.set(role.id)
        else:
            await self.config.guild(ctx.guild).mute_role.set(role)
        await ctx.tick()

    @commands.command()
    @checks.admin_or_permissions(ban_members=True)
    @commands.guild_only()
    async def fenrirban(self, ctx: commands.Context) -> None:
        """Create a reaction emoji to ban users"""
        msg = await ctx.send("React to this message to be banned!")
        await msg.add_reaction("✅")
        await msg.add_reaction("❌")
        self.bans.append(msg.id)

    @commands.command()
    @checks.admin_or_permissions(ban_members=True)
    @commands.guild_only()
    async def fenrirmute(self, ctx: commands.Context) -> None:
        """Create a reaction emoji to mute users"""
        if not await self.config.guild(ctx.guild).mute_role():
            return await ctx.send("No mute role has been setup on this server.")
        msg = await ctx.send("React to this message to be muted!")
        await msg.add_reaction("✅")
        await msg.add_reaction("❌")
        self.mutes.append(msg.id)

    @commands.command(aliases=["fenririnsult"])
    @checks.mod_or_permissions(manage_messages=True)
    @commands.guild_only()
    @commands.check(lambda ctx: ctx.bot.get_cog("Insult"))
    async def fenrirfeedback(self, ctx: commands.Context) -> None:
        """Create a reaction emoji to insult users"""
        msg = await ctx.send("React to this message to be insulted!")
        await msg.add_reaction("✅")
        await msg.add_reaction("❌")
        self.feedback[msg.id] = []

    async def is_mod_or_admin(self, member: discord.Member) -> bool:
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

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent) -> None:
        try:
            guild = self.bot.get_guild(payload.guild_id)
        except Exception:
            return
        if version_info >= VersionInfo.from_str("3.4.0"):
            if await self.bot.cog_disabled_in_guild(self, guild):
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
                await member.ban(reason="They asked for it.", delete_message_days=0)
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
                r = guild.get_role(await self.config.guild(guild).mute_role())
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
            try:
                msg = await channel.fetch_message(payload.message_id)
            except Exception:
                return
            ctx = await self.bot.get_context(msg)
            if await self.is_mod_or_admin(member) or str(payload.emoji) == "\N{DOG FACE}":
                try:
                    compliment = self.bot.get_command("compliment")
                except AttributeError:
                    compliment = self.bot.get_command("insult")
                if compliment:
                    await ctx.invoke(compliment, user=member)
            else:
                insult = self.bot.get_command("insult")
                await ctx.invoke(insult, user=member)
            self.feedback[payload.message_id].append(member.id)
