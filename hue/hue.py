from random import choice as randchoice
from datetime import datetime as dt
from redbot.core import commands
import discord
from redbot.core import Config
from redbot.core import checks
import random
import os
import asyncio
from phue import Bridge

class Hue(getattr(commands, "Cog", object)):
    """
        Control philips hue light on the same network as the bot
    """

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, 1384534876565)
        default_global = {"ip":None}
        self.bridge = None
        self.lights = None

    async def get_bridge(self):
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

    # @commands.command(pass_context=True)
    async def oilersgoal(self):
        if not await self.get_bridge():
            await ctx.send("No IP has been set.")
            return
        old_lights = {}
        for light in self.lights:
            old_lights[light.name] = [light.on, light.colortemp]
        for i in range(10):
            await self.oilers_hex_set(1.0, 1.0)
            await asyncio.sleep(0.5)
            await self.oilers_hex_set(0, 0)
            await asyncio.sleep(0.5)
        for light in self.lights:
            light.on = old_lights[light.name][0]
            light.colortemp = old_lights[light.name][1]


    async def oilers_hex_set(self, x:float, y:float, *, name=None):
        """Sets the colour for Oilers Goals"""
        if x > 1.0 or x < 0.0:
            x = 1.0
        if y > 1.0 or y < 0.0:
            y = 1.0
        for light in self.lights:
            if not light.on:
                light.on = True
            light.xy = [x, y]

    @commands.group(pass_context=True, name="hue")
    @checks.is_owner()
    async def _hue(self, ctx):
        """Commands for interacting with Hue lights"""
        pass

    @_hue.command(name="connect")
    async def hue_connect(self):
        """Setup command if bridge cannot connect"""
        if not await self.get_bridge():
            await ctx.send("No IP has been set.")
            return
        self.bridge.connect()

    @_hue.command(pass_context=True, name="set")
    async def hue_setup(self, ctx, ip):
        """
            Set the IP address of the hue bridge

            `ip` is the bridges IP address
        """
        await self.config.ip.set(ip)
        self.bridge = Bridge(await self.config.ip())
        self.lights = self.bridge.lights 

    @_hue.command(pass_context=True, name="check")
    async def check_api(self, ctx):
        """Gets light data from bridge and prints to terminal"""
        if not await self.get_bridge():
            await ctx.send("No IP has been set.")
            return
        print(self.bridge.get_api())

    async def max_min_check(self, value, max, min):
        if value > max:
            return max
        if value < min:
            return min
        else:
            return value

    @_hue.command(pass_context=True, name="brightness")
    async def brightness_set(self, ctx, brightness:int=254, *, name=None):
        """
            Sets the brightness for lights

            `brightness` the level of brightness to set
            `name` the name of the light to adjust
        """
        if not await self.get_bridge():
            await ctx.send("No IP has been set.")
            return
        brightness = await self.max_min_check(brightness, 254, 0)
        for light in self.lights:
            if name is None or light.name.lower() == name.lower() and light.on:
                light.brightness = brightness

    @_hue.command(pass_context=True, name="temp", aliases=["ct", "colourtemp", "temperature"])
    async def colourtemp_set(self, ctx, ct:int=500, *, name=None):
        """
            Sets the colour temperature for lights

            `ct` must be a number the colour temperature to set
            `name` the name of the light to adjust
        """
        if not await self.get_bridge():
            await ctx.send("No IP has been set.")
            return
        ct = await self.max_min_check(ct, 600, 154)
        for light in self.lights:
            if name is None or light.name.lower() == name.lower() and light.on:
                light.colortemp = ct

    @_hue.command(pass_context=True, name="hue")
    async def hue_set(self, ctx, hue:int=25000, *, name=None):
        """
            Sets the hue for lights

            `hue` must be a number the hue value to set the light to
            `name` the name of the light to adjust 
        """
        if not await self.get_bridge():
            await ctx.send("No IP has been set.")
            return
        for light in self.lights:
            if name is None or light.name.lower() == name.lower() and light.on:
                light.hue = hue

    @_hue.command(pass_context=True, name="saturation", aliases=["sat"])
    async def saturation_set(self, ctx, saturation:int=254, *, name=None):
        """
            Sets the saturation for lights

            `saturation` must be a number the saturation value to set the light to
            `name` the name of the light to adjust
        """
        if not await self.get_bridge():
            await ctx.send("No IP has been set.")
            return
        saturation = await self.max_min_check(saturation, 254, 0)
        for light in self.lights:
            if name is None or light.name.lower() == name.lower() and light.on:
                light.saturation = saturation

    @_hue.command(pass_context=True, name="random")
    async def hue_random_colour(self, ctx, *, name=None):
        """
            Sets the light to a random colour

            `name` the name of the light to adjust
        """
        if not await self.get_bridge():
            await ctx.send("No IP has been set.")
            return
        colours = [random.random(), random.random()]
        for light in self.lights:
            if name is None or light.name.lower() == name.lower() and light.on:
                light.xy = colours

    @_hue.command(pass_context=True, name="colourloop", aliases=["cl"])
    async def hue_colourloop(self, ctx, *, name=None):
        """
            Toggles the light on colour looping all colours

            `name` the name of the light to adjust
        """
        if not await self.get_bridge():
            await ctx.send("No IP has been set.")
            return
        for light in self.lights:
            if name is None or light.name.lower() == name.lower():
                if light.effect != "colorloop" and light.on:
                    light.effect = "colorloop"
                    continue
                if light.effect == "colorloop" and light.on:
                    light.effect = "none"
                    continue

    @_hue.group(pass_context=True, name="colour")
    async def _colour(self, ctx):
        """Sets the colour for lights"""
        if not await self.get_bridge():
            await ctx.send("No IP has been set.")
            return
        pass

    async def rgb_to_xy(self, red:float, green:float, blue:float):
        X = 0.4124*red + 0.3576*green + 0.1805*blue
        Y = 0.2126*red + 0.7152*green + 0.0722*blue
        Z = 0.0193*red + 0.1192*green + 0.9505*blue
        try:
            x = X / (X + Y + Z)
            y = Y / (X + Y + Z)
        except ZeroDivisionError:
            x = 1.0
            y = 1.0
        return x, y

    @_colour.command(pass_context=True, name="rgb")
    async def hue_colour_rgb(self, ctx, red:float, green:float, blue:float, *, name=None):
        """
            Sets the colour using RGB colour coordinates

            `red` must be a number the red value to set
            `green` must be a number the green value to set
            `blue` must be a number the blue value to set
            `name` the name of the light to adjust
        """
        if not await self.get_bridge():
            await ctx.send("No IP has been set.")
            return
        x, y = await self.rgb_to_xy(red, green, blue)
        for light in self.lights:
            if name is None or light.name.lower() == name.lower() and light.on:
                light.xy = [x, y]

    @_colour.command(pass_context=True, name="xy", aliases=["xyz"])
    async def hue_colour_xy(self, ctx, x:float, y:float, *, name=None):
        """
            Sets the colour using xyz colour values

            `x` must be a number the x value to set
            `y` must be a number the y value to set
            `name` the name of the light to adjust
            Note: The z value is determined from two other values
        """
        if not await self.get_bridge():
            await ctx.send("No IP has been set.")
            return
        if x > 1.0 or x < 0.0:
            x = 1.0
        if y > 1.0 or y < 0.0:
            y = 1.0
        for light in self.lights:
            if name is None or light.name.lower() == name.lower() and light.on:
                light.xy = [x, y]

    @_colour.command(pass_context=True, name="hex")
    async def hue_colour_hex(self, ctx, hex, *, name=None):
        """
            Attempt to set the colour based on hex values
            Not 100% accurate

            `hex` the hex code colour to try to change to
            `name` the name of the light to adjust
        """
        if not await self.get_bridge():
            await ctx.send("No IP has been set.")
            return
        if "#" in hex:
            hex.replace("#", "")
        r, g, b = tuple(int(hex[i:i+2], 16) for i in (0, 2 ,4))
        x, y = await self.rgb_to_xy(r, g, b)
        for light in self.lights:
            if name is None or light.name.lower() == name.lower() and light.on:
                light.xy = [x, y]

    @_hue.command(pass_context=True, name="test")
    async def hue_test(self, ctx, cl1:float, cl2:float):
        """Testing function"""
        if not await self.get_bridge():
            await ctx.send("No IP has been set.")
            return
        for light in self.lights:
            light.xy = [cl1, cl2]

    @_hue.command(pass_context=True, name="switch")
    async def hue_switch(self, ctx, *, name=None):
        """
            Toggles lights on or off

            `name` the name of the light to adjust
        """
        if not await self.get_bridge():
            await ctx.send("No IP has been set.")
            return
        for light in self.lights:
            if name is None or light.name.lower() == name.lower():
                if light.on:
                    light.on = False
                    continue
                if not light.on:
                    light.on = True
                    continue

    @_hue.command(pass_context=True, name="off")
    async def turn_off(self, ctx, *, name=None):
        """
            Turns off light

            `name` the name of the light to adjust
        """
        if not await self.get_bridge():
            await ctx.send("No IP has been set.")
            return
        for light in self.lights:
            if name is None or light.name.lower() == name.lower():
                light.on = False

    @_hue.command(pass_context=True, name="on")
    async def turn_on(self, ctx, name=None):
        """
            Turns on Light

            `name` the name of the light to adjust
        """
        if not await self.get_bridge():
            await ctx.send("No IP has been set.")
            return
        for light in self.lights:
            if name is None or light.name.lower() == name.lower():
                light.on = True
