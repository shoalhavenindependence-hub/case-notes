package com.shoalhavenindependence.casenotes;

import android.content.Intent;
import android.os.Build;
import android.os.Bundle;
import android.speech.RecognitionListener;
import android.speech.RecognizerIntent;
import android.speech.SpeechRecognizer;
import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;
import java.util.ArrayList;

/**
 * Continuous dictation for the Dictate button, so the Play app listens the same way
 * Chrome does in the web app: one beep when it starts, and it keeps listening through pauses.
 * On Android 13 and later it asks for a "segmented session" (keeps going through pauses and
 * sends each phrase as it finishes). On older phones Android stops at each pause and the app
 * starts it again.
 * Events ("dictation"): {type:"partial"|"final", text}, {type:"error", code}, {type:"end"}.
 */
@CapacitorPlugin(name = "Dictation")
public class DictationPlugin extends Plugin {

    private SpeechRecognizer recognizer;
    private int session = 0;

    @PluginMethod
    public void start(PluginCall call) {
        final String lang = call.getString("lang", "en-AU");
        getActivity().runOnUiThread(() -> {
            try {
                destroy();
                if (!SpeechRecognizer.isRecognitionAvailable(getContext())) {
                    call.reject("not-available");
                    return;
                }
                final int mine = ++session;
                recognizer = SpeechRecognizer.createSpeechRecognizer(getContext());
                recognizer.setRecognitionListener(new Listener(mine));
                Intent intent = new Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH);
                intent.putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM);
                intent.putExtra(RecognizerIntent.EXTRA_LANGUAGE, lang);
                intent.putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 1);
                intent.putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, true);
                intent.putExtra(RecognizerIntent.EXTRA_CALLING_PACKAGE, getContext().getPackageName());
                intent.putExtra("android.speech.extra.DICTATION_MODE", true);
                if (Build.VERSION.SDK_INT >= 33) {
                    intent.putExtra(RecognizerIntent.EXTRA_SEGMENTED_SESSION,
                        RecognizerIntent.EXTRA_SPEECH_INPUT_COMPLETE_SILENCE_LENGTH_MILLIS);
                    intent.putExtra(RecognizerIntent.EXTRA_SPEECH_INPUT_COMPLETE_SILENCE_LENGTH_MILLIS, 20000L);
                }
                recognizer.startListening(intent);
                call.resolve();
            } catch (Exception e) {
                call.reject("start-failed");
            }
        });
    }

    @PluginMethod
    public void stop(PluginCall call) {
        getActivity().runOnUiThread(() -> {
            try { if (recognizer != null) recognizer.stopListening(); } catch (Exception ignored) {}
            call.resolve();
        });
    }

    @PluginMethod
    public void abort(PluginCall call) {
        getActivity().runOnUiThread(() -> {
            session++;
            destroy();
            call.resolve();
        });
    }

    private void destroy() {
        if (recognizer != null) {
            try { recognizer.cancel(); } catch (Exception ignored) {}
            try { recognizer.destroy(); } catch (Exception ignored) {}
            recognizer = null;
        }
    }

    private void send(int mine, String type, String text, Integer code) {
        if (mine != session) return;
        JSObject o = new JSObject();
        o.put("type", type);
        if (text != null) o.put("text", text);
        if (code != null) o.put("code", code);
        notifyListeners("dictation", o);
    }

    private static String first(Bundle b) {
        if (b == null) return null;
        ArrayList<String> m = b.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION);
        return (m != null && !m.isEmpty()) ? m.get(0) : null;
    }

    private class Listener implements RecognitionListener {
        private final int mine;
        private boolean ended = false;
        Listener(int mine) { this.mine = mine; }

        private void end() { if (!ended) { ended = true; send(mine, "end", null, null); } }

        @Override public void onReadyForSpeech(Bundle params) {}
        @Override public void onBeginningOfSpeech() {}
        @Override public void onRmsChanged(float rmsdB) {}
        @Override public void onBufferReceived(byte[] buffer) {}
        @Override public void onEndOfSpeech() {}
        @Override public void onEvent(int eventType, Bundle params) {}

        @Override public void onPartialResults(Bundle b) {
            String t = first(b);
            if (t != null && !t.isEmpty()) send(mine, "partial", t, null);
        }

        // Android 13+: one finished phrase in a session that keeps listening.
        @Override public void onSegmentResults(Bundle b) {
            String t = first(b);
            if (t != null && !t.isEmpty()) send(mine, "final", t, null);
        }

        @Override public void onEndOfSegmentedSession() { end(); }

        @Override public void onResults(Bundle b) {
            String t = first(b);
            if (t != null && !t.isEmpty()) send(mine, "final", t, null);
            end();
        }

        @Override public void onError(int error) {
            send(mine, "error", null, error);
            end();
        }
    }
}
