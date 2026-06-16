package com.robotca.ControlApp.Views;

import android.content.Context;
import android.graphics.Bitmap;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Paint;
import android.graphics.RectF;
import android.os.SystemClock;
import android.util.AttributeSet;
import android.view.MotionEvent;
import android.view.ScaleGestureDetector;
import android.view.View;

import com.robotca.ControlApp.Core.SlamMapDiagnostics;
import com.robotca.ControlApp.Core.SlamMapStats;

import nav_msgs.OccupancyGrid;
import nav_msgs.Path;
import org.jboss.netty.buffer.ChannelBuffer;

import java.util.ArrayList;
import java.util.List;

import geometry_msgs.PoseStamped;

/**
 * Custom View for rendering a SLAM occupancy grid as a cached Bitmap.
 */
public class SlamMapView extends View {

    public enum MissionWaypointState {
        PENDING,
        CURRENT,
        COMPLETED,
        FAILED
    }

    public static class MissionWaypointMarker {
        public final int number;
        public final double x;
        public final double y;
        public final MissionWaypointState state;

        public MissionWaypointMarker(int number, double x, double y, MissionWaypointState state) {
            this.number = number;
            this.x = x;
            this.y = y;
            this.state = state;
        }
    }

    public static class MapPoint {
        public final double x;
        public final double y;

        public MapPoint(double x, double y) {
            this.x = x;
            this.y = y;
        }
    }

    public interface MapTapListener {
        void onMapTapped(MapPoint point);
    }

    private static final float MIN_SCALE = 0.1f;
    private static final float MAX_SCALE = 10.0f;
    private static final float MAX_RECENTER_SCALE = 4.0f;
    private static final float OVERLAY_STROKE_PX = 2.0f;
    private static final float PLAN_STROKE_PX = 3.0f;
    private static final int PLAN_COLOR = Color.argb(200, 40, 120, 255);
    private static final int MISSION_PENDING_COLOR = Color.rgb(40, 120, 255);
    private static final int MISSION_CURRENT_COLOR = Color.rgb(255, 210, 40);
    private static final int MISSION_COMPLETED_COLOR = Color.rgb(40, 180, 80);
    private static final int MISSION_FAILED_COLOR = Color.rgb(230, 50, 50);
    private static final float TAP_SLOP_PX = 12.0f;

    private Bitmap mapBitmap;
    private final Paint paint = new Paint(Paint.FILTER_BITMAP_FLAG);
    private final Paint configuredBoundsPaint = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint knownBoundsPaint = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint pointAPaint = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint pointBPaint = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint pointTextPaint = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint robotPaint = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint robotArrowPaint = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint planPaint = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint missionPendingPaint = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint missionCurrentFillPaint = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint missionCurrentStrokePaint = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint missionCompletedPaint = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint missionFailedPaint = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint missionNumberPaint = new Paint(Paint.ANTI_ALIAS_FLAG);

    private MapTapListener mapTapListener;
    private MapPoint pointA;
    private MapPoint pointB;
    private MapPoint robotPoint;
    private double robotYaw;
    private boolean hasRobotPose;
    private final ArrayList<MissionWaypointMarker> missionWaypoints = new ArrayList<>();
    private nav_msgs.Path lastMoveBasePlanRos;
    private android.graphics.Path cachedPlanPath;
    private int moveBasePlanPoseCount;
    private long moveBasePlanUpdatedMs;
    private byte[] lastGridData;

    private float scale = 1.0f;
    private float translateX = 0.0f;
    private float translateY = 0.0f;
    private float lastX;
    private float lastY;
    private float downX;
    private float downY;
    private boolean dragging;

    private int lastBitmapWidth;
    private int lastBitmapHeight;

    private int updateCount;
    private long lastUpdateTimeMs;
    private long lastRenderDurationMs;
    private double lastResolution;
    private double lastOriginX;
    private double lastOriginY;
    private int lastUnknownCount;
    private int lastFreeCount;
    private int lastOccupiedCount;
    private boolean hasConfiguredAreaStats;
    private int configuredUnknownCount;
    private int configuredFreeCount;
    private int configuredOccupiedCount;
    private boolean hasKnownCells;
    private int knownMinX;
    private int knownMinY;
    private int knownMaxX;
    private int knownMaxY;
    private double knownWidthMeters;
    private double knownHeightMeters;
    private boolean hasConfiguredBounds;
    private double configuredMinX;
    private double configuredMaxX;
    private double configuredMinY;
    private double configuredMaxY;

    private final ScaleGestureDetector scaleGestureDetector;

    public SlamMapView(Context context) {
        super(context);
        initPaints();
        scaleGestureDetector = new ScaleGestureDetector(context, new ScaleListener());
    }

    public SlamMapView(Context context, AttributeSet attrs) {
        super(context, attrs);
        initPaints();
        scaleGestureDetector = new ScaleGestureDetector(context, new ScaleListener());
    }

    public SlamMapView(Context context, AttributeSet attrs, int defStyleAttr) {
        super(context, attrs, defStyleAttr);
        initPaints();
        scaleGestureDetector = new ScaleGestureDetector(context, new ScaleListener());
    }

    private void initPaints() {
        configuredBoundsPaint.setStyle(Paint.Style.STROKE);
        configuredBoundsPaint.setStrokeWidth(2.0f);
        configuredBoundsPaint.setColor(Color.YELLOW);

        knownBoundsPaint.setStyle(Paint.Style.STROKE);
        knownBoundsPaint.setStrokeWidth(2.0f);
        knownBoundsPaint.setColor(Color.rgb(0, 220, 120));

        pointAPaint.setColor(Color.rgb(40, 120, 255));
        pointAPaint.setStyle(Paint.Style.FILL);

        pointBPaint.setColor(Color.rgb(230, 50, 50));
        pointBPaint.setStyle(Paint.Style.FILL);

        pointTextPaint.setColor(Color.WHITE);
        pointTextPaint.setTextAlign(Paint.Align.CENTER);
        pointTextPaint.setTextSize(14.0f);
        pointTextPaint.setFakeBoldText(true);

        robotPaint.setColor(Color.rgb(255, 40, 40));
        robotPaint.setStyle(Paint.Style.FILL);

        robotArrowPaint.setColor(Color.rgb(30, 120, 255));
        robotArrowPaint.setStyle(Paint.Style.STROKE);
        robotArrowPaint.setStrokeWidth(3.0f);

        planPaint.setColor(PLAN_COLOR);
        planPaint.setStyle(Paint.Style.STROKE);
        planPaint.setStrokeWidth(PLAN_STROKE_PX);
        planPaint.setStrokeJoin(Paint.Join.ROUND);
        planPaint.setStrokeCap(Paint.Cap.ROUND);

        missionPendingPaint.setColor(MISSION_PENDING_COLOR);
        missionPendingPaint.setStyle(Paint.Style.FILL);

        missionCurrentFillPaint.setColor(MISSION_PENDING_COLOR);
        missionCurrentFillPaint.setStyle(Paint.Style.FILL);

        missionCurrentStrokePaint.setColor(MISSION_CURRENT_COLOR);
        missionCurrentStrokePaint.setStyle(Paint.Style.STROKE);

        missionCompletedPaint.setColor(MISSION_COMPLETED_COLOR);
        missionCompletedPaint.setStyle(Paint.Style.FILL);

        missionFailedPaint.setColor(MISSION_FAILED_COLOR);
        missionFailedPaint.setStyle(Paint.Style.FILL);

        missionNumberPaint.setColor(Color.WHITE);
        missionNumberPaint.setTextAlign(Paint.Align.CENTER);
        missionNumberPaint.setTextSize(14.0f);
        missionNumberPaint.setFakeBoldText(true);
    }

    public void setMapTapListener(MapTapListener listener) {
        this.mapTapListener = listener;
    }

    public void setPointA(MapPoint point) {
        pointA = point;
        invalidate();
    }

    public void setPointB(MapPoint point) {
        pointB = point;
        invalidate();
    }

    public void setRobotPose(double x, double y, double yaw) {
        robotPoint = new MapPoint(x, y);
        robotYaw = yaw;
        hasRobotPose = true;
        invalidate();
    }

    public void clearRobotPose() {
        hasRobotPose = false;
        robotPoint = null;
        invalidate();
    }

    public void updateMoveBasePlan(Path path) {
        lastMoveBasePlanRos = path;
        moveBasePlanUpdatedMs = SystemClock.elapsedRealtime();
        rebuildCachedPlanPath();
        invalidate();
    }

    public void clearMoveBasePlan() {
        lastMoveBasePlanRos = null;
        cachedPlanPath = null;
        moveBasePlanPoseCount = 0;
        moveBasePlanUpdatedMs = 0;
        invalidate();
    }

    public void setMissionWaypoints(List<MissionWaypointMarker> markers) {
        missionWaypoints.clear();
        if (markers != null) {
            missionWaypoints.addAll(markers);
        }
        invalidate();
    }

    public void clearMissionWaypoints() {
        missionWaypoints.clear();
        invalidate();
    }

    public double getRobotYaw() {
        return robotYaw;
    }

    public boolean hasRobotYaw() {
        return hasRobotPose;
    }

    public int getMoveBasePlanPoseCount() {
        return moveBasePlanPoseCount;
    }

    public long getMoveBasePlanAgeMs() {
        if (moveBasePlanUpdatedMs <= 0) {
            return -1;
        }
        return SystemClock.elapsedRealtime() - moveBasePlanUpdatedMs;
    }

    public MapPoint screenToMap(float screenX, float screenY) {
        if (mapBitmap == null || lastResolution <= 0.0) {
            return null;
        }

        double bitmapX = (screenX - translateX) / scale;
        double bitmapY = (screenY - translateY) / scale;

        if (bitmapX < 0 || bitmapY < 0
                || bitmapX >= mapBitmap.getWidth() || bitmapY >= mapBitmap.getHeight()) {
            return null;
        }

        double mapX = lastOriginX + bitmapX * lastResolution;
        double mapY = lastOriginY + (mapBitmap.getHeight() - bitmapY) * lastResolution;
        return new MapPoint(mapX, mapY);
    }

    public boolean isFreeForGoal(MapPoint point) {
        if (point == null || lastGridData == null || lastResolution <= 0.0) {
            return false;
        }

        int gx = (int) Math.floor((point.x - lastOriginX) / lastResolution);
        int gy = (int) Math.floor((point.y - lastOriginY) / lastResolution);

        if (gx < 0 || gy < 0 || gx >= lastBitmapWidth || gy >= lastBitmapHeight) {
            return false;
        }

        int radiusCells = 3;
        for (int y = gy - radiusCells; y <= gy + radiusCells; y++) {
            for (int x = gx - radiusCells; x <= gx + radiusCells; x++) {
                if (x < 0 || y < 0 || x >= lastBitmapWidth || y >= lastBitmapHeight) {
                    continue;
                }
                int value = lastGridData[y * lastBitmapWidth + x];
                if (value < 0 || value > 50) {
                    return false;
                }
            }
        }

        return true;
    }

    public void setConfiguredBounds(double minX, double maxX, double minY, double maxY) {
        if (maxX <= minX || maxY <= minY) {
            hasConfiguredBounds = false;
        } else {
            configuredMinX = minX;
            configuredMaxX = maxX;
            configuredMinY = minY;
            configuredMaxY = maxY;
            hasConfiguredBounds = true;
        }
        invalidate();
    }

    public void updateMap(OccupancyGrid grid) {
        if (grid == null || grid.getInfo() == null) {
            return;
        }

        int width = grid.getInfo().getWidth();
        int height = grid.getInfo().getHeight();
        if (width <= 0 || height <= 0) {
            return;
        }

        ChannelBuffer data = grid.getData();
        if (data == null || data.readableBytes() < width * height) {
            return;
        }

        boolean sizeChanged = mapBitmap == null
                || lastBitmapWidth != width
                || lastBitmapHeight != height;

        rebuildBitmap(grid, width, height, data);
        SlamMapDiagnostics.logMapUpdate(getStats());

        if (sizeChanged) {
            post(new Runnable() {
                @Override
                public void run() {
                    recenter();
                }
            });
        } else {
            invalidate();
        }
    }

    public SlamMapStats getStats() {
        return new SlamMapStats(
                lastBitmapWidth,
                lastBitmapHeight,
                lastResolution,
                lastUnknownCount,
                lastFreeCount,
                lastOccupiedCount,
                knownWidthMeters,
                knownHeightMeters,
                hasKnownCells,
                hasConfiguredAreaStats,
                configuredUnknownCount,
                configuredFreeCount,
                configuredOccupiedCount,
                lastUpdateTimeMs,
                updateCount,
                lastRenderDurationMs,
                scale
        );
    }

    public void recenter() {
        if (mapBitmap == null) {
            return;
        }

        int viewW = getWidth();
        int viewH = getHeight();
        if (viewW == 0 || viewH == 0) {
            return;
        }

        RectF focusRect = hasConfiguredBounds
                ? mapRectToBitmapRect(configuredMinX, configuredMaxX, configuredMinY, configuredMaxY)
                : null;

        float bw = focusRect == null ? mapBitmap.getWidth() : focusRect.width();
        float bh = focusRect == null ? mapBitmap.getHeight() : focusRect.height();
        if (bw <= 0 || bh <= 0) {
            return;
        }
        scale = Math.min(viewW / bw, viewH / bh);
        if (scale > MAX_RECENTER_SCALE) {
            scale = MAX_RECENTER_SCALE;
        }
        if (focusRect == null) {
            translateX = (viewW - bw * scale) / 2f;
            translateY = (viewH - bh * scale) / 2f;
        } else {
            translateX = (viewW - bw * scale) / 2f - focusRect.left * scale;
            translateY = (viewH - bh * scale) / 2f - focusRect.top * scale;
        }
        invalidate();
    }

    public void clear() {
        if (mapBitmap != null) {
            mapBitmap.recycle();
            mapBitmap = null;
        }
        lastBitmapWidth = 0;
        lastBitmapHeight = 0;
        lastResolution = 0.0;
        lastUnknownCount = 0;
        lastFreeCount = 0;
        lastOccupiedCount = 0;
        hasConfiguredAreaStats = false;
        configuredUnknownCount = 0;
        configuredFreeCount = 0;
        configuredOccupiedCount = 0;
        hasKnownCells = false;
        knownWidthMeters = 0.0;
        knownHeightMeters = 0.0;
        lastUpdateTimeMs = 0;
        updateCount = 0;
        lastRenderDurationMs = 0;
        invalidate();
    }

    public boolean hasMap() {
        return mapBitmap != null;
    }

    private void rebuildBitmap(OccupancyGrid grid, int width, int height, ChannelBuffer data) {
        long renderStart = SystemClock.elapsedRealtime();

        if (mapBitmap != null) {
            mapBitmap.recycle();
        }

        int unknownCount = 0;
        int freeCount = 0;
        int occupiedCount = 0;
        int configuredUnknown = 0;
        int configuredFree = 0;
        int configuredOccupied = 0;
        boolean foundKnown = false;
        int minKnownX = width;
        int minKnownY = height;
        int maxKnownX = -1;
        int maxKnownY = -1;
        int[] pixels = new int[width * height];
        lastGridData = new byte[width * height];

        lastResolution = grid.getInfo().getResolution();
        lastOriginX = grid.getInfo().getOrigin().getPosition().getX();
        lastOriginY = grid.getInfo().getOrigin().getPosition().getY();

        boolean countConfiguredArea = false;
        int configuredMinCellX = 0;
        int configuredMaxCellX = -1;
        int configuredMinCellY = 0;
        int configuredMaxCellY = -1;
        if (hasConfiguredBounds && lastResolution > 0.0) {
            configuredMinCellX = Math.max(0, (int) Math.floor((configuredMinX - lastOriginX) / lastResolution));
            configuredMaxCellX = Math.min(width - 1, (int) Math.ceil((configuredMaxX - lastOriginX) / lastResolution) - 1);
            configuredMinCellY = Math.max(0, (int) Math.floor((configuredMinY - lastOriginY) / lastResolution));
            configuredMaxCellY = Math.min(height - 1, (int) Math.ceil((configuredMaxY - lastOriginY) / lastResolution) - 1);
            countConfiguredArea = configuredMinCellX <= configuredMaxCellX
                    && configuredMinCellY <= configuredMaxCellY;
        }

        for (int y = 0; y < height; y++) {
            for (int x = 0; x < width; x++) {
                int index = y * width + x;
                int value = readOccupancyValue(data, index);
                lastGridData[index] = (byte) value;

                if (value < 0) {
                    unknownCount++;
                } else if (value == 0) {
                    freeCount++;
                    foundKnown = true;
                } else {
                    occupiedCount++;
                    foundKnown = true;
                }

                if (value >= 0) {
                    if (x < minKnownX) {
                        minKnownX = x;
                    }
                    if (x > maxKnownX) {
                        maxKnownX = x;
                    }
                    if (y < minKnownY) {
                        minKnownY = y;
                    }
                    if (y > maxKnownY) {
                        maxKnownY = y;
                    }
                }

                if (countConfiguredArea
                        && x >= configuredMinCellX
                        && x <= configuredMaxCellX
                        && y >= configuredMinCellY
                        && y <= configuredMaxCellY) {
                    if (value < 0) {
                        configuredUnknown++;
                    } else if (value == 0) {
                        configuredFree++;
                    } else {
                        configuredOccupied++;
                    }
                }

                int color = occupancyToColor(value);
                int drawY = height - 1 - y;
                pixels[drawY * width + x] = color;
            }
        }

        mapBitmap = Bitmap.createBitmap(width, height, Bitmap.Config.ARGB_8888);
        mapBitmap.setPixels(pixels, 0, width, 0, 0, width, height);

        lastBitmapWidth = width;
        lastBitmapHeight = height;
        lastUnknownCount = unknownCount;
        lastFreeCount = freeCount;
        lastOccupiedCount = occupiedCount;
        hasConfiguredAreaStats = countConfiguredArea;
        configuredUnknownCount = configuredUnknown;
        configuredFreeCount = configuredFree;
        configuredOccupiedCount = configuredOccupied;
        hasKnownCells = foundKnown;
        if (foundKnown) {
            knownMinX = minKnownX;
            knownMinY = minKnownY;
            knownMaxX = maxKnownX;
            knownMaxY = maxKnownY;
            knownWidthMeters = (maxKnownX - minKnownX + 1) * lastResolution;
            knownHeightMeters = (maxKnownY - minKnownY + 1) * lastResolution;
        } else {
            knownWidthMeters = 0.0;
            knownHeightMeters = 0.0;
        }
        lastUpdateTimeMs = SystemClock.elapsedRealtime();
        updateCount++;
        lastRenderDurationMs = SystemClock.elapsedRealtime() - renderStart;

        rebuildCachedPlanPath();
        invalidate();
    }

    private void rebuildCachedPlanPath() {
        if (lastMoveBasePlanRos == null || mapBitmap == null || lastResolution <= 0.0) {
            cachedPlanPath = null;
            moveBasePlanPoseCount = 0;
            return;
        }

        List<PoseStamped> poses = lastMoveBasePlanRos.getPoses();
        if (poses == null || poses.isEmpty()) {
            cachedPlanPath = null;
            moveBasePlanPoseCount = 0;
            return;
        }

        android.graphics.Path path = new android.graphics.Path();
        int validPoints = 0;
        boolean hasStart = false;
        for (PoseStamped pose : poses) {
            if (pose == null || pose.getPose() == null || pose.getPose().getPosition() == null) {
                continue;
            }
            float[] bitmapPoint = mapWorldToBitmap(
                    pose.getPose().getPosition().getX(),
                    pose.getPose().getPosition().getY());
            if (bitmapPoint == null) {
                continue;
            }
            if (!hasStart) {
                path.moveTo(bitmapPoint[0], bitmapPoint[1]);
                hasStart = true;
            } else {
                path.lineTo(bitmapPoint[0], bitmapPoint[1]);
            }
            validPoints++;
        }

        if (validPoints < 2) {
            cachedPlanPath = null;
            moveBasePlanPoseCount = 0;
        } else {
            cachedPlanPath = path;
            moveBasePlanPoseCount = validPoints;
        }
    }

    private int readOccupancyValue(ChannelBuffer data, int index) {
        return data.getByte(index);
    }

    private int occupancyToColor(int value) {
        if (value < 0) {
            return Color.rgb(150, 150, 150);
        } else if (value == 0) {
            return Color.WHITE;
        } else {
            int c = 255 - Math.min(100, value) * 255 / 100;
            return Color.rgb(c, c, c);
        }
    }

    @Override
    protected void onDraw(Canvas canvas) {
        super.onDraw(canvas);

        if (mapBitmap == null) {
            return;
        }

        canvas.save();
        canvas.translate(translateX, translateY);
        canvas.scale(scale, scale);
        canvas.drawBitmap(mapBitmap, 0, 0, paint);
        configuredBoundsPaint.setStrokeWidth(OVERLAY_STROKE_PX / scale);
        knownBoundsPaint.setStrokeWidth(OVERLAY_STROKE_PX / scale);
        drawConfiguredBounds(canvas);
        drawKnownBounds(canvas);
        drawMoveBasePlan(canvas);
        drawNavPoint(canvas, pointA, pointAPaint, "A");
        drawNavPoint(canvas, pointB, pointBPaint, "B");
        drawMissionWaypoints(canvas);
        drawRobotPose(canvas);
        canvas.restore();
    }

    private void drawMissionWaypoints(Canvas canvas) {
        if (missionWaypoints.isEmpty() || mapBitmap == null || lastResolution <= 0.0) {
            return;
        }

        for (MissionWaypointMarker marker : missionWaypoints) {
            float[] bitmapPoint = mapWorldToBitmap(marker.x, marker.y);
            if (bitmapPoint == null) {
                continue;
            }
            float bx = bitmapPoint[0];
            float by = bitmapPoint[1];
            float r = 8.0f / scale;
            Paint fillPaint;
            switch (marker.state) {
                case CURRENT:
                    fillPaint = missionCurrentFillPaint;
                    break;
                case COMPLETED:
                    fillPaint = missionCompletedPaint;
                    break;
                case FAILED:
                    fillPaint = missionFailedPaint;
                    break;
                case PENDING:
                default:
                    fillPaint = missionPendingPaint;
                    break;
            }
            canvas.drawCircle(bx, by, r, fillPaint);
            if (marker.state == MissionWaypointState.CURRENT) {
                missionCurrentStrokePaint.setStrokeWidth(3.0f / scale);
                canvas.drawCircle(bx, by, r + 3.0f / scale, missionCurrentStrokePaint);
            }
            missionNumberPaint.setTextSize(12.0f / scale);
            canvas.drawText(String.valueOf(marker.number), bx, by + 4.0f / scale, missionNumberPaint);
        }
    }

    private void drawRobotPose(Canvas canvas) {
        if (!hasRobotPose || robotPoint == null || mapBitmap == null || lastResolution <= 0.0) {
            return;
        }

        float[] bitmapPoint = mapWorldToBitmap(robotPoint.x, robotPoint.y);
        if (bitmapPoint == null) {
            return;
        }
        float bx = bitmapPoint[0];
        float by = bitmapPoint[1];

        float r = 7.0f / scale;
        canvas.drawCircle(bx, by, r, robotPaint);

        float len = 18.0f / scale;
        float endX = bx + (float) (Math.cos(robotYaw) * len);
        float endY = by - (float) (Math.sin(robotYaw) * len);

        robotArrowPaint.setStrokeWidth(3.0f / scale);
        canvas.drawLine(bx, by, endX, endY, robotArrowPaint);
    }

    private void drawMoveBasePlan(Canvas canvas) {
        if (cachedPlanPath == null || moveBasePlanPoseCount < 2) {
            return;
        }

        planPaint.setStrokeWidth(PLAN_STROKE_PX / scale);
        canvas.drawPath(cachedPlanPath, planPaint);
    }

    private float[] mapWorldToBitmap(double worldX, double worldY) {
        if (mapBitmap == null || lastResolution <= 0.0) {
            return null;
        }
        float bx = (float) ((worldX - lastOriginX) / lastResolution);
        float by = (float) (mapBitmap.getHeight() - (worldY - lastOriginY) / lastResolution);
        return new float[]{bx, by};
    }

    private void drawNavPoint(Canvas canvas, MapPoint point, Paint fillPaint, String label) {
        if (point == null || mapBitmap == null || lastResolution <= 0.0) {
            return;
        }

        float[] bitmapPoint = mapWorldToBitmap(point.x, point.y);
        if (bitmapPoint == null) {
            return;
        }
        float bx = bitmapPoint[0];
        float by = bitmapPoint[1];

        float r = 8.0f / scale;
        canvas.drawCircle(bx, by, r, fillPaint);

        pointTextPaint.setTextSize(12.0f / scale);
        canvas.drawText(label, bx, by + 4.0f / scale, pointTextPaint);
    }

    private void drawConfiguredBounds(Canvas canvas) {
        if (!hasConfiguredBounds || mapBitmap == null || lastResolution <= 0.0) {
            return;
        }
        RectF rect = mapRectToBitmapRect(configuredMinX, configuredMaxX, configuredMinY, configuredMaxY);
        canvas.drawRect(rect, configuredBoundsPaint);
    }

    private void drawKnownBounds(Canvas canvas) {
        if (!hasKnownCells || mapBitmap == null) {
            return;
        }
        RectF rect = new RectF(
                knownMinX,
                mapBitmap.getHeight() - 1 - knownMaxY,
                knownMaxX + 1,
                mapBitmap.getHeight() - knownMinY);
        canvas.drawRect(rect, knownBoundsPaint);
    }

    private RectF mapRectToBitmapRect(double minX, double maxX, double minY, double maxY) {
        float left = (float) ((minX - lastOriginX) / lastResolution);
        float right = (float) ((maxX - lastOriginX) / lastResolution);
        float top = (float) (mapBitmap.getHeight() - (maxY - lastOriginY) / lastResolution);
        float bottom = (float) (mapBitmap.getHeight() - (minY - lastOriginY) / lastResolution);
        return new RectF(left, top, right, bottom);
    }

    @Override
    public boolean onTouchEvent(MotionEvent event) {
        scaleGestureDetector.onTouchEvent(event);

        switch (event.getActionMasked()) {
            case MotionEvent.ACTION_DOWN:
                downX = event.getX();
                downY = event.getY();
                lastX = downX;
                lastY = downY;
                dragging = true;
                break;
            case MotionEvent.ACTION_MOVE:
                if (dragging && !scaleGestureDetector.isInProgress() && event.getPointerCount() == 1) {
                    float dx = event.getX() - lastX;
                    float dy = event.getY() - lastY;
                    translateX += dx;
                    translateY += dy;
                    lastX = event.getX();
                    lastY = event.getY();
                    invalidate();
                }
                break;
            case MotionEvent.ACTION_UP:
            case MotionEvent.ACTION_CANCEL:
                float dx = event.getX() - downX;
                float dy = event.getY() - downY;
                if (Math.sqrt(dx * dx + dy * dy) < TAP_SLOP_PX && mapTapListener != null) {
                    MapPoint point = screenToMap(event.getX(), event.getY());
                    if (point != null) {
                        mapTapListener.onMapTapped(point);
                    }
                }
                dragging = false;
                break;
            default:
                break;
        }

        return true;
    }

    private class ScaleListener extends ScaleGestureDetector.SimpleOnScaleGestureListener {
        @Override
        public boolean onScale(ScaleGestureDetector detector) {
            scale *= detector.getScaleFactor();
            if (scale < MIN_SCALE) {
                scale = MIN_SCALE;
            } else if (scale > MAX_SCALE) {
                scale = MAX_SCALE;
            }
            invalidate();
            return true;
        }
    }
}
