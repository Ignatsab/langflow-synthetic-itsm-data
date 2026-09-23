"""Generate deterministic mock AutoSys dependency, snapshot, and history datasets."""

from __future__ import annotations

import json
import random
from copy import deepcopy
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path


SEED = 20260921
UTC = timezone.utc
OUTPUT_DIR = Path(__file__).resolve().parent

REGIONS = {
    "APAC": {"schedule_utc": "00:30", "timezone": "Asia/Singapore", "volume_base": 820_000, "sla_minutes": 180},
    "EMEA": {"schedule_utc": "04:30", "timezone": "Europe/Paris", "volume_base": 1_050_000, "sla_minutes": 180},
    "AMER": {"schedule_utc": "11:30", "timezone": "America/New_York", "volume_base": 1_300_000, "sla_minutes": 200},
}

TEMPLATES = [
    {"suffix": "INIT", "description": "Initialize business date and regional workspace", "base_minutes": 4, "depends_on": [], "volume_sensitive": False},
    {"suffix": "EXTRACT_TRANSACTIONS", "description": "Extract regional transaction data", "base_minutes": 36, "depends_on": ["INIT"], "volume_sensitive": True},
    {"suffix": "EXTRACT_REFERENCE", "description": "Extract reference and exchange-rate data", "base_minutes": 12, "depends_on": ["INIT"], "volume_sensitive": False},
    {"suffix": "EXTRACT_CUSTOMERS", "description": "Extract regional customer master data", "base_minutes": 20, "depends_on": ["INIT"], "volume_sensitive": True},
    {"suffix": "VALIDATE_TRANSACTIONS", "description": "Validate transaction completeness and control totals", "base_minutes": 16, "depends_on": ["EXTRACT_TRANSACTIONS"], "volume_sensitive": True},
    {"suffix": "ENRICH_DATA", "description": "Join validated transactions with reference and customer data", "base_minutes": 25, "depends_on": ["VALIDATE_TRANSACTIONS", "EXTRACT_REFERENCE", "EXTRACT_CUSTOMERS"], "volume_sensitive": True},
    {"suffix": "BUILD_REPORT", "description": "Build the regional SOD report package", "base_minutes": 32, "depends_on": ["ENRICH_DATA"], "volume_sensitive": True},
    {"suffix": "PUBLISH_REPORT", "description": "Publish the regional reports to the delivery location", "base_minutes": 8, "depends_on": ["BUILD_REPORT"], "volume_sensitive": False, "delivery_milestone": True},
    {"suffix": "ARCHIVE", "description": "Archive inputs, outputs, and execution evidence", "base_minutes": 10, "depends_on": ["PUBLISH_REPORT"], "volume_sensitive": True, "terminal_for_box": True},
    {"suffix": "SEND_STATUS", "description": "Generate and send the regional completion notification", "base_minutes": 3, "depends_on": ["PUBLISH_REPORT"], "volume_sensitive": False, "terminal_for_box": True},
]

MOCK_HOLIDAYS = {
    "APAC": {date(2026, 8, 14)},
    "EMEA": {date(2026, 8, 17)},
    "AMER": {date(2026, 9, 7)},
}


def iso(value: datetime | None) -> str | None:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z") if value else None


def scheduled_at(day: date, region: str) -> datetime:
    hour, minute = map(int, REGIONS[region]["schedule_utc"].split(":"))
    return datetime.combine(day, time(hour, minute), tzinfo=UTC)


def box_name(region: str) -> str:
    return f"BOX_SOD_{region}_REPORTS"


def job_name(region: str, suffix: str) -> str:
    return f"CMD_{region}_{suffix}"


def build_job_catalog() -> list[dict]:
    jobs: list[dict] = []
    for region, config in REGIONS.items():
        children = [job_name(region, template["suffix"]) for template in TEMPLATES]
        jobs.append(
            {
                "job_name": box_name(region),
                "job_type": "BOX",
                "description": f"Orchestrates {region} start-of-day regional report delivery",
                "region": region,
                "timezone": config["timezone"],
                "run_calendar": "WEEKDAYS",
                "scheduled_time_utc": config["schedule_utc"],
                "delivery_sla_minutes": config["sla_minutes"],
                "delivery_milestone_job": job_name(region, "PUBLISH_REPORT"),
                "dependencies": [],
                "child_jobs": children,
                "command": None,
                "owner_group": f"regional-reporting-{region.lower()}",
            }
        )
        for template in TEMPLATES:
            suffix = template["suffix"]
            jobs.append(
                {
                    "job_name": job_name(region, suffix),
                    "job_type": "CMD",
                    "box_name": box_name(region),
                    "description": template["description"],
                    "region": region,
                    "dependencies": [
                        {"job_name": job_name(region, parent), "condition": "SUCCESS"}
                        for parent in template["depends_on"]
                    ],
                    "command": f"/opt/aps/sod/{suffix.lower()}.sh --region {region.lower()}",
                    "base_duration_minutes": template["base_minutes"],
                    "volume_sensitive": template["volume_sensitive"],
                    "delivery_milestone": template.get("delivery_milestone", False),
                    "terminal_for_box": template.get("terminal_for_box", False),
                    "owner_group": f"regional-reporting-{region.lower()}",
                }
            )
    return jobs


def build_baseline_snapshot() -> dict:
    business_date = "2026-09-21"
    as_of = "2026-09-21T06:15:00Z"
    states: list[dict] = []

    apac_times = {
        "INIT": ("2026-09-21T00:30:00Z", "2026-09-21T00:34:00Z"),
        "EXTRACT_TRANSACTIONS": ("2026-09-21T00:35:00Z", "2026-09-21T01:12:00Z"),
        "EXTRACT_REFERENCE": ("2026-09-21T00:35:00Z", "2026-09-21T00:48:00Z"),
        "EXTRACT_CUSTOMERS": ("2026-09-21T00:35:00Z", "2026-09-21T00:57:00Z"),
        "VALIDATE_TRANSACTIONS": ("2026-09-21T01:13:00Z", "2026-09-21T01:28:00Z"),
        "ENRICH_DATA": ("2026-09-21T01:29:00Z", "2026-09-21T01:55:00Z"),
        "BUILD_REPORT": ("2026-09-21T01:56:00Z", "2026-09-21T02:29:00Z"),
        "PUBLISH_REPORT": ("2026-09-21T02:30:00Z", "2026-09-21T02:38:00Z"),
        "ARCHIVE": ("2026-09-21T02:39:00Z", "2026-09-21T02:50:00Z"),
        "SEND_STATUS": ("2026-09-21T02:39:00Z", "2026-09-21T02:42:00Z"),
    }
    states.append({"job_name": box_name("APAC"), "job_type": "BOX", "region": "APAC", "status": "SUCCESS", "actual_start": "2026-09-21T00:30:00Z", "actual_end": "2026-09-21T02:50:00Z", "elapsed_seconds": 8400, "latest_status_message": "All child CMD jobs completed; report delivered at 02:38 UTC."})
    for suffix, (start, end) in apac_times.items():
        states.append({"job_name": job_name("APAC", suffix), "job_type": "CMD", "region": "APAC", "status": "SUCCESS", "actual_start": start, "actual_end": end, "elapsed_seconds": int((datetime.fromisoformat(end.replace("Z", "+00:00")) - datetime.fromisoformat(start.replace("Z", "+00:00"))).total_seconds()), "latest_status_message": "Completed normally."})

    states.append({"job_name": box_name("EMEA"), "job_type": "BOX", "region": "EMEA", "status": "RUNNING", "actual_start": "2026-09-21T04:30:00Z", "actual_end": None, "elapsed_seconds": 6300, "latest_status_message": "Waiting for the long-running transaction extract."})
    emea_complete = {
        "INIT": ("2026-09-21T04:30:00Z", "2026-09-21T04:35:00Z"),
        "EXTRACT_REFERENCE": ("2026-09-21T04:36:00Z", "2026-09-21T04:49:00Z"),
        "EXTRACT_CUSTOMERS": ("2026-09-21T04:36:00Z", "2026-09-21T04:58:00Z"),
    }
    for template in TEMPLATES:
        suffix = template["suffix"]
        if suffix in emea_complete:
            start, end = emea_complete[suffix]
            state = {"status": "SUCCESS", "actual_start": start, "actual_end": end, "elapsed_seconds": int((datetime.fromisoformat(end.replace("Z", "+00:00")) - datetime.fromisoformat(start.replace("Z", "+00:00"))).total_seconds()), "latest_status_message": "Completed normally."}
        elif suffix == "EXTRACT_TRANSACTIONS":
            state = {"status": "RUNNING", "actual_start": "2026-09-21T04:36:00Z", "actual_end": None, "elapsed_seconds": 5940, "latest_status_message": "Processing elevated input volume; no failure reported."}
        else:
            state = {"status": "WAITING", "actual_start": None, "actual_end": None, "elapsed_seconds": 0, "latest_status_message": "Waiting for predecessor success."}
        states.append({"job_name": job_name("EMEA", suffix), "job_type": "CMD", "region": "EMEA", **state})

    states.append({"job_name": box_name("AMER"), "job_type": "BOX", "region": "AMER", "status": "NOT_STARTED", "actual_start": None, "actual_end": None, "elapsed_seconds": 0, "latest_status_message": "Scheduled for 11:30 UTC."})
    for template in TEMPLATES:
        states.append({"job_name": job_name("AMER", template["suffix"]), "job_type": "CMD", "region": "AMER", "status": "NOT_STARTED", "actual_start": None, "actual_end": None, "elapsed_seconds": 0, "latest_status_message": "Regional box has not started."})

    return {
        "business_date": business_date,
        "as_of": as_of,
        "job_states": states,
        "email_recipients": {
            "APAC": ["apac-report-ops@example.test"],
            "EMEA": ["emea-report-ops@example.test"],
            "AMER": ["amer-report-ops@example.test"],
            "GLOBAL": ["global-sod-operations@example.test"]
        },
        "status_email_requirements": [
            "Report each region as complete, running, waiting, not started, failed, or blocked.",
            "Include actual delivery time when complete and predicted P50/P90 delivery time when incomplete.",
            "Name the current or blocking CMD job and identify SLA risk.",
            "Do not report a BOX as complete until all terminal child CMD jobs succeed."
        ]
    }


def shift_timestamp(value: str | None, days: int = 0, hours: int = 0) -> str | None:
    if value is None:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return iso(parsed + timedelta(days=days, hours=hours))


def shifted_snapshot(baseline: dict, business_day: date) -> dict:
    snapshot = deepcopy(baseline)
    day_offset = (business_day - date(2026, 9, 21)).days
    snapshot["business_date"] = business_day.isoformat()
    snapshot["as_of"] = shift_timestamp(snapshot["as_of"], days=day_offset)
    for state in snapshot["job_states"]:
        state["actual_start"] = shift_timestamp(state["actual_start"], days=day_offset)
        state["actual_end"] = shift_timestamp(state["actual_end"], days=day_offset)
    return snapshot


def update_state(snapshot: dict, name: str, **changes: object) -> None:
    state = next(item for item in snapshot["job_states"] if item["job_name"] == name)
    state.update(changes)


def apply_emea_scenario(snapshot: dict, scenario: str) -> None:
    day = snapshot["business_date"]

    if scenario in {"enrichment_running", "report_build_running", "validation_failed"}:
        update_state(
            snapshot,
            job_name("EMEA", "EXTRACT_TRANSACTIONS"),
            status="SUCCESS",
            actual_start=f"{day}T04:36:00Z",
            actual_end=f"{day}T05:18:00Z",
            elapsed_seconds=2520,
            latest_status_message="Completed normally.",
        )
        update_state(
            snapshot,
            job_name("EMEA", "VALIDATE_TRANSACTIONS"),
            status="SUCCESS",
            actual_start=f"{day}T05:19:00Z",
            actual_end=f"{day}T05:35:00Z",
            elapsed_seconds=960,
            latest_status_message="Completed normally.",
        )

    if scenario == "enrichment_running":
        update_state(
            snapshot,
            box_name("EMEA"),
            latest_status_message="Data enrichment is running after all extracts completed.",
        )
        update_state(
            snapshot,
            job_name("EMEA", "ENRICH_DATA"),
            status="RUNNING",
            actual_start=f"{day}T05:36:00Z",
            actual_end=None,
            elapsed_seconds=2340,
            latest_status_message="Joining transaction, reference, and customer datasets.",
        )

    elif scenario == "report_build_running":
        update_state(
            snapshot,
            job_name("EMEA", "ENRICH_DATA"),
            status="SUCCESS",
            actual_start=f"{day}T05:36:00Z",
            actual_end=f"{day}T05:58:00Z",
            elapsed_seconds=1320,
            latest_status_message="Completed normally.",
        )
        update_state(
            snapshot,
            job_name("EMEA", "BUILD_REPORT"),
            status="RUNNING",
            actual_start=f"{day}T05:59:00Z",
            actual_end=None,
            elapsed_seconds=960,
            latest_status_message="Rendering the regional report package.",
        )
        update_state(
            snapshot,
            box_name("EMEA"),
            latest_status_message="Report build is running; publication has not started.",
        )

    elif scenario == "validation_failed":
        update_state(
            snapshot,
            job_name("EMEA", "VALIDATE_TRANSACTIONS"),
            status="FAILED",
            actual_start=f"{day}T05:19:00Z",
            actual_end=f"{day}T05:36:00Z",
            elapsed_seconds=1020,
            latest_status_message="Control totals did not match the extracted source totals.",
        )
        for suffix in ("ENRICH_DATA", "BUILD_REPORT", "PUBLISH_REPORT", "ARCHIVE", "SEND_STATUS"):
            update_state(
                snapshot,
                job_name("EMEA", suffix),
                status="BLOCKED",
                actual_start=None,
                actual_end=None,
                elapsed_seconds=0,
                latest_status_message="Blocked by CMD_EMEA_VALIDATE_TRANSACTIONS failure.",
            )
        update_state(
            snapshot,
            box_name("EMEA"),
            status="FAILED",
            actual_end=f"{day}T05:36:00Z",
            elapsed_seconds=3960,
            latest_status_message="Validation failed; five downstream CMD jobs are blocked.",
        )

    elif scenario == "recovery_complete":
        states = {item["job_name"]: item for item in snapshot["job_states"]}
        for template in TEMPLATES:
            suffix = template["suffix"]
            apac_state = states[job_name("APAC", suffix)]
            update_state(
                snapshot,
                job_name("EMEA", suffix),
                status="SUCCESS",
                actual_start=shift_timestamp(apac_state["actual_start"], hours=4),
                actual_end=shift_timestamp(apac_state["actual_end"], hours=4),
                elapsed_seconds=apac_state["elapsed_seconds"],
                latest_status_message="Completed normally after the prior-day validation issue was resolved.",
            )
        snapshot["as_of"] = f"{day}T07:15:00Z"
        update_state(
            snapshot,
            box_name("EMEA"),
            status="SUCCESS",
            actual_start=f"{day}T04:30:00Z",
            actual_end=f"{day}T06:50:00Z",
            elapsed_seconds=8400,
            latest_status_message="All child CMD jobs completed; report delivered at 06:38 UTC.",
        )


def build_current_status_dataset() -> dict:
    baseline = build_baseline_snapshot()
    scenarios = [
        (date(2026, 9, 21), "extract_delayed", "EMEA transaction extraction is running longer than usual."),
        (date(2026, 9, 22), "enrichment_running", "EMEA extraction completed and data enrichment is running."),
        (date(2026, 9, 23), "report_build_running", "EMEA report generation is in progress and publication is waiting."),
        (date(2026, 9, 24), "validation_failed", "EMEA validation failed and downstream jobs are blocked."),
        (date(2026, 9, 25), "recovery_complete", "EMEA recovered and completed successfully after the prior-day failure."),
    ]
    snapshots: list[dict] = []
    for business_day, scenario_id, description in scenarios:
        snapshot = shifted_snapshot(baseline, business_day)
        snapshot["scenario_id"] = scenario_id
        snapshot["scenario_description"] = description
        apply_emea_scenario(snapshot, scenario_id)
        snapshots.append(snapshot)

    return {
        "metadata": {
            "dataset_name": "autosys_sod_daily_status_snapshots",
            "generated_at": "2026-09-21T00:00:00Z",
            "snapshot_start": scenarios[0][0].isoformat(),
            "snapshot_end": scenarios[-1][0].isoformat(),
            "snapshot_count": len(snapshots),
            "time_basis": "UTC",
            "snapshot_semantics": "Each snapshot is an independent mock point-in-time scheduler state for ETA and status-email testing.",
        },
        "snapshots": snapshots,
    }


def build_dependencies_dataset() -> dict:
    return {
        "metadata": {
            "dataset_name": "autosys_sod_regional_report_dependencies",
            "generated_at": "2026-09-21T00:00:00Z",
            "timezone_for_schedules": "UTC",
            "box_semantics": "A BOX is a logical container and executes no script. It completes only after all terminal child CMD jobs reach SUCCESS.",
            "delivery_semantics": "Regional report delivery occurs when the configured PUBLISH_REPORT CMD succeeds; BOX completion may occur later after archive and notification jobs.",
            "dependency_semantics": "A CMD becomes eligible only when every dependency condition is satisfied. Independent eligible CMD jobs may run in parallel."
        },
        "calendars": [
            {"calendar_name": "WEEKDAYS", "included_weekdays": ["MON", "TUE", "WED", "THU", "FRI"], "regional_holidays_by_region": {region: sorted(day.isoformat() for day in days) for region, days in MOCK_HOLIDAYS.items()}, "run_on_regional_holidays": True}
        ],
        "jobs": build_job_catalog()
    }


def business_days(start: date, end: date) -> list[date]:
    days: list[date] = []
    current = start
    while current <= end:
        if current.weekday() < 5:
            days.append(current)
        current += timedelta(days=1)
    return days


def duration_seconds(template: dict, volume_ratio: float, rng: random.Random) -> int:
    volume_factor = (0.55 + 0.45 * volume_ratio) if template["volume_sensitive"] else 1.0
    noise = max(0.72, rng.gauss(1.0, 0.11))
    return max(60, round(template["base_minutes"] * 60 * volume_factor * noise))


def build_historical_dataset() -> dict:
    rng = random.Random(SEED)
    command_runs: list[dict] = []
    box_runs: list[dict] = []
    for day in business_days(date(2026, 7, 27), date(2026, 9, 18)):
        split = "evaluation" if day >= date(2026, 9, 14) else "train"
        for region, config in REGIONS.items():
            schedule = scheduled_at(day, region)
            is_holiday = day in MOCK_HOLIDAYS[region]
            weekday_factor = 1.12 if day.weekday() == 0 else 1.04 if day.weekday() == 4 else 1.0
            holiday_factor = 0.58 if is_holiday else 1.0
            volume = max(50_000, round(config["volume_base"] * weekday_factor * holiday_factor * rng.uniform(0.86, 1.17)))
            volume_ratio = volume / config["volume_base"]
            region_run_id = f"{day.strftime('%Y%m%d')}-{region}"
            outcomes: dict[str, dict] = {}
            path_info: dict[str, tuple[int, list[str]]] = {}

            for template in TEMPLATES:
                suffix = template["suffix"]
                name = job_name(region, suffix)
                deps = [job_name(region, parent) for parent in template["depends_on"]]
                blocked_by = [dep for dep in deps if outcomes[dep]["status"] != "SUCCESS"]
                if blocked_by:
                    record = {
                        "run_id": f"{region_run_id}-{suffix}", "region_run_id": region_run_id, "business_date": day.isoformat(), "weekday": day.strftime("%A"), "dataset_split": split,
                        "region": region, "box_name": box_name(region), "job_name": name, "job_type": "CMD", "status": "BLOCKED",
                        "scheduled_box_start": iso(schedule), "eligible_at": None, "actual_start": None, "actual_end": None, "duration_seconds": None,
                        "queue_wait_seconds": None, "dependency_wait_seconds": None, "retry_count": 0, "exit_code": None, "failure_category": "UPSTREAM_FAILURE",
                        "blocked_by": blocked_by, "predecessor_jobs": deps, "input_record_count": volume, "is_regional_holiday": is_holiday
                    }
                    outcomes[name] = record
                    path_info[name] = (0, [name])
                    command_runs.append(record)
                    continue

                eligible = max([schedule, *[datetime.fromisoformat(outcomes[dep]["actual_end"].replace("Z", "+00:00")) for dep in deps]])
                queue_wait = rng.randint(20, 220)
                start = eligible + timedelta(seconds=queue_wait)
                run_duration = duration_seconds(template, volume_ratio, rng)
                retry_probability = 0.07 if suffix in {"EXTRACT_TRANSACTIONS", "EXTRACT_CUSTOMERS", "BUILD_REPORT"} else 0.025
                retry_count = 1 if rng.random() < retry_probability else 0
                if retry_count:
                    run_duration += rng.randint(180, 600)
                final_failure_probability = 0.012 if suffix in {"EXTRACT_TRANSACTIONS", "VALIDATE_TRANSACTIONS", "BUILD_REPORT", "PUBLISH_REPORT"} else 0.003
                failed = rng.random() < final_failure_probability
                status = "FAILED" if failed else "SUCCESS"
                end = start + timedelta(seconds=run_duration)
                dependency_wait = round((eligible - schedule).total_seconds())
                failure_category = rng.choice(["SOURCE_TIMEOUT", "DATA_QUALITY", "SCRIPT_ERROR"]) if failed else None
                record = {
                    "run_id": f"{region_run_id}-{suffix}", "region_run_id": region_run_id, "business_date": day.isoformat(), "weekday": day.strftime("%A"), "dataset_split": split,
                    "region": region, "box_name": box_name(region), "job_name": name, "job_type": "CMD", "status": status,
                    "scheduled_box_start": iso(schedule), "eligible_at": iso(eligible), "actual_start": iso(start), "actual_end": iso(end), "duration_seconds": run_duration,
                    "queue_wait_seconds": queue_wait, "dependency_wait_seconds": dependency_wait, "retry_count": retry_count, "exit_code": 1 if failed else 0,
                    "failure_category": failure_category, "blocked_by": [], "predecessor_jobs": deps, "input_record_count": volume, "is_regional_holiday": is_holiday
                }
                outcomes[name] = record
                command_runs.append(record)
                if deps:
                    parent_elapsed, parent_path = max((path_info[dep] for dep in deps), key=lambda item: item[0])
                else:
                    parent_elapsed, parent_path = 0, []
                path_info[name] = (parent_elapsed + queue_wait + run_duration, [*parent_path, name])

            terminal_names = [job_name(region, template["suffix"]) for template in TEMPLATES if template.get("terminal_for_box")]
            completed_ends = [datetime.fromisoformat(record["actual_end"].replace("Z", "+00:00")) for record in outcomes.values() if record["actual_end"]]
            box_end = max(completed_ends) if completed_ends else None
            box_status = "SUCCESS" if all(outcomes[name]["status"] == "SUCCESS" for name in terminal_names) else "FAILED"
            publish = outcomes[job_name(region, "PUBLISH_REPORT")]
            delivery_at = datetime.fromisoformat(publish["actual_end"].replace("Z", "+00:00")) if publish["status"] == "SUCCESS" else None
            sla_deadline = schedule + timedelta(minutes=config["sla_minutes"])
            if box_status == "SUCCESS":
                critical_endpoint = max(terminal_names, key=lambda name: path_info[name][0])
            else:
                failed_names = [name for name, record in outcomes.items() if record["status"] == "FAILED"]
                critical_endpoint = max(failed_names, key=lambda name: path_info[name][0])
            box_runs.append(
                {
                    "region_run_id": region_run_id, "business_date": day.isoformat(), "weekday": day.strftime("%A"), "dataset_split": split, "region": region,
                    "box_name": box_name(region), "job_type": "BOX", "status": box_status, "scheduled_start": iso(schedule), "actual_start": iso(schedule),
                    "delivery_milestone_job": job_name(region, "PUBLISH_REPORT"), "delivery_at": iso(delivery_at),
                    "delivery_duration_seconds": round((delivery_at - schedule).total_seconds()) if delivery_at else None,
                    "delivery_sla_at": iso(sla_deadline), "delivery_sla_met": bool(delivery_at and delivery_at <= sla_deadline),
                    "actual_end": iso(box_end), "box_duration_seconds": round((box_end - schedule).total_seconds()) if box_end else None,
                    "critical_path_jobs": path_info[critical_endpoint][1], "input_record_count": volume, "is_regional_holiday": is_holiday,
                    "successful_cmd_count": sum(record["status"] == "SUCCESS" for record in outcomes.values()),
                    "failed_cmd_count": sum(record["status"] == "FAILED" for record in outcomes.values()),
                    "blocked_cmd_count": sum(record["status"] == "BLOCKED" for record in outcomes.values()),
                    "total_retry_count": sum(record["retry_count"] for record in outcomes.values())
                }
            )

    return {
        "metadata": {
            "dataset_name": "autosys_sod_regional_report_history",
            "random_seed": SEED,
            "history_start": "2026-07-27",
            "history_end": "2026-09-18",
            "time_basis": "UTC",
            "training_target_command": "duration_seconds",
            "training_target_delivery": "delivery_duration_seconds",
            "prediction_intervals_recommended": [0.5, 0.9],
            "split_policy": "Dates through 2026-09-11 are train; 2026-09-14 through 2026-09-18 are evaluation.",
            "box_duration_note": "BOX duration is derived from the dependency graph and parallel execution; it is not the sum of CMD durations."
        },
        "command_runs": command_runs,
        "box_runs": box_runs
    }


def main() -> None:
    dependencies = build_dependencies_dataset()
    current_status = build_current_status_dataset()
    history = build_historical_dataset()
    (OUTPUT_DIR / "autosys_job_dependencies.json").write_text(json.dumps(dependencies, indent=2) + "\n", encoding="utf-8")
    (OUTPUT_DIR / "autosys_current_sod_snapshot.json").write_text(json.dumps(current_status, indent=2) + "\n", encoding="utf-8")
    (OUTPUT_DIR / "autosys_execution_history.json").write_text(json.dumps(history, indent=2) + "\n", encoding="utf-8")
    print(f"Generated {len(dependencies['jobs'])} job definitions")
    print(f"Generated {len(current_status['snapshots'])} daily SOD snapshots")
    print(f"Generated {sum(len(snapshot['job_states']) for snapshot in current_status['snapshots'])} current SOD job states")
    print(f"Generated {len(history['command_runs'])} CMD runs and {len(history['box_runs'])} BOX runs")


if __name__ == "__main__":
    main()
