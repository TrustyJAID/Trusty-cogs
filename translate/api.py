import aiohttp
import discord
import logging
import asyncio
import time
import re

from typing import cast, Optional, List, Union, Mapping, Dict, Tuple
from copy import deepcopy

from redbot.core import Config, commands
from redbot.core.bot import Red
from redbot.core.i18n import Translator
from redbot.core.utils.common_filters import filter_mass_mentions
from discord.ext.commands.converter import Converter
from discord.ext.commands.errors import BadArgument

from .flags import FLAGS
from .errors import GoogleTranslateAPIError

BASE_URL = "https://translation.googleapis.com"
_ = Translator("Translate", __file__)
log = logging.getLogger("red.trusty-cogs.Translate")

FLAG_REGEX = re.compile(r"|".join(rf"{re.escape(f)}" for f in FLAGS.keys()))


class FlagTranslation(Converter):
    """
    This will convert flags and languages to the correct code to be used by the API

    Guidance code on how to do this from:
    https://github.com/Rapptz/discord.py/blob/rewrite/discord/ext/commands/converter.py#L85
    https://github.com/Cog-Creators/Red-DiscordBot/blob/V3/develop/redbot/cogs/mod/mod.py#L24

    """

    async def convert(self, ctx: commands.Context, argument: str) -> List[str]:
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
    _key: Optional[str]

    def __init__(self, *_args):
        self.config: Config
        self.bot: Red
        self.cache: dict
        self._key: Optional[str]

    async def cleanup_cache(self) -> None:
        await self.bot.wait_until_ready()
        while self is self.bot.get_cog("Translate"):
            # cleanup the cache every 10 minutes
            self.cache["translations"] = []
            await asyncio.sleep(600)

    async def _get_google_api_key(self) -> Optional[str]:
        key = {}
        if not self._key:
            try:
                key = await self.bot.get_shared_api_tokens("google_translate")
            except AttributeError:
                # Red 3.1 support
                key = await self.bot.db.api_tokens.get_raw("google_translate", default={})
            self._key = key.get("api_key")
        return self._key

    async def _bw_list_cache_update(self, guild: discord.Guild) -> None:
        self.cache["guild_blacklist"][guild.id] = await self.config.guild(guild).blacklist()
        self.cache["guild_whitelist"][guild.id] = await self.config.guild(guild).whitelist()

    async def check_bw_list(self, message: discord.Message, member: discord.Member) -> bool:
        can_run = True
        author: discord.Member = member
        guild = cast(discord.Guild, message.guild)
        if guild.id not in self.cache["guild_blacklist"]:
            self.cache["guild_blacklist"][guild.id] = await self.config.guild(guild).blacklist()
        if guild.id not in self.cache["guild_whitelist"]:
            self.cache["guild_whitelist"][guild.id] = await self.config.guild(guild).whitelist()
        whitelist = self.cache["guild_whitelist"][guild.id]
        blacklist = self.cache["guild_whitelist"][guild.id]
        if whitelist:
            can_run = False
            if message.channel.id in whitelist:
                can_run = True
            if author.id in whitelist:
                can_run = True
            for role in author.roles:
                if role.is_default():
                    continue
                if role.id in whitelist:
                    can_run = True
            return can_run
        else:
            if message.channel.id in blacklist:
                can_run = False
            if author.id in blacklist:
                can_run = False
            for role in author.roles:
                if role.is_default():
                    continue
                if role.id in blacklist:
                    can_run = False
        return can_run

    async def detect_language(self, text: str) -> List[List[Dict[str, str]]]:
        """
            Detect the language from given text
        """
        params = {"q": text, "key": self._key}
        url = BASE_URL + "/language/translate/v2/detect"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params) as resp:
                data = await resp.json()
        if "error" in data:
            log.error(data["error"]["message"])
            raise GoogleTranslateAPIError(data["error"]["message"])
        return data["data"]["detections"]

    async def translation_embed(
        self,
        author: Union[discord.Member, discord.User],
        translation: Tuple[str, str, str],
        requestor: Optional[Union[discord.Member, discord.User]] = None,
    ) -> discord.Embed:
        em = discord.Embed(colour=author.colour, description=translation[0])
        em.set_author(name=author.display_name + _(" said:"), icon_url=str(author.avatar_url))
        detail_string = _("{_from} to {_to} | Requested by ").format(
            _from=translation[1].upper(), _to=translation[2].upper()
        )
        if requestor:
            detail_string += str(requestor)
        else:
            detail_string += str(author)
        em.set_footer(text=detail_string)
        return em

    async def translate_text(self, from_lang: str, target: str, text: str) -> Optional[str]:
        """
            request to translate the text
        """
        formatting = "text"
        params = {
            "q": text,
            "target": target,
            "key": self._key,
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
            translated_text: str = data["data"]["translations"][0]["translatedText"]
        return translated_text

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """
            Translates the message based off reactions
            with country flags
        """
        if not self.bot.is_ready():
            return
        if not message.guild:
            return
        if message.author.bot:
            return
        if not await self._get_google_api_key():
            return
        author = cast(discord.Member, message.author)
        if not await self.check_bw_list(message, author):
            return
        guild = message.guild

        if not await self.config.guild(guild).text():
            return
        if guild.id not in self.cache["guild_messages"]:
            if not await self.config.guild(guild).text():
                return
            else:
                self.cache["guild_messages"].append(guild.id)
        if not await self.local_perms(guild, author):
            return
        if not await self.global_perms(author):
            return
        if not await self.check_ignored_channel(message):
            return
        flag = FLAG_REGEX.search(message.clean_content)
        if not flag:
            return
        await self.translate_message(message, flag.group())

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent) -> None:
        """
            Translates the message based off reactions
            with country flags
        """
        if not self.bot.is_ready():
            return
        if payload.message_id in self.cache["translations"]:
            return
        if not await self._get_google_api_key():
            return
        channel = self.bot.get_channel(id=payload.channel_id)
        if not channel:
            return
        try:
            if channel.recipient:
                return
        except AttributeError:
            pass
        guild = channel.guild
        reacted_user = guild.get_member(payload.user_id)
        try:
            message = await channel.fetch_message(id=payload.message_id)
        except AttributeError:
            message = await channel.get_message(id=payload.message_id)
        except (discord.errors.NotFound, discord.Forbidden):
            return
        if reacted_user.bot:
            return
        if not await self.check_bw_list(message, reacted_user):
            return

        if guild.id not in self.cache["guild_reactions"]:
            if not await self.config.guild(guild).reaction():
                return
            else:
                self.cache["guild_reactions"].append(guild.id)
        if str(payload.emoji) not in FLAGS:
            return
        if not await self.local_perms(guild, reacted_user):
            return
        if not await self.global_perms(reacted_user):
            return
        if not await self.check_ignored_channel(message):
            return
        await self.translate_message(message, str(payload.emoji), reacted_user)

    async def translate_message(
        self, message: discord.Message, flag: str, reacted_user: Optional[discord.Member] = None
    ) -> None:
        guild = cast(discord.Guild, message.guild)
        channel = cast(discord.TextChannel, message.channel)
        if message.id in self.cache["cooldown_translations"]:
            if str(flag) in self.cache["cooldown_translations"][message.id]["past_flags"]:
                return
            if not self.cache["cooldown_translations"][message.id]["multiple"]:
                return
            if time.time() < self.cache["cooldown_translations"][message.id]["wait"]:
                delete_after = (
                    self.cache["cooldown_translations"][message.id]["wait"] - time.time()
                )
                await channel.send(
                    _("You're translating too many messages!"), delete_after=delete_after
                )
                return
        if message.embeds != []:
            if message.embeds[0].description:
                to_translate = cast(str, message.embeds[0].description)
        else:
            to_translate = message.clean_content
        num_emojis = 0
        for reaction in message.reactions:
            if reaction.emoji == str(flag):
                num_emojis = reaction.count
        if num_emojis > 1:
            return
        target = FLAGS[str(flag)]["code"]
        try:
            detected_lang = await self.detect_language(to_translate)
        except GoogleTranslateAPIError:
            return
        original_lang = detected_lang[0][0]["language"]
        if target == original_lang:
            return
        try:
            translated_text = filter_mass_mentions(
                await self.translate_text(original_lang, target, to_translate)
            )
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

        if message.id not in self.cache["cooldown_translations"]:
            if not self.cache["cooldown"]:
                self.cache["cooldown"] = await self.config.cooldown()
            cooldown = deepcopy(self.cache["cooldown"])
        else:
            cooldown = self.cache["cooldown_translations"][message.id]
        cooldown["wait"] = time.time() + cooldown["timeout"]
        cooldown["past_flags"].append(str(flag))
        self.cache["cooldown_translations"][message.id] = cooldown

        if channel.permissions_for(guild.me).embed_links:
            em = await self.translation_embed(author, translation, reacted_user)
            translated_msg = await channel.send(embed=em)
        else:
            msg = _("{author} said:\n{translated_text}").format(
                author=author, translate_text=translated_text
            )
            translated_msg = await channel.send(msg)
        if not cooldown["multiple"]:
            self.cache["translations"].append(translated_msg.id)

    async def local_perms(self, guild: discord.Guild, author: discord.Member) -> bool:
        """Check the user is/isn't locally whitelisted/blacklisted.
            https://github.com/Cog-Creators/Red-DiscordBot/blob/V3/release/3.0.0/redbot/core/global_checks.py
        """
        if await self.bot.is_owner(author):
            return True
        elif guild is None:
            return True
        try:
            guild_settings = self.bot.db.guild(guild)
            local_blacklist = await guild_settings.blacklist()
            local_whitelist = await guild_settings.whitelist()

            _ids = [r.id for r in author.roles if not r.is_default()]
            _ids.append(author.id)
            if local_whitelist:
                return any(i in local_whitelist for i in _ids)

            return not any(i in local_blacklist for i in _ids)
        except AttributeError:
            return await self.bot.allowed_by_whitelist_blacklist(
                author, who_id=author.id, guild_id=guild.id, role_ids=[r.id for r in author.roles]
            )

    async def global_perms(self, author: discord.Member) -> bool:
        """Check the user is/isn't globally whitelisted/blacklisted.
            https://github.com/Cog-Creators/Red-DiscordBot/blob/V3/release/3.0.0/redbot/core/global_checks.py
        """
        if await self.bot.is_owner(author):
            return True
        try:
            whitelist = await self.bot.db.whitelist()
            if whitelist:
                return author.id in whitelist

            return author.id not in await self.bot.db.blacklist()
        except AttributeError:
            return await self.bot.allowed_by_whitelist_blacklist(author)

    async def check_ignored_channel(self, message: discord.Message) -> bool:
        """
        https://github.com/Cog-Creators/Red-DiscordBot/blob/V3/release/3.0.0/redbot/cogs/mod/mod.py#L1273
        """
        channel = cast(discord.TextChannel, message.channel)
        guild = channel.guild
        author = cast(discord.Member, message.author)
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
        if hasattr(mod, "settings"):
            guild_ignored = await mod.settings.guild(guild).ignored()
            chann_ignored = await mod.settings.channel(channel).ignored()
        else:
            guild_ignored = await mod.config.guild(guild).ignored()
            chann_ignored = await mod.config.channel(channel).ignored()
        return not (guild_ignored or chann_ignored and not perms.manage_channels)

    @commands.Cog.listener()
    async def on_red_api_tokens_update(
        self, service_name: str, api_tokens: Mapping[str, str]
    ) -> None:
        if service_name != "google_translate":
            return

        self._key = None
