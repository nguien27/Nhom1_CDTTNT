"""Đánh giá lại đúng holdout test; không predict trên toàn dataset bằng production model."""
from __future__ import annotations

import numpy as np

from .train import RANDOM_STATE, build_pipeline, load_dataset, split_grouped, tinh_metrics


def evaluate_model() -> dict:
    df = load_dataset()
    df_train, df_test = split_grouped(df, n_splits=5, random_state=RANDOM_STATE)
    model = build_pipeline()
    model.fit(df_train["processed"], df_train["label"])
    y_pred = model.predict(df_test["processed"])
    metrics = tinh_metrics(df_test["label"], y_pred)

    print(f"Accuracy           : {metrics['accuracy']:.4f}")
    print(f"Precision macro    : {metrics['precision_macro']:.4f}")
    print(f"Recall macro       : {metrics['recall_macro']:.4f}")
    print(f"Macro F1           : {metrics['macro_f1']:.4f}")
    print(f"Precision weighted : {metrics['precision_weighted']:.4f}")
    print(f"Recall weighted    : {metrics['recall_weighted']:.4f}")
    print(f"Weighted F1        : {metrics['weighted_f1']:.4f}")
    print("Confusion Matrix:")
    print(np.array(metrics["confusion_matrix"]))
    return metrics


if __name__ == "__main__":
    evaluate_model()
