import io

import pytest

from leap_teleop.sources.keyboard import KeyboardSource, TerminalKeyReader


def scripted(keys):
    iterator = iter(keys)
    return lambda: next(iterator, None)


def test_first_poll_is_open_with_the_given_timestamp():
    source = KeyboardSource(read_key=scripted([]))
    reading = source.poll(12.5)
    assert reading.grasp == 0.0
    assert reading.timestamp == 12.5


def test_space_toggles_between_open_and_closed():
    source = KeyboardSource(read_key=scripted([" ", None, " ", None]))
    assert source.poll(0.0).grasp == 1.0
    assert source.poll(0.1).grasp == 0.0


def test_all_pending_keys_are_applied_in_one_poll():
    source = KeyboardSource(read_key=scripted([" ", " ", " ", None]))
    assert source.poll(0.0).grasp == 1.0


def test_q_requests_stop_in_either_case():
    for key in ("q", "Q"):
        source = KeyboardSource(read_key=scripted([key, None]))
        assert not source.stop_requested
        source.poll(0.0)
        assert source.stop_requested


def test_other_keys_are_ignored():
    source = KeyboardSource(read_key=scripted(["x", "\n", None]))
    assert source.poll(0.0).grasp == 0.0
    assert not source.stop_requested


def test_terminal_reader_refuses_a_non_tty_stream():
    with pytest.raises(RuntimeError, match="TTY"):
        TerminalKeyReader(stream=io.StringIO())
