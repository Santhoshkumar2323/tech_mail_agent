"""
score_agent.py
Module 2 — The agentic scoring engine, built as a LangGraph.

Per item flow:
  1. initial_score   -> every candidate gets scored on title+abstract/description
  2. deep_dive        -> ONLY if score lands in the fuzzy band (config: fuzzy_band_low/high),
                          AND we're still under max_deep_dive_items_per_run for this run.
                          Re-scores with more context (fuller text / README).
  3. critique         -> runs right after deep_dive, sanity-checks the new score
                          against the rubric anchors, may nudge it slightly.

Once every item has a final score, approved items (>= min_passing_score) go
through a single run-once writer step that turns them into a narration script.

Every LLM call in this file counts against the Groq free-tier budget
(12k TPM / 30 RPM / 1000 RPD) — see rate_limiting section in config.yaml.
"""

import os
import time
from typing import TypedDict, Optional
from langchain_groq import ChatGroq
from langgraph.graph import StateGraph, END


RUBRIC_ANCHORS = """
Scoring rubric (0-10), anchored with worked examples:

- 9-10 (exceptional): Genuinely novel technique with clear real-world implementation
  path. Example: a new quantization method letting a 70B model run on 8GB VRAM with
  <2% accuracy loss, with code released.
- 7-8 (strong): Solid, useful contribution but incremental or narrow in scope.
  Example: a robotics paper improving grasp success rate by 12% on a known benchmark
  using an existing architecture with tuning changes.
- 5-6 (moderate): Interesting but limited practical value, purely theoretical,
  or narrow reproduction of known results.
- 0-4 (low): Minor variations, unclear contribution, or no real novelty/utility.

Judge on: novelty, real-world implementation value, and hardware/resource efficiency
where relevant. Be decisive — avoid clustering everything at 7.
"""


class ItemState(TypedDict):
    source: str
    id: str
    title: str
    text: str          # abstract or description used for scoring
    extra_context: str  # fuller text used only in deep_dive
    score: float
    reasoning: str
    went_deep_dive: bool


def build_llm(model_name: str, temperature: float) -> ChatGroq:
    return ChatGroq(
        model=model_name,
        temperature=temperature,
        groq_api_key=os.environ["GROQ_API_KEY"],
    )


def _parse_score(raw: str) -> tuple[float, str]:
    """
    Expects the model to respond in the form:
    SCORE: <number>
    REASON: <text>
    Falls back gracefully if the format isn't followed exactly.
    """
    score = 0.0
    reason = raw.strip()
    for line in raw.splitlines():
        if line.upper().startswith("SCORE:"):
            try:
                score = float(line.split(":", 1)[1].strip())
            except ValueError:
                pass
        if line.upper().startswith("REASON:"):
            reason = line.split(":", 1)[1].strip()
    return score, reason


def make_graph(llm: ChatGroq, fuzzy_low: float, fuzzy_high: float, deep_dive_budget: dict):
    """
    deep_dive_budget is a mutable dict like {"used": 0, "max": 35} shared across
    the whole run, so the graph can enforce the hard cap on deep-dive calls.
    """

    def initial_score(state: ItemState) -> ItemState:
        prompt = f"""{RUBRIC_ANCHORS}

Item title: {state['title']}
Item text: {state['text']}

Respond in exactly this format:
SCORE: <number 0-10>
REASON: <one sentence>"""
        response = llm.invoke(prompt)
        score, reason = _parse_score(response.content)
        state["score"] = score
        state["reasoning"] = reason
        state["went_deep_dive"] = False
        return state

    def route_after_initial(state: ItemState) -> str:
        in_fuzzy_band = fuzzy_low <= state["score"] <= fuzzy_high
        under_budget = deep_dive_budget["used"] < deep_dive_budget["max"]
        if in_fuzzy_band and under_budget:
            return "deep_dive"
        return "end"

    def deep_dive(state: ItemState) -> ItemState:
        deep_dive_budget["used"] += 1
        state["went_deep_dive"] = True

        prompt = f"""{RUBRIC_ANCHORS}

Item title: {state['title']}
Original text: {state['text']}
Additional context: {state['extra_context']}

This item scored in the borderline range on a first pass. Re-score it now
with this fuller context in mind.

Respond in exactly this format:
SCORE: <number 0-10>
REASON: <one sentence>"""
        response = llm.invoke(prompt)
        score, reason = _parse_score(response.content)
        state["score"] = score
        state["reasoning"] = reason
        return state

    def critique(state: ItemState) -> ItemState:
        prompt = f"""{RUBRIC_ANCHORS}

An item was scored {state['score']}/10 with this reasoning: "{state['reasoning']}"
Item title: {state['title']}

Does this score actually match the rubric anchors above? If it's off,
correct it. If it's right, keep it as is.

Respond in exactly this format:
SCORE: <number 0-10>
REASON: <one sentence>"""
        response = llm.invoke(prompt)
        score, reason = _parse_score(response.content)
        state["score"] = score
        state["reasoning"] = reason
        return state

    graph = StateGraph(ItemState)
    graph.add_node("initial_score", initial_score)
    graph.add_node("deep_dive", deep_dive)
    graph.add_node("critique", critique)

    graph.set_entry_point("initial_score")
    graph.add_conditional_edges(
        "initial_score",
        route_after_initial,
        {"deep_dive": "deep_dive", "end": END},
    )
    graph.add_edge("deep_dive", "critique")
    graph.add_edge("critique", END)

    return graph.compile()


def score_items(items: list[dict], config: dict) -> list[dict]:
    """
    Runs the scoring graph over every pre-filtered candidate.
    `items` need: source, id, title, text (abstract/description), extra_context.
    Returns items with `score` and `reasoning` attached, sorted highest first.
    """
    agent_cfg = config["agent"]
    llm = build_llm(agent_cfg["model_heavy"], agent_cfg["temperature"])

    deep_dive_budget = {"used": 0, "max": agent_cfg["max_deep_dive_items_per_run"]}
    graph = make_graph(llm, agent_cfg["fuzzy_band_low"], agent_cfg["fuzzy_band_high"], deep_dive_budget)

    results = []
    requests_made = 0
    rl = config["rate_limiting"]

    for item in items:
        state: ItemState = {
            "source": item["source"],
            "id": item["id"],
            "title": item["title"],
            "text": item.get("abstract", item.get("text", "")),
            "extra_context": item.get("extra_context", ""),
            "score": 0.0,
            "reasoning": "",
            "went_deep_dive": False,
        }

        final_state = graph.invoke(state)

        item["score"] = final_state["score"]
        item["reasoning"] = final_state["reasoning"]
        item["went_deep_dive"] = final_state["went_deep_dive"]
        results.append(item)

        # Requests per call: 1 (clear pass/fail) or 3 (deep-dive path)
        requests_made += 3 if final_state["went_deep_dive"] else 1

        # Respect RPM by pausing periodically — simple guard, not a full token-bucket
        if requests_made % rl["max_requests_per_minute"] == 0:
            time.sleep(rl["sleep_between_batches_seconds"])

    results.sort(key=lambda x: x["score"], reverse=True)
    return results


def write_narration_script(approved_items: list[dict], config: dict) -> str:
    """
    Module 2, Step 4 — runs ONCE per run, not per item. Takes the final
    approved list and writes a natural spoken narration script.
    """
    agent_cfg = config["agent"]
    llm = build_llm(agent_cfg["model_heavy"], 0.4)  # slightly higher temp for natural prose

    items_text = "\n\n".join(
        f"- [{item['source'].upper()}] {item['title']} (score {item['score']}/10): {item['reasoning']}"
        for item in approved_items
    )

    prompt = f"""You are writing a short spoken narration script for a tech briefing podcast.
Below is the final approved list of research papers and GitHub repos for this episode.
Write a natural-sounding script that groups related items, uses smooth transitions,
and briefly explains why each item matters. Keep it concise — this will be read aloud.
Do not include URLs or markdown, this is spoken text only.

Approved items:
{items_text}

Write the narration script now:"""

    response = llm.invoke(prompt)
    return response.content.strip()