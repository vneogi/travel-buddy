"""SPEC-41 Phase A1: Canonical structured-hours evaluator.

Evaluates whether an activity of a given duration fits inside the
opening hours of a venue on a specific day.  Operates entirely on
static catalog data -- never calls Maps, LLMs, datetime.now(), or
any network service.

The structured hours format is::

    {
        "mon": [["08:00", "12:00"], ["13:00", "16:00"]],
        "tue": [],          # explicitly closed
        ...
    }

Weekday keys: mon tue wed thu fri sat sun.
Each window is [open_time, close_time] in HH:MM 24-hour format.

close > open  -> same-day window
close <= open -> overnight window ending the following day
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


class HoursResult(str, Enum):
    """Three-state result for a slot evaluation."""

    FITS = "fits"
    CLOSED = "closed"
    UNKNOWN = "unknown"


_WEEKDAY_KEYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


def _weekday_key(dt: datetime) -> str:
    """Return the 3-letter weekday key for a timezone-aware datetime."""
    return _WEEKDAY_KEYS[dt.weekday()]


def _prev_weekday_key(dt: datetime) -> str:
    """Return the weekday key for the calendar day before *dt*."""
    prev = dt - timedelta(days=1)
    return _WEEKDAY_KEYS[prev.weekday()]


def _parse_hhmm(text: str) -> Optional[timedelta]:
    """Parse 'HH:MM' into a timedelta offset from midnight.

    Returns None if the text is malformed.
    """
    try:
        parts = text.strip().split(":")
        if len(parts) != 2:
            return None
        h, m = int(parts[0]), int(parts[1])
        if not (0 <= h <= 23 and 0 <= m <= 59):
            return None
        return timedelta(hours=h, minutes=m)
    except (ValueError, AttributeError):
        return None


def _slot_fits_window(
    start_offset: timedelta,
    end_offset: timedelta,
    win_open: timedelta,
    win_close: timedelta,
) -> bool:
    """Check if [start_offset, end_offset] fits inside [win_open, win_close].

    All offsets are relative to midnight of the *window's opening day*.
    Overnight windows have win_close > 24h (next-day close).
    """
    return start_offset >= win_open and end_offset <= win_close


def check_slot(
    hours_structured: Optional[Dict[str, Any]],
    start: datetime,
    duration_minutes: int,
) -> HoursResult:
    """Evaluate whether an activity fits inside the venue's opening hours.

    Parameters
    ----------
    hours_structured:
        The structured opening-hours dict, or None / malformed.
    start:
        A timezone-aware, destination-local datetime for the activity start.
    duration_minutes:
        Positive duration in minutes.

    Returns
    -------
    HoursResult
        ``fits``    -- the entire activity fits in one declared window.
        ``closed``  -- the venue is explicitly closed at this time.
        ``unknown`` -- data is null, malformed, or input is invalid.

    Raises
    ------
    ValueError
        If *start* is naive (no tzinfo) or *duration_minutes* <= 0.
        These are programmer errors, not catalog-data issues.
    """
    # ---- Programmer-input guards (raise, not unknown) --------------------
    if start.tzinfo is None:
        raise ValueError("start must be timezone-aware; got naive datetime")
    if duration_minutes <= 0:
        raise ValueError(f"duration_minutes must be positive; got {duration_minutes}")

    # ---- Catalog-data guards (unknown, never raise) ----------------------
    if not isinstance(hours_structured, dict):
        return HoursResult.UNKNOWN

    # Validate the entire structure upfront.  Any malformed or incomplete
    # data makes the result unknowable -- we must never guess "open".
    if not _validate_structure(hours_structured):
        return HoursResult.UNKNOWN

    day_key = _weekday_key(start)
    prev_key = _prev_weekday_key(start)
    today_windows = hours_structured[day_key]  # safe: validated above
    prev_windows = hours_structured[prev_key]

    # ---- Build slot offsets relative to today's midnight -----------------
    midnight = start.replace(hour=0, minute=0, second=0, microsecond=0)
    slot_open = start - midnight
    slot_close = slot_open + timedelta(minutes=duration_minutes)

    # 1) Today's own windows (may be empty => skip to overnight check)
    for win in today_windows:
        w_open, w_close = _parse_window_safe(win)  # validated
        if w_close > w_open:
            # Same-day window
            if _slot_fits_window(slot_open, slot_close, w_open, w_close):
                return HoursResult.FITS
        else:
            # Overnight window (close <= open): opens today, closes tomorrow.
            eff_close = w_close + timedelta(days=1)
            if _slot_fits_window(slot_open, slot_close, w_open, eff_close):
                return HoursResult.FITS

    # 2) Previous day's overnight windows that extend into today.
    #    This runs even when today_windows is [] -- an explicitly closed
    #    day can still be reached by yesterday's overnight window.
    for win in prev_windows:
        w_open, w_close = _parse_window_safe(win)  # validated
        if w_close <= w_open:
            # Overnight: opened yesterday, closes today.
            eff_open = timedelta(0)  # midnight (earliest today)
            eff_close = w_close
            if _slot_fits_window(slot_open, slot_close, eff_open, eff_close):
                return HoursResult.FITS

    # ---- No window matched -> closed ------------------------------------
    return HoursResult.CLOSED


def _validate_structure(hours: Dict[str, Any]) -> bool:
    """Return True only when the entire structure is well-formed.

    Requirements:
    - All seven weekday keys present.
    - Every value is a list.
    - Every element inside each list is a 2-element [HH:MM, HH:MM].
    """
    for key in _WEEKDAY_KEYS:
        windows = hours.get(key)
        if windows is None or not isinstance(windows, list):
            return False
        for win in windows:
            if _parse_window(win) is None:
                return False
    return True


def _parse_window_safe(win: Any) -> tuple:
    """Parse a validated window.  Only call after _validate_structure."""
    result = _parse_window(win)
    assert result is not None, "_parse_window_safe called on unvalidated data"
    return result


def _parse_window(win: Any) -> Optional[tuple]:
    """Parse a single [open, close] window.

    Returns (open_td, close_td) or None if malformed.
    """
    if not isinstance(win, (list, tuple)) or len(win) != 2:
        return None
    o = _parse_hhmm(win[0]) if isinstance(win[0], str) else None
    c = _parse_hhmm(win[1]) if isinstance(win[1], str) else None
    if o is None or c is None:
        return None
    return o, c
