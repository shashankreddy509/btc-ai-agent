"""
Unit tests for the _validate() function in btc_agent/config.py.
Patches module-level variables directly to avoid touching .env.
"""
import pytest
import btc_agent.config as cfg


def _validate_with(**overrides):
    """Run _validate() with specific config values temporarily overridden."""
    originals = {k: getattr(cfg, k) for k in overrides}
    for k, v in overrides.items():
        setattr(cfg, k, v)
    try:
        cfg._validate()
    finally:
        for k, v in originals.items():
            setattr(cfg, k, v)


class TestValidConfig:
    def test_default_config_is_valid(self):
        # The loaded .env config must pass validation without error
        cfg._validate()

    def test_all_three_patterns_valid(self):
        _validate_with(SCANNER_PATTERNS=["4-Flag", "Morning Star", "Evening Star"])

    def test_single_pattern_valid(self):
        _validate_with(SCANNER_PATTERNS=["4-Flag"])

    def test_time_format_hhmm(self):
        _validate_with(BRIEFING_TIME="00:00", SCANNER_TIME="23:59")


class TestInvalidTFRange:
    def test_min_greater_than_max(self):
        with pytest.raises(ValueError, match="TF range"):
            _validate_with(SCANNER_TF_MIN=720, SCANNER_TF_MAX=30)

    def test_max_exceeds_1440(self):
        with pytest.raises(ValueError, match="TF range"):
            _validate_with(SCANNER_TF_MIN=30, SCANNER_TF_MAX=1441)

    def test_min_zero(self):
        with pytest.raises(ValueError, match="TF range"):
            _validate_with(SCANNER_TF_MIN=0, SCANNER_TF_MAX=720)


class TestInvalidPatterns:
    def test_unknown_pattern(self):
        with pytest.raises(ValueError, match="Unknown pattern"):
            _validate_with(SCANNER_PATTERNS=["4-Flag", "BadPattern"])

    def test_empty_patterns_list_is_allowed(self):
        # Empty list passes validation (scanner itself handles the empty case)
        _validate_with(SCANNER_PATTERNS=[])


class TestInvalidPort:
    def test_port_zero(self):
        with pytest.raises(ValueError, match="EMAIL_SMTP_PORT"):
            _validate_with(EMAIL_SMTP_PORT=0)

    def test_port_too_high(self):
        with pytest.raises(ValueError, match="EMAIL_SMTP_PORT"):
            _validate_with(EMAIL_SMTP_PORT=65536)

    def test_valid_ports(self):
        _validate_with(EMAIL_SMTP_PORT=587)
        _validate_with(EMAIL_SMTP_PORT=465)


class TestInvalidTimeFormat:
    def test_missing_colon(self):
        with pytest.raises(ValueError, match="BRIEFING_TIME"):
            _validate_with(BRIEFING_TIME="0730")

    def test_wrong_separator(self):
        with pytest.raises(ValueError, match="SCANNER_TIME"):
            _validate_with(SCANNER_TIME="08-00")

    def test_single_digit_hour(self):
        with pytest.raises(ValueError, match="BRIEFING_TIME"):
            _validate_with(BRIEFING_TIME="7:30")
