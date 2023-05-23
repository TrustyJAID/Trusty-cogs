from typing import Dict, Optional, Set

import discord
from red_commons.logging import getLogger
from redbot import VersionInfo, version_info
from redbot.core import Config, checks, commands
from redbot.core.bot import Red
from redbot.core.utils.chat_formatting import humanize_list

log = getLogger("red.trusty-cogs.Fenrir")


class Fenrir(commands.Cog):
    """
    Various unreasonable commands inspired by Fenrir
    """

    __version__ = "1.2.0"
    __author__ = ["TrustyJAID"]

    def __init__(self, bot):
        self.bot: Red = bot
        self.kicks: Set[int] = set()
        self.bans: Set[int] = set()
        self.mutes: Set[int] = set()
        self.feedback: Dict[int, Set[int]] = {}
        self.lockdown: Set[int] = set()
        self.block: Dict[int, Set[int]] = {}
        default_guild: Dict[str, Optional[int]] = {"mute_role": None}

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

    async def insult_user(self, ctx: commands.Context):
        insult = self.bot.get_command("insult")
        if insult:
            await ctx.invoke(insult, user=ctx.author)

    async def bot_check_once(self, ctx: commands.Context):
        if await self.bot.is_owner(ctx.author):
            return True
        if not ctx.guild:
            return True
        if ctx.guild.id in self.block and ctx.author.id in self.block[ctx.guild.id]:
            await self.insult_user(ctx)
            return False
        if ctx.guild.owner_id == ctx.author.id:
            return True

        if await self.bot.is_admin(ctx.author) or ctx.author.guild_permissions.administrator:
            return True
        if ctx.guild and ctx.guild.id in self.lockdown:
            await self.insult_user(ctx)
            return False
        return True

    @commands.group(invoke_without_command=True)
    async def fenrir(self, ctx: commands.Context):
        """
        We're Moving on.
        """
        await ctx.send(
            "https://cdn.discordapp.com/attachments/290329951184355328/862891414690201601/HMQA3-XvnbN5V.png"
        )

    @fenrir.command(name="kick")
    @checks.admin_or_permissions(kick_members=True)
    @commands.guild_only()
    async def fenrirkick(self, ctx: commands.Context) -> None:
        """Create a reaction emoji to kick users"""
        msg = await ctx.send("React to this message to be kicked!")
        await msg.add_reaction("✅")
        await msg.add_reaction("❌")
        self.kicks.add(msg.id)

    @fenrir.command(name="lockdown", aliases=["lockdonw"])
    @checks.admin_or_permissions(administrator=True)
    @commands.guild_only()
    async def fenrirlockdown(self, ctx: commands.Context) -> None:
        """Replace all commands in the server with insults

        Run this command again to disable it.
        """
        if ctx.guild.id not in self.lockdown:
            await ctx.send(f"{ctx.guild.name} is now in lockdown.")
            self.lockdown.add(ctx.guild.id)
        else:
            await ctx.send(f"{ctx.guild.name} is no longer in lockdown.")
            self.lockdown.remove(ctx.guild.id)

    @fenrir.command(name="block")
    @checks.admin_or_permissions(administrator=True)
    @commands.guild_only()
    async def fenrirblock(self, ctx: commands.Context, *members: discord.Member) -> None:
        """Replaces all commands for specific members with insults"""
        if not members:
            await ctx.send_help()
        added = []
        removed = []
        if ctx.guild.id not in self.block:
            self.block[ctx.guild.id] = set()
        for member in members:
            if member.id not in self.block[ctx.guild.id]:
                self.block[ctx.guild.id].add(member.id)
                added.append(member)
            else:
                self.block[ctx.guild.id].remove(member.id)
                removed.append(member)
        msg = ""
        if added:
            msg += (
                f"The following members have had their bot command "
                f"privleges revoked: {humanize_list([m.mention for m in added])}"
            )
        if removed:
            msg += (
                f"The following members have had their bot command "
                f"privleges re-instated: {humanize_list([m.mention for m in removed])}"
            )
        if msg:
            await ctx.send(msg, allowed_mentions=discord.AllowedMentions(users=False))

    @fenrir.command(name="set")
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

    @fenrir.command(name="ban")
    @checks.admin_or_permissions(ban_members=True)
    @commands.guild_only()
    async def fenrirban(self, ctx: commands.Context) -> None:
        """Create a reaction emoji to ban users"""
        msg = await ctx.send("React to this message to be banned!")
        await msg.add_reaction("✅")
        await msg.add_reaction("❌")
        self.bans.add(msg.id)

    @fenrir.command(name="mute")
    @checks.admin_or_permissions(ban_members=True)
    @commands.guild_only()
    async def fenrirmute(self, ctx: commands.Context) -> None:
        """Create a reaction emoji to mute users"""
        if not await self.config.guild(ctx.guild).mute_role():
            return await ctx.send("No mute role has been setup on this server.")
        msg = await ctx.send("React to this message to be muted!")
        await msg.add_reaction("✅")
        await msg.add_reaction("❌")
        self.mutes.add(msg.id)

    @fenrir.command(name="feedback", aliases=["fenririnsult"])
    @checks.mod_or_permissions(manage_messages=True)
    @commands.guild_only()
    @commands.check(lambda ctx: ctx.bot.get_cog("Insult"))
    async def fenrirfeedback(self, ctx: commands.Context) -> None:
        """Create a reaction emoji to insult users"""
        msg = await ctx.send("React to this message to be insulted!")
        await msg.add_reaction("✅")
        await msg.add_reaction("❌")
        self.feedback[msg.id] = set()

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
            channel = guild.get_channel_or_thread(payload.channel_id)
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
            self.feedback[payload.message_id].add(member.id)
