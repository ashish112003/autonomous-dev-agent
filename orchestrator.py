

"""
orchestrator.py
Persistent Planner (Groq) <-> Coding Agent (Aider) autonomous loop.

The Planner is one continuous conversation (message history persists across
the whole run). Each turn it sees the real task, the real code diff, and the
real test output from the last attempt, then decides CONTINUE / FIX / DONE.
"""

import os
import re
import json
import glob
import subprocess
import time
from datetime import datetime

from dotenv import load_dotenv
from groq import Groq

from supervisor_prompt import SUPERVISOR_PROMPT
from task_agent_prompt import TASK_AGENT_PROMPT
from coding_agent_prompt import CODING_AGENT_PROMPT

load_dotenv()

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
SUPERVISOR_MODEL = "llama-3.3-70b-versatile"   # needs the strongest judgment
TASK_AGENT_MODEL = "llama-3.3-70b-versatile"   # precise technical writing — keep strong too
CODING_AGENT_MODEL = "llama-3.3-70b-versatile" # the actual coding model

WORKSPACE_DIR = "workspace"
LOGS_DIR = "logs"
LOG_FILE = os.path.join(LOGS_DIR, "run_001.jsonl")
PROJECT_STATE_PATH = "project_state.json"

MAX_ITERATIONS = 40
TASK_TIMEOUT_SECONDS = 300
MAX_REPEATED_FAILURES = 4

client = Groq(api_key=GROQ_API_KEY)


def log_event(event: dict):
    """Append one structured event to the run log."""
    os.makedirs(LOGS_DIR, exist_ok=True)
    event["timestamp"] = datetime.utcnow().isoformat()
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(event) + "\n")


ORIGINAL_GOAL = (
    "Build detector.py with parse_bullets(text) and detect(text). detect() "
    "sends bullets to Groq and returns JSON {duplicates, contradictions}. "
    "Must handle empty input, missing API key, HTTP errors, malformed JSON. "
    "Must correctly find multiple real duplicate/contradiction relationships, "
    "verified by both mocked unit tests AND a real Groq API call."
)


def load_project_state() -> dict:
    """Persistent memory of the whole build, independent of chat history
    trimming — this is what makes the Supervisor's 'eyes' genuinely
    continuous instead of only remembering the last couple of exchanges."""
    if os.path.exists(PROJECT_STATE_PATH):
        try:
            with open(PROJECT_STATE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "original_goal": ORIGINAL_GOAL,
        "completed_tasks": [],
        "unresolved_issues": [],
        "current_phase": "starting",
    }


def save_project_state(state: dict):
    with open(PROJECT_STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def update_project_state(state: dict, iteration: int, decision: str, focus: str,
                          reason: str, test_result: dict, real_check: dict) -> dict:
    """Update the persistent record after one real attempt."""
    state["current_phase"] = focus or state.get("current_phase", "")

    tests_ok = bool(test_result.get("passed"))
    real_ok = bool(real_check.get("passed"))

    if decision.upper() == "FIX":
        # Record the problem. Keep it bounded — only the most recent
        # distinct issues, so this stays a genuinely useful summary rather
        # than an ever-growing dump.
        state.setdefault("unresolved_issues", [])
        entry = {"iteration": iteration, "focus": focus, "reason": reason}
        # avoid piling up near-duplicate entries about the same focus
        state["unresolved_issues"] = [
            e for e in state["unresolved_issues"] if e.get("focus") != focus
        ]
        state["unresolved_issues"].append(entry)
        state["unresolved_issues"] = state["unresolved_issues"][-8:]

    if tests_ok and real_ok:
        # Real, verified progress — record it and clear resolved issues
        # tied to this focus.
        state.setdefault("completed_tasks", [])
        state["completed_tasks"].append({
            "iteration": iteration, "focus": focus,
            "outcome": "mocked tests + real API check both passed",
        })
        state["unresolved_issues"] = [
            e for e in state.get("unresolved_issues", []) if e.get("focus") != focus
        ]

    return state


def project_state_summary(state: dict) -> str:
    """Compact text form of the state to inject into every Supervisor call,
    regardless of how much chat history has been trimmed."""
    completed = state.get("completed_tasks", [])
    unresolved = state.get("unresolved_issues", [])
    lines = [
        f"ORIGINAL GOAL: {state.get('original_goal', '')}",
        f"CURRENT PHASE: {state.get('current_phase', '')}",
        f"COMPLETED TASKS ({len(completed)}):",
    ]
    for c in completed[-10:]:
        lines.append(f"  - [iter {c['iteration']}] {c['focus']} -> {c['outcome']}")
    lines.append(f"UNRESOLVED ISSUES ({len(unresolved)}):")
    for u in unresolved:
        lines.append(f"  - [iter {u['iteration']}] {u['focus']}: {u['reason'][:150]}")
    if not unresolved:
        lines.append("  (none currently known)")
    return "\n".join(lines)


MAX_HISTORY_EXCHANGES = 2  # how many past (assistant, user) turn-pairs to keep


def trim_history(messages: list) -> list:
    """Keep the system prompt + initial goal, plus only the most recent
    exchanges, so token usage per call doesn't keep growing every iteration."""
    head = messages[:2]  # system prompt + first user goal message
    tail = messages[2:]
    keep = MAX_HISTORY_EXCHANGES * 2
    if len(tail) > keep:
        tail = tail[-keep:]
    return head + tail


def call_planner(messages: list, max_retries: int = 3) -> dict:
    """Call the Planner LLM and parse its structured response.
    Retries with backoff on rate limits so the loop doesn't silently
    skip forward when Groq throttles a request."""
    last_error = None
    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model=SUPERVISOR_MODEL,
                messages=trim_history(messages),
                temperature=0.0,
                max_tokens=500,
            )
            break
        except Exception as e:
            last_error = e
            wait = 5 * (attempt + 1)
            print(f"Planner call failed ({e}). Retrying in {wait}s...")
            time.sleep(wait)
    else:
        raise RuntimeError(f"Planner call failed after {max_retries} retries: {last_error}")

    text = response.choices[0].message.content.strip()

    decision = _extract(text, "DECISION")
    task = _extract(text, "FOCUS")
    reason = _extract(text, "REASON")

    return {
        "raw": text,
        "decision": decision,
        "task": task,
        "reason": reason,
        "acceptance_criteria": "",
    }


def _extract(text: str, field: str) -> str:
    """Pull a single field out of the Planner's structured response."""
    pattern = rf"{field}:\s*(.*?)(?=\n[A-Z_]+:|\Z)"
    match = re.search(pattern, text, re.DOTALL)
    return match.group(1).strip() if match else ""


ALLOWED_WORKSPACE_FILES = {"detector.py", "test_detector.py"}


def enforce_file_scope():
    """Delete any .py file in workspace/ that isn't explicitly allowed.
    Aider cannot reliably delete files through a chat instruction, so this
    guardrail is enforced directly in code instead of relying on the model."""
    for path in glob.glob(os.path.join(WORKSPACE_DIR, "*.py")):
        if os.path.basename(path) not in ALLOWED_WORKSPACE_FILES:
            try:
                os.remove(path)
                print(f"[scope guard] removed disallowed file: {path}")
            except OSError:
                pass


def call_task_agent(focus: str, reason: str, context: str) -> dict:
    """Translate the Supervisor's single FOCUS item into one precise,
    narrowly-scoped instruction for Aider."""
    messages = [
        {"role": "system", "content": TASK_AGENT_PROMPT},
        {"role": "user", "content": (
            f"SUPERVISOR FOCUS: {focus}\n"
            f"SUPERVISOR REASON: {reason}\n\n"
            f"CURRENT STATE:\n{context}\n\n"
            "Translate this into one precise coding instruction."
        )},
    ]
    last_error = None
    for attempt in range(3):
        try:
            response = client.chat.completions.create(
                model=TASK_AGENT_MODEL,
                messages=messages,
                temperature=0.0,
            )
            break
        except Exception as e:
            last_error = e
            wait = 5 * (attempt + 1)
            print(f"Task Agent call failed ({e}). Retrying in {wait}s...")
            time.sleep(wait)
    else:
        raise RuntimeError(f"Task Agent call failed after 3 retries: {last_error}")

    text = response.choices[0].message.content.strip()
    task = _extract(text, "TASK")
    acceptance = _extract(text, "ACCEPTANCE_CRITERIA")
    return {"raw": text, "task": task, "acceptance_criteria": acceptance}


DETECTOR_PATH = os.path.join(WORKSPACE_DIR, "detector.py")
TEST_DETECTOR_PATH = os.path.join(WORKSPACE_DIR, "test_detector.py")
ALLOWED_FILENAMES = {"detector.py", "test_detector.py"}


def _read_file(path: str) -> str:
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception:
            return ""
    return ""


def _path_for(filename: str):
    """Resolve an allowed filename to its real path, or None if disallowed."""
    if filename not in ALLOWED_FILENAMES:
        return None
    return os.path.join(WORKSPACE_DIR, filename)


# --- Real tools the Coding Agent can actually call ---

def tool_list_files() -> str:
    files = sorted(glob.glob(os.path.join(WORKSPACE_DIR, "*.py")))
    if not files:
        return "(workspace is empty — no files exist yet)"
    return "\n".join(os.path.basename(f) for f in files)


def tool_read_file(filename: str) -> str:
    path = _path_for(filename)
    if path is None:
        return f"ERROR: '{filename}' is not an allowed filename. Only detector.py and test_detector.py exist."
    content = _read_file(path)
    return content if content else f"(file '{filename}' does not exist yet — it is empty)"


def tool_write_file(filename: str, content: str) -> str:
    path = _path_for(filename)
    if path is None:
        return f"ERROR: '{filename}' is not an allowed filename. Only detector.py and test_detector.py may be written."
    os.makedirs(WORKSPACE_DIR, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content.rstrip() + "\n")
    return f"OK: wrote {len(content)} characters to {filename}"


def tool_run_tests() -> str:
    result = run_tests()
    status = "PASSED" if result.get("passed") else "FAILED (or no tests found)"
    return f"pytest result: {status}\n\n{result.get('output', '')}"


def tool_git_diff() -> str:
    diff = get_git_diff()
    return diff if diff else "(no diff — no committed changes yet in this run)"


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List the .py files currently present in the workspace.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the current full content of a file before editing it.",
            "parameters": {
                "type": "object",
                "properties": {"filename": {"type": "string", "description": "'detector.py' or 'test_detector.py'"}},
                "required": ["filename"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write the COMPLETE new content of a file, overwriting whatever was there.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {"type": "string", "description": "'detector.py' or 'test_detector.py'"},
                    "content": {"type": "string", "description": "The full new file content."},
                },
                "required": ["filename", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_tests",
            "description": "Run pytest on test_detector.py and see the real pass/fail output.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "git_diff",
            "description": "See the diff of the most recent committed change in workspace/.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]

TOOL_DISPATCH = {
    "list_files": lambda args: tool_list_files(),
    "read_file": lambda args: tool_read_file(args.get("filename", "")),
    "write_file": lambda args: tool_write_file(args.get("filename", ""), args.get("content", "")),
    "run_tests": lambda args: tool_run_tests(),
    "git_diff": lambda args: tool_git_diff(),
}

MAX_TOOL_ROUNDS = 12


def run_coding_agent(task: str) -> dict:
    """A genuine agentic loop: the model gets real tools (list/read/write
    files, run tests, view diffs) and decides what to inspect and change,
    round by round — it is not handed the files and told to blindly
    rewrite them in one shot."""
    messages = [
        {"role": "system", "content": CODING_AGENT_PROMPT},
        {"role": "user", "content": f"TASK: {task}\n\nBegin by inspecting the current state before making any changes."},
    ]

    transcript = []
    files_written = set()
    final_text = ""

    for round_num in range(1, MAX_TOOL_ROUNDS + 1):
        last_error = None
        response = None
        for attempt in range(3):
            try:
                response = client.chat.completions.create(
                    model=CODING_AGENT_MODEL,
                    messages=messages,
                    tools=TOOLS,
                    tool_choice="auto",
                    temperature=0.0,
                )
                break
            except Exception as e:
                last_error = e
                time.sleep(5 * (attempt + 1))
        if response is None:
            transcript.append(f"[Coding Agent call failed after 3 retries: {last_error}]")
            break

        msg = response.choices[0].message
        tool_calls = getattr(msg, "tool_calls", None)

        if not tool_calls:
            final_text = msg.content or ""
            transcript.append(f"[round {round_num}] Coding Agent final summary: {final_text}")
            break

        messages.append({
            "role": "assistant",
            "content": msg.content or "",
            "tool_calls": [
                {"id": tc.id, "type": "function",
                 "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                for tc in tool_calls
            ],
        })

        for tc in tool_calls:
            fn_name = tc.function.name
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}

            handler = TOOL_DISPATCH.get(fn_name)
            if handler is None:
                result = f"ERROR: unknown tool '{fn_name}'"
            else:
                result = handler(args)

            if fn_name == "write_file" and result.startswith("OK:"):
                files_written.add(args.get("filename", ""))

            transcript.append(f"[round {round_num}] CALL {fn_name}({args}) -> {result[:500]}")

            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "name": fn_name,
                "content": result[:4000],
            })
    else:
        transcript.append(f"[Stopped: reached MAX_TOOL_ROUNDS={MAX_TOOL_ROUNDS} without the agent finishing on its own]")

    # Commit whatever was actually written, from the project root
    if files_written:
        try:
            paths = [os.path.join(WORKSPACE_DIR, f) for f in files_written]
            subprocess.run(["git", "add"] + paths, capture_output=True, text=True)
            subprocess.run(["git", "commit", "-m", f"task: {task[:60]}"], capture_output=True, text=True)
        except Exception:
            pass

    stdout = "\n".join(transcript)[-6000:]
    return {
        "stdout": stdout,
        "stderr": "",
        "returncode": 0 if files_written else 1,
        "timed_out": False,
    }


def get_git_diff() -> str:
    """Diff of the last committed change inside workspace/."""
    result = subprocess.run(
        ["git", "diff", "HEAD~1", "HEAD", "--", WORKSPACE_DIR],
        capture_output=True, text=True,
    )
    return result.stdout[-3000:]


def run_tests() -> dict:
    """Run pytest inside workspace/ and capture pass/fail + traceback."""
    test_files = glob.glob(os.path.join(WORKSPACE_DIR, "test_*.py"))
    if not test_files:
        return {"ran": False, "passed": False, "output": "No test files found yet."}

    result = subprocess.run(
        ["python", "-m", "pytest", "-v"] + test_files,
        capture_output=True, text=True,
    )
    return {
        "ran": True,
        "passed": result.returncode == 0,
        "output": (result.stdout + result.stderr)[-4000:],
    }


def run_real_integration_check() -> dict:
    """Make an ACTUAL Groq API call through the current detector.py — not a
    mock. Uses a richer real example (6 bullets, 2 known duplicate pairs,
    2 known contradiction pairs) so genuinely getting this right requires
    real correctness, not a lucky minimal pass."""
    if not os.path.exists(DETECTOR_PATH):
        return {"ran": False, "passed": False, "output": "detector.py does not exist yet."}

    script = (
        "import sys, json, traceback\n"
        "sys.path.insert(0, 'workspace')\n"
        "try:\n"
        "    import importlib\n"
        "    import detector\n"
        "    importlib.reload(detector)\n"
        "    text = (\n"
        "        '1. The rate for Material A shall be Rs. 50 per kg.\\n'\n"
        "        '2. Rate of Material A is fifty rupees per kg.\\n'\n"
        "        '3. The rate for Material A shall be Rs. 80 per kg.\\n'\n"
        "        '4. Payment terms: 30 days from the date of invoice.\\n'\n"
        "        '5. Invoice payment shall be released within thirty days of invoicing.\\n'\n"
        "        '6. Payment shall be made within 45 days from invoice date.'\n"
        "    )\n"
        "    result = detector.detect(text)\n"
        "    if not isinstance(result, dict) or 'duplicates' not in result or 'contradictions' not in result:\n"
        "        print('FAIL: result is not a dict with duplicates/contradictions keys:', repr(result))\n"
        "        sys.exit(1)\n"
        "    def flat(pairs):\n"
        "        return set(frozenset(p) for p in pairs)\n"
        "    dup_found = flat(result['duplicates'])\n"
        "    contra_found = flat(result['contradictions'])\n"
        "    expected_dup = frozenset({1, 2})\n"
        "    expected_contra_1 = frozenset({1, 3})\n"
        "    expected_contra_2 = frozenset({4, 6})\n"
        "    missing = []\n"
        "    if not any(expected_dup <= s for s in dup_found):\n"
        "        missing.append('duplicate 1&2 (rate of Material A)')\n"
        "    if not any(expected_contra_1 <= s for s in contra_found):\n"
        "        missing.append('contradiction 1&3 (Rs 50 vs Rs 80)')\n"
        "    if not any(expected_contra_2 <= s for s in contra_found):\n"
        "        missing.append('contradiction 4&6 (30 days vs 45 days)')\n"
        "    if missing:\n"
        "        print(f'FAIL: missing expected relationships: {missing}. Full result: {result}')\n"
        "        sys.exit(1)\n"
        "    print('PASS:', json.dumps(result))\n"
        "except Exception:\n"
        "    print('FAIL: real call raised an exception:')\n"
        "    traceback.print_exc()\n"
        "    sys.exit(1)\n"
    )

    try:
        result = subprocess.run(
            ["python", "-c", script],
            capture_output=True, text=True, timeout=60,
        )
        output = (result.stdout + result.stderr)[-3000:]
        return {
            "ran": True,
            "passed": result.returncode == 0 and "PASS:" in result.stdout,
            "output": output,
        }
    except subprocess.TimeoutExpired:
        return {"ran": True, "passed": False, "output": "Real integration check timed out (60s) — likely a hung/incorrect API call."}


def get_all_workspace_files() -> str:
    """Full contents of every .py file in workspace/, so the Planner can
    catch mismatches between files (e.g. wrong function name imported)
    that a single-file diff would hide."""
    parts = []
    for path in sorted(glob.glob(os.path.join(WORKSPACE_DIR, "*.py"))):
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            parts.append(f"--- {path} ---\n{content}")
        except Exception:
            continue
    return "\n\n".join(parts)[-5000:]  # bounded


def build_feedback_message(task: str, aider_result: dict, diff: str, test_result: dict, real_check: dict, project_state: dict) -> str:
    """Everything the Planner needs to actually 'see' the real outcome,
    PLUS the persistent project state — so even if chat history has been
    trimmed, the Supervisor still has real continuity."""
    return f"""PROJECT STATE (persistent — survives chat history trimming):
{project_state_summary(project_state)}

TASK ATTEMPTED:
{task}

AIDER OUTPUT:
{aider_result['stdout']}
{'[TIMED OUT]' if aider_result['timed_out'] else ''}

GIT DIFF (last change only):
{diff if diff else '(no diff captured)'}

CURRENT FULL CONTENTS OF ALL WORKSPACE FILES (check for cross-file mismatches):
{get_all_workspace_files()}

TEST RESULTS (mocked unit tests — these can pass even if the real API integration is broken):
ran: {test_result['ran']}
passed: {test_result.get('passed')}
output:
{test_result['output']}

REAL INTEGRATION CHECK (an ACTUAL Groq API call, not mocked — this is the
real proof the tool works, since mocked tests alone cannot catch a wrong
model name, wrong request format, or a broken prompt):
ran: {real_check['ran']}
passed: {real_check.get('passed')}
output:
{real_check['output']}

DONE is only valid if BOTH the mocked tests AND the real integration check
have passed. If the real integration check failed, you must choose FIX and
address the SPECIFIC error shown above, even if the mocked tests passed.

Based on this real feedback, respond with your next DECISION / TASK / REASON / ACCEPTANCE_CRITERIA.
"""


def main():
    os.makedirs(WORKSPACE_DIR, exist_ok=True)

    project_state = load_project_state()
    save_project_state(project_state)

    messages = [
        {"role": "system", "content": SUPERVISOR_PROMPT},
        {"role": "user", "content": (
            "Begin. What is the first thing to focus on to build the "
            "duplicate/contradiction detector described in the goal?\n\n"
            f"PROJECT STATE (persistent memory from prior work, if any):\n"
            f"{project_state_summary(project_state)}"
        )},
    ]

    recent_failure_signatures = []
    last_test_result = {"passed": False}
    last_real_check = {"passed": False}

    for i in range(1, MAX_ITERATIONS + 1):
        print(f"\n=== Iteration {i} ===")

        plan = call_planner(messages)
        decision = plan["decision"]
        focus = plan["task"]  # reuse _extract("TASK") slot for FOCUS field
        reason = plan["reason"]

        print(f"DECISION: {decision}")
        print(f"FOCUS: {focus}")
        print(f"REASON: {reason}")

        log_event({"iteration": i, "stage": "supervisor_decision", **plan})

        if decision.upper() == "DONE":
            if last_test_result.get("passed") and last_real_check.get("passed"):
                print("\nSupervisor reports DONE, and both mocked tests AND "
                      "the real API integration check have genuinely passed. "
                      "Stopping loop.")
                project_state["current_phase"] = "complete"
                save_project_state(project_state)
                log_event({"iteration": i, "stage": "run_complete"})
                break
            else:
                print("\nSupervisor said DONE, but the real integration check "
                      "has not actually passed yet — overriding and forcing "
                      "another FIX round with the real evidence.")
                log_event({"iteration": i, "stage": "done_overridden_real_check_failed"})
                messages.append({"role": "assistant", "content": plan["raw"]})
                messages.append({"role": "user", "content": (
                    "You said DONE, but the real integration check has NOT "
                    "passed yet (see the REAL INTEGRATION CHECK section from "
                    "the last feedback — either it hasn't been run yet, or it "
                    f"failed with: {last_real_check.get('output', '(no output yet)')}). "
                    "DONE is only valid when both the mocked tests AND the "
                    "real integration check pass. Respond again with a FIX "
                    "focus that addresses the real integration check's "
                    "specific failure."
                )})
                continue

        if not focus:
            print("Supervisor returned no focus. Stopping to avoid a blind loop.")
            log_event({"iteration": i, "stage": "aborted_no_task"})
            break

        # Task Agent translates the Supervisor's focus into a precise instruction
        context = get_all_workspace_files() or "(workspace is empty)"
        translated = call_task_agent(focus, reason, context)
        print(f"TASK AGENT TASK: {translated['task']}")
        log_event({"iteration": i, "stage": "task_agent_translation", **translated})

        precise_task = translated["task"] or focus  # fallback if translation failed

        aider_result = run_coding_agent(precise_task)
        print(f"CODING AGENT TRANSCRIPT:\n{aider_result['stdout']}\n")
        enforce_file_scope()
        diff = get_git_diff()
        test_result = run_tests()

        # Only spend a real API call checking integration once the mocked
        # tests actually pass — no point burning a call on code that's
        # already known-broken at the unit level.
        if test_result.get("passed"):
            real_check = run_real_integration_check()
        else:
            real_check = {"ran": False, "passed": False,
                           "output": "Skipped — mocked unit tests did not pass yet, so the real check was not run."}

        last_test_result = test_result
        last_real_check = real_check

        project_state = update_project_state(
            project_state, i, decision, focus, reason, test_result, real_check
        )
        save_project_state(project_state)

        log_event({
            "iteration": i, "stage": "aider_result",
            "aider_result": aider_result, "diff": diff,
            "test_result": test_result, "real_check": real_check,
            "project_state": project_state,
        })

        # Repeated-failure safety control — only counts REAL test failures
        # (a test actually ran and failed). "No test files found yet" is a
        # normal transitional state early in the build, not a stuck loop.
        failure_signature = test_result.get("output", "")[-300:]
        if test_result.get("ran") and not test_result.get("passed"):
            recent_failure_signatures.append(failure_signature)
        else:
            recent_failure_signatures = []

        if recent_failure_signatures.count(failure_signature) >= MAX_REPEATED_FAILURES:
            print("\nSame failure repeated. Stopping loop (safety control).")
            log_event({"iteration": i, "stage": "aborted_repeated_failure"})
            break

        feedback = build_feedback_message(precise_task, aider_result, diff, test_result, real_check, project_state)

        messages.append({"role": "assistant", "content": plan["raw"]})
        messages.append({"role": "user", "content": feedback})

    else:
        print(f"\nReached max iterations ({MAX_ITERATIONS}). Stopping.")
        log_event({"stage": "aborted_max_iterations"})


if __name__ == "__main__":
    main()


















