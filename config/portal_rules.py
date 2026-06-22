import os
from dataclasses import dataclass


@dataclass(frozen=True)
class PortalRule:
    portal_name: str
    login_url: str
    dataconnect_url: str | None = None
    reports_url: str | None = None


def get_dtn_portal_rule() -> PortalRule:
    return PortalRule(
        portal_name="dtn",
        login_url=os.getenv("DTN_LOGIN_URL", "https://fuelbuyer.dtn.com/energy"),
        dataconnect_url=os.getenv(
            "DTN_DATACONNECT_URL",
            "https://fuelbuyer.dtn.com/energy/common/link.do?contentId=750701&parentId=-1",
        ),
    )


def get_sunoco_portal_rule() -> PortalRule:
    return PortalRule(
        portal_name="sunoco",
        login_url=os.getenv("SUNOCO_LOGIN_URL", ""),
        reports_url=os.getenv("SUNOCO_REPORTS_URL", ""),
    )