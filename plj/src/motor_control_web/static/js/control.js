// 控制电机核心函数（发送AJAX请求）
function controlMotor(event, action) {
    const btn = event.target;
    const motorId = btn.value;

    fetch(`/${action}?motor=${motorId}`, {
        method: 'GET',
        headers: { 'Content-Type': 'application/json' }
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showResult(data.message, 'success');
        } else {
            showResult(data.message, 'error');
        }
    })
    .catch(error => {
        showResult(`请求失败：${error}`, 'error');
    });
}

// 显示结果提示
function showResult(msg, type) {
    const resultDiv = document.getElementById('result');
    resultDiv.textContent = msg;
    resultDiv.className = `result ${type}`;

    setTimeout(() => {
        resultDiv.className = 'result';
    }, 3000);
}

// ====================== 后轮驱动电机控制 ======================
function controlChassisMotor() {
    const id = document.getElementById("slaveId").value;
    const speed = document.getElementById("speed").value;
    const dir = document.getElementById("direction").value;

    fetch(`/chassis_motor_run?id=${id}&speed=${speed}&dir=${dir}`, {
        method: 'GET',
        headers: { 'Content-Type': 'application/json' }
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showResult(data.message, 'success');
        } else {
            showResult(data.message, 'error');
        }
    })
    .catch(error => {
        showResult(`请求失败：${error}`, 'error');
    });
}

function stopChassisMotor() {
    const id = document.getElementById("slaveId").value;
    fetch(`/chassis_motor_run?id=${id}&speed=0&dir=0`, {
        method: 'GET',
        headers: { 'Content-Type': 'application/json' }
    })
    .then(res => res.json())
    .then(data => {
        showResult("底盘电机已停止", "success");
    }).catch(err => {
        showResult("停止失败", "error");
    });
}

// ====================== 同步控制 ======================
function syncForward() {
    const speed = document.getElementById("speed").value;
    runMotor(1, speed, 0);
    runMotor(2, speed, 0);
    showResult("电机1+2 同步正转", "success");
}

function syncBackward() {
    const speed = document.getElementById("speed").value;
    runMotor(1, speed, 1);
    runMotor(2, speed, 1);
    showResult("电机1+2 同步反转", "success");
}

function syncStop() {
    runMotor(1, 0, 0);
    runMotor(2, 0, 0);
    showResult("电机1+2 已同步停止", "success");
}

function turn_left() {
    const speed = document.getElementById("speed").value;
    runMotor(1, speed, 0);
    runMotor(2, speed, 1);
    showResult("1正转 2反转(向左转向)", "success");
}

function turn_right() {
    const speed = document.getElementById("speed").value;
    runMotor(2, speed, 0);
    runMotor(1, speed, 1);
    showResult("2正转 1反转(向右转向)", "success");
}

// ====================== 底盘电机控制 ===========================
function start_dipan() {
    const dir = document.getElementById("dipan_zhuanxiang_direction").value;
    const speed = document.getElementById("dipan_zhuanxiang_speed").value;
    const id = 1;

    fetch(`/dipan_motor_run?id=${id}&speed=${speed}&dir=${dir}`, {
        method: 'GET',
        headers: { 'Content-Type': 'application/json' }
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showResult(data.message, 'success');
        } else {
            showResult(data.message, 'error');
        }
    })
    .catch(error => {
        showResult(`请求失败：${error}`, 'error');
    });
}

function stop_dipan() {
    const id = 1;
    fetch(`/dipan_motor_run?id=${id}&speed=0&dir=0`, {
        method: 'GET',
        headers: { 'Content-Type': 'application/json' }
    })
    .then(res => res.json())
    .then(data => {
        showResult("底盘电机已停止", "success");
    }).catch(err => {
        showResult("停止失败", "error");
    });
}

// ====================== 转向电机控制 ===========================
function start_zhuanxiang() {
    const target_position = document.getElementById("target_position").value;
    const zhuanxiang_speed = document.getElementById("zhuanxiang_speed").value;

    fetch(`/zhuanxiang_motor_run?target_position=${target_position}&zhuanxiang_speed=${zhuanxiang_speed}`, {
        method: 'GET',
        headers: { 'Content-Type': 'application/json' }
    })
    .then(res => res.json())
    .then(data => {
        showResult("转向指令发送成功", "success");
    }).catch(err => {
        showResult("发送失败", "error");
    });
}

function stop_zhuanxiang() {
    const target_position = document.getElementById("target_position").value;
    fetch(`/zhuanxiang_motor_run?target_position=${target_position}&zhuanxiang_speed=0`, {
        method: 'GET',
        headers: { 'Content-Type': 'application/json' }
    })
    .then(res => res.json())
    .then(data => {
        showResult("转向电机已停止", "success");
    }).catch(err => {
        showResult("停止失败", "error");
    });
}

// ====================== 实时刷新电机数据 ===========================
// function updateMotorData() {
//     fetch('/data')
//         .then(res => res.json())
//         .then(res => {
//             let d = res.data;
//
//             document.getElementById('m1c').innerText = d.motor1_current;
//             // document.getElementById('m2c').innerText = d.motor2_current;
//             document.getElementById('m1t').innerText = d.motor1_target;
//             // document.getElementById('m2t').innerText = d.motor2_target;
//
//             let l1 = document.getElementById('l1');
//             l1.innerText = d.motor1_limit == 1 ? "✅ 正常" : "❌ 触发";
//             l1.style.color = d.motor1_limit == 1 ? "green" : "red";
//
//             let l2 = document.getElementById('l2');
//             l2.innerText = d.motor2_limit == 1 ? "✅ 正常" : "❌ 触发";
//             l2.style.color = d.motor2_limit == 1 ? "green" : "red";
//         })
//         .catch(err => console.log("获取数据失败", err));
// }
//
// setInterval(updateMotorData, 1000);

// ====================== 通用驱动电机发送 ===========================
function runMotor(motor, speed, dir) {
    fetch(`/chassis_motor_run?id=${motor}&speed=${speed}&dir=${dir}`, {
        method: 'GET',
        headers: { 'Content-Type': 'application/json' }
    });
}