import streamlit as st
import subprocess
import pandas as pd
import sqlite3
import requests
import random
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

# ================= CONFIG =================
DEMO_MODE = True  # True = run at home with fake data. False = real SNMP.

SWITCHES = {
    "Lab Switch": "192.168.137.111",
}

UPS_DEVICES = {
    "Demo UPS": "192.168.137.120",
}

COMMUNITY = "public"
SNMPWALK_PATH = "snmpwalk"
DB_FILE = "network_monitor.db"

# Leave blank unless using a private webhook locally
DISCORD_WEBHOOK_URL = ""

st.set_page_config(page_title="SNMP Network Monitoring System", layout="wide")

# ================= STYLE =================
st.markdown("""
<style>
[data-testid="stAppViewContainer"] {
    background: linear-gradient(180deg, #0b1020 0%, #111827 100%);
}
[data-testid="stSidebar"] {
    background-color: #020617;
}
.stMetric {
    background-color: #111827;
    border: 1px solid #1f2937;
    padding: 14px;
    border-radius: 14px;
}
.noc-card {
    background-color: #111827;
    border: 1px solid #1f2937;
    padding: 18px;
    border-radius: 16px;
    margin-bottom: 12px;
}
.port-up {
    background-color: #052e16;
    border: 1px solid #22c55e;
    color: #bbf7d0;
    padding: 8px;
    border-radius: 10px;
    text-align: center;
    font-size: 13px;
}
.port-down {
    background-color: #450a0a;
    border: 1px solid #ef4444;
    color: #fecaca;
    padding: 8px;
    border-radius: 10px;
    text-align: center;
    font-size: 13px;
}
</style>
""", unsafe_allow_html=True)

# ================= DATABASE =================
def init_db():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS traffic_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            switch_name TEXT,
            switch_ip TEXT,
            interface TEXT,
            in_mbps REAL,
            out_mbps REAL,
            total_mbps REAL,
            status TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS ups_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            ups_name TEXT,
            ups_ip TEXT,
            battery_status TEXT,
            charge_percent INTEGER,
            runtime_minutes INTEGER,
            replace_battery TEXT
        )
    """)

    conn.commit()
    conn.close()


def save_to_db(df, switch_name, switch_ip):
    if df.empty:
        return

    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()

    for _, row in df.iterrows():
        cur.execute("""
            INSERT INTO traffic_logs (
                timestamp, switch_name, switch_ip, interface,
                in_mbps, out_mbps, total_mbps, status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            row["Time"], switch_name, switch_ip, row["Interface"],
            row["In Mbps"], row["Out Mbps"], row["Total Mbps"], row["Status"]
        ))

    conn.commit()
    conn.close()


def save_ups_to_db(ups_df):
    if ups_df.empty:
        return

    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()

    for _, row in ups_df.iterrows():
        cur.execute("""
            INSERT INTO ups_logs (
                timestamp, ups_name, ups_ip, battery_status,
                charge_percent, runtime_minutes, replace_battery
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            row["Time"], row["UPS"], row["IP"], row["Battery Status"],
            row["Charge %"], row["Runtime Min"], row["Replace Battery"]
        ))

    conn.commit()
    conn.close()


def load_interface_history(switch_ip, interface, limit=100):
    conn = sqlite3.connect(DB_FILE)

    query = """
        SELECT timestamp AS Time,
               in_mbps AS "In Mbps",
               out_mbps AS "Out Mbps",
               total_mbps AS "Total Mbps"
        FROM traffic_logs
        WHERE switch_ip = ? AND interface = ?
        ORDER BY id DESC
        LIMIT ?
    """

    df = pd.read_sql_query(query, conn, params=(switch_ip, interface, limit))
    conn.close()

    if not df.empty:
        df = df.iloc[::-1]

    return df


def load_recent_logs(limit=100):
    conn = sqlite3.connect(DB_FILE)

    query = """
        SELECT timestamp AS Time,
               switch_name AS Switch,
               switch_ip AS IP,
               interface AS Interface,
               in_mbps AS "In Mbps",
               out_mbps AS "Out Mbps",
               total_mbps AS "Total Mbps",
               status AS Status
        FROM traffic_logs
        ORDER BY id DESC
        LIMIT ?
    """

    df = pd.read_sql_query(query, conn, params=(limit,))
    conn.close()

    return df


def load_ups_logs(limit=100):
    conn = sqlite3.connect(DB_FILE)

    query = """
        SELECT timestamp AS Time,
               ups_name AS UPS,
               ups_ip AS IP,
               battery_status AS "Battery Status",
               charge_percent AS "Charge %",
               runtime_minutes AS "Runtime Min",
               replace_battery AS "Replace Battery"
        FROM ups_logs
        ORDER BY id DESC
        LIMIT ?
    """

    df = pd.read_sql_query(query, conn, params=(limit,))
    conn.close()

    return df

# ================= DISCORD =================
def send_discord_alert(message):
    if not DISCORD_WEBHOOK_URL:
        return

    try:
        requests.post(DISCORD_WEBHOOK_URL, json={"content": message}, timeout=5)
    except Exception as e:
        st.warning(f"Discord alert failed: {e}")


def can_send_alert(alert_key, cooldown_seconds=60):
    now = datetime.now()

    if "last_alert_time" not in st.session_state:
        st.session_state.last_alert_time = {}

    last_sent = st.session_state.last_alert_time.get(alert_key)

    if last_sent is None:
        st.session_state.last_alert_time[alert_key] = now
        return True

    elapsed = (now - last_sent).total_seconds()

    if elapsed >= cooldown_seconds:
        st.session_state.last_alert_time[alert_key] = now
        return True

    return False

# ================= SNMP / DEMO =================
def snmp_walk(device_ip, oid):
    try:
        cmd = f"{SNMPWALK_PATH} -v2c -c {COMMUNITY} {device_ip} {oid}"

        result = subprocess.check_output(
            cmd,
            shell=True,
            timeout=10,
            stderr=subprocess.DEVNULL
        )

        text = result.decode("cp1252", errors="ignore")
        data = []

        for line in text.splitlines():
            if "=" not in line:
                continue

            left, right = line.split("=", 1)
            data.append((left.strip(), right.strip()))

        return data

    except Exception as e:
        st.error(f"SNMP error on {device_ip}: {e}")
        return []


def clean_value(value):
    for prefix in ["STRING:", "INTEGER:", "Counter32:", "Counter64:", "Gauge32:", "Timeticks:"]:
        value = value.replace(prefix, "")

    return value.replace('"', "").strip()


def demo_counter(device_ip, oid):
    if "demo_counters" not in st.session_state:
        st.session_state.demo_counters = {}

    key = f"{device_ip}-{oid}"

    if key not in st.session_state.demo_counters:
        st.session_state.demo_counters[key] = random.randint(1_000_000, 5_000_000)

    st.session_state.demo_counters[key] += random.randint(50_000, 900_000)

    return str(st.session_state.demo_counters[key])


def get_value(device_ip, oid):
    if DEMO_MODE:
        # Interface status: 1 = UP, 2 = DOWN
        if ".1.8." in oid:
            return str(random.choice([1, 1, 1, 1, 2]))

        # Interface traffic counters
        if ".1.10." in oid or ".1.16." in oid:
            return demo_counter(device_ip, oid)

        # UPS battery status: 2 normal, 3 low, 4 depleted
        if "33.1.2.1.0" in oid:
            return str(random.choice([2, 2, 2, 3]))

        # UPS runtime minutes
        if "33.1.2.3.0" in oid:
            return str(random.randint(10, 90))

        # UPS charge percentage
        if "33.1.2.4.0" in oid:
            return str(random.randint(15, 100))

        # APC replace battery: 1 no, 2 yes
        if "318.1.1.1.2.2.4.0" in oid:
            return str(random.choice([1, 1, 1, 2]))

        return "0"

    raw = snmp_walk(device_ip, oid)

    if not raw:
        return None

    return clean_value(raw[0][1])

# ================= SWITCH MONITORING =================
@st.cache_data(ttl=300)
def get_interfaces(switch_ip):
    if DEMO_MODE:
        return {
            "GigabitEthernet1/0/1": 1,
            "GigabitEthernet1/0/2": 2,
            "GigabitEthernet1/0/3": 3,
            "GigabitEthernet1/0/4": 4,
            "GigabitEthernet1/0/5": 5,
            "GigabitEthernet1/0/6": 6,
            "GigabitEthernet1/0/7": 7,
            "GigabitEthernet1/0/8": 8,
            "GigabitEthernet1/0/9": 9,
            "GigabitEthernet1/0/10": 10,
            "GigabitEthernet1/0/11": 11,
            "GigabitEthernet1/0/12": 12,
            "GigabitEthernet1/0/13": 13,
            "GigabitEthernet1/0/14": 14,
        }

    raw = snmp_walk(switch_ip, "1.3.6.1.2.1.2.2.1.2")
    interfaces = {}

    for oid, value in raw:
        try:
            idx = int(oid.split(".")[-1])
            name = clean_value(value)

            if not name.startswith("GigabitEthernet"):
                continue

            port_num = int(name.split("/")[-1])
            if port_num > 14:
                continue

            interfaces[name] = idx

        except Exception:
            continue

    return interfaces


if "prev_data" not in st.session_state:
    st.session_state.prev_data = {}

if "last_poll_time" not in st.session_state:
    st.session_state.last_poll_time = datetime.now()

if "alerts" not in st.session_state:
    st.session_state.alerts = []

if "active_down_alerts" not in st.session_state:
    st.session_state.active_down_alerts = set()

if "active_high_alerts" not in st.session_state:
    st.session_state.active_high_alerts = set()

if "active_ups_alerts" not in st.session_state:
    st.session_state.active_ups_alerts = set()

if "last_alert_time" not in st.session_state:
    st.session_state.last_alert_time = {}


def get_interface_data(switch_name, switch_ip, interfaces):
    rows = []
    now = datetime.now()
    now_display = now.strftime("%Y-%m-%d %H:%M:%S")

    elapsed = (now - st.session_state.last_poll_time).total_seconds()
    if elapsed <= 0:
        elapsed = 1

    for name, idx in interfaces.items():
        try:
            key = f"{switch_ip}-{name}"

            in_val = get_value(switch_ip, f"1.3.6.1.2.1.2.2.1.10.{idx}")
            out_val = get_value(switch_ip, f"1.3.6.1.2.1.2.2.1.16.{idx}")
            status_val = get_value(switch_ip, f"1.3.6.1.2.1.2.2.1.8.{idx}")

            in_bytes = int(in_val) if in_val and in_val.isdigit() else 0
            out_bytes = int(out_val) if out_val and out_val.isdigit() else 0
            status_num = int(status_val) if status_val and status_val.isdigit() else 2

            prev = st.session_state.prev_data.get(key)

            if prev:
                in_delta = max(in_bytes - prev["in"], 0)
                out_delta = max(out_bytes - prev["out"], 0)

                in_mbps = (in_delta * 8) / elapsed / 1_000_000
                out_mbps = (out_delta * 8) / elapsed / 1_000_000
            else:
                in_mbps = 0
                out_mbps = 0

            st.session_state.prev_data[key] = {"in": in_bytes, "out": out_bytes}

            total_mbps = in_mbps + out_mbps
            status = "UP" if status_num == 1 else "DOWN"

            rows.append({
                "Time": now_display,
                "Switch": switch_name,
                "IP": switch_ip,
                "Interface": name,
                "In Mbps": round(in_mbps, 3),
                "Out Mbps": round(out_mbps, 3),
                "Total Mbps": round(total_mbps, 3),
                "Status": status
            })

        except Exception:
            continue

    st.session_state.last_poll_time = now

    return pd.DataFrame(rows, columns=[
        "Time", "Switch", "IP", "Interface",
        "In Mbps", "Out Mbps", "Total Mbps", "Status"
    ])

# ================= UPS MONITORING =================
def parse_int(value, default=None):
    if value is None:
        return default

    value = str(value).strip()

    if value.isdigit():
        return int(value)

    return default


def get_ups_data():
    rows = []
    now_display = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for ups_name, ups_ip in UPS_DEVICES.items():
        battery_status_raw = get_value(ups_ip, "1.3.6.1.2.1.33.1.2.1.0")
        runtime_raw = get_value(ups_ip, "1.3.6.1.2.1.33.1.2.3.0")
        charge_raw = get_value(ups_ip, "1.3.6.1.2.1.33.1.2.4.0")
        replace_raw = get_value(ups_ip, "1.3.6.1.4.1.318.1.1.1.2.2.4.0")

        battery_status_num = parse_int(battery_status_raw, 1)
        runtime_min = parse_int(runtime_raw, 0)
        charge_percent = parse_int(charge_raw, 0)
        replace_num = parse_int(replace_raw, 1)

        if battery_status_num == 2:
            battery_status = "NORMAL"
        elif battery_status_num == 3:
            battery_status = "LOW"
        elif battery_status_num == 4:
            battery_status = "DEPLETED"
        else:
            battery_status = "UNKNOWN"

        replace_battery = "YES" if replace_num == 2 else "NO"

        rows.append({
            "Time": now_display,
            "UPS": ups_name,
            "IP": ups_ip,
            "Battery Status": battery_status,
            "Charge %": charge_percent,
            "Runtime Min": runtime_min,
            "Replace Battery": replace_battery
        })

    return pd.DataFrame(rows, columns=[
        "Time", "UPS", "IP", "Battery Status",
        "Charge %", "Runtime Min", "Replace Battery"
    ])


def add_alert(message, alert_type="info"):
    entry = {
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "type": alert_type,
        "message": message
    }

    st.session_state.alerts.insert(0, entry)
    st.session_state.alerts = st.session_state.alerts[:30]


def generate_switch_alerts(df, threshold):
    for _, row in df.iterrows():
        switch = row["Switch"]
        ip = row["IP"]
        interface = row["Interface"]
        total_mbps = row["Total Mbps"]
        status = row["Status"]

        down_key = f"DOWN-{ip}-{interface}"
        high_key = f"HIGH-{ip}-{interface}"

        if status == "DOWN" and down_key not in st.session_state.active_down_alerts:
            message = f"🔴 {switch} {interface} is DOWN"
            st.session_state.active_down_alerts.add(down_key)
            add_alert(message, "down")

            if can_send_alert(down_key):
                send_discord_alert(message)

        if status == "UP" and down_key in st.session_state.active_down_alerts:
            message = f"🟢 {switch} {interface} is back UP"
            st.session_state.active_down_alerts.remove(down_key)
            add_alert(message, "recovery")

            if can_send_alert(f"RECOVERY-{ip}-{interface}"):
                send_discord_alert(message)

        if total_mbps > threshold and high_key not in st.session_state.active_high_alerts:
            message = f"⚠️ High traffic on {switch} {interface}: {total_mbps} Mbps"
            st.session_state.active_high_alerts.add(high_key)
            add_alert(message, "high")

            if can_send_alert(high_key):
                send_discord_alert(message)

        if total_mbps <= threshold and high_key in st.session_state.active_high_alerts:
            message = f"✅ Traffic normalized on {switch} {interface}: {total_mbps} Mbps"
            st.session_state.active_high_alerts.remove(high_key)
            add_alert(message, "recovery")

            if can_send_alert(f"HIGH-RECOVERY-{ip}-{interface}"):
                send_discord_alert(message)


def generate_ups_alerts(ups_df, low_charge_threshold):
    for _, row in ups_df.iterrows():
        ups = row["UPS"]
        ip = row["IP"]
        battery_status = row["Battery Status"]
        charge = row["Charge %"]
        replace_battery = row["Replace Battery"]

        low_key = f"UPS-LOW-{ip}"
        replace_key = f"UPS-REPLACE-{ip}"

        if battery_status in ["LOW", "DEPLETED"] or charge <= low_charge_threshold:
            if low_key not in st.session_state.active_ups_alerts:
                message = f"🔋 UPS Alert: {ups} battery is {battery_status}, charge {charge}%"
                st.session_state.active_ups_alerts.add(low_key)
                add_alert(message, "high")

                if can_send_alert(low_key):
                    send_discord_alert(message)

        else:
            if low_key in st.session_state.active_ups_alerts:
                message = f"✅ UPS Recovery: {ups} battery is normal, charge {charge}%"
                st.session_state.active_ups_alerts.remove(low_key)
                add_alert(message, "recovery")

                if can_send_alert(f"UPS-LOW-RECOVERY-{ip}"):
                    send_discord_alert(message)

        if replace_battery == "YES":
            if replace_key not in st.session_state.active_ups_alerts:
                message = f"🚨 UPS Battery Replacement Needed: {ups}"
                st.session_state.active_ups_alerts.add(replace_key)
                add_alert(message, "down")

                if can_send_alert(replace_key):
                    send_discord_alert(message)

        else:
            if replace_key in st.session_state.active_ups_alerts:
                message = f"✅ UPS Battery Replacement Cleared: {ups}"
                st.session_state.active_ups_alerts.remove(replace_key)
                add_alert(message, "recovery")

                if can_send_alert(f"UPS-REPLACE-RECOVERY-{ip}"):
                    send_discord_alert(message)


def status_badge(status):
    if status == "UP":
        return "🟢 UP"
    return "🔴 DOWN"


def render_network_map(df):
    st.subheader("🗺️ Network Map View")

    if df.empty:
        st.info("No interface data yet.")
        return

    switch_name = df["Switch"].iloc[0]
    switch_ip = df["IP"].iloc[0]

    st.markdown(
        f"""
        <div class="noc-card">
            <h3>🖧 {switch_name}</h3>
            <p>{switch_ip}</p>
        </div>
        """,
        unsafe_allow_html=True
    )

    cols = st.columns(4)

    for i, (_, row) in enumerate(df.iterrows()):
        port = row["Interface"].replace("GigabitEthernet", "Gi")
        status = row["Status"]
        traffic = row["Total Mbps"]

        css_class = "port-up" if status == "UP" else "port-down"

        with cols[i % 4]:
            st.markdown(
                f"""
                <div class="{css_class}">
                    <b>{port}</b><br>
                    {status_badge(status)}<br>
                    {traffic} Mbps
                </div>
                """,
                unsafe_allow_html=True
            )

# ================= START =================
init_db()

st.title("🖥️ SNMP Network Monitoring System")

if DEMO_MODE:
    st.warning("⚠️ Running in DEMO MODE — simulated switch and UPS data")

st.caption("NOC-style monitoring for switches and UPS devices using SNMP, SQLite, and Discord alerts.")

st.sidebar.header("NOC Controls")

selected_switch_name = st.sidebar.selectbox("Select Switch", list(SWITCHES.keys()))
selected_switch_ip = SWITCHES[selected_switch_name]

refresh_rate = st.sidebar.slider("Refresh Interval (sec)", 10, 60, 15)
traffic_threshold = st.sidebar.slider("High Traffic Alert Mbps", 1, 100, 25)
low_charge_threshold = st.sidebar.slider("UPS Low Battery Threshold %", 5, 50, 20)
history_limit = st.sidebar.slider("History Records", 25, 500, 100)

st.sidebar.write(f"Monitoring switch: `{selected_switch_ip}`")

if st.sidebar.button("Refresh Interfaces"):
    st.cache_data.clear()
    st.session_state.prev_data = {}
    st.rerun()

if st.sidebar.button("Clear Alerts"):
    st.session_state.alerts = []
    st.session_state.active_down_alerts = set()
    st.session_state.active_high_alerts = set()
    st.session_state.active_ups_alerts = set()
    st.session_state.last_alert_time = {}
    st.rerun()

st_autorefresh(interval=refresh_rate * 1000, key="refresh")

interfaces = get_interfaces(selected_switch_ip)

if not interfaces:
    st.error("No GigabitEthernet ports 1-14 found.")
    st.stop()

df = get_interface_data(selected_switch_name, selected_switch_ip, interfaces)

save_to_db(df, selected_switch_name, selected_switch_ip)
generate_switch_alerts(df, traffic_threshold)

ups_df = get_ups_data()
save_ups_to_db(ups_df)
generate_ups_alerts(ups_df, low_charge_threshold)

total_ports = len(df)
up_ports = len(df[df["Status"] == "UP"])
down_ports = len(df[df["Status"] == "DOWN"])
total_traffic = round(df["Total Mbps"].sum(), 3) if not df.empty else 0

ups_alerts = 0
if not ups_df.empty:
    ups_alerts = len(
        ups_df[
            (ups_df["Battery Status"].isin(["LOW", "DEPLETED"])) |
            (ups_df["Replace Battery"] == "YES") |
            (ups_df["Charge %"] <= low_charge_threshold)
        ]
    )

col1, col2, col3, col4, col5 = st.columns(5)

with col1:
    st.metric("Ports Monitored", total_ports)

with col2:
    st.metric("Ports UP", up_ports)

with col3:
    st.metric("Ports DOWN", down_ports)

with col4:
    st.metric("Total Mbps", total_traffic)

with col5:
    st.metric("UPS Alerts", ups_alerts)

st.divider()

st.subheader("🔋 UPS Battery Monitoring")

if not ups_df.empty:
    st.dataframe(ups_df, use_container_width=True)

    for _, row in ups_df.iterrows():
        if row["Replace Battery"] == "YES":
            st.error(f"🚨 {row['UPS']}: Battery replacement needed")
        elif row["Battery Status"] in ["LOW", "DEPLETED"]:
            st.warning(f"🔋 {row['UPS']}: Battery {row['Battery Status']}")
        elif row["Charge %"] <= low_charge_threshold:
            st.warning(f"🔋 {row['UPS']}: Low charge {row['Charge %']}%")
        else:
            st.success(f"✅ {row['UPS']}: Battery OK")
else:
    st.info("No UPS devices configured or no UPS data available.")

st.divider()

render_network_map(df)

st.divider()

st.subheader("🚨 Alert Center")

if st.session_state.alerts:
    for alert in st.session_state.alerts[:8]:
        msg = f"{alert['time']} - {alert['message']}"

        if alert["type"] == "down":
            st.error(msg)
        elif alert["type"] == "high":
            st.warning(msg)
        elif alert["type"] == "recovery":
            st.success(msg)
        else:
            st.info(msg)
else:
    st.success("No active alerts.")

st.divider()

left, right = st.columns(2)

with left:
    st.subheader("📡 Live Interface Table")

    styled_df = df.copy()
    styled_df["Status"] = styled_df["Status"].apply(status_badge)

    st.dataframe(styled_df, use_container_width=True)

with right:
    st.subheader("📊 Current Traffic by Port")

    if not df.empty:
        chart_df = df.set_index("Interface")[["In Mbps", "Out Mbps"]]
        st.bar_chart(chart_df)
    else:
        st.info("No traffic data yet.")

st.divider()

st.subheader("🔥 Top Talkers")

if not df.empty:
    top_talkers = df.sort_values("Total Mbps", ascending=False).head(5)
    st.dataframe(
        top_talkers[["Switch", "Interface", "In Mbps", "Out Mbps", "Total Mbps", "Status"]],
        use_container_width=True
    )
else:
    st.info("No top talker data yet.")

st.divider()

st.subheader("📈 SQLite Historical Traffic")

selected_port = st.selectbox("Select Interface", df["Interface"].tolist())

history_df = load_interface_history(selected_switch_ip, selected_port, history_limit)

if not history_df.empty:
    history_chart = history_df.set_index("Time")[["In Mbps", "Out Mbps", "Total Mbps"]]
    st.line_chart(history_chart)
else:
    st.info("No historical records yet.")

st.divider()

st.subheader("🗄️ Recent Switch Database Records")

recent_logs = load_recent_logs(history_limit)
st.dataframe(recent_logs, use_container_width=True)

st.subheader("🔋 Recent UPS Database Records")

recent_ups_logs = load_ups_logs(history_limit)
st.dataframe(recent_ups_logs, use_container_width=True)

st.caption(f"Database file: `{DB_FILE}`")