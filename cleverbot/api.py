import re
from typing import Optional, Tuple, Union

import aiohttp
import discord
from charset_normalizer import detect
from discord.ext.commands.converter import Converter, IDConverter
from discord.ext.commands.errors import BadArgument
from red_commons.logging import getLogger
from redbot import VersionInfo, version_info
from redbot.core import Config, commands
from redbot.core.bot import Red
from redbot.core.i18n import Translator

from .errors import APIError, InvalidCredentials, NoCredentials, OutOfRequests

API_URL = "https://www.cleverbot.com/getreply"
IO_API_URL = "https://cleverbot.io/1.0"

log = getLogger("red.trusty-cogs.Cleverbot")

_ = Translator("cleverbot", __file__)


class ChannelUserRole(IDConverter):
    """
    This will check to see if the provided argument is a channel, user, or role

    Guidance code on how to do this from:
    https://github.com/Rapptz/discord.py/blob/rewrite/discord/ext/commands/converter.py#L85
    https://github.com/Cog-Creators/Red-DiscordBot/blob/V3/develop/redbot/cogs/mod/mod.py#L24
    """

    async def convert(
        self, ctx: commands.Context, argument: str
    ) -> Union[discord.TextChannel, discord.Member, discord.Role]:
        guild = ctx.guild
        result = None
        id_match = self._get_id_match(argument)
        channel_match = re.match(r"<#([0-9]+)>$", argument)
        member_match = re.match(r"<@!?([0-9]+)>$", argument)
        role_match = re.match(r"<@&([0-9]+)>$", argument)
        for converter in ["channel", "role", "member"]:
            if converter == "channel":
                match = id_match or channel_match
                if match:
                    channel_id = match.group(1)
                    result = guild.get_channel(int(channel_id))
                else:
                    result = discord.utils.get(guild.text_channels, name=argument)
            if converter == "member":
                match = id_match or member_match
                if match:
                    member_id = match.group(1)
                    result = guild.get_member(int(member_id))
                else:
                    result = guild.get_member_named(argument)
            if converter == "role":
                match = id_match or role_match
                if match:
                    role_id = match.group(1)
                    result = guild.get_role(int(role_id))
                else:
                    result = discord.utils.get(guild._roles.values(), name=argument)
            if result:
                break
        if not result:
            msg = ("{arg} is not a valid channel, user or role.").format(arg=argument)
            raise BadArgument(msg)
        return result


class IntRange(Converter):
    async def convert(self, ctx, argument) -> int:
        try:
            argument = int(argument)
        except ValueError:
            raise BadArgument("The provided input must be a number.")
        if argument == -1:
            return argument
        if argument < -1:
            raise BadArgument("You must provide a number greater than -1.")
        return max(min(100, argument), 0)


class CleverbotAPI:
    """
    All API access for both cleverbot and cleverbot.io
    """

    bot: Red
    config: Config
    instances: dict

    async def send_cleverbot_response(
        self, message: str, author: Union[discord.Member, discord.User], ctx: commands.Context
    ) -> None:
        """
        This is called when we actually want to send a reply
        """
        await ctx.typing()
        try:
            response = await self.get_response(author, message)
        except NoCredentials:
            msg = _(
                "The owner needs to set the credentials first.\n" "See: [p]cleverbotset apikey"
            )
            await ctx.send(msg)
        except APIError as e:
            await ctx.send("Error contacting the API. Error code: {}".format(e))
        except InvalidCredentials:
            msg = _("The token that has been set is not valid.\n" "See: [p]cleverbotset")
            await ctx.send(msg)
        except OutOfRequests:
            msg = _(
                "You have ran out of requests for this month. "
                "The free tier has a 5000 requests a month limit."
            )
            await ctx.send(msg)
        else:
            replies = version_info >= VersionInfo.from_str("3.4.6")
            if ctx.guild:
                replies = replies or await self.config.guild(ctx.guild).reply()
                if await self.config.guild(ctx.guild).mention():
                    if replies:
                        await ctx.send(response, reference=ctx.message, mention_author=True)
                    else:
                        await ctx.send(f"{author.mention} {response}")
                else:
                    if replies:
                        await ctx.send(response, reference=ctx.message, mention_author=False)
                    else:
                        await ctx.send(response)
            else:
                if replies:
                    await ctx.send(response, reference=ctx.message, mention_author=False)
                else:
                    await ctx.send(response)

    async def local_perms(self, message: discord.Message) -> bool:
        """Check the user is/isn't locally whitelisted/blacklisted.
        https://github.com/Cog-Creators/Red-DiscordBot/blob/V3/release/3.0.0/redbot/core/global_checks.py
        """
        if await self.bot.is_owner(message.author):
            return True
        elif message.guild is None:
            return True
        if not getattr(message.author, "roles", None):
            return False
        try:
            return await self.bot.allowed_by_whitelist_blacklist(
                message.author,
                who_id=message.author.id,
                guild=message.guild,
                role_ids=[r.id for r in message.author.roles],
            )
        except AttributeError:
            guild_settings = self.bot.db.guild(message.guild)
            local_blacklist = await guild_settings.blacklist()
            local_whitelist = await guild_settings.whitelist()
            author: discord.Member = message.author
            _ids = [r.id for r in author.roles if not r.is_default()]
            _ids.append(message.author.id)
            if local_whitelist:
                return any(i in local_whitelist for i in _ids)

            return not any(i in local_blacklist for i in _ids)

    async def build_tweak_msg(self, guild: Optional[discord.Guild] = None) -> str:
        if guild:
            g_tweak1 = await self.config.guild(guild).tweak1()
            g_tweak2 = await self.config.guild(guild).tweak2()
            g_tweak3 = await self.config.guild(guild).tweak3()
        else:
            g_tweak1, g_tweak2, g_tweak3 = -1, -1, -1
        tweak1 = await self.config.tweak1() if g_tweak1 == -1 else g_tweak1
        tweak2 = await self.config.tweak2() if g_tweak2 == -1 else g_tweak2
        tweak3 = await self.config.tweak3() if g_tweak3 == -1 else g_tweak3
        msg = "Alright, I will be "
        if tweak1 < 0:
            msg += f"{100}% sensible, "
        if tweak1 >= 0 and tweak1 < 50:
            msg += f"{100-tweak1}% sensible, "
        if tweak1 > 50:
            msg += f"{tweak1}% wacky, "
        if tweak1 == 50:
            msg += f"{tweak1}% wacky and sensible, "

        if tweak2 < 0:
            msg += f"{100}% shy, and "
        if tweak2 >= 0 and tweak2 < 50:
            msg += f"{100-tweak2}% shy, and "
        if tweak2 > 50:
            msg += f"{tweak2}% talkative, and "
        if tweak2 == 50:
            msg += f"{tweak2}% shy and talkative, and "

        if tweak3 < 0:
            msg += f"{100}% self-centered "
        if tweak3 >= 0 and tweak3 < 50:
            msg += f"{100-tweak3}% self-centered "
        if tweak3 > 50:
            msg += f"{tweak3}% attentive "
        if tweak3 == 50:
            msg += f"{tweak3}% self-centered and attentive "
        return msg

    async def global_perms(self, message: discord.Message) -> bool:
        """Check the user is/isn't globally whitelisted/blacklisted.
        https://github.com/Cog-Creators/Red-DiscordBot/blob/V3/release/3.0.0/redbot/core/global_checks.py
        """
        if version_info >= VersionInfo.from_str("3.3.6"):
            if not await self.bot.ignored_channel_or_guild(message):
                return False
        if await self.bot.is_owner(message.author):
            return True
        try:
            return await self.bot.allowed_by_whitelist_blacklist(message.author)
        except AttributeError:
            whitelist = await self.bot.db.whitelist()
            if whitelist:
                return message.author.id in whitelist

            return message.author.id not in await self.bot.db.blacklist()

    async def check_bw_list(self, message: discord.Message) -> bool:
        can_run = True
        if not message.guild:
            return can_run
        global_perms = await self.global_perms(message)
        if not global_perms:
            return global_perms
        whitelist = await self.config.guild(message.guild).whitelist()
        blacklist = await self.config.guild(message.guild).blacklist()
        channel = message.channel
        if whitelist:
            can_run = False
            if channel.id in whitelist:
                can_run = True
            if channel.category_id and channel.category_id in whitelist:
                can_run = True
            if message.author.id in whitelist:
                can_run = True
            for role in getattr(message.author, "roles", []):
                if role.is_default():
                    continue
                if role.id in whitelist:
                    can_run = True
            return can_run
        else:
            if channel.id in blacklist:
                can_run = False
            if channel.category_id and channel.category_id in whitelist:
                can_run = False
            if message.author.id in blacklist:
                can_run = False
            for role in getattr(message.author, "roles", []):
                if role.is_default():
                    continue
                if role.id in blacklist:
                    can_run = False
        return can_run

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        guild = message.guild
        if message.author.bot:
            return
        if not await self.check_bw_list(message):
            return
        if version_info >= VersionInfo.from_str("3.4.0"):
            if guild and await self.bot.cog_disabled_in_guild(self, guild):
                return
        ctx = await self.bot.get_context(message)
        author = message.author
        text = message.clean_content
        to_strip = f"(?m)^(<@!?{self.bot.user.id}>)"
        is_mention = re.search(to_strip, message.content)
        is_reply = False
        reply = getattr(message, "reference", None)
        if reply and (reference := getattr(reply, "resolved")) is not None:
            author = getattr(reference, "author")
            if author is not None:
                is_reply = reference.author.id == self.bot.user.id and ctx.me in message.mentions
        if is_mention:
            text = text[len(ctx.me.display_name) + 2 :]
            log.trace("CleverbotAPI text: %s", text)
        if not text:
            log.debug("No text to send to cleverbot.")
            return
        if guild is None:
            if await self.config.allow_dm() and message.author.id != self.bot.user.id:
                if ctx.prefix:
                    return
                await self.send_cleverbot_response(text, message.author, ctx)
            return

        if message.author.id != self.bot.user.id:
            auto_channel = await self.config.guild(guild).channel()
            if (not is_mention and not is_reply) and message.channel.id != auto_channel:
                log.debug("Not a mention or reply and not auto channel")
                return
            if not await self.config.guild(guild).toggle():
                return
            await self.send_cleverbot_response(text, author, ctx)

    async def get_response(self, author: Union[discord.Member, discord.User], text: str) -> str:
        payload = {}
        try:
            payload["key"] = await self.get_credentials()
            payload["cs"] = self.instances.get(str(author.id), "")
            payload["input"] = text
            payload.update(await self.get_tweaks(author))
            return await self.get_cleverbotcom_response(payload, author)
        except NoCredentials:
            payload["user"], payload["key"] = await self.get_io_credentials()
            payload["nick"] = str("{}".format(self.bot.user))
            return await self.get_cleverbotio_response(payload, text)

    async def get_tweaks(self, author: Union[discord.Member, discord.User]):
        ret = {}
        ret["cb_settings_tweak1"] = str(await self.config.tweak1())
        ret["cb_settings_tweak2"] = str(await self.config.tweak2())
        ret["cb_settings_tweak3"] = str(await self.config.tweak3())
        if isinstance(author, discord.Member):
            tweak1 = str(await self.config.guild(author.guild).tweak1())
            tweak2 = str(await self.config.guild(author.guild).tweak2())
            tweak3 = str(await self.config.guild(author.guild).tweak3())

            if ret["cb_settings_tweak1"] != tweak1 and tweak1 != "-1":
                ret["cb_settings_tweak1"] = tweak1
            if ret["cb_settings_tweak2"] != tweak2 and tweak2 != "-1":
                ret["cb_settings_tweak2"] = tweak2
            if ret["cb_settings_tweak3"] != tweak3 and tweak3 != "-1":
                ret["cb_settings_tweak3"] = tweak3
        return ret

    async def make_cleverbotio_instance(self, payload: dict) -> None:
        """Makes the cleverbot.io instance if one isn't created for the user"""
        del payload["text"]
        async with aiohttp.ClientSession() as session:
            async with session.post(IO_API_URL + "/create", json=payload) as r:
                if r.status == 200:
                    return
                elif r.status == 400:
                    try:
                        error_msg = await r.json()
                    except Exception:
                        error_msg = "Error status 400, credentials seem to be invalid"
                        pass
                    log.error(error_msg)
                    raise InvalidCredentials()
                else:
                    error_msg = "Error making instance: " + str(r.status)
                    log.error(error_msg)
                    raise APIError(error_msg)

    async def get_cleverbotio_response(self, payload: dict, text: str) -> str:
        payload["text"] = text
        async with aiohttp.ClientSession() as session:
            async with session.post(IO_API_URL + "/ask/", json=payload) as r:
                if r.status == 200:
                    data = await r.json()
                elif r.status == 400:
                    # Try to make the instance for the user first before raising the error
                    await self.make_cleverbotio_instance(payload)
                    return await self.get_cleverbotio_response(payload, text)
                else:
                    error_msg = "Error getting response: " + str(r.status)
                    log.error(error_msg)
                    raise APIError(error_msg)
        return data["response"]

    async def get_cleverbotcom_response(
        self, payload: dict, author: Union[discord.Member, discord.User]
    ) -> str:
        async with aiohttp.ClientSession() as session:
            async with session.get(API_URL, params=payload) as r:
                # print(r.status)
                if r.status == 200:
                    try:
                        msg = await r.read()
                        detected = detect(msg)
                        encoding: str = detected["encoding"]
                        data = await r.json(encoding=encoding)
                    except Exception:
                        raise APIError("Error decoding cleverbot respose.")
                    self.instances[str(author.id)] = data["cs"]  # Preserves conversation status
                elif r.status == 401:
                    log.error("Cleverbot.com Invalid Credentials")
                    raise InvalidCredentials()
                elif r.status == 503:
                    log.error("Cleverbot.com Out of Requests")
                    raise OutOfRequests()
                else:
                    error_msg = "Cleverbot.com API Error " + str(r.status)
                    log.error(error_msg)
                    raise APIError(error_msg)
        return data["output"]

    async def get_credentials(self) -> str:
        key = await self.config.api()
        if key is None:
            raise NoCredentials()
        else:
            return key

    async def get_io_credentials(self) -> Tuple[str, str]:
        io_key = await self.config.io_key()
        io_user = await self.config.io_user()
        if io_key is None:
            raise NoCredentials()
        else:
            return io_user, io_key
