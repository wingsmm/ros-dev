package com.robotca.ControlApp.Core;

import android.content.Context;
import android.content.SharedPreferences;
import android.preference.PreferenceManager;

import com.robotca.ControlApp.R;

/**
 * Shared manual speed limits used by hold-buttons, joystick, and SLAM navigation.
 */
public final class ManualSpeedPreferences {

    public static final double DEFAULT_LINEAR_SPEED = 0.10;
    public static final double DEFAULT_ANGULAR_SPEED = 0.20;
    public static final double MIN_LINEAR_SPEED = 0.02;
    public static final double MAX_LINEAR_SPEED = 0.30;
    public static final double MIN_ANGULAR_SPEED = 0.05;
    public static final double MAX_ANGULAR_SPEED = 0.80;

    private ManualSpeedPreferences() {
    }

    public static double getLinearSpeed(Context context) {
        return clampSpeed(
                readPreferenceDouble(context, R.string.prefs_manual_linear_speed_key, DEFAULT_LINEAR_SPEED),
                MIN_LINEAR_SPEED,
                MAX_LINEAR_SPEED);
    }

    public static double getAngularSpeed(Context context) {
        return clampSpeed(
                readPreferenceDouble(context, R.string.prefs_manual_angular_speed_key, DEFAULT_ANGULAR_SPEED),
                MIN_ANGULAR_SPEED,
                MAX_ANGULAR_SPEED);
    }

    private static double readPreferenceDouble(Context context, int keyResId, double defaultValue) {
        SharedPreferences prefs = PreferenceManager.getDefaultSharedPreferences(context);
        String value = prefs.getString(context.getString(keyResId), String.valueOf(defaultValue));
        try {
            return Double.parseDouble(value);
        } catch (NumberFormatException e) {
            return defaultValue;
        }
    }

    private static double clampSpeed(double value, double min, double max) {
        return Math.max(min, Math.min(max, value));
    }
}
