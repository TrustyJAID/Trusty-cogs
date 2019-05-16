import discord
from redbot.core import commands
import datetime
import aiohttp
import re
from typing import Optional


class Conversions(commands.Cog):
    """
        Gather information about various crypto currencies,
        rare metals, stocks, and converts to different currencies
    """

    def __init__(self, bot):
        self.bot = bot

    @commands.command(aliases=["bitcoin", "BTC"])
    async def btc(self, ctx, ammount: Optional[float] = 1.0, currency="USD", full: bool = True):
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
        if type(embed) is str:
            await ctx.send(embed)
        else:
            await ctx.send(embed=embed)

    @commands.command(aliases=["ethereum", "ETH"])
    async def eth(self, ctx, ammount: Optional[float] = 1.0, currency="USD", full: bool = True):
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
        if type(embed) is str:
            await ctx.send(embed)
        else:
            await ctx.send(embed=embed)

    @commands.command(aliases=["litecoin", "LTC"])
    async def ltc(self, ctx, ammount: Optional[float] = 1.0, currency="USD", full: bool = True):
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
        if type(embed) is str:
            await ctx.send(embed)
        else:
            await ctx.send(embed=embed)

    @commands.command(aliases=["monero", "XMR"])
    async def xmr(self, ctx, ammount: Optional[float] = 1.0, currency="USD", full: bool = True):
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
        if type(embed) is str:
            await ctx.send(embed)
        else:
            await ctx.send(embed=embed)

    @commands.command(aliases=["bitcoin-cash", "BCH"])
    async def bch(self, ctx, ammount: Optional[float] = 1.0, currency="USD", full: bool = True):
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
        if type(embed) is str:
            await ctx.send(embed)
        else:
            await ctx.send(embed=embed)

    async def checkcoins(self, base):
        link = "https://api.coinmarketcap.com/v2/ticker/"
        async with aiohttp.ClientSession() as session:
            async with session.get(link) as resp:
                data = await resp.json()
        for coin in data["data"]:
            if (
                base.upper() == data["data"][coin]["symbol"].upper()
                or base.lower() == data["data"][coin]["name"].lower()
            ):
                return data["data"][coin]
        return None

    @commands.command()
    async def multicoin(self, ctx, *, coins=None):
        """
            Gets the current USD value for a list of coins

            `coins` must be a list of white space separated crypto coins
            e.g. `[p]multicoin BTC BCH LTC ETH DASH XRP`
        """
        coin_list = []
        if coins is None:
            async with aiohttp.ClientSession() as session:
                async with session.get("https://api.coinmarketcap.com/v2/ticker/") as resp:
                    data = await resp.json()
            for coin in data["data"]:
                coin_list.append(data["data"][coin])
        else:
            coins = re.split(r"\W+", coins)
            for coin in coins:
                coin_list.append(await self.checkcoins(coin))
        embed = discord.Embed(title="Crypto coin comparison")
        if ctx.channel.permissions_for(ctx.me).embed_links:
            for coin in coin_list[:25]:
                if coin is not None:
                    msg = "1 {0} is {1:,.2f} USD".format(
                        coin["symbol"], float(coin["quotes"]["USD"]["price"])
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
        self, ctx, coin, ammount: Optional[float] = 1.0, currency="USD", full: bool = True
    ):
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
        if type(embed) is str:
            await ctx.send(embed)
        else:
            await ctx.send(embed=embed)

    async def crypto_embed(self, ctx, coin, ammount=1.0, currency="USD", full=True):
        """Creates the embed for the crypto currency"""
        coin_data = await self.checkcoins(coin)
        if coin_data is None:
            await ctx.send("{} is not in my list of currencies!".format(coin))
            return
        coin_colour = {
            "Bitcoin": discord.Colour.gold(),
            "Bitcoin Cash": discord.Colour.orange(),
            "Ethereum": discord.Colour.dark_grey(),
            "Litecoin": discord.Colour.dark_grey(),
            "Monero": discord.Colour.orange(),
        }
        price = float(coin_data["quotes"]["USD"]["price"]) * ammount
        market_cap = float(coin_data["quotes"]["USD"]["market_cap"])
        volume_24h = float(coin_data["quotes"]["USD"]["volume_24h"])
        coin_image = "https://s2.coinmarketcap.com/static/img/coins/128x128/{}.png".format(
            coin_data["id"]
        )
        coin_url = "https://coinmarketcap.com/currencies/{}".format(coin_data["id"])
        if currency.upper() != "USD":
            conversionrate = await self.conversionrate("USD", currency.upper())
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
        embed.timestamp = datetime.datetime.utcfromtimestamp(int(coin_data["last_updated"]))
        if full:
            hour_1 = coin_data["quotes"]["USD"]["percent_change_1h"]
            hour_24 = coin_data["quotes"]["USD"]["percent_change_24h"]
            days_7 = coin_data["quotes"]["USD"]["percent_change_7d"]
            hour_1_emoji = "🔼" if hour_1 >= 0 else "🔽"
            hour_24_emoji = "🔼" if hour_24 >= 0 else "🔽"
            days_7_emoji = "🔼" if days_7 >= 0 else "🔽"
            available_supply = "{0:,.2f}".format(coin_data["circulating_supply"])
            try:
                max_supply = "{0:,.2f}".format(coin_data["max_supply"])
            except KeyError:
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
    async def gold(self, ctx, ammount: Optional[int] = 1, currency="USD"):
        """
            Converts gold in ounces to a given currency.

            `ammount` must be a number of ounces to convert defaults to 1 ounce
            `[currency]` must be a valid currency defaults to USD
        """
        GOLD = "https://www.quandl.com/api/v3/datasets/WGC/GOLD_DAILY_{}.json?api_key=EKvr5W-sJUFVSevcpk4v"
        async with aiohttp.ClientSession() as session:
            async with session.get(GOLD.format(currency.upper())) as resp:
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
    async def silver(self, ctx, ammount: Optional[int] = 1, currency="USD"):
        """
            Converts silver in ounces to a given currency.

            `[ammount]` must be a number of ounces to convert defaults to 1 ounce
            `[currency]` must be a valid currency defaults to USD
        """
        SILVER = (
            "https://www.quandl.com/api/v3/datasets/LBMA/SILVER.json?api_key=EKvr5W-sJUFVSevcpk4v"
        )
        async with aiohttp.ClientSession() as session:
            async with session.get(SILVER) as resp:
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
    async def platinum(self, ctx, ammount: Optional[int] = 1, currency="USD"):
        """
            Converts platinum in ounces to a given currency.

            `[ammount]` must be a number of ounces to convert defaults to 1 ounce
            `[currency]` must be a valid currency defaults to USD
        """
        PLATINUM = "https://www.quandl.com/api/v3/datasets/JOHNMATT/PLAT.json?api_key=EKvr5W-sJUFVSevcpk4v"
        async with aiohttp.ClientSession() as session:
            async with session.get(PLATINUM) as resp:
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
    async def stock(self, ctx, ticker, currency="USD"):
        """
            Gets current ticker symbol price.

            `<ticker>` is the ticker symbol you want to look up
            `[currency]` is the currency you want to convert to defaults to USD
        """
        stock = "https://www.quandl.com/api/v3/datasets/WIKI/{}.json?api_key=EKvr5W-sJUFVSevcpk4v"
        async with aiohttp.ClientSession() as session:
            async with session.get(stock.format(ticker.upper())) as resp:
                data = await resp.json()
        if "quandl_error" in data:
            return await ctx.send(data["quandl_error"]["message"])
        convertrate = 1
        if currency != "USD":
            convertrate = self.conversionrate("USD", currency.upper())
        price = (data["dataset"]["data"][0][1]) * convertrate
        msg = "{0} is {1:,.2f} {2}".format(ticker.upper(), price, currency.upper())
        embed = discord.Embed(descirption="Stock Price", colour=discord.Colour.lighter_grey())
        embed.add_field(name=ticker.upper(), value=msg)
        if not ctx.channel.permissions_for(ctx.me).embed_links:
            await ctx.send(msg)
        else:
            await ctx.send(embed=embed)

    @commands.command(aliases=["currency"])
    async def convertcurrency(
        self, ctx, ammount: Optional[float] = 1.0, currency1="USD", currency2="GBP"
    ):
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

    async def conversionrate(self, currency1, currency2):
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
