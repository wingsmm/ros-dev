package com.robotca.ControlApp.Core.Navigation;

/**
 * A single map-frame navigation waypoint for multi-point missions.
 */
public class Waypoint {

    public final String id;
    public final double x;
    public final double y;
    public final double yaw;
    public final String label;

    public Waypoint(String id, double x, double y, double yaw, String label) {
        this.id = id;
        this.x = x;
        this.y = y;
        this.yaw = yaw;
        this.label = label;
    }
}
