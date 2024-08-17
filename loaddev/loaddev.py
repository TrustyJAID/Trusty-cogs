from typing import Optional

import discord
from red_commons.logging import getLogger
from redbot import version_info
from redbot.core import Config, checks, commands, i18n
from redbot.core.dev_commands import Dev, DevOutput, cleanup_code
from redbot.core.utils.chat_formatting import box, pagify
from yarl import URL

log = getLogger("red.trusty-cogs.loaddev")

_ = i18n.Translator("LoadDev", __file__)


class EvalModal(discord.ui.Modal):
    def __init__(self, ctx: commands.Context, debug: bool):
        self.debug = debug
        self.ctx = ctx
        title = "Debug" if self.debug else "Eval"
        super().__init__(title=title)

        self.text = discord.ui.TextInput(style=discord.TextStyle.paragraph, label=title)
        self.add_item(self.text)

    async def on_submit(self, interaction: discord.Interaction):
        dev_cog = interaction.client.get_cog("Dev")
        env = dev_cog.get_environment(self.ctx)
        env["interaction"] = interaction
        source = cleanup_code(self.text.value)
        if self.debug:
            output = await DevOutput.from_debug(
                self.ctx, source=source, source_cache=dev_cog.source_cache, env=env
            )
        else:
            output = await DevOutput.from_eval(
                self.ctx, source=source, source_cache=dev_cog.source_cache, env=env
            )
        if output.result is not None:
            dev_cog._last_result = output.result
        await output.send()
        await interaction.response.defer()


class EvalButton(discord.ui.Button):
    def __init__(self, ctx: commands.Context, debug: bool):
        self.debug = debug
        self.ctx = ctx
        title = "Debug" if self.debug else "Eval"
        super().__init__(style=discord.ButtonStyle.blurple, label=title)

    async def callback(self, interaction: discord.Interaction):
        modal = EvalModal(self.ctx, self.debug)
        await interaction.response.send_modal(modal)


class EvalView(discord.ui.View):
    def __init__(self, ctx: commands.Context):
        super().__init__()
        self.eval_button = EvalButton(ctx, debug=False)
        self.debug_button = EvalButton(ctx, debug=True)
        self.add_item(self.eval_button)
        self.add_item(self.debug_button)
        self.message: discord.Message = discord.utils.MISSING

    async def on_timeout(self):
        if self.message is not None:
            await self.message.edit(view=None)

    async def interaction_check(self, interaction: discord.Interaction):
        if not await interaction.client.is_owner(interaction.user):
            await interaction.response.send_message(
                content=_("You are not authorized to interact with this."), ephemeral=True
            )
            return False
        return True


class LoadDev(commands.Cog):
    """Allow live loading of Dev commands from Core"""

    __version__ = version_info
    __author__ = [
        "TrustyJAID",
    ]

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=218773382617890828)
        self.config.register_global(
            replace_mock=None,
            auto_load_dev=False,
        )

    async def cog_unload(self):
        if not self.bot._cli_flags.dev:
            # only remove the dev cog if the dev cli flag is not set
            await self.bot.remove_cog("Dev")
        try:
            self.bot.remove_dev_env_value("evalview")
        except Exception:
            log.exception("Error removing retrigger from dev environment.")

    async def cog_load(self):
        replace_mock = await self.config.replace_mock()
        if await self.config.auto_load_dev():
            dev = Dev()
            if replace_mock:
                for command in dev.walk_commands():
                    if command.name == "mock":
                        del dev.all_commands[str(command)]
                        command.name = replace_mock
                        dev.all_commands[replace_mock] = command
                        log.debug("Replaced Mock command")
            await self.bot.remove_cog("Dev")
            await self.bot.add_cog(dev)
        try:
            self.bot.add_dev_env_value("evalview", lambda x: EvalView)
        except Exception:
            pass

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

    @commands.command(aliases=["ebutt"])
    @commands.is_owner()
    async def ebutton(self, ctx: commands.Context):
        """
        Send a button that allows you to eval code written in a modal.
        """
        if not self.bot.get_cog("Dev"):
            command = self.load_dev.qualified_name
            await ctx.send(
                "You need Dev loaded for this command to work."
                f"Use `{ctx.clean_prefix}{command}` to set this up without the `--dev` flag."
            )
            return
        view = EvalView(ctx)
        view.message = await ctx.send("Dev Tools", view=view)

    @commands.command(name="url")
    @commands.bot_has_permissions(embed_links=True)
    async def url_command(self, ctx: commands.Context, *, url: str) -> None:
        """
        Parse and make a URL human readable.
        """
        url_obj = URL(url)
        em = discord.Embed(description=box(url_obj.human_repr()))
        if url_obj.scheme:
            em.add_field(name="Scheme", value=box(url_obj.scheme))
        if url_obj.user:
            em.add_field(name="User", value=box(url_obj.user))
        if url_obj.password:
            em.add_field(name="password", value=box(url_obj.password))
        if url_obj.host:
            em.add_field(name="host", value=box(url_obj.host))
        if url_obj.port:
            em.add_field(name="port", value=box(str(url_obj.port)))
        if url_obj.path:
            em.add_field(name="path", value=box(url_obj.path))
        if url_obj.query:
            msg = "".join(box(f"{k}={v}") for k, v in url_obj.query.items())
            for page in pagify(msg, delims="```\n", page_length=1024):
                em.add_field(name="query", value=page)
        if url_obj.fragment:
            em.add_field(name="fragment", value=box(url_obj.fragment))
        await ctx.send(embed=em)

    @commands.group()
    @checks.is_owner()
    async def devset(self, ctx: commands.Context):
        """
        Settings for automatically loading/unloading cores dev
        using this cog
        """

    @devset.command()
    async def autoload(self, ctx: commands.Context, auto_load: bool):
        """
        Whether or not to automatically load dev when this cog is loaded.

        Note: This does not affect the CLI flag `--dev`
        """
        await self.config.auto_load_dev.set(auto_load)
        if auto_load:
            await ctx.send(_("I will automatically load dev when this cog is loaded."))
        else:
            await ctx.send(_("I will not automatically load dev when this cog is loaded."))

    @devset.command()
    async def replacemock(self, ctx: commands.Context, replacement: Optional[str]):
        """
        Set an automatic replacement for `[p]mock` when auto loading dev.
        """
        await self.config.replace_mock.set(replacement)
        if replacement:
            await ctx.send(
                _("I will replace the `[p]mock` command with `[p]{replacement}`.").format(
                    replacement=replacement
                )
            )
        else:
            await ctx.send(_("I will not replace the `[p]mock` command."))

    @commands.command(name="loaddev")
    @checks.is_owner()
    async def load_dev(self, ctx: commands.Context, replace_mock: Optional[str] = None):
        """
        Dynamically loads dev cog

        `[replace_mock]` the replacement command name for `[p]mock`
        If nothing is provided this will not replace `[p]mock`.
        """
        dev = Dev()
        # log.debug(dir(dev))
        # return
        if not replace_mock:
            replace_mock = await self.config.replace_mock()
        if replace_mock:
            for command in dev.walk_commands():
                if command.name == "mock":
                    del dev.all_commands[str(command)]
                    command.name = replace_mock
                    dev.all_commands[replace_mock] = command
                    log.verbose("load_dev loading command: %s", command.name)
        await self.bot.remove_cog("Dev")
        # remove currently existing dev cog if it's loaded
        await self.bot.add_cog(dev)
        await ctx.send(_("The following package was loaded: `{pack}`").format(pack="dev"))

    @commands.command(name="unloaddev")
    @checks.is_owner()
    async def unload_dev(self, ctx: commands.Context):
        """
        Unload Dev
        """
        await self.bot.remove_cog("Dev")
        await ctx.send(_("The following package was unloaded: `{pack}`").format(pack="dev"))
