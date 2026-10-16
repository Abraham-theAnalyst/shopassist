"""Check retrieval and answer quality against quality/questions.json.

Usage:
    python -m app.cli.quality retrieval
        Embeds every question in one request and reports where the expected
        document ranks, with scores, plus a suggested RAG_MIN_SIMILARITY.
    python -m app.cli.quality answers --ids delivery-abuja,laptops
        Gets real replies for the chosen questions and checks the required
        facts. Uses 1 embedding request plus 1 reply request per question,
        so run it rarely.
"""

import argparse
import json
import logging
import math
import sys
from pathlib import Path

from app.core.config import settings
from app.db.session import SessionLocal
from app.services.ai import EMBEDDING_BATCH_SIZE, AIServiceError, embed_texts, generate_reply
from app.services.prompts import build_system_prompt
from app.services.retrieval import (
    always_included_chunks,
    build_search_text,
    relevant_chunks,
    search_by_vector,
)

QUESTIONS_FILE = Path("quality/questions.json")


def load_questions(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))["questions"]


def search_text_for(q: dict) -> str:
    return build_search_text([q["previous"], q["question"]] if q.get("previous") else [q["question"]])


def check_reply(reply: str, q: dict) -> list[str]:
    """Problems with the reply; an empty list means it passed."""
    text = reply.lower().replace("’", "'")
    problems = []
    for options in q.get("must_contain", []):
        if not any(option.lower() in text for option in options):
            problems.append("missing " + " / ".join(repr(o) for o in options))
    for banned in q.get("must_not_contain", []):
        if banned.lower() in text:
            problems.append(f"contains {banned!r}")
    return problems


def run_retrieval_check(questions: list[dict]) -> int:
    vectors = embed_texts([search_text_for(q) for q in questions], "query")
    requests = math.ceil(len(questions) / EMBEDDING_BATCH_SIZE)
    top_k, threshold = settings.rag_top_k, settings.rag_min_similarity

    relevant_scores, uncovered_scores, misses = [], [], 0
    with SessionLocal() as db:
        for q, vector in zip(questions, vectors):
            ranked = search_by_vector(db, vector, limit=None)
            top = ranked[:top_k]
            expected = q["expected_document"]
            print(f"\n[{q['id']}] {q['question']}")
            if expected:
                ranks = [i for i, c in enumerate(ranked, 1) if c.source == expected]
                best_expected = ranked[ranks[0] - 1].similarity
                best_other = max((c.similarity for c in ranked if c.source != expected), default=0.0)
                found = ranks[0] <= top_k
                misses += not found
                relevant_scores.append(best_expected)
                print(
                    f"  {'OK  ' if found else 'MISS'} expected {expected}: rank {ranks[0]}, "
                    f"best score {best_expected:.3f} (best other document {best_other:.3f})"
                )
            else:
                uncovered_scores.append(top[0].similarity)
                print(f"  (not covered) best score {top[0].similarity:.3f}")
            for c in top:
                mark = "*" if c.similarity >= threshold else " "
                print(f"   {mark} {c.similarity:.3f}  {c.label}")

    covered = len(relevant_scores)
    print(f"\nExpected document in the top {top_k}: {covered - misses}/{covered} covered questions")
    print(f"(* = at or above the current RAG_MIN_SIMILARITY={threshold:.2f})")
    lowest_relevant = min(relevant_scores)
    highest_uncovered = max(uncovered_scores, default=0.0)
    print(f"Lowest best score of an expected document: {lowest_relevant:.3f}")
    print(f"Highest best score of an uncovered question: {highest_uncovered:.3f}")
    if lowest_relevant > highest_uncovered:
        suggestion = math.floor((lowest_relevant + highest_uncovered) / 2 * 100) / 100
        print(f"Suggested RAG_MIN_SIMILARITY: {suggestion:.2f} (midway between the two)")
    else:
        print("No threshold separates them: some uncovered question scores as high as a relevant one.")
    print(f"\nReal requests used: {requests}")
    return 0 if misses == 0 else 1


def run_answer_check(questions: list[dict]) -> int:
    vectors = embed_texts([search_text_for(q) for q in questions], "query")
    requests = math.ceil(len(questions) / EMBEDDING_BATCH_SIZE)
    failures = 0
    with SessionLocal() as db:
        for q, vector in zip(questions, vectors):
            chunks = relevant_chunks(db, vector)
            chunks += always_included_chunks(db, exclude=chunks)
            history = []
            if q.get("previous"):
                history += [
                    {"role": "user", "content": q["previous"]},
                    {"role": "assistant", "content": q["previous_answer"]},
                ]
            history.append({"role": "user", "content": q["question"]})

            print(f"\n[{q['id']}] {q['question']}")
            for c in chunks:
                score = f"{c.similarity:.3f}" if c.similarity is not None else "always"
                print(f"   {score:>6}  {c.label}")
            requests += 1
            try:
                reply = generate_reply(build_system_prompt(chunks), history)
            except AIServiceError:
                failures += 1
                print("  FAIL: the AI did not reply")
                continue
            problems = check_reply(reply, q)
            failures += bool(problems)
            print("  Reply: " + reply.replace("\n", "\n         "))
            print("  PASS" if not problems else "  FAIL: " + "; ".join(problems))

    print(f"\n{len(questions) - failures}/{len(questions)} passed. Real requests used: {requests}")
    return 0 if failures == 0 else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Knowledge base quality checks.")
    parser.add_argument("mode", choices=["retrieval", "answers"])
    parser.add_argument("--ids", help="Comma separated question ids (answers mode: required)")
    parser.add_argument("--file", type=Path, default=QUESTIONS_FILE)
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")

    questions = load_questions(args.file)
    if args.ids:
        wanted = [i.strip() for i in args.ids.split(",")]
        by_id = {q["id"]: q for q in questions}
        unknown = [i for i in wanted if i not in by_id]
        if unknown:
            print(f"Unknown question ids: {', '.join(unknown)}", file=sys.stderr)
            return 2
        questions = [by_id[i] for i in wanted]
    elif args.mode == "answers":
        print("answers mode needs --ids, to keep real requests low", file=sys.stderr)
        return 2

    try:
        if args.mode == "retrieval":
            return run_retrieval_check(questions)
        return run_answer_check(questions)
    except AIServiceError:
        print("The embedding request failed; nothing was checked.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
