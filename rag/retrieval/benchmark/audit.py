"""기존 실험의 BM25 산술·순위·지표를 독립 계산하고 전체 dev 복원을 감사한다."""
import gzip
import json
import math
from collections import Counter

import numpy as np
from rank_bm25 import BM25Okapi

from rag.config import read_jsonl
from rag.retrieval.indexing import KiwiTokenizer
from rag.retrieval.retrieval import DocRouter, read_csv_orgs
from rag.validation.evidence import normalize_evidence

from .common import OUT, RECORD, ROOT, no_network, offline_environment, save_json
from .prepare import freeze_inputs
from .run import prepare_sparse

def reference_scores(corpus, query):
    frequencies = [Counter(tokens) for tokens in corpus]
    document_frequency = Counter(term for counts in frequencies for term in counts)
    size = len(corpus)
    idfs = {term: math.log((size - count + 0.5) / (count + 0.5))
            for term, count in document_frequency.items()}
    average_idf = sum(idfs.values()) / len(idfs)
    average_length = sum(map(len, corpus)) / size
    terms = Counter(query)
    scores = []
    for counts, tokens in zip(frequencies, corpus):
        length = 1.5 * (0.25 + 0.75 * len(tokens) / average_length)
        score = 0.0
        for term, repetitions in terms.items():
            frequency = counts[term]
            if frequency:
                idf = idfs[term] if idfs[term] >= 0 else 0.25 * average_idf
                score += repetitions * idf * frequency * 2.5 / (frequency + length)
        scores.append(score)
    return np.array(scores)


def term_contributions(index, query, position):
    counts = index.doc_freqs[position]
    length = index.k1 * (1 - index.b + index.b * index.doc_len[position] / index.avgdl)
    return {term: repetitions * index.idf.get(term, 0) * counts[term] * (index.k1 + 1)
            / (counts[term] + length)
            for term, repetitions in Counter(query).items() if counts.get(term)}


def saved_method(sparse):
    path = ROOT / "artifacts/seven_model/record/results/kure" / f"isolated-{sparse}-0.0.jsonl.gz"
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        return {row["id"]: row for row in map(json.loads, stream)}


def query_diagnostics(row, chunks, index, query, tokenizer, route):
    allowed = np.array([route is None or chunk["doc_id"] in route for chunk in chunks])
    by_id = {chunk["chunk_id"]: i for i, chunk in enumerate(chunks)}
    content = row["question"].split(" 사업에서 ", 1)[1]
    variants = {"unique_query_tokens": list(dict.fromkeys(query)), "content_only_same_route": tokenizer(content)}
    results = {}
    for name, tokens in variants.items():
        scores = index.get_scores(tokens)
        ranks = {}
        for ref in row["evidence"]:
            position = by_id[ref["chunk_id"]]
            value = scores[position]
            ranks[ref["chunk_id"]] = {"best": int(np.sum(scores[allowed] > value)) + 1,
                                      "worst": int(np.sum(scores[allowed] >= value))}
        results[name] = {"query_tokens": tokens, "gold_rank_interval": ranks}
    return results


def check_saved_metrics(records, questions):
    checked = 0
    for qid, record in records.items():
        question = questions[qid]
        for level in ("doc", "chunk"):
            if record[f"{level}_label_state"] != "fully_labelled":
                assert all(value is None for key, value in record["scores"].items() if key.startswith(level + "_"))
                continue
            gold = {ref[f"{level}_id"] for ref in question["evidence"]}
            ranking = [candidate[f"{level}_id"] for candidate in record["ranked_candidates"]]
            for k in (5, 10, 20):
                recall = sum(value in set(ranking[:k]) for value in gold) / len(gold)
                hits = [i + 1 for i, value in enumerate(ranking[:k]) if value in gold]
                mrr = 1 / min(hits) if hits else 0.0
                assert record["scores"][f"{level}_fused_recall_at_{k}"] == recall
                assert record["scores"][f"{level}_mrr_at_{k}"] == mrr
                checked += 2
    return checked


def check_probe(qid, row, chunks, corpus, index, query, record, router, tokenizer):
    scores = index.get_scores(query)
    np.testing.assert_allclose(scores, reference_scores(corpus, query), rtol=1e-12, atol=1e-12)
    by_id = {chunk["chunk_id"]: i for i, chunk in enumerate(chunks)}
    routes = list(router.route(row["question"]).values()) or [None]
    assert len(routes) == 1, "These diagnostic probes use one fixed agency route"
    groups = [routed_candidates(scores, chunks, route) for route in routes]
    expected = [group[i] for i in range(max(map(len, groups))) for group in groups if i < len(group)]
    actual = [by_id[c["chunk_id"]] for c in record["ranked_candidates"]]
    assert Counter(expected) == Counter(actual)
    np.testing.assert_allclose(scores[expected], scores[actual], rtol=1e-12, atol=1e-12)
    for candidate in record["ranked_candidates"]:
        assert math.isclose(candidate["bm25_score"], scores[by_id[candidate["chunk_id"]]], rel_tol=1e-12)
    gold = {ref["chunk_id"] for ref in row["evidence"]}
    gold_rows = [{"chunk_id": cid, "rank": actual.index(by_id[cid]) + 1 if by_id[cid] in actual else None,
                  "terms": term_contributions(index, query, by_id[cid])} for cid in sorted(gold)]
    top = actual[0]
    return {"id": qid, "query_tokens": query, "gold": gold_rows,
            "equal_score_order_differences": sum(a != b for a, b in zip(expected, actual)),
            "diagnostic_only_query_changes": query_diagnostics(row, chunks, index, query, tokenizer, routes[0]),
            "top_chunk_id": chunks[top]["chunk_id"], "top_terms": term_contributions(index, query, top)}


def routed_candidates(scores, chunks, route):
    allowed = np.array([route is None or chunk["doc_id"] in route for chunk in chunks])
    masked = np.where(allowed, scores, 0.0)
    return [int(i) for i in np.argsort(-masked)[:50] if masked[i] > 0]


def grouping_audit(rows):
    split = json.loads((RECORD / "split.json").read_text(encoding="utf-8"))
    sides = {qid: name for name, ids in split["ids"].items() for qid in ids}
    seen = {}
    for row in rows:
        keys = [("question", normalize_evidence(row["question"])), ("bundle", row["bundle_id"])]
        for ref in row["evidence"]:
            keys += [("original_chunk", ref["doc_sha"], ref["golden_chunk_id"]),
                     ("source_span", ref["doc_sha"], ref["element_id"], json.dumps(ref["location"], sort_keys=True))]
            if ref["chunk_id"]:
                keys.append(("mapped_chunk", ref["doc_sha"], ref["chunk_id"]))
        for key in keys:
            seen.setdefault(key, set()).add(sides[row["id"]])
    shared = Counter(key[0] for key, partitions in seen.items() if len(partitions) > 1)
    assert not shared, dict(shared)
    return {"cross_partition_shared_groups": dict(shared), "group_count": len(split["group_sizes"]),
            "largest_group": max(split["group_sizes"]), "topic_counts": split["topic_counts"]}


def audit():
    offline_environment()
    with no_network() as attempts:
        probe_ids = json.loads((OUT / "audit_probes.json").read_text(encoding="utf-8"))
        manifest = freeze_inputs()
        prepare_sparse()
        rows = read_jsonl(RECORD / "questions.jsonl")
        grouping = grouping_audit(rows)
        questions = {row["id"]: row for row in rows}
        chunks = read_jsonl(OUT / "input/chunks.jsonl")
        kiwi = KiwiTokenizer()
        texts = [row["question"] for row in rows]
        assert kiwi.batch(texts) == [kiwi(text) for text in texts]
        tokens = json.loads((OUT / "kiwi_tokens.json").read_text(encoding="utf-8"))["tokens"]
        router = DocRouter(read_jsonl(OUT / "input/docs.jsonl"), read_csv_orgs(OUT / "input/orgs.csv"))
        probes, checked = [], 0
        for sparse in ("whitespace", "kiwi"):
            corpus = [chunk["text"].split() for chunk in chunks] if sparse == "whitespace" else tokens
            index = BM25Okapi(corpus, k1=1.5, b=0.75)
            records = saved_method(sparse)
            checked += check_saved_metrics({qid: row for qid, row in records.items() if qid in questions}, questions)
            for qid in probe_ids:
                query = questions[qid]["question"].split() if sparse == "whitespace" else kiwi(questions[qid]["question"])
                probes.append({"sparse": sparse, **check_probe(qid, questions[qid], chunks, corpus, index,
                                                             query, records[qid], router,
                                                             str.split if sparse == "whitespace" else kiwi)})
        assert not attempts
        save_json({"full_dev_questions": len(rows), "evidence_entries": sum(len(row["evidence"]) for row in rows),
                   "frozen_split_sha256": manifest["split_sha256"], "independent_metric_values_checked": checked,
                   "query_batch_single_consistency": len(rows), "bm25_arithmetic_and_saved_rank_probes": len(probes),
                   "grouping": grouping,
                   "network_attempts": attempts, "probes": probes,
                   "confirmed_defect": "Generation key_facts filtering omitted dev questions; removed in full-dev input",
                   "bm25_arithmetic_defect_found": False,
                   "interpretation": "Observed term splitting and repeated agency/project tokens change rankings; this is not proof of a Kiwi arithmetic defect or universal whitespace superiority"},
                  RECORD / "audit.json")
        evidence_count = sum(len(row["evidence"]) for row in rows)
        print(f"AUDIT PASSED: {len(rows)} dev questions, {evidence_count} evidence references, "
              f"{checked} independent metric values, {len(probes)} BM25 probes; zero network attempts", flush=True)


if __name__ == "__main__":
    audit()
