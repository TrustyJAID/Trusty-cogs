from typing import Optional

import discord
from redbot.core import checks, commands


class TrustyBot(commands.Cog):
    """
    This is mostly a test cog to try out new things
    before I figure out how to make them work elsewhere
    Generally for commands that don't fit anywhere else or are
    not meant to be used by anyone except TrustyBot
    """

    __author__ = ["TrustyJAID"]
    __version__ = "1.0.0"

    def __init__(self, bot):
        self.bot = bot

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

    @commands.command(hidden=True)
    @checks.is_owner()
    async def trustyrules(self, ctx: commands.Context):
        """
        Display rules for Trusty's testing server
        """
        guidelines = "[Community Guidelines](https://discordapp.com/guidelines)"
        terms = "[Discord Terms of Service](https://discordapp.com/terms)"
        rules = (
            "1. Don't be a jerk - We're here to have fun "
            "and enjoy music, new bot features, and games!\n\n"
            "2. No sharing of personal or confidential information - "
            f"This is a {terms} "
            "violation and can result in immediate ban.\n\n"
            "3. No NSFW content, anything deemed NSFW by a mod can and will be "
            f"deleted as per discords {guidelines}.\n\n"
            "4. Do not harass, threaten, or otherwise make another user "
            "feel poorly about themselves - This is another "
            f"{terms} violation.\n\n"
            "5. Moderator action is at the discretion of a moderator and "
            "changes may be made without warning to your privliges.\n\n"
            f"***Violating {terms} or "
            f"{guidelines} will result "
            "in an immediate ban. You may also be reported to Discord.***\n\n"
        )
        em = discord.Embed(colour=discord.Colour.gold())
        em.add_field(name="__RULES__", value=rules)
        em.set_image(url="https://i.imgur.com/6FPYjoU.gif")
        # em.set_thumbnail(url="https://i.imgur.com/EfOnDQy.gif")
        em.set_author(name=ctx.guild.name, icon_url="https://i.imgur.com/EfOnDQy.gif")
        await ctx.message.delete()
        await ctx.send(embed=em)

    @commands.command(hidden=True)
    async def say(self, ctx: commands.Context, *, msg: str):
        """Say things as the bot"""
        await ctx.send(msg)

    @commands.command(hidden=True, aliases=["ss"])
    async def silentsay(self, ctx: commands.Context, *, msg: str):
        """Say things as the bot and deletes the command if it can"""
        if ctx.channel.permissions_for(ctx.guild).manage_messages:
            await ctx.message.delete()
        await ctx.send(msg)

    @commands.command(hidden=True, aliases=["hooksay"])
    @commands.bot_has_permissions(manage_webhooks=True)
    async def websay(self, ctx: commands.Context, member: Optional[discord.Member], *, msg: str):
        """
        Say things as another user

        The bot will create a webhook in the channel the command is sent in
        it will use that webhook to make messages that look like the
        `member` if provided otherwise it will default to the bot
        """
        if member is None:
            member = ctx.me
        if ctx.channel.permissions_for(ctx.me).manage_messages:
            await ctx.message.delete()
        guild = ctx.guild
        webhook = None
        for hook in await ctx.channel.webhooks():
            if hook.name == guild.me.name:
                webhook = hook
        if webhook is None:
            webhook = await ctx.channel.create_webhook(name=guild.me.name)
        avatar = member.avatar_url_as(format="png")
        msg = msg.replace("@everyone", "everyone").replace("@here", "here")
        for mention in ctx.message.mentions:
            msg = msg.replace(mention.mention, mention.display_name)
        # Apparently webhooks have @everyone permissions
        await webhook.send(msg, username=member.display_name, avatar_url=avatar)

    @commands.command()
    async def pingtime(self, ctx: commands.Context):
        """Ping pong."""

        # https://github.com/aikaterna/aikaterna-cogs/blob/v3/pingtime/pingtime.py
        msg = "Pong!\n"
        for shard, ping in ctx.bot.latencies:
            msg += f"Shard {shard+1}/{len(ctx.bot.latencies)}: {round(ping * 1000)}ms\n"
        await ctx.send(msg)

    @commands.command(aliases=["guildhelp", "serverhelp", "helpserver"])
    async def helpguild(self, ctx: commands.Context):
        """
        Invites you to TrustyBot's playground for testing

        https://discord.gg/wVVrqej
        """
        await ctx.send("https://discord.gg/wVVrqej")

    @commands.command()
    async def donate(self, ctx: commands.Context):
        """
        Donate to the development of TrustyBot!

        https://trustyjaid.com
        """
        msg = (
            "Help support me and my work on TrustyBot "
            "by buying my album or donating, details "
            "on my website at the bottom :smile: https://trustyjaid.com/"
        )
        await ctx.send(msg)
