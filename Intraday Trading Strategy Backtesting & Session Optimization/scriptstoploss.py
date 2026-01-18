print("SCRIPT STARTED", flush=True)

import pandas as pd
from pathlib import Path

# =====================================================
# CONFIG
# =====================================================

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR
TIMEZONE = "US/Eastern"

# NY session
SESSION_START = 9.5
SESSION_END = 16.0

# What we are optimizing
LAST_ENTRY_TIMES = [14.0, 14.5, 15.0, 15.5, 16.0]

# Strategy universe
STRATEGIES = {
    "15m/1m": (15, 1),
    "30m/1m": (30, 1),
    "60m/1m": (60, 1),
}

R_MULTIPLES = [2]
STOP_OFFSETS = list(range(0, 11))
BE_TRIGGERS = [0.5, 1.0, 1.5]

# Risk / eval rules
MAX_TRADES_PER_DAY = 3
DAILY_LOSS_LIMIT = -1.0
DAILY_PROFIT_CAP = 2.0

SWING_LOOKBACK = 2
MIN_TRADES_REQUIRED = 250

# =====================================================
# DATA LOADER (FIXED)
# =====================================================

def load_markettick_folder():
    dfs = []

    for f in sorted(DATA_DIR.glob("*.csv")):
        try:
            raw = pd.read_csv(
                f,
                sep=None,               # auto-detect delimiter
                engine="python",
                encoding="latin1",
                on_bad_lines="skip"
            )
        except Exception as e:
            print(f"⚠️ Skipping {f.name}: {e}")
            continue

        if raw.shape[1] < 7:
            continue

        raw = raw.iloc[:, :7]
        raw.columns = ["timestamp", "type", "open", "high", "low", "close", "volume"]

        raw = raw[raw["type"] == 2]
        if raw.empty:
            continue

        raw["time"] = pd.to_datetime(
            raw["timestamp"].astype(str),
            format="%Y%m%d%H%M%S",
            utc=True,
            errors="coerce"
        )

        raw = raw.dropna(subset=["time"])
        raw["time"] = raw["time"].dt.tz_convert(TIMEZONE)

        dfs.append(raw[["time", "open", "high", "low", "close"]])

    if not dfs:
        raise RuntimeError("❌ No valid CSVs loaded")

    out = pd.concat(dfs).sort_values("time").reset_index(drop=True)
    print(f"✅ Loaded {len(out):,} bars from {len(dfs)} files")
    return out

# =====================================================
# TIME FILTERING
# =====================================================

def in_session(ts):
    h = ts.hour + ts.minute / 60
    return SESSION_START <= h < SESSION_END

def build_tf(df, minutes):
    out = (
        df.set_index("time")
        .resample(f"{minutes}min", label="right", closed="right")
        .agg(
            open=("open", "first"),
            high=("high", "max"),
            low=("low", "min"),
            close=("close", "last"),
        )
        .dropna()
        .reset_index()
    )

    out = out[out["time"].apply(in_session)]
    out["date"] = out["time"].dt.date
    return out

# =====================================================
# SWING LOGIC
# =====================================================

def is_swing_low(lows, i):
    return all(lows[i] < lows[i - j] and lows[i] < lows[i + j]
               for j in range(1, SWING_LOOKBACK + 1))

def is_swing_high(highs, i):
    return all(highs[i] > highs[i - j] and highs[i] > highs[i + j]
               for j in range(1, SWING_LOOKBACK + 1))

# =====================================================
# STRATEGY ENGINE
# =====================================================

def run_strategy(df, struct_tf, exec_tf, R, stop_offset, be_trigger, last_entry):

    struct = build_tf(df, struct_tf)
    exec_tf = build_tf(df, exec_tf)

    trades = []
    daily = {}

    for i in range(1, len(struct)):
        prev, cur = struct.iloc[i - 1], struct.iloc[i]
        day = cur.date

        h = cur.time.hour + cur.time.minute / 60
        if h > last_entry:
            continue

        daily.setdefault(day, {"pnl": 0.0, "trades": 0})
        d = daily[day]

        if (
            d["pnl"] <= DAILY_LOSS_LIMIT or
            d["pnl"] >= DAILY_PROFIT_CAP or
            d["trades"] >= MAX_TRADES_PER_DAY
        ):
            continue

        # Simple continuation entry
        if prev.close > prev.open and cur.close > cur.open and cur.close > prev.high:
            direction, level = "long", prev.high
        elif prev.close < prev.open and cur.close < cur.open and cur.close < prev.low:
            direction, level = "short", prev.low
        else:
            continue

        candles = exec_tf[(exec_tf.time > cur.time) & (exec_tf.date == day)]
        if len(candles) < SWING_LOOKBACK * 2 + 1:
            continue

        lows, highs, closes = candles.low.values, candles.high.values, candles.close.values
        swing_points = []
        entry = stop = risk = target = None

        for idx in range(SWING_LOOKBACK, len(candles) - SWING_LOOKBACK):
            if direction == "long" and is_swing_low(lows, idx):
                swing_points.append(lows[idx])
            if direction == "short" and is_swing_high(highs, idx):
                swing_points.append(highs[idx])

            if swing_points:
                if direction == "long" and closes[idx] > level:
                    entry = closes[idx]
                    stop = swing_points[-1] - stop_offset
                    risk = entry - stop
                    target = entry + R * risk
                    break
                if direction == "short" and closes[idx] < level:
                    entry = closes[idx]
                    stop = swing_points[-1] + stop_offset
                    risk = stop - entry
                    target = entry - R * risk
                    break

        if entry is None or risk <= 0:
            continue

        moved_to_be = False
        R_result = 0.0

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
                    R_result = R
                    break
            else:
                if c.high >= stop:
                    break
                if c.low <= target:
                    R_result = R
                    break

        trades.append(R_result)
        d["pnl"] += R_result
        d["trades"] += 1

    return trades

# =====================================================
# METRICS
# =====================================================

def summarize(trades):
    s = pd.Series(trades)
    return {
        "trades": len(s),
        "avg_R": s.mean(),
        "win_rate": (s > 0).mean(),
        "breakeven_rate": (s == 0).mean(),
        "loss_rate": (s < 0).mean(),
    }

# =====================================================
# MAIN — ANSWERS THE QUESTION
# =====================================================

if __name__ == "__main__":

    df = load_markettick_folder()
    results = []

    for cutoff in LAST_ENTRY_TIMES:
        all_trades = []

        for _, (s_tf, e_tf) in STRATEGIES.items():
            for R in R_MULTIPLES:
                for stop in STOP_OFFSETS:
                    for be in BE_TRIGGERS:
                        all_trades += run_strategy(
                            df, s_tf, e_tf, R, stop, be, cutoff
                        )

        stats = summarize(all_trades)
        stats["last_entry_time"] = cutoff
        results.append(stats)

    out = pd.DataFrame(results)
    out = out[out["trades"] >= MIN_TRADES_REQUIRED]
    out = out.sort_values("avg_R", ascending=False)

    out.to_csv("BEST_LAST_ENTRY_TIME.csv", index=False)

    print("\n✅ FINAL ANSWER — WHEN TO STOP TRADING")
    print(out)
