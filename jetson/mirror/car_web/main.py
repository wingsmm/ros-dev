import json
import os
import sys
import urllib.parse
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

# 导入各模块（TODO：后续在 model 中填入实际控制逻辑后取消注释）
from model.rwd_control import rwd_motor_init, motor_run, rear_drive, rear_stop
from model.rear_lift import rear_lift_init, rear_lift_stop, lift_home, lift_move_to, lift_get_position, lift_is_homed, \
    read_limits as lift_read_limits, lift_speed_run
from model.front_grab import grab_motor_init, grab_stop, grab_home, grab_move_to, grab_get_position, grab_is_homed, \
    read_limits as grab_read_limits, grab_speed_run
from model.steer_control import steer_motor_init, steer_motor_run, steer_stop, steer_to_angle, get_steer_angle, \
    get_steer_voltage, angle_sensor_init, get_sensor_data
from model.front_walk import front_walk_init, front_walk_run, front_walk_stop
from model.tilt_sensor import tilt_sensor_init, read_x_angle
from model.level_control import start_leveling, stop_leveling, is_leveling

STATIC_DIR = os.path.join(os.path.dirname(__file__), 'static')
HOST = '0.0.0.0'
PORT = 8080


class CarControlHandler(BaseHTTPRequestHandler):

    def _qp(self, key, default='0'):
        """快捷获取当前请求的查询参数"""
        if not hasattr(self, '_params') or self._params is None:
            parsed = urllib.parse.urlparse(self.path)
            self._params = urllib.parse.parse_qs(parsed.query)
        return self._params.get(key, [default])[0]

    def send_json_response(self, success, message, data=None):
        self.send_response(200)
        self.send_header('Content-type', 'application/json; charset=utf-8')
        self.end_headers()
        response = json.dumps({'success': success, 'message': message, 'data': data}, ensure_ascii=False)
        self.wfile.write(response.encode('utf-8'))

    def handle_static_file(self):
        if self.path == '/':
            file_path = os.path.join(STATIC_DIR, 'index.html')
        elif self.path == '/ctl':
            file_path = os.path.join(STATIC_DIR, 'control.html')
        else:
            file_path = os.path.join(STATIC_DIR, self.path.lstrip('/'))
        if not os.path.exists(file_path):
            self.send_error(404)
            return
        ct = ('text/html; charset=utf-8' if file_path.endswith('.html') else
              'text/css' if file_path.endswith('.css') else
              'application/javascript' if file_path.endswith('.js') else
              'application/octet-stream')
        try:
            with open(file_path, 'rb') as f:
                self.send_response(200)
                self.send_header('Content-type', ct)
                self.end_headers()
                self.wfile.write(f.read())
        except Exception as e:
            self.send_error(500, f"服务器错误：{str(e)}")

    def do_GET(self):
        print(f"[请求] {self.path}")
        self._params = None

        path = self.path

        # ====================== 前侧扒手（升降电机）======================
        if path.startswith('/api/grab/stop'):
            self.send_json_response(*grab_stop())
        elif path.startswith('/api/grab/home'):
            to = int(self._qp('timeout', '10'))
            self.send_json_response(*grab_home(to))
        elif path.startswith('/api/grab/move_to'):
            target = int(self._qp('pos', '0'))
            spd = int(self._qp('speed', '50'))
            self.send_json_response(*grab_move_to(target, spd))
        elif path.startswith('/api/grab/position'):
            data = {"position": grab_get_position(), "homed": grab_is_homed()}
            self.send_json_response(True, f"当前位置={data['position']}", data)
        elif path.startswith('/api/grab/limits'):
            sq1, sq2, raw = grab_read_limits()
            data = {"sq1": sq1, "sq2": sq2, "raw": raw}
            self.send_json_response(True, f"限位 SQ1={sq1} SQ2={sq2}", data)

        # ====================== 前侧扒手速度模式 ======================
        elif path.startswith('/api/grab/speed_run'):
            sp = int(self._qp('speed', '0'))
            self.send_json_response(*grab_speed_run(sp))

        # ====================== 前后同时移动 ======================
        elif path.startswith('/api/both/move_to'):
            lift_pos = int(self._qp('lift_pos', '0'))
            grab_pos = int(self._qp('grab_pos', '0'))
            lift_spd = int(self._qp('lift_speed', '60'))
            grab_spd = int(self._qp('grab_speed', '60'))
            r1, m1 = lift_move_to(lift_pos, lift_spd)
            r2, m2 = grab_move_to(grab_pos, grab_spd)
            ok = r1 and r2
            self.send_json_response(ok, f"升降: {m1}, 扒手: {m2}")

        # ====================== 前轮行走 ======================
        elif path.startswith('/api/front_walk/run'):
            mid = int(self._qp('id', '1'))
            sp = int(self._qp('speed', '50'))
            dr = int(self._qp('dir', '0'))
            self.send_json_response(*front_walk_run(mid, sp, dr))
        elif path.startswith('/api/front_walk/stop'):
            mid = int(self._qp('id', '1'))
            self.send_json_response(*front_walk_stop(mid))

        # ====================== 后轮驱动 ======================
        elif path.startswith('/api/rear_drive'):
            dr = int(self._qp('dir', '1'))  # 1=前进, 0=后退
            sp = int(self._qp('speed', '50'))
            self.send_json_response(*rear_drive(dr, sp))
        elif path.startswith('/api/rear_stop'):
            self.send_json_response(*rear_stop())
        elif path.startswith('/api/rear_walk/run'):
            mid = int(self._qp('id', '1'))
            sp = int(self._qp('speed', '50'))
            dr = int(self._qp('dir', '0'))
            self.send_json_response(*motor_run(mid, sp, dr))

        elif path.startswith('/api/lift/speed_run'):
            sp = int(self._qp('speed', '0'))
            self.send_json_response(*lift_speed_run(sp))

        # ====================== 倾角传感器 ======================
        elif path.startswith('/api/tilt/angle'):
            angle, raw = read_x_angle()
            if angle is not None:
                self.send_json_response(True, f"X轴倾角: {angle:.2f}°", {"angle": angle, "raw": raw})
            else:
                self.send_json_response(False, "读取失败")

        # ====================== 水平自动调整 ======================
        elif path.startswith('/api/leveling/start'):
            ls = int(self._qp('lift_speed', '300'))
            gs = int(self._qp('grab_speed', '300'))
            self.send_json_response(*start_leveling(ls, gs))
        elif path.startswith('/api/leveling/stop'):
            self.send_json_response(*stop_leveling())
        elif path.startswith('/api/leveling/status'):
            self.send_json_response(is_leveling(), "", {"running": is_leveling()})

        # ====================== 后侧升降 ======================
        elif path.startswith('/api/lift/home'):
            to = int(self._qp('timeout', '10'))
            self.send_json_response(*lift_home(to))
        elif path.startswith('/api/lift/move_to'):
            target = int(self._qp('pos', '0'))
            spd = int(self._qp('speed', '50'))
            self.send_json_response(*lift_move_to(target, spd))
        elif path.startswith('/api/lift/position'):
            data = {"position": lift_get_position(), "homed": lift_is_homed()}
            self.send_json_response(True, f"当前位置={data['position']}", data)
        elif path.startswith('/api/lift/stop'):
            self.send_json_response(*rear_lift_stop())
        elif path.startswith('/api/lift/limits'):
            sq1, sq2, raw = lift_read_limits()
            data = {"sq1": sq1, "sq2": sq2, "raw": raw}
            self.send_json_response(True, f"限位 SQ1={sq1}", data)

        # ====================== 转向控制 ======================
        elif path.startswith('/api/steer/run'):
            mid = int(self._qp('id', '1'))
            sp = int(self._qp('speed', '50'))
            dr = int(self._qp('dir', '0'))
            self.send_json_response(*steer_motor_run(mid, sp, dr))
        elif path.startswith('/api/steer/to_angle'):
            left_target = float(self._qp('angle', '0'))
            right_str = self._qp('right_angle', '')
            right_target = float(right_str) if right_str else None
            spd = int(self._qp('speed', '50'))
            self.send_json_response(*steer_to_angle(left_target, spd, right_target=right_target))
        elif path.startswith('/api/steer/stop'):
            self.send_json_response(*steer_stop())

        # ====================== 数据接口 ======================
        elif path == '/api/steer/angle':
            data = get_sensor_data()
            self.send_json_response(True, f"左={data['left_angle']}° 右={data['right_angle']}°", data)
        elif path == '/api/status':
            self.send_json_response(True, "系统状态", {
                "online": True, "mode": "idle"
            })

        # ====================== 爬楼梯复合流程 ======================
        elif path.startswith('/api/stair/climb'):
            # TODO: 爬楼梯完整流程
            # 1. 前侧扒手下降（扒住楼梯）
            # 2. 后侧升降升起（抬车尾）
            # 3. 前轮+后轮同步前进（推上台阶）
            # 4. 后侧升降落下
            # 5. 前侧扒手上升（收回上限位）
            self.send_json_response(True, "[占位] 爬楼梯流程")
        elif path.startswith('/api/stair/stop'):
            self.send_json_response(True, "[占位] 紧急停止所有电机")

        else:
            self.handle_static_file()


def main():
    server = HTTPServer((HOST, PORT), CarControlHandler)
    print("=" * 50)
    print(f"  智能小车控制系统")
    print(f"  HTTP: http://{HOST}:{PORT}")
    print(f"  首页: http://localhost:{PORT}/")
    print(f"  控制: http://localhost:{PORT}/ctl")
    print(f"  按 Ctrl+C 停止服务器")
    print("=" * 50)

    # ========== 初始化串口 ==========
    rwd_motor_init()  # COM13  后轮驱动
    steer_motor_init()  # 复用COM13  转向电机（共用后轮串口）
    rear_lift_init()  # COM10  后侧升降（串口宿主）
    grab_motor_init()  # 复用COM10  前侧扒手（共用升降串口）
    front_walk_init()  # COM12  前轮行走
    angle_sensor_init()  # COM11  角度传感器
    tilt_sensor_init()  # COM14  倾角传感器

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n服务器正在停止...")
        server.server_close()
        sys.exit(0)


if __name__ == "__main__":
    main()
