package com.finance.finance_tracker_app

import android.os.Build
import android.view.WindowManager
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine

class MainActivity : FlutterActivity() {
    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        
        // Enforce the highest refresh rate (90Hz, 120Hz, etc.) supported by the display
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            try {
                val layoutParams = window.attributes
                val display = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
                    this.display
                } else {
                    @Suppress("DEPRECATION")
                    window.windowManager.defaultDisplay
                }
                
                val supportedModes = display?.supportedModes
                var highestMode = display?.mode
                
                if (supportedModes != null) {
                    for (mode in supportedModes) {
                        if (highestMode == null || mode.refreshRate > highestMode.refreshRate) {
                            highestMode = mode
                        }
                    }
                }
                
                if (highestMode != null) {
                    layoutParams.preferredDisplayModeId = highestMode.modeId
                    window.attributes = layoutParams
                }
            } catch (e: Exception) {
                // Fail silently if display manager is not available
            }
        }
    }
}
