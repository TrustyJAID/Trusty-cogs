import logging
from typing import Literal, Optional

import discord
from discord import app_commands
from redbot.core.i18n import Translator

from .converter import DestinyActivity

log = logging.getLogger("red.trusty-cogs.destiny")
_ = Translator("Destiny", __file__)


class DestinySlash:

    search = app_commands.Group(
        name="search", description="Search for a destiny item, vendor, record, etc."
    )
    clan = app_commands.Group(name="clan", description="Clan settings")

    @app_commands.command(name="forgetme")
    async def forgetme_slash(self, interaction: discord.Interaction):
        """Remove your authorization to the Destiny API on this bot"""
        await self.forgetme(interaction)

    @app_commands.command(name="joinme")
    async def destiny_join_slash(self, interaction: discord.Interaction):
        """Get your Steam ID to give people to join your in-game fireteam"""
        await self.destiny_join_command(interaction)

    @app_commands.command(name="reset")
    async def destiny_reset_time_slash(self, interaction: discord.Interaction):
        """Show exactly when Weekly and Daily reset is"""
        await self.destiny_reset_time(interaction)

    @app_commands.command(name="user")
    async def user_slash(self, interaction: discord.Interaction, user: Optional[discord.Member]):
        """Display a menu of your basic character's info"""
        await self.user(interaction, user)

    @app_commands.command(name="whereisxur")
    async def whereisxur_slash(self, interaction: discord.Interaction):
        """Display Xûr's current location"""
        await self.whereisxur(interaction)

    @app_commands.command(name="xur")
    async def xur_slash(self, interaction: discord.Interaction, full: Optional[bool]):
        """Display a menu of Xûr's current wares"""
        await self.xur(interaction, full)

    @app_commands.command(name="rahool")
    async def rahool_slash(self, interaction: discord.Interaction):
        """Display Rahool's wares"""
        await self.rahool(interaction)

    @app_commands.command(name="banshee")
    async def banshee_slash(self, interaction: discord.Interaction):
        """Display Banshee-44's wares"""
        await self.banshee(interaction)

    @app_commands.command(name="ada-1")
    async def ada_1_slash(self, interaction: discord.Interaction):
        """Display Ada-1's wares"""
        await self.ada_1_inventory(interaction)

    @app_commands.command(name="loadout")
    async def loadout_slash(
        self,
        interaction: discord.Interaction,
        full: Optional[bool],
        user: Optional[discord.Member],
    ):
        """Display a menu of each character's equipped weapons and their info"""
        await self.loadout(interaction, full, user)

    @app_commands.command(name="stats")
    async def stats_slash(
        self,
        interaction: discord.Interaction,
        stat_type: Literal[
            "allpvp", "patrol", "raid", "story", "allstrikes", "allpve", "allPvECompetitive"
        ],
    ):
        """Display each character's stats for a specific activity"""
        await self.stats(interaction, stat_type)

    @app_commands.command(name="history")
    async def history_slash(self, interaction: discord.Interaction, activity: str):
        """Display a menu of each character's last 5 activities"""
        await self.history(interaction, activity)

    @app_commands.command(name="eververse")
    @app_commands.choices(
        item_types=[
            app_commands.Choice(name="consumable", value=9),
            app_commands.Choice(name="ship", value=21),
            app_commands.Choice(name="vehicle", value=22),
            app_commands.Choice(name="ghost", value=24),
            app_commands.Choice(name="finisher", value=29),
        ]
    )
    async def eververse_slash(
        self, interaction: discord.Interaction, item_types: Optional[app_commands.Choice[int]]
    ):
        await self.eververse(interaction, item_types=item_types)

    @search.command(name="item")
    async def items_slash(
        self,
        interaction: discord.Interaction,
        details_or_lore: Optional[app_commands.Choice[str]],
        search: str,
    ):
        """Search for a specific item in Destiny 2"""
        await self.items(interaction, details_or_lore, search=search)

    @search.command(name="lore")
    async def lore_slash(self, interaction: discord.Interaction, entry: Optional[str]):
        await self.lore(interaction, entry)

    @clan.command(name="info")
    async def show_clan_info_slash(self, interaction: discord.Interaction, clan_id: Optional[str]):
        """Display basic informaition about a clan in this server"""
        await self.show_clan_info(interaction, clan_id)

    # @clan.command(name="set")
    async def set_clan_id_slash(self, interaction: discord.Interaction, clan_id: str):
        """Set the clan ID for this server"""
        await self.show_clan_info(interaction, clan_id)
        # disabled until permissions v2

    # @clan.command(name="pending")
    async def clan_pending_slash(self, interaction: discord.Interaction):
        """Display pending clan members."""
        await self.clan_pending(interaction)
        # disabled until permissions v2

    @clan.command(name="roster")
    async def get_clan_roster(
        self, interaction: discord.Interaction, output_format: Optional[Literal["csv", "md"]]
    ):
        """Get the full clan roster"""
        await self.get_clan_roster(interaction, output_format)

    @history_slash.autocomplete("activity")
    async def parse_history(self, interaction: discord.Interaction, current: str):
        possible_options = [
            app_commands.Choice(name=i["name"], value=i["value"]) for i in DestinyActivity.CHOICES
        ]
        choices = []
        for choice in possible_options:
            if current.lower() in choice.name.lower():
                choices.append(app_commands.Choice(name=choice.name, value=choice.value))
        return choices[:25]

    @items_slash.autocomplete("search")
    async def parse_search_items(self, interaction: discord.Interaction, current: str):
        possible_options = await self.search_definition("simpleitems", current)
        choices = []
        for hash_key, data in possible_options.items():
            name = data["displayProperties"]["name"]
            if name:
                choices.append(app_commands.Choice(name=name, value=hash_key))
        return choices[:25]

    @lore_slash.autocomplete("entry")
    async def parse_search_lore(self, interaction: discord.Interaction, current: str):
        possible_options = self.get_entities("DestinyLoreDefinition")
        choices = []
        for hash_key, data in possible_options.items():
            name = data["displayProperties"]["name"]
            if current.lower() in name.lower():
                choices.append(app_commands.Choice(name=name, value=name))
        log.debug(len(choices))
        return choices[:25]

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not await self.bot.allowed_by_whitelist_blacklist(interaction.user):
            await interaction.response.send_message(
                _("You are not allowed to run this command here."), ephemeral=True
            )
            return False
        fake_ctx = discord.Object(id=interaction.id)
        fake_ctx.author = interaction.user
        fake_ctx.guild = interaction.guild
        if isinstance(interaction.channel, discord.channel.PartialMessageable):
            channel = interaction.user.dm_channel or await interaction.user.create_dm()
        else:
            channel = interaction.channel

        fake_ctx.channel = channel
        if not await self.bot.ignored_channel_or_guild(fake_ctx):
            await interaction.response.send_message(
                _("Commands are not allowed in this channel or guild."), ephemeral=True
            )
            return False
        return True
