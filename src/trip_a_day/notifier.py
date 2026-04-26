"""Notification delivery: Resend HTML email with stdout fallback."""

from __future__ import annotations

import base64
import json
import logging
import os
import textwrap
from typing import TYPE_CHECKING

from trip_a_day.db import get_emails_sent_this_month, record_email_sent
from trip_a_day.fetcher import get_airport_city
from trip_a_day.ranker import TripCandidate

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def get_monthly_email_usage(db_session: Session) -> tuple[int, int]:
    """Return (emails_sent_this_month, monthly_limit) from DB."""
    from trip_a_day.preferences import get_or

    sent = get_emails_sent_this_month(db_session)
    limit = int(get_or(db_session, "email_monthly_limit", "3000"))
    return sent, limit


def _check_email_limit(db_session: Session) -> tuple[bool, str]:
    """Return (can_send, reason_if_blocked)."""
    sent, limit = get_monthly_email_usage(db_session)
    if sent >= limit:
        reason = (
            f"Monthly email limit reached ({sent}/{limit}). "
            "No emails will be sent until next month."
        )
        return False, reason
    return True, ""


def _record_run_log_blocked(db_session: Session, reason: str) -> None:
    """Mark the most recent RunLog entry as email_blocked."""
    from sqlalchemy import desc

    from trip_a_day.db import RunLog

    row = db_session.query(RunLog).order_by(desc(RunLog.id)).first()
    if row is not None:
        row.email_blocked = True
        row.email_blocked_reason = reason


def send_trip_notification(
    trip: TripCandidate,
    prefs: dict[str, str],
    *,
    filter_fallback: bool = False,
    is_mock: bool = False,
    home_airport: str = "",
    trip_id: int | None = None,
    db_session: Session | None = None,
) -> bool:
    """Send the daily trip notification email (or print to stdout if no API key).

    Returns True if delivery succeeded, False otherwise.
    """
    recipients = _parse_recipients(prefs)
    subject = _build_subject(trip)
    html_body = _build_html(
        trip,
        filter_fallback=filter_fallback,
        is_mock=is_mock,
        home_airport=home_airport,
        trip_id=trip_id,
        db_session=db_session,
    )
    plain_body = _build_plain(
        trip,
        filter_fallback=filter_fallback,
        is_mock=is_mock,
        home_airport=home_airport,
        trip_id=trip_id,
    )

    api_key = os.environ.get("RESEND_API_KEY", "")
    from_email = os.environ.get("RESEND_FROM_EMAIL", "onboarding@resend.dev")

    if not api_key:
        _print_fallback(subject, plain_body)
        return True

    if not recipients:
        logger.warning("No notification_emails configured; printing to stdout.")
        _print_fallback(subject, plain_body)
        return True

    if db_session is not None:
        can_send, block_reason = _check_email_limit(db_session)
        if not can_send:
            logger.warning("Email blocked: %s", block_reason)
            _record_run_log_blocked(db_session, block_reason)
            return False

    return _send_via_resend(
        api_key, from_email, recipients, subject, html_body, plain_body, db_session
    )


def _parse_recipients(prefs: dict[str, str]) -> list[str]:
    raw = prefs.get("notification_emails", "[]")
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            emails = [e.strip() for e in parsed if e.strip()]
            if emails:
                return emails
    except (json.JSONDecodeError, TypeError):
        pass

    # Fall back to NOTIFICATION_EMAILS env var (also used when DB preference is empty)
    env_emails = os.environ.get("NOTIFICATION_EMAILS", "")
    if env_emails:
        return [e.strip() for e in env_emails.split(",") if e.strip()]

    return []


def _build_subject(trip: TripCandidate) -> str:
    nights = (trip.return_date - trip.departure_date).days
    return (
        f"\u2708\ufe0f Trip of the Day: {trip.city}, {trip.country}"
        f" \u2014 ${trip.cost.total:,.0f} for {nights} nights"
    )


_FILTER_FALLBACK_WARNING_HTML = """\
  <div style="background:#fff3cd;border:1px solid #ffc107;border-radius:4px;padding:12px 16px;margin-bottom:16px;">
    <strong>&#9888; Filter notice:</strong> Your active destination filters produced no matches.
    Today&#8217;s result is from the unfiltered pool. Consider relaxing your filters in Preferences.
  </div>
"""

_FILTER_FALLBACK_WARNING_TEXT = (
    "NOTE: Your active destination filters produced no matches. "
    "Today's result is from the unfiltered pool. "
    "Consider relaxing your filters in Preferences.\n\n"
)

_MOCK_DATA_BANNER_HTML = """\
  <div style="background:#fff3cd;border:2px solid #ffc107;border-radius:4px;padding:12px 16px;margin-bottom:16px;">
    <strong>&#9888; Development Mode</strong> &#8212; Flight prices in this email came from mock data, not live fares.
    Set <code>FLIGHT_DATA_MODE=live</code> in your <code>.env</code> file to receive real pricing.
  </div>
"""

_MOCK_DATA_BANNER_TEXT = (
    "*** DEVELOPMENT MODE ***\n"
    "Flight prices in this email came from mock data, not live fares.\n"
    "Set FLIGHT_DATA_MODE=live in your .env file to receive real pricing.\n\n"
)


def _email_limit_warning_html(db_session: Session | None) -> str:
    """Return warning banner HTML when monthly email usage >= warning threshold."""
    if db_session is None:
        return ""
    try:
        from trip_a_day.preferences import get_or

        sent, limit = get_monthly_email_usage(db_session)
        threshold_pct = int(get_or(db_session, "email_warning_threshold_pct", "90"))
        if limit <= 0 or sent < (limit * threshold_pct // 100):
            return ""
        pct = int(sent * 100 / limit)
        return (
            f'  <div style="background:#fff3cd;border:1px solid #ffc107;border-radius:4px;'
            f'padding:12px 16px;margin-top:16px;">\n'
            f"    <strong>&#9888; Email limit warning:</strong> {sent:,} of {limit:,} emails"
            f" sent this month ({pct}% used). Emails will stop sending when the limit is"
            f" reached. To continue receiving daily emails next month, no action is needed"
            f" &mdash; the counter resets automatically on the 1st.\n"
            f"  </div>\n"
        )
    except Exception:
        return ""


def _airport_label(iata: str) -> str:
    """Return 'City (IATA)' if city is known, else just 'IATA'."""
    city = get_airport_city(iata)
    return iata if city == iata else f"{city} ({iata})"


def _dep_line_html(trip: TripCandidate, home_airport: str) -> str:
    """Always-visible 'Departing from' line; adds warning when non-home airport."""
    if not trip.departure_airport:
        return ""
    label = _airport_label(trip.departure_airport)
    if trip.departure_airport != home_airport and home_airport:
        warning = f' <span style="color:#b26a00;">&#x26A0;&#xFE0F; Not your home airport ({home_airport})</span>'
    else:
        warning = ""
    return f"    <strong>Departing from:</strong> {label}{warning}<br>\n"


def _nearby_dep_html(trip: TripCandidate, home_airport: str) -> str:
    """Transport-cost banner shown only when departing from a non-home airport."""
    if not trip.departure_airport or trip.departure_airport == home_airport:
        return ""
    city = get_airport_city(trip.departure_airport)
    city_label = trip.departure_airport if city == trip.departure_airport else city
    return (
        f'  <div style="background:#e8f4fd;border:1px solid #90caf9;border-radius:4px;'
        f'padding:10px 14px;margin-bottom:12px;">'
        f"&#x2708; Departing from <strong>{city_label} ({trip.departure_airport})</strong>"
        f" &mdash; estimated <strong>${trip.cost.transport_usd:,.0f}</strong> transport"
        f" to reach this airport (IRS mileage estimate).</div>\n"
    )


def _price_history_section_html(trip: TripCandidate, db_session: Session | None) -> str:
    """Return the price-history chart block, or a 'not enough data' fallback."""
    import datetime as _dt

    if db_session is not None:
        try:
            from trip_a_day.charts import generate_price_history_chart

            chart_bytes = generate_price_history_chart(
                trip.destination_iata,
                f"{trip.city}, {trip.country}",
                trip.cost.total,
                _dt.date.today(),
                db_session,
            )
        except Exception as exc:
            logger.warning("Failed to generate price history chart: %s", exc)
            chart_bytes = None
    else:
        chart_bytes = None

    if chart_bytes is not None:
        b64 = base64.b64encode(chart_bytes).decode("ascii")
        return (
            f'  <img src="data:image/png;base64,{b64}"\n'
            f'       alt="Price history chart for {trip.city}"\n'
            f'       width="600" style="max-width:100%;border-radius:4px;" />\n'
            f'  <p class="estimate">Historical total trip cost estimates for this destination.'
            f" Hotel and food costs are per diem estimates; car costs are regional estimates.</p>\n"
            f'  <p class="estimate">Blue: price history for this destination.'
            f" Green: recent daily picks (may be different destinations).</p>\n"
        )

    return (
        '  <p style="color:#888;font-size:13px;">&#x1F4CA; Price history will appear here'
        " once more data has been collected for this destination.</p>\n"
    )


def _build_html(
    trip: TripCandidate,
    *,
    filter_fallback: bool = False,
    is_mock: bool = False,
    home_airport: str = "",
    trip_id: int | None = None,
    db_session: Session | None = None,
) -> str:
    nights = (trip.return_date - trip.departure_date).days
    distance_str = (
        f"{trip.distance_miles:,.0f} mi" if trip.distance_miles > 0 else "N/A"
    )

    return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    body {{ font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; color: #333; }}
    h1 {{ color: #1a6496; }}
    table {{ border-collapse: collapse; width: 100%; margin: 16px 0; }}
    th {{ background: #f5f5f5; text-align: left; padding: 8px 12px; border: 1px solid #ddd; }}
    td {{ padding: 8px 12px; border: 1px solid #ddd; }}
    .total {{ font-weight: bold; background: #eaf4fb; }}
    .btn {{ display: inline-block; padding: 10px 20px; background: #1a6496; color: white;
            text-decoration: none; border-radius: 4px; margin: 4px 2px; }}
    .footer {{ font-size: 12px; color: #888; margin-top: 24px; border-top: 1px solid #eee; padding-top: 12px; }}
    .estimate {{ color: #888; font-size: 11px; }}
  </style>
</head>
<body>
  <h1>&#x2708;&#xFE0F; Trip of the Day</h1>
  {_MOCK_DATA_BANNER_HTML if is_mock else ""}
  {_FILTER_FALLBACK_WARNING_HTML if filter_fallback else ""}
  {_nearby_dep_html(trip, home_airport)}
  <h2>{trip.city}, {trip.country}</h2>
  <p>
{_dep_line_html(trip, home_airport)}    <strong>Region:</strong> {trip.region}<br>
    <strong>Departure:</strong> {trip.departure_date.strftime("%B %d, %Y")}<br>
    <strong>Return:</strong> {trip.return_date.strftime("%B %d, %Y")} ({nights} nights)<br>
    <strong>Distance from home:</strong> {distance_str}
  </p>

  <h3>Cost Breakdown</h3>
  <table>
    <tr><th>Component</th><th>Cost (USD)</th></tr>
    <tr><td>&#x2708; Flights (round-trip, all travelers)</td><td>${trip.cost.flights:,.2f}</td></tr>
    <tr><td>&#x1F3E8; Hotel ({nights} nights) *</td><td>${trip.cost.hotel:,.2f}</td></tr>
    <tr><td>&#x1F697; Rental Car *</td><td>${trip.cost.car:,.2f}</td></tr>
    <tr><td>&#x1F374; Food (all travelers) *</td><td>${trip.cost.food:,.2f}</td></tr>
    <tr class="total"><td><strong>Total</strong></td><td><strong>${trip.cost.total:,.2f}</strong></td></tr>
  </table>
  <p class="estimate">* Hotel and food are government per diem rate estimates (GSA / State Dept); car rental is a regional average. Only flight prices are live quotes from Google Flights.</p>

  <h3>Price History</h3>
{_price_history_section_html(trip, db_session)}
  <h3>Book Now</h3>
  <a class="btn" href="{trip.flight_booking_url}">&#x2708; Book Flights</a>
  <a class="btn" href="{trip.hotel_booking_url}">&#x1F3E8; Book Hotel</a>
  <a class="btn" href="{trip.car_booking_url}">&#x1F697; Find Car Rental</a>

{_email_limit_warning_html(db_session)}
  <div class="footer">
    <p>Generated by <strong>trip-a-day</strong>.{_mark_booked_link_html(trip_id)}</p>
  </div>
</body>
</html>"""


def _build_plain(
    trip: TripCandidate,
    *,
    filter_fallback: bool = False,
    is_mock: bool = False,
    home_airport: str = "",
    trip_id: int | None = None,
) -> str:
    nights = (trip.return_date - trip.departure_date).days
    distance_str = (
        f"{trip.distance_miles:,.0f} mi" if trip.distance_miles > 0 else "N/A"
    )
    mock_warning = _MOCK_DATA_BANNER_TEXT if is_mock else ""
    filter_warning = _FILTER_FALLBACK_WARNING_TEXT if filter_fallback else ""
    if trip.departure_airport:
        dep_label = _airport_label(trip.departure_airport)
        if trip.departure_airport != home_airport and home_airport:
            dep_label += f"  ⚠️ Not your home airport ({home_airport})"
        if trip.departure_airport != home_airport and trip.cost.transport_usd > 0:
            dep_label += (
                f" — est. ${trip.cost.transport_usd:,.0f} transport (IRS mileage)"
            )
        dep_line = f"Departing from: {dep_label}"
    else:
        dep_line = ""
    return (
        mock_warning
        + filter_warning
        + textwrap.dedent(f"""\
        ✈️  TRIP OF THE DAY
        ==================
        Destination : {trip.city}, {trip.country} ({trip.region})
        {dep_line}
        Departure   : {trip.departure_date.strftime("%B %d, %Y")}
        Return      : {trip.return_date.strftime("%B %d, %Y")} ({nights} nights)
        Distance    : {distance_str}

        COST BREAKDOWN
        --------------
        Flights     : ${trip.cost.flights:>10,.2f}  (live quote — Google Flights)
        Hotel    *  : ${trip.cost.hotel:>10,.2f}
        Car      *  : ${trip.cost.car:>10,.2f}
        Food     *  : ${trip.cost.food:>10,.2f}
        ─────────────────────────────────────────
        Total       : ${trip.cost.total:>10,.2f}

        * Hotel and food are government per diem estimates (GSA / State Dept);
          car rental is a regional average. Only flights are live quotes.

        BOOKING LINKS
        -------------
        Flights  : {trip.flight_booking_url}
        Hotel    : {trip.hotel_booking_url}
        Car      : {trip.car_booking_url}
        {_mark_booked_link_plain(trip_id)}
    """)
    )


def _mark_booked_link_html(trip_id: int | None) -> str:
    if trip_id is None:
        return ""
    url = f"http://localhost:8501/?action=mark_booked&trip_id={trip_id}"
    return f' &nbsp;<a href="{url}" style="color:#2e7d32;">&#x2705; Mark as Booked</a>'


def _mark_booked_link_plain(trip_id: int | None) -> str:
    if trip_id is None:
        return ""
    url = f"http://localhost:8501/?action=mark_booked&trip_id={trip_id}"
    return f"Mark as Booked : {url}\n        "


def _print_fallback(subject: str, plain_body: str) -> None:
    print("\n" + "=" * 60)
    print(f"SUBJECT: {subject}")
    print("=" * 60)
    print(plain_body)
    print("=" * 60 + "\n")
    logger.info("Trip notification printed to stdout (no Resend key configured).")


def _send_via_resend(
    api_key: str,
    from_email: str,
    recipients: list[str],
    subject: str,
    html_body: str,
    plain_body: str,
    db_session: Session | None = None,
) -> bool:
    try:
        import resend  # type: ignore[import]

        resend.api_key = api_key
        params: resend.Emails.SendParams = {
            "from": from_email,
            "to": recipients,
            "subject": subject,
            "html": html_body,
            "text": plain_body,
        }
        email = resend.Emails.send(params)
        if email and email.get("id"):
            logger.info("Email sent to %s (id: %s).", recipients, email["id"])
            if db_session is not None:
                record_email_sent(db_session)
            return True
        else:
            logger.error("Resend returned unexpected response: %s", email)
            return False
    except Exception as exc:
        logger.error("Failed to send email via Resend: %s", exc)
        return False


def send_test_email(
    prefs: dict[str, str],
    db_session: Session | None = None,
) -> tuple[bool, str]:
    """Send a test email to configured recipients.

    Returns (success, message) where message describes the outcome.
    """
    api_key = os.environ.get("RESEND_API_KEY", "")
    from_email = os.environ.get("RESEND_FROM_EMAIL", "onboarding@resend.dev")

    if not api_key:
        return False, "No RESEND_API_KEY configured. Set it in your .env file."

    recipients = _parse_recipients(prefs)
    if not recipients:
        return (
            False,
            "No notification emails configured. Add at least one email address.",
        )

    subject = "Trip of the Day — Test Email"
    html_body = textwrap.dedent(f"""\
        <!DOCTYPE html><html><body style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;">
        <h2>&#x2705; Trip of the Day — Test Email</h2>
        <p>This is a test email confirming that your notification configuration is working.</p>
        <ul>
          <li><strong>Sender:</strong> {from_email}</li>
          <li><strong>Recipients:</strong> {", ".join(recipients)}</li>
          <li><strong>Flight data mode:</strong> {os.environ.get("FLIGHT_DATA_MODE", "mock")}</li>
        </ul>
        <p>If you received this, your Resend integration is set up correctly.</p>
        </body></html>
    """)
    plain_body = (
        "Trip of the Day — Test Email\n\n"
        "This is a test email confirming your notification configuration is working.\n"
        f"Sender: {from_email}\n"
        f"Recipients: {', '.join(recipients)}\n"
        f"Flight data mode: {os.environ.get('FLIGHT_DATA_MODE', 'mock')}\n"
    )

    if db_session is not None:
        can_send, block_reason = _check_email_limit(db_session)
        if not can_send:
            return False, f"Email blocked: {block_reason}"

    ok = _send_via_resend(
        api_key, from_email, recipients, subject, html_body, plain_body, db_session
    )
    if ok:
        return True, f"Test email sent to {', '.join(recipients)}."
    return False, "Failed to send test email — check logs for details."


def send_no_results_notification(
    prefs: dict[str, str],
    run_date: object,
    diagnostics: dict,
    db_session: Session | None = None,
) -> bool:
    """Send an alert when no trips could be priced for today's run.

    Returns True if delivery succeeded, False otherwise.
    """
    subject = "⚠️ Trip of the Day — No results today"
    run_date_str = str(run_date)

    diag_lines = "\n".join(
        f"  <li><strong>{k}:</strong> {v}</li>" for k, v in diagnostics.items()
    )
    html_body = textwrap.dedent(f"""\
        <!DOCTYPE html><html><body style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;">
        <h2>⚠️ Trip of the Day &mdash; No Results Today ({run_date_str})</h2>
        <p>The daily run could not price any trips. The scheduler will retry tomorrow.</p>
        <h3>Diagnostics</h3>
        <ul>
        {diag_lines}
        </ul>
        <p style="color:#888;font-size:12px;">
          This is an automated alert from Trip of the Day.
          Check your API connectivity and logs for details.
        </p>
        </body></html>
    """)
    plain_body = (
        f"Trip of the Day — No Results Today ({run_date_str})\n\n"
        "The daily run could not price any trips. Will retry tomorrow.\n\n"
        "Diagnostics:\n"
        + "\n".join(f"  {k}: {v}" for k, v in diagnostics.items())
        + "\n"
    )

    api_key = os.environ.get("RESEND_API_KEY", "")
    from_email = os.environ.get("RESEND_FROM_EMAIL", "onboarding@resend.dev")

    if not api_key:
        _print_fallback(subject, plain_body)
        return True

    recipients = _parse_recipients(prefs)
    if not recipients:
        logger.warning(
            "No notification_emails configured; printing no-results alert to stdout."
        )
        _print_fallback(subject, plain_body)
        return True

    if db_session is not None:
        can_send, block_reason = _check_email_limit(db_session)
        if not can_send:
            logger.warning("No-results email blocked: %s", block_reason)
            return False

    return _send_via_resend(
        api_key, from_email, recipients, subject, html_body, plain_body, db_session
    )
