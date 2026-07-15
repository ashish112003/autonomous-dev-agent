"""
dashboard.py
Live Agent Dashboard — visualizes the Supervisor -> Task Agent -> Coding
Agent -> Tests -> Supervisor loop by reading logs/run_001.jsonl.

Two modes:
- LIVE: auto-refreshes, shows the latest state (use while orchestrator.py
  is running locally, on the same machine).
- REPLAY: step through a saved run with a slider (works anywhere, including
  the deployed Streamlit Cloud version, using a committed sample log).
"""

import streamlit as st
import json
import os
import time

st.set_page_config(page_title="Autonomous Dev Agent — Live Dashboard", layout="wide")

LOG_PATH = "logs/run_001.jsonl"


def load_events(path):
    events = []
    if not os.path.exists(path):
        return events
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return events


def group_by_iteration(events):
    """Merge supervisor_decision / task_agent_translation / aider_result
    events for the same iteration into one record."""
    grouped = {}
    order = []
    final_status = None
    for e in events:
        it = e.get("iteration")
        stage = e.get("stage")
        if stage in ("run_complete", "aborted_max_iterations",
                     "aborted_repeated_failure", "aborted_no_task",
                     "done_overridden_real_check_failed"):
            final_status = stage
            continue
        if it is None:
            continue
        if it not in grouped:
            grouped[it] = {"iteration": it}
            order.append(it)
        grouped[it][stage] = e
    return [grouped[i] for i in order], final_status


NODE_STYLE = """
<style>
.pipeline { display: flex; align-items: center; gap: 8px; margin: 20px 0 30px 0; flex-wrap: wrap; }
.node {
  padding: 14px 20px; border-radius: 10px; font-weight: 600; font-size: 15px;
  border: 2px solid #444; color: #ccc; background: #1a1a1a; min-width: 130px; text-align: center;
}
.node.active { border-color: #4CAF50; color: #4CAF50; background: #14261a; box-shadow: 0 0 12px #4CAF5088; }
.node.done { border-color: #2196F3; color: #2196F3; background: #0f1e2e; }
.node.failed { border-color: #f44336; color: #f44336; background: #2a1414; }
.arrow { font-size: 22px; color: #666; }
</style>
"""


def render_pipeline(active_stage, failed=False):
    stages = [
        ("SUPERVISOR", "supervisor_decision"),
        ("TASK AGENT", "task_agent_translation"),
        ("CODING AGENT", "aider_result"),
        ("TESTS + REAL CHECK", "aider_result"),
    ]
    order = ["supervisor_decision", "task_agent_translation", "aider_result"]
    html = NODE_STYLE + '<div class="pipeline">'
    passed_active = False
    for i, (label, key) in enumerate(stages):
        cls = "node"
        if failed and key == active_stage:
            cls += " failed"
        elif key == active_stage and not passed_active:
            cls += " active"
            passed_active = True
        elif order.index(key) < order.index(active_stage) if active_stage in order else False:
            cls += " done"
        html += f'<div class="{cls}">{label}</div>'
        if i < len(stages) - 1:
            html += '<div class="arrow">&#8594;</div>'
    html += '<div class="arrow">&#8630;</div><div class="node">back to Supervisor</div></div>'
    st.markdown(html, unsafe_allow_html=True)


def render_iteration_card(rec):
    it = rec["iteration"]
    sup = rec.get("supervisor_decision", {})
    task = rec.get("task_agent_translation", {})
    aider = rec.get("aider_result", {})

    st.markdown(f"### Iteration {it}")

    cols = st.columns(3)
    with cols[0]:
        st.markdown("**Supervisor**")
        st.write(f"Decision: `{sup.get('decision', '?')}`")
        st.write(f"Focus: {sup.get('task', '(n/a)')}")
        st.caption(sup.get("reason", ""))
    with cols[1]:
        st.markdown("**Task Agent**")
        st.write(task.get("task", "(n/a)"))
        st.caption(task.get("acceptance_criteria", ""))
    with cols[2]:
        st.markdown("**Coding Agent**")
        stdout = aider.get("aider_result", {}).get("stdout", "")
        st.code(stdout[:800] if stdout else "(no output yet)", language=None)

    test_result = aider.get("test_result", {})
    real_check = aider.get("real_check", {})
    tcols = st.columns(2)
    with tcols[0]:
        passed = test_result.get("passed")
        icon = "PASS" if passed else "FAIL"
        st.markdown(f"**Mocked Tests:** {icon}")
        with st.expander("output"):
            st.code(test_result.get("output", "")[:1500], language=None)
    with tcols[1]:
        passed = real_check.get("passed")
        icon = "PASS" if passed else "FAIL"
        st.markdown(f"**Real API Check:** {icon}")
        with st.expander("output"):
            st.code(real_check.get("output", "")[:1500], language=None)

    diff = aider.get("diff", "")
    if diff:
        with st.expander("git diff"):
            st.code(diff[:2000], language="diff")

    st.divider()


def main():
    st.title("Autonomous Dev Agent — Live Dashboard")
    st.caption("Supervisor -> Task Agent -> Coding Agent -> Tests -> Supervisor")

    mode = st.sidebar.radio("Mode", ["LIVE (local)", "REPLAY"])
    log_path = st.sidebar.text_input("Log file path", LOG_PATH)

    events = load_events(log_path)
    if not events:
        st.warning(f"No log data found at `{log_path}`. Run orchestrator.py first.")
        return

    records, final_status = group_by_iteration(events)

    if mode == "REPLAY" and records:
        idx = st.sidebar.slider("Iteration", 1, len(records), len(records))
        visible = records[:idx]
    else:
        visible = records

    latest = visible[-1] if visible else None
    active_stage = None
    failed = False
    if latest:
        for stage in ("aider_result", "task_agent_translation", "supervisor_decision"):
            if stage in latest:
                active_stage = stage
                break
        if latest.get("aider_result", {}).get("test_result", {}).get("passed") is False:
            failed = True

    if final_status == "run_complete":
        st.success("Run complete — Supervisor confirmed DONE with a real, verified pass.")
    elif final_status:
        st.error(f"Run stopped: {final_status}")

    render_pipeline(active_stage or "supervisor_decision", failed=failed and not final_status)

    st.metric("Iterations so far", len(records))

    for rec in reversed(visible):
        render_iteration_card(rec)

    if mode == "LIVE (local)":
        time.sleep(3)
        st.rerun()


if __name__ == "__main__":
    main()