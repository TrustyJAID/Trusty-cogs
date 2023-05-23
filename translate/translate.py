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
from typing import Optional

import discord
from discord.ext.commands.errors import BadArgument
from red_commons.logging import getLogger
from redbot.core import Config, VersionInfo, checks, commands, version_info
from redbot.core.i18n import Translator, cog_i18n
from redbot.core.utils.chat_formatting import humanize_list
from redbot.core.utils.views import SetApiView

from .api import FlagTranslation, GoogleTranslateAPI, GoogleTranslator, StatsCounter
from .converters import ChannelUserRole
from .errors import GoogleTranslateAPIError

BASE_URL = "https://translation.googleapis.com"
_ = Translator("Translate", __file__)
log = getLogger("red.trusty-cogs.Translate")


@cog_i18n(_)
class Translate(GoogleTranslateAPI, commands.Cog):
    """
    Translate messages using Google Translate
    """

    __author__ = ["Aziz", "TrustyJAID"]
    __version__ = "2.5.0"

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, 156434873547, force_registration=True)
        default_guild = {
            "reaction": False,
            "text": False,
            "whitelist": [],
            "blacklist": [],
            "count": {"characters": 0, "requests": 0, "detect": 0},
        }
        default = {
            "cooldown": {"past_flags": [], "timeout": 0, "multiple": False},
            "count": {"characters": 0, "requests": 0, "detect": 0},
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
            "guild_whitelist": {},
        }
        self._key: Optional[str] = None
        self.translation_loop.start()
        self.stats_counter = StatsCounter(config=self.config)
        self.translate_ctx = discord.app_commands.ContextMenu(
            name="Translate Message", callback=self.translate_from_message
        )
        self._tr = None

    def format_help_for_context(self, ctx: commands.Context) -> str:
        """
        Thanks Sinbad!
        """
        pre_processed = super().format_help_for_context(ctx)
        return f"{pre_processed}\n\nCog Version: {self.__version__}"

    async def red_delete_data_for_user(self, **kwargs):
        """
        Nothing to delete
        """
        return

    async def cog_load(self) -> None:
        self.bot.tree.add_command(self.translate_ctx)
        central_key = (await self.bot.get_shared_api_tokens("google_translate")).get("api_key")
        if central_key:
            self._tr = GoogleTranslator(central_key)
        await self.stats_counter.initialize()

    @commands.hybrid_group(fallback="text")
    async def translate(
        self,
        ctx: commands.Context,
        to_language: FlagTranslation,
        *,
        text: str,
    ) -> None:
        """
        Translate messages with Google Translate

        `<to_language>` is the language you would like to translate
        `<text>` is the text you want to translate.
        """
        if self._tr is None:
            msg = _("The bot owner needs to set an api key first!")
            await ctx.send(msg)
            return
        author = ctx.message.author
        requestor = ctx.message.author
        msg = ctx.message
        try:
            detected_lang = await self._tr.detect_language(text)
            await self.stats_counter.add_detect(ctx.guild)
        except GoogleTranslateAPIError as e:
            await ctx.send(str(e))
            return
        from_lang = str(detected_lang)
        if to_language == from_lang:
            await ctx.send(
                _("I cannot translate `{from_lang}` to `{to}`").format(
                    from_lang=from_lang, to=to_language
                )
            )
            return
        try:
            translated_text = await self._tr.translate_text(to_language, text, str(from_lang))
            await self.stats_counter.add_requests(ctx.guild, text)
        except GoogleTranslateAPIError as e:
            await ctx.send(str(e))
            return
        if translated_text is None:
            await ctx.send(_("Nothing to be translated."))
            return
        if ctx.channel.permissions_for(ctx.me).embed_links:
            em = translated_text.embed(author, from_lang, to_language, requestor)
            if version_info >= VersionInfo.from_str("3.4.6") and msg.channel.id == ctx.channel.id:
                await ctx.send(embed=em, reference=msg, mention_author=False)
            else:
                await ctx.send(embed=em)
        else:
            if version_info >= VersionInfo.from_str("3.4.6") and msg.channel.id == ctx.channel.id:
                await ctx.send(translated_text, reference=msg, mention_author=False)
            else:
                await ctx.send(translated_text)

    @translate.group(name="set")
    async def translateset(self, ctx: commands.Context) -> None:
        """
        Toggle the bot auto translating
        """
        pass

    @translate.command(name="stats")
    async def translate_stats(self, ctx: commands.Context, guild_id: Optional[int]):
        """
        Shows translation usage
        """
        if guild_id and not await self.bot.is_owner(ctx.author):
            await ctx.send(_("That is only available for the bot owner."))
            return
        elif guild_id and await self.bot.is_owner(ctx.author):
            if not (guild := self.bot.get_guild(guild_id)):
                await ctx.send(_("Guild `{guild_id}` not found.").format(guild_id=guild_id))
                return
        else:
            guild = ctx.guild
        if guild is None and not await self.bot.is_owner(ctx.author):
            await ctx.send(_("This command is only available inside guilds."))
            return
        msg = await self.stats_counter.text(guild)
        await ctx.maybe_send_embed(msg)

    @translate.group(name="blocklist", aliases=["blacklist"], with_app_command=False)
    @checks.mod_or_permissions(manage_messages=True)
    @commands.guild_only()
    async def blacklist(self, ctx: commands.Context) -> None:
        """
        Set blacklist options for translations

        blacklisting supports channels, users, or roles
        """
        pass

    @translate.group(name="allowlist", aliases=["whitelist"], with_app_command=False)
    @checks.mod_or_permissions(manage_messages=True)
    @commands.guild_only()
    async def whitelist(self, ctx: commands.Context) -> None:
        """
        Set whitelist options for translations

        whitelisting supports channels, users, or roles
        """
        pass

    @whitelist.command(name="add", with_app_command=False)
    @checks.mod_or_permissions(manage_messages=True)
    @commands.guild_only()
    async def whitelist_add(
        self, ctx: commands.Context, *channel_user_role: ChannelUserRole
    ) -> None:
        """
        Add a channel, user, or role to translation whitelist
        """
        if len(channel_user_role) < 1:
            await ctx.send(
                _("You must supply 1 or more channels users or roles to be whitelisted.")
            )
            return
        for obj in channel_user_role:
            if obj.id not in await self.config.guild(ctx.guild).whitelist():
                async with self.config.guild(ctx.guild).whitelist() as whitelist:
                    whitelist.append(obj.id)

        msg = _("`{list_type}` added to translation whitelist.")
        list_type = humanize_list([c.name for c in channel_user_role])
        await ctx.send(msg.format(list_type=list_type))

    @whitelist.command(name="remove", aliases=["rem", "del"], with_app_command=False)
    @checks.mod_or_permissions(manage_messages=True)
    @commands.guild_only()
    async def whitelist_remove(
        self, ctx: commands.Context, *channel_user_role: ChannelUserRole
    ) -> None:
        """
        Remove a channel, user, or role from translation whitelist
        """
        if len(channel_user_role) < 1:
            await ctx.send(
                _(
                    "You must supply 1 or more channels, users, "
                    "or roles to be removed from the whitelist"
                )
            )
            return
        for obj in channel_user_role:
            if obj.id in await self.config.guild(ctx.guild).whitelist():
                async with self.config.guild(ctx.guild).whitelist() as whitelist:
                    whitelist.remove(obj.id)

        msg = _("`{list_type}` removed from translation whitelist.")
        list_type = humanize_list([c.name for c in channel_user_role])
        await ctx.send(msg.format(list_type=list_type))

    @whitelist.command(name="list", with_app_command=False)
    @checks.mod_or_permissions(manage_messages=True)
    @commands.guild_only()
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
        if whitelist:
            whitelist_s = ", ".join(x.name for x in whitelist)
            await ctx.send(
                _("`{whitelisted}` are currently whitelisted.").format(whitelisted=whitelist_s)
            )
        else:
            await ctx.send(
                _(
                    "There are currently no channels, users, or roles in this servers translate allowlist."
                )
            )

    @blacklist.command(name="add", with_app_command=False)
    @checks.mod_or_permissions(manage_messages=True)
    @commands.guild_only()
    async def blacklist_add(
        self, ctx: commands.Context, *channel_user_role: ChannelUserRole
    ) -> None:
        """
        Add a channel, user, or role to translation blacklist
        """
        if len(channel_user_role) < 1:
            await ctx.send(
                _("You must supply 1 or more channels users or roles to be blacklisted.")
            )
            return
        for obj in channel_user_role:
            if obj.id not in await self.config.guild(ctx.guild).blacklist():
                async with self.config.guild(ctx.guild).blacklist() as blacklist:
                    blacklist.append(obj.id)
        msg = _("`{list_type}` added to translation blacklist.")
        list_type = humanize_list([c.name for c in channel_user_role])
        await ctx.send(msg.format(list_type=list_type))

    @blacklist.command(name="remove", aliases=["rem", "del"], with_app_command=False)
    @checks.mod_or_permissions(manage_messages=True)
    @commands.guild_only()
    async def blacklist_remove(
        self, ctx: commands.Context, *channel_user_role: ChannelUserRole
    ) -> None:
        """
        Remove a channel, user, or role from translation blacklist
        """
        if len(channel_user_role) < 1:
            await ctx.send(
                _(
                    "You must supply 1 or more channels, users, "
                    "or roles to be removed from the blacklist"
                )
            )
            return
        for obj in channel_user_role:
            if obj.id in await self.config.guild(ctx.guild).blacklist():
                async with self.config.guild(ctx.guild).blacklist() as blacklist:
                    blacklist.remove(obj.id)

        msg = _("`{list_type}` removed from translation blacklist.")
        list_type = humanize_list([c.name for c in channel_user_role])
        await ctx.send(msg.format(list_type=list_type))

    @blacklist.command(name="list", with_app_command=False)
    @checks.mod_or_permissions(manage_messages=True)
    @commands.guild_only()
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
        if blacklist:
            blacklist_s = ", ".join(x.name for x in blacklist)
            await ctx.send(
                _("`{blacklisted}` are currently blacklisted.").format(blacklisted=blacklist_s)
            )
        else:
            await ctx.send(
                _(
                    "There are currently no channels, users, or roles in this servers translate blocklist."
                )
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

    @translateset.command(aliases=["multi"], with_app_command=False)
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

    @translateset.command(aliases=["cooldown"], with_app_command=False)
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

    @translateset.command(with_app_command=False)
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
            '7. At the top click the link for "API key".\n'
            "8. No application restrictions are needed. Click Create at the bottom.\n"
            "9. You now have a key to add to \n"
            "`{prefix}set api google_translate api_key,YOUR_KEY_HERE`\n"
        ).format(prefix=ctx.prefix)
        keys = {"api_key": ""}
        view = SetApiView("google_translate", keys)
        if await ctx.embed_requested():
            em = discord.Embed(description=msg)
            await ctx.send(embed=em, view=view)
            # await ctx.send(embed=em)
        else:
            await ctx.send(msg, view=view)
            # await ctx.send(message)

    async def cog_unload(self):
        await self.stats_counter.save()
        self.bot.tree.remove_command(self.translate_ctx.name, type=self.translate_ctx.type)
        if self._tr is not None:
            await self._tr.close()
