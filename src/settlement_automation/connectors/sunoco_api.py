import json
from datetime import date, timedelta
from urllib.parse import urlencode

from settlement_automation.exceptions import PortalDownloadError


SUNOCO_SETTLEMENT_API_URL = "https://api.portal.sunocolp.com/odata/SettlementSummary"

SUNOCO_SETTLEMENT_CONTEXT = (
    "https://api.portal.sunocolp.com/odata/$metadata#"
    "SettlementSummary("
    "location(sapReferenceId,id,businessUnitId,shipToNumber,"
    "shipToCustomerName,shipToStreetAddress,shipToStreetAddress2,"
    "shipToCity,shipToZip,brandId,shipToState(name)),"
    "businessUnit(sapReferenceId,id,billToNumber,phoneNumber,"
    "faxNumber,customerName,streetAddress,city,state,zip),"
    "settlementHeader())"
)

SUNOCO_SETTLEMENT_EXPAND = (
    "location($select=sapReferenceId,id,businessUnitId,shipToNumber,"
    "shipToCustomerName,shipToStreetAddress,shipToStreetAddress2,"
    "shipToCity,shipToZip,brandId;"
    "$expand=shipToState($select=name)), "
    "businessUnit($select=sapReferenceId,id,billToNumber,phoneNumber,"
    "faxNumber,customerName,streetAddress,city,state,zip),"
    "settlementHeader"
)


def build_sunoco_settlement_filter(settlement_date: date) -> str:
    """
    Build Sunoco OData date filter.

    Observed portal request uses:
        settlementDate ge YYYY-MM-DDT05:00:00.000Z
        settlementDate le NEXT_DAYT04:59:59.999Z
    """
    next_day = settlement_date + timedelta(days=1)

    return (
        f" settlementDate ge {settlement_date.isoformat()}T05:00:00.000Z "
        f"and settlementDate le {next_day.isoformat()}T04:59:59.999Z"
    )


def build_sunoco_settlement_api_url(
    settlement_date: date,
    skip: int = 0,
    top: int = 250,
) -> str:
    params = {
        "$filter": build_sunoco_settlement_filter(settlement_date),
        "$expand": SUNOCO_SETTLEMENT_EXPAND,
        "$orderby": "settlementDate desc",
        "$count": "true",
        "$skip": str(skip),
        "$top": str(top),
    }

    return f"{SUNOCO_SETTLEMENT_API_URL}?{urlencode(params)}"


def is_sunoco_settlement_api_url(url: str) -> bool:
    lowered = url.lower()

    return (
        "api.portal.sunocolp.com" in lowered
        and "/odata/settlementsummary" in lowered
    )


def sanitize_replay_headers(headers: dict[str, str]) -> dict[str, str]:
    """
    Keep headers needed for Sunoco API replay and remove unsafe transport headers.
    """
    excluded = {
        "host",
        "content-length",
        "connection",
        "accept-encoding",
    }

    sanitized = {}

    for key, value in headers.items():
        lower_key = key.lower()

        if lower_key in excluded:
            continue

        sanitized[key] = value

    sanitized.setdefault("Accept", "application/json, text/plain, */*")
    sanitized.setdefault("Origin", "https://portal.sunocolp.com")
    sanitized.setdefault("Referer", "https://portal.sunocolp.com/financial/settlement")

    return sanitized


def fetch_sunoco_settlement_json_text(
    page,
    settlement_date: date,
    auth_headers: dict[str, str],
    top: int = 250,
) -> str:
    """
    Fetch all Sunoco settlement rows directly from the authenticated API.

    The browser must already be logged in, and auth_headers must come from a
    real frontend SettlementSummary request.
    """
    if not auth_headers:
        raise PortalDownloadError(
            "Sunoco API auth headers were not provided. "
            "Open the settlement page and capture a real SettlementSummary request first."
        )

    replay_headers = sanitize_replay_headers(auth_headers)

    all_values = []
    total_count = None
    odata_context = None
    skip = 0

    while True:
        url = build_sunoco_settlement_api_url(
            settlement_date=settlement_date,
            skip=skip,
            top=top,
        )

        response = page.context.request.get(
            url,
            headers=replay_headers,
            timeout=60000,
        )

        if not response.ok:
            raise PortalDownloadError(
                f"Sunoco settlement API request failed. "
                f"status={response.status}, url={url}"
            )

        try:
            payload = response.json()
        except Exception as exc:
            raise PortalDownloadError(
                f"Sunoco settlement API did not return valid JSON. url={url}"
            ) from exc

        if odata_context is None:
            odata_context = payload.get("@odata.context")

        values = payload.get("value", [])

        if total_count is None:
            total_count = payload.get("@odata.count")

        if not isinstance(values, list):
            raise PortalDownloadError(
                "Sunoco settlement API response value is not a list."
            )

        all_values.extend(values)

        if not values:
            break

        skip += len(values)

        if total_count is not None and len(all_values) >= int(total_count):
            break

        if len(values) < top:
            break

    combined_payload = {
        "@odata.context": odata_context or SUNOCO_SETTLEMENT_CONTEXT,
        "@odata.count": total_count if total_count is not None else len(all_values),
        "value": all_values,
    }

    return json.dumps(combined_payload, indent=4)