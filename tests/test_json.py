import pytest
import simplejson
from pydesk_json_tools import transform
from pydesktools_sdk import CancellationToken, PluginError


def convert(text, **kwargs):
    return transform(text, cancellation=CancellationToken(), **kwargs)


def test_precise_numbers_and_unicode():
    source = '{"世界": 9007199254740993123456789, "small": 0.1234567890123456789012345, "exponent": 1e-999}'
    result = convert(source)
    assert simplejson.loads(result, use_decimal=True) == simplejson.loads(source, use_decimal=True)
    assert "世界" in result
    assert convert('{"b":2,"a":1}', minify=True) == '{"b":2,"a":1}'
    assert convert('{"b":2,"a":1}', minify=True, sort_keys=True) == '{"a":1,"b":2}'


@pytest.mark.parametrize(
    "source", ["", "{", '{"a":1,"a":2}', "[NaN]", "[Infinity]", "[" * 129 + "0" + "]" * 129]
)
def test_invalid(source):
    with pytest.raises(PluginError) as exc:
        convert(source)
    assert exc.value.details["line"] >= 1
    assert exc.value.details["column"] >= 1


def test_duplicate_location_and_independent_objects():
    with pytest.raises(PluginError) as exc:
        convert('{\n "a": 1,\n "a": 2}')
    assert exc.value.details["line"] == 3
    assert exc.value.details["column"] == 2
    assert convert('[{"a":1},{"a":2}]', minify=True) == '[{"a":1},{"a":2}]'


def test_limits_and_cancellation():
    with pytest.raises(PluginError, match="20 MiB"):
        convert(" " * (20 * 1024 * 1024 + 1))
    token = CancellationToken()
    token.cancel()
    with pytest.raises(PluginError) as exc:
        transform("{}", cancellation=token)
    assert exc.value.kind == "canceled"
