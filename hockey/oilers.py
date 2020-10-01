import asyncio
import functools

from phue import Bridge


class Oilers:
    def __init__(self, bot):
        self.bot = bot
        self.bridge = Bridge("192.168.50.123")
        self.lights = self.bridge.lights
        self.bridge2 = Bridge("192.168.50.163")
        self.lights2 = self.bridge2.lights
        self.cur_lights = {}
        self.cur_lights2 = {}

    def goal_lights(self):
        async def task():
            task = functools.partial(self.get_current_lights_setting)
            task = self.bot.loop.run_in_executor(None, task)
            try:
                await asyncio.wait_for(task, timeout=60)
            except asyncio.TimeoutError:
                return
            for i in range(5):
                task = functools.partial(self.oilers_hex_set, x=1.0, y=1.0)
                task = self.bot.loop.run_in_executor(None, task)
                try:
                    await asyncio.wait_for(task, timeout=60)
                except asyncio.TimeoutError:
                    pass
                # await self.oilers_hex_set(1.0, 1.0)
                await asyncio.sleep(0.5)
                task = functools.partial(self.oilers_hex_set, x=0, y=0)
                task = self.bot.loop.run_in_executor(None, task)
                try:
                    await asyncio.wait_for(task, timeout=60)
                except asyncio.TimeoutError:
                    pass
                # await self.oilers_hex_set(0, 0)
                await asyncio.sleep(0.5)
            task = functools.partial(self.reset_light_setting)
            task = self.bot.loop.run_in_executor(None, task)
            try:
                await asyncio.wait_for(task, timeout=60)
            except asyncio.TimeoutError:
                return

        return self.bot.loop.create_task(task())

    def reset_light_setting(self):
        for light in self.lights:
            old_temp = self.cur_lights[light.name][1]
            if old_temp < 154:
                old_temp = 154
            if old_temp > 500:
                old_temp = 499
            light.colortemp = old_temp
            light.on = self.cur_lights[light.name][0]
        for light in self.lights2:
            old_temp = self.cur_lights2[light.name][1]
            if old_temp < 154:
                old_temp = 154
            if old_temp > 500:
                old_temp = 499
            light.colortemp = old_temp
            light.on = self.cur_lights2[light.name][0]
        return

    def get_current_lights_setting(self):
        for light in self.lights:
            self.cur_lights[light.name] = [light.on, light.colortemp]
        for light in self.lights2:
            self.cur_lights2[light.name] = [light.on, light.colortemp]
        return

    def oilers_hex_set(self, x: float, y: float):
        """Sets the colour for Oilers Goals"""
        if x > 1.0 or x < 0.0:
            x = 1.0
        if y > 1.0 or y < 0.0:
            y = 1.0
        for light in self.lights:
            if not light.on:
                light.on = True
            light.xy = [x, y]
        for light in self.lights2:
            if not light.on:
                light.on = True
            light.xy = [x, y]
