package com.robotca.ControlApp.Views;

import android.content.Context;
import android.util.AttributeSet;
import android.view.LayoutInflater;
import android.view.MotionEvent;
import android.view.View;
import android.view.ViewConfiguration;
import android.view.ViewGroup;
import android.view.ViewTreeObserver;
import android.view.animation.DecelerateInterpolator;
import android.widget.FrameLayout;
import android.widget.LinearLayout;

import com.robotca.ControlApp.R;

/**
 * AssistiveTouch-style floating menu for SLAM navigation controls.
 * Collapsed: small draggable circle. Tap to expand menu panel to the left.
 */
public class SlamFloatingNavMenu extends FrameLayout {

    private static final float DEFAULT_Y_RATIO = 0.35f;

    private LinearLayout menuPanel;
    private LinearLayout rootRow;
    private View anchor;
    private boolean expanded;
    private boolean positionInitialized;
    private boolean panelOnLeftSide = true;

    private float touchStartRawX;
    private float touchStartRawY;
    private float viewStartX;
    private float viewStartY;
    private boolean dragging;
    private int touchSlop;

    public SlamFloatingNavMenu(Context context) {
        super(context);
        init(context);
    }

    public SlamFloatingNavMenu(Context context, AttributeSet attrs) {
        super(context, attrs);
        init(context);
    }

    public SlamFloatingNavMenu(Context context, AttributeSet attrs, int defStyleAttr) {
        super(context, attrs, defStyleAttr);
        init(context);
    }

    private void init(Context context) {
        touchSlop = ViewConfiguration.get(context).getScaledTouchSlop();
        LayoutInflater.from(context).inflate(R.layout.view_slam_floating_nav_menu, this, true);
        rootRow = (LinearLayout) findViewById(R.id.slam_float_root);
        menuPanel = (LinearLayout) findViewById(R.id.slam_float_menu_panel);
        anchor = findViewById(R.id.slam_float_anchor);
        anchor.setOnTouchListener(new AnchorTouchListener());
    }

    public boolean isExpanded() {
        return expanded;
    }

    public void setExpanded(boolean expand) {
        if (expanded == expand) {
            return;
        }
        expanded = expand;
        menuPanel.setVisibility(expand ? VISIBLE : GONE);
        if (expand) {
            menuPanel.setAlpha(0f);
            menuPanel.setScaleX(0.85f);
            menuPanel.setScaleY(0.85f);
            menuPanel.animate()
                    .alpha(1f)
                    .scaleX(1f)
                    .scaleY(1f)
                    .setDuration(180)
                    .setInterpolator(new DecelerateInterpolator())
                    .start();
            post(new Runnable() {
                @Override
                public void run() {
                    clampToParent();
                }
            });
        }
    }

    public void toggleExpanded() {
        setExpanded(!expanded);
    }

    public void setExportVisible(boolean visible) {
        View exportButton = findViewById(R.id.slam_map_export_button);
        if (exportButton != null) {
            exportButton.setVisibility(visible ? VISIBLE : GONE);
        }
    }

    @Override
    protected void onAttachedToWindow() {
        super.onAttachedToWindow();
        getViewTreeObserver().addOnGlobalLayoutListener(new ViewTreeObserver.OnGlobalLayoutListener() {
            @Override
            public void onGlobalLayout() {
                if (positionInitialized) {
                    getViewTreeObserver().removeOnGlobalLayoutListener(this);
                    return;
                }
                View parent = (View) getParent();
                if (parent == null || parent.getWidth() == 0 || getWidth() == 0) {
                    return;
                }
                initDefaultPosition();
                getViewTreeObserver().removeOnGlobalLayoutListener(this);
            }
        });
    }

    private void initDefaultPosition() {
        View parent = (View) getParent();
        if (parent == null || parent.getWidth() == 0) {
            return;
        }
        float x = parent.getWidth() - getWidth() - dp(12);
        float y = parent.getHeight() * DEFAULT_Y_RATIO - getHeight() / 2f;
        setX(Math.max(dp(8), x));
        setY(Math.max(dp(8), y));
        positionInitialized = true;
        updatePanelSide();
    }

    private void updatePanelSide() {
        if (rootRow == null || menuPanel == null || anchor == null) {
            return;
        }
        View parent = (View) getParent();
        if (parent == null || parent.getWidth() == 0) {
            return;
        }

        boolean panelOnLeft = getX() + getWidth() / 2f > parent.getWidth() / 2f;
        if (panelOnLeft == panelOnLeftSide) {
            applyPanelMargin(panelOnLeft);
            return;
        }
        panelOnLeftSide = panelOnLeft;

        safeRemoveFromParent(menuPanel);
        safeRemoveFromParent(anchor);
        if (panelOnLeft) {
            rootRow.addView(menuPanel);
            rootRow.addView(anchor);
        } else {
            rootRow.addView(anchor);
            rootRow.addView(menuPanel);
        }
        applyPanelMargin(panelOnLeft);
    }

    private void applyPanelMargin(boolean panelOnLeft) {
        LinearLayout.LayoutParams lp = (LinearLayout.LayoutParams) menuPanel.getLayoutParams();
        if (lp == null) {
            return;
        }
        if (panelOnLeft) {
            lp.setMarginStart(0);
            lp.setMarginEnd(dp(6));
        } else {
            lp.setMarginStart(dp(6));
            lp.setMarginEnd(0);
        }
        menuPanel.setLayoutParams(lp);
    }

    private void safeRemoveFromParent(View view) {
        if (view == null) {
            return;
        }
        ViewGroup parent = (ViewGroup) view.getParent();
        if (parent != null) {
            parent.removeView(view);
        }
    }

    private void moveTo(float x, float y) {
        View parent = (View) getParent();
        if (parent == null) {
            return;
        }
        float maxX = Math.max(0, parent.getWidth() - getWidth());
        float maxY = Math.max(0, parent.getHeight() - getHeight());
        setX(Math.max(0, Math.min(x, maxX)));
        setY(Math.max(0, Math.min(y, maxY)));
    }

    private void clampToParent() {
        moveTo(getX(), getY());
    }

    private int dp(int value) {
        float density = getResources().getDisplayMetrics().density;
        return Math.round(value * density);
    }

    private final class AnchorTouchListener implements OnTouchListener {
        @Override
        public boolean onTouch(View v, MotionEvent event) {
            switch (event.getActionMasked()) {
                case MotionEvent.ACTION_DOWN:
                    touchStartRawX = event.getRawX();
                    touchStartRawY = event.getRawY();
                    viewStartX = getX();
                    viewStartY = getY();
                    dragging = false;
                    return true;
                case MotionEvent.ACTION_MOVE:
                    float dx = event.getRawX() - touchStartRawX;
                    float dy = event.getRawY() - touchStartRawY;
                    if (!dragging && (Math.abs(dx) > touchSlop || Math.abs(dy) > touchSlop)) {
                        dragging = true;
                    }
                    if (dragging) {
                        moveTo(viewStartX + dx, viewStartY + dy);
                        updatePanelSide();
                    }
                    return true;
                case MotionEvent.ACTION_UP:
                case MotionEvent.ACTION_CANCEL:
                    if (!dragging) {
                        toggleExpanded();
                    } else {
                        clampToParent();
                    }
                    dragging = false;
                    return true;
                default:
                    return false;
            }
        }
    }
}
