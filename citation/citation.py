import asyncio
import functools
import random
import re
from io import BytesIO
from typing import Any, Dict, List, Optional

import discord
from PIL import Image
from red_commons.logging import getLogger
from redbot.core import Config, checks, commands
from redbot.core.utils.chat_formatting import humanize_list

from .citations.factory import Factory
from .citations.themes import Theme
from .citations.themes import named as default_themes

RE_CTX: re.Pattern = re.compile(r"{([^}]+)\}")

log = getLogger("red.trusty-cogs.citation")


class AdvancedCitationFlags(commands.FlagConverter, case_insensitive=True):
    content: str = commands.flag(name="content")
    title: Optional[str] = commands.flag(name="title")
    penalty: Optional[str] = commands.flag(name="penalty")
    theme_name: Optional[str] = commands.flag(name="theme_name")
    alt_font: bool = commands.flag(name="alt_font", default=False)
    background: Optional[discord.Colour] = commands.flag(
        name="background", converter=commands.ColourConverter, default=None
    )
    foreground: Optional[discord.Colour] = commands.flag(
        name="foreground",
        converter=commands.ColourConverter,
        default=None,
    )
    details: Optional[discord.Colour] = commands.flag(
        name="details",
        converter=commands.ColourConverter,
        default=None,
    )
    to: Optional[discord.Member] = commands.flag(name="to", default=None)

    def get_theme(self, default_theme: Theme):
        return Theme(
            str(self.background or default_theme.background),
            str(self.foreground or default_theme.foreground),
            str(self.details or default_theme.details),
        )


class Citation(commands.Cog):
    """
    Create Papers Please citations

    Citation generation from https://gitlab.com/Saphire/citations
    """

    __author__ = [
        "Saphire",
        "TrustyJAID",
    ]
    __version__ = "1.3.0"
    __flavour__ = "Dynamic Replacements"

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=132620654087241729)
        self.config.register_guild(
            penalty="WARNING ISSUED - NO PENALTY",
            theme="blue",
            themes={},
            title="{guild.name} CITATION",
        )
        self._commit = ""
        self._repo = ""

    def format_help_for_context(self, ctx: commands.Context) -> str:
        """
        Thanks Sinbad!
        """
        pre_processed = super().format_help_for_context(ctx)
        ret = f"{pre_processed}\n\n- Cog Version: {self.__version__}\n"
        # we'll only have a repo if the cog was installed through Downloader at some point
        if self._repo:
            ret += f"- Repo: {self._repo}\n"
        # we should have a commit if we have the repo but just incase
        if self._commit:
            ret += f"- Commit: [{self._commit[:9]}]({self._repo}/tree/{self._commit})"
        return ret

    async def cog_before_invoke(self, ctx: commands.Context):
        await self._get_commit()

    async def _get_commit(self):
        if self._repo:
            return
        downloader = self.bot.get_cog("Downloader")
        if not downloader:
            return
        cogs = await downloader.installed_cogs()
        for cog in cogs:
            if cog.name == "citation":
                if cog.repo is not None:
                    self._repo = cog.repo.clean_url
                self._commit = cog.commit

    async def get_themes(self, guild: Optional[discord.Guild]) -> Dict[str, Theme]:
        if guild is None:
            return default_themes
        custom_themes = await self.config.guild(guild).themes()
        # I should only need a shallow copy of this since it's not nested
        ret = default_themes.copy()
        for theme_name, colours in custom_themes.items():
            ret[theme_name] = Theme(*colours)
        return ret

    async def get_theme(self, guild: Optional[discord.Guild]) -> Theme:
        if guild is not None:
            themes = await self.get_themes(guild)
            theme_name = await self.config.guild(guild).theme()
            return themes[theme_name]
        return default_themes["pink"]

    async def replace_mentions(self, ctx: commands.Context, content: str) -> str:
        """
        Replace mentions in the content of a message with the actual string.
        This is because the image doesn't render discord mentions properly.

        This should be the last step before rendering. Other converters have already been used.
        """
        for mention in ctx.message.mentions:
            content = re.sub(rf"<@!?{mention.id}>", f"@{mention.display_name}", content)
        for mention in ctx.message.channel_mentions:
            content = content.replace(mention.mention, f"#{mention.name}")
        for mention in ctx.message.role_mentions:
            content = content.replace(mention.mention, f"@{mention.name}")
        return content

    async def convert_parms(
        self, ctx: commands.Context, raw_response: str, to: Optional[discord.Member]
    ) -> str:
        # https://github.com/Cog-Creators/Red-DiscordBot/blob/V3/develop/redbot/cogs/customcom/customcom.py
        # ctx = await self.bot.get_context(message)
        results = RE_CTX.findall(raw_response)
        for result in results:
            param = await self.transform_parameter(result, ctx, to)
            raw_response = raw_response.replace("{" + result + "}", param)
        raw_response = raw_response.replace("[p]", ctx.clean_prefix)
        raw_prefixes = await self.bot.get_prefix(ctx.channel)
        prefixes = []
        for p in raw_prefixes:
            pattern = re.compile(rf"<@!?{ctx.me.id}>")
            prefixes.append(pattern.sub(f"@{ctx.me.display_name}".replace("\\", r"\\"), p))
        raw_response = raw_response.replace("[pp]", humanize_list(prefixes))
        return await self.replace_mentions(ctx, raw_response)

    @staticmethod
    async def transform_parameter(
        result: str, ctx: commands.Context, to: Optional[discord.Member]
    ) -> str:
        """
        For security reasons only specific objects are allowed
        Internals are ignored
        """
        raw_result = "{" + result + "}"
        objects: Dict[str, Any] = {
            "message": ctx.message,
            "author": ctx.author,
            "channel": ctx.channel,
            "guild": ctx.guild,
            "server": ctx.guild,
            "bot": ctx.me,
            "to": to,
        }
        if ctx.message.attachments:
            objects["attachment"] = ctx.message.attachments[0]
            # we can only reasonably support one attachment at a time
        if result in objects:
            return str(objects[result])
        try:
            first, second = result.split(".")
        except ValueError:
            return raw_result
        if first in objects and not second.startswith("_"):
            first = objects[first]
        else:
            return raw_result
        return str(getattr(first, second, raw_result))

    async def default_title(self, guild: Optional[discord.Guild]) -> str:
        if guild is not None:
            return await self.config.guild(guild).title()
        return "{bot.display_name} CITATION"

    async def default_penalty(self, guild: Optional[discord.Guild]) -> str:
        if guild is not None:
            return await self.config.guild(guild).penalty()
        return "WARNING ISSUED - NO PENALTY"

    @commands.hybrid_group(aliases=["citation"], fallback="make")
    @commands.bot_has_permissions(attach_files=True)
    async def citate(self, ctx: commands.Context, *, content: str) -> None:
        """
        Generate a citation from papers please

        `<content>` the content of the citation
        """
        async with ctx.typing():
            user = None
            if ctx.message.reference:
                if isinstance(ctx.message.reference.resolved, discord.Message):
                    user = ctx.message.reference.resolved.author

            content = await self.convert_parms(ctx, content, user)
            title = await self.convert_parms(ctx, await self.default_title(ctx.guild), user)

            barcode = self.user_id_to_barcode(ctx.author.id)

            penalty = await self.convert_parms(ctx, await self.default_penalty(ctx.guild), user)

            theme = await self.get_theme(ctx.guild)
            file = await self.make_citation(
                issuer=ctx.author,
                content=content,
                penalty=penalty,
                title=title,
                barcode=barcode,
                theme=theme,
                to=user,
            )
            if file is None:
                await ctx.send("sorry something went wrong!")
                return
        await ctx.send(file=file, reference=ctx.message.reference, mention_author=False)

    @citate.command(name="advanced", aliases=["advcitation"])
    @commands.bot_has_permissions(attach_files=True)
    async def advcitate(
        self,
        ctx: commands.Context,
        *,
        citation: AdvancedCitationFlags,
    ) -> None:
        """
        Generate a citation from papers please

        This command allows full control over the citation generator.
        You can provide the following arguments:
        - `content:` The body of the citation and is required.
        - `title:` the title of the citation. By default this will be the server name.
        - `penalty:` The penalty being issued.
        - `theme_name:` If provided will set the theme to one that is saved or a default.
        Your servers saved default will be used if not provided.
        - `background:` If provided will set the background for the citation.
        This overrides the background of whatever `theme_name` becomes.
        - `foreground:` If provided will set the foreground colour for the citaiton.
        This overrides the foreground of whatever `theme_name` becomes.
        - `details:` If provided will set the details colour for the citation.
        This overrides the details of whatever `theme_name` becomes.
        - `to:` Who this citation is issued to. If not provided then using a
        reply can be used instead or will not appear.

        """
        async with ctx.typing():
            theme = await self.get_theme(ctx.guild)

            user = citation.to
            if user is None and ctx.message.reference:
                if isinstance(ctx.message.reference.resolved, discord.Message):
                    user = ctx.message.reference.resolved.author

            if citation.theme_name:
                themes = await self.get_themes(ctx.guild)
                if citation.theme_name not in themes:
                    await ctx.send(f"`{citation.theme_name}` is not an available theme.")
                    return
                theme = themes[citation.theme_name]
            elif citation.background or citation.foreground or citation.details:
                theme = citation.get_theme(theme)

            content = await self.convert_parms(ctx, citation.content, user)
            title = await self.convert_parms(
                ctx,
                citation.title or await self.default_title(ctx.guild),
                user,
            )
            penalty = await self.convert_parms(
                ctx, citation.penalty or await self.default_penalty(ctx.guild), user
            )
            barcode = self.user_id_to_barcode(ctx.author.id)

            file = await self.make_citation(
                issuer=ctx.author,
                content=content,
                penalty=penalty,
                title=title,
                barcode=barcode,
                theme=theme,
                use_alt_font=citation.alt_font,
                to=user,
            )
            if file is None:
                await ctx.send("sorry something went wrong!")
                return
        await ctx.send(file=file, reference=ctx.message.reference, mention_author=False)

    @staticmethod
    def user_id_to_barcode(user_id: int) -> List[int]:
        return [max(int(i), 1) for i in str(user_id)[-4:]]

    @citate.group(name="set")
    @checks.mod_or_permissions(manage_messages=True)
    @commands.guild_only()
    async def citationset(self, ctx: commands.Context) -> None:
        """
        Set citation settings for the server.
        """
        pass

    @citationset.command(name="theme")
    @commands.guild_only()
    async def set_theme(self, ctx: commands.Context, theme: str):
        """
        Set the citation theme to be used on this server

        Available themes are:
        - pink
        - gold
        - gray
        - blue
        """
        async with ctx.typing():
            themes = await self.get_themes(ctx.guild)
            if theme not in themes:
                return await ctx.send(f"`{theme}` is not an available theme.")
            await self.config.guild(ctx.guild).theme.set(theme)
        await ctx.send(f"Theme set to `{theme}`.")

    @citationset.command(name="penalty")
    @commands.guild_only()
    async def set_penalty(self, ctx: commands.Context, *, penalty: str):
        """
        Set the citation penalty for the server.

        This supports dynamic replacement. So if you want to always
        show the author of the command in the title, the server, etc.
        you can do so.
        Available parameters:
        - `{author}` [Attributes.](https://discordpy.readthedocs.io/en/latest/api.html#member)
        - `{bot}` The bot user. See `{author}` for attributes.
        - `{channel}` [Attributes.](https://discordpy.readthedocs.io/en/latest/api.html#textchannel)
        - `{guild}` or `{server}` [Attributes.](https://discordpy.readthedocs.io/en/latest/api.html#guild)
        - `{message}` [Attributes.](https://discordpy.readthedocs.io/en/latest/api.html#message)
        - `{to}` The user this is issued to. Can be `None`. See `{author}` for attributes.
        - `[\u200bp]` The prefix that was used to make this command.
        - `[pp]` a humanized list of all the bots prefixes in the channel.

        Example:
        `[p]citation set penalty {guild.name} WARNING`
        will set the default title to the current server name.
        """
        async with ctx.typing():
            penalty = await self.replace_mentions(ctx, penalty)
            await self.config.guild(ctx.guild).penalty.set(penalty)
        await ctx.send(f"Penalty set to `{penalty}`")

    @citationset.command(name="title")
    @commands.guild_only()
    async def set_title(self, ctx: commands.Context, *, title: str):
        """
        Set the citation title for the server.

        This supports dynamic replacement. So if you want to always
        show the author of the command in the title, the server, etc.
        you can do so.
        Available parameters:
        - `{author}` [Attributes.](https://discordpy.readthedocs.io/en/latest/api.html#member)
        - `{bot}` The bot user. See `{author}` for attributes.
        - `{channel}` [Attributes.](https://discordpy.readthedocs.io/en/latest/api.html#textchannel)
        - `{guild}` or `{server}` [Attributes.](https://discordpy.readthedocs.io/en/latest/api.html#guild)
        - `{message}` [Attributes.](https://discordpy.readthedocs.io/en/latest/api.html#message)
        - `{to}` The user this is issued to. Can be `None`. See `{author}` for attributes.
        - `[\u200bp]` The prefix that was used to make this command.
        - `[pp]` a humanized list of all the bots prefixes in the channel.

        Example:
        `[p]citation set title {guild.name} CITATION`
        will set the default title to the current server name.
        """
        async with ctx.typing():
            # replace the mentions here with strings so they're saved.
            # Dynamic replacements happen after.
            penalty = await self.replace_mentions(ctx, title)
            await self.config.guild(ctx.guild).title.set(penalty)
        await ctx.send(f"Penalty set to `{penalty}`")

    @citationset.command(name="maketheme")
    @commands.guild_only()
    @commands.bot_has_permissions(attach_files=True)
    async def make_theme(
        self,
        ctx: commands.Context,
        name: str,
        background: discord.Colour,
        foreground: discord.Colour,
        details: discord.Colour,
    ):
        """
        Create your own custom theme to be used for advanced citation
        """
        # here we check default_themes only so we don't override them
        # this allows the user to modify ones they've made already
        if name in default_themes:
            await ctx.send("That theme name already exists.")
            return
        async with ctx.typing():
            theme = Theme(str(background), str(foreground), str(details))
            async with self.config.guild(ctx.guild).themes() as saved_themes:
                saved_themes[name] = theme.to_json()
            file = await self.make_citation(
                ctx.author,
                "test theme",
                "none",
                "Test Theme",
                self.user_id_to_barcode(ctx.author.id),
                theme,
            )
        await ctx.send("Here's how your theme will look.", file=file)

    async def make_citation(
        self,
        issuer: discord.abc.User,
        content: str,
        penalty: str,
        title: str,
        barcode: List[int],
        theme: Theme,
        use_alt_font: bool = False,
        to: Optional[discord.abc.User] = None,
    ) -> Optional[discord.File]:
        penalty_list = [penalty]
        if to is not None:
            penalty_list.append(f"Issued to {to.display_name}")
        penalty_list.append(f"Generated by {issuer.display_name}")
        task = functools.partial(
            self.make_citation_gif,
            content=content.split("\n"),
            penalty=penalty_list,
            title=title.split("\n"),
            barcode=barcode,
            theme=theme,
            use_alt_font=use_alt_font,
        )
        loop = asyncio.get_running_loop()
        task = loop.run_in_executor(None, task)
        try:
            temp: BytesIO = await asyncio.wait_for(task, timeout=60)
        except asyncio.TimeoutError:
            return None

        temp.seek(0)
        return discord.File(temp)

    def make_citation_gif(
        self,
        content: List[str],
        penalty: List[str],
        title: List[str],
        barcode: List[int],
        theme: Theme,
        use_alt_font: bool,
    ):
        factory = Factory(theme=theme, use_alt_font=use_alt_font)
        temp = BytesIO()
        base_img = factory.generate_image(content, penalty, title, barcode)
        new_img_list = []
        height = int(base_img.height / 2)
        with Image.new(mode="RGBA", size=(359, height), color=(0, 0, 0, 0)) as new_image:
            temp_img = new_image.copy()

            base = base_img.copy().convert("RGBA")
            temp_img.paste(base, (0, height))
            new_img_list.append(temp_img)
            duration = [1, 1]
            for i in range(0, height):
                temp_img = new_image.copy()
                base = base_img.copy().convert("RGBA")
                temp_img.paste(base, (0, (height - (i * 2))))
                new_img_list.append(temp_img)
                duration.append(random.randint(0, 250))
            new_image.save(
                temp,
                format="GIF",
                save_all=True,
                append_images=new_img_list,
                duration=duration,
                disposal=2,
                optimize=False,
            )
        # image.save(temp, format="GIF")
        temp.name = "citation.gif"
        return temp
