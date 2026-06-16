package com.robotca.ControlApp.Core;

import android.os.SystemClock;
import android.util.Log;

import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.HashMap;
import java.util.Locale;
import java.util.Map;

/**
 * Short, human-readable breadcrumbs for field debugging.
 *
 * Use `adb logcat -s RCATrace` to follow user actions and ROS state without
 * the noisy Android/rosjava logs.
 */
public final class AppTrace {

    public static final String TAG = "RCATrace";
    private static final Map<String, Long> LAST_LOG_MS = new HashMap<>();
    private static final ThreadLocal<SimpleDateFormat> TIME_FORMAT =
            new ThreadLocal<SimpleDateFormat>() {
                @Override
                protected SimpleDateFormat initialValue() {
                    return new SimpleDateFormat("HH:mm:ss.SSS", Locale.US);
                }
            };

    private AppTrace() {
    }

    public static void d(String area, String message) {
        Log.d(TAG, format(area, message));
    }

    public static void i(String area, String message) {
        Log.i(TAG, format(area, message));
    }

    public static void w(String area, String message) {
        Log.w(TAG, format(area, message));
    }

    public static void e(String area, String message, Throwable throwable) {
        Log.e(TAG, format(area, message), throwable);
    }

    public static void dThrottle(String key, long intervalMs, String area, String message) {
        if (shouldLog(key, intervalMs)) {
            d(area, message);
        }
    }

    public static String point(double x, double y) {
        return String.format(Locale.US, "(%.2f,%.2f)", x, y);
    }

    private static String format(String area, String message) {
        SimpleDateFormat formatter = TIME_FORMAT.get();
        String time = formatter != null
                ? formatter.format(new Date())
                : String.valueOf(System.currentTimeMillis());
        return time + " [" + area + "] " + message;
    }

    private static synchronized boolean shouldLog(String key, long intervalMs) {
        long now = SystemClock.elapsedRealtime();
        Long last = LAST_LOG_MS.get(key);
        if (last != null && now - last < intervalMs) {
            return false;
        }
        LAST_LOG_MS.put(key, now);
        return true;
    }
}
