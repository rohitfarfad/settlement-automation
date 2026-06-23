import json
from datetime import date
from urllib.parse import parse_qs, urlparse

from settlement_automation.connectors.sunoco_api import (
    build_sunoco_settlement_api_url,
    build_sunoco_settlement_filter,
    fetch_sunoco_settlement_json_text,
    is_sunoco_settlement_api_url,
    sanitize_replay_headers,
)


class FakeResponse:
    def __init__(self, payload, ok=True, status=200):
        self._payload = payload
        self.ok = ok
        self.status = status

    def json(self):
        return self._payload


class FakeRequestClient:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def get(self, url, headers=None, timeout=None):
        self.calls.append(
            {
                "url": url,
                "headers": headers or {},
                "timeout": timeout,
            }
        )

        if not self.responses:
            raise AssertionError("Unexpected extra API call")

        return self.responses.pop(0)


class FakeContext:
    def __init__(self, request_client):
        self.request = request_client


class FakePage:
    def __init__(self, request_client):
        self.context = FakeContext(request_client)


def test_build_sunoco_settlement_filter():
    result = build_sunoco_settlement_filter(date(2026, 6, 17))

    assert "settlementDate ge 2026-06-17T05:00:00.000Z" in result
    assert "settlementDate le 2026-06-18T04:59:59.999Z" in result


def test_build_sunoco_settlement_api_url_contains_expected_query_params():
    url = build_sunoco_settlement_api_url(
        settlement_date=date(2026, 6, 17),
        skip=0,
        top=250,
    )

    parsed = urlparse(url)
    query = parse_qs(parsed.query)

    assert parsed.scheme == "https"
    assert parsed.netloc == "api.portal.sunocolp.com"
    assert parsed.path == "/odata/SettlementSummary"

    assert "$filter" in query
    assert "$expand" in query
    assert "$orderby" in query
    assert "$count" in query
    assert "$skip" in query
    assert "$top" in query

    assert query["$skip"] == ["0"]
    assert query["$top"] == ["250"]
    assert query["$count"] == ["true"]

    filter_text = query["$filter"][0]
    assert "settlementDate ge 2026-06-17T05:00:00.000Z" in filter_text
    assert "settlementDate le 2026-06-18T04:59:59.999Z" in filter_text


def test_is_sunoco_settlement_api_url():
    assert is_sunoco_settlement_api_url(
        "https://api.portal.sunocolp.com/odata/SettlementSummary?$top=15"
    )

    assert not is_sunoco_settlement_api_url(
        "https://portal.sunocolp.com/financial/settlement"
    )

    assert not is_sunoco_settlement_api_url(
        "https://api.portal.sunocolp.com/odata/OtherEndpoint"
    )


def test_sanitize_replay_headers_removes_transport_headers_and_keeps_auth():
    headers = {
        "host": "api.portal.sunocolp.com",
        "connection": "keep-alive",
        "content-length": "123",
        "accept-encoding": "gzip",
        "authorization": "Bearer fake-token",
        "user-agent": "fake-browser",
        "accept": "application/json",
    }

    result = sanitize_replay_headers(headers)

    assert "host" not in {key.lower() for key in result}
    assert "connection" not in {key.lower() for key in result}
    assert "content-length" not in {key.lower() for key in result}
    assert "accept-encoding" not in {key.lower() for key in result}

    assert result["authorization"] == "Bearer fake-token"
    assert result["user-agent"] == "fake-browser"
    assert result["accept"] == "application/json"

    assert result["Origin"] == "https://portal.sunocolp.com"
    assert result["Referer"] == "https://portal.sunocolp.com/financial/settlement"


def test_fetch_sunoco_settlement_json_text_preserves_context_and_paginates():
    response_1 = FakeResponse(
        {
            "@odata.context": (
                "https://api.portal.sunocolp.com/odata/$metadata#"
                "SettlementSummary(location(),businessUnit(),settlementHeader())"
            ),
            "@odata.count": 2,
            "value": [
                {
                    "settlementDate": "2026-06-17T00:00:00-05:00",
                    "totalSalesAmount": 100.00,
                    "totalDealerFeeAmount": -2.00,
                    "totalAdjustedNetAmount": 98.00,
                    "location": {
                        "shipToNumber": "0326461100",
                    },
                }
            ],
        }
    )

    response_2 = FakeResponse(
        {
            "@odata.context": (
                "https://api.portal.sunocolp.com/odata/$metadata#"
                "SettlementSummary(location(),businessUnit(),settlementHeader())"
            ),
            "@odata.count": 2,
            "value": [
                {
                    "settlementDate": "2026-06-17T00:00:00-05:00",
                    "totalSalesAmount": 200.00,
                    "totalDealerFeeAmount": -4.00,
                    "totalAdjustedNetAmount": 196.00,
                    "location": {
                        "shipToNumber": "0434020400",
                    },
                }
            ],
        }
    )

    request_client = FakeRequestClient([response_1, response_2])
    page = FakePage(request_client)

    result_text = fetch_sunoco_settlement_json_text(
        page=page,
        settlement_date=date(2026, 6, 17),
        auth_headers={
            "authorization": "Bearer fake-token",
            "user-agent": "fake-browser",
        },
        top=1,
    )

    payload = json.loads(result_text)

    assert "SettlementSummary" in payload["@odata.context"]
    assert payload["@odata.count"] == 2
    assert len(payload["value"]) == 2

    assert payload["value"][0]["location"]["shipToNumber"] == "0326461100"
    assert payload["value"][1]["location"]["shipToNumber"] == "0434020400"

    assert len(request_client.calls) == 2

    first_query = parse_qs(urlparse(request_client.calls[0]["url"]).query)
    second_query = parse_qs(urlparse(request_client.calls[1]["url"]).query)

    assert first_query["$skip"] == ["0"]
    assert second_query["$skip"] == ["1"]

    assert request_client.calls[0]["headers"]["authorization"] == "Bearer fake-token"