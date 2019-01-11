import aiohttp
import discord
from redbot.core import commands, Config, checks
from redbot.core.i18n import Translator, cog_i18n
from discord.ext.commands.converter import Converter
from discord.ext.commands.errors import BadArgument

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
_ = Translator("Translate", __file__)


class FlagTranslation(Converter):
    """
    This will convert flags and languages to the correct code to be used by the API

    Guidance code on how to do this from:
    https://github.com/Rapptz/discord.py/blob/rewrite/discord/ext/commands/converter.py#L85
    https://github.com/Cog-Creators/Red-DiscordBot/blob/V3/develop/redbot/cogs/mod/mod.py#L24
    
    """
    async def convert(self, ctx, argument):
        result = []
        if argument in FLAGS:
            result = FLAGS[argument]["code"].upper()
        else:
            for lang in FLAGS:
                if FLAGS[lang]["name"].lower() in argument.lower():
                    result = FLAGS[lang]["code"].upper()
                if FLAGS[lang]["country"].lower() in argument.lower():
                    result = FLAGS[lang]["code"].upper()
        if result is None:
            raise BadArgument('Language "{}" not found'.format(argument))

        return result


@cog_i18n(_)
class Translate(getattr(commands, "Cog", object)):
    """
        Translate messages using google translate
    """

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, 156434873547)
        default_guild = {"reaction":False, "text":False}
        default = {"api_key":None}
        self.config.register_guild(**default_guild)
        self.config.register_global(**default)

    async def detect_language(self, text):
        """
            Detect the language from given text
        """
        params = {"q":text, "key":await self.config.api_key()}
        url = BASE_URL + "/language/translate/v2/detect"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params) as resp:
                    data = await resp.json()
        return data["data"]["detections"]

    async def translation_embed(self, author, translation, requestor=None):
        em = discord.Embed(colour=author.colour, 
                           description=translation[0])
        em.set_author(name=author.display_name + _(" said:"),
                      icon_url=author.avatar_url)
        detail_string = (translation[1] + _(" to ") + translation[2] + " | " +
                         _("Requested by "))
        if requestor:
            detail_string += str(requestor)
        else:
            detail_string += str(author)
        em.set_footer(text=detail_string)
        return em

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
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params) as resp:
                    data = await resp.json()
        except:
            return None
        if "data" in data:
            translated_text = data["data"]["translations"][0]["translatedText"]
            return translated_text

    async def on_message(self, message):
        """
            Translates the message based off reactions
            with country flags
        """
        if not message.guild:
            return
        if message.author.bot:
            return
        channel = message.channel
        guild = message.guild
        if await self.config.api_key() is None:
            return
        # check_emoji = lambda emoji: emoji in FLAGS
        if not await self.config.guild(guild).text():
            return
        if not await self.local_perms(message):
            return
        if not await self.global_perms(message):
            return
        if not await self.check_ignored_channel(message):
            return
        has_flag = False
        for word in message.clean_content.split(" "):
            if word in FLAGS:
                has_flag = True
                flag = word
        if not has_flag:
            return
        if message.embeds != []:
            to_translate = message.embeds[0].description
        else:
            to_translate = message.clean_content
        detected_lang = await self.detect_language(to_translate)
        original_lang = detected_lang[0][0]["language"]
        target = FLAGS[flag]["code"]
        if target == original_lang:
            return
        translated_text = await self.translate_text(original_lang, 
                                                    target, 
                                                    to_translate)
        if not translated_text:
            return
        author = message.author
        from_lang = detected_lang[0][0]["language"].upper()
        to_lang = target.upper()
        if from_lang == to_lang:
            # don't post anything if the detected language is the same
            return
        translation = (translated_text, from_lang, to_lang)
        
        if channel.permissions_for(guild.me).embed_links:
            em = await self.translation_embed(author, translation)
            await channel.send(embed=em)
        else:
            msg = f"{author.display_name} " + _("said:") + "\n"
            await channel.send(msg + translated_text)

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
        if not await self.config.guild(guild).reaction():
            return
        if str(payload.emoji) not in FLAGS:
            return
        if not await self.local_perms(message):
            return
        if not await self.global_perms(message):
            return
        if not await self.check_ignored_channel(message):
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
        if target == original_lang:
            return
        translated_text = await self.translate_text(original_lang, 
                                                    target, 
                                                    to_translate)
        if not translated_text:
            return
        author = message.author
        from_lang = detected_lang[0][0]["language"].upper()
        to_lang = target.upper()
        if from_lang == to_lang:
            # don't post anything if the detected language is the same
            return
        translation = (translated_text, from_lang, to_lang)
        
        if channel.permissions_for(guild.me).embed_links:
            em = await self.translation_embed(author, translation, user)
            await channel.send(embed=em)
        else:
            msg = (detail_string + f"\n{translated_text}")
            await channel.send(msg)

    async def local_perms(self, message):
        """Check the user is/isn't locally whitelisted/blacklisted.
            https://github.com/Cog-Creators/Red-DiscordBot/blob/V3/release/3.0.0/redbot/core/global_checks.py
        """
        if await self.bot.is_owner(message.author):
            return True
        elif message.guild is None:
            return True
        guild_settings = self.bot.db.guild(message.guild)
        local_blacklist = await guild_settings.blacklist()
        local_whitelist = await guild_settings.whitelist()

        _ids = [r.id for r in message.author.roles if not r.is_default()]
        _ids.append(message.author.id)
        if local_whitelist:
            return any(i in local_whitelist for i in _ids)

        return not any(i in local_blacklist for i in _ids)

    async def global_perms(self, message):
        """Check the user is/isn't globally whitelisted/blacklisted.
            https://github.com/Cog-Creators/Red-DiscordBot/blob/V3/release/3.0.0/redbot/core/global_checks.py
        """
        if await self.bot.is_owner(message.author):
            return True

        whitelist = await self.bot.db.whitelist()
        if whitelist:
            return message.author.id in whitelist

        return message.author.id not in await self.bot.db.blacklist()

    async def check_ignored_channel(self, message):
        """https://github.com/Cog-Creators/Red-DiscordBot/blob/V3/release/3.0.0/redbot/cogs/mod/mod.py#L1273"""
        channel = message.channel
        guild = channel.guild
        author = message.author
        mod = self.bot.get_cog("Mod")
        perms = channel.permissions_for(author)
        surpass_ignore = (
            isinstance(channel, discord.abc.PrivateChannel)
            or perms.manage_guild
            or await self.bot.is_owner(author)
            or await self.bot.is_admin(author)
        )
        if surpass_ignore:
            return True
        guild_ignored = await mod.settings.guild(guild).ignored()
        chann_ignored = await mod.settings.channel(channel).ignored()
        return not (guild_ignored or chann_ignored and not perms.manage_channels)

    @commands.command()
    async def translate(self, ctx, to_language:FlagTranslation, *, message:str):
        """
            Translate messages with google translate

            `to_language` is the language you would like to translate
            `message` is the message to translate
        """
        
        if await self.config.api_key() is None:
            msg = _("The bot owner needs to set an api key first!")
            await ctx.send(msg)
            return        
        
        detected_lang = await self.detect_language(message)
        from_lang = detected_lang[0][0]["language"].upper()
        original_lang = detected_lang[0][0]["language"]
        translated_text = await self.translate_text(original_lang, 
                                                    to_language, 
                                                    message)
        author = ctx.message.author
        if ctx.channel.permissions_for(ctx.me).embed_links:
            translation = (translated_text, from_lang, to_language)
            em = await self.translation_embed(author, translation)
            await ctx.send(embed=em)
        else:
            await ctx.send(translated_text)

    @commands.group()
    @checks.mod_or_permissions(manage_channels=True)
    @commands.guild_only()
    async def translateset(self, ctx):
        """
            Toggle the bot auto translating
        """
        pass

    @translateset.command(aliases=["reaction", "reactions"])
    @checks.mod_or_permissions(manage_channels=True)
    @commands.guild_only()
    async def react(self, ctx):
        """
            Toggle translations to flag emoji reactions
        """
        guild = ctx.message.guild
        toggle = not await self.config.guild(guild).reaction()
        if toggle:
            verb = _("on")
        else:
            verb = _("off")
        await self.config.guild(guild).reaction.set(toggle)
        msg = _("Reaction translations have been turned ")
        await ctx.send(msg + verb)

    @translateset.command(aliases=["flags"])
    @checks.mod_or_permissions(manage_channels=True)
    @commands.guild_only()
    async def flag(self, ctx):
        """
            Toggle translations with flag emojis in text
        """
        guild = ctx.message.guild
        toggle = not await self.config.guild(guild).text()
        if toggle:
            verb = _("on")
        else:
            verb = _("off")
        await self.config.guild(guild).text.set(toggle)
        msg = _("Flag emoji translations have been turned ")
        await ctx.send(msg + verb)

    @translateset.command()
    @checks.is_owner()
    async def creds(self, ctx, api_key):
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
