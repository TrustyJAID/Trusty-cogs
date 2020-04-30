import logging

from typing import Optional

from redbot.core import commands, Config, checks
from redbot.core.i18n import Translator, cog_i18n
from redbot.core.utils.chat_formatting import humanize_list

from discord.ext.commands.errors import BadArgument

from .api import GoogleTranslateAPI, FlagTranslation
from .errors import GoogleTranslateAPIError
from .converters import ChannelUserRole

"""
Translator cog

Cog credit to aziz#5919 for the idea and

Links

Wiki                                                https://goo.gl/3fxjSA
GitHub                                              https://goo.gl/oQAQde
Support the developer                               https://goo.gl/Brchj4
Invite the bot to your guild                       https://goo.gl/aQm2G7
Join the official development guild                https://discord.gg/uekTNPj
"""

BASE_URL = "https://translation.googleapis.com"
_ = Translator("Translate", __file__)
log = logging.getLogger("red.trusty-cogs.Translate")


@cog_i18n(_)
class Translate(GoogleTranslateAPI, commands.Cog):
    """
        Translate messages using Google Translate
    """

    __author__ = ["Aziz", "TrustyJAID"]
    __version__ = "2.2.1"

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, 156434873547, force_registration=True)
        default_guild = {"reaction": False, "text": False, "whitelist": [], "blacklist": []}
        default = {
            "cooldown": {"past_flags": [], "timeout": 0, "multiple": False},
        }
        self.config.register_guild(**default_guild)
        self.config.register_global(**default)
        self.cache = {
            "translations": [],
            "cooldown_translations": {},
            "guild_messages": [],
            "guild_reactions": [],
            "cooldown": {},
            "guild_blacklist": {},
            "guild_whitelist": {}

        }
        self._key: Optional[str] = None
        self.clear_cache = self.bot.loop.create_task(self.cleanup_cache())

    def format_help_for_context(self, ctx: commands.Context) -> str:
        """
            Thanks Sinbad!
        """
        pre_processed = super().format_help_for_context(ctx)
        return f"{pre_processed}\n\nCog Version: {self.__version__}"

    async def init(self) -> None:
        try:
            key = await self.config.api_key()
        except AttributeError:
            return
        try:
            central_key = await self.bot.get_shared_api_tokens("google_translate")
        except AttributeError:
            # Red 3.1 support
            central_key = await self.bot.db.api_tokens.get_raw("google_translate", default={})
        if not central_key:
            try:
                await self.bot.set_shared_api_tokens("google_translate", api_key=key)
            except AttributeError:
                await self.bot.db.api_tokens.set_raw(
                    "google_translate", value={"api_key": key}
                )
        await self.config.api_key.clear()

    @commands.command()
    async def translate(
        self, ctx: commands.Context, to_language: FlagTranslation, *, message: str
    ) -> None:
        """
            Translate messages with Google Translate

            `to_language` is the language you would like to translate
            `message` is the message to translate
        """
        if not await self._get_google_api_key():
            msg = _("The bot owner needs to set an api key first!")
            await ctx.send(msg)
            return
        try:
            detected_lang = await self.detect_language(message)
        except GoogleTranslateAPIError as e:
            await ctx.send(str(e))
            return
        from_lang = detected_lang[0][0]["language"]
        original_lang = detected_lang[0][0]["language"]
        if to_language == original_lang:
            return await ctx.send(
                _("I cannot translate `{from_lang}` to `{to}`").format(
                    from_lang=from_lang, to=to_language
                )
            )
        try:
            translated_text = await self.translate_text(original_lang, to_language, message)
        except GoogleTranslateAPIError as e:
            await ctx.send(str(e))
            return
        author = ctx.message.author
        if ctx.channel.permissions_for(ctx.me).embed_links:
            translation = (translated_text, from_lang, to_language)
            em = await self.translation_embed(author, translation)
            await ctx.send(embed=em)
        else:
            await ctx.send(translated_text)

    @commands.group()
    @checks.mod_or_permissions(manage_channels=True)
    async def translateset(self, ctx: commands.Context) -> None:
        """
            Toggle the bot auto translating
        """
        pass

    @translateset.group()
    @checks.mod_or_permissions(manage_messages=True)
    async def blacklist(self, ctx: commands.Context) -> None:
        """
            Set blacklist options for translations

            blacklisting supports channels, users, or roles
        """
        pass

    @translateset.group()
    @checks.mod_or_permissions(manage_messages=True)
    async def whitelist(self, ctx: commands.Context) -> None:
        """
            Set whitelist options for translations

            whitelisting supports channels, users, or roles
        """
        pass

    @whitelist.command(name="add")
    @checks.mod_or_permissions(manage_messages=True)
    async def whitelist_add(
        self, ctx: commands.Context, *channel_user_role: ChannelUserRole
    ) -> None:
        """
            Add a channel, user, or role to translation whitelist
        """
        if len(channel_user_role) < 1:
            return await ctx.send(
                _("You must supply 1 or more channels users or roles to be whitelisted.")
            )
        for obj in channel_user_role:
            if obj.id not in await self.config.guild(ctx.guild).whitelist():
                async with self.config.guild(ctx.guild).whitelist() as whitelist:
                    whitelist.append(obj.id)
                await self._bw_list_cache_update(ctx.guild)
        msg = _("`{list_type}` added to translation whitelist.")
        list_type = humanize_list([c.name for c in channel_user_role])
        await ctx.send(msg.format(list_type=list_type))

    @whitelist.command(name="remove", aliases=["rem", "del"])
    @checks.mod_or_permissions(manage_messages=True)
    async def whitelist_remove(
        self, ctx: commands.Context, *channel_user_role: ChannelUserRole
    ) -> None:
        """
            Remove a channel, user, or role from translation whitelist
        """
        if len(channel_user_role) < 1:
            return await ctx.send(
                _(
                    "You must supply 1 or more channels, users, "
                    "or roles to be removed from the whitelist"
                )
            )
        for obj in channel_user_role:
            if obj.id in await self.config.guild(ctx.guild).whitelist():
                async with self.config.guild(ctx.guild).whitelist() as whitelist:
                    whitelist.remove(obj.id)
                await self._bw_list_cache_update(ctx.guild)
        msg = _("`{list_type}` removed from translation whitelist.")
        list_type = humanize_list([c.name for c in channel_user_role])
        await ctx.send(msg.format(list_type=list_type))

    @whitelist.command(name="list")
    @checks.mod_or_permissions(manage_messages=True)
    async def whitelist_list(self, ctx: commands.Context) -> None:
        """
            List Channels, Users, and Roles in the servers translation whitelist.
        """
        whitelist = []
        for _id in await self.config.guild(ctx.guild).whitelist():
            try:
                whitelist.append(await ChannelUserRole().convert(ctx, str(_id)))
            except BadArgument:
                continue
        whitelist_s = ", ".join(x.name for x in whitelist)
        await ctx.send(
            _("`{whitelisted}` are currently whitelisted.").format(whitelisted=whitelist_s)
        )

    @blacklist.command(name="add")
    @checks.mod_or_permissions(manage_messages=True)
    async def blacklist_add(
        self, ctx: commands.Context, *channel_user_role: ChannelUserRole
    ) -> None:
        """
            Add a channel, user, or role to translation blacklist
        """
        if len(channel_user_role) < 1:
            return await ctx.send(
                _("You must supply 1 or more channels users or roles to be blacklisted.")
            )
        for obj in channel_user_role:
            if obj.id not in await self.config.guild(ctx.guild).blacklist():
                async with self.config.guild(ctx.guild).blacklist() as blacklist:
                    blacklist.append(obj.id)
                await self._bw_list_cache_update(ctx.guild)
        msg = _("`{list_type}` added to translation blacklist.")
        list_type = humanize_list([c.name for c in channel_user_role])
        await ctx.send(msg.format(list_type=list_type))

    @blacklist.command(name="remove", aliases=["rem", "del"])
    @checks.mod_or_permissions(manage_messages=True)
    async def blacklist_remove(
        self, ctx: commands.Context, *channel_user_role: ChannelUserRole
    ) -> None:
        """
            Remove a channel, user, or role from translation blacklist
        """
        if len(channel_user_role) < 1:
            return await ctx.send(
                _(
                    "You must supply 1 or more channels, users, "
                    "or roles to be removed from the blacklist"
                )
            )
        for obj in channel_user_role:
            if obj.id in await self.config.guild(ctx.guild).blacklist():
                async with self.config.guild(ctx.guild).blacklist() as blacklist:
                    blacklist.remove(obj.id)
                await self._bw_list_cache_update(ctx.guild)
        msg = _("`{list_type}` removed from translation blacklist.")
        list_type = humanize_list([c.name for c in channel_user_role])
        await ctx.send(msg.format(list_type=list_type))

    @blacklist.command(name="list")
    @checks.mod_or_permissions(manage_messages=True)
    async def blacklist_list(self, ctx: commands.Context) -> None:
        """
            List Channels, Users, and Roles in the servers translation blacklist.
        """
        blacklist = []
        for _id in await self.config.guild(ctx.guild).blacklist():
            try:
                blacklist.append(await ChannelUserRole().convert(ctx, str(_id)))
            except BadArgument:
                continue
        blacklist_s = ", ".join(x.name for x in blacklist)
        await ctx.send(
            _("`{blacklisted}` are currently blacklisted.").format(blacklisted=blacklist_s)
        )

    @translateset.command(aliases=["reaction", "reactions"])
    @checks.mod_or_permissions(manage_channels=True)
    @commands.guild_only()
    async def react(self, ctx: commands.Context) -> None:
        """
            Toggle translations to flag emoji reactions
        """
        guild = ctx.message.guild
        toggle = not await self.config.guild(guild).reaction()
        if toggle:
            verb = _("on")
        else:
            verb = _("off")
            if guild.id in self.cache["guild_reactions"]:
                self.cache["guild_reactions"].remove(guild.id)
        await self.config.guild(guild).reaction.set(toggle)
        msg = _("Reaction translations have been turned ")
        await ctx.send(msg + verb)

    @translateset.command(aliases=["multi"])
    @checks.is_owner()
    @commands.guild_only()
    async def multiple(self, ctx: commands.Context) -> None:
        """
            Toggle multiple translations for the same message

            This will also ignore the translated message from
            being translated into another language
        """
        toggle = not await self.config.cooldown.multiple()
        if toggle:
            verb = _("on")
        else:
            verb = _("off")
        await self.config.cooldown.multiple.set(toggle)
        self.cache["cooldown"] = await self.config.cooldown()
        msg = _("Multiple translations have been turned ")
        await ctx.send(msg + verb)

    @translateset.command(aliases=["cooldown"])
    @checks.is_owner()
    @commands.guild_only()
    async def timeout(self, ctx: commands.Context, time: int) -> None:
        """
            Set the cooldown before a message can be reacted to again
            for translation

            `<time>` Number of seconds until that message can be reacted to again
            Note: If multiple reactions are not allowed the timeout setting
            is ignored until the cache cleanup ~10 minutes.
        """
        await self.config.cooldown.timeout.set(time)
        self.cache["cooldown"] = await self.config.cooldown()
        msg = _("Translation timeout set to {time}s.").format(time=time)
        await ctx.send(msg)

    @translateset.command(aliases=["flags"])
    @checks.mod_or_permissions(manage_channels=True)
    @commands.guild_only()
    async def flag(self, ctx: commands.Context) -> None:
        """
            Toggle translations with flag emojis in text
        """
        guild = ctx.message.guild
        toggle = not await self.config.guild(guild).text()
        if toggle:
            verb = _("on")
        else:
            verb = _("off")
            if guild.id in self.cache["guild_messages"]:
                self.cache["guild_messages"].remove(guild.id)
        await self.config.guild(guild).text.set(toggle)
        msg = _("Flag emoji translations have been turned ")
        await ctx.send(msg + verb)

    @translateset.command()
    @checks.is_owner()
    async def creds(self, ctx: commands.Context) -> None:
        """
            You must get an API key from Google to set this up

            Note: Using this cog costs money, current rates are $20 per 1 million characters.
        """
        msg = _(
            "1. Go to Google Developers Console and log in with your Google account."
            "(https://console.developers.google.com/)\n"
            "2. You should be prompted to create a new project (name does not matter).\n"
            "3. Click on Enable APIs and Services at the top.\n"
            "4. In the list of APIs choose or search for Cloud Translate API and click on it."
            "Choose Enable.\n"
            "5. Click on Credentials on the left navigation bar.\n"
            "6. Click on Create Credential at the top.\n"
            "7. At the top click the link for \"API key\".\n"
            "8. No application restrictions are needed. Click Create at the bottom.\n"
            "9. You now have a key to add to \n"
            "`{prefix}set api google_translate api_key,YOUR_KEY_HERE`\n"
            ).format(prefix=ctx.prefix)
        await ctx.maybe_send_embed(msg)

    def cog_unload(self):
        self.clear_cache.cancel()

    __unload = cog_unload
