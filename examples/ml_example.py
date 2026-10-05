"""Machine learning in a few lines, and an honest look at what it found.

    python examples/ml_example.py

Predict each stock's return over the next 20 days from where its close stands against its moving averages.
Train on 2010-2022, test on 2023 onwards.
"""

from sklearn.ensemble import HistGradientBoostingRegressor

from osloquant.ml import MaStockMLMachine

codes = ["EQNR", "DNB", "MOWI", "TEL", "NHY", "ORK", "YAR", "KOG", "STB", "SUBC", "TOM", "SALM"]

machine = MaStockMLMachine(codes=codes, start_timestamp="2010-01-01", predict_start_timestamp="2023-01-01", predict_steps=20)
print(f"{len(machine.training_X):,} training rows, {len(machine.testing_X):,} test rows, features {machine.feature_names}")

for name, model in (("linear regression", None), ("gradient boosting", HistGradientBoostingRegressor(max_depth=3, max_iter=100))):
    machine.train(model=model)
    machine.predict()
    result = machine.evaluate()
    print(
        f"{name:18} rank IC {result['rank_ic']:+.3f}   hit rate {result['hit_rate']:.1%}   "
        f"R2 against predicting the training average {result['r2_vs_naive']:+.3f}"
    )

# machine.draw_result(code="EQNR", show=True) plots predicted against realised returns for one stock
