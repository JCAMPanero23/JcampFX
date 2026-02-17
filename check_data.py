import pandas as pd
from pathlib import Path

data_dir = Path("data/ticks")
files = sorted(data_dir.glob("*.parquet"))

if not files:
    print("No tick files found in data/ticks/")
else:
    for f in files:
        df = pd.read_parquet(f)
        if df.empty:
            print(f"{f.stem}: EMPTY")
        else:
            t_min = df["time"].min()
            t_max = df["time"].max()
            print(f"{f.stem}: {len(df):,} ticks | {t_min.date()} -> {t_max.date()}")
