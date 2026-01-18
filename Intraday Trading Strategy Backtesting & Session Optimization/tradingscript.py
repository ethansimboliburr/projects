import pandas as pd
from pathlib import Path

# =========================
# CONFIG
# =========================

DATA_DIR = Path(".")
TIMEZONE = "US/Eastern"

SESSION_START = 9.5
SESSION_END = 16.0

STRATEGIES = [
    ("15m", 15, 1, 2, 1, 1.0),
    ("15m", 15, 1, 2, 2, 1.5),
    ("30m", 30, 1, 2, 2, 1.0),
]

SWING_LOOKBACK = 2

# =========================
# DATA LOADING
# =========================

def load_data():
    dfs = []

    for f in DATA_DIR.glob("*.csv"):
        raw = pd.read_csv(f, sep=None, engine="python", on_bad_lines="skip")
        raw = raw.iloc[:, :7]
        raw.columns = ["timestamp", "type", "open", "high", "low", "close", "volume"]
        raw = raw[raw["type"] == 2]

        raw["time"] = pd.to_datetime(
            raw["timestamp"].astype(str),
            format="%Y%m%d%H%M%S",
            utc=True,
            errors="coerce"
        ).dt.tz_convert(TIMEZONE)

        dfs.append(raw[["time", "open", "high", "low", "close"]])

    return pd.concat(dfs).sort_values("time").reset_index(drop=True)

# =========================
# TIMEFRAME BUILDER
# =========================

def in_session(ts):
    h = ts.hour + ts.minute / 60
    return SESSION_START <= h < SESSION_END

def build_tf(df, minutes):
    out = (
        df.set_index("time")
        .resample(f"{minutes}min", label="right", closed="right")
        .agg(open=("open", "first"),
             high=("high", "max"),
             low=("low", "min"),
             close=("close", "last"))
        .dropna()
        .reset_index()
    )
    return out[out["time"].apply(in_session)]

# =========================
# SWING LOGIC
# =========================

def swing_low(lows, i):
    return all(lows[i] < lows[i - j] and lows[i] < lows[i + j]
               for j in range(1, SWING_LOOKBACK + 1))

def swing_high(highs, i):
    return all(highs[i] > highs[i - j] and highs[i] > highs[i + j]
               for j in range(1, SWING_LOOKBACK + 1))

# =========================
# STRATEGY ENGINE
# =========================

def run_strategy(df, struct_tf, exec_tf, R, stop_offset, be_trigger):
    struct = build_tf(df, struct_tf)
    exec_tf = build_tf(df, exec_tf)

    results = []

    for i in range(1, len(struct)):
        prev, cur = struct.iloc[i - 1], struct.iloc[i]

        # Breakout continuation
        if prev.close > prev.open and cur.close > cur.open and cur.close > prev.high:
            direction, level = "long", prev.high
        elif prev.close < prev.open and cur.close < cur.open and cur.close < prev.low:
            direction, level = "short", prev.low
        else:
            continue

        candles = exec_tf[exec_tf.time > cur.time]
        if len(candles) < SWING_LOOKBACK * 2:
            continue

        lows, highs, closes = candles.low.values, candles.high.values, candles.close.values

        entry = stop = target = None

        for idx in range(SWING_LOOKBACK, len(candles) - SWING_LOOKBACK):
            if direction == "long" and swing_low(lows, idx) and closes[idx] > level:
                entry = closes[idx]
                stop = lows[idx] - stop_offset
                risk = entry - stop
                target = entry + R * risk
                break

            if direction == "short" and swing_high(highs, idx) and closes[idx] < level:
                entry = closes[idx]
                stop = highs[idx] + stop_offset
                risk = stop - entry
                target = entry - R * risk
                break

        if not entry or risk <= 0:
            continue

        moved_to_be = False
        R_out = -1

        for _, c in candles.iterrows():
            if not moved_to_be:
                if direction == "long" and c.high >= entry + be_trigger * risk:
                    stop = entry
                    moved_to_be = True
                if direction == "short" and c.low <= entry - be_trigger * risk:
                    stop = entry
                    moved_to_be = True

            if direction == "long":
                if c.low <= stop:
                    break
                if c.high >= target:
                    R_out = R
                    break
            else:
                if c.high >= stop:
                    break
                if c.low <= target:
                    R_out = R
                    break

        results.append(R_out)

    return results

# =========================
# METRICS
# =========================

def summarize(trades):
    s = pd.Series(trades)
    return {
        "trades": len(s),
        "avg_R": s.mean(),
        "win_rate": (s > 0).mean(),
        "breakeven_rate": (s == 0).mean(),
        "loss_rate": (s < 0).mean(),
    }

# =========================
# MAIN
# =========================

if __name__ == "__main__":
    df = load_data()
    rows = []

    for name, s_tf, e_tf, R, stop, be in STRATEGIES:
        trades = run_strategy(df, s_tf, e_tf, R, stop, be)
        stats = summarize(trades)
        stats["strategy"] = f"{name}/{e_tf} | R={R} | Stop={stop} | BE={be}"
        rows.append(stats)

    out = pd.DataFrame(rows).sort_values("avg_R", ascending=False)
    out.to_csv("FINAL_ELITE_STRATEGIES.csv", index=False)

    print(out)
