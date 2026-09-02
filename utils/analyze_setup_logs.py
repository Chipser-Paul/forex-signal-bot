"""
Setup Log Analysis Tool for Phase 3
Analyzes logged setup evaluations to build win-rate-by-score tables and statistics.
"""

import json
import pandas as pd
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from typing import Any, Dict, List
import sys


SETUP_LOG_DIR = Path("logs/setup_evaluations")


def load_trade_results(trades_path: str | None = None) -> Dict[str, Dict[str, Any]]:
    """
    Load trade results from CSV file and map by setup_id.
    
    Args:
        trades_path: Path to trades CSV file. If None, looks for default backtest output.
    
    Returns:
        Dict mapping setup_id to trade outcome data.
    """
    if trades_path is None:
        # Try to find the most recent trades file
        backtest_dir = Path("backtests")
        if not backtest_dir.exists():
            print("Backtest directory not found")
            return {}
        
        # Find most recent shadow_mode_trades.csv
        trades_files = list(backtest_dir.rglob("shadow_mode_trades.csv"))
        if not trades_files:
            print("No trades CSV files found")
            return {}
        
        trades_path = max(trades_files, key=lambda p: p.stat().st_mtime)
        print(f"Loading trades from: {trades_path}")
    
    try:
        df = pd.read_csv(trades_path)
    except Exception as e:
        print(f"Error loading trades CSV: {e}")
        return {}
    
    # Map setup_id to trade outcome
    trade_map = {}
    for _, row in df.iterrows():
        setup_id = row.get("setup_id")
        if setup_id and pd.notna(setup_id):
            trade_map[str(setup_id)] = {
                "pnl": float(row.get("pnl", 0)),
                "won": float(row.get("pnl", 0)) > 0,
                "score": int(row.get("score", 0)) if pd.notna(row.get("score")) else None,
                "grade": str(row.get("grade", "")) if pd.notna(row.get("grade")) else "",
                "reason": str(row.get("reason", "")),
            }
    
    print(f"Loaded {len(trade_map)} trade results")
    return trade_map


def load_setup_logs(date_str: str | None = None) -> List[Dict[str, Any]]:
    """
    Load setup logs from JSONL files.
    
    Args:
        date_str: Optional specific date (YYYY-MM-DD). If None, loads all available.
    
    Returns:
        List of setup log entries.
    """
    logs = []
    
    def parse_line(line: str) -> List[Dict[str, Any]]:
        """Parse a line that may contain multiple JSON objects."""
        entries = []
        line = line.strip()
        if not line:
            return entries
        
        # Try to parse as single JSON first
        try:
            entries.append(json.loads(line))
            return entries
        except json.JSONDecodeError:
            pass
        
        # If that fails, try to split by whitespace and parse each
        # This handles malformed JSONL where objects are concatenated
        parts = line.split()
        for part in parts:
            try:
                entries.append(json.loads(part))
            except json.JSONDecodeError:
                continue
        
        return entries
    
    if date_str:
        log_file = SETUP_LOG_DIR / f"setups_{date_str}.jsonl"
        if not log_file.exists():
            print(f"Log file not found: {log_file}")
            return logs
        
        with open(log_file, "r", encoding="utf-8") as f:
            for line in f:
                logs.extend(parse_line(line))
    else:
        # Load all available log files
        if not SETUP_LOG_DIR.exists():
            print(f"Setup log directory not found: {SETUP_LOG_DIR}")
            return logs
        
        for log_file in sorted(SETUP_LOG_DIR.glob("setups_*.jsonl")):
            print(f"Loading {log_file.name}...")
            with open(log_file, "r", encoding="utf-8") as f:
                for line in f:
                    logs.extend(parse_line(line))
    
    print(f"Loaded {len(logs)} setup evaluations")
    return logs


def build_win_rate_by_score(logs: List[Dict[str, Any]], trade_map: Dict[str, Dict[str, Any]]) -> Dict[int, Dict[str, Any]]:
    """
    Build win-rate-by-score table from logged setups, linking to trade outcomes.
    
    Args:
        logs: List of setup log entries
        trade_map: Dict mapping setup_id to trade outcome data
    
    Returns:
        Dict mapping score to statistics (wins, losses, win_rate, expectancy).
    """
    score_stats = defaultdict(lambda: {"wins": 0, "losses": 0, "rejected": 0, "total_evaluations": 0, "pnl": 0.0})
    
    for entry in logs:
        score = entry.get("gate_results", {}).get("gate_11_confluence_score", {}).get("raw", {}).get("score", 0)
        outcome = entry.get("outcome")
        outcome_detail = entry.get("outcome_detail")
        setup_id = entry.get("setup_id")
        
        score_stats[score]["total_evaluations"] += 1
        
        # Link to trade outcome if available
        if setup_id and setup_id in trade_map:
            trade_data = trade_map[setup_id]
            if trade_data.get("won"):
                score_stats[score]["wins"] += 1
            else:
                score_stats[score]["losses"] += 1
            score_stats[score]["pnl"] += trade_data.get("pnl", 0)
        elif outcome == "rejected":
            score_stats[score]["rejected"] += 1
    
    # Calculate win rates and expectancy
    results = {}
    for score, stats in score_stats.items():
        total_trades = stats["wins"] + stats["losses"]
        win_rate = (stats["wins"] / total_trades * 100) if total_trades > 0 else 0.0
        avg_pnl = (stats["pnl"] / total_trades) if total_trades > 0 else 0.0
        
        results[score] = {
            "score": score,
            "total_evaluations": stats["total_evaluations"],
            "trades_taken": total_trades,
            "rejected": stats["rejected"],
            "wins": stats["wins"],
            "losses": stats["losses"],
            "win_rate_pct": round(win_rate, 2),
            "total_pnl": round(stats["pnl"], 2),
            "avg_pnl_per_trade": round(avg_pnl, 2),
        }
    
    return dict(sorted(results.items()))


def build_rejection_reason_stats(logs: List[Dict[str, Any]]) -> Dict[str, int]:
    """
    Build statistics on rejection reasons.
    
    Returns:
        Dict mapping rejection reason to count.
    """
    rejection_stats = defaultdict(int)
    
    for entry in logs:
        if entry.get("outcome") == "rejected":
            reason = entry.get("outcome_detail", "unknown")
            rejection_stats[reason] += 1
    
    return dict(sorted(rejection_stats.items(), key=lambda x: x[1], reverse=True))


def build_gate_pass_rates(logs: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """
    Build pass/fail statistics for each gate.
    
    Returns:
        Dict mapping gate name to pass/fail counts and pass rate.
    """
    gate_stats = defaultdict(lambda: {"pass": 0, "fail": 0, "total": 0})
    
    for entry in logs:
        gate_results = entry.get("gate_results", {})
        for gate_name, gate_data in gate_results.items():
            if isinstance(gate_data, dict) and "pass" in gate_data:
                gate_stats[gate_name]["total"] += 1
                if gate_data["pass"]:
                    gate_stats[gate_name]["pass"] += 1
                else:
                    gate_stats[gate_name]["fail"] += 1
    
    # Calculate pass rates
    results = {}
    for gate_name, stats in gate_stats.items():
        pass_rate = (stats["pass"] / stats["total"] * 100) if stats["total"] > 0 else 0.0
        results[gate_name] = {
            "gate": gate_name,
            "total_evaluations": stats["total"],
            "passed": stats["pass"],
            "failed": stats["fail"],
            "pass_rate_pct": round(pass_rate, 2),
        }
    
    return dict(sorted(results.items(), key=lambda x: x[0]))


def print_win_rate_table(win_rate_data: Dict[int, Dict[str, Any]]):
    """Print win-rate-by-score table in a readable format."""
    print("\n" + "=" * 100)
    print("WIN-RATE BY SCORE TABLE")
    print("=" * 100)
    print(f"{'Score':<8} {'Total':<12} {'Trades':<10} {'Rejected':<10} {'Wins':<8} {'Losses':<8} {'Win Rate':<10} {'Total PnL':<12} {'Avg PnL':<12}")
    print("-" * 100)
    
    for score, stats in win_rate_data.items():
        print(
            f"{score:<8} "
            f"{stats['total_evaluations']:<12} "
            f"{stats['trades_taken']:<10} "
            f"{stats['rejected']:<10} "
            f"{stats['wins']:<8} "
            f"{stats['losses']:<8} "
            f"{stats['win_rate_pct']:<10.2f}% "
            f"${stats['total_pnl']:<11.2f} "
            f"${stats['avg_pnl_per_trade']:<11.2f}"
        )
    
    print("=" * 100)


def print_rejection_stats(rejection_data: Dict[str, int]):
    """Print rejection reason statistics."""
    print("\n" + "=" * 80)
    print("REJECTION REASON STATISTICS")
    print("=" * 80)
    print(f"{'Reason':<40} {'Count':<10}")
    print("-" * 80)
    
    for reason, count in rejection_data.items():
        print(f"{reason:<40} {count:<10}")
    
    print("=" * 80)


def print_gate_pass_rates(gate_data: Dict[str, Dict[str, Any]]):
    """Print gate pass/fail statistics."""
    print("\n" + "=" * 80)
    print("GATE PASS/FAIL STATISTICS")
    print("=" * 80)
    print(f"{'Gate':<35} {'Total':<12} {'Passed':<10} {'Failed':<10} {'Pass Rate':<10}")
    print("-" * 80)
    
    for gate_name, stats in gate_data.items():
        print(
            f"{gate_name:<35} "
            f"{stats['total_evaluations']:<12} "
            f"{stats['passed']:<10} "
            f"{stats['failed']:<10} "
            f"{stats['pass_rate_pct']:<10.2f}%"
        )
    
    print("=" * 80)


def main():
    """Main analysis function."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Analyze setup logs for win-rate-by-score analysis")
    parser.add_argument("--date", type=str, help="Specific date to analyze (YYYY-MM-DD)")
    parser.add_argument("--trades", type=str, help="Path to trades CSV file")
    parser.add_argument("--output", type=str, help="Output JSON file path")
    args = parser.parse_args()
    
    # Load logs
    logs = load_setup_logs(args.date)
    if not logs:
        print("No logs found. Exiting.")
        return
    
    # Load trade results
    trade_map = load_trade_results(args.trades)
    
    # Build statistics
    win_rate_data = build_win_rate_by_score(logs, trade_map)
    rejection_data = build_rejection_reason_stats(logs)
    gate_data = build_gate_pass_rates(logs)
    
    # Print results
    print_win_rate_table(win_rate_data)
    print_rejection_stats(rejection_data)
    print_gate_pass_rates(gate_data)
    
    # Save to JSON if requested
    if args.output:
        output_data = {
            "win_rate_by_score": win_rate_data,
            "rejection_reasons": rejection_data,
            "gate_pass_rates": gate_data,
            "total_evaluations": len(logs),
            "total_trades": len(trade_map),
            "analysis_date": datetime.now().isoformat(),
        }
        
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(output_data, f, indent=2)
        
        print(f"\nAnalysis saved to: {output_path}")


if __name__ == "__main__":
    main()
