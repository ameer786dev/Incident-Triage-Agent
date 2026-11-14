"""Record a real local diagnosis and render an explicitly labeled GIF replay."""
from __future__ import annotations

import argparse
import asyncio
from collections import defaultdict
import json
from pathlib import Path
import textwrap
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
WIDTH, HEIGHT = 1000, 660
BG = "#101722"
FG = "#d8e3ee"
MUTED = "#8d9aab"
GREEN = "#81d6a1"
BLUE = "#87bfff"


def _font(size: int):
    from PIL import ImageFont
    for candidate in (
        "/System/Library/Fonts/Menlo.ttc",
        "/System/Library/Fonts/SFNSMono.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    ):
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size)
    return ImageFont.load_default(size=size)


def _lines(text: str, width: int = 91, limit: int = 4) -> list[str]:
    lines = textwrap.wrap(" ".join(str(text).split()), width=width, break_long_words=True) or [""]
    if len(lines) > limit:
        lines = lines[:limit]
        lines[-1] = lines[-1][:-3] + "..."
    return lines


def _stage_content(alert: dict[str, Any], result: dict[str, Any]) -> list[list[tuple[str, str]]]:
    """Build presentation stages from captured observations, never canned answers."""
    intro = [
        ("$ triage-demo  |  measured run replay", BLUE),
        ("", MUTED),
        (f"ALERT {alert['id']}  service={alert['service']}", GREEN),
        *[(line, FG) for line in _lines(alert["summary"], limit=3)],
        (f"Started: {alert['started_at']}", MUTED),
    ]
    trace = result.get("tool_trace", [])
    grouped: dict[str, list[dict]] = defaultdict(list)
    for entry in trace:
        grouped[entry["service"]].append(entry)
    tool_lines = [("READ-ONLY OBSERVABILITY", BLUE)]
    for service, entries in grouped.items():
        names = ", ".join(f"{e['tool']}={e['status']}" for e in entries)
        tool_lines.append((service, GREEN))
        tool_lines.extend((f"  {line}", FG) for line in _lines(names, width=87, limit=2))
    tool_lines.append((f"Captured {len(trace)} tool calls; full timings saved in demo-result.json", MUTED))
    evidence_lines = [("CITED OBSERVATIONS", BLUE)]
    for evidence in result.get("evidence", [])[:3]:
        evidence_lines.append((f"{evidence['source']} / {evidence['service']} / {evidence['id']}", GREEN))
        evidence_lines.extend((f"  {line}", FG) for line in _lines(evidence["detail"], width=87, limit=3))
    if not result.get("evidence"):
        evidence_lines.append(("No supporting observations were returned.", MUTED))
    diagnosis_lines = [
        ("DIAGNOSIS", BLUE),
        (f"{result['root_cause']}  |  affected service: {result['affected_service']}", GREEN),
        *[(line, FG) for line in _lines(result["summary"], limit=4)],
        (f"Human review requested: {result['needs_human_review']}", MUTED),
        ("", MUTED),
        ("MATCHED RUNBOOKS", BLUE),
    ]
    for book in result.get("runbooks", [])[:3]:
        diagnosis_lines.extend((line, FG) for line in _lines(f"{book['id']}: {book['title']}", limit=2))
    steps = [("NEXT STEPS", BLUE)]
    for index, step in enumerate(result.get("next_steps", [])[:4], start=1):
        steps.extend((line, FG) for line in _lines(f"{index}. {step}", limit=3))
    usage = result.get("usage", {})
    cost = usage.get("estimated_cost_usd")
    cost_label = "not configured" if cost is None else f"${cost:.6f}"
    timing = [
        ("MEASURED RUN", BLUE),
        (f"End-to-end diagnosis: {result['elapsed_ms']:.2f} ms", GREEN),
        (f"Provider: {usage.get('provider', 'unknown')}", FG),
        (f"Hosted model token cost: {cost_label}", FG),
        (f"Tool calls: {len(trace)}", FG),
        ("", MUTED),
        ("Snapshot replay; timings exclude live backend/network delays.", MUTED),
        ("GIF playback is slowed for reading; it is not a wall-clock recording.", MUTED),
        ("Full captured output: demo-result.json", BLUE),
    ]
    return [intro, intro + [("", MUTED)] + tool_lines[:7], tool_lines, evidence_lines, diagnosis_lines, steps, timing]


def render_gif(alert: dict[str, Any], result: dict[str, Any], output: Path) -> None:
    from PIL import Image, ImageDraw
    regular = _font(16)
    small = _font(13)
    title_font = _font(18)
    stages = _stage_content(alert, result)
    frames = []
    for index, lines in enumerate(stages):
        frame = Image.new("RGB", (WIDTH, HEIGHT), BG)
        draw = ImageDraw.Draw(frame)
        draw.rounded_rectangle((16, 16, WIDTH - 16, HEIGHT - 16), radius=14, fill="#141f2d", outline="#2d3e52", width=2)
        draw.rounded_rectangle((17, 17, WIDTH - 17, 66), radius=13, fill="#213047")
        for x, color in ((39, "#f57878"), (62, "#ebc66a"), (85, "#79cf9b")):
            draw.ellipse((x, 34, x + 11, 45), fill=color)
        draw.text((119, 29), "incident-triage-agent", font=title_font, fill=FG)
        draw.text((35, 85), "Recorded local baseline | synthetic incident", font=regular, fill=GREEN)
        draw.text((35, 111), "Actual graph output, presented as a step-by-step replay", font=small, fill=MUTED)
        y = 157
        for line, color in lines:
            if y > 575:
                draw.text((35, y), "... see captured JSON for full output", font=small, fill=MUTED)
                break
            # Apply the same width limit even to IDs or tool labels.
            for wrapped in _lines(line, width=91, limit=2):
                if y > 575:
                    break
                draw.text((35, y), wrapped, font=regular, fill=color)
                y += 24
        draw.line((35, 605, WIDTH - 35, 605), fill="#2d3e52", width=1)
        draw.text((35, 619), f"Stage {index + 1}/{len(stages)}  |  {result['incident_id']}  |  {result['elapsed_ms']:.2f} ms measured", font=small, fill=MUTED)
        frames.append(frame)
    output.parent.mkdir(parents=True, exist_ok=True)
    frames[0].save(output, save_all=True, append_images=frames[1:], duration=[1800, 1800, 2600, 4200, 4200, 4200, 3600], loop=0, optimize=False, disposal=2)


async def record(incident_id: str | None, fixtures: Path, output: Path) -> dict:
    from triage_lab.config import Settings, get_retriever
    from triage_lab.graph import TriageAgent
    from triage_lab.models import Alert
    from triage_lab.observability import SnapshotBackend

    rows = [json.loads(line) for line in fixtures.read_text().splitlines() if line.strip()]
    case = next((row for row in rows if row["id"] == incident_id), None) if incident_id else rows[0]
    if case is None:
        raise ValueError(f"Incident {incident_id!r} is not in {fixtures}")
    settings = Settings(triage_provider="baseline", retrieval_backend="memory", embedding_provider="local", reranker_provider="local", runbook_dir=str(ROOT / "runbooks"))
    # The diagnosis boundary receives no expected labels or generator provenance.
    backend = SnapshotBackend({case["id"]: case["snapshot"]})
    agent = TriageAgent(settings=settings, backend=backend, retriever=get_retriever(settings))
    diagnosis = await agent.diagnose(Alert.model_validate(case["alert"]))
    result = diagnosis.model_dump(mode="json")
    output.parent.mkdir(parents=True, exist_ok=True)
    result_path = output.with_name(output.stem + "-result.json")
    result_path.write_text(json.dumps({"recording": {"kind": "measured local baseline replay", "fixture_file": str(fixtures.relative_to(ROOT)) if fixtures.is_relative_to(ROOT) else str(fixtures), "alert": case["alert"], "playback": "presentation frames; not a wall-clock terminal recording"}, "diagnosis": result}, indent=2) + "\n")
    render_gif(case["alert"], result, output)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--incident", help="Development incident ID; defaults to the first case")
    parser.add_argument("--fixtures", type=Path, default=ROOT / "evals" / "development.jsonl")
    parser.add_argument("--output", type=Path, default=ROOT / "docs" / "demo.gif")
    args = parser.parse_args()
    result = asyncio.run(record(args.incident, args.fixtures.resolve(), args.output.resolve()))
    print(f"Recorded {result['incident_id']}: {result['root_cause']} in {result['elapsed_ms']:.2f} ms")
    print(f"GIF: {args.output}; captured JSON: {args.output.with_name(args.output.stem + '-result.json')}")


if __name__ == "__main__":
    main()
