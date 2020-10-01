import asyncio
import random
from typing import Optional, Tuple

from redbot.core import Config, checks, commands
from redbot.core.data_manager import cog_data_path

from .phue import Bridge, RemoteBridge, RemoteToken


class Hue(commands.Cog):
    """
    Control philips hue light on the same network as the bot
    """

    __author__ = ["TrustyJAID"]
    __version__ = "1.2.0"

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, 1384534876565)
        default_global = {
            "ip": None,
            "external": False,
        }
        self.config.register_global(**default_global)
        self.bridge = None
        self.lights = None

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

    async def get_bridge(self) -> bool:
        if not await self.config.external():
            if self.bridge is None:
                try:
                    self.bridge = Bridge(await self.config.ip())
                    self.lights = self.bridge.lights
                    return True
                except Exception as e:
                    print(e)
                    return False
            else:
                return True
        else:
            if self.bridge is None:
                try:
                    self.bridge = RemoteBridge(
                        token_path=str(cog_data_path(self) / "phue_token.json")
                    )
                    self.lights = self.bridge.lights
                    return True
                except Exception as e:
                    print(e)
                    return False
            else:
                return True

    @commands.group(name="hueset")
    @checks.is_owner()
    async def hue_set(self, ctx: commands.Context) -> None:
        """Commands for setting hue settings"""
        pass

    @commands.group(name="hue")
    @checks.is_owner()
    async def _hue(self, ctx: commands.Context) -> None:
        """Commands for interacting with Hue lights"""
        pass

    @hue_set.command(name="connect")
    async def hue_connect(self, ctx: commands.Context) -> None:
        """Setup command if bridge cannot connect"""
        if not await self.get_bridge():
            return await ctx.send("No IP has been set.")
        self.bridge.connect()

    @hue_set.command()
    async def external(self, ctx: commands.Context, external: bool) -> None:
        """Set whether or not to use external api calls"""
        await self.config.external.set(external)
        await ctx.tick()

    @hue_set.command()
    async def tokens(
        self, ctx: commands.Context, client_id: str, client_secret: str, app_id: str
    ) -> None:
        """
        Set the external API tokens

        Register for a [Philips Hue Developer Account](https://developers.meethue.com/)
        Use the [Developer Account dashboard](https://developers.meethue.com/user/me/apps)
        to create an 'App'
        provide the client_id, client_secret, and app_id
        after
        """
        token = RemoteToken(
            clientid=client_id,
            clientsecret=client_secret,
            appid=app_id,
            saveto=str(cog_data_path(self) / "phue_token.json"),
        )
        await ctx.send(
            "Now visit the following URL, login, and paste "
            f"the full URL provided in chat {token.__get_auth_url__()}"
        )
        try:
            msg = await ctx.bot.wait_for(
                "message", check=lambda m: m.author.id == ctx.author.id, timeout=60
            )
        except asyncio.TimeoutError:
            return
        await ctx.bot.loop.run_in_executor(None, token.__authorise__, msg.content)
        await ctx.tick()

    @hue_set.command(name="ip")
    async def hue_ip(self, ctx: commands.Context, ip: str) -> None:
        """
        Set the IP address of the hue bridge

        `ip` is the bridges IP address
        """
        await self.config.ip.set(ip)
        self.bridge = Bridge(await self.config.ip())
        self.lights = self.bridge.lights

    @hue_set.command(name="check")
    async def check_api(self, ctx: commands.Context) -> None:
        """Gets light data from bridge and prints to terminal"""
        if not await self.get_bridge():
            return await ctx.send("No IP has been set.")
        print(self.bridge.get_api())

    def max_min_check(self, value: int, _max: int, _min: int):
        if value > _max:
            return _max
        if value < _min:
            return _min
        else:
            return value

    @_hue.command(name="brightness")
    async def brightness_set(
        self, ctx: commands.Context, brightness: int = 254, *, name: Optional[str] = None
    ) -> None:
        """
        Sets the brightness for lights

        `brightness` the level of brightness to set
        `name` the name of the light to adjust
        """
        if not await self.get_bridge():
            return await ctx.send("No IP has been set.")

        def _change(brightness, name):
            for light in self.lights:
                if name is None or light.name.lower() == name.lower() and light.on:
                    light.brightness = self.max_min_check(brightness, 254, 0)

        await ctx.bot.loop.run_in_executor(None, _change, brightness, name)
        await ctx.tick()

    @_hue.command(name="temp", aliases=["ct", "colourtemp", "colortemp", "temperature"])
    async def colourtemp_set(
        self, ctx: commands.Context, ct: int = 500, *, name: Optional[str] = None
    ) -> None:
        """
        Sets the colour temperature for lights

        `ct` must be a number the colour temperature to set
        `name` the name of the light to adjust
        """
        if not await self.get_bridge():
            return await ctx.send("No IP has been set.")

        def _change(ct, name):
            for light in self.lights:
                if name is None or light.name.lower() == name.lower() and light.on:
                    light.colortemp = self.max_min_check(ct, 600, 154)

        await ctx.bot.loop.run_in_executor(None, _change, ct, name)
        await ctx.tick()

    @_hue.command(name="hue")
    async def set_hue(
        self, ctx: commands.Context, hue: int = 25000, *, name: Optional[str] = None
    ) -> None:
        """
        Sets the hue for lights

        `hue` must be a number the hue value to set the light to
        `name` the name of the light to adjust
        """
        if not await self.get_bridge():
            return await ctx.send("No IP has been set.")

        def _change(hue, name):
            for light in self.lights:
                if name is None or light.name.lower() == name.lower() and light.on:
                    light.hue = hue

        await ctx.bot.loop.run_in_executor(None, _change, hue, name)
        await ctx.tick()

    @_hue.command(name="saturation", aliases=["sat"])
    async def saturation_set(
        self, ctx: commands.Context, saturation: int = 254, *, name: Optional[str] = None
    ) -> None:
        """
        Sets the saturation for lights

        `saturation` must be a number the saturation value to set the light to
        `name` the name of the light to adjust
        """
        if not await self.get_bridge():
            return await ctx.send("No IP has been set.")

        def _change(saturation, name):
            for light in self.lights:
                if name is None or light.name.lower() == name.lower() and light.on:
                    light.saturation = self.max_min_check(saturation, 254, 0)

        await ctx.bot.loop.run_in_executor(None, _change, saturation, name)
        await ctx.tick()

    @_hue.command(name="random")
    async def hue_random_colour(
        self, ctx: commands.Context, *, name: Optional[str] = None
    ) -> None:
        """
        Sets the light to a random colour

        `name` the name of the light to adjust
        """
        if not await self.get_bridge():
            return await ctx.send("No IP has been set.")

        def _change(name):
            colours = [random.random(), random.random()]
            for light in self.lights:
                if name is None or light.name.lower() == name.lower() and light.on:
                    light.xy = colours

        await ctx.bot.loop.run_in_executor(None, _change, name)
        await ctx.tick()

    @_hue.command(name="colourloop", aliases=["cl", "colorloop"])
    async def hue_colourloop(self, ctx: commands.Context, *, name: Optional[str] = None) -> None:
        """
        Toggles the light on colour looping all colours

        `name` the name of the light to adjust
        """
        if not await self.get_bridge():
            return await ctx.send("No IP has been set.")

        def _change(name):
            for light in self.lights:
                if name is None or light.name.lower() == name.lower():
                    if light.effect != "colorloop" and light.on:
                        light.effect = "colorloop"
                        continue
                    if light.effect == "colorloop" and light.on:
                        light.effect = "none"
                        continue

        await ctx.bot.loop.run_in_executor(None, _change, name)
        await ctx.tick()

    @_hue.group(name="colour", aliases=["color"])
    async def _colour(self, ctx: commands.Context) -> None:
        """Sets the colour for lights"""
        if not await self.get_bridge():
            return await ctx.send("No IP has been set.")
        pass

    def rgb_to_xy(self, red: float, green: float, blue: float) -> Tuple[float, float]:
        X = 0.4124 * red + 0.3576 * green + 0.1805 * blue
        Y = 0.2126 * red + 0.7152 * green + 0.0722 * blue
        Z = 0.0193 * red + 0.1192 * green + 0.9505 * blue
        try:
            x = X / (X + Y + Z)
            y = Y / (X + Y + Z)
        except ZeroDivisionError:
            x = 1.0
            y = 1.0
        return x, y

    @_colour.command(name="rgb")
    async def hue_colour_rgb(
        self,
        ctx: commands.Context,
        red: float,
        green: float,
        blue: float,
        *,
        name: Optional[str] = None,
    ) -> None:
        """
        Sets the colour using RGB colour coordinates

        `red` must be a number the red value to set
        `green` must be a number the green value to set
        `blue` must be a number the blue value to set
        `name` the name of the light to adjust
        """
        if not await self.get_bridge():
            return await ctx.send("No IP has been set.")

        def _change(red, green, blue, name):
            x, y = self.rgb_to_xy(red, green, blue)
            for light in self.lights:
                if name is None or light.name.lower() == name.lower() and light.on:
                    light.xy = [x, y]

        await ctx.bot.loop.run_in_executor(None, _change, red, green, blue, name)
        await ctx.tick()

    @_colour.command(name="xy", aliases=["xyz"])
    async def hue_colour_xy(
        self, ctx: commands.Context, x: float, y: float, *, name: Optional[str] = None
    ) -> None:
        """
        Sets the colour using xyz colour values

        `x` must be a number the x value to set
        `y` must be a number the y value to set
        `name` the name of the light to adjust
        Note: The z value is determined from two other values
        """
        if not await self.get_bridge():
            return await ctx.send("No IP has been set.")

        def _change(x, y, name):
            if x > 1.0 or x < 0.0:
                x = 1.0
            if y > 1.0 or y < 0.0:
                y = 1.0
            for light in self.lights:
                if name is None or light.name.lower() == name.lower() and light.on:
                    light.xy = [x, y]

        await ctx.bot.loop.run_in_executor(None, _change, x, y, name)
        await ctx.tick()

    @_colour.command(name="hex")
    async def hue_colour_hex(self, ctx: commands.Context, hex_code, *, name=None) -> None:
        """
        Attempt to set the colour based on hex values
        Not 100% accurate

        `hex` the hex code colour to try to change to
        `name` the name of the light to adjust
        """
        if not await self.get_bridge():
            return await ctx.send("No IP has been set.")

        def _change(hex_code, name):
            if "#" in hex_code:
                hex_code.replace("#", "")
            r, g, b = tuple(int(hex_code[i : i + 2], 16) for i in (0, 2, 4))
            x, y = self.rgb_to_xy(r, g, b)
            for light in self.lights:
                if name is None or light.name.lower() == name.lower() and light.on:
                    light.xy = [x, y]

        await ctx.bot.loop.run_in_executor(None, _change, hex_code, name)
        await ctx.tick()

    @_hue.command(name="test", hidden=True)
    async def hue_test(self, ctx: commands.Context, cl1: float, cl2: float) -> None:
        """Testing function"""
        if not await self.get_bridge():
            return await ctx.send("No IP has been set.")
        for light in self.lights:
            light.xy = [cl1, cl2]

    @_hue.command(name="switch")
    async def hue_switch(self, ctx: commands.Context, *, name=None) -> None:
        """
        Toggles lights on or off

        `name` the name of the light to adjust
        """
        if not await self.get_bridge():
            return await ctx.send("No IP has been set.")

        def _change(name):
            for light in self.lights:
                if name is None or light.name.lower() == name.lower():
                    if light.on:
                        light.on = False
                        continue
                    if not light.on:
                        light.on = True
                        continue

        await ctx.bot.loop.run_in_executor(None, _change, name)
        await ctx.tick()

    @_hue.command(name="off")
    async def turn_off(self, ctx: commands.Context, *, name=None) -> None:
        """
        Turns off light

        `name` the name of the light to adjust
        """
        if not await self.get_bridge():
            return await ctx.send("No IP has been set.")

        def _change(name):
            for light in self.lights:
                if name is None or light.name.lower() == name.lower():
                    light.on = False

        await ctx.bot.loop.run_in_executor(None, _change, name)
        await ctx.tick()

    @_hue.command(name="on")
    async def turn_on(self, ctx: commands.Context, name=None) -> None:
        """
        Turns on Light

        `name` the name of the light to adjust
        """
        if not await self.get_bridge():
            return await ctx.send("No IP has been set.")

        def _change(name):
            for light in self.lights:
                if name is None or light.name.lower() == name.lower():
                    light.on = True

        await ctx.bot.loop.run_in_executor(None, _change, name)
        await ctx.tick()
