package com.robotca.ControlApp.Core.Navigation;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

/**
 * Ordered list of waypoints with optional loop playback.
 */
public class WaypointMission {

    private final ArrayList<Waypoint> waypoints = new ArrayList<>();
    private int currentIndex = -1;
    private boolean loop;

    public void add(Waypoint waypoint) {
        if (waypoint != null) {
            waypoints.add(waypoint);
        }
    }

    public void clear() {
        waypoints.clear();
        currentIndex = -1;
    }

    public int size() {
        return waypoints.size();
    }

    public boolean isEmpty() {
        return waypoints.isEmpty();
    }

    public Waypoint get(int index) {
        if (index < 0 || index >= waypoints.size()) {
            return null;
        }
        return waypoints.get(index);
    }

    public int getCurrentIndex() {
        return currentIndex;
    }

    public Waypoint current() {
        return get(currentIndex);
    }

    public boolean hasNext() {
        return currentIndex >= 0 && currentIndex < waypoints.size() - 1;
    }

    public boolean advance() {
        if (!hasNext()) {
            return false;
        }
        currentIndex++;
        return true;
    }

    public void reset() {
        currentIndex = waypoints.isEmpty() ? -1 : 0;
    }

    public void setLoop(boolean loop) {
        this.loop = loop;
    }

    public boolean isLoop() {
        return loop;
    }

    public List<Waypoint> getWaypoints() {
        return Collections.unmodifiableList(waypoints);
    }
}
