package com.robotca.ControlApp.Core;

/**
 * Snapshot of SLAM occupancy grid rendering statistics.
 */
public class SlamMapStats {

    public final int width;
    public final int height;
    public final double resolution;
    public final double extentWidthMeters;
    public final double extentHeightMeters;
    public final double knownWidthMeters;
    public final double knownHeightMeters;
    public final boolean hasKnownCells;
    public final int unknownCount;
    public final int freeCount;
    public final int occupiedCount;
    public final int unknownPercent;
    public final int freePercent;
    public final int occupiedPercent;
    public final boolean hasConfiguredAreaStats;
    public final int configuredUnknownPercent;
    public final int configuredFreePercent;
    public final int configuredOccupiedPercent;
    public final long lastUpdateTimeMs;
    public final int updateCount;
    public final long lastRenderDurationMs;
    public final float scale;

    public SlamMapStats(int width, int height, double resolution,
                        int unknownCount, int freeCount, int occupiedCount,
                        double knownWidthMeters, double knownHeightMeters,
                        boolean hasKnownCells,
                        boolean hasConfiguredAreaStats,
                        int configuredUnknownCount,
                        int configuredFreeCount,
                        int configuredOccupiedCount,
                        long lastUpdateTimeMs, int updateCount,
                        long lastRenderDurationMs, float scale) {
        this.width = width;
        this.height = height;
        this.resolution = resolution;
        this.extentWidthMeters = width * resolution;
        this.extentHeightMeters = height * resolution;
        this.knownWidthMeters = knownWidthMeters;
        this.knownHeightMeters = knownHeightMeters;
        this.hasKnownCells = hasKnownCells;
        this.unknownCount = unknownCount;
        this.freeCount = freeCount;
        this.occupiedCount = occupiedCount;

        int total = unknownCount + freeCount + occupiedCount;
        if (total > 0) {
            this.unknownPercent = unknownCount * 100 / total;
            this.freePercent = freeCount * 100 / total;
            this.occupiedPercent = occupiedCount * 100 / total;
        } else {
            this.unknownPercent = 0;
            this.freePercent = 0;
            this.occupiedPercent = 0;
        }

        this.hasConfiguredAreaStats = hasConfiguredAreaStats;
        int configuredTotal = configuredUnknownCount + configuredFreeCount + configuredOccupiedCount;
        if (hasConfiguredAreaStats && configuredTotal > 0) {
            this.configuredUnknownPercent = configuredUnknownCount * 100 / configuredTotal;
            this.configuredFreePercent = configuredFreeCount * 100 / configuredTotal;
            this.configuredOccupiedPercent = configuredOccupiedCount * 100 / configuredTotal;
        } else {
            this.configuredUnknownPercent = 0;
            this.configuredFreePercent = 0;
            this.configuredOccupiedPercent = 0;
        }

        this.lastUpdateTimeMs = lastUpdateTimeMs;
        this.updateCount = updateCount;
        this.lastRenderDurationMs = lastRenderDurationMs;
        this.scale = scale;
    }

    public boolean hasMap() {
        return width > 0 && height > 0;
    }
}
