import aiohttp
import discord
import logging
import asyncio
import time
import re

from redbot.core import Config, commands
from redbot.core.bot import Red
from redbot.core.i18n import Translator
from discord.ext.commands.converter import Converter
from discord.ext.commands.errors import BadArgument

from .flags import FLAGS
from .errors import GoogleTranslateAPIError

BASE_URL = "https://translation.googleapis.com"
_ = Translator("Translate", __file__)
log = logging.getLogger("red.trusty-cogs.Translate")

FLAG_REGEX = re.compile(r"|".join(rf"{re.escape(f)}" for f in FLAGS.keys()))
listener = getattr(commands.Cog, "listener", None)  # red 3.0 backwards compatibility support

if listener is None:  # thanks Sinbad
    def listener(name=None):
        return lambda x: x


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
                    result = FLAGS[lang]["code"]
                    break
                if FLAGS[lang]["country"].lower() in argument.lower():
                    result = FLAGS[lang]["code"]
                    break
                if not FLAGS[lang]["code"]:
                    continue
                if FLAGS[lang]["code"] in argument.lower() and len(argument) == 2:
                    result = FLAGS[lang]["code"]
                    break
        if not result:
            raise BadArgument('Language "{}" not found'.format(argument))

        return result


class GoogleTranslateAPI:
    config: Config
    bot: Red
    cache: dict

    def __init__(self, *_args):
        self.config: Config
        self.bot: Red
        self.cache: dict

    async def cleanup_cache(self):
        await self.bot.wait_until_ready()
        while self is self.bot.get_cog("Translate"):
            # cleanup the cache every 10 minutes
            self.cache = {"translations": []}
            await asyncio.sleep(600)

    async def detect_language(self, text):
        """
            Detect the language from given text
        """
        params = {"q": text, "key": await self.config.api_key()}
        url = BASE_URL + "/language/translate/v2/detect"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params) as resp:
                data = await resp.json()
        if "error" in data:
            log.error(data["error"]["message"])
            raise GoogleTranslateAPIError(data["error"]["message"])
        return data["data"]["detections"]

    async def translation_embed(self, author, translation, requestor=None):
        em = discord.Embed(colour=author.colour, description=translation[0])
        em.set_author(name=author.display_name + _(" said:"), icon_url=author.avatar_url)
        detail_string = _("{_from} to {_to} | Requested by ").format(
            _from=translation[1].upper(), _to=translation[2].upper()
        )
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
        params = {
            "q": text,
            "target": target,
            "key": await self.config.api_key(),
            "format": formatting,
            "source": from_lang,
        }
        url = BASE_URL + "/language/translate/v2"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params) as resp:
                    data = await resp.json()
        except Exception:
            return None
        if "error" in data:
            log.error(data["error"]["message"])
            raise GoogleTranslateAPIError(data["error"]["message"])
        if "data" in data:
            translated_text = data["data"]["translations"][0]["translatedText"]
            return translated_text

    @listener()
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
        author = message.author
        if await self.config.api_key() is None:
            return
        # check_emoji = lambda emoji: emoji in FLAGS
        if not await self.config.guild(guild).text():
            return
        if not await self.local_perms(guild, author):
            return
        if not await self.global_perms(author):
            return
        if not await self.check_ignored_channel(message):
            return
        flag = FLAG_REGEX.search(message.clean_content)
        if not flag:
            return
        if message.id in self.cache:
            if str(flag) in self.cache[message.id]["past_flags"]:
                return
            if not self.cache[message.id]["multiple"]:
                return
            if time.time() < self.cache[message.id]["wait"]:
                await channel.send(_("You're translating too many messages!"), delete_after=10)
                return
        if message.embeds != []:
            to_translate = message.embeds[0].description
        else:
            to_translate = message.clean_content
        try:
            detected_lang = await self.detect_language(to_translate)
        except GoogleTranslateAPIError:
            return
        original_lang = detected_lang[0][0]["language"]
        target = FLAGS[flag.group()]["code"]
        if target == original_lang:
            return
        try:
            translated_text = await self.translate_text(original_lang, target, to_translate)
        except GoogleTranslateAPIError:
            return
        if not translated_text:
            return

        from_lang = detected_lang[0][0]["language"].upper()
        to_lang = target.upper()
        if from_lang == to_lang:
            # don't post anything if the detected language is the same
            return
        translation = (translated_text, from_lang, to_lang)
        if message.id not in self.cache:
            cooldown = await self.config.cooldown()
        else:
            cooldown = self.cache[message.id]
        cooldown["wait"] = time.time() + cooldown["timeout"]
        cooldown["past_flags"].append(str(flag))
        self.cache[message.id] = cooldown
        if channel.permissions_for(guild.me).embed_links:
            em = await self.translation_embed(author, translation)
            translation = await channel.send(embed=em)
        else:
            msg = f"{author.display_name} " + _("said:") + "\n"
            translation = await channel.send(msg + translated_text)
        if not cooldown["multiple"]:
            self.cache["translations"].append(translation.id)

    @listener()
    async def on_raw_reaction_add(self, payload):
        """
            Translates the message based off reactions
            with country flags
        """
        if payload.message_id in self.cache["translations"]:
            return
        channel = self.bot.get_channel(id=payload.channel_id)
        try:
            if channel.recipient:
                return
        except AttributeError:
            pass
        guild = channel.guild
        user = guild.get_member(payload.user_id)
        try:
            message = await channel.fetch_message(id=payload.message_id)
        except AttributeError:
            message = await channel.get_message(id=payload.message_id)
            return
        except discord.errors.NotFound:
            return
        if user.bot:
            return
        if await self.config.api_key() is None:
            return
        # check_emoji = lambda emoji: emoji in FLAGS
        if not await self.config.guild(guild).reaction():
            return
        if str(payload.emoji) not in FLAGS:
            return
        if not await self.local_perms(guild, user):
            return
        if not await self.global_perms(user):
            return
        if not await self.check_ignored_channel(message):
            return

        if message.id in self.cache:
            if str(payload.emoji) in self.cache[message.id]["past_flags"]:
                return
            if not self.cache[message.id]["multiple"]:
                return
            if time.time() < self.cache[message.id]["wait"]:
                await channel.send(_("You're translating too many messages!"), delete_after=10)
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
        target = FLAGS[str(payload.emoji)]["code"]
        try:
            detected_lang = await self.detect_language(to_translate)
        except GoogleTranslateAPIError:
            return
        original_lang = detected_lang[0][0]["language"]
        if target == original_lang:
            return
        try:
            translated_text = await self.translate_text(original_lang, target, to_translate)
        except Exception:
            return
        if not translated_text:
            return
        author = message.author
        from_lang = detected_lang[0][0]["language"].upper()
        to_lang = target.upper()
        if from_lang == to_lang:
            # don't post anything if the detected language is the same
            return
        translation = (translated_text, from_lang, to_lang)
        if message.id not in self.cache:
            cooldown = await self.config.cooldown()
        else:
            cooldown = self.cache[message.id]
        cooldown["wait"] = time.time() + cooldown["timeout"]
        cooldown["past_flags"].append(str(payload.emoji))
        self.cache[message.id] = cooldown
        if channel.permissions_for(guild.me).embed_links:
            em = await self.translation_embed(author, translation, user)
            translation = await channel.send(embed=em)
        else:
            msg = _(
                "{author} said:\n{translated_text}"
            ).format(author=author, translate_text=translated_text)
            translation = await channel.send(msg)
        if not cooldown["multiple"]:
            self.cache["translations"].append(translation.id)

    async def local_perms(self, guild, author):
        """Check the user is/isn't locally whitelisted/blacklisted.
            https://github.com/Cog-Creators/Red-DiscordBot/blob/V3/release/3.0.0/redbot/core/global_checks.py
        """
        if await self.bot.is_owner(author):
            return True
        elif guild is None:
            return True
        guild_settings = self.bot.db.guild(guild)
        local_blacklist = await guild_settings.blacklist()
        local_whitelist = await guild_settings.whitelist()

        _ids = [r.id for r in author.roles if not r.is_default()]
        _ids.append(author.id)
        if local_whitelist:
            return any(i in local_whitelist for i in _ids)

        return not any(i in local_blacklist for i in _ids)

    async def global_perms(self, author):
        """Check the user is/isn't globally whitelisted/blacklisted.
            https://github.com/Cog-Creators/Red-DiscordBot/blob/V3/release/3.0.0/redbot/core/global_checks.py
        """
        if await self.bot.is_owner(author):
            return True

        whitelist = await self.bot.db.whitelist()
        if whitelist:
            return author.id in whitelist

        return author.id not in await self.bot.db.blacklist()

    async def check_ignored_channel(self, message):
        """
        https://github.com/Cog-Creators/Red-DiscordBot/blob/V3/release/3.0.0/redbot/cogs/mod/mod.py#L1273
        """
        channel = message.channel
        guild = channel.guild
        author = message.author
        mod = self.bot.get_cog("Mod")
        if mod is None:
            return True
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
