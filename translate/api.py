from __future__ import annotations

import re
import time
from collections import OrderedDict
from copy import deepcopy
from dataclasses import dataclass
from typing import Dict, List, Mapping, Optional, Union, cast

import aiohttp
import discord
from discord.ext import tasks
from discord.ext.commands.errors import BadArgument
from red_commons.logging import getLogger
from redbot.core import Config, commands
from redbot.core.bot import Red
from redbot.core.i18n import Translator
from redbot.core.utils.views import SimpleMenu

from .errors import GoogleTranslateAPIError
from .flags import FLAGS

BASE_URL = "https://translation.googleapis.com"
_ = Translator("Translate", __file__)
log = getLogger("red.trusty-cogs.Translate")

FLAG_REGEX = re.compile(r"|".join(rf"{re.escape(f)}" for f in FLAGS.keys()))


class FlagTranslation(discord.app_commands.Transformer):
    """
    This will convert flags and languages to the correct code to be used by the API

    Guidance code on how to do this from:
    https://github.com/Rapptz/discord.py/blob/rewrite/discord/ext/commands/converter.py#L85
    https://github.com/Cog-Creators/Red-DiscordBot/blob/V3/develop/redbot/cogs/mod/mod.py#L24

    """

    @classmethod
    async def convert(cls, ctx: commands.Context, argument: str) -> str:
        result = ""
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

    @classmethod
    async def transform(cls, interaction: discord.Interaction, argument: str) -> str:
        ctx = await interaction.client.get_context(interaction)
        return await cls.convert(ctx, argument)

    async def autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> List[discord.app_commands.Choice]:
        options = [
            discord.app_commands.Choice(name=i["name"], value=i["code"])
            for i in FLAGS.values()
            if current.lower() in i["name"].lower() or current.lower() in i["code"].lower()
        ]
        return list(set(options))[:25]


@dataclass
class GoogleTranslateResponse:
    data: dict

    @classmethod
    def from_json(cls, data: dict) -> GoogleTranslateResponse:
        return cls(data=data["data"])


@dataclass
class DetectLanguageResponse(GoogleTranslateResponse):
    detections: List[DetectedLanguage]

    @classmethod
    def from_json(cls, data: dict) -> DetectLanguageResponse:
        return cls(
            data=data["data"],
            detections=[DetectedLanguage.from_json(i) for i in data["data"]["detections"]],
        )

    @property
    def language(self) -> Optional[DetectedLanguage]:
        conf = 0.0
        ret = None
        for lang in self.detections:
            if lang.confidence > conf:
                ret = lang
                conf = lang.confidence
        return ret


@dataclass
class TranslateTextResponse(GoogleTranslateResponse):
    translations: List[Translation]

    def __str__(self):
        return str(self.translations[0])

    @classmethod
    def from_json(cls, data: dict) -> TranslateTextResponse:
        return cls(
            data=data["data"],
            translations=[Translation.from_json(i) for i in data["data"]["translations"]],
        )

    def embeds(
        self,
        author: Union[discord.Member, discord.User],
        from_language: str,
        to_language: str,
        requestor: Optional[Union[discord.Member, discord.User]] = None,
    ):
        """Return a list of all translations"""
        return [
            self.embed(translation, author, from_language, to_language, requestor)
            for translation in self.translations
        ]

    def embed(
        self,
        translation: Translation,
        author: Union[discord.Member, discord.User],
        from_language: str,
        to_language: str,
        requestor: Optional[Union[discord.Member, discord.User]] = None,
    ) -> discord.Embed:
        em = discord.Embed(colour=author.colour, description=str(translation))
        em.set_author(name=author.display_name, icon_url=author.display_avatar)
        detail_string = _("{_from} to {_to} | Requested by ").format(
            _from=from_language.upper(), _to=to_language.upper()
        )
        if requestor:
            detail_string += str(requestor)
        else:
            detail_string += str(author)
        em.set_footer(text=detail_string)
        return em


@dataclass
class Translation:
    detected_source_language: Optional[str]
    model: Optional[str]
    translated_text: str

    def __str__(self):
        return self.translated_text

    @classmethod
    def from_json(cls, data: dict) -> Translation:
        return cls(
            detected_source_language=data.get("detectedSourceLanguage"),
            model=data.get("model"),
            translated_text=data["translatedText"],
        )

    @property
    def text(self) -> str:
        return self.translated_text


@dataclass
class DetectedLanguage:
    language: str
    isReliable: bool
    confidence: float

    def __str__(self):
        return self.language

    @classmethod
    def from_json(cls, data: List[dict]) -> DetectedLanguage:
        return cls(**data[0])


class FixedSizeOrderedDict(OrderedDict):
    # https://stackoverflow.com/a/49274421
    def __init__(self, *args, max_len=0, **kwargs):
        self._max_len = max_len
        super().__init__(*args, **kwargs)

    def __setitem__(self, key, value):
        super().__setitem__(key, value)
        if self._max_len > 0:
            if len(self) > self._max_len:
                self.popitem(False)


class GoogleTranslator:
    def __init__(
        self,
        api_token: Optional[str],
        session: Optional[aiohttp.ClientSession] = None,
        *,
        stats_counter: StatsCounter,
    ):
        self._api_token = api_token
        self.session = session or aiohttp.ClientSession(
            headers={"User-Agent": "Trusty-cogs Translate cog for Red-DiscordBot"}
        )
        self.stats_counter = stats_counter
        self._cache_limit = 128
        self._translation_cache = FixedSizeOrderedDict(max_len=self._cache_limit)
        self._detection_cache = FixedSizeOrderedDict(max_len=self._cache_limit)

    @property
    def has_token(self):
        return self._api_token is not None

    async def close(self):
        await self.stats_counter.save()
        await self.session.close()

    async def detect_language(
        self,
        text: str,
        *,
        guild: Optional[discord.Guild] = None,
    ) -> Optional[DetectedLanguage]:
        """
        Detect the language from given text
        """
        if self._api_token is None:
            raise GoogleTranslateAPIError("The API token is missing.")
        # Hash the text for a relatively unique key
        # I am not concerned about collisions here just memory
        # a user message can be up to 4000 characters long which would be 4049 bytes
        # a hash is only 36 bytes and since we're caching the result which is much larger
        # there's no reason to cache the original text just a hash of it
        cache_key = hash(text)
        if cache_key in self._detection_cache:
            return self._detection_cache[cache_key]
        params = {"q": text, "key": self._api_token}
        url = BASE_URL + "/language/translate/v2/detect"
        async with self.session.get(url, params=params) as resp:
            data = await resp.json()
        if "error" in data:
            log.error(data["error"]["message"])
            raise GoogleTranslateAPIError(data["error"]["message"])
        detection = DetectLanguageResponse.from_json(data)
        await self.stats_counter.add_detect(guild)
        self._detection_cache[cache_key] = detection.language
        return detection.language

    async def translate_text(
        self,
        target: str,
        text: str,
        from_lang: Optional[str] = None,
        *,
        guild: Optional[discord.Guild] = None,
    ) -> Optional[TranslateTextResponse]:
        """
        request to translate the text
        """
        if self._api_token is None:
            raise GoogleTranslateAPIError("The API token is missing.")
        # Hash the text for a relatively unique key
        # I am not concerned about collisions here just memory
        # a user message can be up to 4000 characters long which would be 4049 bytes
        # a hash is only 36 bytes and since we're caching the result which is much larger
        # there's no reason to cache the original text just a hash of it
        cache_key = (target, hash(text), from_lang)
        if cache_key in self._translation_cache:
            return self._translation_cache[cache_key]
        formatting = "text"
        params = {
            "q": text,
            "target": target,
            "key": self._api_token,
            "format": formatting,
        }
        if from_lang is not None:
            params["source"] = from_lang
        url = BASE_URL + "/language/translate/v2"
        try:
            async with self.session.get(url, params=params) as resp:
                data = await resp.json()
        except Exception:
            return None
        if "error" in data:
            log.error(data["error"]["message"])
            raise GoogleTranslateAPIError(data["error"]["message"])
        translation = TranslateTextResponse.from_json(data)
        await self.stats_counter.add_requests(guild, text)
        self._translation_cache[cache_key] = translation
        return translation


class StatsCounter:
    def __init__(self, config: Config):
        self.config = config
        self._guild_counter: Dict[int, Dict[str, int]] = {}
        self._global_counter: Dict[str, int] = {}

    async def text(self, guild: Optional[discord.Guild] = None) -> str:
        tr_keys = {
            "requests": _("API Requests:"),
            "detect": _("API Detect Language:"),
            "characters": _("Characters requested:"),
        }
        gl_count = self._global_counter if self._global_counter else await self.config.count()
        msg = _("### __Global Usage__:\n")
        for key, value in gl_count.items():
            msg += tr_keys[key] + f" **{value}**\n"
        if guild is not None:
            count = (
                self._guild_counter[guild.id]
                if guild.id in self._guild_counter
                else await self.config.guild(guild).count()
            )
            msg += _("### __{guild} Usage__:\n").format(guild=guild.name)
            for key, value in count.items():
                msg += tr_keys[key] + f" **{value}**\n"
        return msg

    async def initialize(self):
        self._global_counter = await self.config.count()
        all_guilds = await self.config.all_guilds()
        for g_id, data in all_guilds.items():
            self._guild_counter[g_id] = data["count"]

    async def save(self):
        async with self.config.count() as count:
            for key, value in self._global_counter.items():
                count[key] = value
        for guild_id, data in self._guild_counter.items():
            async with self.config.guild_from_id(int(guild_id)).count() as count:
                for key, value in data.items():
                    count[key] = value

    async def add_detect(self, guild: Optional[discord.Guild]):
        if guild:
            log.debug("adding detect to %s", guild.name)
            if guild.id not in self._guild_counter:
                self._guild_counter[guild.id] = await self.config.guild(guild).count()
            self._guild_counter[guild.id]["detect"] += 1
        if not self._global_counter:
            self._global_counter = await self.config.count()
        self._global_counter["detect"] += 1

    async def add_requests(self, guild: Optional[discord.Guild], message: str):
        if guild:
            log.debug("Adding requests to %s", guild.name)
            if guild.id not in self._guild_counter:
                self._guild_counter[guild.id] = await self.config.guild(guild).count()
            self._guild_counter[guild.id]["requests"] += 1
            self._guild_counter[guild.id]["characters"] += len(message)
        if not self._global_counter:
            self._global_counter = await self.config.count()
        self._global_counter["requests"] += 1
        self._global_counter["characters"] += len(message)


class GoogleTranslateAPI:
    config: Config
    bot: Red
    cache: dict
    _key: Optional[str]
    _tr: GoogleTranslator

    async def translate_from_message(
        self, interaction: discord.Interaction, message: discord.Message
    ):
        if not self._tr.has_token:
            await interaction.response.send_message(
                _("The bot owner needs to set an api key first!"), ephemeral=True
            )
            return
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        to_translate = None
        if message.embeds != []:
            if message.embeds[0].description:
                to_translate = cast(str, message.embeds[0].description)
        else:
            to_translate = message.clean_content

        if not to_translate:
            return
        target = str(interaction.locale).split("-")[0]
        try:
            detected_lang = await self._tr.detect_language(to_translate, guild=interaction.guild)
        except GoogleTranslateAPIError:
            return
        except Exception:
            log.exception("Error detecting language")
            return
        if detected_lang is None:
            return
        author = message.author
        from_lang = detected_lang.language
        to_lang = target
        if from_lang == to_lang:
            # don't post anything if the detected language is the same
            await interaction.followup.send(
                _("The detected language is the same as the language being translated to.")
            )
            return
        try:
            translated_text = await self._tr.translate_text(
                target, to_translate, str(from_lang), guild=interaction.guild
            )
        except Exception:
            log.exception(f"Error translating message {guild=} {interaction.channel=}")
            return
        if not translated_text:
            return
        # translation = (translated_text, from_lang, to_lang)
        ems = translated_text.embeds(author, from_lang, to_lang, interaction.user)
        ctx = await interaction.client.get_context(interaction)
        await SimpleMenu(ems).start(ctx)
        # await interaction.followup.send(embed=em, ephemeral=True)

    @tasks.loop(seconds=120)
    async def translation_loop(self):
        self.cache["translations"] = []
        await self._tr.stats_counter.save()

    async def check_bw_list(
        self,
        guild: discord.Guild,
        channel: discord.TextChannel,
        member: Union[discord.Member, discord.User],
    ) -> bool:
        can_run = True
        if guild.id not in self.cache["guild_blacklist"]:
            self.cache["guild_blacklist"][guild.id] = await self.config.guild(guild).blacklist()
        if guild.id not in self.cache["guild_whitelist"]:
            self.cache["guild_whitelist"][guild.id] = await self.config.guild(guild).whitelist()
        whitelist = self.cache["guild_whitelist"][guild.id]
        blacklist = self.cache["guild_blacklist"][guild.id]
        if whitelist:
            can_run = False
            if channel.id in whitelist:
                can_run = True
            if channel.category_id and channel.category_id in whitelist:
                can_run = True
            if member.id in whitelist:
                can_run = True
            for role in getattr(member, "roles", []):
                if role.is_default():
                    continue
                if role.id in whitelist:
                    can_run = True
            return can_run
        else:
            if channel.id in blacklist:
                can_run = False
            if channel.category_id and channel.category_id in blacklist:
                can_run = False
            if member.id in blacklist:
                can_run = False
            for role in getattr(member, "roles", []):
                if role.is_default():
                    continue
                if role.id in blacklist:
                    can_run = False
        return can_run

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """
        Translates the message based off reactions
        with country flags
        """
        guild = message.guild
        channel = message.channel
        author = message.author
        if guild is None:
            return
        if not guild or author.bot or self._tr is None:
            return
        if await self.bot.cog_disabled_in_guild(self, guild):
            return
        if guild.get_member(message.author.id):
            if not await self.bot.message_eligible_as_command(message):
                return
        if not await self.check_bw_list(guild, channel, author):
            return
        flag_search = FLAG_REGEX.search(message.clean_content)
        if not flag_search:
            return
        flag = flag_search.group(0)
        if not await self.config.guild(guild).text():
            return
        if guild.id not in self.cache["guild_messages"]:
            self.cache["guild_messages"].append(guild.id)
        if not await self._check_cooldown(message.id, FLAGS[str(flag)]["code"]):
            return
        if message.id not in self.cache["cooldown_translations"]:
            if not self.cache["cooldown"]:
                self.cache["cooldown"] = await self.config.cooldown()
            cooldown = deepcopy(self.cache["cooldown"])
        else:
            cooldown = self.cache["cooldown_translations"][message.id]
        cooldown["wait"] = time.time() + cooldown["timeout"]
        cooldown["past_flags"].append(str(flag))
        self.cache["cooldown_translations"][message.id] = cooldown

        msgs = await self.translate_message(message, to_lang=None, flag=str(flag))
        if not msgs:
            return
        ctx = await self.bot.get_context(message)
        if not await ctx.embed_requested():
            msgs = [f"{author}:\n{translated_text.description}" for translated_text in msgs]
        await SimpleMenu(msgs).start(ctx)
        if not cooldown["multiple"]:
            self.cache["translations"].append(message.id)

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent) -> None:
        """
        Translates the message based off reactions
        with country flags
        """
        if payload.message_id in self.cache["translations"]:
            return
        if str(payload.emoji) not in FLAGS:
            log.debug("Emoji is not in the flags")
            return
        if not self._tr.has_token:
            log.debug("Bot owner token has not been set")
            return
        if payload.guild_id is None:
            log.debug("We don't support reaction translations in dms")
            return
        guild = self.bot.get_guild(payload.guild_id)
        if guild is None:
            log.debug("The guild cannot be found")
            return
        channel = guild.get_channel(payload.channel_id)
        if channel is None:
            log.debug("The channel cannot be found")
            return
        if await self.bot.cog_disabled_in_guild(self, guild):
            log.debug("The cog is disabled in this guild")
            return
        reacted_user = payload.member or guild.get_member(payload.user_id)
        if reacted_user is None or reacted_user.bot:
            log.debug("The User reacting cannot be found or is a bot user")
            return
        if not await self.check_bw_list(guild, channel, reacted_user):
            log.debug("The User reacting  did so in a blocked channel or is blocked themselves")
            return
        if not await self._check_cooldown(payload.message_id, FLAGS[str(payload.emoji)]["code"]):
            log.debug("This message has hit the cooldown checks")
            return

        if guild.id not in self.cache["guild_reactions"]:
            if not await self.config.guild(guild).reaction():
                log.debug("This server has not opted for reaction translations")
                return
            else:
                self.cache["guild_reactions"].append(guild.id)
        try:
            message = await channel.fetch_message(payload.message_id)
        except (discord.errors.NotFound, discord.Forbidden):
            log.debug("The message could not be found")
            return
        message_author = guild.get_member(message.author.id)
        if message_author and not message_author.bot:
            if not await self.bot.message_eligible_as_command(message):
                log.debug("The message is not eligable as a command")
                return

        if message.id not in self.cache["cooldown_translations"]:
            if not self.cache["cooldown"]:
                self.cache["cooldown"] = await self.config.cooldown()
            cooldown = deepcopy(self.cache["cooldown"])
        else:
            cooldown = self.cache["cooldown_translations"][message.id]
        cooldown["wait"] = time.time() + cooldown["timeout"]
        cooldown["past_flags"].append(str(payload.emoji))
        self.cache["cooldown_translations"][message.id] = cooldown

        msgs = await self.translate_message(
            message, to_lang=None, flag=str(payload.emoji), reacted_user=reacted_user
        )
        if msgs is None:
            log.debug("The translation failed")
            return
        channel = message.channel
        author = message.author
        ctx = await self.bot.get_context(message)
        if not await ctx.embed_requested():
            msgs = [f"{author}:\n{translated_text.description}" for translated_text in msgs]
        await SimpleMenu(msgs).start(ctx)
        if not cooldown["multiple"]:
            self.cache["translations"].append(message.id)

    async def _check_cooldown(self, message: Union[discord.Message, int], lang: str) -> bool:
        if isinstance(message, int):
            message_id = message
        else:
            message_id = message.id

        if message_id in self.cache["cooldown_translations"]:
            if str(lang) in self.cache["cooldown_translations"][message_id]["past_flags"]:
                return False
            if not self.cache["cooldown_translations"][message_id]["multiple"]:
                return False
            if time.time() < self.cache["cooldown_translations"][message_id]["wait"]:
                return False
        return True

    async def translate_message(
        self,
        message: discord.Message,
        to_lang: Optional[str] = None,
        flag: Optional[str] = None,
        reacted_user: Optional[discord.Member] = None,
    ) -> List[discord.Embed]:
        to_translate = None
        if message.embeds != []:
            if message.embeds[0].description:
                to_translate = cast(str, message.embeds[0].description)
        else:
            to_translate = message.clean_content

        if not to_translate:
            return []
        if flag is not None:
            num_emojis = 0
            for reaction in message.reactions:
                if reaction.emoji == str(flag):
                    num_emojis = reaction.count
            if num_emojis > 1:
                return []
            to_lang = FLAGS[str(flag)]["code"]
        try:
            detected_lang = await self._tr.detect_language(to_translate, guild=message.guild)
        except GoogleTranslateAPIError:
            return []
        except Exception:
            log.exception("Error detecting language")
            return []
        original_lang = str(detected_lang)
        if original_lang is None:
            return []
        author = message.author
        from_lang = str(detected_lang)
        if from_lang == to_lang:
            # don't post anything if the detected language is the same
            return []
        try:
            translated_text = await self._tr.translate_text(
                to_lang, to_translate, original_lang, guild=message.guild
            )
        except Exception:
            log.exception(f"Error translating message {message.guild=} {message.channel=}")
            return []
        if not translated_text:
            return []
        return translated_text.embeds(author, from_lang, to_lang, reacted_user)

    @commands.Cog.listener()
    async def on_red_api_tokens_update(
        self, service_name: str, api_tokens: Mapping[str, str]
    ) -> None:
        if service_name != "google_translate":
            return
        if "api_key" not in api_tokens:
            return
        if self._tr is None:
            self._tr = GoogleTranslator(api_tokens["api_key"])
        self._tr._api_token = api_tokens["api_key"]
