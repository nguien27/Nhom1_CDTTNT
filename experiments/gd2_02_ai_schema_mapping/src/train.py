"""Huấn luyện TF-IDF Character N-gram + Logistic Regression."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.pipeline import Pipeline

from .preprocessing import preprocess, preprocess_no_accent

RANDOM_STATE = 42
INITIAL_CONFIDENCE_THRESHOLD = 0.70
VALID_LABELS = (
    "MA_NHAN_VIEN",
    "HO_TEN",
    "TEN_DON_VI",
    "LOAI_DON_VI",
    "OTHER",
)

EXPERIMENT_DIR = Path(__file__).resolve().parents[1]
DATA_PATH = EXPERIMENT_DIR / "data" / "schema_mapping_dataset.csv"
MODEL_DIR = EXPERIMENT_DIR / "models" / "schema_mapping"
MODEL_PATH = MODEL_DIR / "schema_mapping_model.joblib"
METADATA_PATH = MODEL_DIR / "metadata.json"


def load_dataset(path: str | Path = DATA_PATH) -> pd.DataFrame:
    df = pd.read_csv(path, encoding="utf-8")
    if not {"text", "label"}.issubset(df.columns):
        raise ValueError("Dataset phải có cột text,label")

    df = df[["text", "label"]].dropna().copy()
    df["text"] = df["text"].astype(str).str.strip()
    df["label"] = df["label"].astype(str).str.strip()

    invalid = sorted(set(df["label"]) - set(VALID_LABELS))
    if invalid:
        raise ValueError(f"Dataset chứa label không hợp lệ: {invalid}")
    if df["text"].str.contains("�", regex=False).any():
        raise ValueError("Dataset có ký tự Unicode replacement (�)")

    df["processed"] = df["text"].map(preprocess_no_accent)
    df["group_key"] = df["processed"]
    df = df[(df["processed"] != "") & (df["group_key"] != "")].copy()

    # Nếu cùng một dạng chuẩn hóa bị gán cho nhiều class thì dataset mâu thuẫn.
    conflicts = df.groupby("group_key")["label"].nunique()
    bad_groups = conflicts[conflicts > 1]
    if not bad_groups.empty:
        raise ValueError(f"Dataset có group xung đột label: {bad_groups.index.tolist()}")

    # Bỏ duplicate y hệt; các biến thể khác raw text vẫn được giữ để model học.
    df = df.drop_duplicates(subset=["text", "label"]).reset_index(drop=True)
    return df


def build_pipeline() -> Pipeline:
    return Pipeline([
        ("tfidf", TfidfVectorizer(
            analyzer="char_wb",
            ngram_range=(2, 5),
            max_features=12000,
            sublinear_tf=True,
            lowercase=False,  # đã lowercase ở preprocessing
            min_df=1,
        )),
        ("clf", LogisticRegression(
            class_weight="balanced",
            C=4.0,
            max_iter=3000,
            random_state=RANDOM_STATE,
        )),
    ])


def split_grouped(df: pd.DataFrame, n_splits: int = 5, random_state: int = RANDOM_STATE):
    """Split stratified theo group_key để biến thể có/không dấu không lọt qua train-test."""
    splitter = StratifiedGroupKFold(n_splits=n_splits, shuffle=True, random_state=random_state)
    X = df["processed"].to_numpy()
    y = df["label"].to_numpy()
    groups = df["group_key"].to_numpy()
    train_idx, test_idx = next(splitter.split(X, y, groups))
    return df.iloc[train_idx].reset_index(drop=True), df.iloc[test_idx].reset_index(drop=True)


def tinh_metrics(y_true, y_pred, labels=None) -> dict:
    labels = list(labels or VALID_LABELS)
    report = classification_report(
        y_true, y_pred, labels=labels, zero_division=0, output_dict=True
    )
    cm = confusion_matrix(y_true, y_pred, labels=labels)
    return {
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "precision_macro": float(precision_score(y_true, y_pred, average="macro", zero_division=0)),
        "recall_macro": float(recall_score(y_true, y_pred, average="macro", zero_division=0)),
        "macro_f1": float(f1_score(y_true, y_pred, average="macro", zero_division=0)),
        "precision_weighted": float(precision_score(y_true, y_pred, average="weighted", zero_division=0)),
        "recall_weighted": float(recall_score(y_true, y_pred, average="weighted", zero_division=0)),
        "weighted_f1": float(f1_score(y_true, y_pred, average="weighted", zero_division=0)),
        "classification_report": report,
        "confusion_matrix": cm.tolist(),
        "labels": labels,
    }


def tune_threshold(model: Pipeline, df_val: pd.DataFrame) -> tuple[float, list[dict]]:
    """Tune threshold trên validation, không dùng test set."""
    probs = model.predict_proba(df_val["processed"])
    pred_idx = probs.argmax(axis=1)
    pred = model.classes_[pred_idx]
    conf = probs[np.arange(len(probs)), pred_idx]
    y = df_val["label"].to_numpy()

    candidates = np.round(np.arange(0.30, 0.86, 0.05), 2)
    rows = []
    for threshold in candidates:
        accepted = conf >= threshold
        coverage = float(accepted.mean())
        accepted_accuracy = float((pred[accepted] == y[accepted]).mean()) if accepted.any() else 0.0
        rows.append({
            "threshold": float(threshold),
            "coverage": round(coverage, 4),
            "accepted_accuracy": round(accepted_accuracy, 4),
            "accepted_count": int(accepted.sum()),
        })

    # Ưu tiên >=98% accuracy trên mẫu được chấp nhận và coverage cao nhất.
    feasible = [r for r in rows if r["accepted_count"] > 0 and r["accepted_accuracy"] >= 0.98]
    if feasible:
        best = max(feasible, key=lambda r: (r["coverage"], r["accepted_accuracy"], -r["threshold"]))
    else:
        best = max(rows, key=lambda r: (0.7 * r["accepted_accuracy"] + 0.3 * r["coverage"], r["coverage"]))
    return float(best["threshold"]), rows


def train_and_evaluate(save: bool = True) -> dict:
    df = load_dataset()
    df_train, df_test = split_grouped(df, n_splits=5, random_state=RANDOM_STATE)
    df_fit, df_val = split_grouped(df_train, n_splits=4, random_state=RANDOM_STATE + 1)

    # Threshold chỉ được tune trên validation.
    threshold_model = build_pipeline()
    threshold_model.fit(df_fit["processed"], df_fit["label"])
    threshold, threshold_table = tune_threshold(threshold_model, df_val)

    # Metric cuối trên test chưa hề dùng để tune.
    eval_model = build_pipeline()
    eval_model.fit(df_train["processed"], df_train["label"])
    y_pred = eval_model.predict(df_test["processed"])
    metrics = tinh_metrics(df_test["label"], y_pred)

    test_probs = eval_model.predict_proba(df_test["processed"])
    test_conf = test_probs.max(axis=1)
    confidence_summary = {
        "min": round(float(np.min(test_conf)), 4),
        "median": round(float(np.median(test_conf)), 4),
        "mean": round(float(np.mean(test_conf)), 4),
        "max": round(float(np.max(test_conf)), 4),
        "accepted_at_threshold": int((test_conf >= threshold).sum()),
        "test_size": int(len(df_test)),
    }

    # Production model tận dụng toàn bộ dataset sau khi đã chốt metric/threshold.
    production_model = build_pipeline()
    production_model.fit(df["processed"], df["label"])

    metadata = {
        "model": "TF-IDF char_wb(2,5) + LogisticRegression",
        "model_params": {"C": 4.0, "class_weight": "balanced", "max_iter": 3000},
        "tfidf_params": {"analyzer": "char_wb", "ngram_range": [2, 5], "max_features": 12000},
        "classes": list(VALID_LABELS),
        "train_date": datetime.now().isoformat(timespec="seconds"),
        "dataset_size": int(len(df)),
        "train_size": int(len(df_train)),
        "test_size": int(len(df_test)),
        "initial_threshold": INITIAL_CONFIDENCE_THRESHOLD,
        "threshold": threshold,
        "threshold_source": "validation_set",
        "confidence_test": confidence_summary,
        "metrics_test": {
            k: round(v, 4) if isinstance(v, float) else v
            for k, v in metrics.items()
            if k not in {"classification_report", "confusion_matrix", "labels"}
        },
        "classification_report_test": metrics["classification_report"],
        "confusion_matrix_test": metrics["confusion_matrix"],
        "labels_confusion_matrix": metrics["labels"],
        "threshold_tuning": threshold_table,
        "split": "StratifiedGroupKFold; group_key=preprocess_no_accent(text)",
        "version": "2.0",
    }

    if save:
        MODEL_DIR.mkdir(parents=True, exist_ok=True)
        joblib.dump(production_model, MODEL_PATH)
        METADATA_PATH.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=" * 72)
    print(f"Dataset       : {len(df)}")
    print(f"Train/Test    : {len(df_train)}/{len(df_test)}")
    print(f"Threshold     : {threshold:.2f} (tuned trên validation)")
    print(f"Accuracy      : {metrics['accuracy']:.4f}")
    print(f"Precision M   : {metrics['precision_macro']:.4f}")
    print(f"Recall M      : {metrics['recall_macro']:.4f}")
    print(f"Macro F1      : {metrics['macro_f1']:.4f}")
    print(f"Weighted F1   : {metrics['weighted_f1']:.4f}")
    print("Confusion Matrix:")
    print(np.array(metrics["confusion_matrix"]))
    print("=" * 72)

    return {
        "pipeline": production_model,
        "evaluation_model": eval_model,
        "threshold": threshold,
        "metadata": metadata,
        "metrics": metrics,
        "train_df": df_train,
        "test_df": df_test,
    }


if __name__ == "__main__":
    train_and_evaluate(save=True)
