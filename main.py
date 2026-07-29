import yaml
import state
import ingest_arxiv
import ingest_github
import score_agent
import audio_gen
import send_email


def load_config(path: str = "config.yaml") -> dict:
    with open(path, "r") as f:
        return yaml.safe_load(f)


def main():
    config = load_config()
    run_state = state.load_state(
        config["state"]["state_file"],
        config["ingestion"]["default_lookback_days"],
    )
    window_start = run_state["window_start"]
    window_end = run_state["window_end"]
    sent_ids = run_state["sent_ids"]

    print(f"[main] Window: {window_start} -> {window_end}")

    ing_cfg = config["ingestion"]
    pf_cfg = config["pre_filter"]

    papers = ingest_arxiv.fetch_all_arxiv(
        ing_cfg["arxiv_categories"], ing_cfg["arxiv_max_results_per_category"], window_start
    )
    papers = ingest_arxiv.dedup_against_sent(papers, sent_ids, state.make_item_id)
    papers = ingest_arxiv.apply_keyword_prefilter(
        papers, pf_cfg["priority_keywords"], pf_cfg["min_keyword_hits"], pf_cfg["max_candidates_to_score"]
    )

    repos = ingest_github.fetch_all_github(
        ing_cfg["github_topics"], ing_cfg["min_github_stars"], window_start, ing_cfg["max_repos_per_topic"]
    )
    repos = ingest_github.dedup_against_sent(repos, sent_ids, state.make_item_id)
    repos = ingest_github.apply_keyword_prefilter(
        repos, pf_cfg["priority_keywords"], pf_cfg["min_keyword_hits"], pf_cfg["max_candidates_to_score"]
    )

    candidates = papers + repos
    print(f"[main] {len(candidates)} candidates after ingestion + pre-filter")

    if not candidates:
        print("[main] No candidates this run. Exiting without sending.")
        state.save_state(config["state"]["state_file"], window_end, sent_ids)
        return

    for item in candidates:
        item.setdefault("extra_context", "")  

    scored = score_agent.score_items(candidates, config)

    min_score = config["agent"]["min_passing_score"]
    max_items = config["agent"]["max_total_report_items"]
    approved = [i for i in scored if i["score"] >= min_score][:max_items]

    print(f"[main] {len(approved)} items approved for this briefing")

    if not approved:
        print("[main] Nothing scored high enough this run. Exiting without sending.")
        state.save_state(config["state"]["state_file"], window_end, sent_ids)
        return

    narration_script = score_agent.write_narration_script(approved, config)

    audio_path = None
    if config["audio"]["enabled"]:
        audio_path = audio_gen.generate_narration_audio(
            narration_script, config["audio"]["voice_model"], config["audio"]["output_filename"]
        )

    html_body = send_email.build_html_report(approved)
    plain_body = send_email.build_plain_text_report(approved)
    recipients = send_email.get_recipients_from_env()

    if not recipients:
        print("[main] No recipients configured (RECIPIENT_LIST empty). Skipping send.")
    else:
        send_email.send_briefing(
            recipients=recipients,
            subject=config["delivery"]["email_subject"],
            sender_name=config["delivery"]["sender_name"],
            html_body=html_body,
            plain_body=plain_body,
            audio_path=audio_path,
            smtp_server=config["delivery"]["smtp_server"],
            smtp_port=config["delivery"]["smtp_port"],
        )

    for item in approved:
        sent_ids.add(state.make_item_id(item["source"], item["id"]))
    state.save_state(config["state"]["state_file"], window_end, sent_ids)
    print("[main] Run complete.")


if __name__ == "__main__":
    main()