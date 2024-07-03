from red_commons.logging import getLogger
from redbot.core import Config, commands

from .converters import AutoModActionFlags, AutoModRuleFlags, AutoModTriggerFlags
from .menus import (
    AutoModActionsPages,
    AutoModRulePages,
    AutoModTriggersPages,
    BaseMenu,
    ConfirmView,
)

log = getLogger("red.trusty-cogs.automod")


class AutoMod(commands.Cog):
    """
    Interact with and view discord's automod
    """

    __author__ = ["TrustyJAID"]
    __version__ = "1.0.4"

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, 218773382617890828)
        self.config.register_guild(actions={}, triggers={}, rules={})
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
            if cog.name == "automod":
                if cog.repo is not None:
                    self._repo = cog.repo.clean_url
                self._commit = cog.commit

    @commands.hybrid_group(name="automod")
    @commands.guild_only()
    async def automod(self, ctx: commands.Context):
        """Commnads for interacting with automod"""

    @automod.command(name="rules", aliases=["list", "rule", "view"])
    @commands.bot_has_permissions(manage_guild=True)
    @commands.mod_or_permissions(manage_guild=True)
    async def view_automod(self, ctx: commands.Context):
        """View the servers current automod rules"""
        rules = await ctx.guild.fetch_automod_rules()
        if len(rules) <= 0:
            await ctx.send("There are no rules setup yet.")
            return
        pages = AutoModRulePages(rules, guild=ctx.guild)
        await BaseMenu(pages, self).start(ctx)

    @automod.command(name="actions", aliases=["action"])
    @commands.mod_or_permissions(manage_guild=True)
    async def view_automod_actions(self, ctx: commands.Context):
        """View the servers saved automod actions"""
        actions_dict = await self.config.guild(ctx.guild).actions()
        actions = []
        for k, v in actions_dict.items():
            v.update({"name": k, "guild": ctx.guild})
            actions.append(v)
        if len(actions) <= 0:
            await ctx.send("There are no actions saved.")
            return
        pages = AutoModActionsPages(actions, guild=ctx.guild)
        await BaseMenu(pages, self).start(ctx)

    @automod.command(name="triggers", aliases=["trigger"])
    @commands.mod_or_permissions(manage_guild=True)
    async def view_automod_triggers(self, ctx: commands.Context):
        """View the servers saved automod triggers"""
        triggers_dict = await self.config.guild(ctx.guild).triggers()
        triggers = []
        for k, v in triggers_dict.items():
            v.update({"name": k, "guild": ctx.guild})
            triggers.append(v)
        if len(triggers) <= 0:
            await ctx.send("There are no triggers saved.")
            return
        pages = AutoModTriggersPages(triggers, guild=ctx.guild)
        await BaseMenu(pages, self).start(ctx)

    @automod.group(name="create", aliases=["c"])
    @commands.admin_or_permissions(manage_guild=True)
    async def create(self, ctx: commands.Context):
        """Create automod rules, triggers, and actions"""

    @create.command(name="rule")
    @commands.bot_has_permissions(manage_guild=True)
    @commands.admin_or_permissions(manage_guild=True)
    async def create_automod_rule(
        self, ctx: commands.Context, name: str, *, rule: AutoModRuleFlags
    ):
        """
        Create an automod rule in the server

        Usage:
        - `trigger:` The name of a saved trigger.
        - `actions:` The name(s) of saved actions.
        - `enabled:` yes/true/t to enable this rule right away.
        - `roles:` The roles that are exempt from this rule.
        - `channels:` The channels that are exempt from this rule.
        - `reason:` An optional reason for creating this rule.

        Example:
            `[p]automod create rule trigger: mytrigger actions: timeoutuser notifymods enabled: true roles: @mods`
            Will create an automod rule with the saved trigger `mytrigger` and
            the saved actions `timeoutuser` and `notifymods`.
        """
        if not name:
            await ctx.send_help()
            return
        log.debug(f"{rule.to_args()}")
        if not rule.trigger:
            await ctx.send("No trigger was provided for the rule.")
            return
        rule_args = rule.to_args()
        name = name.lower()
        if rule_args.get("reason") is not None:
            rule_args["reason"] = f"Created by {ctx.author}\n" + rule_args["reason"]
        try:
            rule = await ctx.guild.create_automod_rule(name=name, **rule_args)
        except Exception as e:
            rule_args_str = "\n".join(f"- {k}: {v}" for k, v in rule_args.items())
            await ctx.send(
                (
                    "There was an error creating a rule with the following rules:\n"
                    f"Error: {e}\n"
                    f"Name: {name}\n"
                    f"Rules:\n{rule_args_str}"
                )
            )
            return
        pages = AutoModRulePages([rule], guild=ctx.guild)
        await BaseMenu(pages, self).start(ctx)

    @create.command(name="action", aliases=["a"])
    @commands.admin_or_permissions(manage_guild=True)
    async def create_automod_action(
        self, ctx: commands.Context, name: str, *, action: AutoModActionFlags
    ):
        """
        Create a saved action for use in automod Rules.

        - `<name>` The name of this action for reference later.
        Usage: `<action>`
        - `message:` The message to send to a user when triggered.
        - `channel:` The channel to send a notification to.
        - `duration:` How long to timeout the user for. Max 28 days.
        Only one of these options can be applied at a time.
        Examples:
            `[p]automod create action grumpyuser message: You're being too grumpy`
            `[p]automod create action notifymods channel: #modlog`
            `[p]automod create action 2hrtimeout duration: 2 hours`

        """
        try:
            action.get_action()
        except ValueError as e:
            # d.py errors here are concise enough to explain the issue.
            await ctx.send(e)
            return
        name = name.lower()
        async with self.config.guild(ctx.guild).actions() as actions:
            if name in actions:
                pred = ConfirmView(ctx.author)
                pred.message = await ctx.send(
                    f"An action with the name `{name}` already exists. Would you like to overwrite it?",
                    view=pred,
                )
                await pred.wait()
                if not pred.result:
                    await ctx.send("Please choose a different name then.")
                    return
            actions[name] = action.to_json()
        await ctx.send(f"Saving action `{name}` with the following settings:\n{action.to_str()}")

    @create.command(name="trigger")
    @commands.admin_or_permissions(manage_guild=True)
    async def create_automod_trigger(
        self, ctx: commands.Context, name: str, *, trigger: AutoModTriggerFlags
    ):
        """
        Create a saved trigger for use in automod Rules.

        - `<name>` The name of this trigger for reference later.
        Usage: `<trigger>`
        - `allows:` A space separated list of words to allow.
        - `keywords:` A space separated list of words to filter.
        - `mentions:` The number of user/role mentions that would trigger this rule (0-50).
        - `presets:` Any combination of discord presets. e.g. `profanity`, `sexual_content`, or `slurs`.
        - `regex:` A space separated list of regex patterns to include.
        Note: If you want to use `mentions` you cannot also use `presets`, `keywords` or
        `regex` in the same trigger. Likewise if you use any `presets` you cannot
        use `keywords`, `regex`, or `mentions`.
        Examples:
            `[p]automod create trigger mytrigger regex: ^b(a|@)dw(o|0)rd(s|5)$`
        """
        try:
            trigger.get_trigger()
        except ValueError as e:
            # d.py errors here are concise enough to explain the issue.
            await ctx.send(e)
            return
        name = name.lower()
        async with self.config.guild(ctx.guild).triggers() as triggers:
            if name in triggers:
                pred = ConfirmView(ctx.author)
                pred.message = await ctx.send(
                    f"A trigger with the name `{name}` already exists. Would you like to overwrite it?",
                    view=pred,
                )
                await pred.wait()
                if not pred.result:
                    await ctx.send("Please choose a different name then.")
                    return
            triggers[name] = trigger.to_json()
        await ctx.send(f"Saving trigger `{name}` with the following settings:\n{trigger.to_str()}")
