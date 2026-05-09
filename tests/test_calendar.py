"""中国工作日日历测试。"""

from datetime import date

from xushi.calendar import ChinaWorkdayCalendar


def test_china_calendar_treats_adjusted_sunday_as_workday() -> None:
    calendar = ChinaWorkdayCalendar()

    assert calendar.is_workday(date(2026, 1, 4)) is True


def test_china_calendar_treats_spring_festival_holiday_as_non_workday() -> None:
    calendar = ChinaWorkdayCalendar()

    assert calendar.is_workday(date(2026, 2, 17)) is False


def test_china_calendar_rolls_forward_to_next_workday() -> None:
    calendar = ChinaWorkdayCalendar()

    assert calendar.next_workday(date(2026, 2, 17)) == date(2026, 2, 24)


def test_china_calendar_uses_full_2026_adjusted_workdays() -> None:
    calendar = ChinaWorkdayCalendar()

    assert calendar.is_workday(date(2026, 2, 14)) is True
    assert calendar.is_workday(date(2026, 2, 28)) is True
    assert calendar.is_workday(date(2026, 5, 9)) is True
    assert calendar.is_workday(date(2026, 9, 20)) is True
    assert calendar.is_workday(date(2026, 10, 10)) is True


def test_china_calendar_uses_full_2026_holidays() -> None:
    calendar = ChinaWorkdayCalendar()

    assert calendar.is_workday(date(2026, 1, 1)) is False
    assert calendar.is_workday(date(2026, 5, 5)) is False
    assert calendar.is_workday(date(2026, 6, 19)) is False
    assert calendar.is_workday(date(2026, 9, 25)) is False
    assert calendar.is_workday(date(2026, 10, 7)) is False


def test_china_calendar_exposes_holiday_names() -> None:
    calendar = ChinaWorkdayCalendar()

    assert calendar.holiday_name(date(2026, 1, 1)) == "元旦"
    assert calendar.holiday_name(date(2026, 2, 17)) == "春节"
    assert calendar.holiday_name(date(2026, 4, 4)) == "清明节"
    assert calendar.holiday_name(date(2026, 5, 5)) == "劳动节"
    assert calendar.holiday_name(date(2026, 6, 19)) == "端午节"
    assert calendar.holiday_name(date(2026, 9, 25)) == "中秋节"
    assert calendar.holiday_name(date(2026, 10, 7)) == "国庆节"
    assert calendar.holiday_name(date(2026, 3, 2)) is None


def test_china_calendar_exposes_adjusted_workday_names() -> None:
    calendar = ChinaWorkdayCalendar()

    assert calendar.adjusted_workday_name(date(2026, 1, 4)) == "元旦"
    assert calendar.adjusted_workday_name(date(2026, 2, 14)) == "春节"
    assert calendar.adjusted_workday_name(date(2026, 5, 9)) == "劳动节"
    assert calendar.adjusted_workday_name(date(2026, 9, 20)) == "中秋节"
    assert calendar.adjusted_workday_name(date(2026, 10, 10)) == "国庆节"
    assert calendar.adjusted_workday_name(date(2026, 3, 2)) is None
