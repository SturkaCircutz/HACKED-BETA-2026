import operator
from typing import Annotated, TypedDict


class ReportState(TypedDict, total=False):
    # Identity
    run_id: str
    user_id: str
    report_id: str

    # Input
    story: str
    category: str
    geometry: dict
    lat: float
    lng: float
    photo_ids: list[str]

    # 1 intake
    photo_findings: list[dict]
    issue_summary: str
    severity: str

    # 2 geo_resolve
    address: str
    city: str | None
    jurisdiction_id: str | None

    # 3a retrieve_contacts / 3b nearby_reports
    contacts: list[dict]
    contact_source: str  # kb | web | none
    open311: dict
    nearby: list[dict]

    # 4 draft_action / 5 human_review
    action_type: str  # email | call
    draft: dict
    review_feedback: str
    approval_status: str | None  # awaiting | approved | edit_requested | rejected

    # 6 deliver / 7 track
    delivery: dict

    # Steps shown in the main conversation (each is an anchor for branches)
    log: Annotated[list[dict], operator.add]
