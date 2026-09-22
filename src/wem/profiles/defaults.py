from wem.profiles.models import TestProfileConfig

DEFAULT_PROFILE_NAME = "Default"
DEFAULT_PROFILE_DESCRIPTION = (
    "Compatibility profile matching the test targets, cadence and diagnostic thresholds "
    "used before configurable profiles were introduced."
)


def default_profile_config() -> TestProfileConfig:
    return TestProfileConfig()
