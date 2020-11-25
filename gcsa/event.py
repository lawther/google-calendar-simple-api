from functools import total_ordering

from beautiful_date import BeautifulDate
from tzlocal import get_localzone
from datetime import datetime, date, timedelta

from .attachment import Attachment
from .attendee import Attendee
from .reminders import PopupReminder, EmailReminder
from .util.date_time_util import insure_localisation


class Visibility:
    """ Possible values of the event visibility.

    * DEFAULT - Uses the default visibility for events on the calendar. This is the default value.
    * PUBLIC - The event is public and event details are visible to all readers of the calendar.
    * PRIVATE - The event is private and only event attendees may view event details.
    """

    DEFAULT = "default"
    PUBLIC = "public"
    PRIVATE = "private"


@total_ordering
class Event:
    def __init__(self,
                 summary,
                 start,
                 end=None,
                 *,
                 timezone=str(get_localzone()),
                 event_id=None,
                 description=None,
                 location=None,
                 recurrence=None,
                 color=None,
                 visibility=Visibility.DEFAULT,
                 attendees=None,
                 attachments=None,
                 conference_solution=None,
                 reminders=None,
                 default_reminders=False,
                 minutes_before_popup_reminder=None,
                 minutes_before_email_reminder=None,
                 _updated=None,
                 **other):
        """
        :param summary:
                Title of the event.
        :param start:
                Starting date/datetime.
        :param end:
                Ending date/datetime. If 'end' is not specified, event is considered as a 1-day or 1-hour event
                if 'start' is date or datetime respectively.
        :param timezone:
                Timezone formatted as an IANA Time Zone Database name, e.g. "Europe/Zurich". By default,
                the computers local timezone is used if it is configured. UTC is used otherwise.
        :param event_id:
                Opaque identifier of the event. By default is generated by the server. You can specify id as a
                5-1024 long string of characters used in base32hex ([a-vA-V0-9]). The ID must be unique per
                calendar.
        :param description:
                Description of the event.
        :param location:
                Geographic location of the event as free-form text.
        :param recurrence:
                RRULE/RDATE/EXRULE/EXDATE string or list of such strings. See :py:mod:`~gcsa.recurrence`
        :param color:
                Color id referring to an entry from colors endpoint (list_event_colors)
        :param visibility:
                Visibility of the event. Default is default visibility for events on the calendar.
                See :py:class:`~gcsa.event.Visibility`
        :param attendees:
                Attendee or list of attendees. See :py:class:`~gcsa.attendee.Attendee`.
                Each attendee may be given as email string or :py:class:`~gcsa.attendee.Attendee` object.
        :param attachments:
                Attachment or list of attachments. See :py:class:`~gcsa.attachment.Attachment`
        :param conference_solution:
                :py:class:`~gcsa.conference.ConferenceSolutionCreateRequest` object to create a new conference
                or :py:class:`~gcsa.conference.ConferenceSolution` object for existing conference.
        :param reminders:
                Reminder or list of reminder objects. See :py:mod:`~gcsa.reminders`
        :param default_reminders:
                Whether the default reminders of the calendar apply to the event.
        :param minutes_before_popup_reminder:
                Minutes before popup reminder or None if reminder is not needed.
        :param minutes_before_email_reminder:
                Minutes before email reminder or None if reminder is not needed.
        :param _updated:
                Last modification time of the event. Read-only.
        :param other:
                Other fields that should be included in request json. Will be included as they are.
        """

        def assure_list(obj):
            return [] if obj is None else obj if isinstance(obj, list) else [obj]

        self.timezone = timezone
        self.start = start
        if end:
            self.end = end
        elif isinstance(start, datetime):
            self.end = start + timedelta(hours=1)
        elif isinstance(start, date):
            self.end = start + timedelta(days=1)

        if isinstance(self.start, datetime) and isinstance(self.end, datetime):
            self.start = insure_localisation(self.start, timezone)
            self.end = insure_localisation(self.end, timezone)
        elif isinstance(self.start, datetime) or isinstance(self.end, datetime):
            raise TypeError('Start and end must either both be date or both be datetime.')

        def insure_date(d):
            """Converts d to date if it is of type BeautifulDate."""
            if isinstance(d, BeautifulDate):
                return date(year=d.year, month=d.month, day=d.day)
            else:
                return d

        self.start = insure_date(self.start)
        self.end = insure_date(self.end)
        self.updated = _updated

        attendees = [self._ensure_attendee_from_email(a) for a in assure_list(attendees)]
        reminders = assure_list(reminders)

        if len(reminders) > 5:
            raise ValueError('The maximum number of override reminders is 5.')

        if default_reminders and reminders:
            raise ValueError('Cannot specify both default reminders and overrides at the same time.')

        self.event_id = event_id
        self.summary = summary
        self.description = description
        self.location = location
        self.recurrence = assure_list(recurrence)
        self.color_id = color
        self.visibility = visibility
        self.attendees = attendees
        self.attachments = assure_list(attachments)
        self.conference_solution = conference_solution
        self.reminders = reminders
        self.default_reminders = default_reminders
        self.other = other

        if minutes_before_popup_reminder is not None:
            self.add_popup_reminder(minutes_before_popup_reminder)
        if minutes_before_email_reminder is not None:
            self.add_email_reminder(minutes_before_email_reminder)

    @property
    def id(self):
        return self.event_id

    def add_attendee(self, attendee):
        """Adds attendee to an event. See :py:class:`~gcsa.attendee.Attendee`.
        Attendee may be given as email string or :py:class:`~gcsa.attendee.Attendee` object."""
        self.attendees.append(self._ensure_attendee_from_email(attendee))

    def add_attachment(self, file_url, title, mime_type):
        """Adds attachment to an event. See :py:class:`~gcsa.attachment.Attachment`"""
        self.attachments.append(Attachment(title=title, file_url=file_url, mime_type=mime_type))

    def add_email_reminder(self, minutes_before_start=60):
        """Adds email reminder to an event. See :py:class:`~gcsa.reminders.EmailReminder`"""
        self.add_reminder(EmailReminder(minutes_before_start))

    def add_popup_reminder(self, minutes_before_start=30):
        """Adds popup reminder to an event. See :py:class:`~gcsa.reminders.PopupReminder`"""
        self.add_reminder(PopupReminder(minutes_before_start))

    def add_reminder(self, reminder):
        """Adds reminder to an event. See :py:mod:`~gcsa.reminders`"""
        if len(self.reminders) > 4:
            raise ValueError('The maximum number of override reminders is 5.')
        self.reminders.append(reminder)

    @staticmethod
    def _ensure_attendee_from_email(attendee_or_email):
        """If attendee_or_email is email string, returns created :py:class:`~gcsa.attendee.Attendee`
        object with the given email."""
        if isinstance(attendee_or_email, str):
            return Attendee(email=attendee_or_email)
        else:
            return attendee_or_email

    def __str__(self):
        return '{} - {}'.format(self.start, self.summary)

    def __repr__(self):
        return '<Event {}>'.format(self.__str__())

    def __lt__(self, other):
        def insure_datetime(d, timezone):
            if type(d) == date:
                return insure_localisation(datetime(year=d.year, month=d.month, day=d.day), timezone)
            else:
                return d

        start = insure_datetime(self.start, self.timezone)
        end = insure_datetime(self.end, self.timezone)

        other_start = insure_datetime(other.start, other.timezone)
        other_end = insure_datetime(other.end, other.timezone)

        return (start, end) < (other_start, other_end)

    def __eq__(self, other):
        return isinstance(other, Event) \
               and self.start == other.start \
               and self.end == other.end \
               and self.event_id == other.event_id \
               and self.summary == other.summary \
               and self.description == other.description \
               and self.location == other.location \
               and self.recurrence == other.recurrence \
               and self.color_id == other.color_id \
               and self.visibility == other.visibility \
               and self.attendees == other.attendees \
               and self.attachments == other.attachments \
               and self.reminders == other.reminders \
               and self.default_reminders == other.default_reminders \
               and self.other == other.other
