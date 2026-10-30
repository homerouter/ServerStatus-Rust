#!/usr/bin/env python3
"""
traffic_reporter.py - Tailnet VPS ServerStatus Traffic Digest & Anomaly Monitor.

Features:
- Daily traffic summary report to Telegram channel.
- Real-time bandwidth burst and daily usage anomaly alerting.
- Automatic daily delta calculation with persistent baseline tracking.
- Anti-spam cooldown per node.
- Zero extra dependencies (pure Python 3 standard library).
"""

import argparse
import datetime
import json
import os
import sys
import urllib.parse
import urllib.request

FLAG_MAP = {
    "us": "🇺🇸",
    "jp": "🇯🇵",
    "hk": "🇭🇰",
    "sg": "🇸🇬",
    "cn": "🇨🇳",
}

REGION_TITLES = {
    "us": "🇺🇸 美西 (US)",
    "jp": "🇯🇵 日本 (JP)",
    "hk": "🇭🇰 香港 (HK)",
    "sg": "🇸🇬 新加坡 (SG)",
}


def human_bytes(num_bytes: float) -> str:
    """Format bytes into human readable string (e.g., 1.25 GB, 250 MB)."""
    if num_bytes < 0:
        num_bytes = 0
    for unit in ["B", "KB", "MB", "GB", "TB", "PB"]:
        if num_bytes < 1024.0 or unit == "PB":
            if unit in ["B", "KB"]:
                return f"{int(num_bytes)} {unit}"
            return f"{num_bytes:.2f} {unit}"
        num_bytes /= 1024.0
    return f"{num_bytes:.2f} PB"


def human_rate(bytes_per_sec: float) -> str:
    """Format bytes per second with Mbps equivalence."""
    mb_s = bytes_per_sec / (1024.0 * 1024.0)
    mbps = (bytes_per_sec * 8.0) / (1000.0 * 1000.0)
    if mb_s >= 1.0:
        return f"{mb_s:.1f} MB/s ({mbps:.1f} Mbps)"
    kb_s = bytes_per_sec / 1024.0
    return f"{kb_s:.1f} KB/s"


def parse_labels(label_str: str) -> dict:
    """Parse 'role=sing-box;loc=San Jose;;os=debian' into a dict."""
    res = {}
    if not label_str:
        return res
    for part in label_str.split(";"):
        part = part.strip()
        if "=" in part:
            k, v = part.split("=", 1)
            res[k.strip()] = v.strip()
    return res


def send_telegram(token: str, chat_id: str, text: str) -> bool:
    """Send HTML message via Telegram Bot API."""
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", "User-Agent": "TailnetTrafficReporter/1.0"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            res = json.loads(resp.read().decode())
            return res.get("ok", False)
    except Exception as e:
        sys.stderr.write(f"Error sending telegram message: {e}\n")
        return False


def load_state(path: str) -> dict:
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            sys.stderr.write(f"Warning: Failed to load state file {path}: {e}\n")
    return {"last_daily": {}, "alerts": {}}


def save_state(path: str, state: dict):
    tmp_path = f"{path}.tmp"
    dir_name = os.path.dirname(path)
    if dir_name:
        os.makedirs(dir_name, exist_ok=True)
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
    os.replace(tmp_path, path)


def fetch_stats(url: str) -> dict:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "TailnetTrafficReporter/1.0"},
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode())


CST_TZ = datetime.timezone(datetime.timedelta(hours=8))


def get_cst_now() -> datetime.datetime:
    """Return current datetime in UTC+8 (Beijing Time)."""
    return datetime.datetime.now(CST_TZ)


def sync_daily_baselines(servers: list, state: dict) -> dict:
    """Maintain daily 00:00 baselines indexed by YYYY-MM-DD in CST (UTC+8)."""
    now_cst = get_cst_now()
    today_str = now_cst.strftime("%Y-%m-%d")

    new_state = dict(state)
    daily = new_state.setdefault("daily_baselines", {})

    # Migrate legacy last_daily if daily_baselines is empty
    if not daily and "last_daily" in new_state and "nodes" in new_state["last_daily"]:
        legacy_ts = new_state["last_daily"].get("timestamp", int(now_cst.timestamp()))
        legacy_date = datetime.datetime.fromtimestamp(legacy_ts, tz=CST_TZ).strftime("%Y-%m-%d")
        daily[legacy_date] = {
            "timestamp": legacy_ts,
            "nodes": new_state["last_daily"]["nodes"],
        }

    curr_nodes = {
        s.get("name"): {"in": s.get("network_in", 0), "out": s.get("network_out", 0)}
        for s in servers
        if s.get("name")
    }

    if today_str not in daily:
        daily[today_str] = {
            "timestamp": int(now_cst.timestamp()),
            "nodes": curr_nodes,
        }

    # Prune snapshots older than 7 days
    cutoff_date = (now_cst - datetime.timedelta(days=7)).strftime("%Y-%m-%d")
    for k in list(daily.keys()):
        if k < cutoff_date:
            del daily[k]

    return new_state


def build_daily_report(servers: list, state: dict) -> tuple[str, dict]:
    """Generate HTML daily report strictly for a 24-hour single-day period."""
    now_cst = get_cst_now()
    today_str = now_cst.strftime("%Y-%m-%d")
    yesterday_str = (now_cst - datetime.timedelta(days=1)).strftime("%Y-%m-%d")

    state = sync_daily_baselines(servers, state)
    daily = state.get("daily_baselines", {})

    curr_nodes = {
        s.get("name"): {"in": s.get("network_in", 0), "out": s.get("network_out", 0)}
        for s in servers
        if s.get("name")
    }

    # Check if yesterday's full 24h baseline exists (yesterday 00:00 to today 00:00)
    has_yesterday = yesterday_str in daily and today_str in daily

    if has_yesterday:
        report_title = f"📅 统计周期: <code>{yesterday_str} 00:00 ~ 24:00 (UTC+8)</code>"
        start_nodes = daily[yesterday_str]["nodes"]
        end_nodes = daily[today_str]["nodes"]
    else:
        # Fallback to today so far (00:00 ~ now)
        report_title = f"📅 统计周期: <code>{today_str} 00:00 ~ {now_cst.strftime('%H:%M')} (UTC+8)</code>"
        start_nodes = daily.get(today_str, {}).get("nodes", curr_nodes)
        end_nodes = curr_nodes

    total_delta_in = 0
    total_delta_out = 0
    online_count = sum(1 for s in servers if s.get("online4"))

    regions: dict[str, list] = {}
    top_out_list = []

    for s in servers:
        name = s.get("name", "")
        loc = s.get("location", "us")

        s_start = start_nodes.get(name, {})
        s_end = end_nodes.get(name, {})
        start_out = s_start.get("out", 0)
        start_in = s_start.get("in", 0)
        end_out = s_end.get("out", 0)
        end_in = s_end.get("in", 0)

        # Calculate single-day delta
        if end_out >= start_out:
            delta_out = end_out - start_out
        elif start_out > 0 and end_out < (start_out / 2):
            delta_out = end_out  # Reboot from 0
        else:
            delta_out = 0  # Interface exclusion or counter adjustment

        if end_in >= start_in:
            delta_in = end_in - start_in
        elif start_in > 0 and end_in < (start_in / 2):
            delta_in = end_in  # Reboot from 0
        else:
            delta_in = 0  # Interface exclusion or counter adjustment

        total_delta_out += delta_out
        total_delta_in += delta_in

        top_out_list.append((delta_out, delta_in, s))

        if loc not in regions:
            regions[loc] = []
        regions[loc].append((s, delta_out, delta_in))

    # Sort Top 3 by outbound traffic in this period
    top_out_list.sort(key=lambda x: x[0], reverse=True)

    lines = [
        "📊 <b>Tailnet 节点流量日报</b>",
        report_title,
        f"🌐 节点状态: <b>{online_count}/{len(servers)}</b> 在线\n",
        "📈 <b>全网单日流量</b>",
        f"• 单日出站 (TX): <b>{human_bytes(total_delta_out)}</b>",
        f"• 单日入站 (RX): <b>{human_bytes(total_delta_in)}</b>",
    ]

    # Top 3 consumer nodes by single-day traffic
    lines.append("\n🏆 <b>单日出站 Top 3</b>")
    for idx, (d_out, d_in, s) in enumerate(top_out_list[:3], 1):
        labels = parse_labels(s.get("labels", ""))
        role_desc = labels.get("role") or ("Alpine" if labels.get("os") == "alpine" else "")
        role_txt = f" ({role_desc})" if role_desc else ""
        flag = FLAG_MAP.get(s.get("location", ""), "🌐")
        lines.append(f"{idx}. {flag} <code>{s.get('name')}</code>{role_txt}: <b>{human_bytes(d_out)}</b>")

    # Region breakdown (pure single-day delta)
    region_order = ["us", "jp", "hk", "sg"]
    for r in region_order:
        if r not in regions:
            continue
        r_title = REGION_TITLES.get(r, f"🌐 {r.upper()}")
        lines.append(f"\n{r_title}")
        for s, d_out, d_in in regions[r]:
            labels = parse_labels(s.get("labels", ""))
            role_desc = labels.get("role") or ("Alpine" if labels.get("os") == "alpine" else "")
            role_txt = f" ({role_desc})" if role_desc else ""
            lines.append(f"• <code>{s.get('name'):<4}</code>{role_txt}: {human_bytes(d_out)} ↑ | {human_bytes(d_in)} ↓")

    return "\n".join(lines), state


def check_anomalies(
    servers: list,
    state: dict,
    burst_bytes_sec: float,
    daily_quota_bytes: float,
    cooldown_sec: int,
) -> tuple[list[str], dict]:
    """Check for real-time bursts or extreme usage, return alert messages and updated state."""
    now_ts = int(datetime.datetime.now().timestamp())
    alerts_state = state.get("alerts", {})
    now_cst = get_cst_now()
    today_str = now_cst.strftime("%Y-%m-%d")
    time_str = now_cst.strftime("%Y-%m-%d %H:%M:%S (UTC+8)")

    state = sync_daily_baselines(servers, state)
    daily = state.get("daily_baselines", {})
    today_baseline = daily.get(today_str, {}).get("nodes", {})

    alert_msgs = []

    for s in servers:
        name = s.get("name", "")
        if not s.get("online4"):
            continue

        rx_rate = s.get("network_rx", 0)
        tx_rate = s.get("network_tx", 0)
        labels = parse_labels(s.get("labels", ""))
        role_desc = labels.get("role") or ("Alpine" if labels.get("os") == "alpine" else "")
        role_txt = f" ({role_desc})" if role_desc else ""
        flag = FLAG_MAP.get(s.get("location", ""), "🌐")
        loc_desc = labels.get("loc", s.get("location", ""))

        # 1. Bandwidth burst check
        if max(rx_rate, tx_rate) >= burst_bytes_sec:
            alert_key = f"burst_{name}"
            last_alert = alerts_state.get(alert_key, 0)
            if now_ts - last_alert >= cooldown_sec:
                msg = (
                    f"⚡ <b>【流量突增告警】节点带宽瞬时飙升</b>\n\n"
                    f"🖥 <b>节点</b>: {flag} <code>{name}</code>{role_txt}\n"
                    f"📍 <b>位置</b>: {loc_desc}\n"
                    f"🚀 <b>实时下行 (RX)</b>: <code>{human_rate(rx_rate)}</code>\n"
                    f"🚀 <b>实时上行 (TX)</b>: <code>{human_rate(tx_rate)}</code>\n"
                    f"⏰ <b>时间</b>: <code>{time_str}</code>\n\n"
                    f"💡 <i>瞬时速率已超过设定阈值 ({human_rate(burst_bytes_sec)})，请留意服务负载。</i>"
                )
                alert_msgs.append(msg)
                alerts_state[alert_key] = now_ts

        # 2. Daily delta surge check (measured strictly against today's 00:00 baseline)
        if today_baseline and name in today_baseline:
            prev_out = today_baseline[name].get("out", 0)
            net_out = s.get("network_out", 0)
            if net_out >= prev_out:
                delta_out = net_out - prev_out
            elif prev_out > 0 and net_out < (prev_out / 2):
                delta_out = net_out  # Reboot from 0
            else:
                # Counter dropped slightly (e.g. interface exclusion); re-anchor baseline safely
                today_baseline[name]["out"] = net_out
                delta_out = 0
            if delta_out >= daily_quota_bytes:
                alert_key = f"quota_{name}"
                last_alert = alerts_state.get(alert_key, 0)
                if now_ts - last_alert >= cooldown_sec:
                    msg = (
                        f"⚠️ <b>【流量超额告警】单日流量消耗过快</b>\n\n"
                        f"🖥 <b>节点</b>: {flag} <code>{name}</code>{role_txt}\n"
                        f"📍 <b>位置</b>: {loc_desc}\n"
                        f"📈 <b>今日出站消耗</b>: <b>{human_bytes(delta_out)}</b>\n"
                        f"⏰ <b>时间</b>: <code>{time_str}</code>\n\n"
                        f"💡 <i>单日消耗已突破告警阈值 ({human_bytes(daily_quota_bytes)})，请留意异常流出。</i>"
                    )
                    alert_msgs.append(msg)
                    alerts_state[alert_key] = now_ts

    new_state = dict(state)
    new_state["alerts"] = alerts_state
    return alert_msgs, new_state


def main():
    parser = argparse.ArgumentParser(description="Tailnet VPS Traffic Reporter & Anomaly Monitor")
    parser.add_argument("--stats-url", default=os.getenv("STAT_URL", "http://100.74.39.33:8888/json/stats.json"), help="ServerStatus JSON URL")
    parser.add_argument("--bot-token", default=os.getenv("TG_BOT_TOKEN"), help="Telegram Bot Token")
    parser.add_argument("--chat-id", default=os.getenv("TG_CHANNEL_ID"), help="Telegram Chat ID or Channel ID")
    parser.add_argument("--state-file", default="/opt/ServerStatus/traffic_state.json", help="Path to state JSON")
    parser.add_argument("--burst-mb", type=float, default=20.0, help="Burst threshold in MB/s (default: 20 MB/s)")
    parser.add_argument("--daily-gb", type=float, default=80.0, help="Daily quota alert in GB (default: 80 GB)")
    parser.add_argument("--cooldown-sec", type=int, default=7200, help="Alert cooldown in seconds (default: 7200s)")
    parser.add_argument("--report", action="store_true", help="Send daily traffic report")
    parser.add_argument("--check", action="store_true", help="Check for traffic anomalies")
    parser.add_argument("--init-baseline", action="store_true", help="Save current snapshot as baseline without sending Telegram message")
    parser.add_argument("--dry-run", action="store_true", help="Print output to stdout without sending Telegram")

    args = parser.parse_args()

    if not args.report and not args.check and not args.init_baseline:
        # Default to dry-run report if nothing specified
        args.report = True
        args.dry_run = True

    try:
        stats = fetch_stats(args.stats_url)
    except Exception as e:
        sys.stderr.write(f"Error fetching stats from {args.stats_url}: {e}\n")
        sys.exit(1)

    servers = stats.get("servers", [])
    state = load_state(args.state_file)

    if args.init_baseline:
        new_state = sync_daily_baselines(servers, state)
        save_state(args.state_file, new_state)
        print(f"Baseline saved to {args.state_file} ({len(servers)} servers tracked).")
        return

    if args.report:
        report_text, new_state = build_daily_report(servers, state)
        if args.dry_run:
            print("--- DAILY REPORT (DRY RUN) ---")
            print(report_text)
        else:
            if not args.bot_token or not args.chat_id:
                sys.stderr.write("Error: bot-token or chat-id missing for Telegram report.\n")
                sys.exit(1)
            ok = send_telegram(args.bot_token, args.chat_id, report_text)
            if ok:
                save_state(args.state_file, new_state)
                print("Daily report sent successfully.")
            else:
                sys.exit(1)

    if args.check:
        burst_bytes = args.burst_mb * 1024.0 * 1024.0
        daily_quota_bytes = args.daily_gb * 1024.0 * 1024.0 * 1024.0
        alerts, new_state = check_anomalies(servers, state, burst_bytes, daily_quota_bytes, args.cooldown_sec)

        for msg in alerts:
            if args.dry_run:
                print("--- ANOMALY ALERT (DRY RUN) ---")
                print(msg)
            else:
                if not args.bot_token or not args.chat_id:
                    sys.stderr.write("Error: bot-token or chat-id missing for Telegram alert.\n")
                    sys.exit(1)
                send_telegram(args.bot_token, args.chat_id, msg)

        # Always persist baseline state on 15-minute check to guarantee 00:00 midnight capture
        if not args.dry_run:
            save_state(args.state_file, new_state)
            if alerts:
                print(f"Sent {len(alerts)} anomaly alert(s).")
        else:
            if not alerts:
                print("No anomalies detected.")


if __name__ == "__main__":
    main()
