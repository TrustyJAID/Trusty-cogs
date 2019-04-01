# https://github.com/mikeshardmind/SinbadCogs/blob/v3/scheduler/time_utils.py
# this is all thanks to sinbad for putting it together and making it easy to work with
import re
from datetime import datetime as dt, timedelta
from typing import Callable, Optional

import pytz
from dateutil.tz import gettz
from dateutil import parser

TIME_RE_STRING = r"\s?".join(
    [
        r"((?P<days>\d+?)\s?(d(ays?)?))?",
        r"((?P<hours>\d+?)\s?(hours?|hrs|hr?))?",
        r"((?P<minutes>\d+?)\s?(minutes?|mins?|m))?",
        r"((?P<seconds>\d+?)\s?(seconds?|secs?|s))?",
    ]
)

TIME_RE = re.compile(TIME_RE_STRING, re.I)


def gen_tzinfos():
    for zone in pytz.common_timezones:
        try:
            tzdate = pytz.timezone(zone).localize(dt.utcnow(), is_dst=None)
        except pytz.NonExistentTimeError:
            pass
        else:
            tzinfo = gettz(zone)

            if tzinfo:
                yield tzdate.tzname(), tzinfo


def parse_time(datetimestring: str):
    ret = parser.parse(datetimestring, tzinfos=dict(gen_tzinfos()))
    ret = ret.astimezone(pytz.utc)
    return ret


def td_format(td_object: timedelta, _: Callable = lambda x: x) -> str:
    seconds = int(td_object.total_seconds())
    periods = [
        (_("year"), _("years"), 60 * 60 * 24 * 365),
        (_("month"), _("months"), 60 * 60 * 24 * 30),
        (_("day"), _("days"), 60 * 60 * 24),
        (_("hour"), _("hours"), 60 * 60),
        (_("minute"), _("minutes"), 60),
        (_("second"), _("seconds"), 1),
    ]

    strings = []
    for period_name, plural_period_name, period_seconds in periods:
        if seconds >= period_seconds:
            period_value, seconds = divmod(seconds, period_seconds)
            if period_value == 0:
                continue
            unit = plural_period_name if period_value > 1 else period_name
            strings.append(f"{period_value} {unit}")
    return_str = ", ".join(strings)
    if not return_str:
        return_str = _("0 seconds")
    return return_str


def parse_timedelta(argument: str) -> Optional[timedelta]:
    matches = TIME_RE.match(argument)
    if matches:
        params = {k: int(v) for k, v in matches.groupdict().items() if v is not None}
        if params:
            return timedelta(**params)
    return None