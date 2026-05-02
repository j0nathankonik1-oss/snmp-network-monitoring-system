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

*(Add screenshots here)*

- Live Interface Monitoring  
- Network Map View  
- Alert Center  
- Traffic Graphs  

---

## ⚙️ Installation

```bash
pip install streamlit pandas requests streamlit-autorefresh