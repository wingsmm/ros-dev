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
import org.jboss.netty.buffer.ChannelBuffer;

/**
 * Custom View for rendering a SLAM occupancy grid as a cached Bitmap.
 */
public class SlamMapView extends View {

    private static final float MIN_SCALE = 0.1f;
    private static final float MAX_SCALE = 10.0f;
    private static final float MAX_RECENTER_SCALE = 4.0f;
    private static final float OVERLAY_STROKE_PX = 2.0f;

    private Bitmap mapBitmap;
    private final Paint paint = new Paint(Paint.FILTER_BITMAP_FLAG);
    private final Paint configuredBoundsPaint = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint knownBoundsPaint = new Paint(Paint.ANTI_ALIAS_FLAG);

    private float scale = 1.0f;
    private float translateX = 0.0f;
    private float translateY = 0.0f;
    private float lastX;
    private float lastY;
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

        invalidate();
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
        canvas.restore();
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
                lastX = event.getX();
                lastY = event.getY();
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
