import asyncio
from datetime import datetime
import csv
import traceback

from pysnmp.hlapi.v3arch.asyncio import (
    SnmpEngine,
    CommunityData,
    UdpTransportTarget,
    ContextData,
    ObjectType,
    ObjectIdentity,
    get_cmd,
    next_cmd
)

# ================= CONFIG =================
SWITCH_IP = "192.168.137.111"
COMMUNITY = "public"
CSV_FILE = r"C:\Users\jkonik\Desktop\Network Traffic Project\snmp_log.csv"
POLL_INTERVAL = 2

# Dynamic tracking
status_up = {}
prev_in = {}
prev_out = {}

# ================= SNMP GET =================
async def snmp_get(ip, oid):
    try:
        errorIndication, errorStatus, errorIndex, varBinds = await get_cmd(
            SnmpEngine(),
            CommunityData(COMMUNITY, mpModel=1),
            await UdpTransportTarget.create((ip, 161)),
            ContextData(),
            ObjectType(ObjectIdentity(oid))
        )

        if errorIndication or errorStatus or not varBinds:
            return None

        return int(varBinds[0][1])

    except Exception:
        return None


# ================= SNMP WALK =================

import subprocess

def snmp_walk(ip, oid):
    try:
        result = subprocess.check_output([
            "snmpwalk",
            "-v2c",
            "-c", COMMUNITY,
            ip,
            oid
        ], text=True, timeout=20)

        lines = result.splitlines()

        parsed = []

        for line in lines:
            if "=" not in line:
                continue

            left, right = line.split("=", 1)

            oid_part = left.strip()
            value_part = right.strip()

            # convert into pseudo varBind format
            parsed.append((oid_part, value_part))

        return parsed

    except Exception as e:
        print("SNMP WALK FAILED:", e)
        return []

# ================= DISCOVER INTERFACES =================

async def discover_interfaces():
    print("🔍 Discovering interfaces...\n")

    descrs = snmp_walk(SWITCH_IP, "1.3.6.1.2.1.2.2.1.2")

    print(f"DEBUG: Raw SNMP results count = {len(descrs)}")

    interface_map = {}

    for oid, value in descrs:
        try:
            if_index = int(oid.split('.')[-1])
            name = value.replace('"', '').strip()
            interface_map[name] = if_index
        except:
            continue

    print("\n✅ Found Interfaces:")
    for name, idx in interface_map.items():
        print(f"{name} → {idx}")

    return interface_map

# ================= CSV LOGGING =================
def log_to_csv(timestamp, port, in_mbps, out_mbps, status):
    with open(CSV_FILE, "a", newline="") as f:
        csv.writer(f).writerow([
            timestamp,
            port,
            f"{in_mbps:.4f}",
            f"{out_mbps:.4f}",
            "up" if status else "down"
        ])


# ================= MAIN LOOP =================
async def poll_ports():
    print("\nStarting SNMP monitoring...\n")

    try:
        interfaces = await discover_interfaces()

        if not interfaces:
            print("❌ No interfaces found. Exiting.")
            return

        while True:
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"\n--- {ts} ---")

            for name, ifidx in interfaces.items():
                try:
                    if name not in status_up:
                        status_up[name] = None

                    in_oid = f"1.3.6.1.2.1.2.2.1.10.{ifidx}"
                    out_oid = f"1.3.6.1.2.1.2.2.1.16.{ifidx}"
                    status_oid = f"1.3.6.1.2.1.2.2.1.8.{ifidx}"

                    in_bytes = await snmp_get(SWITCH_IP, in_oid) or 0
                    out_bytes = await snmp_get(SWITCH_IP, out_oid) or 0
                    status_val = await snmp_get(SWITCH_IP, status_oid)

                    status = (status_val == 1)

                    # ===== SPEED CALC =====
                    if name in prev_in:
                        if in_bytes < prev_in[name]:
                            in_mbps = 0
                        else:
                            in_mbps = (in_bytes - prev_in[name]) * 8 / POLL_INTERVAL / 1_000_000

                        if out_bytes < prev_out[name]:
                            out_mbps = 0
                        else:
                            out_mbps = (out_bytes - prev_out[name]) * 8 / POLL_INTERVAL / 1_000_000
                    else:
                        in_mbps = 0
                        out_mbps = 0

                    prev_in[name] = in_bytes
                    prev_out[name] = out_bytes

                    # ===== ALERTS =====
                    if status_up[name] is not None and status != status_up[name]:
                        print(f"⚠️ ALERT: {name} changed to {'UP' if status else 'DOWN'}")

                    if in_mbps > 50:
                        print(f"🚨 HIGH TRAFFIC on {name}: {in_mbps:.2f} Mbps")

                    status_up[name] = status

                    print(f"{name}: In={in_mbps:.2f} Mbps Out={out_mbps:.2f} Mbps Status={'UP' if status else 'DOWN'}")

                    log_to_csv(ts, name, in_mbps, out_mbps, status)

                except Exception as e:
                    print(f"❌ Error on interface {name}: {e}")

            await asyncio.sleep(POLL_INTERVAL)

    except Exception:
        print("💥 CRASH:")
        traceback.print_exc()
        input("Press Enter to exit...")


# ================= RUN =================
asyncio.run(poll_ports())

input("Press Enter to exit...")