"""M8 -- fine-tune a hosted model on the LOVA corpus (OpenAI-style API).

    python experiments/m8_finetune.py --estimate                 # tokens and cost, no call
    python experiments/m8_finetune.py --submit --base gpt-4o-mini-2024-07-18
    python experiments/m8_finetune.py --status ftjob-...

The corpus is ``corpus/finetune/chat_train.jsonl`` and ``chat_val.jsonl``
(``python -m corpus.finetune`` makes them; the ``chat_card_*`` files
carry the language card in every example and cost ten times more to
train on -- use them only to compare).  ``--estimate`` counts the
training tokens with tiktoken when it is installed and with a
four-characters-a-token rule when it is not, and prints the cost at the
price given by ``--price`` (dollars per million training tokens; the
default is gpt-4o-mini's at the time of writing).  Nothing is sent.

``--submit`` uploads both files and creates the job; it prints the job
id and the command that polls it.  ``--status`` polls, and when the
job has finished prints the fine-tuned model id to pass to
``experiments/experiment_17_llm_benchmark.py --model``.

The decision M8 exists to make: does the fine-tuned model's LOVA
pass@1 on LOVABench v3 exceed its own Python pass@1, and its base
model's LOVA pass@1?  Exp 17 measures; this script only trains.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CORPUS = ROOT / "corpus" / "finetune"


def _count_tokens(path: Path) -> int:
    text = path.read_text(encoding="utf-8")
    try:
        import tiktoken
        enc = tiktoken.get_encoding("cl100k_base")
        return sum(len(enc.encode(json.loads(line)["messages"][i]["content"]))
                   for line in text.splitlines() if line.strip()
                   for i in range(3))
    except ImportError:
        return sum(len(m["content"]) // 4
                   for line in text.splitlines() if line.strip()
                   for m in json.loads(line)["messages"])


def estimate(price_per_million: float, epochs: int) -> int:
    for name in ("chat_train.jsonl", "chat_val.jsonl"):
        path = CORPUS / name
        if not path.exists():
            print(f"missing {path}; run `python -m corpus.finetune` first")
            return 1
        lines = sum(1 for l in path.read_text(encoding="utf-8").splitlines() if l.strip())
        tokens = _count_tokens(path)
        print(f"{name}: {lines} examples, ~{tokens:,} tokens")
        if name == "chat_train.jsonl":
            total = tokens * epochs
            print(f"  x {epochs} epochs = ~{total:,} training tokens, "
                  f"~${total / 1e6 * price_per_million:.2f} at ${price_per_million}/M")
    return 0


def submit(base: str, epochs: int, suffix: str) -> int:
    from openai import OpenAI
    client = OpenAI()
    ids = {}
    for name in ("chat_train.jsonl", "chat_val.jsonl"):
        with (CORPUS / name).open("rb") as handle:
            uploaded = client.files.create(file=handle, purpose="fine-tune")
        ids[name] = uploaded.id
        print(f"uploaded {name} -> {uploaded.id}")
    job = client.fine_tuning.jobs.create(
        training_file=ids["chat_train.jsonl"],
        validation_file=ids["chat_val.jsonl"],
        model=base, suffix=suffix,
        hyperparameters={"n_epochs": epochs},
    )
    print(f"job {job.id} created on {base}; poll with:\n"
          f"  python experiments/m8_finetune.py --status {job.id}")
    return 0


def status(job_id: str, wait: bool) -> int:
    from openai import OpenAI
    client = OpenAI()
    while True:
        job = client.fine_tuning.jobs.retrieve(job_id)
        print(f"{job.id}: {job.status}", end="")
        if job.status == "succeeded":
            print(f"\nfine-tuned model: {job.fine_tuned_model}\n"
                  f"  python experiments/experiment_17_llm_benchmark.py --model {job.fine_tuned_model}")
            return 0
        if job.status in ("failed", "cancelled"):
            print(f"\n{job.error}")
            return 1
        if not wait:
            print()
            return 0
        print(" ... waiting", flush=True)
        time.sleep(60)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--estimate", action="store_true")
    ap.add_argument("--submit", action="store_true")
    ap.add_argument("--status", metavar="JOB_ID")
    ap.add_argument("--wait", action="store_true", help="with --status: poll until done")
    ap.add_argument("--base", default="gpt-4o-mini-2024-07-18")
    ap.add_argument("--epochs", type=int, default=3)
    ap.add_argument("--suffix", default="lova")
    ap.add_argument("--price", type=float, default=3.0, help="dollars per million training tokens")
    args = ap.parse_args(argv)
    if args.estimate:
        return estimate(args.price, args.epochs)
    if args.submit:
        return submit(args.base, args.epochs, args.suffix)
    if args.status:
        return status(args.status, args.wait)
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
