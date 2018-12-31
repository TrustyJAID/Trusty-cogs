import aiohttp
import discord
from redbot.core import commands, Config, checks
from redbot.core.i18n import Translator, cog_i18n

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

BASE_URL = "https://translation.googleapis.com"
_ = Translator("Starboard", __file__)


@cog_i18n(_)
class Translate(getattr(commands, "Cog", object)):
    """
        Translate messages using google translate
    """

    def __init__(self, bot):
        self.bot = bot
        self.session = aiohttp.ClientSession(loop=self.bot.loop)
        self.config = Config.get_conf(self, 156434873547)
        default_guild = {"enabled":False}
        default = {"api_key":None}
        self.config.register_guild(**default_guild)
        self.config.register_global(**default)

    @commands.command()
    async def translate(self, ctx, to_language, *, message):
        """
            Translate messages with google translate

            `to_language` is the language you would like to translate
            `message` is the message to translate
        """
        
        if await self.config.api_key() is None:
            msg = _("The bot owner needs to set an api key first!")
            await ctx.send(msg)
            return
        if to_language in FLAGS:
            language_code = FLAGS[to_language]["code"]
        else:
            language_code = await self.get_to_language_code(to_language)
            if language_code is None:
                msg = to_language + _(" is not an available language!")
                await ctx.send(msg)
                return
        
        detected_lang = await self.detect_language(message)
        from_lang = detected_lang[0][0]["language"].upper()
        original_lang = detected_lang[0][0]["language"]
        to_lang = language_code.upper()
        translated_text = await self.translate_text(original_lang, 
                                                    language_code, 
                                                    message)
        author = ctx.message.author
        if ctx.channel.permissions_for(ctx.me).embed_links:
            em = discord.Embed(colour=author.colour, 
                               description=translated_text)
            em.set_author(name=author.display_name + _(" Said:"),
                          icon_url=author.avatar_url)
            detail_string = (from_lang + _(" to ") + to_lang + " | " +
                             _("Requested by ") + str(author))
            em.set_footer(text=detail_string)
            await ctx.send(embed=em)
        else:
            await ctx.send(translated_text)

    async def get_to_language_code(self, to_language):
        code = None
        for lang in FLAGS:
            if FLAGS[lang]["name"].lower() in to_language.lower():
                code = FLAGS[lang]["code"]
            if FLAGS[lang]["country"].lower() in to_language.lower():
                code = FLAGS[lang]["code"]
        return code

    async def detect_language(self, text):
        """
            Detect the language from given text
        """
        params = {"q":text, "key":await self.config.api_key()}
        url = BASE_URL + "/language/translate/v2/detect"
        async with self.session.get(url, params=params) as resp:
                data = await resp.json()
        return data["data"]["detections"]



    async def translate_text(self, from_lang, target, text):
        """
            request to translate the text
        """
        formatting = "text"
        params = {"q":text, 
                  "target":target,
                  "key":await self.config.api_key(), 
                  "format":formatting, 
                  "source":from_lang}
        url = BASE_URL + "/language/translate/v2"
        try:
            async with self.session.get(url, params=params) as resp:
                data = await resp.json()
        except:
            return None
        if "data" in data:
            translated_text = data["data"]["translations"][0]["translatedText"]
            return translated_text

    @commands.command()
    @checks.mod_or_permissions(manage_channels=True)
    @commands.guild_only()
    async def translatereact(self, ctx):
        """
            Toggle the bot responding to flag emojis
            to translate text
        """
        guild = ctx.message.guild
        if not await self.config.guild(guild).enabled():
            await self.config.guild(guild).enabled.set(True)
            msg = guild.name + _(" has been added to post"
                                 " translated responses!")
            await ctx.send(msg)
        elif await self.config.guild(guild).enabled():
            await self.config.guild(guild).enabled.set(False)
            msg = guild.name + _(" has been removed from"
                                 " translated responses!")
            await ctx.send(msg)

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
        target = FLAGS[str(payload.emoji)]["code"]
        detected_lang = await self.detect_language(to_translate)
        original_lang = detected_lang[0][0]["language"]
        translated_text = await self.translate_text(original_lang, 
                                                    target, 
                                                    to_translate)
        author = message.author
        em = discord.Embed(colour=author.colour, 
                           description=translated_text[:2048])
        em.set_author(name=author.display_name + _(" Said:"), 
                      icon_url=author.avatar_url)
        from_lang = detected_lang[0][0]["language"].upper()
        to_lang = target.upper()
        if from_lang == to_lang:
            # don't post anything if the detected language is the same
            return
        detail_string = (from_lang + _(" to ") + to_lang + " | " +
                         _("Requested by ") + str(user))
        em.set_footer(text=detail_string)
        if channel.permissions_for(guild.me).embed_links:
            await channel.send(embed=em)
        else:
            msg = (detail_string + f"\n{translated_text}")

    @commands.command()
    @checks.is_owner()
    async def translateset(self, ctx, api_key):
        """
            You must get an API key from google to set this up

            Note: Using this cog costs money, current rates are $20 per 1 million characters.

            1. Go to Google Developers Console and log in with your Google account. 
            (https://console.developers.google.com/)
            2. You should be prompted to create a new project (name does not matter).
            3. Click on Enable APIs and Services at the top.
            4. In the list of APIs choose or search for Cloud Translate API and click on it. 
            Choose Enable.
            5. Click on Credentials on the left navigation bar.
            6. Click on Create Credential at the top.
            7. At the top click the link for \"API key\".
            8. No application restrictions are needed. Click Create at the bottom.
            9. You now have a key to add to `[p]translateset`
        """
        await self.config.api_key.set(api_key)
        await ctx.send(_("API key set."))

    def __unload(self):
        self.bot.loop.create_task(self.session.close())
