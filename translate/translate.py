import aiohttp
import discord
from redbot.core import commands
from redbot.core import Config
from redbot.core import checks
from redbot.core.data_manager import bundled_data_path
import json
from .flags import FLAGS

"""
Translator cog 

Cog credit to aziz#5919 for the idea and 
 
Links

Wiki                                                https://goo.gl/3fxjSA
Github                                              https://goo.gl/oQAQde
Support the developer                               https://goo.gl/Brchj4
Invite the bot to your guild                       https://goo.gl/aQm2G7
Join the official development guild                https://discord.gg/uekTNPj
"""


class Translate(getattr(commands, "Cog", object)):
    """
        Translate messages using google translate
    """

    def __init__(self, bot):
        self.bot = bot
        self.session = aiohttp.ClientSession(loop=self.bot.loop)
        self.url = "https://translation.googleapis.com"
        self.config = Config.get_conf(self, 156434873547)
        default_guild = {"enabled":False}
        default = {"api_key":None}
        self.config.register_guild(**default_guild)
        self.config.register_global(**default)

    @commands.command(pass_context=True)
    async def translate(self, ctx, to_language, *, message):
        """
            Translate messages with google translate
        """
        
        if await self.config.api_key() is None:
            await ctx.send("The bot owner needs to set an api key first!")
            return
        if to_language in FLAGS:
            language_code = FLAGS[to_language]["code"]
        else:
            try:
                language_code = [FLAGS[lang]["code"] for lang in FLAGS if (FLAGS[lang]["name"].lower() in to_language.lower()) or (FLAGS[lang]["country"].lower() in to_language.lower())][0]
            except IndexError:
                await ctx.send("{} is not an available language!".format(to_language))
                return
        
        original_lang = await self.detect_language(message)
        from_lang = original_lang[0][0]["language"].upper()
        to_lang = language_code.upper()
        translated_text = await self.translate_text(original_lang[0][0]["language"], language_code, message)
        author = ctx.message.author
        user_name = f"{author.name}#{author.discriminator}"
        if ctx.channel.permissions_for(ctx.me).embed_links:
            em = discord.Embed(colour=author.top_role.colour, description=translated_text)
            em.set_author(name=author.display_name, icon_url=author.avatar_url)
            em.set_footer(text=f"{from_lang} to {to_language} Requested by {user_name}")
            await ctx.send(embed=em)
        else:
            await ctx.send(translated_text)

    async def detect_language(self, text):
        """
            Detect the language from given text
        """
        async with self.session.get(self.url + "/language/translate/v2/detect", params={"q":text, "key":await self.config.api_key()}) as resp:
                data = await resp.json()
        return data["data"]["detections"]


    async def translate_text(self, from_lang, target, text):
        """
            request to translate the text
        """
        formatting = "text"
        params = {"q":text, "target":target,"key":await self.config.api_key(), "format":formatting, "source":from_lang}
        try:
            async with self.session.get(self.url + "/language/translate/v2", params=params) as resp:
                data = await resp.json()
        except:
            return None
        if "data" in data:
            translated_text = data["data"]["translations"][0]["translatedText"]
            return translated_text

    @commands.command(pass_context=True)
    @checks.mod_or_permissions(manage_channels=True)
    @commands.guild_only()
    async def translatereact(self, ctx):
        """
            Have the bot translate messages when
            a flag is reacted to the message
        """
        guild = ctx.message.guild
        if not await self.config.guild(guild).enabled():
            await self.config.guild(guild).enabled.set(True)
            await ctx.send("{} has been added to post translated responses!".format(guild.name))
        elif await self.config.guild(guild).enabled():
            await self.config.guild(guild).enabled.set(False)
            await ctx.send("{} has been removed from translated responses!".format(guild.name))

    async def on_raw_reaction_add(self, payload):
        """
            Translates the message based off reactions
            with country flags
        """
        channel = self.bot.get_channel(id=payload.channel_id)
        try:
            guild = channel.guild
            message = await channel.get_message(id=payload.message_id)
        except:
            return
        if await self.config.api_key() is None:
            return
        # check_emoji = lambda emoji: emoji in FLAGS
        if str(payload.emoji) not in FLAGS:
            return
        if not await self.config.guild(guild).enabled():
            return
        if message.embeds != []:
            to_translate = message.embeds[0].description
        else:
            to_translate = message.clean_content
        num_emojis = 0
        for reaction in message.reactions:
            if reaction.emoji == str(payload.emoji):
                num_emojis = reaction.count
        if num_emojis > 1:
            return
        user = self.bot.get_user(payload.user_id)
        user_name = f"{user.name}#{user.discriminator}"
        target = FLAGS[str(payload.emoji)]["code"]
        original_lang = await self.detect_language(to_translate)
        translated_text = await self.translate_text(original_lang[0][0]["language"], target, to_translate)
        author = message.author
        em = discord.Embed(colour=author.top_role.colour, description=translated_text)
        em.set_author(name=author.display_name, icon_url=author.avatar_url)
        from_lang = original_lang[0][0]["language"].upper()
        to_lang = target.upper()
        if from_lang == to_lang:
            # don't post anything if the detected language is the same
            return
        em.set_footer(text=f"{from_lang} to {to_lang} Requested by {user_name}")
        if channel.permissions_for(guild.me).embed_links:
            await channel.send(embed=em)
        else:
            msg = f"{from_lang} to {to_lang} Requested by {user_name}\n{translated_text}"

    @commands.command(pass_context=True)
    @checks.is_owner()
    async def translateset(self, ctx, api_key):
        """
            You must get an API key from google to set this up

            https://console.cloud.google.com/apis/library/translate.googleapis.com/
        """
        await self.config.api_key.set(api_key)
        await ctx.send("API key set.")

    def __unload(self):
        self.bot.loop.create_task(self.session.close())
