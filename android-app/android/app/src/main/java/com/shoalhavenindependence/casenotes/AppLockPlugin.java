package com.shoalhavenindependence.casenotes;

import androidx.biometric.BiometricManager;
import androidx.biometric.BiometricPrompt;
import androidx.core.content.ContextCompat;
import androidx.fragment.app.FragmentActivity;
import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;

/**
 * Shows Android's own unlock prompt (fingerprint, face, or the phone's PIN/pattern)
 * for the app's optional lock screen.
 */
@CapacitorPlugin(name = "AppLock")
public class AppLockPlugin extends Plugin {

    private static final int AUTHENTICATORS =
        BiometricManager.Authenticators.BIOMETRIC_WEAK | BiometricManager.Authenticators.DEVICE_CREDENTIAL;

    @PluginMethod
    public void available(PluginCall call) {
        int result = BiometricManager.from(getContext()).canAuthenticate(AUTHENTICATORS);
        JSObject out = new JSObject();
        out.put("available", result == BiometricManager.BIOMETRIC_SUCCESS);
        call.resolve(out);
    }

    @PluginMethod
    public void verify(PluginCall call) {
        String reason = call.getString("reason", "Unlock your case notes");
        getActivity().runOnUiThread(() -> {
            FragmentActivity activity = (FragmentActivity) getActivity();
            BiometricPrompt prompt = new BiometricPrompt(
                activity,
                ContextCompat.getMainExecutor(activity),
                new BiometricPrompt.AuthenticationCallback() {
                    @Override
                    public void onAuthenticationSucceeded(BiometricPrompt.AuthenticationResult result) {
                        call.resolve();
                    }

                    @Override
                    public void onAuthenticationError(int errorCode, CharSequence errString) {
                        call.reject(String.valueOf(errString), String.valueOf(errorCode));
                    }
                }
            );
            BiometricPrompt.PromptInfo info = new BiometricPrompt.PromptInfo.Builder()
                .setTitle("Shift Case Notes")
                .setSubtitle(reason)
                .setAllowedAuthenticators(AUTHENTICATORS)
                .build();
            prompt.authenticate(info);
        });
    }
}
