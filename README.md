# 🖥️ SNMP Network Monitoring System

A real-time network monitoring dashboard built using Python and Streamlit that tracks switch performance, detects outages, and provides alerting with historical data logging.

---

## 🚀 Overview

This project simulates a lightweight enterprise monitoring system similar to tools like SolarWinds or PRTG. It uses SNMP to collect network data, processes it in real-time, and displays it in a web-based dashboard.

---

## ⚙️ Features

- 📡 Real-time SNMP monitoring of network devices  
- 📊 Traffic analysis (Inbound/Outbound Mbps per interface)  
- 🚨 Alerting system (port down + high traffic detection)  
- 🔔 Discord webhook notifications  
- 🗄️ SQLite database for historical data tracking  
- 🌐 Multi-switch monitoring support  
- 🔋 UPS battery monitoring and alerts  
- 🗺️ Network map visualization (NOC-style UI)  
- 🔥 Top talkers (highest bandwidth usage)  

---

## 🧰 Tech Stack

- **Python**
- **Streamlit** (Dashboard UI)
- **SNMP (v2c)** (Network data collection)
- **SQLite** (Data storage)
- **Pandas** (Data processing)
- **Requests** (Alerts / API calls)

---

## 🏗️ How It Works

1. SNMP queries are sent to network devices using `snmpwalk`
2. Data is parsed and converted into readable metrics (Mbps)
3. Traffic is calculated using byte counters over time
4. Results are displayed in a live dashboard
5. Alerts are triggered when:
   - A port goes DOWN
   - Traffic exceeds a threshold
6. All data is stored in SQLite for historical tracking

---

## 📸 Dashboard Preview

<img width="1874" height="524" alt="Screenshot 2026-04-28 165636" src="https://github.com/user-attachments/assets/68fa3314-8d5f-4689-9cd3-a9eaaf608fa1" />
<img width="1880" height="893" alt="Screenshot 2026-04-28 165659" src="https://github.com/user-attachments/assets/11cb7a58-2972-44bb-bb30-71cfc7859339" />
<img width="1887" height="897" alt="Screenshot 2026-04-28 165714" src="https://github.com/user-attachments/assets/bdc9bb1e-e12b-4965-b57c-fefbba203852" />
<img width="1860" height="864" alt="Screenshot 2026-04-28 165737" src="https://github.com/user-attachments/assets/531c0f75-1ce5-4138-b9c8-f33f19b20b5d" />
<img width="1890" height="701" alt="Screenshot 2026-04-28 165756" src="https://github.com/user-attachments/assets/7a07d194-434f-4997-9b5d-01bd64487fdc" />
<img width="1864" height="878" alt="Screenshot 2026-04-28 165810" src="https://github.com/user-attachments/assets/105b98e5-1d7e-470d-a2da-bfbcb082f82f" />
<img width="1880" height="884" alt="Screenshot 2026-04-28 165822" src="https://github.com/user-attachments/assets/0297eab6-da60-49f0-a2f9-1a46855e054a" />


- Live Interface Monitoring  
- Network Map View  
- Alert Center  
- Traffic Graphs  

---

## ⚙️ Installation

```bash
pip install streamlit pandas requests streamlit-autorefresh
