package com.shoalhavenindependence.casenotes;

import android.app.Activity;
import androidx.activity.result.ActivityResultLauncher;
import androidx.activity.result.IntentSenderRequest;
import androidx.activity.result.contract.ActivityResultContracts;
import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;
import com.google.android.gms.auth.GoogleAuthUtil;
import com.google.android.gms.auth.api.identity.AuthorizationRequest;
import com.google.android.gms.auth.api.identity.AuthorizationResult;
import com.google.android.gms.auth.api.identity.Identity;
import com.google.android.gms.common.api.Scope;
import java.util.Collections;

/**
 * Lets the app ask for access to the files it creates in the person's own Google Drive
 * (the drive.file permission) and hands back a short-lived access token for the Drive
 * and Sheets web APIs. Google matches the app by package name and signing certificate,
 * so no client ID is needed here.
 */
@CapacitorPlugin(name = "GoogleDrive")
public class GoogleDrivePlugin extends Plugin {

    private static final String DRIVE_FILE = "https://www.googleapis.com/auth/drive.file";

    private ActivityResultLauncher<IntentSenderRequest> consentLauncher;
    private PluginCall pendingCall;

    @Override
    public void load() {
        consentLauncher = getActivity().registerForActivityResult(
            new ActivityResultContracts.StartIntentSenderForResult(),
            res -> {
                PluginCall call = pendingCall;
                pendingCall = null;
                if (call == null) return;
                if (res.getResultCode() != Activity.RESULT_OK || res.getData() == null) {
                    call.reject("Sign-in was cancelled", "cancelled");
                    return;
                }
                try {
                    AuthorizationResult result = Identity.getAuthorizationClient(getActivity())
                        .getAuthorizationResultFromIntent(res.getData());
                    resolveToken(call, result);
                } catch (Exception e) {
                    call.reject("Google sign-in failed", "failed", e);
                }
            }
        );
    }

    @PluginMethod
    public void authorize(PluginCall call) {
        boolean interactive = Boolean.TRUE.equals(call.getBoolean("interactive", false));
        AuthorizationRequest request = AuthorizationRequest.builder()
            .setRequestedScopes(Collections.singletonList(new Scope(DRIVE_FILE)))
            .build();
        Identity.getAuthorizationClient(getActivity())
            .authorize(request)
            .addOnSuccessListener(result -> {
                if (!result.hasResolution()) {
                    resolveToken(call, result);
                } else if (!interactive || result.getPendingIntent() == null) {
                    call.reject("Google needs the person to sign in again", "consent_required");
                } else {
                    if (pendingCall != null) pendingCall.reject("Replaced by a newer sign-in", "cancelled");
                    pendingCall = call;
                    consentLauncher.launch(
                        new IntentSenderRequest.Builder(result.getPendingIntent().getIntentSender()).build()
                    );
                }
            })
            .addOnFailureListener(e -> call.reject("Google sign-in failed: " + e.getMessage(), "failed", e));
    }

    /** Drops a token Google has stopped accepting, so the next authorize() fetches a fresh one. */
    @PluginMethod
    public void clearToken(PluginCall call) {
        String token = call.getString("token");
        if (token == null || token.isEmpty()) {
            call.resolve();
            return;
        }
        new Thread(() -> {
            try {
                GoogleAuthUtil.clearToken(getContext(), token);
            } catch (Exception ignored) {
            }
            call.resolve();
        }).start();
    }

    private void resolveToken(PluginCall call, AuthorizationResult result) {
        String token = result.getAccessToken();
        if (token == null || token.isEmpty()) {
            call.reject("Google did not return access", "failed");
            return;
        }
        JSObject out = new JSObject();
        out.put("accessToken", token);
        call.resolve(out);
    }
}
