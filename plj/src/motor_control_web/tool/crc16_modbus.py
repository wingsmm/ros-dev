import struct

# ---------------------- CRC16校验码计算函数（Modbus专用） ----------------------
def crc16_modbus(data):
    """
    计算Modbus RTU的CRC16校验码
    :param data: 待校验的字节列表/字节串
    :return: 2字节的校验码（低位在前，高位在后）
    """
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x0001:
                crc >>= 1
                crc ^= 0xA001
            else:
                crc >>= 1
    # 转换为低位在前、高位在后的字节格式
    return struct.pack('<H', crc)
