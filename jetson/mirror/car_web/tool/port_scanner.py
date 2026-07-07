"""
串口自动探测与识别工具

扫描所有可用串口，通过Modbus探测指令识别各设备对应的串口，
输出端口映射结果用于配置 mon_config.json。

探测策略：
  1. 角度传感器  → Modbus 0x04 读输入寄存器（唯一使用0x04的设备）
  2. AQMD2403NS  → Modbus 0x03 读限位寄存器 0x0018（升降/扒手驱动器）
  3. FT-DM-01B   → Modbus 0x03 读方向寄存器 0x0004（前后轮驱动器）

用法：
  python tool/port_scanner.py            # 扫描并打印结果
  python tool/port_scanner.py --json     # 输出JSON格式
"""
import sys
import os
import time
import json

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import serial
    import serial.tools.list_ports
except ImportError:
    print("错误: 需要安装 pyserial: pip install pyserial")
    sys.exit(1)

from tool.crc16_modbus import crc16_modbus


# ==================== 探测指令构造 ====================

def _make_cmd(addr, func, reg, count=1):
    """构造 Modbus 指令字节"""
    cmd = [addr, func, (reg >> 8) & 0xFF, reg & 0xFF, 0x00, count]
    return bytes(cmd) + crc16_modbus(cmd)


def _probe(port, cmd_bytes, baud=9600, timeout=0.3):
    """在串口发送指令并返回响应，失败返回 None"""
    try:
        with serial.Serial(str(port), baud, timeout=timeout) as ser:
            time.sleep(0.15)  # 等待串口稳定
            ser.flushInput()
            ser.flushOutput()
            ser.write(cmd_bytes)
            time.sleep(0.08)
            resp = ser.read(256)
            return resp if resp else None
    except Exception:
        return None


# ==================== 设备识别函数 ====================

def probe_angle_sensor(port):
    """探测是否为角度传感器（Modbus 0x04 读输入寄存器）"""
    resp = _probe(port, _make_cmd(0x01, 0x04, 0x0000, 1))
    if resp and len(resp) >= 5 and resp[0] == 0x01 and resp[1] == 0x04:
        ch1 = (resp[3] << 8) | resp[4] if len(resp) >= 5 else 0
        return True, {"function": "0x04", "ch1_raw": ch1, "response": resp.hex(' ').upper()}
    return False, None


def probe_aqmd(port, addr):
    """
    探测是否为 AQMD2403NS-M2B 驱动器
    Modbus 0x03 读限位寄存器 0x0018（升降/扒手）
    """
    resp = _probe(port, _make_cmd(addr, 0x03, 0x0018, 2))
    if resp and len(resp) >= 7 and resp[0] == addr and resp[1] == 0x03:
        return True, {"response": resp.hex(' ').upper()}
    return False, None


def probe_ftdm(port, addr):
    """
    探测是否为 FT-DM-01B 驱动器
    Modbus 0x03 读方向寄存器 0x0004（后轮驱动/转向/前轮行走）
    """
    resp = _probe(port, _make_cmd(addr, 0x03, 0x0004, 2))
    if resp and len(resp) >= 7 and resp[0] == addr and resp[1] == 0x03:
        return True, {"response": resp.hex(' ').upper()}
    return False, None


# ==================== 主扫描逻辑 ====================

def list_all_ports():
    """列出所有可用串口"""
    ports = serial.tools.list_ports.comports()
    return sorted([p.device for p in ports], key=lambda x: x.lower())


def scan():
    """扫描所有串口，返回设备映射表"""
    ports = list_all_ports()
    result = {
        "angle_sensor": None,    # 角度传感器串口
        "lift_grab": None,       # 后侧升降+前侧扒手（共用）
        "rear_steer": None,      # 后轮驱动+转向（共用）
        "front_walk": None,      # 前轮行走
        "unidentified": [],      # 未识别的串口
    }

    for port in ports:
        # ---- 1. 探测角度传感器 ----
        ok, info = probe_angle_sensor(port)
        if ok:
            result["angle_sensor"] = {"port": port, "info": info}
            continue

        # ---- 2. 探测 AQMD2403（升降/扒手） ----
        addrs_found = []
        for addr in [1, 2]:
            ok, _ = probe_aqmd(port, addr)
            if ok:
                addrs_found.append(addr)
        if addrs_found:
            device_names = {1: "后侧升降", 2: "前侧扒手"}
            names = [f"addr={a}({device_names[a]})" for a in addrs_found]
            result["lift_grab"] = {"port": port, "devices": names}
            continue

        # ---- 3. 探测 FT-DM-01B（后轮驱动/转向/前轮行走） ----
        addrs_found = []
        for addr in [1, 2]:
            ok, _ = probe_ftdm(port, addr)
            if ok:
                addrs_found.append(addr)
        if addrs_found:
            # 无法区分是后轮+转向 还是前轮行走，暂标记为 ftdm
            result.setdefault("ftdm_ports", []).append({"port": port, "addresses": addrs_found})
            continue

        # ---- 4. 未识别 ----
        result["unidentified"].append(port)

    return result


# ==================== 输出格式化 ====================

def print_result(scan_result):
    """打印人类可读的扫描结果"""
    print("=" * 60)
    print("  串口设备自动探测结果")
    print("=" * 60)

    if scan_result["angle_sensor"]:
        p = scan_result["angle_sensor"]
        print(f"\n  [角度传感器]   → {p['port']}")
    else:
        print(f"\n  [角度传感器]   → 未找到")

    if scan_result["lift_grab"]:
        p = scan_result["lift_grab"]
        print(f"  [升降+扒手]    → {p['port']}  ({', '.join(p['devices'])})")
    else:
        print(f"  [升降+扒手]    → 未找到")

    ftdm_ports = scan_result.get("ftdm_ports", [])
    for i, fp in enumerate(ftdm_ports):
        label = "后轮驱动+转向/前轮行走"
        print(f"  [{label}] → {fp['port']}  (addr={', '.join(map(str, fp['addresses']))})")

    if scan_result["unidentified"]:
        print(f"\n  [未识别]       → {', '.join(scan_result['unidentified'])}")

    print()
    print("--- 建议的 mon_config.json 映射 ---")
    print('{')
    if scan_result["angle_sensor"]:
        print(f'    "angle_sensor":  "{scan_result["angle_sensor"]["port"]}",')
    if scan_result["lift_grab"]:
        print(f'    "lift_grab":      "{scan_result["lift_grab"]["port"]}",')
    for i, fp in enumerate(ftdm_ports):
        key = "rear_steer" if i == 0 else "front_walk"
        print(f'    "{key}":           "{fp["port"]}",')
    print('}')


def json_result(scan_result):
    """输出 JSON 格式"""
    output = {}
    if scan_result["angle_sensor"]:
        output["angle_sensor"] = scan_result["angle_sensor"]["port"]
    if scan_result["lift_grab"]:
        output["lift_grab"] = scan_result["lift_grab"]["port"]
    for i, fp in enumerate(scan_result.get("ftdm_ports", [])):
        if i == 0:
            output["rear_steer"] = fp["port"]
        elif i == 1:
            output["front_walk"] = fp["port"]
    if scan_result["unidentified"]:
        output["unidentified"] = scan_result["unidentified"]
    print(json.dumps(output, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    use_json = "--json" in sys.argv
    result = scan()
    if use_json:
        json_result(result)
    else:
        print_result(result)
