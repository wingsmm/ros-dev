package com.robotca.ControlApp.Core;

import android.os.Bundle;
import android.preference.PreferenceManager;
import android.support.annotation.NonNull;
import android.util.Log;

import com.robotca.ControlApp.ControlApp;
import com.robotca.ControlApp.Core.Plans.RobotPlan;
import com.robotca.ControlApp.R;

import org.ros.message.MessageListener;
import org.ros.namespace.GraphName;
import org.ros.node.ConnectedNode;
import org.ros.node.Node;
import org.ros.node.NodeConfiguration;
import org.ros.node.NodeMain;
import org.ros.node.NodeMainExecutor;
import org.ros.node.parameter.ParameterTree;
import org.ros.node.topic.Publisher;
import org.ros.node.topic.Subscriber;

import java.util.ArrayList;
import java.util.Timer;
import java.util.TimerTask;

import actionlib_msgs.GoalID;
import actionlib_msgs.GoalStatusArray;
import geometry_msgs.Point;
import geometry_msgs.Pose;
import geometry_msgs.PoseStamped;
import geometry_msgs.Quaternion;
import geometry_msgs.Twist;
import nav_msgs.OccupancyGrid;
import nav_msgs.Odometry;
import sensor_msgs.CompressedImage;
import sensor_msgs.LaserScan;
import sensor_msgs.NavSatFix;
import std_msgs.Float64;

/**
 * Manages receiving data from, and sending commands to, a connected Robot.
 *
 * Created by Michael Brunson on 2/13/16.
 */
public class RobotController implements NodeMain, Savable {

    /**
     * Notified when the ROS node connection state changes.
     */
    public interface ConnectionStateListener {
        void onRosConnectionLost(String reason);
        void onRosConnectionStarted();
        void onRosConnectionShutdown();
    }

    // Logcat Tag
    private static final String TAG = "RobotController";

    // The parent Context
    private final ControlApp context;

    // Whether the RobotController has been initialized
    private boolean initialized;

    // Timer for periodically publishing velocity commands
    private Timer publisherTimer;
    // Indicates when a velocity command should be published
    private boolean publishVelocity;

    // Publisher for velocity commands
    private Publisher<Twist> movePublisher;
    // Contains the current velocity plan to be published
    private Twist currentVelocityCommand;

    // Subscriber to NavSatFix data
    private Subscriber<NavSatFix> navSatFixSubscriber;
    // The most recent NavSatFix
    private NavSatFix navSatFix;
    // Lock for synchronizing accessing and receiving the current NatSatFix
    private final Object navSatFixMutex = new Object();

    // Subscriber to LaserScan data
    private Subscriber<LaserScan> laserScanSubscriber;
    // The most recent LaserScan
    private LaserScan laserScan;
    // Lock for synchronizing accessing and receiving the current LaserScan
    private final Object laserScanMutex = new Object();

    // Subscriber to Odometry data
    private Subscriber<Odometry> odometrySubscriber;
    // The most recent Odometry
    private Odometry odometry;
    // Lock for synchronizing accessing and receiving the current Odometry
    private final Object odometryMutex = new Object();

    // Subscriber to Pose data
    private Subscriber<Pose> poseSubscriber;
    // The most recent Pose
    private Pose pose;
    // Lock for synchronizing accessing and receiving the current Pose
    private final Object poseMutex = new Object();

    // Subscriber to Pose data
    private Subscriber<CompressedImage> imageSubscriber;
    // The most recent Pose
    private CompressedImage image;
    // Lock for synchronizing accessing and receiving the current Pose
    private final Object imageMutex = new Object();
    private MessageListener<CompressedImage> imageMessageReceived;

    // The currently running RobotPlan
    private RobotPlan motionPlan;
    // The currently paused RobotPlan
    private int pausedPlanId;

    // The node connected to the Robot on which data can be sent and received
    private ConnectedNode connectedNode;

    // Listener for LaserScans
    private final ArrayList<MessageListener<LaserScan>> laserScanListeners;
    // Listener for Odometry
    private ArrayList<MessageListener<Odometry>> odometryListeners;
    // Listener for NavSatFix
    private ArrayList<MessageListener<NavSatFix>> navSatListeners;

    // Subscriber to OccupancyGrid (/map) data
    private Subscriber<OccupancyGrid> mapSubscriber;
    // The most recent OccupancyGrid
    private OccupancyGrid occupancyGrid;
    // Lock for synchronizing accessing and receiving the current OccupancyGrid
    private final Object mapMutex = new Object();
    // Listener for OccupancyGrid
    private final ArrayList<MessageListener<OccupancyGrid>> mapListeners;

    // Subscriber to gmapping entropy (optional debug topic)
    private Subscriber<Float64> slamEntropySubscriber;
    private double slamEntropy = Double.NaN;
    private final Object slamEntropyMutex = new Object();

    // move_base navigation topics
    private Publisher<PoseStamped> moveBaseGoalPublisher;
    private Publisher<GoalID> moveBaseCancelPublisher;
    private Publisher<Twist> navSpeedPublisher;

    private static final String NAV_SPEED_TOPIC = "/android/nav_speed";
    private static final String ROBOT_POSE_IN_MAP_TOPIC = "/robot_pose_in_map";
    private Subscriber<GoalStatusArray> moveBaseStatusSubscriber;
    private Subscriber<PoseStamped> robotPoseInMapSubscriber;
    private PoseStamped robotPoseInMap;
    private final Object robotPoseInMapMutex = new Object();
    private final ArrayList<MessageListener<PoseStamped>> robotPoseInMapListeners;
    private final ArrayList<MessageListener<GoalStatusArray>> moveBaseStatusListeners;
    private final ArrayList<ConnectionStateListener> connectionStateListeners;

    /**
     * LocationProvider subscribers can register to to receive location updates.
     */
    public final LocationProvider LOCATION_PROVIDER;

    // The Robot's starting position
    private static Point startPos;
    // The Robot's last recorded position
    private static Point currentPos;
    // The Robot's last recorded orientation
    private static Quaternion rotation;
    // The Robot's last recorded speed
    private static double speed;
    // The Robot's last recorded turn rate
    private static double turnRate;

    // Bundle ID for pausedPlan
    private static final String PAUSED_PLAN_BUNDLE_ID = "com.robotca.ControlApp.Core.RobotController.pausedPlan";

    // Constant for no motion plan
    private static final int NO_PLAN = -1;

    /**
     * Creates a RobotController.
     * @param context The Context the RobotController belongs to.
     */
    public RobotController(ControlApp context) {
        this.context = context;

        this.initialized = false;

        this.laserScanListeners = new ArrayList<>();
        this.odometryListeners = new ArrayList<>();
        this.navSatListeners = new ArrayList<>();
        this.mapListeners = new ArrayList<>();
        this.moveBaseStatusListeners = new ArrayList<>();
        this.robotPoseInMapListeners = new ArrayList<>();
        this.connectionStateListeners = new ArrayList<>();

        this.LOCATION_PROVIDER = new LocationProvider();
        this.addNavSatFixListener(this.LOCATION_PROVIDER);

        pausedPlanId = NO_PLAN;

        startPos = null;
        currentPos = null;
        rotation = null;
    }

    /**
     * Adds an Odometry listener.
     * @param l The listener
     * @return True on success
     */
    public boolean addOdometryListener(MessageListener<Odometry> l) {
        return odometryListeners.add(l);
    }

    /**
     * Removes an Odometry listener.
     * @param l The listener
     * @return True if the listener was removed
     */
    public boolean removeOdometryListener(MessageListener<Odometry> l) {
        return odometryListeners.remove(l);
    }

    /**
     * Adds a NavSatFix listener.
     * @param l The listener
     * @return True on success
     */
    public boolean addNavSatFixListener(MessageListener<NavSatFix> l) {
       return navSatListeners.add(l);
    }

    /**
     * Adds a LaserScan listener.
     * @param l The listener
     * @return True on success
     */
    public boolean addLaserScanListener(MessageListener<LaserScan> l) {
        synchronized (laserScanListeners) {
            return laserScanListeners.add(l);
        }
    }

    /**
     * Removes a LaserScan listener.
     * @param l The listener
     * @return True if the listener was removed
     */
    public boolean removeLaserScanListener(MessageListener<LaserScan> l) {

        synchronized (laserScanListeners) {
            return laserScanListeners.remove(l);
        }
    }

    /**
     * Adds an OccupancyGrid listener.
     * @param listener The listener
     * @return True on success
     */
    public boolean addMapListener(MessageListener<OccupancyGrid> listener) {
        synchronized (mapListeners) {
            return mapListeners.add(listener);
        }
    }

    /**
     * Removes an OccupancyGrid listener.
     * @param listener The listener
     * @return True if the listener was removed
     */
    public boolean removeMapListener(MessageListener<OccupancyGrid> listener) {
        synchronized (mapListeners) {
            return mapListeners.remove(listener);
        }
    }

    /**
     * @return The most recently received OccupancyGrid
     */
    public OccupancyGrid getOccupancyGrid() {
        synchronized (mapMutex) {
            return occupancyGrid;
        }
    }

    /**
     * Sets the current OccupancyGrid and notifies listeners.
     * @param grid The OccupancyGrid
     */
    protected void setOccupancyGrid(OccupancyGrid grid) {
        synchronized (mapMutex) {
            occupancyGrid = grid;
        }

        synchronized (mapListeners) {
            for (MessageListener<OccupancyGrid> listener : mapListeners) {
                listener.onNewMessage(grid);
            }
        }
    }

    /**
     * Initializes the RobotController.
     * @param nodeMainExecutor The NodeMainExecutor on which to execute the NodeConfiguration.
     * @param nodeConfiguration The NodeConfiguration to execute
     */
    public void initialize(NodeMainExecutor nodeMainExecutor, NodeConfiguration nodeConfiguration) {
        nodeMainExecutor.execute(this, nodeConfiguration.setNodeName("android/robot_controller"));
    }

    /**
     * Runs the specified RobotPlan on the Robot.
     * @param plan The RobotPlan
     */
    public void runPlan(RobotPlan plan) {
        stop(true);
        pausedPlanId = NO_PLAN;

        publishVelocity = true;

        motionPlan = plan;
        if (motionPlan != null)
            motionPlan.run(this);
    }

    /**
     * Attempts to resume a stopped RobotPlan.
     * @return True if a RobotPlan was resumed
     */
    public boolean resumePlan() {
        if (pausedPlanId != NO_PLAN) {
            Log.d(TAG, "Resuming paused plan");
            runPlan(ControlMode.getRobotPlan(context, ControlMode.values()[pausedPlanId]));
            return true;
        }

        return false;
    }

    /**
     * @return The current RobotPlan
     */
    public RobotPlan getMotionPlan() {
        return motionPlan;
    }

    /**
     * @return Whether there is a paused motion plan
     */
    public boolean hasPausedPlan() {
        return pausedPlanId != NO_PLAN;
    }

    /**
     * Stops the Robot's current motion and any RobotPlan that may be running.
     *
     * @return True if a resumable RobotPlan was cancelled
     */
    public boolean stop() {
        return stop(true);
    }

    /**
     * Stops the Robot's current motion and optionally any RobotPlan that may be running.
     *
     * @param cancelMotionPlan Whether to cancel the current motion plan
     *
     * @return True if a resumable RobotPlan was cancelled
     */
    public boolean stop(boolean cancelMotionPlan) {

        if (cancelMotionPlan || pausedPlanId == NO_PLAN) {
            pausedPlanId = NO_PLAN;

            if (motionPlan != null) {
                motionPlan.stop();

                if (motionPlan.isResumable()) {
                    pausedPlanId = motionPlan.getControlMode() == null ? NO_PLAN : motionPlan.getControlMode().ordinal();
                }

                motionPlan = null;
            }
        }

        publishVelocity = false;
        publishVelocity(0.0, 0.0, 0.0);

        if (movePublisher != null){
            movePublisher.publish(currentVelocityCommand);
        }

        return pausedPlanId != NO_PLAN && cancelMotionPlan;
    }

    /**
     * Sets the next values of the next velocity to publish.
     * @param linearVelocityX Linear velocity in the x direction
     * @param linearVelocityY Linear velocity in the y direction
     * @param angularVelocityZ Angular velocity about the z axis
     */
    public void publishVelocity(double linearVelocityX, double linearVelocityY, double angularVelocityZ) {
        if (currentVelocityCommand != null) {

            float scale = 1.0f;

            try {
                // Safe Mode
                if (context.getWarningSystem().isSafemodeEnabled() && linearVelocityX >= 0.0) {
                    scale = (float) Math.pow(1.0f - context.getHUDFragment().getWarnAmount(), 2.0);
                }
            }
            catch(Exception e){
                scale = 0;
                Log.e("Emergency Stop", e.getMessage());
            }

            if(PreferenceManager.getDefaultSharedPreferences(context).getBoolean(context.getString(R.string.prefs_invert_x_axis_key), false)){
                linearVelocityX *= -1;
            }

            if(PreferenceManager.getDefaultSharedPreferences(context).getBoolean(context.getString(R.string.prefs_invert_y_axis_key), false)){
                linearVelocityY *= -1;
            }

            if(PreferenceManager.getDefaultSharedPreferences(context).getBoolean(context.getString(R.string.prefs_invert_angular_velocity_key), false)){
                angularVelocityZ *= -1;
            }

            currentVelocityCommand.getLinear().setX(linearVelocityX * scale);
            currentVelocityCommand.getLinear().setY(-linearVelocityY * scale);
            currentVelocityCommand.getLinear().setZ(0.0);
            currentVelocityCommand.getAngular().setX(0.0);
            currentVelocityCommand.getAngular().setY(0.0);
            currentVelocityCommand.getAngular().setZ(-angularVelocityZ);
        } else {
            Log.w("Emergency Stop", "currentVelocityCommand is null");
        }
    }

    /**
     * Same as above, but forces the velocity to be published.
     * @param linearVelocityX Linear velocity in the x direction
     * @param linearVelocityY Linear velocity in the y direction
     * @param angularVelocityZ Angular velocity about the z axis
     */
    public void forceVelocity(double linearVelocityX, double linearVelocityY,
                              double angularVelocityZ) {
        publishVelocity = true;
        publishVelocity(linearVelocityX, linearVelocityY, angularVelocityZ);
    }

    /**
     * @return The default node name for the RobotController
     */
    @Override
    public GraphName getDefaultNodeName() {
        return GraphName.of("android/robot_controller");
    }

    /**
     * Callback for when the RobotController is connected.
     * @param connectedNode The ConnectedNode the RobotController is connected through
     */
    public void addConnectionStateListener(ConnectionStateListener listener) {
        synchronized (connectionStateListeners) {
            if (listener != null && !connectionStateListeners.contains(listener)) {
                connectionStateListeners.add(listener);
            }
        }
    }

    public void removeConnectionStateListener(ConnectionStateListener listener) {
        synchronized (connectionStateListeners) {
            connectionStateListeners.remove(listener);
        }
    }

    private void notifyConnectionLost(String reason) {
        synchronized (connectionStateListeners) {
            for (ConnectionStateListener listener : connectionStateListeners) {
                listener.onRosConnectionLost(reason);
            }
        }
    }

    private void notifyConnectionStarted() {
        synchronized (connectionStateListeners) {
            for (ConnectionStateListener listener : connectionStateListeners) {
                listener.onRosConnectionStarted();
            }
        }
    }

    private void notifyConnectionShutdown() {
        synchronized (connectionStateListeners) {
            for (ConnectionStateListener listener : connectionStateListeners) {
                listener.onRosConnectionShutdown();
            }
        }
    }

    @Override
    public void onStart(ConnectedNode connectedNode) {
        this.connectedNode = connectedNode;
        initialize();
        notifyConnectionStarted();
    }

    /*
     * Initializes the RobotController.
     */
    public void initialize() {
        if (!initialized && connectedNode != null) {

            // Start the topics
            refreshTopics();

            initialized = true;
        }
    }

    /**
     * Refreshes all topics, recreating them if there topic names have been changed.
     */
    public void refreshTopics() {

        // Get the correct topic names
        String moveTopic = PreferenceManager.getDefaultSharedPreferences(context)
                .getString(context.getString(R.string.prefs_joystick_topic_edittext_key),
                        context.getString(R.string.joy_topic));

        String navSatTopic = PreferenceManager.getDefaultSharedPreferences(context)
                .getString(context.getString(R.string.prefs_navsat_topic_edittext_key),
                        context.getString(R.string.navsat_topic));

        String laserScanTopic = PreferenceManager.getDefaultSharedPreferences(context)
                .getString(context.getString(R.string.prefs_laserscan_topic_edittext_key),
                        context.getString(R.string.laser_scan_topic));

        String odometryTopic = PreferenceManager.getDefaultSharedPreferences(context)
                .getString(context.getString(R.string.prefs_odometry_topic_edittext_key),
                        context.getString(R.string.odometry_topic));

        String poseTopic = PreferenceManager.getDefaultSharedPreferences(context)
                .getString(context.getString(R.string.prefs_pose_topic_edittext_key),
                        context.getString(R.string.pose_topic));

        String imageTopic = PreferenceManager.getDefaultSharedPreferences(context)
                .getString(context.getString(R.string.prefs_camera_topic_edittext_key),
                        context.getString(R.string.camera_topic));

        String mapTopic = PreferenceManager.getDefaultSharedPreferences(context)
                .getString(context.getString(R.string.prefs_map_topic_edittext_key),
                        context.getString(R.string.map_topic));

        // Refresh the Move Publisher
        if (movePublisher == null
                || !moveTopic.equals(movePublisher.getTopicName().toString())) {

            if (publisherTimer != null) {
                publisherTimer.cancel();
            }

            if (movePublisher != null) {
                movePublisher.shutdown();
            }

            // Start the move publisher
            movePublisher = connectedNode.newPublisher(moveTopic, Twist._TYPE);
            currentVelocityCommand = movePublisher.newMessage();

            publisherTimer = new Timer();
            publisherTimer.schedule(new TimerTask() {
                @Override
                public void run() { if (publishVelocity) {
                    movePublisher.publish(currentVelocityCommand);
                }
                }
            }, 0, 80);
            publishVelocity = false;
        }

        // Refresh the NavSat Subscriber
        if (navSatFixSubscriber == null
                || !navSatTopic.equals(navSatFixSubscriber.getTopicName().toString())) {

            if (navSatFixSubscriber != null)
                navSatFixSubscriber.shutdown();

            // Start the NavSatFix subscriber
            navSatFixSubscriber = connectedNode.newSubscriber(navSatTopic, NavSatFix._TYPE);
            navSatFixSubscriber.addMessageListener(new MessageListener<NavSatFix>() {
                @Override
                public void onNewMessage(NavSatFix navSatFix) {
                    setNavSatFix(navSatFix);
                }
            });
        }

        // Refresh the LaserScan Subscriber
        if (laserScanSubscriber == null
                || !laserScanTopic.equals(laserScanSubscriber.getTopicName().toString())) {

            if (laserScanSubscriber != null)
                laserScanSubscriber.shutdown();

            // Start the LaserScan subscriber
            laserScanSubscriber = connectedNode.newSubscriber(laserScanTopic, LaserScan._TYPE);
            laserScanSubscriber.addMessageListener(new MessageListener<LaserScan>() {
                @Override
                public void onNewMessage(LaserScan laserScan) {
                    setLaserScan(laserScan);
                }
            });
        }

        // Refresh the Odometry Subscriber
        if (odometrySubscriber == null
                || !odometryTopic.equals(odometrySubscriber.getTopicName().toString())) {

            if (odometrySubscriber != null)
                odometrySubscriber.shutdown();

            // Start the Odometry subscriber
            odometrySubscriber = connectedNode.newSubscriber(odometryTopic, Odometry._TYPE);
            odometrySubscriber.addMessageListener(new MessageListener<Odometry>() {
                @Override
                public void onNewMessage(Odometry odometry) {
                    setOdometry(odometry);
                }
            });
        }

        // Refresh the Pose Subscriber
        if (poseSubscriber == null
                || !poseTopic.equals(poseSubscriber.getTopicName().toString())) {

            if (poseSubscriber != null)
                poseSubscriber.shutdown();

            // Start the Pose subscriber
            poseSubscriber = connectedNode.newSubscriber(poseTopic, Pose._TYPE);
            poseSubscriber.addMessageListener(new MessageListener<Pose>() {
                @Override
                public void onNewMessage(Pose pose) {
                    setPose(pose);
                }
            });
        }

        if(imageSubscriber == null || !imageTopic.equals(imageSubscriber.getTopicName().toString())){
            if(imageSubscriber != null)
                imageSubscriber.shutdown();

            imageSubscriber = connectedNode.newSubscriber(imageTopic, CompressedImage._TYPE);

            imageSubscriber.addMessageListener(new MessageListener<CompressedImage>() {
                @Override
                public void onNewMessage(CompressedImage image) {
                    setImage(image);
                    synchronized (imageMutex) {
                        if (imageMessageReceived != null) {
                            imageMessageReceived.onNewMessage(image);
                        }
                    }
                }
            });
        }

        // Refresh the Map Subscriber
        if (mapSubscriber == null
                || !mapTopic.equals(mapSubscriber.getTopicName().toString())) {

            if (mapSubscriber != null) {
                mapSubscriber.shutdown();
            }

            mapSubscriber = connectedNode.newSubscriber(mapTopic, OccupancyGrid._TYPE);
            mapSubscriber.addMessageListener(new MessageListener<OccupancyGrid>() {
                @Override
                public void onNewMessage(OccupancyGrid grid) {
                    setOccupancyGrid(grid);
                }
            });
        }

        if (slamEntropySubscriber == null) {
            slamEntropySubscriber = connectedNode.newSubscriber(
                    context.getString(R.string.slam_entropy_topic), Float64._TYPE);
            slamEntropySubscriber.addMessageListener(new MessageListener<Float64>() {
                @Override
                public void onNewMessage(Float64 entropy) {
                    synchronized (slamEntropyMutex) {
                        slamEntropy = entropy.getData();
                    }
                }
            });
        }

        if (moveBaseGoalPublisher == null) {
            moveBaseGoalPublisher = connectedNode.newPublisher(
                    "/move_base_simple/goal", PoseStamped._TYPE);
        }

        if (moveBaseCancelPublisher == null) {
            moveBaseCancelPublisher = connectedNode.newPublisher(
                    "/move_base/cancel", GoalID._TYPE);
        }

        if (navSpeedPublisher == null) {
            navSpeedPublisher = connectedNode.newPublisher(NAV_SPEED_TOPIC, Twist._TYPE);
        }

        if (moveBaseStatusSubscriber == null) {
            moveBaseStatusSubscriber = connectedNode.newSubscriber(
                    "/move_base/status", GoalStatusArray._TYPE);
            moveBaseStatusSubscriber.addMessageListener(new MessageListener<GoalStatusArray>() {
                @Override
                public void onNewMessage(GoalStatusArray message) {
                    synchronized (moveBaseStatusListeners) {
                        for (MessageListener<GoalStatusArray> listener : moveBaseStatusListeners) {
                            listener.onNewMessage(message);
                        }
                    }
                }
            });
        }

        if (robotPoseInMapSubscriber == null) {
            robotPoseInMapSubscriber = connectedNode.newSubscriber(
                    ROBOT_POSE_IN_MAP_TOPIC, PoseStamped._TYPE);
            robotPoseInMapSubscriber.addMessageListener(new MessageListener<PoseStamped>() {
                @Override
                public void onNewMessage(PoseStamped pose) {
                    synchronized (robotPoseInMapMutex) {
                        robotPoseInMap = pose;
                    }
                    synchronized (robotPoseInMapListeners) {
                        for (MessageListener<PoseStamped> listener : robotPoseInMapListeners) {
                            listener.onNewMessage(pose);
                        }
                    }
                }
            });
        }
    }

    /**
     * Shuts down all topics.
     */
    public void shutdownTopics() {
        if (publisherTimer != null) {
            publisherTimer.cancel();
            publisherTimer = null;
        }

        if (movePublisher != null) {
            movePublisher.shutdown();
            movePublisher = null;
        }
        currentVelocityCommand = null;
        publishVelocity = false;

        if (navSatFixSubscriber != null) {
            navSatFixSubscriber.shutdown();
            navSatFixSubscriber = null;
        }

        if (laserScanSubscriber != null) {
            laserScanSubscriber.shutdown();
            laserScanSubscriber = null;
        }

        if (odometrySubscriber != null) {
            odometrySubscriber.shutdown();
            odometrySubscriber = null;
        }

        if (poseSubscriber != null) {
            poseSubscriber.shutdown();
            poseSubscriber = null;
        }

        if (imageSubscriber != null) {
            imageSubscriber.shutdown();
            imageSubscriber = null;
        }

        if (mapSubscriber != null) {
            mapSubscriber.shutdown();
            mapSubscriber = null;
        }

        if (slamEntropySubscriber != null) {
            slamEntropySubscriber.shutdown();
            slamEntropySubscriber = null;
        }

        if (moveBaseGoalPublisher != null) {
            moveBaseGoalPublisher.shutdown();
            moveBaseGoalPublisher = null;
        }

        if (moveBaseCancelPublisher != null) {
            moveBaseCancelPublisher.shutdown();
            moveBaseCancelPublisher = null;
        }

        if (navSpeedPublisher != null) {
            navSpeedPublisher.shutdown();
            navSpeedPublisher = null;
        }

        if (moveBaseStatusSubscriber != null) {
            moveBaseStatusSubscriber.shutdown();
            moveBaseStatusSubscriber = null;
        }

        if (robotPoseInMapSubscriber != null) {
            robotPoseInMapSubscriber.shutdown();
            robotPoseInMapSubscriber = null;
        }
        synchronized (robotPoseInMapMutex) {
            robotPoseInMap = null;
        }

        initialized = false;
    }

    /**
     * Callback for when the RobotController is shutdown.
     * @param node The Node
     */
    @Override
    public void onShutdown(Node node) {
        shutdownTopics();
        notifyConnectionLost("ROS node shutdown");
    }

    /**
     * Callback for when the shutdown is complete.
     * @param node The Node
     */
    @Override
    public void onShutdownComplete(Node node) {
        this.connectedNode = null;
        notifyConnectionShutdown();
    }

    /**
     * Callback indicating an error has occurred.
     * @param node The Node
     * @param throwable The error
     */
    @Override
    public void onError(Node node, Throwable throwable) {
        Log.e(TAG, "ROS node error", throwable);
        String message = throwable != null ? throwable.getMessage() : "unknown";
        notifyConnectionLost("ROS node error: " + message);
    }

    /**
     * @return The most recently received LaserScan
     */
    public LaserScan getLaserScan() {
        synchronized (laserScanMutex) {
            return laserScan;
        }
    }

    /**
     * Sets the current LaserScan.
     * @param laserScan The LaserScan
     */
    protected void setLaserScan(LaserScan laserScan) {
        synchronized (laserScanMutex) {
            this.laserScan = laserScan;

            boolean invertLaserScan = PreferenceManager.getDefaultSharedPreferences(context).getBoolean(context.getString(R.string.prefs_reverse_angle_reading_key), false);

            if(invertLaserScan) {
                float[] ranges = this.laserScan.getRanges();

                for (int i = 0; i < this.laserScan.getRanges().length / 2; i++) {
                    float range = ranges[i];
                    ranges[i] = ranges[ranges.length - i - 1];
                    ranges[ranges.length - i - 1] = range;
                }
            }
        }

        // Call the listener callbacks
        synchronized (laserScanListeners) {
            for (MessageListener<LaserScan> listener : laserScanListeners) {
                listener.onNewMessage(laserScan);
            }
        }
    }

    /**
     * @return The most recently received NavSatFix
     */
    @SuppressWarnings("unused")
    public NavSatFix getNavSatFix() {
        synchronized (navSatFixMutex) {
            return navSatFix;
        }
    }

    /**
     * Sets the current NavSatFix.
     * @param navSatFix The NavSatFix
     */
    protected void setNavSatFix(NavSatFix navSatFix) {
        synchronized (navSatFixMutex) {
            this.navSatFix = navSatFix;

            // Call the listener callbacks
            for (MessageListener<NavSatFix> listener: navSatListeners) {
                listener.onNewMessage(navSatFix);
            }
        }
    }

    /**
     * @return The most recently received Odometry.
     */
    @SuppressWarnings("unused")
    public Odometry getOdometry() {
        synchronized (odometryMutex) {
            return odometry;
        }
    }

    /**
     * Sets the current Odometry.
     * @param odometry The Odometry
     */
    protected void setOdometry(Odometry odometry) {
        synchronized (odometryMutex) {
            this.odometry = odometry;

            // Call the listener callbacks
            for (MessageListener<Odometry> listener: odometryListeners) {
                listener.onNewMessage(odometry);
            }

            // Record position TODO this should be moved to setPose() but that's not being called for some reason
            if (startPos == null) {
                startPos = odometry.getPose().getPose().getPosition();
            } else {
                currentPos = odometry.getPose().getPose().getPosition();
            }
            rotation = odometry.getPose().getPose().getOrientation();

            // Record speed and turnrate
            speed = odometry.getTwist().getTwist().getLinear().getX();
            turnRate = odometry.getTwist().getTwist().getAngular().getZ();
        }
    }

    /**
     * @return The most recently received Pose.
     */
    @SuppressWarnings("unused")
    public Pose getPose() {
        synchronized (poseMutex) {
            return pose;
        }
    }

    /**
     * Sets the current Pose.
     * @param pose The Pose
     */
    public void setPose(Pose pose){
        synchronized (poseMutex){
            this.pose = pose;
        }

        Log.d("RobotController", "Pose Set");
//        // Record position
//        if (startPos == null) {
//            startPos = pose.getPosition();
//        } else {
//            currentPos = pose.getPosition();
//        }
//        rotation = pose.getOrientation();
    }

    /**
     * Load from a Bundle.
     *
     * @param bundle The Bundle
     */
    @Override
    public void load(@NonNull Bundle bundle) {
        pausedPlanId = bundle.getInt(PAUSED_PLAN_BUNDLE_ID, NO_PLAN);
    }

    /**
     * Save to a Bundle.
     *
     * @param bundle The Bundle
     */
    @Override
    public void save(@NonNull Bundle bundle) {
        bundle.putInt(PAUSED_PLAN_BUNDLE_ID, pausedPlanId);
    }

    /**
     * @return The Robot's last reported x position
     */
    public static double getX() {
        if (currentPos == null)
            return 0.0;
        else
            return currentPos.getX() - startPos.getX();
    }

    /**
     * @return The Robot's last reported y position
     */
    public static double getY() {
        if (currentPos == null)
            return 0.0;
        else
            return currentPos.getY() - startPos.getY();
    }

    /**
     * @return The Robot's last reported heading in radians
     */
    public static double getHeading() {
        if (rotation == null)
            return 0.0;
        else
            return Utils.getHeading(org.ros.rosjava_geometry.Quaternion.fromQuaternionMessage(rotation));
    }

    /**
     * @return The Robot's last reported speed in the range [-1, 1].
     */
    public static double getSpeed() {
        return speed;
    }

    /**
     * @return The Robot's last reported turn rate in the range[-1, 1].
     */
    public static double getTurnRate() {
        return turnRate;
    }


    public void setCameraMessageReceivedListener(MessageListener<CompressedImage> cameraMessageReceived) {
        this.imageMessageReceived = cameraMessageReceived;
    }

    public void setImage(CompressedImage image) {
        synchronized (imageMutex) {
            this.image = image;
        }
    }

    public CompressedImage getImage(){
        synchronized (imageMutex) {
            return this.image;
        }
    }

    /**
     * @return Latest gmapping entropy if available, otherwise null.
     */
    public Double getSlamEntropy() {
        synchronized (slamEntropyMutex) {
            if (Double.isNaN(slamEntropy)) {
                return null;
            }
            return slamEntropy;
        }
    }

    /**
     * @return The connected ROS node, or null if not connected yet.
     */
    public ConnectedNode getConnectedNode() {
        return connectedNode;
    }

    /**
     * @return True if the named ROS parameter exists on the parameter server.
     */
    public boolean hasRosParam(String name) {
        try {
            if (connectedNode == null) {
                return false;
            }
            return connectedNode.getParameterTree().has(name);
        } catch (Exception e) {
            Log.w(TAG, "Failed to check ROS param: " + name, e);
            return false;
        }
    }

    /**
     * Reads a double ROS parameter, returning fallback when unavailable.
     */
    public double getRosDoubleParam(String name, double fallback) {
        try {
            if (connectedNode == null) {
                return fallback;
            }
            ParameterTree params = connectedNode.getParameterTree();
            if (!params.has(name)) {
                return fallback;
            }
            return params.getDouble(name, fallback);
        } catch (Exception e) {
            Log.w(TAG, "Failed to read ROS param: " + name, e);
            return fallback;
        }
    }

    /**
     * Adds a move_base status listener.
     */
    public boolean addMoveBaseStatusListener(MessageListener<GoalStatusArray> listener) {
        synchronized (moveBaseStatusListeners) {
            if (!moveBaseStatusListeners.contains(listener)) {
                return moveBaseStatusListeners.add(listener);
            }
        }
        return false;
    }

    /**
     * Removes a move_base status listener.
     */
    public boolean removeMoveBaseStatusListener(MessageListener<GoalStatusArray> listener) {
        synchronized (moveBaseStatusListeners) {
            return moveBaseStatusListeners.remove(listener);
        }
    }

    public boolean addRobotPoseInMapListener(MessageListener<PoseStamped> listener) {
        synchronized (robotPoseInMapListeners) {
            if (listener != null && !robotPoseInMapListeners.contains(listener)) {
                return robotPoseInMapListeners.add(listener);
            }
        }
        return false;
    }

    public boolean removeRobotPoseInMapListener(MessageListener<PoseStamped> listener) {
        synchronized (robotPoseInMapListeners) {
            return robotPoseInMapListeners.remove(listener);
        }
    }

    /**
     * Publishes a navigation goal in the map frame.
     */
    public boolean publishMoveBaseGoal(double x, double y, double yaw) {
        if (moveBaseGoalPublisher == null || connectedNode == null) {
            return false;
        }

        publishVelocity = false;
        publishVelocity(0.0, 0.0, 0.0);
        if (movePublisher != null && currentVelocityCommand != null) {
            movePublisher.publish(currentVelocityCommand);
        }
        syncMoveBaseSpeedFromPreferences();

        PoseStamped goal = moveBaseGoalPublisher.newMessage();
        goal.getHeader().setFrameId("map");
        goal.getHeader().setStamp(connectedNode.getCurrentTime());
        goal.getPose().getPosition().setX(x);
        goal.getPose().getPosition().setY(y);
        goal.getPose().getPosition().setZ(0.0);

        double halfYaw = yaw * 0.5;
        goal.getPose().getOrientation().setX(0.0);
        goal.getPose().getOrientation().setY(0.0);
        goal.getPose().getOrientation().setZ(Math.sin(halfYaw));
        goal.getPose().getOrientation().setW(Math.cos(halfYaw));

        moveBaseGoalPublisher.publish(goal);
        Log.d(TAG, String.format("Published move_base goal (%.2f, %.2f, %.2f)", x, y, yaw));
        return true;
    }

    private void syncMoveBaseSpeedFromPreferences() {
        if (navSpeedPublisher == null || connectedNode == null) {
            return;
        }

        double linearSpeed = ManualSpeedPreferences.getLinearSpeed(context);
        double angularSpeed = ManualSpeedPreferences.getAngularSpeed(context);

        Twist speed = navSpeedPublisher.newMessage();
        speed.getLinear().setX(linearSpeed);
        speed.getLinear().setY(0.0);
        speed.getLinear().setZ(0.0);
        speed.getAngular().setX(0.0);
        speed.getAngular().setY(0.0);
        speed.getAngular().setZ(angularSpeed);
        navSpeedPublisher.publish(speed);
        Log.d(TAG, String.format(
                "Synced move_base speed from prefs: linear=%.2f angular=%.2f",
                linearSpeed, angularSpeed));
    }

    /**
     * Cancels the current move_base goal and stops manual velocity.
     */
    public boolean cancelMoveBaseGoal() {
        if (moveBaseCancelPublisher == null) {
            return false;
        }

        GoalID cancel = moveBaseCancelPublisher.newMessage();
        cancel.setId("");
        moveBaseCancelPublisher.publish(cancel);

        forceVelocity(0.0, 0.0, 0.0);
        Log.d(TAG, "Published move_base cancel");
        return true;
    }
}