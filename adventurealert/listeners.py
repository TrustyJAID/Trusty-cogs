from enum import Enum
from typing import List

import discord
from redbot.core import Config, commands
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import humanize_list, pagify

from .abc import MixinMeta

_ = Translator("AdventureAlert", __file__)


class AlertTypes(Enum):
    adventure = "adventure"
    boss = "boss"
    cart = "cart"
    immortal = "immortal"
    miniboss = "miniboss"
    possessed = "possessed"
    ascended = "ascended"
    transcended = "transcended"

    def get_name(self):
        return {
            AlertTypes.adventure: _("Adventure"),
            AlertTypes.boss: _("Dragon"),
            AlertTypes.cart: _("Cart"),
            AlertTypes.immortal: _("Immortal"),
            AlertTypes.miniboss: _("Miniboss"),
            AlertTypes.possessed: _("Possessed"),
            AlertTypes.ascended: _("Ascended"),
            AlertTypes.transcended: _("Transcended"),
        }.get(self, _("Adventure"))

    def get_role_config(self, config: Config):
        if self is AlertTypes.boss:
            value = "roles"
        else:
            value = f"{self.name}_roles"
        return getattr(config, value)

    def get_user_config(self, config: Config):
        if self is AlertTypes.boss:
            value = "users"
        else:
            value = f"{self.name}_users"
        return getattr(config, value)

    def get_user_global_config(self, config: Config):
        return getattr(config, self.get_users_global())

    def get_users_global(self):
        if self is AlertTypes.boss:
            return "dragon"
        else:
            return self.name

    def get_message(self):
        return {
            AlertTypes.adventure: _("An adventure has started, come join!"),
            AlertTypes.boss: _("A Dragon has appeared!"),
            AlertTypes.cart: _("A cart has arrived, come buy something!"),
            AlertTypes.immortal: _("An immortal has appeared!"),
            AlertTypes.miniboss: _("A miniboss has appeared, come join!"),
            AlertTypes.possessed: _("A possessed has appeared!"),
            AlertTypes.ascended: _("An Ascended has appeared!"),
            AlertTypes.transcended: _("A Transcended has appeared!"),
        }.get(self, _("An adventure has started, come join!"))


class AlertTypeConverter(discord.app_commands.Transformer):
    async def convert(self, ctx: commands.Context, argument: str) -> AlertTypes:
        if argument.lower() == "dragon":
            return AlertTypes.boss
        try:
            return AlertTypes(argument.lower())
        except ValueError:
            raise commands.BadArgument(
                _("`{argument}` is not a valid alert type. Choose from {alerts}.").format(
                    argument=argument, alerts=humanize_list([i.name.title() for i in AlertTypes])
                )
            )

    async def transform(self, interaction: discord.Interaction, argument: str) -> AlertTypes:
        ctx = await interaction.client.get_context(interaction)
        return await self.convert(ctx, argument)

    async def autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> List[discord.app_commands.Choice]:
        choices = [
            discord.app_commands.Choice(name=i.name.title(), value=i.name) for i in AlertTypes
        ]
        choices.append(discord.app_commands.Choice(name="Dragon", value="boss"))
        return [i for i in choices if current.lower() in i.name.lower()]


class AdventureAlertListeners(MixinMeta):
    async def send_alert(
        self,
        ctx: commands.Context,
        style: AlertTypes,
    ):
        if await self.bot.cog_disabled_in_guild(self, ctx.guild):
            return
        if ctx.guild is None:
            return
        role_config = style.get_role_config(self.config.guild(ctx.guild))
        user_config = style.get_user_config(self.config.guild(ctx.guild))
        roles = set()
        users = set()
        for rid in await role_config():
            if role := ctx.guild.get_role(rid):
                roles.add(role.mention)
        for uid in await user_config():
            if user := ctx.guild.get_member(uid):
                users.add(user.mention)

        # guild_members = [m.id for m in ctx.guild.members]
        all_users = await self.config.all_users()

        for u_id, data in all_users.items():
            user = ctx.guild.get_member(u_id)
            if not user:
                continue
            if data.get(style.get_users_global(), False):
                users.add(user.mention)
        all_mentions = roles | users
        jump_url = ctx.message.jump_url
        if all_mentions:
            msg = f"{humanize_list(list(all_mentions))} " + f"[{style.get_message()}]({jump_url})"
            for page in pagify(msg):
                await ctx.channel.send(
                    page, allowed_mentions=discord.AllowedMentions(users=True, roles=True)
                )

    @commands.Cog.listener()
    async def on_adventure(self, ctx: commands.Context) -> None:
        await self.send_alert(ctx, AlertTypes.adventure)

    @commands.Cog.listener()
    async def on_adventure_boss(self, ctx: commands.Context) -> None:
        await self.send_alert(ctx, AlertTypes.boss)

    @commands.Cog.listener()
    async def on_adventure_transcended(self, ctx: commands.Context) -> None:
        await self.send_alert(ctx, AlertTypes.transcended)

    @commands.Cog.listener()
    async def on_adventure_possessed(self, ctx: commands.Context) -> None:
        await self.send_alert(ctx, AlertTypes.possessed)

    @commands.Cog.listener()
    async def on_adventure_miniboss(self, ctx: commands.Context) -> None:
        await self.send_alert(ctx, AlertTypes.miniboss)

    @commands.Cog.listener()
    async def on_adventure_immortal(self, ctx: commands.Context) -> None:
        await self.send_alert(ctx, AlertTypes.immortal)

    @commands.Cog.listener()
    async def on_adventure_cart(self, ctx: commands.Context) -> None:
        await self.send_alert(ctx, AlertTypes.cart)

    @commands.Cog.listener()
    async def on_adventure_ascended(self, ctx: commands.Context) -> None:
        await self.send_alert(ctx, AlertTypes.ascended)
