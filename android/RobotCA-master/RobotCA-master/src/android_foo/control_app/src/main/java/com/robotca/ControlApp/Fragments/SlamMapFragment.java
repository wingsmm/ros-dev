package com.robotca.ControlApp.Fragments;

import android.os.Bundle;
import android.os.Handler;
import android.os.SystemClock;
import android.preference.PreferenceManager;
import android.util.Log;
import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.TextView;

import com.robotca.ControlApp.ControlApp;
import com.robotca.ControlApp.Core.RobotController;
import com.robotca.ControlApp.Core.SlamMapDiagnostics;
import com.robotca.ControlApp.Core.SlamMapStats;
import com.robotca.ControlApp.R;
import com.robotca.ControlApp.Views.SlamMapView;

import org.ros.message.MessageListener;

import java.util.LinkedList;

import nav_msgs.OccupancyGrid;
import nav_msgs.Odometry;
import sensor_msgs.LaserScan;

/**
 * Fragment for displaying SLAM occupancy grid from /map.
 */
public class SlamMapFragment extends SimpleFragment {

    private static final String TAG = "SlamMapFragment";
    private static final long TOPIC_STALE_MS = 2000L;
    private static final long UI_REFRESH_MS = 1000L;
    private static final int SCAN_HZ_WINDOW = 20;

    private SlamMapView slamMapView;
    private TextView statusText;
    private LinearLayout debugPanel;
    private TextView debugSummaryText;
    private TextView debugDetailText;
    private Button exportButton;

    private MessageListener<OccupancyGrid> mapListener;
    private MessageListener<LaserScan> laserListener;
    private MessageListener<Odometry> odometryListener;

    private final Handler uiHandler = new Handler();
    private boolean debugExpanded;
    private boolean boundsFromRos;
    private double appliedMinX;
    private double appliedMaxX;
    private double appliedMinY;
    private double appliedMaxY;
    private long lastScanTimeMs;
    private long lastOdomTimeMs;
    private final LinkedList<Long> scanTimestamps = new LinkedList<>();

    private final Runnable refreshUiRunnable = new Runnable() {
        @Override
        public void run() {
            refreshDebugPanel();
            uiHandler.postDelayed(this, UI_REFRESH_MS);
        }
    };

    @Override
    public View onCreateView(LayoutInflater inflater, ViewGroup container, Bundle savedInstanceState) {
        View view = inflater.inflate(R.layout.fragment_slam_map, container, false);

        slamMapView = (SlamMapView) view.findViewById(R.id.slam_map_view);
        statusText = (TextView) view.findViewById(R.id.slam_map_status_text);
        debugPanel = (LinearLayout) view.findViewById(R.id.slam_map_debug_panel);
        debugSummaryText = (TextView) view.findViewById(R.id.slam_map_debug_summary);
        debugDetailText = (TextView) view.findViewById(R.id.slam_map_debug_detail);
        exportButton = (Button) view.findViewById(R.id.slam_map_export_button);

        Button recenterButton = (Button) view.findViewById(R.id.slam_map_recenter_button);
        recenterButton.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                if (slamMapView != null) {
                    slamMapView.recenter();
                    refreshDebugPanel();
                }
            }
        });

        debugPanel.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                debugExpanded = !debugExpanded;
                debugDetailText.setVisibility(debugExpanded ? View.VISIBLE : View.GONE);
                exportButton.setVisibility(debugExpanded ? View.VISIBLE : View.GONE);
                refreshDebugPanel();
            }
        });

        exportButton.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                ControlApp activity = getControlApp();
                if (activity == null) {
                    return;
                }
                SlamMapDiagnostics.export(activity, buildDetailText());
            }
        });

        mapListener = new MessageListener<OccupancyGrid>() {
            @Override
            public void onNewMessage(final OccupancyGrid grid) {
                if (slamMapView == null) {
                    return;
                }
                slamMapView.post(new Runnable() {
                    @Override
                    public void run() {
                        applyConfiguredBounds();
                        slamMapView.updateMap(grid);
                        updateWaitingState();
                        refreshDebugPanel();
                    }
                });
            }
        };

        laserListener = new MessageListener<LaserScan>() {
            @Override
            public void onNewMessage(LaserScan laserScan) {
                recordScanSample();
            }
        };

        odometryListener = new MessageListener<Odometry>() {
            @Override
            public void onNewMessage(Odometry odometry) {
                lastOdomTimeMs = SystemClock.elapsedRealtime();
            }
        };

        ControlApp activity = getControlApp();
        if (activity != null) {
            RobotController controller = activity.getRobotController();
            if (controller != null) {
                controller.addMapListener(mapListener);
                controller.addLaserScanListener(laserListener);
                controller.addOdometryListener(odometryListener);

                OccupancyGrid cached = controller.getOccupancyGrid();
                if (cached != null) {
                    applyConfiguredBounds();
                    slamMapView.updateMap(cached);
                } else {
                    applyConfiguredBounds();
                }
            }
        } else {
            applyConfiguredBounds();
        }

        updateWaitingState();
        refreshDebugPanel();
        uiHandler.postDelayed(refreshUiRunnable, UI_REFRESH_MS);

        return view;
    }

    @Override
    public void onDestroyView() {
        uiHandler.removeCallbacks(refreshUiRunnable);

        ControlApp activity = getControlApp();
        if (activity != null) {
            RobotController controller = activity.getRobotController();
            if (controller != null) {
                if (mapListener != null) {
                    controller.removeMapListener(mapListener);
                }
                if (laserListener != null) {
                    controller.removeLaserScanListener(laserListener);
                }
                if (odometryListener != null) {
                    controller.removeOdometryListener(odometryListener);
                }
            }
        }

        mapListener = null;
        laserListener = null;
        odometryListener = null;
        slamMapView = null;
        statusText = null;
        debugPanel = null;
        debugSummaryText = null;
        debugDetailText = null;
        exportButton = null;
        scanTimestamps.clear();
        super.onDestroyView();
    }

    private void recordScanSample() {
        long now = SystemClock.elapsedRealtime();
        lastScanTimeMs = now;
        synchronized (scanTimestamps) {
            scanTimestamps.addLast(now);
            while (scanTimestamps.size() > SCAN_HZ_WINDOW) {
                scanTimestamps.removeFirst();
            }
        }
    }

    private double getScanHz() {
        synchronized (scanTimestamps) {
            if (scanTimestamps.size() < 2) {
                return 0.0;
            }
            long oldest = scanTimestamps.getFirst();
            long newest = scanTimestamps.getLast();
            long spanMs = newest - oldest;
            if (spanMs <= 0) {
                return 0.0;
            }
            return (scanTimestamps.size() - 1) * 1000.0 / spanMs;
        }
    }

    private boolean isOdomFresh() {
        return lastOdomTimeMs > 0
                && SystemClock.elapsedRealtime() - lastOdomTimeMs <= TOPIC_STALE_MS;
    }

    private boolean isScanFresh() {
        return lastScanTimeMs > 0
                && SystemClock.elapsedRealtime() - lastScanTimeMs <= TOPIC_STALE_MS;
    }

    private String getMapTopic() {
        ControlApp activity = getControlApp();
        if (activity == null) {
            return "/map";
        }
        return PreferenceManager.getDefaultSharedPreferences(activity)
                .getString(activity.getString(R.string.prefs_map_topic_edittext_key),
                        activity.getString(R.string.map_topic));
    }

    private Double getEntropy() {
        ControlApp activity = getControlApp();
        if (activity == null) {
            return null;
        }
        RobotController controller = activity.getRobotController();
        if (controller == null) {
            return null;
        }
        return controller.getSlamEntropy();
    }

    private long getMapAgeMs() {
        if (slamMapView == null) {
            return -1;
        }
        SlamMapStats stats = slamMapView.getStats();
        if (!stats.hasMap() || stats.lastUpdateTimeMs <= 0) {
            return -1;
        }
        return SystemClock.elapsedRealtime() - stats.lastUpdateTimeMs;
    }

    private String buildSummaryText() {
        ControlApp activity = getControlApp();
        if (activity == null || slamMapView == null) {
            return "";
        }
        return SlamMapDiagnostics.formatSummary(
                activity,
                slamMapView.getStats(),
                getMapAgeMs(),
                getScanHz(),
                isOdomFresh(),
                getEntropy()
        );
    }

    private String buildDetailText() {
        ControlApp activity = getControlApp();
        if (activity == null || slamMapView == null) {
            return "";
        }

        String detail = SlamMapDiagnostics.formatDetail(
                activity,
                slamMapView.getStats(),
                getMapAgeMs(),
                getScanHz(),
                isOdomFresh(),
                getEntropy(),
                getMapTopic()
        );

        detail += "\n" + activity.getString(R.string.slam_map_debug_scan_state,
                isScanFresh() ? activity.getString(R.string.slam_map_debug_ok)
                        : activity.getString(R.string.slam_map_debug_missing));
        detail += "\n" + activity.getString(R.string.slam_map_debug_configured_bounds,
                appliedMinX, appliedMaxX, appliedMinY, appliedMaxY);
        detail += "\n" + activity.getString(boundsFromRos
                ? R.string.slam_map_bounds_source_ros
                : R.string.slam_map_bounds_source_prefs);
        return detail;
    }

    private void applyConfiguredBounds() {
        if (slamMapView == null) {
            return;
        }

        ControlApp activity = getControlApp();
        RobotController controller = activity != null ? activity.getRobotController() : null;
        double fallbackXmin = getPreferenceBound(R.string.prefs_slam_xmin_key, R.string.default_slam_xmin);
        double fallbackXmax = getPreferenceBound(R.string.prefs_slam_xmax_key, R.string.default_slam_xmax);
        double fallbackYmin = getPreferenceBound(R.string.prefs_slam_ymin_key, R.string.default_slam_ymin);
        double fallbackYmax = getPreferenceBound(R.string.prefs_slam_ymax_key, R.string.default_slam_ymax);

        if (tryApplyRosBounds(controller, fallbackXmin, fallbackXmax, fallbackYmin, fallbackYmax)) {
            return;
        }

        boundsFromRos = false;
        appliedMinX = fallbackXmin;
        appliedMaxX = fallbackXmax;
        appliedMinY = fallbackYmin;
        appliedMaxY = fallbackYmax;
        slamMapView.setConfiguredBounds(appliedMinX, appliedMaxX, appliedMinY, appliedMaxY);
        Log.d(TAG, String.format("Using preference bounds x[%.1f,%.1f] y[%.1f,%.1f]",
                appliedMinX, appliedMaxX, appliedMinY, appliedMaxY));
    }

    private boolean tryApplyRosBounds(RobotController controller,
                                      double fallbackXmin, double fallbackXmax,
                                      double fallbackYmin, double fallbackYmax) {
        ControlApp activity = getControlApp();
        if (controller == null || activity == null) {
            return false;
        }

        String paramXmin = activity.getString(R.string.slam_gmapping_param_xmin);
        String paramXmax = activity.getString(R.string.slam_gmapping_param_xmax);
        String paramYmin = activity.getString(R.string.slam_gmapping_param_ymin);
        String paramYmax = activity.getString(R.string.slam_gmapping_param_ymax);

        try {
            if (!controller.hasRosParam(paramXmin)
                    || !controller.hasRosParam(paramXmax)
                    || !controller.hasRosParam(paramYmin)
                    || !controller.hasRosParam(paramYmax)) {
                return false;
            }

            double xmin = controller.getRosDoubleParam(paramXmin, fallbackXmin);
            double xmax = controller.getRosDoubleParam(paramXmax, fallbackXmax);
            double ymin = controller.getRosDoubleParam(paramYmin, fallbackYmin);
            double ymax = controller.getRosDoubleParam(paramYmax, fallbackYmax);

            if (xmax <= xmin || ymax <= ymin) {
                return false;
            }

            boundsFromRos = true;
            appliedMinX = xmin;
            appliedMaxX = xmax;
            appliedMinY = ymin;
            appliedMaxY = ymax;
            slamMapView.setConfiguredBounds(xmin, xmax, ymin, ymax);
            Log.d(TAG, String.format("Using ROS bounds x[%.1f,%.1f] y[%.1f,%.1f]",
                    xmin, xmax, ymin, ymax));
            return true;
        } catch (Exception e) {
            Log.w(TAG, "Failed to read gmapping bounds from ROS", e);
            return false;
        }
    }

    private double getPreferenceBound(int keyResId, int defaultResId) {
        ControlApp activity = getControlApp();
        if (activity == null) {
            return 0.0;
        }
        String defaultValue = activity.getString(defaultResId);
        String value = PreferenceManager.getDefaultSharedPreferences(activity)
                .getString(activity.getString(keyResId), defaultValue);
        try {
            return Double.parseDouble(value);
        } catch (NumberFormatException e) {
            return Double.parseDouble(defaultValue);
        }
    }

    private void refreshDebugPanel() {
        if (debugSummaryText == null || slamMapView == null) {
            return;
        }

        updateWaitingState();

        if (!slamMapView.hasMap()) {
            debugPanel.setVisibility(View.GONE);
            return;
        }

        debugPanel.setVisibility(View.VISIBLE);
        debugSummaryText.setText(buildSummaryText());
        if (debugExpanded) {
            debugDetailText.setText(buildDetailText());
        }
    }

    private void updateWaitingState() {
        if (statusText == null || slamMapView == null) {
            return;
        }
        statusText.setVisibility(slamMapView.hasMap() ? View.GONE : View.VISIBLE);
    }
}
