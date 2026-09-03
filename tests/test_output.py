import json

from transcreve.output import render, timestamp
from transcreve.types import Segment

SEGMENTS = [Segment(1.25, 3.5, "Olá, mundo!"), Segment(65, 66, "Tudo bem?")]


def test_timestamp_formats_milliseconds():
    assert timestamp(3661.234) == "01:01:01,234"


def test_txt_is_plain_by_default():
    assert render(SEGMENTS, "txt") == "Olá, mundo!\nTudo bem?\n"


def test_srt_has_sequence_and_timestamps():
    output = render(SEGMENTS, "srt")
    assert "1\n00:00:01,250 --> 00:00:03,500" in output
    assert "2\n00:01:05,000 --> 00:01:06,000" in output


def test_json_is_machine_readable():
    assert json.loads(render(SEGMENTS, "json"))[0]["text"] == "Olá, mundo!"
