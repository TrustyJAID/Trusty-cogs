from random import choice, randint
import random
import aiohttp
import discord
import asyncio
from redbot.core import commands
from redbot.core import checks, bank
from redbot.core.utils.chat_formatting import pagify, box
from redbot.core.data_manager import bundled_data_path
from redbot.core.data_manager import cog_data_path
from .data import links, messages, donotdo
import datetime
import os
import string
import time
import io
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import pagify, box

from discord import Webhook, AsyncWebhookAdapter

_ = Translator("TrustyBot", __file__)

numbs = {
    "next": "➡",
    "back": "⬅",
    "exit": "❌"
}


class TrustyBot(getattr(commands, "Cog", object)):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(hidden=True)
    @checks.is_owner()
    async def trustyrules(self, ctx):
        rules = """1. Don't be a jerk - We're here to have fun and enjoy music, new bot features, and games!\n
2. No sharing of personal or confidential information - This is a [discord Terms of Service](https://discordapp.com/terms) violation and can result in immediate ban.\n
3. Keep NSFW content in <#412884243195232257> anything outside there deemed NSFW by a mod can and will be deleted as per discords [Community Guidelines](https://discordapp.com/guidelines).\n
4. Do not harass, threaten, or otherwise make another user feel poorly about themselves - This is another [discord TOS](https://discordapp.com/terms) violation.\n
5. Moderator action is at the discretion of a moderator and changes may be made without warning to your privliges.\n
***Any violation of the [discord TOS](https://discordapp.com/terms) or [Community Guidelines](https://discordapp.com/guidelines) will result in immediate banning and possible report to discord.***\n
"""
        em = discord.Embed(colour=discord.Colour.gold())
        em.add_field(name="__RULES__", value=rules)
        em.set_image(url="https://i.imgur.com/6FPYjoU.gif")
        # em.set_thumbnail(url="https://i.imgur.com/EfOnDQy.gif")
        em.set_author(name=ctx.guild.name, icon_url="https://i.imgur.com/EfOnDQy.gif")
        await ctx.message.delete()
        await ctx.send(embed=em)

    @commands.command(hidden=True)
    async def warfarerules(self, ctx):
        rules = """1. **Meme Warfare** is your "*File Cabinet*" for members to *deposit* and *withdraw* memes. If you would like to post memes, ask an <@&402164942192640001> for the *Poster* role.\n
2. The meme channels are ***ONLY*** for Memes. We would like to keep the channels free from conversations as we need to grab the memes and "go fast".\n
3. Wanna be extra-comfy? Click on the subject/category headers to collapse them. Right Click -> Mark as Read -> Collapse Channels is another way to accomplish this.\n
4. Right Click -> Mute channels that don't interest you so that you won't keep receiving notifications.\n
5. <#407705381922537483>/<#424742925474332683> chat is available for striking up conversations about current events and various non-Q-related topics.\n
6. No sharing of personal or confidential information of others - This is a [discord Terms of Service](https://discordapp.com/terms) violation and can result in immediate ban.\n
7. Do not harass or threaten other members, this extends to other discord servers - This is another [discord TOS](https://discordapp.com/terms) violation.\n
8. <@&402164942192640001> action is at the discretion of an <@&402164942192640001> and changes may be made without warning to your privileges.\n
***Any violation of the [discord TOS](https://discordapp.com/terms) or [Community Guidelines](https://discordapp.com/guidelines) will result in immediate banning and possible report to Discord.***\n
"""
        roles = """**Q-RESEARCH**: Q-related research goes in this channel. Remember to always provide "links/sauce" for your research. Images drops must include an article reference.\n
**TRAINING-HOW-TO-MEME**: Teach people how to create memes and instruct others on the purpose of a meme.\n
"""
        rules_3 = """**HIGHEST PRIORITY**: Hottest memes in rotation.\n
**MEMEWORTHY**: Memes that are very relevant. These could move to *HIGHEST PRIORITY* or *DUSTY MEMES*\n
**HOLLYWOOD**: Memes about the corruption in the entertainment industry.\n
**OPERATION MOCKINGBIRD**: Memes about *Fake News* and the *Shadow Government* pushing the narrative.\n
**POLITICS**: Memes about politicians by name.\n
**DUSTY MEMES**: Memes that have lost relevance with current events. These could still return to *HIGHEST PRIORITY* or *MEMEWORTHY*.\n
**OPERATION REDPILL**: How to redpill individuals in real life.\n
        """
        em = discord.Embed(colour=int("1975e1", 16))
        em.title = "__**BASIC OPERATIONS**__"
        em.description = rules
        # em.add_field(name="__**BASIC OPERATIONS**__", value=rules)
        em.add_field(name="__**TOP CATEGORIES**__", value=roles)
        em.add_field(name="__**MEME CATEGORIES**__", value=rules_3)
        # em.set_image(url="https://nhl.bamcontent.com/images/photos/281721030/256x256/cut.png")
        em.set_thumbnail(url=ctx.message.guild.icon_url)
        em.set_author(name=ctx.guild.name, icon_url=ctx.message.guild.icon_url)
        await ctx.message.delete()
        if ctx.message.guild.id == 402161292644712468:
            await ctx.send(embed=em)

    @commands.command(hidden=True)
    async def say(self, ctx, *, msg):
        """Say things as the bot"""
        await ctx.send(msg)

    @commands.command(hidden=True, aliases=["ss"])
    async def silentsay(self, ctx, *, msg):
        """Say things as the bot and deletes the command if it can"""
        if ctx.channel.permissions_for(ctx.guild).manage_messages:
            await ctx.message.delete()
        await ctx.send(msg)

    @commands.command(hidden=True, aliases=["hooksay"])
    async def websay(self, ctx, member:discord.Member, *, msg):
        """Say things as another user"""
        if not ctx.channel.permissions_for(ctx.guild.me).manage_webhooks:
            await ctx.send("I don't have manage_webhooks permission.")
            return
        if ctx.channel.permissions_for(ctx.guild).manage_messages:
            await ctx.message.delete()
        guild = ctx.guild
        webhook = None
        for hook in await ctx.channel.webhooks():
            if hook.name == guild.me.name:
                webhook = hook
        if webhook is None:
            webhook = await ctx.channel.create_webhook(name=guild.me.name)
        avatar = member.avatar_url_as(format="png")
        await webhook.send(msg, username=member.display_name, avatar_url=avatar)

    @commands.command()
    async def pingtime(self, ctx):
        t1 = time.perf_counter()
        await ctx.channel.trigger_typing()
        t2 = time.perf_counter()
        await ctx.send("pong: {}ms".format(round((t2-t1)*1000)))

    @commands.command(pass_context=True, aliases=["guildhelp", "serverhelp", "helpserver"])
    async def helpguild(self, ctx):
        await ctx.send("https://discord.gg/wVVrqej")

    @commands.command()
    @commands.cooldown(1, 3600, commands.BucketType.guild)
    async def beemovie(self, ctx):
        msg = "<a:bm1_1:394355466022551552><a:bm1_2:394355486625103872><a:bm1_3:394355526496026624><a:bm1_4:394355551859113985><a:bm1_5:394355549581606912><a:bm1_6:394355542849617943><a:bm1_7:394355537925373952><a:bm1_8:394355511912300554>\n<a:bm2_1:394355541616361475><a:bm2_2:394355559719239690><a:bm2_3:394355587409772545><a:bm2_4:394355593567272960><a:bm2_5:394355578337624064><a:bm2_6:394355586067726336><a:bm2_7:394355558104432661><a:bm2_8:394355539716472832>\n<a:bm3_1:394355552626409473><a:bm3_2:394355572381843459><a:bm3_3:394355594955456532><a:bm3_4:394355578253737984><a:bm3_5:394355579096793098><a:bm3_6:394355586411528192><a:bm3_7:394355565788397568><a:bm3_8:394355551556861993>\n<a:bm4_1:394355538181488640><a:bm4_2:394355548944072705><a:bm4_3:394355568669884426><a:bm4_4:394355564504809485><a:bm4_5:394355567843606528><a:bm4_6:394355577758679040><a:bm4_7:394355552655900672><a:bm4_8:394355527867564032>"
        em = discord.Embed(title="The Entire Bee Movie", description=msg)
        await ctx.send(embed=em)
    
    @commands.command()
    async def neat(self, ctx, number:int=None):
        """Neat"""
        files = str(cog_data_path(self)) + "/bundled_data/neat{}.gif"
        if number is None:
            image = discord.File(files.format(str(choice(range(1, 6)))))
            await ctx.send(file=image)
        elif(int(number) > 0 or int(number) < 8):
            image = discord.File(files.format(number))
            await ctx.send(file=image)

    @commands.command()
    async def reviewbrah(self, ctx):
        """Reviewbrah"""
        files = ["/bundled_data/revi.png", "/bundled_data/ew.png", "/bundled_data/brah.png"]
        print(cog_data_path(self))
        for file in files:
            data = discord.File(str(cog_data_path(self))+file)
            await ctx.send(file=data)

    @commands.command()
    async def donate(self, ctx):
        """Donate to the development of TrustyBot!"""
        await ctx.send("Help support me  and development of TrustyBot by buying my album or donating bitcoin on my website :smile: https://trustyjaid.com/")
    
    @commands.command()
    async def donotdo(self, ctx, number=None):
        if number is None:
            await ctx.send(choice(donotdo))
        elif number.isdigit():
            await ctx.send(donotdo[int(number)-1])
        else:
            await ctx.send(choice(donotdo))

    @commands.command(hidden=False)
    async def halp(self,ctx, user=None):
        """How to ask for help!"""
        msg = "{} please type `;help` to be PM'd all my commands! :smile: or type `;guildhelp` to get an invite and I can help you personally."
        if user is None:
            await ctx.send(msg.format(""))
        else:
            await ctx.send(msg.format(user))

    @commands.command()
    async def flipm(self, ctx, *, message):
        """Flips a message"""
        msg = ""
        name = ""
        for user in message:
            char = "abcdefghijklmnopqrstuvwxyz - ABCDEFGHIJKLMNOPQRSTUVWXYZ"
            tran = "ɐqɔpǝɟƃɥᴉɾʞlɯuodbɹsʇnʌʍxʎz - ∀qƆpƎℲפHIſʞ˥WNOԀQᴚS┴∩ΛMX⅄Z"
            table = str.maketrans(char, tran)
            name += user.translate(table) + " "
        await ctx.send(msg + "(╯°□°）╯︵ " + name[::-1])

    @commands.command()
    @checks.is_owner()
    async def makerole(self, ctx):
        guild = ctx.guild
        role = await guild.create_role(
            name="Muted",
            reason="A random reason",
        )
        await role.edit(
            position=guild.me.top_role.position - 1,
            reason=(
                "Modifying role's position, keep it under my top role so "
                "I can add it to muted members."
            ),
        )
    