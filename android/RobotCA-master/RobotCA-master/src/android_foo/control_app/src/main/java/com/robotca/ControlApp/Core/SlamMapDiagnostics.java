package com.robotca.ControlApp.Core;

import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.Context;
import android.util.Log;
import android.widget.Toast;

import com.robotca.ControlApp.R;

import java.io.File;
import java.io.FileWriter;
import java.io.IOException;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;

/**
 * Formats SLAM map debug state for UI, Logcat, and export.
 */
public final class SlamMapDiagnostics {

    private static final String TAG = "SlamMap";

    private SlamMapDiagnostics() {
    }

    public static void logMapUpdate(SlamMapStats stats) {
        if (stats == null || !stats.hasMap()) {
            return;
        }
        Log.d(TAG, String.format(Locale.US,
                "map update #%d %dx%d res=%.3f render=%dms free=%d%% occ=%d%% unk=%d%% cfg=%s scale=%.2f",
                stats.updateCount, stats.width, stats.height, stats.resolution,
                stats.lastRenderDurationMs, stats.freePercent, stats.occupiedPercent,
                stats.unknownPercent, formatConfiguredCellsForLog(stats), stats.scale));
    }

    public static String formatSummary(Context context, SlamMapStats stats,
                                       long mapAgeMs, double scanHz,
                                       boolean odomOk, Double entropy) {
        if (stats == null || !stats.hasMap()) {
            return context.getString(R.string.slam_map_debug_waiting)
                    + " | scan " + formatScanHz(scanHz)
                    + (odomOk ? " | odom OK" : " | odom --");
        }

        String mapStatus = context.getString(R.string.slam_map_debug_map_ok,
                formatAge(context, mapAgeMs));
        String entropyText = entropy != null && !entropy.isNaN()
                ? String.format(Locale.US, " entropy %.2f", entropy)
                : "";

        String cellSummary = stats.hasConfiguredAreaStats
                ? "cfg free " + stats.configuredFreePercent + "%"
                + " occ " + stats.configuredOccupiedPercent + "%"
                + " unk " + stats.configuredUnknownPercent + "%"
                : "free " + stats.freePercent + "%"
                + " occ " + stats.occupiedPercent + "%"
                + " unk " + stats.unknownPercent + "%";

        return mapStatus + " | "
                + stats.width + "x" + stats.height
                + " | " + cellSummary
                + " | scan " + formatScanHz(scanHz)
                + (odomOk ? " | odom OK" : " | odom --")
                + entropyText;
    }

    public static String formatDetail(Context context, SlamMapStats stats,
                                      long mapAgeMs, double scanHz,
                                      boolean odomOk, Double entropy,
                                      String mapTopic) {
        StringBuilder sb = new StringBuilder();
        if (stats == null || !stats.hasMap()) {
            sb.append(context.getString(R.string.slam_map_debug_waiting)).append('\n');
            sb.append(context.getString(R.string.slam_map_debug_topic, mapTopic));
            return sb.toString();
        }

        sb.append(context.getString(R.string.slam_map_debug_map_ok, formatAge(context, mapAgeMs))).append('\n');
        sb.append(context.getString(R.string.slam_map_debug_size,
                stats.width, stats.height)).append('\n');
        sb.append(context.getString(R.string.slam_map_debug_resolution, stats.resolution)).append('\n');
        sb.append(context.getString(R.string.slam_map_debug_canvas_extent,
                stats.extentWidthMeters, stats.extentHeightMeters)).append('\n');
        if (stats.hasKnownCells) {
            sb.append(context.getString(R.string.slam_map_debug_known_extent,
                    stats.knownWidthMeters, stats.knownHeightMeters)).append('\n');
        } else {
            sb.append(context.getString(R.string.slam_map_debug_known_extent_missing)).append('\n');
        }
        sb.append(context.getString(R.string.slam_map_debug_updates, stats.updateCount)).append('\n');
        sb.append(context.getString(R.string.slam_map_debug_cells,
                stats.freePercent, stats.occupiedPercent, stats.unknownPercent)).append('\n');
        if (stats.hasConfiguredAreaStats) {
            sb.append(context.getString(R.string.slam_map_debug_configured_cells,
                    stats.configuredFreePercent,
                    stats.configuredOccupiedPercent,
                    stats.configuredUnknownPercent)).append('\n');
        }
        sb.append(context.getString(R.string.slam_map_debug_render, stats.lastRenderDurationMs)).append('\n');
        sb.append(context.getString(R.string.slam_map_debug_scale, stats.scale)).append('\n');
        sb.append(context.getString(R.string.slam_map_debug_scan, formatScanHz(scanHz))).append('\n');
        sb.append(context.getString(R.string.slam_map_debug_odom,
                odomOk ? context.getString(R.string.slam_map_debug_ok)
                        : context.getString(R.string.slam_map_debug_missing))).append('\n');
        if (entropy != null && !entropy.isNaN()) {
            sb.append(context.getString(R.string.slam_map_debug_entropy, entropy)).append('\n');
        } else {
            sb.append(context.getString(R.string.slam_map_debug_entropy_missing)).append('\n');
        }
        sb.append(context.getString(R.string.slam_map_debug_tf_hint)).append('\n');
        sb.append(context.getString(R.string.slam_map_debug_topic, mapTopic));
        return sb.toString();
    }

    public static void export(Context context, String detailText) {
        Log.i(TAG, "diagnostic export\n" + detailText);

        File outFile = new File(context.getExternalCacheDir(), "slam_map_diagnostic.txt");
        try {
            FileWriter writer = new FileWriter(outFile, false);
            writer.write(buildExportHeader());
            writer.write(detailText);
            writer.write('\n');
            writer.close();
        } catch (IOException e) {
            Log.e(TAG, "failed to write diagnostic file", e);
        }

        ClipboardManager clipboard = (ClipboardManager) context.getSystemService(Context.CLIPBOARD_SERVICE);
        if (clipboard != null) {
            clipboard.setPrimaryClip(ClipData.newPlainText("slam_map_diagnostic", detailText));
        }

        Toast.makeText(context,
                context.getString(R.string.slam_map_debug_export_done, outFile.getAbsolutePath()),
                Toast.LENGTH_LONG).show();
    }

    private static String buildExportHeader() {
        SimpleDateFormat fmt = new SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.US);
        return "SLAM Map Diagnostic\n" + fmt.format(new Date()) + "\n\n";
    }

    private static String formatAge(Context context, long ageMs) {
        if (ageMs < 0) {
            return context.getString(R.string.slam_map_debug_never);
        }
        long seconds = Math.max(0, ageMs / 1000);
        if (seconds < 60) {
            return context.getString(R.string.slam_map_debug_seconds_ago, seconds);
        }
        long minutes = seconds / 60;
        return context.getString(R.string.slam_map_debug_minutes_ago, minutes);
    }

    private static String formatScanHz(double scanHz) {
        if (scanHz <= 0.0) {
            return "--";
        }
        return String.format(Locale.US, "%.1fHz", scanHz);
    }

    private static String formatConfiguredCellsForLog(SlamMapStats stats) {
        if (!stats.hasConfiguredAreaStats) {
            return "--";
        }
        return "free " + stats.configuredFreePercent + "%"
                + " occ " + stats.configuredOccupiedPercent + "%"
                + " unk " + stats.configuredUnknownPercent + "%";
    }
}
