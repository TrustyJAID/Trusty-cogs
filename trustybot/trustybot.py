import discord
from redbot.core import commands, checks
from typing import Optional


class TrustyBot(commands.Cog):
    """
        This is mostly a test cog to try out new things
        before I figure out how to make them work elsewhere
        Generally for commands that don't fit anywhere else or are
        not meant to be used by anyone except TrustyBot
    """

    def __init__(self, bot):
        self.bot = bot

    @commands.command(hidden=True)
    @checks.is_owner()
    async def trustyrules(self, ctx):
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
    async def say(self, ctx, *, msg: str):
        """Say things as the bot"""
        await ctx.send(msg)

    @commands.command(hidden=True, aliases=["ss"])
    async def silentsay(self, ctx, *, msg: str):
        """Say things as the bot and deletes the command if it can"""
        if ctx.channel.permissions_for(ctx.guild).manage_messages:
            await ctx.message.delete()
        await ctx.send(msg)

    @commands.command(hidden=True, aliases=["hooksay"])
    @commands.bot_has_permissions(manage_webhooks=True)
    async def websay(self, ctx, member: Optional[discord.Member], *, msg: str):
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
    async def pingtime(self, ctx):
        """Ping pong."""

        # https://github.com/aikaterna/aikaterna-cogs/blob/v3/pingtime/pingtime.py
        msg = "Pong!\n"
        for shard, ping in ctx.bot.latencies:
            msg += f"Shard {shard+1}/{len(ctx.bot.latencies)}: {round(ping * 1000)}ms\n"
        await ctx.send(msg)

    @commands.command(aliases=["guildhelp", "serverhelp", "helpserver"])
    async def helpguild(self, ctx):
        """
            Invites you to TrustyBot's playground for testing
        """
        await ctx.send("https://discord.gg/wVVrqej")

    @commands.command()
    @commands.cooldown(1, 3600, commands.BucketType.guild)
    async def beemovie(self, ctx):
        """
            Yes the actual bee movie as emojis

            I was able to upload them to my server before Discord
            decreased the size limits on gif emojis
        """
        msg = (
            "<a:bm1_1:394355466022551552>"
            "<a:bm1_2:394355486625103872>"
            "<a:bm1_3:394355526496026624>"
            "<a:bm1_4:394355551859113985>"
            "<a:bm1_5:394355549581606912>"
            "<a:bm1_6:394355542849617943>"
            "<a:bm1_7:394355537925373952>"
            "<a:bm1_8:394355511912300554>\n"
            "<a:bm2_1:394355541616361475>"
            "<a:bm2_2:394355559719239690>"
            "<a:bm2_3:394355587409772545>"
            "<a:bm2_4:394355593567272960>"
            "<a:bm2_5:394355578337624064>"
            "<a:bm2_6:394355586067726336>"
            "<a:bm2_7:394355558104432661>"
            "<a:bm2_8:394355539716472832>\n"
            "<a:bm3_1:394355552626409473>"
            "<a:bm3_2:394355572381843459>"
            "<a:bm3_3:394355594955456532>"
            "<a:bm3_4:394355578253737984>"
            "<a:bm3_5:394355579096793098>"
            "<a:bm3_6:394355586411528192>"
            "<a:bm3_7:394355565788397568>"
            "<a:bm3_8:394355551556861993>\n"
            "<a:bm4_1:394355538181488640>"
            "<a:bm4_2:394355548944072705>"
            "<a:bm4_3:394355568669884426>"
            "<a:bm4_4:394355564504809485>"
            "<a:bm4_5:394355567843606528>"
            "<a:bm4_6:394355577758679040>"
            "<a:bm4_7:394355552655900672>"
            "<a:bm4_8:394355527867564032>"
        )
        if ctx.channel.permissions_for(ctx.me).embed_links:
            em = discord.Embed(title="The Entire Bee Movie", description=msg)
            await ctx.send(embed=em)
        else:
            await ctx.send(msg)

    @commands.command()
    async def donate(self, ctx):
        """Donate to the development of TrustyBot!"""
        msg = (
            "Help support me and my work on TrustyBot "
            "by buying my album or donating, details "
            "on my website at the bottom :smile: https://trustyjaid.com/"
        )
        await ctx.send(msg)

    @commands.command(hidden=False)
    async def halp(self, ctx, user: discord.Member = ""):
        """How to ask for help!"""
        msg = (
            f"{user} please type `{ctx.prefix}help` to be PM'd all my commands! "
            ":smile: or type `;guildhelp` to get an invite and "
            "I can help you personally."
        )
        await ctx.send(msg)
