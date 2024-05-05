from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, List, Optional

import discord
from red_commons.logging import getLogger

# from discord.ext.commands.errors import BadArgument
from redbot.core.commands import commands
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import bold, humanize_list
from redbot.vendored.discord.ext import menus

from .converter import BungieTweet, NewsArticle, NewsArticles
from .errors import Destiny2APIError

BASE_URL = "https://bungie.net"


log = getLogger("red.Trusty-cogs.destiny")
_ = Translator("Destiny", __file__)


class YesNoView(discord.ui.View):
    def __init__(self):
        super().__init__()
        self.result: Optional[bool] = None
        self.message: discord.Message

    async def on_timeout(self):
        if self.message is not None:
            await self.message.edit(view=None)

    async def start(self, ctx: commands.Context, content: str):
        self.message = await ctx.send(content, view=self)
        await self.wait()
        return self.result

    @discord.ui.button(label="Yes", style=discord.ButtonStyle.green)
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(view=None)
        self.result = True
        self.stop()

    @discord.ui.button(label="No", style=discord.ButtonStyle.red)
    async def deny(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(view=None)
        self.result = False
        self.stop()


class ClanPendingButton(discord.ui.Button):
    def __init__(
        self,
        clan_id: int,
        bnet_member: dict,
    ):
        self.member_id = bnet_member["destinyUserInfo"]["membershipId"]
        self.membership_type = bnet_member["destinyUserInfo"]["membershipType"]
        self.clan_id = clan_id
        self.bnet_member = bnet_member
        bungie_name = bnet_member["destinyUserInfo"].get("bungieGlobalDisplayName", "")
        bungie_name_code = bnet_member["destinyUserInfo"].get("bungieGlobalDisplayNameCode", "")
        self.bnet_name = f"{bungie_name}#{bungie_name_code}"
        super().__init__(style=discord.ButtonStyle.primary, label=self.bnet_name)

    async def callback(self, interaction: discord.Interaction):
        pred = YesNoView()
        await interaction.response.send_message(
            _("Are you sure you want to approve {bnet_name} into the clan?").format(
                bnet_name=self.bnet_name
            ),
            view=pred,
            ephemeral=True,
        )
        await pred.wait()
        if pred.result:
            try:
                await self.view.cog.api.approve_clan_pending(
                    interaction.user,
                    self.clan_id,
                    self.membership_type,
                    self.member_id,
                    self.bnet_member,
                )
            except Destiny2APIError as e:
                log.exception("error approving clan member.")
                await interaction.followup.send(str(e))
            else:
                user = f"[{self.bnet_name}](<https://www.bungie.net/7/en/User/Profile/{self.membership_type}/{self.member_id}>)"
                await interaction.followup.send(
                    _("{user} has been approved into the clan.").format(user=user)
                )
                self.disabled = True
                await self.view.message.edit(view=self.view)


class ClanPendingView(discord.ui.View):
    def __init__(
        self, cog: commands.Cog, ctx: commands.Context, clan_id: int, pending_users: list
    ):
        super().__init__()
        self.pending_users = pending_users
        self.cog = cog
        self.ctx = ctx
        self.clan_id = clan_id
        self.message = None
        for m in self.pending_users[:25]:
            self.add_item(ClanPendingButton(clan_id, m))

    async def start(self):
        embed = discord.Embed(
            title=_("Pending Clan Members"),
        )
        description = ""
        for index, user in enumerate(self.pending_users[:25]):
            bungie_info = user.get("destinyUserInfo")
            bungie_name = bungie_info.get("bungieGlobalDisplayName", "")
            bungie_name_code = bungie_info.get("bungieGlobalDisplayNameCode", "")
            bungie_name_and_code = f"{bungie_name}#{bungie_name_code}"
            bungie_id = bungie_info.get("membershipId")
            platform = bungie_info.get("membershipType")
            msg = f"[{bungie_name_and_code}](https://www.bungie.net/7/en/User/Profile/{platform}/{bungie_id})"
            description += msg + "\n"
        embed.description = description
        self.message = await self.ctx.send(embed=embed, view=self)


class BasePages(menus.ListPageSource):
    def __init__(self, pages: list, use_author: bool = False):
        super().__init__(pages, per_page=1)
        self.pages = pages
        self.select_options = []
        for count, page in enumerate(pages):
            self.select_options.append(
                discord.SelectOption(
                    label=_("Page {number}").format(number=count + 1),
                    value=count,
                    description=page.title[:50] if not use_author else page.author.name[:50],
                )
            )

    def is_paginating(self):
        return True

    async def format_page(self, menu: menus.MenuPages, page):
        page.set_footer(text=f"Page {menu.current_page + 1}/{self.get_max_pages()}")
        return page


class VaultPages(menus.ListPageSource):
    def __init__(self, pages: list, cog: commands.Cog):
        super().__init__(pages, per_page=1)
        self.pages = pages
        self.select_options = []
        self.cog = cog
        self.current_item_hash = None
        self.current_item_instance = None

        for count, page in enumerate(pages):
            self.select_options.append(
                discord.SelectOption(
                    label=_("Page {number}").format(number=count + 1),
                    value=count,
                    description="figure out how to get the gun name here",
                )
            )

    def is_paginating(self):
        return True

    async def format_page(self, menu: menus.MenuPages, page):
        self.current_item_hash = page["itemHash"]
        self.current_item_instance = page.get("itemInstanceId", None)
        items = await self.cog.api.get_definition(
            "DestinyInventoryItemDefinition", [self.current_item_hash]
        )
        item_data = items[str(self.current_item_hash)]
        embed = discord.Embed(
            title=item_data.get("displayProperties", {"name": "None"}).get("name")
        )
        if "displayProperties" in item_data:
            embed.set_thumbnail(url=BASE_URL + item_data["displayProperties"]["icon"])
        if item_data.get("screenshot", None):
            embed.set_image(url=BASE_URL + item_data["screenshot"])
        if self.current_item_instance is not None:
            instance_data = await self.cog.api.get_instanced_item(
                menu.author, self.current_item_instance
            )
            perk_hashes = [i["perkHash"] for i in instance_data["perks"]["data"]["perks"]]
            perk_info = await self.cog.api.get_definition(
                "DestinyInventoryItemDefinition", perk_hashes
            )
            perk_str = "\n".join(perk["displayProperties"]["name"] for perk in perk_info.values())
            embed.description = perk_str

        embed.set_footer(text=f"Page {menu.current_page + 1}/{self.get_max_pages()}")
        return embed


class StopButton(discord.ui.Button):
    def __init__(
        self,
        style: discord.ButtonStyle,
        row: Optional[int],
    ):
        super().__init__(style=style, row=row)
        self.style = style
        self.emoji = "\N{HEAVY MULTIPLICATION X}\N{VARIATION SELECTOR-16}"

    async def callback(self, interaction: discord.Interaction):
        self.view.stop()
        if interaction.message.flags.ephemeral:
            await interaction.response.edit_message(view=None)
            return
        await interaction.message.delete()


class ForwardButton(discord.ui.Button):
    def __init__(
        self,
        style: discord.ButtonStyle,
        row: Optional[int],
    ):
        super().__init__(style=style, row=row)
        self.style = style
        self.emoji = "\N{BLACK RIGHT-POINTING TRIANGLE}\N{VARIATION SELECTOR-16}"

    async def callback(self, interaction: discord.Interaction):
        await self.view.show_checked_page(self.view.current_page + 1, interaction)


class BackButton(discord.ui.Button):
    def __init__(
        self,
        style: discord.ButtonStyle,
        row: Optional[int],
    ):
        super().__init__(style=style, row=row)
        self.style = style
        self.emoji = "\N{BLACK LEFT-POINTING TRIANGLE}\N{VARIATION SELECTOR-16}"

    async def callback(self, interaction: discord.Interaction):
        await self.view.show_checked_page(self.view.current_page - 1, interaction)


class LastItemButton(discord.ui.Button):
    def __init__(
        self,
        style: discord.ButtonStyle,
        row: Optional[int],
    ):
        super().__init__(style=style, row=row)
        self.style = style
        self.emoji = (
            "\N{BLACK RIGHT-POINTING DOUBLE TRIANGLE WITH VERTICAL BAR}\N{VARIATION SELECTOR-16}"
        )

    async def callback(self, interaction: discord.Interaction):
        await self.view.show_page(self.view._source.get_max_pages() - 1, interaction)


class FirstItemButton(discord.ui.Button):
    def __init__(
        self,
        style: discord.ButtonStyle,
        row: Optional[int],
    ):
        super().__init__(style=style, row=row)
        self.style = style
        self.emoji = (
            "\N{BLACK LEFT-POINTING DOUBLE TRIANGLE WITH VERTICAL BAR}\N{VARIATION SELECTOR-16}"
        )

    async def callback(self, interaction: discord.Interaction):
        await self.view.show_page(0, interaction)


class DestinySelect(discord.ui.Select):
    def __init__(self, options: List[discord.SelectOption]):
        super().__init__(min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        index = int(self.values[0])
        await self.view.show_checked_page(index, interaction)


class DestinyEquipLoadout(discord.ui.Button):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.green, label=_("Equip"))

    async def callback(self, interaction: discord.Interaction):
        try:
            membership_type = self.view.source.membership_type
            character_id = self.view.source.character
            index = self.view.source.current_index
            await self.view.cog.api.equip_loadout(
                interaction.user,
                index,
                character_id,
                membership_type,
            )
            loadout_name = self.view.source.pages[index].title
            await interaction.response.send_message(
                _("Equipping {name} loadout.").format(name=loadout_name)
            )
        except Exception:
            await interaction.response.send_message(
                _("There was an error equipping that loadout.")
            )
            return


class DestinyCharacterSelect(discord.ui.Select):
    def __init__(self, options: List[discord.SelectOption]):
        super().__init__(
            min_values=1, max_values=1, options=options, placeholder=_("Select a Character")
        )

    async def callback(self, interaction: discord.Interaction):
        index = self.values[0]
        new_source = LoadoutPages(self.view.source.loadout_info, index)
        self.view._source = new_source
        self.view.remove_item(self.view.select_view)
        self.view.select_view = self.view._get_select_menu()
        self.view.add_item(self.view.select_view)
        await self.view.show_checked_page(0, interaction)


class PostmasterSelect(discord.ui.Select):
    def __init__(self, items: dict):
        self.items = items
        super().__init__(max_values=len(items["items"]), placeholder=_("Pull from Postmaster"))
        for item in items["items"]:
            item_hash = item["itemHash"]
            item_name = items["data"][str(item_hash)]["displayProperties"]["name"]
            description = None
            if item["quantity"] > 1:
                description = str(item["quantity"]) + "x"
            instance = item.get("itemInstanceId", "")
            value = f"{instance}-{item_hash}"
            self.add_option(label=item_name, description=description, value=value)

    def get_quantity(self, instance: str, item_hash: str) -> int:
        possible_item = None
        for item in self.items["items"]:
            if str(item["itemHash"]) == item_hash:
                possible_item = item
            if "itemInstanceId" in item and str(item["itemInstanceId"]) == instance:
                possible_item = item
        if possible_item and "quantity" in possible_item:
            return possible_item["quantity"]
        return 1

    async def callback(self, interaction: discord.Interaction):
        items = []
        errors = []
        for v in self.values:
            instance, item_hash = v.split("-")
            item = self.items["data"].get(item_hash)
            char_id = self.items["characterId"]
            membership_type = self.items["membershipType"]
            quantity = self.get_quantity(instance, item_hash)
            item_name = item["displayProperties"]["name"]
            url = f"https://www.light.gg/db/items/{item_hash}"
            try:
                await self.view.cog.api.pull_from_postmaster(
                    interaction.user, item_hash, char_id, membership_type, quantity, instance
                )
                self.view.source.remove_item(char_id, item_hash, instance)
                items.append(f"{quantity}x [{item_name}](<{url}>)")
            except Destiny2APIError as e:
                log.exception(e)
                errors.append(f"{quantity}x [{item_name}](<{url}>) - {e}")
                continue
        if items:
            msg = _("Transferring {items} from the postmaster.").format(items=humanize_list(items))
            if interaction.response.is_done():
                await interaction.followup.send(msg)
            else:
                await interaction.response.send_message(msg)
        if errors:
            msg = _(
                "Some of the items selected could not be pulled from the postmaster.\n{errors}"
            ).format(errors="\n".join(e for e in errors))
            if interaction.response.is_done():
                await interaction.followup.send(msg)
            else:
                await interaction.response.send_message(msg)
        await self.view.show_page(self.view.current_page, interaction)


class PostmasterPages(menus.ListPageSource):
    def __init__(self, postmasters: dict):
        self.select_options = []
        for count, page in enumerate(postmasters.values()):
            if page["embed"].author:
                description = page["embed"].author.name[:50]
            else:
                description = page["embed"].title[:50]
            self.select_options.append(
                discord.SelectOption(
                    label=_("Page {number}").format(number=count + 1),
                    value=count,
                    description=description,
                )
            )
        super().__init__(list(postmasters.keys()), per_page=1)
        self.postmasters = postmasters
        self.current_select = None
        self.current_char = None
        self.pages = list(postmasters.keys())

    def remove_item(self, char_id: int, item_hash: str, instance: Optional[str]):
        to_rem = []
        for item in self.postmasters[char_id]["items"]:
            possible_item = None
            if str(item["itemHash"]) == item_hash:
                possible_item = item
            if "itemInstanceId" in item and str(item["itemInstanceId"]) == instance:
                possible_item = item
            if possible_item:
                to_rem.append(possible_item)
        for rem in to_rem:
            try:
                self.postmasters[char_id]["items"].remove(rem)
            except Exception:
                pass

    async def format_page(self, menu: menus.MenuPages, page: int):
        log.trace("PostmasterPages %s", page)
        self.current_char = page
        self.current_select = PostmasterSelect(self.postmasters[page])
        msg = ""
        for item in self.postmasters[page]["items"]:
            item_data = self.postmasters[page]["data"].get(str(item["itemHash"]))
            item_hash = str(item["itemHash"])
            url = f"https://www.light.gg/db/items/{item_hash}"
            item_name = item_data["displayProperties"]["name"]
            quantity = ""
            if item["quantity"] > 1:
                quantity = bold(str(item["quantity"]) + "x ")
            msg += f"{quantity}[{item_name}]({url})\n"
        embed = self.postmasters[page]["embed"]
        embed.description = msg[:4096]
        embed.set_footer(text=f"Page {menu.current_page + 1}/{self.get_max_pages()}")
        return embed


class LoadoutPages(menus.ListPageSource):
    def __init__(self, loadout_info: dict, char_id: Optional[int] = None):
        self.loadout_info = loadout_info
        self.character = str(char_id)
        self.membership_type = loadout_info.get("membership_type")
        if char_id is None or str(char_id) not in self.loadout_info:
            for key in loadout_info.keys():
                if not key.isdigit():
                    continue
                self.character = str(key)
                break
        super().__init__(loadout_info[self.character]["embeds"], per_page=1)
        self.pages = list(loadout_info[self.character]["embeds"])
        self.select_options = []
        for index, page in enumerate(self.pages):
            self.select_options.append(
                discord.SelectOption(
                    label=f"{index+1}. {page.title}", value=index, description=page.description
                )
            )
        self.current_index = 0

    async def format_page(self, menu: menus.MenuPages, page: discord.Embed):
        self.current_index = self.pages.index(page)
        return page


class BungieNewsSource(menus.ListPageSource):
    def __init__(self, news_pages: NewsArticles):
        self.pages = news_pages.NewsArticles
        super().__init__(self.pages, per_page=1)
        self.select_options = []
        for index, page in enumerate(self.pages):
            self.select_options.append(
                discord.SelectOption(
                    label=page.Title[:100], description=page.Description[:100], value=str(index)
                )
            )

    async def format_page(self, menu: Optional[BaseMenu], page: NewsArticle):
        link = page.Link
        time = page.pubdate()
        url = f"{BASE_URL}{link}"
        embed = discord.Embed(
            title=page.Title,
            url=url,
            description=page.Description,
            timestamp=time,
        )
        embed.set_image(url=page.ImagePath)
        # time = datetime.fromisoformat(page["PubDate"])
        # embed.add_field(name=_("Published"), value=discord.utils.format_dt(time, style="R"))

        return {"content": url, "embed": embed}


class BungieTweetsSource(menus.ListPageSource):
    def __init__(self, tweets: List[BungieTweet]):
        self.pages = tweets
        super().__init__(self.pages, per_page=1)
        self.select_options = []
        for index, page in enumerate(self.pages):
            self.select_options.append(
                discord.SelectOption(label=page.text[:100], value=str(index))
            )

    async def format_page(self, menu: Optional[BaseMenu], page: BungieTweet):
        return {"content": page.url}


class BaseMenu(discord.ui.View):
    def __init__(
        self,
        source: menus.PageSource,
        cog: commands.Cog,
        clear_reactions_after: bool = True,
        delete_message_after: bool = False,
        timeout: int = 180,
        message: discord.Message = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            timeout=timeout,
        )
        self.cog = cog
        self.message = message
        self._source = source
        self.ctx = None
        self.current_page = kwargs.get("page_start", 0)
        self.forward_button = ForwardButton(discord.ButtonStyle.grey, 0)
        self.back_button = BackButton(discord.ButtonStyle.grey, 0)
        self.first_item = FirstItemButton(discord.ButtonStyle.grey, 0)
        self.last_item = LastItemButton(discord.ButtonStyle.grey, 0)
        self.stop_button = StopButton(discord.ButtonStyle.red, 0)
        self.add_item(self.stop_button)
        self.add_item(self.first_item)
        self.add_item(self.back_button)
        self.add_item(self.forward_button)
        self.add_item(self.last_item)
        self.postmaster = None
        if isinstance(self._source, LoadoutPages):
            self.equip_button = DestinyEquipLoadout()
            self.add_item(self.equip_button)
            options = []
            for char_id, info in self._source.loadout_info.items():
                if not char_id.isdigit():
                    continue
                options.append(discord.SelectOption(label=info["char_info"], value=char_id))
            self.char_select = DestinyCharacterSelect(options)
            self.add_item(self.char_select)
        if hasattr(self.source, "select_options"):
            self.select_view = self._get_select_menu()
            self.add_item(self.select_view)
        self.author = None

    @property
    def source(self):
        return self._source

    async def on_timeout(self):
        await self.message.edit(view=None)

    async def start(self, ctx: commands.Context):
        self.ctx = ctx
        # await self.source._prepare_once()
        self.message = await self.send_initial_message(ctx)

    def check_disabled_buttons(self):
        if len(self._source.entries) == 1:
            self.first_item.disabled = True
            self.last_item.disabled = True
            self.back_button.disabled = True
            self.forward_button.disabled = True
            if hasattr(self.source, "select_options"):
                self.select_view.disabled = True
        else:
            self.first_item.disabled = False
            self.last_item.disabled = False
            self.back_button.disabled = False
            self.forward_button.disabled = False
            if hasattr(self.source, "select_options"):
                self.select_view.disabled = False

    def _get_select_menu(self) -> Optional[DestinySelect]:
        # handles modifying the select menu if more than 25 pages are provided
        # this will show the previous 12 and next 13 pages in the select menu
        # based on the currently displayed page. Once you reach close to the max
        # pages it will display the last 25 pages.
        if not hasattr(self.source, "select_options"):
            return None
        if len(self.source.select_options) > 25:
            minus_diff = None
            plus_diff = 25
            if 12 < self.current_page < len(self.source.select_options) - 25:
                minus_diff = self.current_page - 12
                plus_diff = self.current_page + 13
            elif self.current_page >= len(self.source.select_options) - 25:
                minus_diff = len(self.source.select_options) - 25
                plus_diff = None
            options = self.source.select_options[minus_diff:plus_diff]
        else:
            options = self.source.select_options[:25]
        return DestinySelect(options)

    async def _get_kwargs_from_page(self, page):
        value = await discord.utils.maybe_coroutine(self._source.format_page, self, page)
        self.check_disabled_buttons()
        if isinstance(value, dict):
            return value
        elif isinstance(value, str):
            return {"content": value, "embed": None}
        elif isinstance(value, discord.Embed):
            return {"embed": value, "content": None}

    async def send_initial_message(self, ctx: commands.Context):
        """|coro|
        The default implementation of :meth:`Menu.send_initial_message`
        for the interactive pagination session.
        This implementation shows the first page of the source.
        """

        page = await self._source.get_page(self.current_page)
        kwargs = await self._get_kwargs_from_page(page)
        if isinstance(self.source, PostmasterPages) and self.source.current_select:
            self.postmaster = self.source.current_select
            self.add_item(self.source.current_select)
        self.message = await ctx.send(**kwargs, view=self)
        self.author = ctx.author
        return self.message

    async def show_page(self, page_number: int, interaction: discord.Interaction):
        if isinstance(self.source, PostmasterPages):
            self.remove_item(self.postmaster)
        page = await self._source.get_page(page_number)
        if hasattr(self.source, "select_options") and page_number >= 12:
            self.remove_item(self.select_view)
            self.select_view = self._get_select_menu()
            self.add_item(self.select_view)
        self.current_page = self.source.pages.index(page)
        kwargs = await self._get_kwargs_from_page(page)
        if isinstance(self.source, PostmasterPages):
            self.postmaster = self.source.current_select
            self.add_item(self.source.current_select)

        if interaction.response.is_done():
            await self.message.edit(**kwargs, view=self)
        else:
            await interaction.response.edit_message(**kwargs, view=self)

    async def show_checked_page(self, page_number: int, interaction: discord.Interaction) -> None:
        max_pages = self._source.get_max_pages()
        try:
            if max_pages is None:
                # If it doesn't give maximum pages, it cannot be checked
                await self.show_page(page_number, interaction)
            elif page_number >= max_pages:
                await self.show_page(0, interaction)
            elif page_number < 0:
                await self.show_page(max_pages - 1, interaction)
            elif max_pages > page_number >= 0:
                await self.show_page(page_number, interaction)
        except IndexError:
            # An error happened that can be handled, so ignore it.
            pass

    async def interaction_check(self, interaction: discord.Interaction):
        """Just extends the default reaction_check to use owner_ids"""
        if interaction.user.id not in (self.author.id,):
            await interaction.response.send_message(
                content=_("You are not authorized to interact with this."), ephemeral=True
            )
            return False
        return True
