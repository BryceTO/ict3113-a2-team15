
import pandas as pd
from pathlib import Path
from itertools import combinations

TUNING_FILE = Path("golden_set/a2/tuning (odd).csv")

LLAMA_FILE = Path(
    "results/accuracy/llama3.2_1b_predictions.csv"
)

GEMMA_FILE = Path(
    "results/accuracy/gemma3_4b_predictions.csv"
)

OUT_DIR = Path("results/a2/tuning")

CATEGORIES = [
    "credit reporting",
    "debt collection",
    "mortgage",
    "credit card",
    "bank account or service",
    "consumer loan",
    "money transfer or service",
]


def normalize(series):
    return series.fillna("").astype(str).str.strip().str.lower()


def load_tuning_set():
    df = pd.read_csv(TUNING_FILE)

    required = {"ROW", "NARRATIVE", "GOLDEN_LABEL"}

    if not required.issubset(df.columns):
        raise ValueError("Missing tuning-set columns")

    if len(df) != 87:
        raise ValueError("Expected 87 tuning tickets")

    if df["ROW"].duplicated().any():
        raise ValueError("Duplicate tuning row IDs")

    if (df["ROW"] % 2 == 0).any():
        raise ValueError("Even rows found in tuning set")

    df = df[["ROW", "GOLDEN_LABEL"]].copy()
    df.columns = ["row", "golden_label"]

    df["golden_label"] = normalize(df["golden_label"])

    if not df["golden_label"].isin(CATEGORIES).all():
        raise ValueError("Invalid golden label")

    return df.sort_values("row")


def load_predictions(path, prefix, tuning):
    df = pd.read_csv(path)

    # Keep only tuning rows before analysing predictions.
    df = df[df["row"].isin(tuning["row"])].copy()

    if df["row"].duplicated().any():
        raise ValueError(f"Duplicate tuning predictions: {path}")

    if set(df["row"]) != set(tuning["row"]):
        raise ValueError(f"Missing tuning predictions: {path}")

    df["golden_label"] = normalize(df["golden_label"])
    df["predicted_label"] = normalize(df["predicted_label"])

    labels = tuning.set_index("row")["golden_label"]

    if not df["golden_label"].eq(df["row"].map(labels)).all():
        raise ValueError(f"Golden label mismatch: {path}")

    valid = (
        df["http_status"].eq(200)
        & df["predicted_label"].isin(CATEGORIES)
    )

    df[f"{prefix}_prediction"] = df["predicted_label"].where(
        valid, "unclassified"
    )

    df[f"{prefix}_http_ok"] = df["http_status"].eq(200)

    df[f"{prefix}_correct"] = (
        valid
        & df["predicted_label"].eq(df["golden_label"])
    )

    return df[
        [
            "row",
            f"{prefix}_prediction",
            f"{prefix}_correct",
            f"{prefix}_http_ok",
        ]
    ]


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    tuning = load_tuning_set()

    llama = load_predictions(
        LLAMA_FILE, "llama", tuning
    )

    gemma = load_predictions(
        GEMMA_FILE, "gemma", tuning
    )

    df = tuning.merge(llama, on="row", validate="one_to_one")
    df = df.merge(gemma, on="row", validate="one_to_one")

    total = len(df)

    print("=== TUNING SET ONLY ===")
    print(f"Tickets: {total}")

    print("\n=== Single-model tuning accuracy ===")

    for model in ["llama", "gemma"]:
        correct = int(df[f"{model}_correct"].sum())
        print(
            f"{model}: {correct}/{total} "
            f"({correct / total * 100:.2f}%)"
        )

    # Reliability based on Llama's predicted category.
    reliability = []

    for category in CATEGORIES:
        predicted = df[df["llama_prediction"] == category]

        count = len(predicted)
        correct = int(predicted["llama_correct"].sum())

        reliability.append({
            "predicted_category": category,
            "predictions": count,
            "correct": correct,
            "wrong": count - correct,
            "reliability_percent": (
                correct / count * 100 if count else None
            ),
        })

    reliability_df = pd.DataFrame(reliability)

    reliability_df = reliability_df.sort_values(
        "reliability_percent", ascending=False
    )

    print("\n=== Llama predicted-category reliability ===")
    print(reliability_df.to_string(index=False))

    reliability_df.to_csv(
        OUT_DIR / "category_reliability.csv",
        index=False
    )

    # Simulate category-based cascade settings.
    settings = []

    for size in range(len(CATEGORIES) + 1):
        for accepted_categories in combinations(CATEGORIES, size):

            accepted = (
                df["llama_http_ok"]
                & df["llama_prediction"].isin(accepted_categories)
            )

            escalated = df["llama_http_ok"] & ~accepted
            unknown = ~df["llama_http_ok"]

            final_correct = (
                (accepted & df["llama_correct"])
                | (escalated & df["gemma_correct"])
            )

            accepted_count = int(accepted.sum())
            escalated_count = int(escalated.sum())
            unknown_count = int(unknown.sum())
            decided_count = accepted_count + escalated_count

            correct_count = int(final_correct.sum())

            result = {
                "accepted_categories": ";".join(
                    accepted_categories
                ),
                "accepted": accepted_count,
                "accepted_wrong": int(
                    (accepted & ~df["llama_correct"]).sum()
                ),
                "escalated": escalated_count,
                "routing_unknown": unknown_count,
                "escalation_percent": (
                    escalated_count / decided_count * 100
                    if decided_count else None
                ),
                "correct": correct_count,
                "accuracy_percent": (
                    correct_count / total * 100
                ),
            }

            for category in CATEGORIES:
                mask = df["golden_label"].eq(category)

                category_correct = int(
                    (mask & final_correct).sum()
                )

                result[f"accuracy_{category}"] = (
                    category_correct / mask.sum() * 100
                    if mask.sum() else None
                )

            settings.append(result)

    settings_df = pd.DataFrame(settings)

    settings_df = settings_df.sort_values(
        ["accuracy_percent", "escalation_percent"],
        ascending=[False, True]
    )

    settings_df.to_csv(
        OUT_DIR / "cascade_settings.csv",
        index=False
    )

    df.to_csv(
        OUT_DIR / "tuning_predictions.csv",
        index=False
    )

    print("\n=== Top 15 simulated cascade settings ===")

    columns = [
        "accepted_categories",
        "accepted",
        "accepted_wrong",
        "escalated",
        "routing_unknown",
        "escalation_percent",
        "correct",
        "accuracy_percent",
    ]

    print(
        settings_df[columns].head(15).to_string(index=False)
    )

    print(f"\nSettings evaluated: {len(settings_df)}")
    print(f"Results saved to: {OUT_DIR}")
    print("No even-row test predictions were evaluated.")


if __name__ == "__main__":
    main()
