from pydantic import ValidationError
from wifi_server.recording_schemas import StartRecordingRequest


def test_blank_context_is_omitted() -> None:
    request = StartRecordingRequest(site="   ", location="\n", description="  ")
    assert request.site is None
    assert request.location is None
    assert request.description is None


def test_site_and_location_length_matches_database_columns() -> None:
    for field in ("site", "location"):
        try:
            StartRecordingRequest.model_validate({field: "X" * 256})
        except ValidationError:
            continue
        raise AssertionError(f"{field} accepted more than 255 characters")
