from typing import Optional

from red_commons.logging import getLogger
from redbot.core import Config, checks, commands

from .api import Client, HueError

log = getLogger("red.trusty-cogs.hue")


class Hue(commands.Cog):
    """
    Control philips hue light on the same network as the bot
    """

    __author__ = ["TrustyJAID"]
    __version__ = "1.3.0"

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, 1384534876565)
        self.config.register_global(ip=None, external=False, username=None, clientkey=None)
        self.bridge = None

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

    async def cog_load(self):
        if await self.config.ip():
            await self.set_bridge()

    async def cog_unload(self):
        if self.bridge:
            await self.bridge.close()

    async def set_bridge(self):
        self.bridge = Client(
            ip=await self.config.ip(),
            username=await self.config.username(),
            clientkey=await self.config.clientkey(),
        )
        await self.bridge.get_lights()

    @commands.group(name="hue")
    @checks.is_owner()
    async def _hue(self, ctx: commands.Context) -> None:
        """Commands for interacting with Hue lights"""
        pass

    @_hue.group(name="set")
    @checks.is_owner()
    async def hue_set(self, ctx: commands.Context) -> None:
        """Commands for setting hue settings"""
        pass

    @_hue.command(name="test")
    async def hue_test(self, ctx: commands.Context) -> None:
        """Testing"""
        if not self.bridge or not self.bridge.authed:
            await ctx.send("No IP has been set.")
            return
        for light in self.bridge.lights:
            await light.flash((1.0, 1.0), (0.0, 0.0), 10, 0.5)
        await ctx.tick()

    @_hue.before_invoke
    async def before_hue_commands(self, ctx: commands.Context):
        if self.bridge and not self.bridge.lights:
            if self.bridge.authed:
                await self.bridge.get_lights()

    @hue_set.command(name="connect")
    async def hue_connect(self, ctx: commands.Context, ip: Optional[str] = None) -> None:
        """Setup command if bridge cannot connect"""
        if ip is None:
            ip = await self.config.ip()
            if not ip:
                await ctx.send("No IP has been set or provided.")
                return
        else:
            await self.config.ip.set(ip)

        if self.bridge is None:
            await self.set_bridge()
        try:
            resp = await self.bridge.auth()
            await self.config.username.set(resp["success"]["username"])
            await self.config.clientkey.set(resp["success"]["clientkey"])
        except HueError as e:
            await ctx.send(e.description)
        else:
            await ctx.send("Connected to {ip}.".format(ip=ip))

    @_hue.command(name="brightness")
    async def brightness_set(
        self, ctx: commands.Context, brightness: int = 254, *, name: Optional[str] = None
    ) -> None:
        """
        Sets the brightness for lights

        `brightness` the level of brightness to set
        `name` the name of the light to adjust
        """
        if not self.bridge or not self.bridge.authed:
            await ctx.send("No IP has been set.")
            return

        for light in self.bridge.lights:
            if name is None or light.name.lower() == name.lower() and light.on:
                async with light:
                    light.set_brightness(brightness)
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
        if not self.bridge or not self.bridge.authed:
            await ctx.send("No IP has been set.")
            return

        for light in self.bridge.lights:
            if name is None or light.name.lower() == name.lower() and light.on:
                async with light:
                    light.set_colour_temperature(ct)
        await ctx.tick()

    @_hue.command(name="random")
    async def hue_random_colour(
        self, ctx: commands.Context, *, name: Optional[str] = None
    ) -> None:
        """
        Sets the light to a random colour

        `name` the name of the light to adjust
        """
        if not self.bridge or not self.bridge.authed:
            await ctx.send("No IP has been set.")
            return

        for light in self.bridge.lights:
            if name is None or light.name.lower() == name.lower() and light.on:
                async with light:
                    light.set_random_colour()
        await ctx.tick()

    @_hue.group(name="colour", aliases=["color"])
    async def _colour(self, ctx: commands.Context) -> None:
        """Sets the colour for lights"""
        if not self.bridge or not self.bridge.authed:
            await ctx.send("No IP has been set.")
            return
        pass

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
        if not self.bridge or not self.bridge.authed:
            await ctx.send("No IP has been set.")
            return

        for light in self.bridge.lights:
            if name is None or light.name.lower() == name.lower() and light.on:
                async with light:
                    light.set_rgb(red, green, blue)
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
        if not self.bridge or not self.bridge.authed:
            await ctx.send("No IP has been set.")
            return

        for light in self.bridge.lights:
            if name is None or light.name.lower() == name.lower() and light.on:
                async with light:
                    light.set_xy(x, y)
        await ctx.tick()

    @_colour.command(name="hex")
    async def hue_colour_hex(self, ctx: commands.Context, hex_code, *, name=None) -> None:
        """
        Attempt to set the colour based on hex values
        Not 100% accurate

        `hex` the hex code colour to try to change to
        `name` the name of the light to adjust
        """
        if not self.bridge or not self.bridge.authed:
            await ctx.send("No IP has been set.")
            return

        for light in self.bridge.lights:
            if name is None or light.name.lower() == name.lower() and light.on:
                async with light:
                    light.set_hex(hex_code)
        await ctx.tick()

    @_hue.command(name="switch")
    async def hue_switch(self, ctx: commands.Context, *, name=None) -> None:
        """
        Toggles lights on or off

        `name` the name of the light to adjust
        """
        if not self.bridge or not self.bridge.authed:
            await ctx.send("No IP has been set.")
            return

        for light in self.bridge.lights:
            if name is None or light.name.lower() == name.lower() and light.on:
                await light.switch()
        await ctx.tick()

    @_hue.command(name="off")
    async def turn_off(self, ctx: commands.Context, *, name=None) -> None:
        """
        Turns off light

        `name` the name of the light to adjust
        """
        if not self.bridge or not self.bridge.authed:
            await ctx.send("No IP has been set.")
            return

        for light in self.bridge.lights:
            if name is None or light.name.lower() == name.lower() and light.on:
                await light.turn_off()
        await ctx.tick()

    @_hue.command(name="on")
    async def turn_on(self, ctx: commands.Context, name=None) -> None:
        """
        Turns on Light

        `name` the name of the light to adjust
        """
        if not self.bridge or not self.bridge.authed:
            await ctx.send("No IP has been set.")
            return

        for light in self.bridge.lights:
            if name is None or light.name.lower() == name.lower() and light.on:
                await light.turn_on()
        await ctx.tick()
