import asyncio
import datetime
import logging
import re
from typing import Dict, Optional, Union

import aiohttp
import discord
from redbot.core import Config, VersionInfo, commands, version_info

log = logging.getLogger("red.trusty-cogs.conversions")


class Conversions(commands.Cog):
    """
    Gather information about various crypto currencies,
    rare metals, stocks, and converts to different currencies
    """

    __author__ = ["TrustyJAID"]
    __version__ = "1.1.2"

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=239232811662311425)
        self.config.register_global(version="0.0.0")
        self.bot.loop.create_task(self.init())
        self._ready = asyncio.Event()

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

    async def cog_before_invoke(self, ctx: commands.Context) -> None:
        await self._ready.wait()

    async def init(self):
        if version_info >= VersionInfo.from_str("3.2.0"):
            await self.bot.wait_until_red_ready()
        else:
            await self.bot.wait_until_ready()
        try:
            if await self.config.version() < "1.1.0":
                prefixes = await self.bot.get_valid_prefixes()
                prefix = re.sub(rf"<@!?{self.bot.user.id}>", f"@{self.bot.user.name}", prefixes[0])
                msg = (
                    "The Conversions cog is now using a couple of API's "
                    "that require API keys. Please use `{prefix}stockapi` "
                    "to continue using the stock, gold, etc. commands. "
                    "Please use `{prefix}cryptoapi` to continue using "
                    "the cryptocurrency commands."
                ).format(prefix=prefix)
                self.bot.loop.create_task(self.bot.send_to_owners(msg))
                await self.config.version.set("1.1.0")
        except Exception:
            log.exception("There was an exception loading the cog.", exec_info=True)
        else:
            self._ready.set()

    @commands.command(aliases=["bitcoin", "BTC"])
    async def btc(
        self,
        ctx: commands.Context,
        ammount: float = 1.0,
        currency: str = "USD",
        full: bool = True,
    ) -> None:
        """
        converts from BTC to a given currency.

        `[ammount]` is any number to convert the value of defaults to 1 coin
        `[currency]` is the desired currency you want to convert defaults to USD
        `[full]` is a True/False value whether to display just the converted amount
        or the full display for the currency
        """
        if ammount == 1.0:
            embed = await self.crypto_embed(ctx, "BTC", ammount, currency, full)
        else:
            embed = await self.crypto_embed(ctx, "BTC", ammount, currency, False)
        if not embed:
            return
        if type(embed) is str:
            await ctx.send(embed)
        else:
            await ctx.send(embed=embed)

    @commands.command(aliases=["ethereum", "ETH"])
    async def eth(
        self,
        ctx: commands.Context,
        ammount: float = 1.0,
        currency: str = "USD",
        full: bool = True,
    ) -> None:
        """
        converts from ETH to a given currency.

        `[ammount]` is any number to convert the value of defaults to 1 coin
        `[currency]` is the desired currency you want to convert defaults to USD
        `[full]` is a True/False value whether to display just the converted amount
        or the full display for the currency
        """
        if ammount == 1.0:
            embed = await self.crypto_embed(ctx, "ETH", ammount, currency, full)
        else:
            embed = await self.crypto_embed(ctx, "ETH", ammount, currency, False)
        if not embed:
            return
        if type(embed) is str:
            await ctx.send(embed)
        else:
            await ctx.send(embed=embed)

    @commands.command(aliases=["litecoin", "LTC"])
    async def ltc(
        self,
        ctx: commands.Context,
        ammount: float = 1.0,
        currency: str = "USD",
        full: bool = True,
    ) -> None:
        """
        converts from LTC to a given currency.

        `[ammount]` is any number to convert the value of defaults to 1 coin
        `[currency]` is the desired currency you want to convert defaults to USD
        `[full]` is a True/False value whether to display just the converted amount
        or the full display for the currency
        """
        if ammount == 1.0:
            embed = await self.crypto_embed(ctx, "LTC", ammount, currency, full)
        else:
            embed = await self.crypto_embed(ctx, "LTC", ammount, currency, False)
        if not embed:
            return
        if type(embed) is str:
            await ctx.send(embed)
        else:
            await ctx.send(embed=embed)

    @commands.command(aliases=["monero", "XMR"])
    async def xmr(
        self,
        ctx: commands.Context,
        ammount: float = 1.0,
        currency: str = "USD",
        full: bool = True,
    ) -> None:
        """
        converts from XMR to a given currency.

        `[ammount]` is any number to convert the value of defaults to 1 coin
        `[currency]` is the desired currency you want to convert defaults to USD
        `[full]` is a True/False value whether to display just the converted amount
        or the full display for the currency
        """
        if ammount == 1.0:
            embed = await self.crypto_embed(ctx, "XMR", ammount, currency, full)
        else:
            embed = await self.crypto_embed(ctx, "XMR", ammount, currency, False)
        if not embed:
            return
        if type(embed) is str:
            await ctx.send(embed)
        else:
            await ctx.send(embed=embed)

    async def get_header(self) -> Optional[Dict[str, str]]:
        api_key = (await self.bot.get_shared_api_tokens("coinmarketcap")).get("api_key")
        if api_key:
            return {"X-CMC_PRO_API_KEY": api_key}
        else:
            return None

    @commands.command(aliases=["bitcoin-cash", "BCH"])
    async def bch(
        self,
        ctx: commands.Context,
        ammount: float = 1.0,
        currency: str = "USD",
        full: bool = True,
    ) -> None:
        """
        converts from BCH to a given currency.

        `[ammount]` is any number to convert the value of defaults to 1 coin
        `[currency]` is the desired currency you want to convert defaults to USD
        `[full]` is a True/False value whether to display just the converted amount
        or the full display for the currency
        """
        if ammount == 1.0:
            embed = await self.crypto_embed(ctx, "BCH", ammount, currency, full)
        else:
            embed = await self.crypto_embed(ctx, "BCH", ammount, currency, False)
        if not embed:
            return
        if type(embed) is str:
            await ctx.send(embed)
        else:
            await ctx.send(embed=embed)

    async def checkcoins(self, base: str) -> dict:
        url = "https://pro-api.coinmarketcap.com/v1/cryptocurrency/listings/latest"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=await self.get_header()) as resp:
                data = await resp.json()
                if resp.status in [400, 401, 403, 429, 500]:
                    return data
        for coin in data["data"]:
            if base.upper() == coin["symbol"].upper() or base.lower() == coin["name"].lower():
                return coin
        return {}

    @commands.command()
    async def multicoin(self, ctx: commands.Context, *, coins: Optional[str] = None) -> None:
        """
        Gets the current USD value for a list of coins

        `coins` must be a list of white space separated crypto coins
        e.g. `[p]multicoin BTC BCH LTC ETH DASH XRP`
        """
        coin_list = []
        if coins is None:
            async with aiohttp.ClientSession() as session:
                url = "https://pro-api.coinmarketcap.com/v1/cryptocurrency/listings/latest"
                async with session.get(url, headers=await self.get_header()) as resp:
                    data = await resp.json()
                    if resp.status in [400, 403, 429, 500]:
                        await ctx.send(
                            "Something went wrong, the error code is "
                            "{code}\n`{error_message}`".format(
                                code=resp.status, error_message=data["error_message"]
                            )
                        )
                        return
                    if resp.status == 401:
                        await ctx.send(
                            "The bot owner has not set an API key. "
                            "Please use `{prefix}cryptoapi` to see "
                            "how to create and setup an API key.".format(prefix=ctx.clean_prefix)
                        )
                        return
            for coin in data["data"]:
                coin_list.append(coin)
        else:
            coins = re.split(r"\W+", coins)
            for coin in coins:
                coin_list.append(await self.checkcoins(coin))
        embed = discord.Embed(title="Crypto coin comparison")
        if ctx.channel.permissions_for(ctx.me).embed_links:
            for coin in coin_list[:25]:
                if coin is not None:
                    msg = "1 {0} is {1:,.2f} USD".format(
                        coin["symbol"], float(coin["quote"]["USD"]["price"])
                    )
                    embed.add_field(name=coin["name"], value=msg)
            await ctx.send(embed=embed)
        else:
            msg = ""
            for coin in coin_list[:25]:
                if coin is not None:
                    msg += "1 {0} is {1:,.2f} USD\n".format(
                        coin["symbol"], float(coin["quotes"]["USD"]["price"])
                    )
            await ctx.send(msg)

    @commands.command()
    async def crypto(
        self,
        ctx: commands.Context,
        coin: str,
        ammount: float = 1.0,
        currency: str = "USD",
        full: bool = True,
    ) -> None:
        """
        Displays the latest information about a specified crypto currency

        `coin` must be the name or symbol of a crypto coin
        `[ammount]` is any number to convert the value of defaults to 1 coin
        `[currency]` is the desired currency you want to convert defaults to USD
        `[full]` is a True/False value whether to display just the converted amount
        or the full display for the currency
        """
        if ammount == 1.0:
            embed = await self.crypto_embed(ctx, coin, ammount, currency, full)
        else:
            embed = await self.crypto_embed(ctx, coin, ammount, currency, False)
        if not embed:
            return
        if type(embed) is str:
            await ctx.send(embed)
        else:
            await ctx.send(embed=embed)

    async def crypto_embed(
        self,
        ctx: commands.Context,
        coin: str,
        ammount: float = 1.0,
        currency: str = "USD",
        full: bool = True,
    ) -> Optional[Union[str, discord.Embed]]:
        """Creates the embed for the crypto currency"""
        coin_data = await self.checkcoins(coin)
        if "status" in coin_data:
            status = coin_data["status"]
            if status["error_code"] in [1003, 1004, 1005, 1006, 1007, 1008, 1009, 1010, 1011]:
                await ctx.send(
                    "Something went wrong, the error code is "
                    "{code}\n`{error_message}`".format(
                        code=coin["error_code"], error_message=coin["error_message"]
                    )
                )
                return None
            if status["error_code"] in [1001, 1002]:
                await ctx.send(
                    "The bot owner has not set an API key. "
                    "Please use `{prefix}cryptoapi` to see "
                    "how to create and setup an API key.".format(prefix=ctx.clean_prefix)
                )
                return None
        if coin_data == {}:
            await ctx.send("{} is not in my list of currencies!".format(coin))
            return None
        coin_colour = {
            "Bitcoin": discord.Colour.gold(),
            "Bitcoin Cash": discord.Colour.orange(),
            "Ethereum": discord.Colour.dark_grey(),
            "Litecoin": discord.Colour.dark_grey(),
            "Monero": discord.Colour.orange(),
        }
        price = float(coin_data["quote"]["USD"]["price"]) * ammount
        market_cap = float(coin_data["quote"]["USD"]["market_cap"])
        volume_24h = float(coin_data["quote"]["USD"]["volume_24h"])
        coin_image = "https://s2.coinmarketcap.com/static/img/coins/128x128/{}.png".format(
            coin_data["id"]
        )
        coin_url = "https://coinmarketcap.com/currencies/{}".format(coin_data["id"])
        if currency.upper() != "USD":
            conversionrate = await self.conversionrate("USD", currency.upper())
            if conversionrate:
                price = conversionrate * price
                market_cap = conversionrate * market_cap
                volume_24h = conversionrate * volume_24h
        msg = "{0} {3} is **{1:,.2f} {2}**".format(
            ammount, price, currency.upper(), coin_data["symbol"]
        )
        embed = discord.Embed(description=msg, colour=discord.Colour.dark_grey())
        if coin_data["name"] in coin_colour:
            embed.colour = coin_colour[coin_data["name"]]
        embed.set_footer(text="As of")
        embed.set_author(name=coin_data["name"], url=coin_url, icon_url=coin_image)
        embed.timestamp = datetime.datetime.strptime(
            coin_data["last_updated"], "%Y-%m-%dT%H:%M:%S.000Z"
        )
        if full:
            hour_1 = coin_data["quote"]["USD"]["percent_change_1h"]
            hour_24 = coin_data["quote"]["USD"]["percent_change_24h"]
            days_7 = coin_data["quote"]["USD"]["percent_change_7d"]
            hour_1_emoji = "🔼" if hour_1 >= 0 else "🔽"
            hour_24_emoji = "🔼" if hour_24 >= 0 else "🔽"
            days_7_emoji = "🔼" if days_7 >= 0 else "🔽"
            available_supply = "{0:,.2f}".format(coin_data["circulating_supply"])
            try:
                max_supply = "{0:,.2f}".format(coin_data["max_supply"])
            except (KeyError, TypeError):
                max_supply = "\N{INFINITY}"
            total_supply = "{0:,.2f}".format(coin_data["total_supply"])
            embed.set_thumbnail(url=coin_image)
            embed.add_field(
                name="Market Cap", value="{0:,.2f} {1}".format(market_cap, currency.upper())
            )
            embed.add_field(
                name="24 Hour Volume", value="{0:,.2f} {1}".format(volume_24h, currency.upper())
            )
            embed.add_field(name="Available Supply", value=available_supply)
            if max_supply is not None:
                embed.add_field(name="Max Supply", value=max_supply)
            embed.add_field(name="Total Supply ", value=total_supply)
            embed.add_field(name="Change 1 hour " + hour_1_emoji, value="{}%".format(hour_1))
            embed.add_field(name="Change 24 hours " + hour_24_emoji, value="{}%".format(hour_24))
            embed.add_field(name="Change 7 days " + days_7_emoji, value="{}%".format(days_7))
        if not ctx.channel.permissions_for(ctx.me).embed_links:
            if full:
                return (
                    f"{msg}\nMarket Cap: **{market_cap}**\n"
                    f"24 Hour Volume: **{volume_24h}**\nAvailable Supply: **{available_supply}**\n"
                    f"Max Supply: **{max_supply}**\nTotal Supply: **{total_supply}**\n"
                    f"Change 1 hour{hour_1_emoji}: **{hour_1}%**\n"
                    f"Change 24 hours{hour_24_emoji}: **{hour_24}%**\n"
                    f"Change 7 days{days_7_emoji}: **{days_7}%**\n"
                )
            else:
                return msg
        else:
            return embed

    @commands.command()
    async def gold(self, ctx: commands.Context, ammount: int = 1, currency: str = "USD") -> None:
        """
        Converts gold in ounces to a given currency.

        `ammount` must be a number of ounces to convert defaults to 1 ounce
        `[currency]` must be a valid currency defaults to USD
        """
        GOLD = "https://www.quandl.com/api/v3/datasets/WGC/GOLD_DAILY_{}.json?api_key="
        api_key = (await self.bot.get_shared_api_tokens("quandl")).get("api_key")
        if not api_key:
            return await ctx.send("The bot owner needs to supply an API key for this to work.")
        async with aiohttp.ClientSession() as session:
            async with session.get(GOLD.format(currency.upper(), api_key)) as resp:
                data = await resp.json()
        price = (data["dataset"]["data"][0][1]) * ammount
        msg = "{0} oz of Gold is {1:,.2f} {2}".format(ammount, price, currency.upper())
        embed = discord.Embed(descirption="Gold", colour=discord.Colour.gold())
        embed.add_field(name="Gold", value=msg)
        embed.set_thumbnail(
            url="https://upload.wikimedia.org/wikipedia/commons/d/d7/Gold-crystals.jpg"
        )
        if not ctx.channel.permissions_for(ctx.me).embed_links:
            await ctx.send(msg)
        else:
            await ctx.send(embed=embed)

    @commands.command()
    async def silver(self, ctx: commands.Context, ammount: int = 1, currency: str = "USD") -> None:
        """
        Converts silver in ounces to a given currency.

        `[ammount]` must be a number of ounces to convert defaults to 1 ounce
        `[currency]` must be a valid currency defaults to USD
        """
        SILVER = "https://www.quandl.com/api/v3/datasets/LBMA/SILVER.json?api_key={}"
        api_key = (await self.bot.get_shared_api_tokens("quandl")).get("api_key")
        if not api_key:
            return await ctx.send("The bot owner needs to supply an API key for this to work.")
        async with aiohttp.ClientSession() as session:
            async with session.get(SILVER.format(api_key)) as resp:
                data = await resp.json()
        price = (data["dataset"]["data"][0][1]) * ammount
        if currency != "USD":
            price = await self.conversionrate("USD", currency.upper()) * price
        msg = "{0} oz of Silver is {1:,.2f} {2}".format(ammount, price, currency.upper())
        embed = discord.Embed(descirption="Silver", colour=discord.Colour.lighter_grey())
        embed.add_field(name="Silver", value=msg)
        embed.set_thumbnail(
            url="https://upload.wikimedia.org/wikipedia/commons/5/55/Silver_crystal.jpg"
        )
        if not ctx.channel.permissions_for(ctx.me).embed_links:
            await ctx.send(msg)
        else:
            await ctx.send(embed=embed)

    @commands.command()
    async def platinum(
        self, ctx: commands.Context, ammount: int = 1, currency: str = "USD"
    ) -> None:
        """
        Converts platinum in ounces to a given currency.

        `[ammount]` must be a number of ounces to convert defaults to 1 ounce
        `[currency]` must be a valid currency defaults to USD
        """
        PLATINUM = "https://www.quandl.com/api/v3/datasets/JOHNMATT/PLAT.json?api_key={}"
        api_key = (await self.bot.get_shared_api_tokens("quandl")).get("api_key")
        if not api_key:
            return await ctx.send("The bot owner needs to supply an API key for this to work.")
        async with aiohttp.ClientSession() as session:
            async with session.get(PLATINUM.format(api_key)) as resp:
                data = await resp.json()
        price = (data["dataset"]["data"][0][1]) * ammount
        if currency != "USD":
            price = await self.conversionrate("USD", currency.upper()) * price
        msg = "{0} oz of Platinum is {1:,.2f} {2}".format(ammount, price, currency.upper())
        embed = discord.Embed(descirption="Platinum", colour=discord.Colour.dark_grey())
        embed.add_field(name="Platinum", value=msg)
        embed.set_thumbnail(
            url="https://upload.wikimedia.org/wikipedia/commons/6/68/Platinum_crystals.jpg"
        )
        if not ctx.channel.permissions_for(ctx.me).embed_links:
            await ctx.send(msg)
        else:
            await ctx.send(embed=embed)

    @commands.command(aliases=["ticker"])
    async def stock(self, ctx: commands.Context, ticker: str, currency: str = "USD") -> None:
        """
        Gets current ticker symbol price.

        `<ticker>` is the ticker symbol you want to look up
        `[currency]` is the currency you want to convert to defaults to USD
        """
        stock = "https://www.quandl.com/api/v3/datasets/WIKI/{}.json?api_key={}"
        api_key = (await self.bot.get_shared_api_tokens("quandl")).get("api_key")
        if not api_key:
            return await ctx.send("The bot owner needs to supply an API key for this to work.")
        async with aiohttp.ClientSession() as session:
            async with session.get(stock.format(ticker.upper(), api_key)) as resp:
                data = await resp.json()
        if "quandl_error" in data:
            return await ctx.send(data["quandl_error"]["message"])
        convertrate: float = 1.0
        if currency != "USD":
            maybe_convert = await self.conversionrate("USD", currency.upper())
            if maybe_convert:
                convertrate = maybe_convert
        price = (data["dataset"]["data"][0][1]) * convertrate
        msg = "{0} is {1:,.2f} {2}".format(ticker.upper(), price, currency.upper())
        embed = discord.Embed(description="Stock Price", colour=discord.Colour.lighter_grey())
        embed.add_field(name=ticker.upper(), value=msg)
        if not ctx.channel.permissions_for(ctx.me).embed_links:
            await ctx.send(msg)
        else:
            await ctx.send(embed=embed)

    @commands.command()
    @commands.is_owner()
    async def cryptoapi(self, ctx: commands.Context) -> None:
        """
        Instructions for how to setup the stock API
        """
        msg = (
            "1. Go to https://coinmarketcap.com/api/ sign up for an account.\n"
            "2. In Dashboard / Overview grab your API Key and enter it with:\n"
            f"`{ctx.prefix}set api coinmarketcap api_key YOUR_KEY_HERE`"
        )
        await ctx.maybe_send_embed(msg)

    @commands.command()
    @commands.is_owner()
    async def stockapi(self, ctx: commands.Context) -> None:
        """
        Instructions for how to setup the stock API
        """
        msg = (
            "1. Go to https://www.quandl.com/ sign up for an account.\n"
            "2. In account settings grab your API Key and enter it with:\n"
            f"`{ctx.prefix}set api quandl api_key YOUR_KEY_HERE`"
        )
        await ctx.maybe_send_embed(msg)

    @commands.command(aliases=["currency"])
    async def convertcurrency(
        self,
        ctx: commands.Context,
        ammount: float = 1.0,
        currency1: str = "USD",
        currency2: str = "GBP",
    ) -> None:
        """
        Converts a value between 2 different currencies

        `[ammount]` is the ammount you want to convert default is 1
        `[currency1]` is the currency you have default is USD
        `[currency2]` is the currency you want to convert to default is GBP
        """
        currency1 = currency1.upper()
        currency2 = currency2.upper()
        conversion = await self.conversionrate(currency1, currency2)
        if not conversion:
            return await ctx.send("The currencies provided are not valid!")
        conversion = conversion * ammount
        await ctx.send("{0} {1} is {2:,.2f} {3}".format(ammount, currency1, conversion, currency2))

    async def conversionrate(self, currency1: str, currency2: str) -> Optional[float]:
        """Function to convert different currencies"""
        params = {"base": currency1, "symbols": currency2}
        CONVERSIONRATES = "https://api.exchangeratesapi.io/latest"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(CONVERSIONRATES, params=params) as resp:
                    data = await resp.json()
            conversion = data["rates"][currency2]
            return conversion
        except Exception as e:
            print(e)
            return None
