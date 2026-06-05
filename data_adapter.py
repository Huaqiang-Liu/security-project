import json
import os
import sys
import pandas as pd
from datetime import datetime as dt
import pytz
import yaml

# Add AlertBERT to path so we can import its modules
sys.path.append(os.path.abspath('AlertBERT'))
from abbrvs import get_short
from attacktimes import get_phase

# Mapping from our labels.csv to AlertBERT expected labels
LABEL_MAP = {
    "service_scans": "service_scan",
    "dirb": "dirb",
    "wpscan": "wpscan",
    "webshell": "webshell_cmd",
    "cracking": "crack_passwords",
    "privilege_escalation": "escalated_sudo_command",
    "dnsteal": "dnsteal",
    "network_scans": "-",  # AlertBERT scripts didn't build attacks for these in augment configs
    "reverse_shell": "-",
    "service_stop": "-"
}

scenarios = [
    "fox", "harrison", "russellmitchell", "santos", 
    "shaw", "wardbeck", "wheeler", "wilson"
]

def get_time(j, ids):
    if ids == "a":
        return float(j["LogData"]["DetectionTimestamp"][-1])
    else:
        return float(
            dt.strptime(j["@timestamp"], "%Y-%m-%dT%H:%M:%S.%fZ")
            .replace(tzinfo=pytz.utc)
            .timestamp()
        )

def main():
    print("Loading labels.csv...")
    labels_df = pd.read_csv("data/ait_ads/labels.csv")
    
    os.makedirs("AlertBERT/alerts_csv", exist_ok=True)
    os.makedirs("AlertBERT/alerts_json", exist_ok=True)

    for scenario in scenarios:
        print(f"Adapting data for {scenario}...")
        
        # Load server config for IP mapping
        with open(f"AlertBERT/server_configs/{scenario}.yaml") as f:
            server_config = yaml.safe_load(f)
        ips = {v["default_ipv4_address"]: k for k, v in server_config.items()}
        
        # Symlink data so unite_alerts_labels.py finds it
        for system in ["aminer", "wazuh"]:
            src = os.path.abspath(f"data/ait_ads/{scenario}_{system}.json")
            dst = os.path.abspath(f"AlertBERT/alerts_json/{scenario}_{system}.json")
            if not os.path.exists(dst):
                os.symlink(src, dst)
                
        intervals = labels_df[labels_df["scenario"] == scenario]
        
        with open(f"AlertBERT/alerts_csv/{scenario}_alerts.csv", "w") as out:
            out.write("time,name,ip,host,short,time_label,event_label\n")
            
            for system in ["wazuh", "aminer"]:
                with open(f"AlertBERT/alerts_json/{scenario}_{system}.json") as f:
                    for line in f:
                        j = json.loads(line)
                        time_val = get_time(j, system[0])
                        
                        if system == "wazuh":
                            desc = j["rule"]["description"]
                            if not desc.startswith("Suricata: "):
                                desc = "Wazuh: " + desc
                            ip = j["agent"]["ip"]
                            name = desc
                        else:
                            name = j["AnalysisComponent"]["AnalysisComponentName"]
                            ip = j["AMiner"]["ID"]
                            desc = name
                            
                        short = get_short(desc)
                        host = ips.get(ip, "unknown")
                        time_label = get_phase(scenario, time_val)
                        if time_label.startswith("false_positive"):
                            time_label = "false_positive"
                            
                        # Assign event_label based on time intervals
                        event_label = "-"
                        for _, row in intervals.iterrows():
                            if row["start"] <= time_val <= row["end"]:
                                mapped = LABEL_MAP.get(row["attack"], None)
                                if mapped and mapped != "-":
                                    event_label = mapped
                                    break
                                
                        out.write(f"{int(time_val)},{name},{ip},{host},{short},{time_label},{event_label}\n")
                        
    print("Data adaptation complete! Ready for unite_alerts_labels.py")

if __name__ == "__main__":
    main()
