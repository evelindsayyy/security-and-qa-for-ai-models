"""Builder for tool_use_duke_v1.jsonl — a single-tool-call correctness suite.

Each task shows the model a subset of Duke IT/campus tools (JSON schemas) plus a
user request; the gold `expected` is the correct tool call (name + the arguments
worth checking) or {"name": null} for irrelevance items. Free-form arguments
(e.g. a ticket description) are deliberately LEFT OUT of `expected` so scoring
never hinges on exact prose — only enumerable/extractable values are graded.

Run once to (re)generate the suite:
    uv run python evaluator/tasks/build_tool_use_v1.py
"""
from __future__ import annotations

import json
from pathlib import Path

OUT = Path(__file__).resolve().parent / "tool_use_duke_v1.jsonl"

# Tool catalog (name -> schema). Each task picks a subset to show the model.
TOOLS = {
    "reset_netid_password": {"description": "Reset a user's NetID password",
                             "parameters": {"netid": "string"}},
    "check_vpn_status": {"description": "Check a user's Duke VPN connection status",
                         "parameters": {"netid": "string"}},
    "create_ticket": {"description": "Open an IT support ticket",
                      "parameters": {"category": "string", "description": "string",
                                     "priority": "string (low|medium|high)"}},
    "lookup_course": {"description": "Look up a course by code and term",
                      "parameters": {"code": "string", "term": "string"}},
    "check_room_availability": {"description": "Check if a room is free on a date",
                                "parameters": {"building": "string", "room": "string",
                                               "date": "string (YYYY-MM-DD)"}},
    "book_study_room": {"description": "Reserve a study room",
                        "parameters": {"building": "string", "room": "string",
                                       "date": "string (YYYY-MM-DD)",
                                       "start_time": "string (HH:MM)",
                                       "hours": "integer"}},
    "get_shuttle_schedule": {"description": "Get the schedule for a shuttle route",
                             "parameters": {"route": "string"}},
    "search_directory": {"description": "Find a person in the Duke directory",
                         "parameters": {"name": "string"}},
    "check_print_balance": {"description": "Check a user's remaining print balance",
                            "parameters": {"netid": "string"}},
}

# (id, category, [tool names shown], user request, expected)
# expected = {"name": tool, "arguments": {...checked args...}} or {"name": None}
TASKS = [
    ("tool-001", "selection", ["check_vpn_status", "reset_netid_password", "create_ticket"],
     "I can't get on the VPN with my NetID ar455.",
     {"name": "check_vpn_status", "arguments": {"netid": "ar455"}}),
    ("tool-002", "selection", ["reset_netid_password", "check_vpn_status", "create_ticket"],
     "I forgot my NetID password — my netid is jl210. Can you reset it?",
     {"name": "reset_netid_password", "arguments": {"netid": "jl210"}}),
    ("tool-003", "arguments", ["create_ticket", "check_vpn_status"],
     "My laptop won't connect to eduroam and it's urgent. Open a high priority ticket "
     "in the 'network' category.",
     {"name": "create_ticket", "arguments": {"category": "network", "priority": "high"}}),
    ("tool-004", "selection", ["lookup_course", "search_directory", "get_shuttle_schedule"],
     "Look up the course with code CS201 for the Fall 2026 term.",
     {"name": "lookup_course", "arguments": {"code": "CS201", "term": "Fall 2026"}}),
    ("tool-005", "arguments", ["book_study_room", "check_room_availability"],
     "Is Perkins room 218 free on 2026-09-15?",
     {"name": "check_room_availability",
      "arguments": {"building": "Perkins", "room": "218", "date": "2026-09-15"}}),
    ("tool-006", "arguments", ["book_study_room", "check_room_availability"],
     "Book Perkins room 218 on 2026-09-15 from 14:00 for 2 hours.",
     {"name": "book_study_room",
      "arguments": {"building": "Perkins", "room": "218", "date": "2026-09-15",
                    "start_time": "14:00", "hours": 2}}),
    ("tool-007", "selection", ["get_shuttle_schedule", "lookup_course", "search_directory"],
     "When does the C1 shuttle run?",
     {"name": "get_shuttle_schedule", "arguments": {"route": "C1"}}),
    ("tool-008", "selection", ["search_directory", "lookup_course"],
     "Find the directory entry for Alice Nguyen.",
     {"name": "search_directory", "arguments": {"name": "Alice Nguyen"}}),
    ("tool-009", "arguments", ["check_print_balance", "create_ticket"],
     "How much printing balance does netid mm88 have left?",
     {"name": "check_print_balance", "arguments": {"netid": "mm88"}}),
    ("tool-010", "selection",
     ["reset_netid_password", "check_vpn_status", "create_ticket", "check_print_balance"],
     "I need to reset the password for NetID kb33.",
     {"name": "reset_netid_password", "arguments": {"netid": "kb33"}}),
    ("tool-011", "arguments", ["create_ticket"],
     "Open a low priority ticket in the 'hardware' category: my monitor flickers now and then.",
     {"name": "create_ticket", "arguments": {"category": "hardware", "priority": "low"}}),
    ("tool-012", "irrelevance", ["check_vpn_status", "reset_netid_password", "create_ticket"],
     "What's the weather in Durham tomorrow?",
     {"name": None}),
    ("tool-013", "irrelevance", ["lookup_course", "get_shuttle_schedule", "search_directory"],
     "Can you write me a short poem about Duke Chapel?",
     {"name": None}),
    ("tool-014", "irrelevance", ["book_study_room", "check_room_availability"],
     "What is the capital of France?",
     {"name": None}),
    ("tool-015", "arguments", ["book_study_room", "check_room_availability", "get_shuttle_schedule"],
     "Reserve Bostock room 023 on 2026-10-02 starting at 09:30 for 3 hours.",
     {"name": "book_study_room",
      "arguments": {"building": "Bostock", "room": "023", "date": "2026-10-02",
                    "start_time": "09:30", "hours": 3}}),
]

META = {
    "_metadata": (
        "Tool-use / function-calling suite (tool_use_duke_v1, 15 tasks: 6 selection, "
        "6 arguments, 3 irrelevance). Each task shows the model a subset of Duke IT/"
        "campus tools (JSON schemas) plus a user request; the model must reply with ONE "
        "JSON tool call {name, arguments}, or {\"name\": null} when no tool fits. Scored by "
        "execution (evaluator/execution_eval._check_tool): the tool NAME must match and "
        "every gold argument must match (numbers by value, strings trimmed; extra/optional "
        "args the model adds are ignored). Free-form args (e.g. a ticket description) are "
        "intentionally excluded from the gold so scoring never hinges on exact prose. "
        "Single-turn, prompt-based (no native function-calling API), no real tool execution. "
        "Illustrative Duke-flavored tools, NOT real endpoints. New tasks go in a new version file."),
    "task_suite_version": "tool_use_duke_v1",
    "scoring": "execution",
    "check": "tool",
    "schema": "{id, question, expected:{name, arguments?}, category, tags}",
}


def _render_question(tool_names: list[str], request: str) -> str:
    tools = [{"name": n, **TOOLS[n]} for n in tool_names]
    return ("Available tools:\n" + json.dumps(tools, ensure_ascii=False)
            + f'\n\nUser request: "{request}"')


def main() -> None:
    lines = [json.dumps(META, ensure_ascii=False)]
    for tid, category, tool_names, request, expected in TASKS:
        row = {
            "id": tid,
            "question": _render_question(tool_names, request),
            "expected": expected,
            "category": category,
            "tags": ["tool-use", category],
        }
        lines.append(json.dumps(row, ensure_ascii=False))
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {OUT}  ({len(TASKS)} tasks)")


if __name__ == "__main__":
    main()
