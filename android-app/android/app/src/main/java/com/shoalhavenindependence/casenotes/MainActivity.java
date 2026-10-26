package com.shoalhavenindependence.casenotes;

import android.os.Bundle;
import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {
    @Override
    public void onCreate(Bundle savedInstanceState) {
        registerPlugin(GoogleDrivePlugin.class);
        registerPlugin(AppLockPlugin.class);
        super.onCreate(savedInstanceState);
    }
}
