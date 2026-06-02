import time
from http.server import BaseHTTPRequestHandler, HTTPServer
import os
import sys
import json

from model.chassis_control import chassis_motor_run, chassis_motor_init
from model.rwd_control import motor_run, rwd_motor_init
from model.lift_motor_control import motor_forward, motor_backward, motor_stop, motor_init, read_limit_switch
from model import rwd_control, zhuanxiang_control

# 配置静态文件目录和服务器参数
STATIC_DIR = os.path.join(os.path.dirname(__file__), 'static')

HOST = '0.0.0.0'
PORT = 8080


# ======================
# HTTP请求处理器（仅处理请求转发）
# ======================
class MotorControlHandler(BaseHTTPRequestHandler):
    # 解析GET请求参数（如?motor=1&speed=1000）
    def parse_get_params(self):
        params = {}
        if '?' in self.path:
            path_parts = self.path.split('?')
            query = path_parts[1]
            for pair in query.split('&'):
                if '=' in pair:
                    key, value = pair.split('=')
                    params[key] = value
        return params

    # ✅【已修复】发送JSON响应，支持 data 参数
    def send_json_response(self, success, message, data=None):
        self.send_response(200)
        self.send_header('Content-type', 'application/json; charset=utf-8')
        self.end_headers()
        response = json.dumps({
            'success': success,
            'message': message,
            'data': data
        }, ensure_ascii=False)
        self.wfile.write(response.encode('utf-8'))

    # 处理静态文件请求（HTML/CSS/JS）
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

        if file_path.endswith('.html'):
            content_type = 'text/html; charset=utf-8'
        elif file_path.endswith('.css'):
            content_type = 'text/css'
        elif file_path.endswith('.js'):
            content_type = 'application/javascript'
        else:
            content_type = 'application/octet-stream'

        try:
            with open(file_path, 'rb') as f:
                self.send_response(200)
                self.send_header('Content-type', content_type)
                self.end_headers()
                self.wfile.write(f.read())
        except Exception as e:
            self.send_error(500, f"服务器错误：{str(e)}")

    # 处理GET请求
    def do_GET(self):
        params = self.parse_get_params()
        motor_id = params.get('motor')

        # ======================
        # 实时获取电机数据接口
        # ======================
        print(self.path)
        if self.path.startswith('/forward_1'):
            print(f"电机{motor_id}执行-正转上升")
            motor_stop(int(motor_id), 2)
            time.sleep(0.05)
            success, msg = motor_forward(int(motor_id))
            self.send_json_response(success, msg)

        elif self.path.startswith('/data'):
            self.send_json_response(True, "success", zhuanxiang_control.motor_data)
            return

        elif self.path.startswith('/backward_1'):
            print(f"电机{motor_id}执行-反转下降")
            motor_stop(int(motor_id), 1)
            success, msg = motor_backward(int(motor_id))
            self.send_json_response(success, msg)

        elif self.path.startswith('/forward_stop_1'):
            print("电机1执行-正转停止")
            success, msg = motor_stop(int(motor_id), 1)
            self.send_json_response(success, msg)

        elif self.path.startswith('/backward_stop_1'):
            print("电机1执行-反转停止")
            success, msg = motor_stop(int(motor_id), 2)
            self.send_json_response(success, msg)

        elif self.path.startswith('/backward_tongbu'):
            print("执行同步下降")
            motor_stop(1, 1)
            motor_stop(2, 1)
            motor_backward(1)
            motor_backward(2)
            self.send_json_response(True, "同步下降中")

        elif self.path.startswith('/read_state'):
            success, msg = read_limit_switch(int(motor_id))
            self.send_json_response(success, msg)

        elif self.path.startswith('/chassis_motor_run'):
            import urllib.parse
            parsed = urllib.parse.urlparse(self.path)
            params = urllib.parse.parse_qs(parsed.query)
            motor_id = int(params.get('id', [1])[0])
            speed = int(params.get('speed', [0])[0])
            direction = int(params.get('dir', [0])[0])
            success, msg = motor_run(motor_id=motor_id, speed=speed, direction=direction)
            self.send_json_response(success, msg)

        elif self.path.startswith('/dipan_motor_run'):
            import urllib.parse
            parsed = urllib.parse.urlparse(self.path)
            params = urllib.parse.parse_qs(parsed.query)
            motor_id = int(params.get('id', [1])[0])
            speed = int(params.get('speed', [0])[0])
            direction = int(params.get('dir', [0])[0])
            success, msg = chassis_motor_run(motor_id=motor_id, speed=speed, direction=direction)
            self.send_json_response(success, msg)

        elif self.path.startswith('/zhuanxiang_motor_run'):
            import urllib.parse
            parsed = urllib.parse.urlparse(self.path)
            params = urllib.parse.parse_qs(parsed.query)
            target_position = int(params.get('target_position', [0])[0])
            zhuanxiang_speed = int(params.get('zhuanxiang_speed', [1000])[0])
            zhuanxiang_control.send_motor_cmd(33, target_position, zhuanxiang_speed)
            self.send_json_response(True, "转向指令已发送")

        else:
            self.handle_static_file()


# ======================
# 主函数：启动服务器
# ======================
def main():
    server = HTTPServer((HOST, PORT), MotorControlHandler)
    print("=" * 30)
    print(f"服务器已启动：http://{HOST}:{PORT}")
    print(f"静态文件目录：{STATIC_DIR}")
    print("按 Ctrl+C 停止服务器")
    print("=" * 30)

    motor_init()  # 初始化前后升降双电机
    rwd_motor_init()  # 初始化后侧驱动电机
    chassis_motor_init()  # 初始化底盘电机

    zhuanxiang_control.zhuanxiang_motor_init()
    # zhuanxiang_control.start_receive()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n服务器正在停止...")
        server.server_close()
        sys.exit(0)


if __name__ == "__main__":
    main()