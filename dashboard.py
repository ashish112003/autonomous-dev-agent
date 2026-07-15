# """
# dashboard.py
# Two tabs:
# 1. Analyze a Document — upload/paste text, watch live status, get real
#    duplicate/contradiction results (calls the actual detector.py + Groq).
# 2. How It Was Built — replay of the autonomous build process
#    (Supervisor -> Task Agent -> Coding Agent -> Tests).
# """

# import streamlit as st
# import json
# import os
# import sys
# import time

# st.set_page_config(page_title="Duplicate/Contradiction Detector", layout="wide")

# sys.path.insert(0, "workspace")

# LOG_PATH = "logs/run_001.jsonl"


# # ---------- Shared: load API key from Streamlit secrets or .env ----------
# def get_api_key():
#     if "GROQ_API_KEY" in st.secrets:
#         return st.secrets["GROQ_API_KEY"]
#     return os.environ.get("GROQ_API_KEY")


# # Must set this BEFORE importing orchestrator, since orchestrator reads
# # GROQ_API_KEY from the environment at import time.
# _key = get_api_key()
# if _key:
#     os.environ["GROQ_API_KEY"] = _key


# # ---------- TAB 1: Analyze a Document ----------
# def merge_pairs_into_groups(pairs):
#     parent = {}

#     def find(x):
#         parent.setdefault(x, x)
#         while parent[x] != x:
#             parent[x] = parent[parent[x]]
#             x = parent[x]
#         return x

#     def union(a, b):
#         ra, rb = find(a), find(b)
#         if ra != rb:
#             parent[ra] = rb

#     for pair in pairs:
#         for item in pair:
#             find(item)
#         for i in range(1, len(pair)):
#             union(pair[0], pair[i])

#     groups = {}
#     for item in parent:
#         root = find(item)
#         groups.setdefault(root, set()).add(item)
#     return [sorted(g) for g in groups.values()]


# def render_analyze_tab():
#     st.header("Analyze a Document")
#     st.caption("Paste numbered bulleted statements")

#     text = st.text_area("Paste text:", height=250,
#                          placeholder="1. The rate for Material A shall be Rs. 50 per kg.\n2. ...")

#     if st.button("Analyze", type="primary", disabled=not text.strip()):
#         os.environ["GROQ_API_KEY"] = get_api_key() or ""

#         status_box = st.status("Starting analysis...", expanded=True)

#         status_box.write("Step 1/4: Parsing bullets...")
#         time.sleep(0.4)
#         try:
#             from detector import detect, parse_bullets
#         except ImportError as e:
#             status_box.update(label="Failed to load detector.py", state="error")
#             st.error(f"Could not import detector.py from workspace/: {e}")
#             return

#         bullets = parse_bullets(text)
#         status_box.write(f"Found {len(bullets)} bullets.")

#         status_box.write("Step 2/4: Sending to Groq API...")
#         time.sleep(0.3)

#         try:
#             result = detect(text)
#         except Exception as e:
#             status_box.update(label="Analysis failed", state="error")
#             st.error(f"detect() raised an exception: {e}")
#             return

#         status_box.write("Step 3/4: Parsing response...")
#         time.sleep(0.3)

#         status_box.write("Step 4/4: Done.")
#         status_box.update(label="Analysis complete", state="complete")

#         bullet_map = {b["id"]: b["text"] for b in bullets}
#         dup_groups = merge_pairs_into_groups(result.get("duplicates", []))
#         contra_groups = merge_pairs_into_groups(result.get("contradictions", []))

#         col1, col2 = st.columns(2)
#         with col1:
#             st.subheader(f"Duplicates ({len(dup_groups)})")
#             if not dup_groups:
#                 st.write("None found.")
#             for group in dup_groups:
#                 with st.container(border=True):
#                     for bid in group:
#                         st.write(f"**{bid}.** {bullet_map.get(bid, bullet_map.get(str(bid), '?'))}")

#         with col2:
#             st.subheader(f"Contradictions ({len(contra_groups)})")
#             if not contra_groups:
#                 st.write("None found.")
#             for group in contra_groups:
#                 with st.container(border=True):
#                     for bid in group:
#                         st.write(f"**{bid}.** {bullet_map.get(bid, bullet_map.get(str(bid), '?'))}")


# # ---------- TAB 2: How It Was Built (existing replay dashboard) ----------
# def load_events(path):
#     events = []
#     if not os.path.exists(path):
#         return events
#     with open(path, "r", encoding="utf-8") as f:
#         for line in f:
#             line = line.strip()
#             if not line:
#                 continue
#             try:
#                 events.append(json.loads(line))
#             except json.JSONDecodeError:
#                 continue
#     return events


# def group_by_iteration(events):
#     grouped = {}
#     order = []
#     final_status = None
#     for e in events:
#         it = e.get("iteration")
#         stage = e.get("stage")
#         if stage in ("run_complete", "aborted_max_iterations",
#                      "aborted_repeated_failure", "aborted_no_task",
#                      "done_overridden_real_check_failed"):
#             final_status = stage
#             continue
#         if it is None:
#             continue
#         if it not in grouped:
#             grouped[it] = {"iteration": it}
#             order.append(it)
#         grouped[it][stage] = e
#     return [grouped[i] for i in order], final_status


# NODE_STYLE = """
# <style>
# .pipeline { display: flex; align-items: center; gap: 8px; margin: 20px 0 30px 0; flex-wrap: wrap; }
# .node {
#   padding: 14px 20px; border-radius: 10px; font-weight: 600; font-size: 15px;
#   border: 2px solid #444; color: #ccc; background: #1a1a1a; min-width: 130px; text-align: center;
# }
# .node.active { border-color: #4CAF50; color: #4CAF50; background: #14261a; box-shadow: 0 0 12px #4CAF5088; }
# .node.done { border-color: #2196F3; color: #2196F3; background: #0f1e2e; }
# .node.failed { border-color: #f44336; color: #f44336; background: #2a1414; }
# .arrow { font-size: 22px; color: #666; }
# </style>
# """


# def render_pipeline(active_stage, failed=False):
#     stages = [("SUPERVISOR", "supervisor_decision"), ("TASK AGENT", "task_agent_translation"),
#               ("CODING AGENT", "aider_result"), ("TESTS + REAL CHECK", "aider_result")]
#     order = ["supervisor_decision", "task_agent_translation", "aider_result"]
#     html = NODE_STYLE + '<div class="pipeline">'
#     passed_active = False
#     for i, (label, key) in enumerate(stages):
#         cls = "node"
#         if failed and key == active_stage:
#             cls += " failed"
#         elif key == active_stage and not passed_active:
#             cls += " active"
#             passed_active = True
#         elif order.index(key) < order.index(active_stage) if active_stage in order else False:
#             cls += " done"
#         html += f'<div class="{cls}">{label}</div>'
#         if i < len(stages) - 1:
#             html += '<div class="arrow">&#8594;</div>'
#     html += '<div class="arrow">&#8630;</div><div class="node">back to Supervisor</div></div>'
#     st.markdown(html, unsafe_allow_html=True)


# def render_iteration_card(rec):
#     it = rec["iteration"]
#     sup = rec.get("supervisor_decision", {})
#     task = rec.get("task_agent_translation", {})
#     aider = rec.get("aider_result", {})

#     st.markdown(f"### Iteration {it}")
#     cols = st.columns(3)
#     with cols[0]:
#         st.markdown("**Supervisor**")
#         st.write(f"Decision: `{sup.get('decision', '?')}`")
#         st.write(f"Focus: {sup.get('task', '(n/a)')}")
#         st.caption(sup.get("reason", ""))
#     with cols[1]:
#         st.markdown("**Task Agent**")
#         st.write(task.get("task", "(n/a)"))
#         st.caption(task.get("acceptance_criteria", ""))
#     with cols[2]:
#         st.markdown("**Coding Agent**")
#         stdout = aider.get("aider_result", {}).get("stdout", "")
#         st.code(stdout[:800] if stdout else "(no output yet)", language=None)

#     test_result = aider.get("test_result", {})
#     real_check = aider.get("real_check", {})
#     tcols = st.columns(2)
#     with tcols[0]:
#         st.markdown(f"**Mocked Tests:** {'PASS' if test_result.get('passed') else 'FAIL'}")
#         with st.expander("output"):
#             st.code(test_result.get("output", "")[:1500], language=None)
#     with tcols[1]:
#         st.markdown(f"**Real API Check:** {'PASS' if real_check.get('passed') else 'FAIL'}")
#         with st.expander("output"):
#             st.code(real_check.get("output", "")[:1500], language=None)

#     diff = aider.get("diff", "")
#     if diff:
#         with st.expander("git diff"):
#             st.code(diff[:2000], language="diff")
#     st.divider()



# def render_build_tab():
#     st.header("How It Was Built")
#     st.caption("Supervisor -> Task Agent -> Coding Agent -> Tests -> Supervisor")
#     render_replay_tab()


# def render_replay_tab():
#     events = load_events(LOG_PATH)
#     if not events:
#         st.warning(f"No log data found at `{LOG_PATH}`.")
#         return

#     records, final_status = group_by_iteration(events)

#     if records:
#         idx = st.slider("Iteration", 1, len(records), len(records))
#         visible = records[:idx]
#     else:
#         visible = records

#     latest = visible[-1] if visible else None
#     active_stage = None
#     failed = False
#     if latest:
#         for stage in ("aider_result", "task_agent_translation", "supervisor_decision"):
#             if stage in latest:
#                 active_stage = stage
#                 break
#         if latest.get("aider_result", {}).get("test_result", {}).get("passed") is False:
#             failed = True

#     if final_status == "run_complete":
#         st.success("Run complete — Supervisor confirmed DONE with a real, verified pass.")
#     elif final_status:
#         st.error(f"Run stopped: {final_status}")

#     render_pipeline(active_stage or "supervisor_decision", failed=failed and not final_status)
#     st.metric("Iterations", len(records))
#     for rec in reversed(visible):
#         render_iteration_card(rec)


# def main():
#     st.title("Duplicate / Contradiction Detector")
#     tab1, tab2 = st.tabs(["How It Was Built", "Analyze a Document"])
#     with tab1:
#         render_build_tab()
#     with tab2:
#         render_analyze_tab()


# if __name__ == "__main__":
#     main()




"""
dashboard.py
Two tabs:
1. Analyze a Document — upload/paste text, watch live status, get real
   duplicate/contradiction results (calls the actual detector.py + Groq).
2. How It Was Built — replay of the autonomous build process
   (Supervisor -> Task Agent -> Coding Agent -> Tests).
"""

import streamlit as st
import json
import os
import sys
import time

st.set_page_config(page_title="Duplicate/Contradiction Detector", layout="wide")

sys.path.insert(0, "workspace")

LOG_PATH = "logs/run_001.jsonl"


# ---------- Shared: load API key from Streamlit secrets or .env ----------
def get_api_key():
    if "GROQ_API_KEY" in st.secrets:
        return st.secrets["GROQ_API_KEY"]
    return os.environ.get("GROQ_API_KEY")


# Must set this BEFORE importing orchestrator, since orchestrator reads
# GROQ_API_KEY from the environment at import time.
_key = get_api_key()
if _key:
    os.environ["GROQ_API_KEY"] = _key


# ---------- TAB 1: Analyze a Document ----------
def merge_pairs_into_groups(pairs):
    parent = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for pair in pairs:
        for item in pair:
            find(item)
        for i in range(1, len(pair)):
            union(pair[0], pair[i])

    groups = {}
    for item in parent:
        root = find(item)
        groups.setdefault(root, set()).add(item)
    return [sorted(g) for g in groups.values()]


def render_analyze_tab():
    st.header("Analyze a Document")
    st.caption("Paste numbered bulleted statements")

    text = st.text_area("Paste text:", height=250,
                         placeholder="1. The rate for Material A shall be Rs. 50 per kg.\n2. ...")

    if st.button("Analyze", type="primary", disabled=not text.strip()):
        os.environ["GROQ_API_KEY"] = get_api_key() or ""

        status_box = st.status("Starting analysis...", expanded=True)

        status_box.write("Step 1/4: Parsing bullets...")
        time.sleep(0.4)
        try:
            from detector import detect, parse_bullets
        except ImportError as e:
            status_box.update(label="Failed to load detector.py", state="error")
            st.error(f"Could not import detector.py from workspace/: {e}")
            return

        bullets = parse_bullets(text)
        status_box.write(f"Found {len(bullets)} bullets.")

        status_box.write("Step 2/4: Sending to Groq API...")
        time.sleep(0.3)

        try:
            result = detect(text)
        except Exception as e:
            status_box.update(label="Analysis failed", state="error")
            st.error(f"detect() raised an exception: {e}")
            return

        status_box.write("Step 3/4: Parsing response...")
        time.sleep(0.3)

        status_box.write("Step 4/4: Done.")
        status_box.update(label="Analysis complete", state="complete")

        bullet_map = {b["id"]: b["text"] for b in bullets}
        dup_groups = merge_pairs_into_groups(result.get("duplicates", []))
        contra_groups = merge_pairs_into_groups(result.get("contradictions", []))

        col1, col2 = st.columns(2)
        with col1:
            st.subheader(f"Duplicates ({len(dup_groups)})")
            if not dup_groups:
                st.write("None found.")
            for group in dup_groups:
                with st.container(border=True):
                    for bid in group:
                        st.write(f"**{bid}.** {bullet_map.get(bid, bullet_map.get(str(bid), '?'))}")

        with col2:
            st.subheader(f"Contradictions ({len(contra_groups)})")
            if not contra_groups:
                st.write("None found.")
            for group in contra_groups:
                with st.container(border=True):
                    for bid in group:
                        st.write(f"**{bid}.** {bullet_map.get(bid, bullet_map.get(str(bid), '?'))}")


# ---------- TAB 2: How It Was Built (existing replay dashboard) ----------
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
    stages = [("SUPERVISOR", "supervisor_decision"), ("TASK AGENT", "task_agent_translation"),
              ("CODING AGENT", "aider_result"), ("TESTS + REAL CHECK", "aider_result")]
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


def render_iteration_card(rec, fallback_aider=None):
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
        st.code(stdout[:800] if stdout else "(no new code change this iteration)", language=None)

    has_run_data = bool(aider)
    source = aider if has_run_data else (fallback_aider or {})
    is_carried_over = not has_run_data and bool(fallback_aider)

    test_result = source.get("test_result", {})
    real_check = source.get("real_check", {})

    if is_carried_over:
        st.caption(f"No new code/test run this iteration — showing the evidence "
                   f"from iteration {source.get('iteration', '?')}, the last real "
                   f"attempt, which is what justified this decision.")

    tcols = st.columns(2)
    with tcols[0]:
        label = "PASS" if test_result.get("passed") else ("FAIL" if test_result else "N/A")
        st.markdown(f"**Mocked Tests:** {label}")
        if test_result:
            with st.expander("output"):
                st.code(test_result.get("output", "")[:1500], language=None)
    with tcols[1]:
        label = "PASS" if real_check.get("passed") else ("FAIL" if real_check else "N/A")
        st.markdown(f"**Real API Check:** {label}")
        if real_check:
            with st.expander("output"):
                st.code(real_check.get("output", "")[:1500], language=None)

    diff = source.get("diff", "")
    if diff:
        with st.expander("git diff"):
            st.code(diff[:2000], language="diff")
    st.divider()



def render_build_tab():
    st.header("How It Was Built")
    st.caption("Supervisor -> Task Agent -> Coding Agent -> Tests -> Supervisor")
    render_replay_tab()


def render_replay_tab():
    events = load_events(LOG_PATH)
    if not events:
        st.warning(f"No log data found at `{LOG_PATH}`.")
        return

    records, final_status = group_by_iteration(events)

    if records:
        idx = st.slider("Iteration", 1, len(records), len(records))
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
    st.metric("Iterations", len(records))

    last_real_aider = None
    for rec in visible:
        if rec.get("aider_result"):
            last_real_aider = rec["aider_result"]

    for rec in reversed(visible):
        render_iteration_card(rec, fallback_aider=last_real_aider if not rec.get("aider_result") else None)


def main():
    st.title("Duplicate / Contradiction Detector")
    tab1, tab2 = st.tabs(["How It Was Built", "Analyze a Document"])
    with tab1:
        render_build_tab()
    with tab2:
        render_analyze_tab()


if __name__ == "__main__":
    main()



