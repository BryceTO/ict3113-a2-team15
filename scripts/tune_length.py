
import pandas as pd
from pathlib import Path

from tune_cascade import (
    load_tuning_set,
    load_predictions,
    LLAMA_FILE,
    GEMMA_FILE,
    TUNING_FILE,
    CATEGORIES,
    OUT_DIR,
)


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    tuning = load_tuning_set()

    narratives = pd.read_csv(TUNING_FILE)

    if narratives["NARRATIVE"].isna().any():
        raise ValueError("Missing tuning narratives")

    narratives["narrative_chars"] = (
        narratives["NARRATIVE"].astype(str).str.len()
    )

    lengths = narratives[["ROW", "narrative_chars"]]
    lengths = lengths.rename(columns={"ROW": "row"})

    llama = load_predictions(LLAMA_FILE, "llama", tuning)
    gemma = load_predictions(GEMMA_FILE, "gemma", tuning)

    df = tuning.merge(llama, on="row", validate="one_to_one")
    df = df.merge(gemma, on="row", validate="one_to_one")
    df = df.merge(lengths, on="row", validate="one_to_one")

    total = len(df)

    print("=== LENGTH TUNING: ODD ROWS ONLY ===")
    print(f"Tickets: {total}")

    print("\n=== Narrative length distribution ===")
    print(df["narrative_chars"].describe().to_string())

    print("\n=== Accuracy by narrative length ===")

    df["length_group"] = pd.qcut(
        df["narrative_chars"],
        q=4,
        duplicates="drop"
    )

    groups = []

    for group, rows in df.groupby(
        "length_group", observed=True
    ):
        count = len(rows)

        groups.append({
            "length_group": str(group),
            "tickets": count,
            "llama_correct": int(rows["llama_correct"].sum()),
            "llama_accuracy_percent":
                rows["llama_correct"].mean() * 100,
            "gemma_correct": int(rows["gemma_correct"].sum()),
            "gemma_accuracy_percent":
                rows["gemma_correct"].mean() * 100,
        })

    group_df = pd.DataFrame(groups)

    print(group_df.round(2).to_string(index=False))

    group_df.to_csv(
        OUT_DIR / "length_reliability.csv",
        index=False
    )

    thresholds = sorted(
        set([0] + df["narrative_chars"].tolist())
    )

    results = []

    for threshold in thresholds:

        accepted = (
            df["llama_http_ok"]
            & df["llama_prediction"].isin(CATEGORIES)
            & df["narrative_chars"].le(threshold)
        )

        escalated = df["llama_http_ok"] & ~accepted
        unknown = ~df["llama_http_ok"]

        final_correct = (
            (accepted & df["llama_correct"])
            | (escalated & df["gemma_correct"])
        )

        accepted_count = int(accepted.sum())
        escalated_count = int(escalated.sum())
        decided = accepted_count + escalated_count
        correct = int(final_correct.sum())

        result = {
            "threshold_chars": threshold,
            "accepted": accepted_count,
            "accepted_wrong": int(
                (accepted & ~df["llama_correct"]).sum()
            ),
            "escalated": escalated_count,
            "routing_unknown": int(unknown.sum()),
            "escalation_percent": (
                escalated_count / decided * 100
                if decided else None
            ),
            "correct": correct,
            "accuracy_percent": correct / total * 100,
        }

        for category in CATEGORIES:

            mask = df["golden_label"].eq(category)

            result[f"accuracy_{category}"] = (
                (mask & final_correct).sum()
                / mask.sum() * 100
                if mask.sum() else None
            )

        results.append(result)

    result_df = pd.DataFrame(results)

    result_df = result_df.sort_values(
        ["accuracy_percent", "escalation_percent"],
        ascending=[False, True]
    )

    result_df.to_csv(
        OUT_DIR / "length_settings.csv",
        index=False
    )

    print("\n=== Top 15 simulated length settings ===")

    columns = [
        "threshold_chars",
        "accepted",
        "accepted_wrong",
        "escalated",
        "routing_unknown",
        "escalation_percent",
        "correct",
        "accuracy_percent",
    ]

    print(
        result_df[columns]
        .head(15)
        .round(2)
        .to_string(index=False)
    )

    print("\n=== Lowest escalation settings by accuracy band ===")

    # Tuning diagnostics only, not official A2 floors.
    gemma_accuracy = df["gemma_correct"].mean() * 100

    for loss in [0, 5, 10, 15]:

        target = gemma_accuracy - loss

        candidates = result_df[
            result_df["accuracy_percent"].ge(target)
        ]

        print(f"\nAllowed tuning accuracy loss: {loss} pp")

        if candidates.empty:
            print("No matching settings")
            continue

        best = candidates.sort_values(
            ["escalation_percent", "accuracy_percent"],
            ascending=[True, False]
        ).head(1)

        print(
            best[columns].round(2).to_string(index=False)
        )

    print(f"\nResults saved to: {OUT_DIR}")
    print("No even-row test predictions were evaluated.")


if __name__ == "__main__":
    main()
