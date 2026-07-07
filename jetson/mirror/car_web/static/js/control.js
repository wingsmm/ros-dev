function callApi(url) {
    fetch(url, { method: 'GET' })
        .then(response => response.json())
        .then(data => { showResult(data.message, data.success ? 'success' : 'error'); })
        .catch(error => { showResult('请求失败：' + error, 'error'); });
}

// ====================== 前轮行走 ======================
// 统一控制（左右轮同时，左轮方向取反因为物理镜像安装）
function frontWalk(action) {
    const speed = document.getElementById('fw_speed').value;
    if (action === 'fwd') {
        callApi('/api/front_walk/run?id=1&speed=' + speed + '&dir=1');  // 右轮反转
        callApi('/api/front_walk/run?id=2&speed=' + speed + '&dir=0');  // 左轮正转（镜像）
    } else if (action === 'bwd') {
        callApi('/api/front_walk/run?id=1&speed=' + speed + '&dir=0');  // 右轮正转
        callApi('/api/front_walk/run?id=2&speed=' + speed + '&dir=1');  // 左轮反转（镜像）
    } else {
        callApi('/api/front_walk/stop?id=1');
        callApi('/api/front_walk/stop?id=2');
    }
}
// 单电机测试（motorId: 1=右轮, 2=左轮）
function frontWalkSingle(motorId, action) {
    const speed = document.getElementById('fw_speed').value;
    if (action === 'fwd') {
        callApi('/api/front_walk/run?id=' + motorId + '&speed=' + speed + '&dir=0');
    } else if (action === 'bwd') {
        callApi('/api/front_walk/run?id=' + motorId + '&speed=' + speed + '&dir=1');
    } else {
        callApi('/api/front_walk/stop?id=' + motorId);
    }
}

// ====================== 后轮驱动 ======================
function rearDrive(action) {
    const speed = document.getElementById('rw_speed').value;
    if (action === 'fwd') callApi('/api/rear_drive?dir=1&speed=' + speed);
    else if (action === 'bwd') callApi('/api/rear_drive?dir=0&speed=' + speed);
    else callApi('/api/rear_stop');
}

function rearWalk(motorId, action) {
    const speed = document.getElementById('rw_speed').value;
    if (action === 'fwd') callApi('/api/rear_walk/run?id=' + motorId + '&speed=' + speed + '&dir=0');
    else if (action === 'rev') callApi('/api/rear_walk/run?id=' + motorId + '&speed=' + speed + '&dir=1');
    else callApi('/api/rear_walk/run?id=' + motorId + '&speed=0&dir=0');
}

// ====================== 后侧升降 ======================
function liftHome() {
    callApi('/api/lift/home');
}
function liftMoveTo() {
    var pos = document.getElementById('lift_target').value;
    callApi('/api/lift/move_to?pos=' + pos);
}
function liftStop() {
    callApi('/api/lift/stop');
}
function liftStatus() {
    fetch('/api/lift/position', { method: 'GET' })
        .then(function(r) { return r.json(); })
        .then(function(d) {
            if (d.success && d.data) {
                document.getElementById('lift_position').textContent = d.data.position;
                document.getElementById('lift_homed').textContent = d.data.homed ? '已找零' : '未找零';
                var homedTag = document.getElementById('lift_homed');
                homedTag.className = d.data.homed ? 'tag tag-green' : 'tag tag-red';
            }
            showResult(d.message, d.success ? 'success' : 'error');
        })
        .catch(function(e) { showResult('读取位置失败: ' + e, 'error'); });
}
function liftReadLimits() {
    fetch('/api/lift/limits', { method: 'GET' })
        .then(function(r) { return r.json(); })
        .then(function(d) {
            if (d.success && d.data) {
                var sq1 = document.getElementById('lift_limit_sq2');
                if (d.data.sq2 === true) {
                    sq1.textContent = '触发';
                    sq1.className = 'tag tag-red';
                } else if (d.data.sq2 === false) {
                    sq1.textContent = '正常';
                    sq1.className = 'tag tag-green';
                } else {
                    sq1.textContent = '--';
                    sq1.className = 'tag tag-gray';
                }
            }
            showResult(d.message, d.success ? 'success' : 'error');
        })
        .catch(function(e) { showResult('读取限位失败: ' + e, 'error'); });
}

// ====================== 前侧扒手 ======================
function grabHome() {
    callApi('/api/grab/home');
}
function grabMoveTo() {
    var pos = document.getElementById('grab_target').value;
    callApi('/api/grab/move_to?pos=' + pos);
}
function grabStop() {
    callApi('/api/grab/stop');
}
function bothMoveTo() {
    var liftPos = document.getElementById('lift_target').value;
    var grabPos = document.getElementById('grab_target').value;
    var url = '/api/both/move_to?lift_pos=' + liftPos + '&grab_pos=' + grabPos;
    callApi(url);
}
function grabSpeedRun(speed) {
    if (speed === undefined) {
        speed = document.getElementById('grab_speed').value;
    }
    callApi('/api/grab/speed_run?speed=' + speed);
}
function liftSpeedRun(speed) {
    if (speed === undefined) {
        speed = document.getElementById('lift_speed').value;
    }
    callApi('/api/lift/speed_run?speed=' + speed);
}
function grabStatus() {
    fetch('/api/grab/position', { method: 'GET' })
        .then(function(r) { return r.json(); })
        .then(function(d) {
            if (d.success && d.data) {
                document.getElementById('grab_position').textContent = d.data.position;
                document.getElementById('grab_homed').textContent = d.data.homed ? '已找零' : '未找零';
                var homedTag = document.getElementById('grab_homed');
                homedTag.className = d.data.homed ? 'tag tag-green' : 'tag tag-red';
            }
            showResult(d.message, d.success ? 'success' : 'error');
        })
        .catch(function(e) { showResult('读取扒手位置失败: ' + e, 'error'); });
}
function grabReadLimits() {
    fetch('/api/grab/limits', { method: 'GET' })
        .then(function(r) { return r.json(); })
        .then(function(d) {
            if (d.success && d.data) {
                var sq1 = document.getElementById('grab_limit_sq1');
                var sq2 = document.getElementById('grab_limit_sq2');
                if (d.data.sq1 === true) {
                    sq1.textContent = '触发';
                    sq1.className = 'tag tag-red';
                } else if (d.data.sq1 === false) {
                    sq1.textContent = '正常';
                    sq1.className = 'tag tag-green';
                } else {
                    sq1.textContent = '--';
                    sq1.className = 'tag tag-gray';
                }
                if (d.data.sq2 === true) {
                    sq2.textContent = '触发';
                    sq2.className = 'tag tag-red';
                } else if (d.data.sq2 === false) {
                    sq2.textContent = '正常';
                    sq2.className = 'tag tag-green';
                } else {
                    sq2.textContent = '--';
                    sq2.className = 'tag tag-gray';
                }
            }
            showResult(d.message, d.success ? 'success' : 'error');
        })
        .catch(function(e) { showResult('读取扒手限位失败: ' + e, 'error'); });
}

// ====================== 转向控制 ======================
function steerRun(motorId, action) {
    var speed = document.getElementById('st_speed').value;
    if (action === 'fwd') {
        callApi('/api/steer/run?id=' + motorId + '&speed=' + speed + '&dir=0');
    } else if (action === 'rev') {
        callApi('/api/steer/run?id=' + motorId + '&speed=' + speed + '&dir=1');
    } else if (action === 'stop') {
        if (motorId === 0) {
            callApi('/api/steer/stop');
        } else {
            callApi('/api/steer/run?id=' + motorId + '&speed=0&dir=0');
        }
    }
}
function steerStop() {
    callApi('/api/steer/stop');
}
function steerToAngle() {
    var angle = document.getElementById('st_target_angle').value;
    var speed = document.getElementById('st_speed').value;
    callApi('/api/steer/to_angle?angle=' + angle + '&speed=' + speed);
}
function steerRelativeLeft() {
    var rel = parseFloat(document.getElementById('st_rel_angle').value) || 90;
    var speed = document.getElementById('st_speed').value;
    fetch('/api/steer/angle')
        .then(function(r) { return r.json(); })
        .then(function(d) {
            if (d.success && d.data) {
                var url = '/api/steer/to_angle?angle=' + (d.data.left_angle + rel)
                        + '&right_angle=' + (d.data.right_angle + rel)
                        + '&speed=' + speed;
                callApi(url);
            } else {
                showResult('读取当前角度失败', 'error');
            }
        })
        .catch(function(e) { showResult('读取角度失败: ' + e, 'error'); });
}
function steerRelativeRight() {
    var rel = parseFloat(document.getElementById('st_rel_angle').value) || 90;
    var speed = document.getElementById('st_speed').value;
    fetch('/api/steer/angle')
        .then(function(r) { return r.json(); })
        .then(function(d) {
            if (d.success && d.data) {
                var url = '/api/steer/to_angle?angle=' + (d.data.left_angle - rel)
                        + '&right_angle=' + (d.data.right_angle - rel)
                        + '&speed=' + speed;
                callApi(url);
            } else {
                showResult('读取当前角度失败', 'error');
            }
        })
        .catch(function(e) { showResult('读取角度失败: ' + e, 'error'); });
}
// ====================== 角度传感器读取 ======================
var _sensorTimer = null;

function readSensor() {
    fetch('/api/steer/angle', { method: 'GET' })
        .then(function(r) { return r.json(); })
        .then(function(d) {
            if (d.success && d.data) {
                document.getElementById('sen_left_voltage').textContent = d.data.left_voltage;
                document.getElementById('sen_left_angle').textContent = d.data.left_angle;
                document.getElementById('sen_right_voltage').textContent = d.data.right_voltage;
                document.getElementById('sen_right_angle').textContent = d.data.right_angle;
            }
            showResult(d.message, d.success ? 'success' : 'error');
        })
        .catch(function(e) { showResult('读取失败: ' + e, 'error'); });
    // 同时读取倾角
    fetch('/api/tilt/angle', { method: 'GET' })
        .then(function(r) { return r.json(); })
        .then(function(d) {
            if (d.success && d.data) {
                document.getElementById('tilt_angle').textContent = d.data.angle;
                document.getElementById('tilt_raw').textContent = d.data.raw;
            }
        })
        .catch(function() {});
}

function toggleAutoRead() {
    var btn = document.getElementById('btn_sensor_auto');
    if (_sensorTimer) {
        clearInterval(_sensorTimer);
        _sensorTimer = null;
        btn.textContent = '自动读取';
        btn.className = 'btn btn-sync';
    } else {
        readSensor();
        _sensorTimer = setInterval(readSensor, 500);
        btn.textContent = '停止读取';
        btn.className = 'btn btn-danger';
    }
}

function showResult(msg, type) {
    const div = document.getElementById('result');
    if (!div) return;
    div.textContent = msg;
    div.className = 'result show ' + type;
    clearTimeout(div._t);
    div._t = setTimeout(() => { div.className = 'result'; }, 3000);
}

// ====================== 水平自动调整 ======================
function startLeveling() {
    var ls = document.getElementById('level_lift_speed').value;
    var gs = document.getElementById('level_grab_speed').value;
    callApi('/api/leveling/start?lift_speed=' + ls + '&grab_speed=' + gs);
    document.getElementById('level_status').textContent = '运行中';
    document.getElementById('level_status').className = 'tag tag-green';
}
function stopLeveling() {
    callApi('/api/leveling/stop');
    document.getElementById('level_status').textContent = '停止';
    document.getElementById('level_status').className = 'tag tag-gray';
}

// 水平调整自动状态检测
var _levelTimer = null;
function checkLevelStatus() {
    fetch('/api/leveling/status', { method: 'GET' })
        .then(function(r) { return r.json(); })
        .then(function(d) {
            if (d.data && d.data.running) {
                document.getElementById('level_status').textContent = '运行中';
                document.getElementById('level_status').className = 'tag tag-green';
            } else {
                document.getElementById('level_status').textContent = '停止';
                document.getElementById('level_status').className = 'tag tag-gray';
            }
        })
        .catch(function() {});
}
setInterval(checkLevelStatus, 1000);
