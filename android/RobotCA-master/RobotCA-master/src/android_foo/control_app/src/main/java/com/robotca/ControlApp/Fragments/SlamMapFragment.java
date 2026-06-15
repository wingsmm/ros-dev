package com.robotca.ControlApp.Fragments;

import android.app.Activity;
import android.os.Bundle;
import android.os.Handler;
import android.os.SystemClock;
import android.preference.PreferenceManager;
import android.util.Log;
import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.CheckBox;
import android.widget.LinearLayout;
import android.widget.TextView;
import android.widget.Toast;

import com.robotca.ControlApp.ControlApp;
import com.robotca.ControlApp.Core.Navigation.MoveBaseMissionRunner;
import com.robotca.ControlApp.Core.Navigation.Waypoint;
import com.robotca.ControlApp.Core.Navigation.WaypointMission;
import com.robotca.ControlApp.Core.RobotController;
import com.robotca.ControlApp.Core.SlamMapDiagnostics;
import com.robotca.ControlApp.Core.SlamMapStats;
import com.robotca.ControlApp.R;
import com.robotca.ControlApp.Views.SlamFloatingNavMenu;
import com.robotca.ControlApp.Views.SlamMapView;

import org.ros.message.MessageListener;

import java.util.ArrayList;
import java.util.LinkedList;
import java.util.List;

import actionlib_msgs.GoalStatus;
import actionlib_msgs.GoalStatusArray;
import geometry_msgs.PoseStamped;
import nav_msgs.OccupancyGrid;
import nav_msgs.Odometry;
import nav_msgs.Path;
import sensor_msgs.LaserScan;

/**
 * Fragment for displaying SLAM occupancy grid from /map.
 */
public class SlamMapFragment extends SimpleFragment {

    private enum PickMode {
        NONE,
        SET_A,
        SET_B
    }

    private enum MapNavMode {
        AB,
        MULTI_WAYPOINT
    }

    private enum RoundTripState {
        IDLE,
        GOING_TO_B,
        RETURNING_TO_A,
        FINISHED,
        FAILED,
        CANCELED
    }

    private static final String TAG = "SlamMapFragment";
    private static final long TOPIC_STALE_MS = 2000L;
    private static final long UI_REFRESH_MS = 1000L;
    private static final long MAP_UI_MIN_INTERVAL_MS = 1000L;
    private static final long ROBOT_POSE_UI_MIN_INTERVAL_MS = 200L;
    private static final long MOVE_BASE_PLAN_UI_MIN_INTERVAL_MS = 500L;
    private static final int SCAN_HZ_WINDOW = 20;

    private SlamMapView slamMapView;
    private TextView statusText;
    private LinearLayout debugPanel;
    private TextView debugSummaryText;
    private TextView debugDetailText;
    private TextView navStatusText;
    private Button exportButton;
    private Button cancelPickButton;
    private Button modeAbButton;
    private Button modeMultiButton;
    private Button multiClearButton;
    private Button multiStartButton;
    private Button multiStopButton;
    private CheckBox multiLoopCheckbox;
    private SlamFloatingNavMenu floatingNavMenu;

    private final WaypointMission multiWaypointMission = new WaypointMission();
    private final ArrayList<SlamMapView.MissionWaypointState> multiWaypointStates = new ArrayList<>();
    private MoveBaseMissionRunner missionRunner;
    private MoveBaseMissionRunner.State multiMissionState = MoveBaseMissionRunner.State.IDLE;

    private MessageListener<OccupancyGrid> mapListener;
    private MessageListener<LaserScan> laserListener;
    private MessageListener<Odometry> odometryListener;
    private MessageListener<GoalStatusArray> moveBaseStatusListener;
    private MessageListener<Path> moveBasePlanListener;
    private MessageListener<PoseStamped> robotPoseInMapListener;

    private final Handler uiHandler = new Handler();
    private boolean debugExpanded;
    private PickMode pickMode = PickMode.NONE;
    private MapNavMode mapNavMode = MapNavMode.AB;
    private RoundTripState roundTripState = RoundTripState.IDLE;
    private boolean autoReturnEnabled;
    private SlamMapView.MapPoint pointA;
    private SlamMapView.MapPoint pointB;
    private byte lastMoveBaseStatus = GoalStatus.PENDING;
    private boolean waitingForCurrentGoalActive;
    private boolean currentGoalSawActive;
    private boolean boundsFromRos;
    private double appliedMinX;
    private double appliedMaxX;
    private double appliedMinY;
    private double appliedMaxY;
    private long lastScanTimeMs;
    private long lastOdomTimeMs;
    private final LinkedList<Long> scanTimestamps = new LinkedList<>();

    private OccupancyGrid pendingMapGrid;
    private boolean mapUiUpdatePosted;
    private long lastMapUiUpdateMs;

    private PoseStamped pendingRobotPose;
    private boolean robotPoseUiPosted;
    private long lastRobotPoseUiMs;

    private Path pendingMoveBasePlan;
    private boolean moveBasePlanUiPosted;
    private long lastMoveBasePlanUiMs;

    private final Runnable mapUiUpdateRunnable = new Runnable() {
        @Override
        public void run() {
            mapUiUpdatePosted = false;
            if (slamMapView == null || pendingMapGrid == null) {
                return;
            }
            lastMapUiUpdateMs = SystemClock.elapsedRealtime();
            OccupancyGrid grid = pendingMapGrid;
            applyConfiguredBounds();
            slamMapView.updateMap(grid);
            updateWaitingState();
        }
    };

    private final Runnable robotPoseUiUpdateRunnable = new Runnable() {
        @Override
        public void run() {
            robotPoseUiPosted = false;
            if (slamMapView == null || pendingRobotPose == null) {
                return;
            }
            lastRobotPoseUiMs = SystemClock.elapsedRealtime();
            PoseStamped pose = pendingRobotPose;
            double x = pose.getPose().getPosition().getX();
            double y = pose.getPose().getPosition().getY();
            double yaw = quaternionToYaw(
                    pose.getPose().getOrientation().getX(),
                    pose.getPose().getOrientation().getY(),
                    pose.getPose().getOrientation().getZ(),
                    pose.getPose().getOrientation().getW());
            slamMapView.setRobotPose(x, y, yaw);
        }
    };

    private final Runnable moveBasePlanUiUpdateRunnable = new Runnable() {
        @Override
        public void run() {
            moveBasePlanUiPosted = false;
            if (slamMapView == null || pendingMoveBasePlan == null) {
                return;
            }
            lastMoveBasePlanUiMs = SystemClock.elapsedRealtime();
            slamMapView.updateMoveBasePlan(pendingMoveBasePlan);
        }
    };

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
        navStatusText = (TextView) view.findViewById(R.id.slam_map_nav_status_text);
        floatingNavMenu = (SlamFloatingNavMenu) view.findViewById(R.id.slam_floating_nav_menu);
        exportButton = (Button) floatingNavMenu.findViewById(R.id.slam_map_export_button);

        Button setAButton = (Button) floatingNavMenu.findViewById(R.id.slam_set_a_button);
        Button setBButton = (Button) floatingNavMenu.findViewById(R.id.slam_set_b_button);
        Button goBButton = (Button) floatingNavMenu.findViewById(R.id.slam_go_b_button);
        Button returnAButton = (Button) floatingNavMenu.findViewById(R.id.slam_return_a_button);
        Button roundTripButton = (Button) floatingNavMenu.findViewById(R.id.slam_round_trip_button);
        Button cancelNavButton = (Button) floatingNavMenu.findViewById(R.id.slam_cancel_nav_button);
        Button recenterButton = (Button) floatingNavMenu.findViewById(R.id.slam_map_recenter_button);
        cancelPickButton = (Button) floatingNavMenu.findViewById(R.id.slam_cancel_pick_button);
        modeAbButton = (Button) floatingNavMenu.findViewById(R.id.slam_mode_ab_button);
        modeMultiButton = (Button) floatingNavMenu.findViewById(R.id.slam_mode_multi_button);
        multiClearButton = (Button) floatingNavMenu.findViewById(R.id.slam_multi_clear_button);
        multiStartButton = (Button) floatingNavMenu.findViewById(R.id.slam_multi_start_button);
        multiStopButton = (Button) floatingNavMenu.findViewById(R.id.slam_multi_stop_button);
        multiLoopCheckbox = (CheckBox) floatingNavMenu.findViewById(R.id.slam_multi_loop_checkbox);

        ControlApp activityForRunner = getControlApp();
        if (activityForRunner != null && activityForRunner.getRobotController() != null) {
            missionRunner = new MoveBaseMissionRunner(
                    activityForRunner.getRobotController(),
                    new MoveBaseMissionRunner.Listener() {
                        @Override
                        public void onStateChanged(MoveBaseMissionRunner.State state, int waypointIndex) {
                            multiMissionState = state;
                            if (waypointIndex >= 0 && waypointIndex < multiWaypointStates.size()) {
                                if (state == MoveBaseMissionRunner.State.WAITING_ACTIVE
                                        || state == MoveBaseMissionRunner.State.NAVIGATING
                                        || state == MoveBaseMissionRunner.State.SENDING_GOAL) {
                                    setMultiWaypointState(waypointIndex,
                                            SlamMapView.MissionWaypointState.CURRENT);
                                }
                            }
                            updateMultiMissionUi();
                            updateNavigationStatusText();
                        }

                        @Override
                        public void onWaypointReached(int waypointIndex) {
                            setMultiWaypointState(waypointIndex,
                                    SlamMapView.MissionWaypointState.COMPLETED);
                            refreshMissionWaypointMarkers();
                            updateNavigationStatusText();
                        }

                        @Override
                        public void onMissionCompleted() {
                            multiMissionState = MoveBaseMissionRunner.State.COMPLETED;
                            showToast(R.string.slam_multi_state_completed);
                            updateMultiMissionUi();
                            updateNavigationStatusText();
                        }

                        @Override
                        public void onMissionFailed(int waypointIndex, byte status) {
                            if (waypointIndex >= 0 && waypointIndex < multiWaypointStates.size()) {
                                setMultiWaypointState(waypointIndex,
                                        SlamMapView.MissionWaypointState.FAILED);
                            }
                            multiMissionState = MoveBaseMissionRunner.State.FAILED;
                            showToast(R.string.slam_multi_state_failed, waypointIndex + 1);
                            clearMoveBasePlanOverlay();
                            updateMultiMissionUi();
                            updateNavigationStatusText();
                        }

                        @Override
                        public void onMissionCanceled() {
                            multiMissionState = MoveBaseMissionRunner.State.CANCELED;
                            showToast(R.string.slam_multi_state_canceled);
                            clearMoveBasePlanOverlay();
                            updateMultiMissionUi();
                            updateNavigationStatusText();
                        }
                    });
            missionRunner.setYawProvider(new MoveBaseMissionRunner.YawProvider() {
                @Override
                public double getCurrentYaw() {
                    return slamMapView != null ? slamMapView.getRobotYaw() : 0.0;
                }

                @Override
                public boolean hasCurrentYaw() {
                    return slamMapView != null && slamMapView.hasRobotYaw();
                }
            });
        }

        modeAbButton.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                setMapNavMode(MapNavMode.AB);
            }
        });

        modeMultiButton.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                setMapNavMode(MapNavMode.MULTI_WAYPOINT);
            }
        });

        multiClearButton.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                clearMultiWaypoints();
            }
        });

        multiStartButton.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                startMultiWaypointMission();
            }
        });

        multiStopButton.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                stopMultiWaypointMission();
            }
        });

        setAButton.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                enterPickMode(PickMode.SET_A);
            }
        });

        setBButton.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                enterPickMode(PickMode.SET_B);
            }
        });

        cancelPickButton.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                cancelPickMode();
            }
        });

        goBButton.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                sendGoalTo(pointB, RoundTripState.GOING_TO_B, false);
            }
        });

        returnAButton.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                sendGoalTo(pointA, RoundTripState.RETURNING_TO_A, false);
            }
        });

        roundTripButton.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                if (pointA == null || pointB == null) {
                    showToast(R.string.slam_nav_missing_a_b);
                    return;
                }
                sendGoalTo(pointB, RoundTripState.GOING_TO_B, true);
            }
        });

        cancelNavButton.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                ControlApp activity = getControlApp();
                if (activity != null && activity.getRobotController() != null) {
                    activity.getRobotController().cancelMoveBaseGoal();
                }
                roundTripState = RoundTripState.CANCELED;
                autoReturnEnabled = false;
                resetGoalTracking();
                clearMoveBasePlanOverlay();
                showToast(R.string.slam_nav_cancel_sent);
                updateNavigationStatusText();
            }
        });

        slamMapView.setMapTapListener(new SlamMapView.MapTapListener() {
            @Override
            public void onMapTapped(SlamMapView.MapPoint point) {
                if (mapNavMode == MapNavMode.MULTI_WAYPOINT) {
                    appendMultiWaypoint(point);
                    return;
                }

                if (pickMode == PickMode.NONE) {
                    return;
                }

                if (!slamMapView.isFreeForGoal(point)) {
                    showToast(R.string.slam_nav_goal_rejected);
                    return;
                }

                if (pickMode == PickMode.SET_A) {
                    pointA = point;
                    slamMapView.setPointA(point);
                } else if (pickMode == PickMode.SET_B) {
                    pointB = point;
                    slamMapView.setPointB(point);
                }

                pickMode = PickMode.NONE;
                updatePickModeUi();
            }
        });
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
                if (floatingNavMenu != null) {
                    floatingNavMenu.setExportVisible(debugExpanded);
                }
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
            public void onNewMessage(OccupancyGrid grid) {
                pendingMapGrid = grid;
                scheduleMapUiUpdate();
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

        moveBaseStatusListener = new MessageListener<GoalStatusArray>() {
            @Override
            public void onNewMessage(final GoalStatusArray statusArray) {
                final Activity activity = getActivity();
                if (activity == null) {
                    return;
                }
                activity.runOnUiThread(new Runnable() {
                    @Override
                    public void run() {
                        handleMoveBaseStatus(statusArray);
                    }
                });
            }
        };

        moveBasePlanListener = new MessageListener<Path>() {
            @Override
            public void onNewMessage(Path path) {
                pendingMoveBasePlan = path;
                scheduleMoveBasePlanUiUpdate();
            }
        };

        robotPoseInMapListener = new MessageListener<PoseStamped>() {
            @Override
            public void onNewMessage(PoseStamped pose) {
                pendingRobotPose = pose;
                scheduleRobotPoseUiUpdate();
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
                    pendingMapGrid = cached;
                    lastMapUiUpdateMs = SystemClock.elapsedRealtime();
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
        updateNavigationStatusText();
        updateMapNavModeUi();
        updateMultiMissionUi();
        refreshDebugPanel();
        uiHandler.postDelayed(refreshUiRunnable, UI_REFRESH_MS);

        return view;
    }

    @Override
    public void onResume() {
        super.onResume();
        ControlApp activity = getControlApp();
        if (activity != null) {
            RobotController controller = activity.getRobotController();
            if (controller != null) {
                if (moveBaseStatusListener != null) {
                    controller.addMoveBaseStatusListener(moveBaseStatusListener);
                }
                if (moveBasePlanListener != null) {
                    controller.addMoveBasePlanListener(moveBasePlanListener);
                }
                if (robotPoseInMapListener != null) {
                    controller.addRobotPoseInMapListener(robotPoseInMapListener);
                }
            }
        }
    }

    @Override
    public void onPause() {
        ControlApp activity = getControlApp();
        if (activity != null) {
            RobotController controller = activity.getRobotController();
            if (controller != null) {
                if (moveBaseStatusListener != null) {
                    controller.removeMoveBaseStatusListener(moveBaseStatusListener);
                }
                if (moveBasePlanListener != null) {
                    controller.removeMoveBasePlanListener(moveBasePlanListener);
                }
                if (robotPoseInMapListener != null) {
                    controller.removeRobotPoseInMapListener(robotPoseInMapListener);
                }
            }
        }
        super.onPause();
    }

    @Override
    public void onDestroyView() {
        uiHandler.removeCallbacks(refreshUiRunnable);
        uiHandler.removeCallbacks(mapUiUpdateRunnable);
        uiHandler.removeCallbacks(robotPoseUiUpdateRunnable);
        uiHandler.removeCallbacks(moveBasePlanUiUpdateRunnable);
        mapUiUpdatePosted = false;
        robotPoseUiPosted = false;
        moveBasePlanUiPosted = false;
        pendingMapGrid = null;
        pendingRobotPose = null;
        pendingMoveBasePlan = null;

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
                if (robotPoseInMapListener != null) {
                    controller.removeRobotPoseInMapListener(robotPoseInMapListener);
                }
            }
        }

        mapListener = null;
        laserListener = null;
        odometryListener = null;
        moveBaseStatusListener = null;
        moveBasePlanListener = null;
        robotPoseInMapListener = null;
        slamMapView = null;
        statusText = null;
        debugPanel = null;
        debugSummaryText = null;
        debugDetailText = null;
        navStatusText = null;
        exportButton = null;
        cancelPickButton = null;
        modeAbButton = null;
        modeMultiButton = null;
        multiClearButton = null;
        multiStartButton = null;
        multiStopButton = null;
        multiLoopCheckbox = null;
        floatingNavMenu = null;
        missionRunner = null;
        scanTimestamps.clear();
        super.onDestroyView();
    }

    private void showToast(int resId) {
        ControlApp activity = getControlApp();
        if (activity != null) {
            Toast.makeText(activity, resId, Toast.LENGTH_SHORT).show();
        }
    }

    private void showToast(int resId, Object... args) {
        ControlApp activity = getControlApp();
        if (activity != null) {
            Toast.makeText(activity, activity.getString(resId, args), Toast.LENGTH_SHORT).show();
        }
    }

    private void scheduleMapUiUpdate() {
        if (slamMapView == null || mapUiUpdatePosted) {
            return;
        }
        mapUiUpdatePosted = true;
        long delay = 0;
        if (lastMapUiUpdateMs > 0) {
            long elapsed = SystemClock.elapsedRealtime() - lastMapUiUpdateMs;
            if (elapsed < MAP_UI_MIN_INTERVAL_MS) {
                delay = MAP_UI_MIN_INTERVAL_MS - elapsed;
            }
        }
        uiHandler.postDelayed(mapUiUpdateRunnable, delay);
    }

    private void scheduleRobotPoseUiUpdate() {
        if (slamMapView == null || robotPoseUiPosted) {
            return;
        }
        robotPoseUiPosted = true;
        long delay = 0;
        if (lastRobotPoseUiMs > 0) {
            long elapsed = SystemClock.elapsedRealtime() - lastRobotPoseUiMs;
            if (elapsed < ROBOT_POSE_UI_MIN_INTERVAL_MS) {
                delay = ROBOT_POSE_UI_MIN_INTERVAL_MS - elapsed;
            }
        }
        uiHandler.postDelayed(robotPoseUiUpdateRunnable, delay);
    }

    private void scheduleMoveBasePlanUiUpdate() {
        if (slamMapView == null || moveBasePlanUiPosted) {
            return;
        }
        moveBasePlanUiPosted = true;
        long delay = 0;
        if (lastMoveBasePlanUiMs > 0) {
            long elapsed = SystemClock.elapsedRealtime() - lastMoveBasePlanUiMs;
            if (elapsed < MOVE_BASE_PLAN_UI_MIN_INTERVAL_MS) {
                delay = MOVE_BASE_PLAN_UI_MIN_INTERVAL_MS - elapsed;
            }
        }
        uiHandler.postDelayed(moveBasePlanUiUpdateRunnable, delay);
    }

    private void enterPickMode(PickMode mode) {
        pickMode = mode;
        updatePickModeUi();
        if (mode == PickMode.SET_A) {
            showToast(R.string.slam_nav_pick_a);
        } else if (mode == PickMode.SET_B) {
            showToast(R.string.slam_nav_pick_b);
        }
    }

    private void cancelPickMode() {
        if (pickMode == PickMode.NONE) {
            return;
        }
        pickMode = PickMode.NONE;
        updatePickModeUi();
        showToast(R.string.slam_nav_pick_canceled);
    }

    private static double quaternionToYaw(double x, double y, double z, double w) {
        return Math.atan2(2.0 * (w * z + x * y), 1.0 - 2.0 * (y * y + z * z));
    }

    private void updatePickModeUi() {
        if (cancelPickButton != null) {
            cancelPickButton.setVisibility(pickMode != PickMode.NONE ? View.VISIBLE : View.GONE);
        }
    }

    private void beginGoalTracking() {
        waitingForCurrentGoalActive = true;
        currentGoalSawActive = false;
    }

    private void resetGoalTracking() {
        waitingForCurrentGoalActive = false;
        currentGoalSawActive = false;
    }

    private void clearMoveBasePlanOverlay() {
        pendingMoveBasePlan = null;
        moveBasePlanUiPosted = false;
        uiHandler.removeCallbacks(moveBasePlanUiUpdateRunnable);
        if (slamMapView != null) {
            slamMapView.clearMoveBasePlan();
        }
    }

    private String formatMoveBasePlanStatus() {
        ControlApp activity = getControlApp();
        if (activity == null || slamMapView == null) {
            return "";
        }
        int poseCount = slamMapView.getMoveBasePlanPoseCount();
        if (poseCount <= 0) {
            return activity.getString(R.string.slam_nav_plan_none);
        }
        long ageMs = slamMapView.getMoveBasePlanAgeMs();
        if (ageMs < 0) {
            return activity.getString(R.string.slam_nav_plan_points, poseCount);
        }
        long ageSec = Math.max(0, ageMs / 1000);
        return activity.getString(R.string.slam_nav_plan_points_age, poseCount, ageSec);
    }

    private void sendGoalTo(SlamMapView.MapPoint point, RoundTripState state, boolean autoReturn) {
        if (point == null) {
            showToast(R.string.slam_nav_missing_a_b);
            return;
        }

        if (slamMapView == null || !slamMapView.isFreeForGoal(point)) {
            showToast(R.string.slam_nav_goal_rejected);
            return;
        }

        ControlApp activity = getControlApp();
        if (activity == null || activity.getRobotController() == null) {
            return;
        }

        boolean sent = activity.getRobotController().publishMoveBaseGoal(point.x, point.y, 0.0);
        if (sent) {
            roundTripState = state;
            autoReturnEnabled = autoReturn;
            beginGoalTracking();
            showToast(R.string.slam_nav_goal_sent);
            updateNavigationStatusText();
        }
    }

    private void handleMoveBaseStatus(GoalStatusArray array) {
        if (array == null) {
            return;
        }

        List<GoalStatus> statusList = array.getStatusList();
        if (statusList == null || statusList.isEmpty()) {
            return;
        }

        byte status = statusList.get(statusList.size() - 1).getStatus();
        lastMoveBaseStatus = status;

        if (missionRunner != null && missionRunner.isRunning()) {
            missionRunner.onMoveBaseStatus(status);
            return;
        }

        if (waitingForCurrentGoalActive) {
            if (status == GoalStatus.PENDING || status == GoalStatus.ACTIVE) {
                currentGoalSawActive = true;
            }
            if (!currentGoalSawActive) {
                updateNavigationStatusText();
                return;
            }
        }

        if (status == GoalStatus.SUCCEEDED) {
            resetGoalTracking();
            if (roundTripState == RoundTripState.GOING_TO_B && autoReturnEnabled) {
                autoReturnEnabled = false;
                sendGoalTo(pointA, RoundTripState.RETURNING_TO_A, false);
                return;
            } else if (roundTripState == RoundTripState.GOING_TO_B) {
                roundTripState = RoundTripState.FINISHED;
            } else if (roundTripState == RoundTripState.RETURNING_TO_A) {
                roundTripState = RoundTripState.FINISHED;
            }
        } else if (status == GoalStatus.ABORTED || status == GoalStatus.REJECTED) {
            resetGoalTracking();
            roundTripState = RoundTripState.FAILED;
            autoReturnEnabled = false;
            clearMoveBasePlanOverlay();
        } else if (status == GoalStatus.PREEMPTED) {
            resetGoalTracking();
            roundTripState = RoundTripState.CANCELED;
            autoReturnEnabled = false;
            clearMoveBasePlanOverlay();
        }

        updateNavigationStatusText();
    }

    private void updateNavigationStatusText() {
        if (navStatusText == null) {
            return;
        }

        ControlApp activity = getControlApp();
        if (activity == null) {
            return;
        }

        if (mapNavMode == MapNavMode.MULTI_WAYPOINT) {
            String multiLabel = formatMultiMissionStateLabel(activity);
            String planStatus = formatMoveBasePlanStatus();
            if (planStatus.isEmpty()) {
                navStatusText.setText(activity.getString(R.string.slam_multi_running, multiLabel));
            } else {
                navStatusText.setText(activity.getString(R.string.slam_nav_state_with_plan,
                        activity.getString(R.string.slam_multi_running, multiLabel), planStatus));
            }
            navStatusText.setVisibility(View.VISIBLE);
            return;
        }

        String stateLabel;
        switch (roundTripState) {
            case GOING_TO_B:
                stateLabel = activity.getString(R.string.slam_nav_state_going_b);
                break;
            case RETURNING_TO_A:
                stateLabel = activity.getString(R.string.slam_nav_state_returning_a);
                break;
            case FINISHED:
                stateLabel = activity.getString(R.string.slam_nav_state_finished);
                break;
            case FAILED:
                stateLabel = activity.getString(R.string.slam_nav_state_failed);
                break;
            case CANCELED:
                stateLabel = activity.getString(R.string.slam_nav_state_canceled);
                break;
            case IDLE:
            default:
                if (lastMoveBaseStatus == GoalStatus.ACTIVE) {
                    stateLabel = activity.getString(R.string.slam_nav_state_active);
                } else if (lastMoveBaseStatus == GoalStatus.PENDING) {
                    stateLabel = activity.getString(R.string.slam_nav_state_pending);
                } else {
                    stateLabel = activity.getString(R.string.slam_nav_state_idle);
                }
                break;
        }

        String planStatus = formatMoveBasePlanStatus();
        if (planStatus.isEmpty()) {
            navStatusText.setText(activity.getString(R.string.slam_nav_state, stateLabel));
        } else {
            navStatusText.setText(activity.getString(R.string.slam_nav_state_with_plan, stateLabel, planStatus));
        }
        navStatusText.setVisibility(View.VISIBLE);
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
        detail += "\n" + formatMoveBasePlanStatus();
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
        updateNavigationStatusText();
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

    private void setMapNavMode(MapNavMode mode) {
        if (missionRunner != null && missionRunner.isRunning()) {
            showToast(R.string.slam_multi_manual_locked);
            return;
        }
        mapNavMode = mode;
        if (mode == MapNavMode.AB) {
            cancelPickMode();
        }
        updateMapNavModeUi();
        if (mode == MapNavMode.MULTI_WAYPOINT) {
            showToast(R.string.slam_multi_pick_hint);
        }
    }

    private void updateMapNavModeUi() {
        if (modeAbButton == null || modeMultiButton == null) {
            return;
        }
        modeAbButton.setAlpha(mapNavMode == MapNavMode.AB ? 1.0f : 0.5f);
        modeMultiButton.setAlpha(mapNavMode == MapNavMode.MULTI_WAYPOINT ? 1.0f : 0.5f);
    }

    private boolean isMultiMissionRunning() {
        return missionRunner != null && missionRunner.isRunning();
    }

    private void updateMultiMissionUi() {
        boolean running = isMultiMissionRunning();
        if (multiClearButton != null) {
            multiClearButton.setEnabled(!running);
        }
        if (multiStartButton != null) {
            multiStartButton.setEnabled(!running);
        }
        if (multiStopButton != null) {
            multiStopButton.setEnabled(running);
        }
        if (modeAbButton != null) {
            modeAbButton.setEnabled(!running);
        }
        if (modeMultiButton != null) {
            modeMultiButton.setEnabled(!running);
        }
        if (multiLoopCheckbox != null) {
            multiLoopCheckbox.setEnabled(!running);
        }
    }

    private void appendMultiWaypoint(SlamMapView.MapPoint point) {
        if (isMultiMissionRunning()) {
            return;
        }
        if (slamMapView == null || point == null) {
            return;
        }
        if (!slamMapView.isFreeForGoal(point)) {
            showToast(R.string.slam_nav_goal_rejected);
            return;
        }

        int number = multiWaypointMission.size() + 1;
        double yaw = slamMapView.hasRobotYaw() ? slamMapView.getRobotYaw() : 0.0;
        multiWaypointMission.add(new Waypoint(
                "wp-" + number, point.x, point.y, yaw, String.valueOf(number)));
        multiWaypointStates.add(SlamMapView.MissionWaypointState.PENDING);
        refreshMissionWaypointMarkers();
        showToast(R.string.slam_multi_added, number);
        updateNavigationStatusText();
    }

    private void clearMultiWaypoints() {
        if (isMultiMissionRunning()) {
            return;
        }
        multiWaypointMission.clear();
        multiWaypointStates.clear();
        multiMissionState = MoveBaseMissionRunner.State.IDLE;
        if (slamMapView != null) {
            slamMapView.clearMissionWaypoints();
        }
        showToast(R.string.slam_multi_cleared);
        updateNavigationStatusText();
    }

    private void startMultiWaypointMission() {
        if (missionRunner == null || multiWaypointMission.isEmpty()) {
            showToast(R.string.slam_multi_need_points);
            return;
        }
        if (isMultiMissionRunning()) {
            return;
        }

        multiWaypointMission.setLoop(multiLoopCheckbox != null && multiLoopCheckbox.isChecked());
        resetMultiWaypointStates(SlamMapView.MissionWaypointState.PENDING);
        multiMissionState = MoveBaseMissionRunner.State.READY;
        clearMoveBasePlanOverlay();
        showToast(R.string.slam_multi_manual_locked);

        WaypointMission missionCopy = new WaypointMission();
        missionCopy.setLoop(multiWaypointMission.isLoop());
        for (Waypoint waypoint : multiWaypointMission.getWaypoints()) {
            missionCopy.add(waypoint);
        }

        if (!missionRunner.start(missionCopy)) {
            showToast(R.string.slam_nav_goal_rejected);
            multiMissionState = MoveBaseMissionRunner.State.FAILED;
            updateMultiMissionUi();
            return;
        }
        updateMultiMissionUi();
        updateNavigationStatusText();
    }

    private void stopMultiWaypointMission() {
        if (missionRunner == null) {
            return;
        }
        missionRunner.cancel();
        multiMissionState = MoveBaseMissionRunner.State.CANCELED;
        clearMoveBasePlanOverlay();
        updateMultiMissionUi();
        updateNavigationStatusText();
    }

    private void resetMultiWaypointStates(SlamMapView.MissionWaypointState state) {
        multiWaypointStates.clear();
        for (int i = 0; i < multiWaypointMission.size(); i++) {
            multiWaypointStates.add(state);
        }
        refreshMissionWaypointMarkers();
    }

    private void setMultiWaypointState(int index, SlamMapView.MissionWaypointState state) {
        if (index < 0 || index >= multiWaypointStates.size()) {
            return;
        }
        for (int i = 0; i < index; i++) {
            if (multiWaypointStates.get(i) == SlamMapView.MissionWaypointState.PENDING
                    || multiWaypointStates.get(i) == SlamMapView.MissionWaypointState.CURRENT) {
                multiWaypointStates.set(i, SlamMapView.MissionWaypointState.COMPLETED);
            }
        }
        multiWaypointStates.set(index, state);
        refreshMissionWaypointMarkers();
    }

    private void refreshMissionWaypointMarkers() {
        if (slamMapView == null) {
            return;
        }
        ArrayList<SlamMapView.MissionWaypointMarker> markers = new ArrayList<>();
        for (int i = 0; i < multiWaypointMission.size(); i++) {
            Waypoint waypoint = multiWaypointMission.get(i);
            SlamMapView.MissionWaypointState state = multiWaypointStates.get(i);
            markers.add(new SlamMapView.MissionWaypointMarker(
                    i + 1, waypoint.x, waypoint.y, state));
        }
        slamMapView.setMissionWaypoints(markers);
    }

    private String formatMultiMissionStateLabel(ControlApp activity) {
        switch (multiMissionState) {
            case NAVIGATING:
            case WAITING_ACTIVE:
            case SENDING_GOAL:
            case GOAL_REACHED:
                int current = missionRunner != null ? missionRunner.getCurrentWaypointIndex() : -1;
                if (current >= 0) {
                    return activity.getString(R.string.slam_multi_state_navigating, current + 1);
                }
                return activity.getString(R.string.slam_multi_state_ready);
            case COMPLETED:
                return activity.getString(R.string.slam_multi_state_completed);
            case FAILED:
                int failed = missionRunner != null ? missionRunner.getCurrentWaypointIndex() : -1;
                if (failed < 0) {
                    failed = 0;
                }
                return activity.getString(R.string.slam_multi_state_failed, failed + 1);
            case CANCELED:
                return activity.getString(R.string.slam_multi_state_canceled);
            case READY:
            case IDLE:
            default:
                if (multiWaypointMission.isEmpty()) {
                    return activity.getString(R.string.slam_nav_state_idle);
                }
                return activity.getString(R.string.slam_multi_state_ready);
        }
    }
}
