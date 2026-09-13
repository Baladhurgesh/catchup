from services.llm import supports_temperature


def test_gpt4o_supports_temperature() -> None:
    assert supports_temperature("gpt-4o") is True


def test_gpt5_does_not_support_temperature() -> None:
    assert supports_temperature("gpt-5") is False
    assert supports_temperature("gpt-5-mini") is False
    assert supports_temperature("o3-mini") is False
