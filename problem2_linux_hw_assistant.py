import json
import platform
import re
import shutil
import subprocess

# 1. Strict allow-list: Only these read-only Linux commands can ever run
ALLOWED_COMMANDS = {
    "cpu": ["lscpu"],
    "ram": ["free", "-b"],
    "ram_slots": ["dmidecode", "-t", "memory"],
    "storage": ["lsblk", "-J", "-o", "NAME,SIZE,TYPE,ROTA,TRAN,MODEL"],
    "gpu": ["lspci"],
}


# 2. Safely run allowed command (shell=False blocks any command injection)
def run_system_tool(tool_key):
    if tool_key not in ALLOWED_COMMANDS:
        return {"error": "Command not allowed for safety reasons."}

    # If running on Windows/Mac for testing, return realistic Linux sample data
    if platform.system() != "Linux":
        return get_sample_linux_data(tool_key)

    cmd = ALLOWED_COMMANDS[tool_key]
    if shutil.which(cmd[0]) is None:
        return {"error": f"{cmd[0]} is not installed on this Linux distro."}

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5, shell=False)
        if result.returncode != 0:
            # Fallback if dmidecode needs sudo/root permission
            if tool_key == "ram_slots":
                return read_proc_meminfo()
            return {"error": "Permission denied or command failed."}
        return parse_tool_output(tool_key, result.stdout)
    except Exception as e:
        return {"error": str(e)}


# 3. Non-root fallback when dmidecode cannot run without sudo
def read_proc_meminfo():
    try:
        with open("/proc/meminfo", "r") as f:
            text = f.read()
        match = re.search(r"MemTotal:\s+(\d+)\s+kB", text)
        ram_gb = round(int(match.group(1)) / (1024 * 1024), 2) if match else "Unknown"
        return {
            "total_ram_gb": ram_gb,
            "slots_info": "Unavailable (needs sudo/root for dmidecode)",
        }
    except Exception:
        return {"error": "Could not read /proc/meminfo"}


# 4. Clean and normalize raw terminal output into structured JSON
def parse_tool_output(tool_key, raw_text):
    if tool_key == "cpu":
        data = {}
        for line in raw_text.splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                if k.strip() in ["Model name", "CPU(s)", "Architecture"]:
                    data[k.strip()] = v.strip()
        return data

    elif tool_key == "ram":
        lines = raw_text.splitlines()
        if len(lines) >= 2:
            parts = lines[1].split()
            return {"total_ram_gb": round(int(parts[1]) / (1024 ** 3), 2)}

    elif tool_key == "ram_slots":
        max_match = re.search(r"Maximum Capacity:\s*(.+)", raw_text)
        sizes = re.findall(r"^\s*Size:\s*(.+)$", raw_text, flags=re.MULTILINE)
        installed = [s.strip() for s in sizes if "No Module Installed" not in s]
        return {
            "installed_sticks": installed,
            "used_slots": len(installed),
            "total_slots": len(sizes),
            "free_slots": len(sizes) - len(installed),
            "max_capacity": max_match.group(1).strip() if max_match else "Unknown",
        }

    elif tool_key == "storage":
        parsed = json.loads(raw_text)
        disks = []
        for dev in parsed.get("blockdevices", []):
            if dev.get("type") == "disk":
                is_nvme = dev.get("tran") == "nvme" or "nvme" in dev.get("name", "")
                disks.append({
                    "name": dev.get("name"),
                    "size": dev.get("size"),
                    "model": (dev.get("model") or "").strip(),
                    "is_nvme": is_nvme,
                })
        return {"disks": disks}

    elif tool_key == "gpu":
        gpus = [line for line in raw_text.splitlines() if "VGA" in line or "3D controller" in line]
        return {"gpus": gpus}

    return {"raw": raw_text}


def get_sample_linux_data(tool_key):
    samples = {
        "cpu": {"Model name": "12th Gen Intel Core i5-1240P", "CPU(s)": "12", "Architecture": "x86_64"},
        "ram": {"total_ram_gb": 16.0},
        "ram_slots": {
            "installed_sticks": ["16 GB"],
            "used_slots": 1,
            "total_slots": 2,
            "free_slots": 1,
            "max_capacity": "64 GB",
        },
        "storage": {"disks": [{"name": "nvme0n1", "size": "512G", "model": "Samsung SSD", "is_nvme": True}]},
        "gpu": {"gpus": ["VGA compatible controller: Intel Alder Lake-P Integrated Graphics"]},
    }
    return samples[tool_key]


# 5. Decide which tool to call based on user question + follow-up history
def choose_tools(question, last_topic):
    q = question.lower()
    if any(w in q for w in ["ram", "memory", "upgrade", "slot"]):
        return ["ram", "ram_slots"], "ram"
    if any(w in q for w in ["ssd", "nvme", "disk", "storage", "drive"]):
        return ["storage"], "storage"
    if any(w in q for w in ["cpu", "processor", "core"]):
        return ["cpu"], "cpu"
    if any(w in q for w in ["gpu", "graphics", "video"]):
        return ["gpu"], "gpu"

    # Handle follow-ups like "can I add more?"
    if last_topic == "ram" and any(w in q for w in ["add", "more", "upgrade", "slots"]):
        return ["ram_slots"], "ram"

    return [], last_topic


# 6. Build accurate plain-English answer strictly from JSON data (no guessing)
def answer_question(question, last_topic):
    tools, new_topic = choose_tools(question, last_topic)
    if not tools:
        return "I don't know — I only have safe tools to check CPU, RAM, Storage/NVMe, and GPU.", new_topic

    results = {t: run_system_tool(t) for t in tools}

    if "ram_slots" in results:
        info = results["ram_slots"]
        if "total_slots" in info:
            ans = (
                f"You have {', '.join(info['installed_sticks'])} installed in "
                f"{info['used_slots']} of {info['total_slots']} slots ({info['free_slots']} free). "
                f"Your motherboard supports up to {info['max_capacity']}."
            )
            return ans, new_topic
        else:
            ram_gb = results.get("ram", {}).get("total_ram_gb", "Unknown")
            return f"You have {ram_gb} GB RAM. {info.get('slots_info', '')}", new_topic

    if "storage" in results:
        disks = results["storage"].get("disks", [])
        lines = [f"{d['name']} ({d['size']}, NVMe={d['is_nvme']})" for d in disks]
        return "Storage drives found: " + ", ".join(lines), new_topic

    if "cpu" in results:
        c = results["cpu"]
        return f"CPU: {c.get('Model name')} ({c.get('CPU(s)')} cores, {c.get('Architecture')}).", new_topic

    if "gpu" in results:
        return f"GPU: {', '.join(results['gpu'].get('gpus', ['None found']))}", new_topic

    return "I could not determine that from the system data.", new_topic


if __name__ == "__main__":
    print("=== Linux Hardware Q&A Assistant (type 'exit' to quit) ===")
    topic = None
    while True:
        q = input("\nAsk about your hardware: ")
        if q.lower() in ["exit", "quit"]:
            break
        reply, topic = answer_question(q, topic)
        print("Assistant:", reply)
