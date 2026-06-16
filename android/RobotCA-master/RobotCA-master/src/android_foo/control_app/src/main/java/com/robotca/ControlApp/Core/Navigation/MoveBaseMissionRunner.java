package com.robotca.ControlApp.Core.Navigation;

import android.util.Log;

import com.robotca.ControlApp.Core.AppTrace;
import com.robotca.ControlApp.Core.RobotController;

import actionlib_msgs.GoalStatus;

/**
 * Android-side task queue for sequential move_base goals.
 * Sends one goal at a time and advances only after a validated SUCCEEDED status.
 */
public class MoveBaseMissionRunner {

    private static final String TAG = "MoveBaseMissionRunner";

    public enum State {
        IDLE,
        READY,
        SENDING_GOAL,
        WAITING_ACTIVE,
        NAVIGATING,
        GOAL_REACHED,
        FAILED,
        CANCELED,
        COMPLETED
    }

    public interface Listener {
        void onStateChanged(State state, int waypointIndex);

        void onWaypointReached(int waypointIndex);

        void onMissionCompleted();

        void onMissionFailed(int waypointIndex, byte status);

        void onMissionCanceled();
    }

    private final RobotController controller;
    private final Listener listener;

    private WaypointMission mission;
    private State state = State.IDLE;
    private boolean waitingForGoalActive;
    private boolean currentGoalSawActive;

    public MoveBaseMissionRunner(RobotController controller, Listener listener) {
        this.controller = controller;
        this.listener = listener;
    }

    public State getState() {
        return state;
    }

    public boolean isRunning() {
        return state == State.READY
                || state == State.SENDING_GOAL
                || state == State.WAITING_ACTIVE
                || state == State.NAVIGATING
                || state == State.GOAL_REACHED;
    }

    public int getCurrentWaypointIndex() {
        return mission != null ? mission.getCurrentIndex() : -1;
    }

    public boolean start(WaypointMission mission) {
        if (controller == null || mission == null || mission.isEmpty()) {
            return false;
        }
        if (isRunning()) {
            return false;
        }

        this.mission = mission;
        AppTrace.i("mission", "start waypoints=" + mission.size() + " loop=" + mission.isLoop());
        mission.reset();
        waitingForGoalActive = false;
        currentGoalSawActive = false;
        setManualBlocked(true);
        setState(State.READY);
        return sendCurrentGoal();
    }

    public void cancel() {
        if (state == State.IDLE || state == State.COMPLETED
                || state == State.CANCELED || state == State.FAILED) {
            return;
        }

        if (controller != null) {
            controller.cancelMoveBaseGoal();
            controller.stopMotion();
        }

        waitingForGoalActive = false;
        currentGoalSawActive = false;
        setManualBlocked(false);
        setState(State.CANCELED);
        if (listener != null) {
            listener.onMissionCanceled();
        }
    }

    public void onMoveBaseStatus(byte status) {
        if (!isRunning() && state != State.GOAL_REACHED) {
            return;
        }

        if (waitingForGoalActive) {
            if (status == GoalStatus.PENDING || status == GoalStatus.ACTIVE) {
                currentGoalSawActive = true;
                if (state == State.WAITING_ACTIVE || state == State.SENDING_GOAL) {
                    setState(State.NAVIGATING);
                }
            }
            if (!currentGoalSawActive) {
                return;
            }
        }

        if (status == GoalStatus.SUCCEEDED) {
            if (!currentGoalSawActive) {
                return;
            }

            int reachedIndex = mission.getCurrentIndex();
            AppTrace.i("mission", "waypoint reached #" + (reachedIndex + 1));
            setState(State.GOAL_REACHED);
            if (listener != null) {
                listener.onWaypointReached(reachedIndex);
            }

            waitingForGoalActive = false;
            currentGoalSawActive = false;

            if (mission.hasNext()) {
                mission.advance();
                sendCurrentGoal();
                return;
            }

            if (mission.isLoop()) {
                mission.reset();
                sendCurrentGoal();
                return;
            }

            setManualBlocked(false);
            AppTrace.i("mission", "completed");
            setState(State.COMPLETED);
            if (listener != null) {
                listener.onMissionCompleted();
            }
            return;
        }

        if (status == GoalStatus.ABORTED
                || status == GoalStatus.REJECTED
                || status == 8   // GoalStatus.RECALLED (not exposed in rosjava binding)
                || status == 9) { // GoalStatus.LOST    (not exposed in rosjava binding)
            if (waitingForGoalActive && !currentGoalSawActive) {
                return;
            }
            failMission(mission.getCurrentIndex(), status);
        } else if (status == GoalStatus.PREEMPTED) {
            if (state != State.CANCELED) {
                waitingForGoalActive = false;
                currentGoalSawActive = false;
                setManualBlocked(false);
                setState(State.CANCELED);
                if (listener != null) {
                    listener.onMissionCanceled();
                }
            }
        }
    }

    private boolean sendCurrentGoal() {
        if (mission == null || controller == null) {
            failMission(-1, GoalStatus.REJECTED);
            return false;
        }

        Waypoint waypoint = mission.current();
        if (waypoint == null) {
            setManualBlocked(false);
            AppTrace.i("mission", "completed");
            setState(State.COMPLETED);
            if (listener != null) {
                listener.onMissionCompleted();
            }
            return false;
        }

        double yaw = waypoint.yaw;

        setState(State.SENDING_GOAL);
        boolean sent = controller.publishMoveBaseGoal(waypoint.x, waypoint.y, yaw);
        if (!sent) {
            failMission(mission.getCurrentIndex(), GoalStatus.REJECTED);
            return false;
        }

        waitingForGoalActive = true;
        currentGoalSawActive = false;
        setState(State.WAITING_ACTIVE);
        AppTrace.i("mission", String.format(
                "send #%d %s yaw=%.2f", mission.getCurrentIndex() + 1,
                AppTrace.point(waypoint.x, waypoint.y), yaw));
        Log.d(TAG, String.format(
                "Sent waypoint %d (%s) at (%.2f, %.2f, %.2f)",
                mission.getCurrentIndex() + 1,
                waypoint.label,
                waypoint.x,
                waypoint.y,
                yaw));
        return true;
    }

    private void failMission(int waypointIndex, byte status) {
        waitingForGoalActive = false;
        currentGoalSawActive = false;
        setManualBlocked(false);
        AppTrace.w("mission", "failed waypoint="
                + (waypointIndex >= 0 ? String.valueOf(waypointIndex + 1) : "none")
                + " status=" + status);
        setState(State.FAILED);
        if (listener != null) {
            listener.onMissionFailed(waypointIndex, status);
        }
    }

    private void setState(State newState) {
        state = newState;
        if (listener != null) {
            listener.onStateChanged(newState, mission != null ? mission.getCurrentIndex() : -1);
        }
    }

    private void setManualBlocked(boolean blocked) {
        if (controller != null) {
            controller.setManualCmdVelBlocked(blocked);
        }
    }
}
