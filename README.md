

# Autonomous Document Comparison

An autonomous chat-to-code supervision system that builds and verifies its own deliverable: a tool that reads numbered bulleted statements (e.g. from a procurement document) and identifies **duplicates** (same meaning, different wording) and **contradictions** (same subject, conflicting values) - with zero manual code editing.

A persistent **Supervisor** ("Chat") observes real evidence from a **Coding Agent** ("Code") after every attempt and decides whether to fix, continue, or finish - the exact loop a human normally runs by hand, fully automated.

Streamlit link: https://autonomous-dev-agent-ac3rfenbwzigr9cbxw57rc.streamlit.app/#autonomous-dev-agent-live-dashboard

| Agent | Role |
|---|---|
| **Supervisor** | Persistent overseer. Holds the original goal across the whole run. Reviews real diffs, test output, and a live API check after every attempt, and decides `CONTINUE` / `FIX` / `DONE`. Never writes code itself. |
| **Task Agent** | Translates the Supervisor's single focus into one precise, narrowly-scoped instruction — exact endpoint, exact request shape, one atomic change at a time. |
| **Coding Agent** | Executes with real tools: `list_files`, `read_file`, `write_file`, `run_tests`, `git_diff`. Inspects before acting, iterates on failures — not a one-shot file generator. |
| **Verification gate** | An actual (non-mocked) call to the Groq API, run by the orchestrator itself, independent of the Coding Agent's self-report. `DONE` is only honored when both mocked tests and this real check genuinely pass. |

This is the automated version of manually relaying messages between a chat model and a coding agent (e.g. Claude Chat + Claude Code) — the same pattern, with the human relay replaced by the orchestrator loop.


## Setup

```bash
python -m venv venv
venv\Scripts\activate        # Windows
pip install -r requirements.txt
pip install groq python-dotenv requests pytest
```

Create a `.env` file in the project root:

```
GROQ_API_KEY=your_groq_api_key_here
```

## Running the Autonomous Build

```bash
python orchestrator.py
```

Watch it work: the Supervisor names one focus, the Task Agent translates it precisely, the Coding Agent inspects/writes/tests, and the Supervisor reviews real evidence — including a genuine live Groq API call — before ever declaring `DONE`. Every step is logged to `logs/run_001.jsonl`.

## Running the Built Tool

Once `workspace/detector.py` exists (either from a build run or already committed):

```bash
python run_detector.py
```

Runs the tool against `fixtures/sample_procurement.txt` using a real Groq API call and prints the duplicate/contradiction groups found.


   ```

## Results

Verified against a real 15-bullet test document via a genuine Groq API call:

| Type | Bullets | Basis |
|---|---|---|
| Duplicate | 1, 3, 11 | Same rate for Material A, stated three ways |
| Duplicate | 2, 7, 14 | Same transport-cost clause, stated three ways |
| Duplicate | 4, 9 | Same 30-day payment term |
| Duplicate | 6, 10 | Same chemistry-compliance clause |
| Contradiction | 1, 5 | Rs. 50/kg vs. Rs. 80/kg |
| Contradiction | 8, 12 | 15 vs. 25 working days delivery |
| Contradiction | 4, 15 | 30 vs. 45 days payment term |

**9 of 9 planted relationships correctly identified, 0 false positives, on the final verified build.**

