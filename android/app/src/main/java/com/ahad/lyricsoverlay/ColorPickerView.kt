package com.ahad.lyricsoverlay

import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.LinearGradient
import android.graphics.Paint
import android.graphics.Shader
import android.util.AttributeSet
import android.view.MotionEvent
import android.view.View
import kotlin.math.roundToInt

class ColorPickerView @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null,
    defStyleAttr: Int = 0
) : View(context, attrs, defStyleAttr) {

    private val hsv = floatArrayOf(260f, 0.68f, 1f)
    private val paint = Paint(Paint.ANTI_ALIAS_FLAG)
    private val markerPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        strokeWidth = dp(2f)
    }
    private var listener: ((Int) -> Unit)? = null
    private val hueColors = intArrayOf(
        Color.RED,
        Color.YELLOW,
        Color.GREEN,
        Color.CYAN,
        Color.BLUE,
        Color.MAGENTA,
        Color.RED
    )

    fun setOnColorChangedListener(newListener: ((Int) -> Unit)?) {
        listener = newListener
    }

    fun selectedColor(): Int = Color.HSVToColor(hsv)

    fun setColor(color: Int, notifyListener: Boolean = false) {
        Color.colorToHSV(color, hsv)
        invalidate()
        updateDescription()
        if (notifyListener) listener?.invoke(selectedColor())
    }

    override fun onMeasure(widthMeasureSpec: Int, heightMeasureSpec: Int) {
        val desiredWidth = dp(300f).roundToInt() + paddingLeft + paddingRight
        val desiredHeight = dp(250f).roundToInt() + paddingTop + paddingBottom
        setMeasuredDimension(
            resolveSize(desiredWidth, widthMeasureSpec),
            resolveSize(desiredHeight, heightMeasureSpec)
        )
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        val left = paddingLeft.toFloat()
        val right = (width - paddingRight).toFloat()
        val top = paddingTop.toFloat()
        val hueHeight = dp(28f)
        val gap = dp(14f)
        val hueTop = height - paddingBottom - hueHeight
        val squareBottom = hueTop - gap
        if (right <= left || squareBottom <= top) return

        val hueColor = Color.HSVToColor(floatArrayOf(hsv[0], 1f, 1f))
        paint.shader = LinearGradient(
            left,
            top,
            right,
            top,
            Color.WHITE,
            hueColor,
            Shader.TileMode.CLAMP
        )
        canvas.drawRoundRect(left, top, right, squareBottom, dp(9f), dp(9f), paint)

        paint.shader = LinearGradient(
            left,
            top,
            left,
            squareBottom,
            Color.TRANSPARENT,
            Color.BLACK,
            Shader.TileMode.CLAMP
        )
        canvas.drawRoundRect(left, top, right, squareBottom, dp(9f), dp(9f), paint)

        paint.shader = LinearGradient(
            left,
            hueTop,
            right,
            hueTop,
            hueColors,
            null,
            Shader.TileMode.CLAMP
        )
        canvas.drawRoundRect(left, hueTop, right, hueTop + hueHeight, dp(8f), dp(8f), paint)
        paint.shader = null

        val selectionX = left + hsv[1] * (right - left)
        val selectionY = top + (1f - hsv[2]) * (squareBottom - top)
        drawMarker(canvas, selectionX, selectionY, selectedColor(), dp(8f))

        val hueX = left + (hsv[0] / 360f) * (right - left)
        drawMarker(
            canvas,
            hueX,
            hueTop + hueHeight / 2f,
            Color.HSVToColor(floatArrayOf(hsv[0], 1f, 1f)),
            dp(7f)
        )
    }

    override fun onTouchEvent(event: MotionEvent): Boolean {
        if (event.actionMasked != MotionEvent.ACTION_DOWN &&
            event.actionMasked != MotionEvent.ACTION_MOVE &&
            event.actionMasked != MotionEvent.ACTION_UP
        ) {
            return super.onTouchEvent(event)
        }

        val left = paddingLeft.toFloat()
        val right = (width - paddingRight).toFloat()
        val top = paddingTop.toFloat()
        val hueHeight = dp(28f)
        val hueTop = height - paddingBottom - hueHeight
        val squareBottom = hueTop - dp(14f)

        if (event.y <= squareBottom) {
            hsv[1] = ((event.x - left) / (right - left)).coerceIn(0f, 1f)
            hsv[2] = (1f - (event.y - top) / (squareBottom - top)).coerceIn(0f, 1f)
        } else if (event.y >= hueTop - dp(7f)) {
            hsv[0] = (((event.x - left) / (right - left)).coerceIn(0f, 1f) * 360f)
        }

        invalidate()
        updateDescription()
        listener?.invoke(selectedColor())
        if (event.actionMasked == MotionEvent.ACTION_UP) performClick()
        return true
    }

    override fun performClick(): Boolean {
        super.performClick()
        return true
    }

    private fun drawMarker(canvas: Canvas, x: Float, y: Float, color: Int, radius: Float) {
        markerPaint.color = Color.WHITE
        markerPaint.strokeWidth = dp(4f)
        canvas.drawCircle(x, y, radius, markerPaint)
        markerPaint.color = if (AppUi.contrastTextColor(color) == Color.BLACK) Color.BLACK else Color.DKGRAY
        markerPaint.strokeWidth = dp(1.5f)
        canvas.drawCircle(x, y, radius, markerPaint)
    }

    private fun updateDescription() {
        val color = selectedColor()
        contentDescription = String.format(
            "Custom color #%02X%02X%02X",
            Color.red(color),
            Color.green(color),
            Color.blue(color)
        )
    }

    private fun dp(value: Float): Float = value * resources.displayMetrics.density
}
