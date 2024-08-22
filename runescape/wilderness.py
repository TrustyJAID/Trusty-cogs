from datetime import datetime, timedelta
from enum import Enum

from .helpers import RUNEDATE_EPOCH


class WildernessFlashEvents(Enum):
    spider_swarm = 0
    unnatural_outcrop = 1
    stryke_the_wyrm = 2
    demon_stragglers = 3
    butterfly_swarm = 4
    king_black_dragon_rampage = 5
    forgotten_soldiers = 6
    surprising_seedlings = 7
    hellhound_pack = 8
    infernal_star = 9
    lost_souls = 10
    ramokee_incursion = 11
    displaced_energy = 12
    evil_bloodwood_tree = 13

    def __str__(self):
        return self.name.replace("_", " ").title().replace("The", "the")

    def __len__(self):
        return len(WildernessFlashEvents)

    @property
    def special(self):
        return self in (
            WildernessFlashEvents.stryke_the_wyrm,
            WildernessFlashEvents.king_black_dragon_rampage,
            WildernessFlashEvents.infernal_star,
            WildernessFlashEvents.evil_bloodwood_tree,
        )

    def get_next(self, today: datetime) -> datetime:
        # represents the hours since the first spider swarm
        # we add 14 hours because the first spiderswarm in relation to the Runedate
        # is 14 hours after
        # this offset needs to be adjusted since the addition of the stryke the wyrm event
        hours_since = int((int((today - RUNEDATE_EPOCH).total_seconds()) / 3600)) + 14
        # the offset mapping how many hours until this even should be next
        offset = hours_since % len(self)
        # the number of hours until this event should be next
        hour = self.value - offset
        # Since the hour can be in the past and we don't care about the past
        # we add the total number of events.
        if hour < 0:
            hour += len(self)
        # add 1 hour because it's off by 1 hour
        next_event = today + timedelta(hours=hour + 1)
        return next_event
