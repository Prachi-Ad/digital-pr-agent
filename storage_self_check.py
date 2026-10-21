"""One-click storage health check for the Digital PR Agent.

Runs the real Streamlit app against a temporary database, exercises every
save path, restarts the session, and verifies exports and backups.

The real project database is never read or written. Run it by double-clicking
run_storage_check.vbs, or with:
    .venv\\Scripts\\python.exe storage_self_check.py
"""
from __future__ import annotations

import csv
import io
import os
import shutil
import sqlite3
import sys
import tempfile
import time
import traceback
from datetime import datetime
from pathlib import Path

PROJECT = Path(__file__).resolve().parent
BACKUPS = PROJECT / "backups"
BACKUPS.mkdir(parents=True, exist_ok=True)
LATEST_LOG = BACKUPS / "latest_storage_check.txt"

# The check never calls the API. A placeholder key keeps imports working
# even when OPENAI_API_KEY is not set for the Windows session.
os.environ.setdefault("OPENAI_API_KEY", "storage-self-check-does-not-call-api")

log_file = open(LATEST_LOG, "w", encoding="utf-8")
FAILURES: list[str] = []


def emit(line: str = "") -> None:
    print(line)
    log_file.write(line + "\n")
    log_file.flush()


def check(label: str, condition: bool, detail: object = "") -> None:
    if condition:
        emit(f"PASS  {label}")
    else:
        emit(f"FAIL  {label}  {detail}")
        FAILURES.append(label)


def main() -> int:
    emit("Digital PR Agent - storage health check")
    emit(f"Run at: {datetime.now().isoformat(timespec='seconds')}")
    emit(f"Project: {PROJECT}")
    emit()

    if not (PROJECT / ".venv" / "Scripts" / "python.exe").exists():
        emit("FAIL  The project's .venv Python environment was not found.")
        return 1

    tmp = Path(tempfile.mkdtemp(prefix="pr_storage_check_"))
    emit(f"Temporary test database: {tmp / 'pr_agent.sqlite3'}")
    emit()

    import database

    database.ROOT = tmp
    database.DATA_DIR = tmp
    database.DB_PATH = tmp / "pr_agent.sqlite3"

    from agent import (
        AssetAnalysis,
        JournalistProfile,
        JournalistResearchResults,
        ListicleContact,
        ListicleContactResearchResults,
        ListicleOpportunity,
        ListicleResearchResults,
        PRAngle,
        PROpportunity,
        PRResearchResults,
        PublisherPolicyAssessment,
    )
    from streamlit.testing.v1 import AppTest

    app_path = str(PROJECT / "app.py")

    def new_app() -> AppTest:
        app = AppTest.from_file(app_path, default_timeout=60)
        app.run()
        if list(app.exception):
            raise AssertionError(f"The app raised an error: {list(app.exception)}")
        return app

    def go(app: AppTest, page: str) -> None:
        app.sidebar.radio[0].set_value(page)
        app.run()
        if list(app.exception):
            raise AssertionError(f"{page} raised an error: {list(app.exception)}")

    # --------------------------------------------------------------
    # Test fixtures
    # --------------------------------------------------------------
    url = "https://example.com/best-tools/?utm_source=newsletter"
    item = ListicleOpportunity(
        publication="Probe Publication",
        listicle_title="Best social tools for probe teams",
        listicle_url=url,
        published_or_updated="2026-01-01",
        listicle_category="social media management",
        target_audience="agencies",
        competitors_listed=["Hootsuite", "Buffer"],
        brand_currently_listed="No",
        brand_fit="the brand matches the category.",
        inclusion_gap="Unknown",
        placement_type="Editorial",
        contact_route="Official editorial form",
        recommended_action="Request editorial consideration",
        evidence="Page checked.",
        confidence="High",
    )
    listicle_results = ListicleResearchResults(
        search_theme="probe theme",
        research_summary="Probe summary.",
        opportunities=[item],
    )
    contacts = ListicleContactResearchResults(
        publication=item.publication,
        listicle_title=item.listicle_title,
        listicle_url=item.listicle_url,
        research_summary="Found an editorial contact page.",
        contacts=[
            ListicleContact(
                contact_name="Alex Editor",
                current_role="Editor",
                professional_email="Not publicly found",
                author_profile_url="https://example.com/author/alex",
                contact_page_url="https://example.com/contact",
                contact_method="official form",
                why_this_contact="Handles tool roundups.",
                evidence="Author page lists the role.",
                source_url="https://example.com/author/alex",
                confidence="High",
            )
        ],
    )
    policy = PublisherPolicyAssessment(
        publication=item.publication,
        listicle_title=item.listicle_title,
        target_url=item.listicle_url,
        policy_status="No explicit policy found",
        policy_summary="No published policy against suggestions.",
        policy_evidence="No relevant policy page located.",
        policy_source_url="Unknown",
        recommended_disposition="Pursue",
        disposition_reason="No conflicting policy was found.",
        recommended_route="editorial consideration",
        confidence="Medium",
    )

    angle = PRAngle(
        angle="Measurement trust gap",
        story_type="Data story",
        recommended_tactic="Expert commentary",
        story_hypothesis="Marketers distrust social measurement.",
        why_useful="Timely topic.",
        brand_contribution="Aggregate platform data.",
        target_publication_types=["Marketing trade press"],
        target_journalist_beats=["analytics"],
        relevant_asset="Probe asset",
        evidence="Probe evidence",
        next_action="Pitch the data angle",
        confidence="High",
    )
    analysis = AssetAnalysis(
        article_title="Probe asset article",
        main_topic="Social measurement",
        target_audience=["Marketers"],
        key_claims=["Claims"],
        statistics=[],
        useful_assets=["Report"],
        pr_angles=[angle],
        assessment="Strong asset.",
    )
    opportunity = PROpportunity(
        publication="Probe Trade",
        article_title="Why measurement is hard",
        article_url="https://example.com/measurement",
        published_date="2026-02-01",
        topic="Measurement",
        opportunity_type="Expert commentary",
        why_relevant="Matches the angle.",
        brand_contribution="Data and commentary.",
        competitor_mention="None identified",
        topical_relevance="High",
        editorial_fit="High",
        recommended_action="Pitch",
        evidence="Article checked.",
        confidence="High",
    )
    opportunity_results = PRResearchResults(
        selected_angle=angle.angle,
        research_summary="One strong candidate.",
        opportunities=[opportunity],
    )
    journalist = JournalistProfile(
        name="Jordan Writer",
        publication="Probe Trade",
        current_role="Reporter",
        relevant_article_title="Why measurement is hard",
        relevant_article_url="https://example.com/measurement",
        article_date="2026-02-01",
        topic_covered="Measurement",
        why_relevant="Covers the exact topic.",
        suggested_pitch_angle="Offer the the brand data.",
        author_profile_or_contact_page="https://example.com/author/jordan",
        evidence="Byline verified.",
        confidence="High",
    )
    co_author = JournalistProfile(
        name="Sam Coauthor",
        publication="Probe Trade",
        current_role="Senior Reporter",
        relevant_article_title="Why measurement is hard",
        relevant_article_url="https://example.com/measurement",
        article_date="2026-02-01",
        topic_covered="Measurement",
        why_relevant="Co-wrote the exact article.",
        suggested_pitch_angle="Offer the same data with a different angle.",
        author_profile_or_contact_page="https://example.com/author/sam",
        evidence="Co-byline verified.",
        confidence="Medium",
    )
    journalist_results = JournalistResearchResults(
        selected_opportunity=opportunity.article_title,
        publication=opportunity.publication,
        research_summary="Two verified co-authors on the same article.",
        journalists=[journalist, co_author],
    )

    # --------------------------------------------------------------
    # 1. Listicle: save, enrich, decide, track placement
    # --------------------------------------------------------------
    emit("1. Listicle workflow")
    app = new_app()
    go(app, "Listicle Opportunities")
    app.session_state["listicle_results"] = listicle_results
    app.session_state["listicle_run_id"] = 1
    app.session_state["listicle_reviews"] = {}
    app.session_state["listicle_placement_progress"] = {}
    app.session_state["listicle_contact_results"] = {"1:0": contacts}
    app.session_state["listicle_policy_results"] = {"1:0": policy}
    app.run()

    saved = database.list_listicle_prospects()
    check("listicle prospect is saved", len(saved) == 1, f"count={len(saved)}")
    row = saved[0] if saved else {}
    check("contact research is saved", bool(row.get("contact_data")))
    check("policy research is saved", bool(row.get("policy_data")))

    app.get_by_key("listicle_review_decision_1_0").set_value("Approve to pursue")
    app.run()
    app.get_by_key("save_listicle_review_1_0").click()
    app.run()
    app.get_by_key("listicle_placement_progress_1_0").set_value("Placement confirmed")
    app.run()
    app.get_by_key("save_listicle_progress_1_0").click()
    app.run()

    row = database.get_listicle_prospect(url, item.listicle_title, item.publication) or {}
    check("review decision is saved", row.get("review_status") == "Approve to pursue", row.get("review_status"))
    check("placement progress is saved", row.get("placement_progress") == "Placement confirmed", row.get("placement_progress"))

    first_updated = row.get("updated_at")
    time.sleep(1.1)
    app.run()
    again = database.get_listicle_prospect(url, item.listicle_title, item.publication) or {}
    check(
        "viewing the page does not rewrite updated_at",
        bool(first_updated) and again.get("updated_at") == first_updated,
        f"{first_updated} -> {again.get('updated_at')}",
    )

    variant = url.replace("/?utm_source=newsletter", "").rstrip("/") + "/"
    variant = variant.replace("example.com", "EXAMPLE.com")
    same = database.get_listicle_prospect(variant, item.listicle_title, item.publication) or {}
    check("URL variants reuse the same record", same.get("prospect_key") == row.get("prospect_key"), variant)

    database.upsert_listicle_prospect(item, search_theme="probe theme")
    row = database.get_listicle_prospect(url, item.listicle_title, item.publication) or {}
    check("re-saving keeps contact research", bool(row.get("contact_data")))
    check("re-saving keeps policy research", bool(row.get("policy_data")))
    check("re-saving keeps review decision", row.get("review_status") == "Approve to pursue", row.get("review_status"))
    check("re-saving keeps placement progress", row.get("placement_progress") == "Placement confirmed", row.get("placement_progress"))
    check("duplicate pages remain one record", len(database.list_listicle_prospects()) == 1, len(database.list_listicle_prospects()))

    # --------------------------------------------------------------
    # 2. Restart: workspace and saved records survive
    # --------------------------------------------------------------
    emit()
    emit("2. Restart and restore")
    app2 = new_app()
    check("workspace is restored after restart", app2.session_state["listicle_results"] is not None)
    go(app2, "Listicle Opportunities")
    restored_status = app2.get_by_key("listicle_review_decision_1_0").value
    restored_progress = app2.get_by_key("listicle_placement_progress_1_0").value
    check("review decision is restored", restored_status == "Approve to pursue", restored_status)
    check("placement progress is restored", restored_progress == "Placement confirmed", restored_progress)

    go(app2, "Research Library")
    counts = [metric.value for metric in app2.metric]
    check("library shows the listicle count", counts and counts[0] == "1", counts)

    # --------------------------------------------------------------
    # 3. PR opportunities
    # --------------------------------------------------------------
    emit()
    emit("3. PR opportunity workflow")
    app2.session_state["analysis"] = analysis
    app2.session_state["selected_angle_index"] = 0
    app2.session_state["opportunity_results"] = opportunity_results
    app2.session_state["research_run_id"] = 1
    app2.session_state["opportunity_reviews"] = {}
    app2.run()
    go(app2, "PR Opportunities")
    app2.get_by_key("review_decision_1_0").set_value("Approve for journalist research")
    app2.run()
    app2.get_by_key("save_review_1_0").click()
    app2.run()

    row = database.get_pr_opportunity(opportunity.article_url, opportunity.article_title, opportunity.publication) or {}
    check("PR opportunity is saved", bool(row))
    check("PR review decision is saved", row.get("review_status") == "Approve for journalist research", row.get("review_status"))
    check("PR angle is saved", row.get("selected_angle") == angle.angle, row.get("selected_angle"))
    check("PR opportunity is not duplicated", len(database.list_pr_opportunities()) == 1, len(database.list_pr_opportunities()))

    time.sleep(1.1)
    database.upsert_pr_opportunity(opportunity, selected_angle=angle.angle, review_status=None)
    row_again = database.get_pr_opportunity(opportunity.article_url, opportunity.article_title, opportunity.publication) or {}
    check("re-saving a PR opportunity does not change updated_at", row_again.get("updated_at") == row.get("updated_at"))

    # --------------------------------------------------------------
    # 4. Journalists and outreach queue
    # --------------------------------------------------------------
    emit()
    emit("4. Journalist workflow")
    app2.session_state["journalist_results"] = {"1:0": journalist_results}
    app2.session_state["journalist_reviews"] = {}
    go(app2, "Journalists")
    app2.get_by_key("journalist_status_1_0_0").set_value("Qualified pitch target")
    app2.run()
    app2.get_by_key("save_journalist_status_1_0_0").click()
    app2.run()

    row = database.get_journalist_record(journalist, opportunity.article_url) or {}
    check("journalist record is saved", bool(row))
    check("journalist qualification is saved", row.get("qualification_status") == "Qualified pitch target", row.get("qualification_status"))
    check("journalist is linked to the opportunity", row.get("related_opportunity_url") == opportunity.article_url, row.get("related_opportunity_url"))

    co_row = database.get_journalist_record(co_author, opportunity.article_url) or {}
    check("co-author on the same article gets a separate record", bool(co_row) and co_row.get("record_key") != row.get("record_key"))
    check("co-author starts as needs review", co_row.get("qualification_status") == "Needs review", co_row.get("qualification_status"))
    check("journalist records are not merged", len(database.list_journalists()) == 2, len(database.list_journalists()))

    app2.get_by_key("journalist_status_1_0_1").set_value("Relevant writer")
    app2.run()
    app2.get_by_key("save_journalist_status_1_0_1").click()
    app2.run()
    row = database.get_journalist_record(journalist, opportunity.article_url) or {}
    co_row = database.get_journalist_record(co_author, opportunity.article_url) or {}
    check("co-author qualification is saved", co_row.get("qualification_status") == "Relevant writer", co_row.get("qualification_status"))
    check("saving one co-author does not change the other", row.get("qualification_status") == "Qualified pitch target", row.get("qualification_status"))

    app3 = new_app()
    go(app3, "Outreach")
    outreach_text = " ".join(text.value for text in app3.markdown) + " ".join(text.value for text in app3.subheader)
    check("outreach queue is restored after restart", "Jordan Writer" in outreach_text, outreach_text[:200])
    check("unqualified co-author is not in the outreach queue", "Sam Coauthor" not in outreach_text)

    go(app3, "Research Library")
    library_counts = [metric.value for metric in app3.metric]
    check("library shows all three record types", library_counts[:3] == ["1", "1", "2"], library_counts)

    # --------------------------------------------------------------
    # 5. Exports and backup
    # --------------------------------------------------------------
    emit()
    emit("5. Exports and backup")
    for label, data, expected in [
        ("listicle CSV", database.listicle_csv_bytes(), "Probe Publication"),
        ("PR CSV", database.opportunity_csv_bytes(), "Why measurement is hard"),
        ("journalist CSV", database.journalist_csv_bytes(), "Jordan Writer"),
    ]:
        text = data.decode("utf-8-sig")
        rows = list(csv.DictReader(io.StringIO(text)))
        check(f"{label} exports the record", expected in text and len(rows) >= 1, f"rows={len(rows)}")
        check(f"{label} opens cleanly in Excel", data.startswith(b"\xef\xbb\xbf"))

    backup_button = [button for button in app3.button if button.label == "Create database backup"][0]
    backup_button.click()
    app3.run()
    backups = sorted((tmp / "backups").glob("pr_agent_database_*.sqlite3"))
    check("database backup is created", len(backups) == 1, backups)
    if backups:
        with sqlite3.connect(backups[0]) as connection:
            check("backup passes its integrity check", connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok")
            for table, expected in [
                ("listicle_prospects", 1),
                ("pr_opportunities", 1),
                ("journalist_records", 2),
                ("app_state", 1),
            ]:
                count = connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                check(f"backup contains {table}", count == expected, count)

    # --------------------------------------------------------------
    # 6. Data safety edge cases
    # --------------------------------------------------------------
    emit()
    emit("6. Data safety edge cases")

    tricky = ListicleOpportunity(
        publication='Probe "Quoted" Pub',
        listicle_title="=HYPERLINK(\"https://bad.example\",\"click\")",
        listicle_url="https://example.com/tricky/",
        published_or_updated="Unknown",
        listicle_category="emoji ✦ test",
        target_audience="agencies",
        competitors_listed=[],
        brand_currently_listed="Unclear",
        brand_fit="Line one\nLine two",
        inclusion_gap="Unknown",
        placement_type="Unclear",
        contact_route="Unknown",
        recommended_action="Research further",
        evidence="Quotes \" and emoji ✦",
        confidence="Low",
    )
    database.upsert_listicle_prospect(tricky, search_theme="edge cases")
    tricky_row = database.get_listicle_prospect(tricky.listicle_url, tricky.listicle_title, tricky.publication) or {}
    check("special characters survive a round trip", (tricky_row.get("payload") or {}).get("listicle_title") == tricky.listicle_title)
    exported = database.listicle_csv_bytes().decode("utf-8-sig")
    exported_row = [
        row for row in csv.DictReader(io.StringIO(exported))
        if row["url"] == tricky.listicle_url
    ]
    check(
        "exported spreadsheet formulas are defused",
        bool(exported_row) and exported_row[0]["title"].startswith("'="),
        exported_row[0]["title"] if exported_row else "row missing",
    )

    database.save_app_snapshot({"probe": "value"})
    with sqlite3.connect(database.DB_PATH) as connection:
        connection.execute("UPDATE app_state SET payload_json='not valid json' WHERE state_key='active_workspace'")
    check("a damaged workspace snapshot does not crash the library", database.load_app_snapshot() == {})

    legacy_person = JournalistProfile(
        name="Legacy Writer",
        publication="Legacy Pub",
        current_role="Reporter",
        relevant_article_title="Legacy article",
        relevant_article_url="https://example.com/legacy",
        article_date="2025-01-01",
        topic_covered="Legacy topic",
        why_relevant="Legacy reason.",
        suggested_pitch_angle="Legacy angle.",
        author_profile_or_contact_page="Unknown",
        evidence="Legacy evidence.",
        confidence="Low",
    )
    with sqlite3.connect(database.DB_PATH) as connection:
        connection.execute(
            """INSERT INTO journalist_records(
                   record_key, name, publication, relevant_article_url,
                   related_opportunity_url, qualification_status, payload_json,
                   first_seen, updated_at
               ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                database.canonical_url(legacy_person.relevant_article_url),
                legacy_person.name,
                legacy_person.publication,
                legacy_person.relevant_article_url,
                "",
                "Relevant writer",
                database._dump(legacy_person),
                "2026-01-01T00:00:00+00:00",
                "2026-01-01T00:00:00+00:00",
            ),
        )
    database.init_db()
    migrated = database.get_journalist_record(legacy_person, "") or {}
    check("legacy journalist keys are migrated", migrated.get("record_key", "").startswith("journalist:"), migrated.get("record_key"))
    check("migration keeps the saved qualification", migrated.get("qualification_status") == "Relevant writer", migrated.get("qualification_status"))

    emit()
    if FAILURES:
        emit(f"RESULT: {len(FAILURES)} check(s) failed: {', '.join(FAILURES)}")
        emit(f"The temporary test database was kept for inspection: {tmp}")
        return 1

    emit("RESULT: all storage checks passed.")
    emit("Your real research database was not touched.")
    shutil.rmtree(tmp, ignore_errors=True)
    return 0


if __name__ == "__main__":
    exit_code = 1
    try:
        exit_code = main()
    except Exception:
        emit()
        emit("The storage check itself stopped with an error:")
        for line in traceback.format_exc().splitlines():
            emit(line)
    finally:
        log_file.write(f"\nExit code: {exit_code}\n")
        log_file.close()
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        try:
            shutil.copyfile(LATEST_LOG, BACKUPS / f"storage_check_{timestamp}.txt")
        except OSError:
            pass
        print(f"Log: {LATEST_LOG}")
    sys.exit(exit_code)
