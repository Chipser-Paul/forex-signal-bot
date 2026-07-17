"""Deep analysis of 59-trade wider-SL+trailing backtest results."""
import csv, statistics
from collections import defaultdict
from datetime import datetime

trades = []
with open('backtests/shadow_mode_wider_sl_v2/shadow_mode_trades.csv') as f:
    reader = csv.DictReader(f)
    for row in reader:
        row['pnl'] = float(row['pnl'])
        row['entry_price'] = float(row['entry_price'])
        row['exit_price'] = float(row['exit_price'])
        row['sl'] = float(row['sl'])
        row['risk_price'] = float(row['risk_price'])
        row['score'] = int(row['score'])
        row['lot'] = float(row['lot'])
        trades.append(row)

wins = [t for t in trades if t['pnl'] > 0]
losses = [t for t in trades if t['pnl'] < 0]

# === SL DISTRIBUTION ===
print('=== SL DISTRIBUTION ===')
sls = [abs(t['entry_price'] - t['sl']) for t in trades]
print(f'  Mean SL distance: {statistics.mean(sls):.2f} pts')
print(f'  Median SL distance: {statistics.median(sls):.2f} pts')
print(f'  Min SL distance: {min(sls):.2f} pts')
print(f'  Max SL distance: {max(sls):.2f} pts')
print(f'  StdDev: {statistics.stdev(sls):.2f} pts')

for lo, hi in [(0,10),(10,12),(12,14),(14,16),(16,18),(18,20),(20,999)]:
    in_range = [t for t in trades if lo <= abs(t['entry_price'] - t['sl']) < hi]
    if in_range:
        w = [t for t in in_range if t['pnl'] > 0]
        print(f'  SL [{lo:>2}-{hi:>3}): {len(in_range):>2} trades, {len(w)/len(in_range)*100:>5.1f}% WR, PnL ${sum(t["pnl"] for t in in_range):>7.2f}')

# === TRADE DURATION ===
print()
print('=== TRADE DURATION ===')
for t in trades:
    opened = datetime.fromisoformat(t['opened_at'])
    closed = datetime.fromisoformat(t['closed_at'])
    t['duration_min'] = (closed - opened).total_seconds() / 60

durations = [t['duration_min'] for t in trades]
print(f'  Mean duration: {statistics.mean(durations):.1f} min')
print(f'  Median duration: {statistics.median(durations):.1f} min')
print(f'  Min: {min(durations):.1f} min')
print(f'  Max: {max(durations):.1f} min')

for label, lo, hi in [('0-15 min',0,15),('15-30 min',15,30),('30-60 min',30,60),('1-2 hr',60,120),('2-4 hr',120,240),('4+ hr',240,9999)]:
    in_range = [t for t in trades if lo <= t['duration_min'] < hi]
    if in_range:
        w = [t for t in in_range if t['pnl'] > 0]
        print(f'  {label:>12}: {len(in_range):>2} trades, {len(w)/len(in_range)*100:>5.1f}% WR, PnL ${sum(t["pnl"] for t in in_range):>7.2f}')

# === ENTRY HOUR (UTC) ===
print()
print('=== ENTRY HOUR (UTC) ===')
hours = defaultdict(list)
for t in trades:
    h = datetime.fromisoformat(t['opened_at']).hour
    hours[h].append(t['pnl'])
for h in sorted(hours.keys()):
    h_trades = hours[h]
    h_wins = [x for x in h_trades if x > 0]
    wr = len(h_wins)/len(h_trades)*100 if h_trades else 0
    print(f'  {h:02d}:00: {len(h_trades):>2} trades, {wr:>5.1f}% WR, PnL ${sum(h_trades):>7.2f}')

# === WIN SIZE DISTRIBUTION ===
print()
print('=== WIN SIZE DISTRIBUTION ===')
win_sizes = sorted([t['pnl'] for t in wins])
print(f'  Smallest win: ${win_sizes[0]:.2f}')
print(f'  25th percentile: ${win_sizes[len(win_sizes)//4]:.2f}')
print(f'  Median win: ${win_sizes[len(win_sizes)//2]:.2f}')
print(f'  75th percentile: ${win_sizes[3*len(win_sizes)//4]:.2f}')
print(f'  Largest win: ${win_sizes[-1]:.2f}')
small_wins = [t for t in wins if t['pnl'] < 5]
print(f'  Wins under $5: {len(small_wins)}/{len(wins)} ({len(small_wins)/len(wins)*100:.1f}%)')
tiny_wins = [t for t in wins if t['pnl'] < 3]
print(f'  Wins under $3: {len(tiny_wins)}/{len(wins)} ({len(tiny_wins)/len(wins)*100:.1f}%)')

# === ENTRY→EXIT DISTANCE ===
print()
print('=== ENTRY TO EXIT DISTANCE (pts) ===')
win_dists = [abs(t['entry_price'] - t['exit_price']) for t in wins]
loss_dists = [abs(t['entry_price'] - t['exit_price']) for t in losses]
print(f'  Wins: mean {statistics.mean(win_dists):.2f}, median {statistics.median(win_dists):.2f}')
print(f'  Losses: mean {statistics.mean(loss_dists):.2f}, median {statistics.median(loss_dists):.2f}')
print(f'  Win/Loss distance ratio: {statistics.mean(win_dists)/statistics.mean(loss_dists):.2f}')

# ORIGINAL SL DISTANCE (using risk_price)
print()
print('=== ORIGINAL SL DISTANCE (risk_price) ===')
orig_sls = [t['risk_price'] for t in trades]
print(f'  Mean: {statistics.mean(orig_sls):.2f} pts')
print(f'  Median: {statistics.median(orig_sls):.2f} pts')
print(f'  Min: {min(orig_sls):.2f} pts')
print(f'  Max: {max(orig_sls):.2f} pts')
for lo, hi in [(0,10),(10,12),(12,14),(14,16),(16,18),(18,20),(20,25),(25,999)]:
    in_range = [t for t in trades if lo <= t['risk_price'] < hi]
    if in_range:
        w = [t for t in in_range if t['pnl'] > 0]
        print(f'  Orig SL [{lo:>2}-{hi:>3}): {len(in_range):>2} trades, {len(w)/len(in_range)*100:>5.1f}% WR, PnL ${sum(t["pnl"] for t in in_range):>7.2f}')

# TRAILING EFFECTIVENESS
print()
print('=== TRAILING EFFECTIVENESS ===')
trailed_wins = [t for t in wins if t['exit_price'] != t['sl']]
# Actually all trades exit at sl, so check if trailing moved SL beyond original risk
trailed_profit_lock = [t for t in wins if abs(t['entry_price'] - t['exit_price']) > t['risk_price']]
untouched_sl = [t for t in losses if abs(t['entry_price'] - t['exit_price']) >= t['risk_price'] * 0.95]
print(f'  Wins where trailing locked >original risk: {len(trailed_profit_lock)}/{len(wins)} ({len(trailed_profit_lock)/len(wins)*100:.1f}%)')
print(f'  Losses that hit near-original SL: {len(untouched_sl)}/{len(losses)} ({len(untouched_sl)/len(losses)*100:.1f}%)')
for t in wins:
    gain = abs(t['entry_price'] - t['exit_price'])
    risk = t['risk_price']
    if gain <= risk * 1.1:
        t['trailing_efficiency'] = 'tight'
    elif gain <= risk * 2:
        t['trailing_efficiency'] = 'moderate'
    else:
        t['trailing_efficiency'] = 'wide'
eff = defaultdict(list)
for t in wins:
    eff[t.get('trailing_efficiency', 'unknown')].append(t['pnl'])
for e in ['tight','moderate','wide']:
    if e in eff:
        print(f'  Trailing {e}: {len(eff[e])} wins, PnL ${sum(eff[e]):.2f}')

# === REALIZED RR ===
print()
print('=== REALIZED RISK:REWARD ===')
win_rr = [abs(t['entry_price'] - t['exit_price'])/t['risk_price'] for t in wins if t['risk_price'] > 0]
loss_rr = [abs(t['entry_price'] - t['exit_price'])/t['risk_price'] for t in losses if t['risk_price'] > 0]
print(f'  Wins: avg {statistics.mean(win_rr):.2f}, median {statistics.median(win_rr):.2f}')
print(f'  Losses: avg {statistics.mean(loss_rr):.2f}, median {statistics.median(loss_rr):.2f}')

# === WEEK DAY ===
print()
print('=== WEEK DAY ===')
days = defaultdict(list)
for t in trades:
    d = datetime.fromisoformat(t['opened_at']).weekday()
    days[d].append(t['pnl'])
day_names = ['Mon','Tue','Wed','Thu','Fri','Sat','Sun']
for d in sorted(days.keys()):
    d_trades = days[d]
    d_wins = [x for x in d_trades if x > 0]
    wr = len(d_wins)/len(d_trades)*100 if d_trades else 0
    print(f'  {day_names[d]}: {len(d_trades)} trades, {wr:.1f}% WR, PnL ${sum(d_trades):.2f}')

# === RE-ENTRY CASCADES (same-direction streaks) ===
print()
print('=== RE-ENTRY CASCADE ANALYSIS ===')
streaks = []
cur_dir = None
cur_pnls = []
for t in trades:
    if t['direction'] == cur_dir:
        cur_pnls.append(t['pnl'])
    else:
        if len(cur_pnls) >= 2:
            streaks.append((cur_dir, cur_pnls))
        cur_dir = t['direction']
        cur_pnls = [t['pnl']]
if len(cur_pnls) >= 2:
    streaks.append((cur_dir, cur_pnls))

total_cascade_losses = sum(1 for _, pnls in streaks for p in pnls if p < 0)
total_cascade_damage = sum(p for _, pnls in streaks for p in pnls if p < 0)
total_cascade_wins = sum(1 for _, pnls in streaks for p in pnls if p > 0)
total_cascade_profit = sum(p for _, pnls in streaks for p in pnls if p > 0)
print(f'  Streaks (2+ same dir): {len(streaks)}')
print(f'  Total cascade trades: {sum(len(p) for _, p in streaks)}')
print(f'  Cascade wins: {total_cascade_wins}, losses: {total_cascade_losses}')
print(f'  Cascade PnL: ${total_cascade_profit+total_cascade_damage:.2f} ({total_cascade_wins}W/${total_cascade_profit:.2f} + {total_cascade_losses}L/${total_cascade_damage:.2f})')

for i, (dir, pnls) in enumerate(streaks):
    w = sum(1 for p in pnls if p > 0)
    l = sum(1 for p in pnls if p < 0)
    print(f'  Streak {i+1}: {dir.upper()} x{len(pnls)} ({w}W/{l}L), PnL ${sum(pnls):.2f}')

# === ENTRY PRICE RELATIVE TO SL ===
print()
print('=== SL REASON BREAKDOWN ===')
reasons = defaultdict(list)
for t in trades:
    reasons[t['sl_reason']].append(t['pnl'])
for r in sorted(reasons.keys()):
    r_trades = reasons[r]
    r_wins = [x for x in r_trades if x > 0]
    wr = len(r_wins)/len(r_trades)*100
    print(f'  {r}: {len(r_trades)} trades, {wr:.1f}% WR, PnL ${sum(r_trades):.2f}')

# === 0.02 LOT vs 0.01 LOT DEEP DIVE ===
print()
print('=== LOT SIZE DEEP DIVE ===')
for lot in [0.01, 0.02, 0.03]:
    lot_trades = [t for t in trades if t['lot'] == lot]
    if not lot_trades:
        continue
    lot_wins = [t for t in lot_trades if t['pnl'] > 0]
    wr = len(lot_wins)/len(lot_trades)*100
    print(f'  0.{int(lot*100):02d} lot: {len(lot_trades)} trades')
    print(f'    WR: {wr:.1f}%, PnL: ${sum(t["pnl"] for t in lot_trades):.2f}')
    # avg score
    avg_score = statistics.mean(t['score'] for t in lot_trades)
    print(f'    Avg score: {avg_score:.1f}')
    # avg SL distance
    avg_sl = statistics.mean(abs(t['entry_price'] - t['sl']) for t in lot_trades)
    print(f'    Avg SL dist: {avg_sl:.2f} pts')
    # avg duration
    avg_dur = statistics.mean(t['duration_min'] for t in lot_trades)
    print(f'    Avg duration: {avg_dur:.1f} min')
