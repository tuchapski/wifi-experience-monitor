"""Process-local diagnostic recording context for asynchronous collectors."""

_active_recording_id: str | None = None


def set_active_recording_id(recording_id: str | None) -> None:
    global _active_recording_id
    _active_recording_id = recording_id


def get_active_recording_id() -> str | None:
    return _active_recording_id
