import logging
from typing import Optional

from redbot import version_info
from redbot.core import Config, checks, commands, i18n
from redbot.core.dev_commands import Dev

log = logging.getLogger("red.trusty-cogs.loaddev")

_ = i18n.Translator("LoadDev", __file__)


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
        self.bot.loop.create_task(self.initialize())

    def cog_unload(self):
        if not self.bot._cli_flags.dev:
            # only remove the dev cog if the dev cli flag is not set
            self.bot.remove_cog("Dev")

    async def initialize(self):
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
            self.bot.remove_cog("Dev")
            self.bot.add_cog(dev)

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
        Set an automatic replacemetn for `[p]mock` when auto loading dev.
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
                    log.debug(command.name)
        self.bot.remove_cog("Dev")
        # remove currently existing dev cog if it's loaded
        self.bot.add_cog(dev)
        await ctx.send(_("The following package was loaded: `{pack}`").format(pack="dev"))

    @commands.command(name="unloaddev")
    @checks.is_owner()
    async def unload_dev(self, ctx: commands.Context):
        """
        Unload Dev
        """
        self.bot.remove_cog("Dev")
        await ctx.send(_("The following package was unloaded: `{pack}`").format(pack="dev"))
