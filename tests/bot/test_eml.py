from datetime import UTC, datetime
from email import message_from_bytes
from email.policy import default as default_policy
from types import SimpleNamespace

from aiogram.types import Chat, Message, MessageOriginChannel, MessageOriginHiddenUser, MessageOriginUser, User

from bot.eml import (
    NO_SUBJECT,
    PLACEHOLDER_ADDRESS,
    build_eml,
    build_eml_from_message,
    sender_from_message,
    subject_from_text,
)

SENT_AT = datetime(2026, 9, 1, 11, 25, tzinfo=UTC)


def _parse(raw):
    # The default policy yields an EmailMessage, so get_content() decodes for us.
    return message_from_bytes(raw, policy=default_policy)


def _message(text="hello", origin=None, date=SENT_AT):
    return Message.model_construct(
        message_id=1,
        date=date,
        chat=Chat.model_construct(id=1, type="private"),
        text=text,
        forward_origin=origin,
    )


class TestSubjectFromText:
    def test_uses_the_first_line(self):
        assert subject_from_text("Invoice overdue\nrest of the body") == "Invoice overdue"

    def test_skips_leading_blank_lines(self):
        assert subject_from_text("\n\n  Real subject\nbody") == "Real subject"

    def test_truncates_to_80_chars(self):
        subject = subject_from_text("x" * 200)
        assert len(subject) == 80

    def test_placeholder_when_empty(self):
        assert subject_from_text("   \n\n ") == NO_SUBJECT


class TestBuildEml:
    def test_parses_as_an_email_with_required_headers(self):
        parsed = _parse(build_eml("Invoice overdue\nPay now.", sent_at=SENT_AT))

        assert parsed["From"] == PLACEHOLDER_ADDRESS
        assert parsed["Subject"] == "Invoice overdue"
        assert parsed["Date"] is not None

    def test_body_is_the_full_text(self):
        text = "Invoice overdue\nPay now, please."
        parsed = _parse(build_eml(text, sent_at=SENT_AT))

        assert parsed.get_content().strip() == text

    def test_sender_name_becomes_the_display_part(self):
        parsed = _parse(build_eml("hi", sender="Alice Smith", sent_at=SENT_AT))

        assert "Alice Smith" in parsed["From"]
        assert PLACEHOLDER_ADDRESS in parsed["From"]

    def test_unicode_body_survives_the_round_trip(self):
        text = "Рахунок прострочено\nСплатіть, будь ласка."
        parsed = _parse(build_eml(text, sent_at=SENT_AT))

        assert parsed.get_content().strip() == text

    def test_date_is_the_given_moment(self):
        parsed = _parse(build_eml("hi", sent_at=SENT_AT))

        assert "01 Sep 2026" in parsed["Date"]

    def test_defaults_to_now_without_a_date(self):
        parsed = _parse(build_eml("hi"))

        assert parsed["Date"] is not None


class TestBuildEmlFromMessage:
    def test_plain_text_message_has_no_sender_name(self):
        parsed = _parse(build_eml_from_message(_message("Just some text")))

        assert parsed["From"] == PLACEHOLDER_ADDRESS
        assert parsed["Subject"] == "Just some text"

    def test_forward_from_a_user(self):
        origin = MessageOriginUser.model_construct(
            type="user",
            date=SENT_AT,
            sender_user=User.model_construct(id=7, is_bot=False, first_name="Bob", last_name="Jones"),
        )
        parsed = _parse(build_eml_from_message(_message("Urgent: verify your account", origin=origin)))

        assert "Bob Jones" in parsed["From"]
        assert parsed["Subject"] == "Urgent: verify your account"

    def test_forward_from_a_hidden_user(self):
        origin = MessageOriginHiddenUser.model_construct(
            type="hidden_user", date=SENT_AT, sender_user_name="Hidden Sender"
        )
        parsed = _parse(build_eml_from_message(_message("hi", origin=origin)))

        assert "Hidden Sender" in parsed["From"]

    def test_forward_from_a_channel(self):
        origin = MessageOriginChannel.model_construct(
            type="channel",
            date=SENT_AT,
            chat=Chat.model_construct(id=-100, type="channel", title="Deals Channel"),
            message_id=5,
        )
        parsed = _parse(build_eml_from_message(_message("50% off", origin=origin)))

        assert "Deals Channel" in parsed["From"]

    def test_forward_date_is_the_message_date(self):
        parsed = _parse(build_eml_from_message(_message("hi")))

        assert "01 Sep 2026" in parsed["Date"]

    def test_caption_is_used_when_there_is_no_text(self):
        message = Message.model_construct(
            message_id=1,
            date=SENT_AT,
            chat=Chat.model_construct(id=1, type="private"),
            text=None,
            caption="Caption body",
            forward_origin=None,
        )
        parsed = _parse(build_eml_from_message(message))

        assert parsed["Subject"] == "Caption body"


class TestLegacyForwardFields:
    def test_pre_bot_api_7_forward_from(self):
        message = SimpleNamespace(
            forward_origin=None,
            forward_from=SimpleNamespace(full_name="Old Style"),
            forward_sender_name=None,
        )

        assert sender_from_message(message) == "Old Style"

    def test_pre_bot_api_7_sender_name(self):
        message = SimpleNamespace(forward_origin=None, forward_from=None, forward_sender_name="Hidden Old")

        assert sender_from_message(message) == "Hidden Old"

    def test_no_forward_metadata_at_all(self):
        message = SimpleNamespace(forward_origin=None, forward_from=None, forward_sender_name=None)

        assert sender_from_message(message) is None

    def test_deprecated_property_that_raises_is_tolerated(self):
        # aiogram exposes the removed fields as properties over forward_origin;
        # on a message without one they can raise instead of returning None.
        class Raising:
            forward_origin = None

            @property
            def forward_from(self):
                raise AttributeError("removed in Bot API 7.0")

        assert sender_from_message(Raising()) is None
