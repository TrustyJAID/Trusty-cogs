import logging

from redbot.core import commands, Config, checks
from redbot.core.i18n import Translator, cog_i18n

from .api import GoogleTranslateAPI, FlagTranslation
from .errors import GoogleTranslateAPIError

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
    __version__ = "2.0.1"

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, 156434873547, force_registration=True)
        default_guild = {
            "reaction": False,
            "text": False
        }
        default = {
            "api_key": None,
            "cooldown": {
                "past_flags": [],
                "timeout": 0,
                "multiple": False,
            }
        }
        self.config.register_guild(**default_guild)
        self.config.register_global(**default)
        self.cache = {"translations": []}
        self.clear_cache = self.bot.loop.create_task(self.cleanup_cache())

    @commands.command()
    async def translate(self, ctx, to_language: FlagTranslation, *, message: str):
        """
            Translate messages with Google Translate

            `to_language` is the language you would like to translate
            `message` is the message to translate
        """
        if await self.config.api_key() is None:
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

    @translateset.command(aliases=["multi"])
    @checks.is_owner()
    @commands.guild_only()
    async def multiple(self, ctx):
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
        msg = _("Multiple translations have been turned ")
        await ctx.send(msg + verb)

    @translateset.command(aliases=["cooldown"])
    @checks.is_owner()
    @commands.guild_only()
    async def timeout(self, ctx, time: int):
        """
            Set the cooldown before a message can be reacted to again
            for translation

            `<time>` Number of seconds until that message can be reacted to again
            Note: If multiple reactions are not allowed the timeout setting
            is ignored until the cache cleanup ~10 minutes.
        """
        await self.config.cooldown.timeout.set(time)
        msg = _("Translation timeout set to {time}s.").format(time=time)
        await ctx.send(msg)

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
            You must get an API key from Google to set this up

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

    def cog_unload(self):
        self.clear_cache.cancel()

    __unload = cog_unload
