package com.robotca.ControlApp.Fragments;

import android.app.Fragment;
import android.os.Bundle;
import android.preference.PreferenceManager;
import android.support.annotation.Nullable;
import android.view.LayoutInflater;
import android.view.MotionEvent;
import android.view.View;
import android.view.ViewGroup;
import android.widget.Button;

import com.robotca.ControlApp.ControlApp;
import com.robotca.ControlApp.Core.ControlMode;
import com.robotca.ControlApp.Core.RobotController;
import com.robotca.ControlApp.R;

/**
 * Hold-to-drive manual control buttons that publish through RobotController.forceVelocity().
 */
public class ManualControlFragment extends Fragment {

    private static final double DEFAULT_LINEAR_SPEED = 0.10;
    private static final double DEFAULT_ANGULAR_SPEED = 0.20;
    private static final double MIN_LINEAR_SPEED = 0.02;
    private static final double MAX_LINEAR_SPEED = 0.30;
    private static final double MIN_ANGULAR_SPEED = 0.05;
    private static final double MAX_ANGULAR_SPEED = 0.80;

    private View view;
    private ControlMode controlMode = ControlMode.Joystick;

    @Override
    public View onCreateView(LayoutInflater inflater, ViewGroup container, Bundle savedInstanceState) {
        if (view == null) {
            view = inflater.inflate(R.layout.fragment_manual_control, container, false);
            bindMotionButton((Button) view.findViewById(R.id.manual_btn_forward), 1, 0, 0, true, false, false);
            bindMotionButton((Button) view.findViewById(R.id.manual_btn_backward), -1, 0, 0, true, false, false);
            bindMotionButton((Button) view.findViewById(R.id.manual_btn_strafe_left), 0, 1, 0, false, true, false);
            bindMotionButton((Button) view.findViewById(R.id.manual_btn_strafe_right), 0, -1, 0, false, true, false);
            bindMotionButton((Button) view.findViewById(R.id.manual_btn_turn_left), 0, 0, 1, false, false, true);
            bindMotionButton((Button) view.findViewById(R.id.manual_btn_turn_right), 0, 0, -1, false, false, true);
            bindStopButton((Button) view.findViewById(R.id.manual_btn_stop));
        }
        return view;
    }

    public ControlMode getControlMode() {
        return controlMode;
    }

    public void setControlMode(ControlMode controlMode) {
        this.controlMode = controlMode;
        invalidate();
    }

    public void invalidate() {
        if (controlMode == ControlMode.Joystick) {
            show();
        } else {
            hide();
            stop();
        }
    }

    public void stop() {
        ControlApp app = getControlApp();
        if (app != null) {
            RobotController controller = app.getRobotController();
            if (controller != null) {
                controller.forceVelocity(0.0, 0.0, 0.0);
            }
        }
    }

    public void show() {
        if (getFragmentManager() != null) {
            getFragmentManager()
                    .beginTransaction()
                    .show(this)
                    .commit();
        }
    }

    public void hide() {
        if (getFragmentManager() != null) {
            getFragmentManager()
                    .beginTransaction()
                    .hide(this)
                    .commit();
        }
    }

    private void bindMotionButton(Button button, final double linearXSign, final double linearYSign,
                                  final double angularZSign, final boolean useLinearX,
                                  final boolean useLinearY, final boolean useAngularZ) {
        button.setOnTouchListener(new View.OnTouchListener() {
            @Override
            public boolean onTouch(View v, MotionEvent event) {
                switch (event.getActionMasked()) {
                    case MotionEvent.ACTION_DOWN:
                        publishMotion(linearXSign, linearYSign, angularZSign,
                                useLinearX, useLinearY, useAngularZ);
                        return true;
                    case MotionEvent.ACTION_MOVE:
                        return true;
                    case MotionEvent.ACTION_UP:
                    case MotionEvent.ACTION_CANCEL:
                        stop();
                        return true;
                    default:
                        return true;
                }
            }
        });
    }

    private void bindStopButton(Button button) {
        button.setOnTouchListener(new View.OnTouchListener() {
            @Override
            public boolean onTouch(View v, MotionEvent event) {
                if (event.getActionMasked() == MotionEvent.ACTION_DOWN) {
                    ControlApp app = getControlApp();
                    if (app != null) {
                        app.stopRobot(false);
                    }
                    return true;
                }
                return false;
            }
        });
    }

    private void publishMotion(double linearXSign, double linearYSign, double angularZSign,
                               boolean useLinearX, boolean useLinearY, boolean useAngularZ) {
        ControlApp app = getControlApp();
        if (app == null) {
            return;
        }

        RobotController controller = app.getRobotController();
        if (controller == null) {
            return;
        }

        double linear = getLinearSpeed();
        double angular = getAngularSpeed();
        double linearX = useLinearX ? linearXSign * linear : 0.0;
        double linearY = useLinearY ? linearYSign * linear : 0.0;
        double angularZ = useAngularZ ? angularZSign * angular : 0.0;

        controller.forceVelocity(linearX, linearY, angularZ);
    }

    private double getLinearSpeed() {
        return clampSpeed(readPreferenceDouble(R.string.prefs_manual_linear_speed_key, DEFAULT_LINEAR_SPEED),
                MIN_LINEAR_SPEED, MAX_LINEAR_SPEED);
    }

    private double getAngularSpeed() {
        return clampSpeed(readPreferenceDouble(R.string.prefs_manual_angular_speed_key, DEFAULT_ANGULAR_SPEED),
                MIN_ANGULAR_SPEED, MAX_ANGULAR_SPEED);
    }

    private double readPreferenceDouble(int keyResId, double defaultValue) {
        if (getActivity() == null) {
            return defaultValue;
        }

        String value = PreferenceManager.getDefaultSharedPreferences(getActivity())
                .getString(getString(keyResId), String.valueOf(defaultValue));
        try {
            return Double.parseDouble(value);
        } catch (NumberFormatException e) {
            return defaultValue;
        }
    }

    private static double clampSpeed(double value, double min, double max) {
        return Math.max(min, Math.min(max, value));
    }

    @Nullable
    private ControlApp getControlApp() {
        if (getActivity() instanceof ControlApp) {
            return (ControlApp) getActivity();
        }
        return null;
    }
}
