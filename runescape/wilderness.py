from datetime import datetime, timedelta
from enum import Enum

from .helpers import RUNEDATE_EPOCH


class WildernessFlashEvents(Enum):
    spider_swarm = 0
    unnatural_outcrop = 1
    demon_stragglers = 2
    butterfly_swarm = 3
    king_black_dragon_rampage = 4
    forgotten_soldiers = 5
    surprising_seedlings = 6
    hellhound_pack = 7
    infernal_star = 8
    lost_souls = 9
    ramokee_incursion = 10
    displaced_energy = 11
    evil_bloodwood_tree = 12

    def __str__(self):
        return self.name.replace("_", " ").title()

    @property
    def special(self):
        return self in (
            WildernessFlashEvents.king_black_dragon_rampage,
            WildernessFlashEvents.infernal_star,
            WildernessFlashEvents.evil_bloodwood_tree,
        )

    def get_next(self, today: datetime) -> datetime:
        # represents the hours since the first spider swarm
        # we add 10 hours because the first spiderswarm in relation to the Runedate
        # is 10 hours after
        hours_since = int((int((today - RUNEDATE_EPOCH).total_seconds()) / 3600)) + 10
        # the offset mapping how many hours until this even should be next
        offset = hours_since % 13
        # the number of hours until this event should be nect
        hour = self.value - offset
        # Since the hour can be in the past and we don't care about the past
        # we add 13 hours, the total number of events.
        if hour < 0:
            hour += 13
        # add 1 hour because it's off by 1 hour
        next_event = today + timedelta(hours=hour + 1)
        return next_event
