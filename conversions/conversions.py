import datetime
from typing import Dict, List, Optional, Union

import aiohttp
import discord
from red_commons.logging import getLogger
from redbot.core import commands
from redbot.core.bot import Red

from .coin import Coin, CoinBase
from .errors import CoinMarketCapError

log = getLogger("red.Trusty-cogs.Conversions")


class Conversions(commands.Cog):
    """
    Gather information about various crypto currencies,
    stocks, and converts to different currencies
    """

    __author__ = ["TrustyJAID"]
    __version__ = "1.3.2"

    def __init__(self, bot: Red) -> None:
        self.bot = bot
        self.session = aiohttp.ClientSession()
        self.coin_index: Dict[int, CoinBase] = {}

    async def cog_unload(self) -> None:
        await self.session.close()

    def format_help_for_context(self, ctx: commands.Context) -> str:
        """
        Thanks Sinbad!
        """
        pre_processed = super().format_help_for_context(ctx)
        return f"{pre_processed}\n\nCog Version: {self.__version__}"

    async def red_delete_data_for_user(self, **kwargs) -> None:
        """
        Nothing to delete
        """
        return

    @commands.command(aliases=["bitcoin", "BTC"])
    async def btc(
        self,
        ctx: commands.Context,
        amount: float = 1.0,
        currency: str = "USD",
        full: Optional[bool] = None,
    ) -> None:
        """
        converts from BTC to a given currency.

        `[ammount=1.0]` The number of coins you want to know the price for.
        `[currency=USD]` The optional desired currency price. Defaults to USD.
        `[full=True]` is a True/False value whether to display just the converted amount
        or the full display for the currency
        """
        await ctx.invoke(self.crypto, "BTC", amount, currency, full)

    @commands.command(aliases=["ethereum", "ETH"])
    async def eth(
        self,
        ctx: commands.Context,
        amount: float = 1.0,
        currency: str = "USD",
        full: Optional[bool] = None,
    ) -> None:
        """
        converts from ETH to a given currency.

        `[ammount=1.0]` The number of coins you want to know the price for.
        `[currency=USD]` The optional desired currency price. Defaults to USD.
        `[full=True]` is a True/False value whether to display just the converted amount
        or the full display for the currency
        """
        await ctx.invoke(self.crypto, "ETH", amount, currency, full)

    @commands.command(aliases=["litecoin", "LTC"])
    async def ltc(
        self,
        ctx: commands.Context,
        amount: float = 1.0,
        currency: str = "USD",
        full: Optional[bool] = None,
    ) -> None:
        """
        converts from LTC to a given currency.

        `[ammount=1.0]` The number of coins you want to know the price for.
        `[currency=USD]` The optional desired currency price. Defaults to USD.
        `[full=True]` is a True/False value whether to display just the converted amount
        or the full display for the currency
        """
        await ctx.invoke(self.crypto, "LTC", amount, currency, full)

    @commands.command(aliases=["monero", "XMR"])
    async def xmr(
        self,
        ctx: commands.Context,
        amount: float = 1.0,
        currency: str = "USD",
        full: Optional[bool] = None,
    ) -> None:
        """
        converts from XMR to a given currency.

        `[ammount=1.0]` The number of coins you want to know the price for.
        `[currency=USD]` The optional desired currency price. Defaults to USD.
        `[full=True]` is a True/False value whether to display just the converted amount
        or the full display for the currency
        """
        await ctx.invoke(self.crypto, "XMR", amount, currency, full)

    @commands.command(aliases=["bitcoin-cash", "BCH"])
    async def bch(
        self,
        ctx: commands.Context,
        amount: float = 1.0,
        currency: str = "USD",
        full: Optional[bool] = None,
    ) -> None:
        """
        converts from BCH to a given currency.

        `[ammount=1.0]` The number of coins you want to know the price for.
        `[currency=USD]` The optional desired currency price. Defaults to USD.
        `[full=True]` is a True/False value whether to display just the converted amount
        or the full display for the currency
        """
        await ctx.invoke(self.crypto, "BCH", amount, currency, full)

    @commands.command(aliases=["dogecoin", "XDG"])
    async def doge(
        self,
        ctx: commands.Context,
        amount: float = 1.0,
        currency: str = "USD",
        full: Optional[bool] = None,
    ) -> None:
        """
        converts from XDG to a given currency.

        `[ammount=1.0]` The number of coins you want to know the price for.
        `[currency=USD]` The optional desired currency price. Defaults to USD.
        `[full=True]` is a True/False value whether to display just the converted amount
        or the full display for the currency
        """
        await ctx.invoke(self.crypto, "DOGE", amount, currency, full)

    async def get_header(self) -> Optional[Dict[str, str]]:
        api_key = (await self.bot.get_shared_api_tokens("coinmarketcap")).get("api_key")
        if api_key:
            return {"X-CMC_PRO_API_KEY": api_key}
        else:
            return None

    async def get_coins(self, coins: List[str]) -> List[Coin]:
        if not self.coin_index:
            await self.checkcoins()
        to_ret = []
        coin_ids = []
        for search_coin in coins:
            for _id, coin in self.coin_index.items():
                if search_coin.upper() == coin.symbol or search_coin.lower() == coin.name.lower():
                    coin_ids.append(str(_id))

        params = {"id": ",".join(coin_ids)}
        url = "https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest"
        async with self.session.get(url, headers=await self.get_header(), params=params) as resp:
            data = await resp.json()
            coins_data = data.get("data", {})
            for coin_id, coin_data in coins_data.items():
                to_ret.append(Coin.from_json(coin_data))
        return to_ret

    async def get_latest_coins(self) -> List[Coin]:
        """
        This converts all latest coins into Coin objects for us to use
        """
        url = "https://pro-api.coinmarketcap.com/v1/cryptocurrency/listings/latest"
        async with self.session.get(url, headers=await self.get_header()) as resp:
            data = await resp.json()
            if resp.status == 200:
                return [Coin.from_json(c) for c in data["data"]]
            elif resp.status == 401:
                raise CoinMarketCapError(
                    "The bot owner has not set an API key. "
                    "Please use `{prefix}cryptoapi` to see "
                    "how to create and setup an API key."
                )
            else:
                raise CoinMarketCapError(
                    "Something went wrong, the error code is "
                    "{code}\n`{error_message}`".format(
                        code=resp.status, error_message=data["error_message"]
                    )
                )

    async def checkcoins(self) -> None:
        if not self.coin_index:
            url = "https://pro-api.coinmarketcap.com/v1/cryptocurrency/map"
            async with self.session.get(url, headers=await self.get_header()) as resp:
                data = await resp.json()
            if resp.status == 200:
                self.coin_index = {c["id"]: CoinBase.from_json(c) for c in data.get("data", [])}
            elif resp.status == 401:
                raise CoinMarketCapError(
                    "The bot owner has not set an API key. "
                    "Please use `{prefix}cryptoapi` to see "
                    "how to create and setup an API key."
                )
            else:
                raise CoinMarketCapError(
                    "Something went wrong, the error code is "
                    "{code}\n`{error_message}`".format(
                        code=resp.status, error_message=data["error_message"]
                    )
                )

    @commands.command()
    async def multicoin(self, ctx: commands.Context, *coins: str) -> None:
        """
        Gets the current USD value for a list of coins

        `coins` must be a list of white space separated crypto coins
        e.g. `[p]multicoin BTC BCH LTC ETH DASH XRP`
        """
        if len(coins) == 0:
            try:
                coin_list = await self.get_latest_coins()
            except CoinMarketCapError as e:
                await ctx.send(str(e).replace("{prefix}", ctx.clean_prefix))
                return
        else:
            coin_list = await self.get_coins(coins)
        if not coin_list:
            await ctx.send("The provided list of coins aren't acceptable.")

        if await ctx.embed_requested():
            embed = discord.Embed(title="Crypto coin comparison")
            for coin in coin_list[:25]:
                price = coin.quote["USD"].price
                msg = f"1 {coin.symbol} is {price:,.2f} USD"
                embed.add_field(name=coin.name, value=msg)
            await ctx.send(embed=embed)
        else:
            msg = ""
            for coin in coin_list[:25]:
                price = coin.quote["USD"].price
                msg = f"1 {coin.symbol} is {price:,.2f} USD"
                embed.add_field(name=coin.name, value=msg)
            await ctx.send(msg)

    @commands.command()
    async def crypto(
        self,
        ctx: commands.Context,
        coin: str,
        amount: float = 1.0,
        currency: str = "USD",
        full: Optional[bool] = None,
    ) -> None:
        """
        Displays the latest information about a specified crypto currency

        `<coin>` must be the name or symbol of a crypto coin
        `[ammount=1.0]` The number of coins you want to know the price for.
        `[currency=USD]` The optional desired currency price. Defaults to USD.
        `[full=True]` is a True/False value whether to display just the converted amount
        or the full display for the currency
        """
        async with ctx.typing():
            if full is None and amount == 1.0:
                embed = await self.crypto_embed(ctx, coin, amount, currency, True)
            elif full is None and amount != 1.0:
                embed = await self.crypto_embed(ctx, coin, amount, currency, False)
            else:
                embed = await self.crypto_embed(ctx, coin, amount, currency, full)
        if embed is None:
            return
        if await ctx.embed_requested():
            await ctx.send(embed=embed["embed"])
        else:
            await ctx.send(embed["content"])

    async def crypto_embed(
        self,
        ctx: commands.Context,
        coin_name: str,
        amount: float,
        currency: str,
        full: Optional[bool],
    ) -> Optional[Dict[str, Union[discord.Embed, str]]]:
        """
        Creates the embed for the crypto currency

        Parameters
        ----------
            ctx: commands.Context
                Used to return an error message should one happen.
            coin_name: str
                The name of the coin you want to pull information for.
            amount: float
                The amount of coins you want to see the price for.
            currency: str
                The ISO 4217 Currency Code you want the coin converted into.
            full: Optional[bool]
                Whether or not to display full information or just the conversions.

        Returns
        -------
            Optional[Dict[str, Union[discord.Embed, str]]]
                A dictionary containing both the plaintext and discord Embed object
                used for later determining if we can post the embed and if not
                we still have the plaintext available.
        """
        currency = currency.upper()
        if len(currency) > 3 or len(currency) < 3:
            currency = "USD"
        try:
            coins = await self.get_coins([coin_name])
            coin = next(iter(coins), None)
        except CoinMarketCapError as e:
            await ctx.send(str(e).replace("{prefix}", ctx.clean_prefix))
            return None
        if coin is None:
            await ctx.send(f"{coin_name} does not appear to be in my list of coins.")
            return None

        coin_colour = {
            "Bitcoin": discord.Colour.gold(),
            "Bitcoin Cash": discord.Colour.orange(),
            "Ethereum": discord.Colour.dark_grey(),
            "Litecoin": discord.Colour.dark_grey(),
            "Monero": discord.Colour.orange(),
        }
        price = float(coin.quote["USD"].price) * amount
        market_cap = float(coin.quote["USD"].market_cap)
        volume_24h = float(coin.quote["USD"].volume_24h)
        coin_image = f"https://s2.coinmarketcap.com/static/img/coins/128x128/{coin.id}.png"
        coin_url = f"https://coinmarketcap.com/currencies/{coin.id}"
        if currency.upper() != "USD":
            conversionrate = await self.conversionrate("USD", currency)
            if conversionrate:
                price = conversionrate * price
                market_cap = conversionrate * market_cap
                volume_24h = conversionrate * volume_24h

        msg = f"{amount} {coin.symbol} is **{price:,.2f} {currency}**\n"
        embed = discord.Embed(
            description=msg,
            colour=coin_colour.get(coin.name, discord.Colour.dark_grey()),
        )
        embed.set_author(name=coin.name, url=coin_url, icon_url=coin_image)
        embed.add_field(name="Last Updated", value=discord.utils.format_dt(coin.last_updated))
        if full:
            hour_1 = coin.quote["USD"].percent_change_1h
            hour_24 = coin.quote["USD"].percent_change_24h
            days_7 = coin.quote["USD"].percent_change_7d
            hour_1_emoji = "🔼" if hour_1 >= 0 else "🔽"
            hour_24_emoji = "🔼" if hour_24 >= 0 else "🔽"
            days_7_emoji = "🔼" if days_7 >= 0 else "🔽"

            available_supply = f"{coin.circulating_supply:,.2f}"
            try:
                max_supply = f"{coin.max_supply:,.2f}"
            except (KeyError, TypeError):
                max_supply = "\N{INFINITY}"
            total_supply = f"{coin.total_supply:,.2f}"
            embed.set_thumbnail(url=coin_image)
            embed.add_field(name="Market Cap", value=f"{market_cap:,.2f} {currency}")
            embed.add_field(name="24 Hour Volume", value=f"{volume_24h:,.2f} {currency}")
            embed.add_field(name="Available Supply", value=available_supply)
            if max_supply is not None:
                embed.add_field(name="Max Supply", value=max_supply)
            embed.add_field(name="Total Supply ", value=total_supply)
            embed.add_field(name="Change 1 hour " + hour_1_emoji, value=f"{hour_1}%")
            embed.add_field(name="Change 24 hours " + hour_24_emoji, value=f"{hour_24}%")
            embed.add_field(name="Change 7 days " + days_7_emoji, value=f"{days_7}%")
            msg += (
                f"Market Cap: **{market_cap}**\n"
                f"24 Hour Volume: **{volume_24h}**\nAvailable Supply: **{available_supply}**\n"
                f"Max Supply: **{max_supply}**\nTotal Supply: **{total_supply}**\n"
                f"Change 1 hour{hour_1_emoji}: **{hour_1}%**\n"
                f"Change 24 hours{hour_24_emoji}: **{hour_24}%**\n"
                f"Change 7 days{days_7_emoji}: **{days_7}%**\n"
            )

        return {"embed": embed, "content": msg}

    @commands.command(aliases=["ticker"])
    async def stock(self, ctx: commands.Context, ticker: str, currency: str = "USD") -> None:
        """
        Gets current ticker symbol price.

        `<ticker>` is the ticker symbol you want to look up
        `[currency]` is the currency you want to convert to defaults to USD
        """
        stock = "https://query1.finance.yahoo.com/v8/finance/chart/{}"
        async with self.session.get(stock.format(ticker.upper())) as resp:
            data = await resp.json()
        if not data["chart"]["result"]:
            await ctx.send(
                "`{ticker}` does not appear to be a valid ticker symbol.".format(ticker=ticker)
            )
            return
        ticker_data = data["chart"]["result"][0]["meta"]
        if not ticker_data["currency"]:
            await ctx.send(
                "`{ticker}` does not have a valid currency to view.".format(ticker=ticker)
            )
            return
        convertrate: float = 1.0
        if ticker_data["currency"] != currency:
            maybe_convert = await self.conversionrate(ticker_data["currency"], currency.upper())
            if maybe_convert:
                convertrate = maybe_convert

        price = (ticker_data["regularMarketPrice"]) * convertrate
        last_updated = datetime.datetime.utcfromtimestamp(ticker_data["regularMarketTime"])
        msg = "{0} is {1:,.2f} {2}".format(ticker.upper(), price, currency.upper())
        embed = discord.Embed(
            description="Stock Price",
            colour=discord.Colour.lighter_grey(),
            timestamp=last_updated,
        )
        embed.set_footer(text="Last Updated")
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

    @commands.command(aliases=["currency"])
    async def convertcurrency(
        self,
        ctx: commands.Context,
        currency1: str,
        currency2: str,
        amount: float = 1.0,
    ) -> None:
        """
        Converts a value between 2 different currencies

        `<currency1>` The first currency in [ISO 4217 format.](https://en.wikipedia.org/wiki/ISO_4217)
        `<currency2>` The second currency in [ISO 4217 format.](https://en.wikipedia.org/wiki/ISO_4217)
        `[amount=1.0]` is the ammount you want to convert default is 1.0
        """
        currency1 = currency1.upper()
        currency2 = currency2.upper()
        if len(currency1) < 3 or len(currency1) > 3:
            await ctx.maybe_send_embed(
                (
                    f"{currency1} does not look like a [3 character ISO "
                    "4217 code](https://en.wikipedia.org/wiki/ISO_4217)"
                )
            )
            return
        if len(currency2) < 3 or len(currency2) > 3:
            await ctx.maybe_send_embed(
                (
                    f"{currency2} does not look like a [3 character ISO "
                    "4217 code](https://en.wikipedia.org/wiki/ISO_4217)"
                )
            )
            return
        conversion = await self.conversionrate(currency1, currency2)
        if conversion is None:
            await ctx.maybe_send_embed("The currencies provided are not valid!")
            return
        cost = conversion * amount
        await ctx.maybe_send_embed(f"{amount} {currency1} is {cost:,.2f} {currency2}")

    async def conversionrate(self, currency1: str, currency2: str) -> Optional[float]:
        """Function to convert different currencies"""
        conversion = None
        try:
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{currency1}{currency2}=x"
            async with self.session.get(url) as resp:
                data = await resp.json()
            results = data.get("chart", {}).get("result", [])
            conversion = results[0].get("meta", {}).get("regularMarketPrice")
        except Exception:
            log.exception(f"Error grabbing conversion rates for {currency1} {currency2}")
        return conversion
