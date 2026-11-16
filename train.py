"""Fit on normal synthetic days; tune on validation, report once on test."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
import joblib
from sklearn.ensemble import IsolationForest
from sklearn.metrics import classification_report, confusion_matrix, f1_score
from engine import make_day, features, FEATURES

ROOT = Path(__file__).resolve().parent


def dataset(base, count, mixed):
    episodes = []
    for i in range(count):
        day = make_day(base + i, leak=mixed and i % 2 == 0)
        episodes.append((day, features(day)))
    return episodes


def evaluate(episodes, scores, threshold, baseline_minutes=None):
    ys, ps = [], []
    detected, leak_days, false_days, normal_days, delay = 0, 0, 0, 0, []
    for (day,x), score in zip(episodes,scores):
        pred = (x.continuous.to_numpy() >= baseline_minutes) if baseline_minutes else (
            (score >= threshold) & (x.continuous.to_numpy() >= 20))
        truth = day.truth.to_numpy()
        ys.extend(truth.tolist()); ps.extend(pred.astype(int).tolist())
        if truth.any():
            leak_days += 1
            hits = np.flatnonzero(pred & (truth == 1))
            if len(hits):
                detected += 1
                delay.append(int(hits[0] - np.flatnonzero(truth)[0]))
        else:
            normal_days += 1
            false_days += int(pred.any())
    return {'classification':classification_report(ys, ps, labels=[0,1],
                target_names=['normal','leak'], output_dict=True, zero_division=0),
            'confusion_matrix':confusion_matrix(ys, ps, labels=[0,1]).tolist(),
            'leak_days_detected':detected, 'leak_days':leak_days,
            'normal_days_alerted':false_days, 'normal_days':normal_days,
            'median_delay_minutes':float(np.median(delay)) if delay else None}


def main():
    training = dataset(1000,60,False)
    validation = dataset(2000,24,True)
    test = dataset(3000,24,True)
    x_train = pd.concat([x for _,x in training],ignore_index=True)
    model = IsolationForest(n_estimators=160, max_samples=512, random_state=42, n_jobs=1)
    model.fit(x_train.sample(n=40000,random_state=42))
    val_scores = [-model.score_samples(x) for _,x in validation]
    y_val = np.concatenate([d.truth.to_numpy() for d,_ in validation])
    durations = np.concatenate([x.continuous.to_numpy() for _,x in validation])
    joined = np.concatenate(val_scores)
    # Restrict to genuinely unusual scores relative to normal training data.
    # Otherwise F1 can choose a threshold below every score, reducing the
    # "AI" to the 20-minute persistence rule alone.
    minimum = float(np.quantile(-model.score_samples(x_train),0.95))
    candidates = np.linspace(minimum,0.8,61)
    best = max(candidates, key=lambda t:f1_score(y_val,(joined>=t)&(durations>=20),zero_division=0))
    test_scores = [-model.score_samples(x) for _,x in test]
    metrics = {'data_type':'SYNTHETIC ONLY', 'features':FEATURES,
        'training_days':60, 'validation_days':24,'test_days':24,
        'training_seed_range':[1000,1059], 'validation_seed_range':[2000,2023],
        'test_seed_range':[3000,3023], 'threshold':float(best),
        'selection':'Validation minute-level F1; score >= training 95th percentile; persistence >=20 minutes',
        'minimum_threshold':minimum,
        'hybrid':evaluate(test,test_scores,best),
        'baseline':evaluate(test,test_scores,best,baseline_minutes=60),
        'rule20':evaluate(test,test_scores,best,baseline_minutes=20)}
    artifacts = ROOT / 'artifacts'; artifacts.mkdir(exist_ok=True)
    joblib.dump({'model':model,'threshold':float(best)},artifacts/'water_model.joblib')
    (artifacts/'metrics.json').write_text(json.dumps(metrics,indent=2),encoding='utf-8')
    make_day(3000,True).to_csv(artifacts/'example_day.csv',index=False)
    print(json.dumps(metrics,indent=2))


if __name__ == '__main__':
    main()
