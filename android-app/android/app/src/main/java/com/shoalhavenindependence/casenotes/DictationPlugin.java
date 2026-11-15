package com.shoalhavenindependence.casenotes;

import android.content.Intent;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.os.SystemClock;
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
 * Continuous dictation for the Dictate button.
 *
 * Android's speech recogniser stops at every pause. Instead of letting the web page restart it
 * (which raced with the recogniser shutting down and left Dictate "on" but deaf), this plugin keeps
 * one dictation going itself: as soon as Android finishes a phrase it hands the words over and
 * starts listening again straight away, recovers from "busy"/"no match"/network hiccups, and
 * restarts the recogniser if it ever goes silent. The page only sees one long dictation until Stop.
 *
 * Events ("dictation"): {type:"partial"|"final", text}, {type:"error", code}, {type:"end"}.
 */
@CapacitorPlugin(name = "Dictation")
public class DictationPlugin extends Plugin {

    private static final int MAX_ERRORS_IN_A_ROW = 12;
    private static final long WATCHDOG_MS = 8000;   // no sound level updates for this long = recogniser has died
    private static final long STOP_WAIT_MS = 2000;  // after Stop, wait this long for the last words

    private final Handler main = new Handler(Looper.getMainLooper());
    private SpeechRecognizer recognizer;
    private String lang = "en-AU";
    private boolean useLang = true;
    private boolean running = false;   // dictation is on (until Stop)
    private boolean stopping = false;  // Stop tapped, waiting for the last words
    private int session = 0;           // whole dictation (start .. end)
    private int attempt = 0;           // one listen of the recogniser
    private int errorsInRow = 0;
    private long lastAlive = 0;

    private final Runnable watchdog = new Runnable() {
        @Override public void run() {
            if (!running) return;
            if (SystemClock.elapsedRealtime() - lastAlive > WATCHDOG_MS) {
                // Android went quiet without telling us; start a fresh recogniser.
                recreate();
                listenSoon(100);
            }
            main.postDelayed(this, 1000);
        }
    };

    @PluginMethod
    public void start(PluginCall call) {
        final String l = call.getString("lang", "en-AU");
        main.post(() -> {
            try {
                endSession(false);
                if (!SpeechRecognizer.isRecognitionAvailable(getContext())) {
                    call.reject("not-available");
                    return;
                }
                lang = l;
                useLang = true;
                running = true;
                stopping = false;
                errorsInRow = 0;
                session++;
                recreate();
                listen();
                main.removeCallbacks(watchdog);
                main.postDelayed(watchdog, 1000);
                call.resolve();
            } catch (Exception e) {
                running = false;
                call.reject("start-failed");
            }
        });
    }

    /** Stop listening, but still deliver the words being spoken right now, then send "end". */
    @PluginMethod
    public void stop(PluginCall call) {
        main.post(() -> {
            if (running && !stopping) {
                stopping = true;
                main.removeCallbacks(watchdog);
                try { if (recognizer != null) recognizer.stopListening(); } catch (Exception ignored) {}
                final int s = session;
                main.postDelayed(() -> { if (s == session && running) endSession(true); }, STOP_WAIT_MS);
            }
            call.resolve();
        });
    }

    /** Stop straight away and throw away anything unfinished. Sends no more events. */
    @PluginMethod
    public void abort(PluginCall call) {
        main.post(() -> {
            session++;
            endSession(false);
            call.resolve();
        });
    }

    @Override
    protected void handleOnDestroy() {
        session++;
        endSession(false);
        super.handleOnDestroy();
    }

    private void endSession(boolean tell) {
        boolean was = running;
        running = false;
        stopping = false;
        attempt++;
        main.removeCallbacks(watchdog);
        destroy();
        if (tell && was) send(session, "end", null, null);
    }

    private void recreate() {
        destroy();
        recognizer = SpeechRecognizer.createSpeechRecognizer(getContext());
    }

    private void destroy() {
        if (recognizer != null) {
            try { recognizer.cancel(); } catch (Exception ignored) {}
            try { recognizer.destroy(); } catch (Exception ignored) {}
            recognizer = null;
        }
    }

    private void listenSoon(long ms) {
        final int a = ++attempt;
        main.postDelayed(() -> { if (a == attempt && running && !stopping) listen(); }, ms);
    }

    private void listen() {
        if (!running || stopping) return;
        if (recognizer == null) recognizer = SpeechRecognizer.createSpeechRecognizer(getContext());
        final int a = ++attempt;
        recognizer.setRecognitionListener(new Listener(session, a));
        Intent intent = new Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH);
        intent.putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM);
        if (useLang) intent.putExtra(RecognizerIntent.EXTRA_LANGUAGE, lang);
        intent.putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 1);
        intent.putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, true);
        intent.putExtra(RecognizerIntent.EXTRA_CALLING_PACKAGE, getContext().getPackageName());
        intent.putExtra("android.speech.extra.DICTATION_MODE", true);
        // Ask Android to wait a little longer before deciding a pause is the end (some phones ignore this).
        intent.putExtra(RecognizerIntent.EXTRA_SPEECH_INPUT_COMPLETE_SILENCE_LENGTH_MILLIS, 2500L);
        intent.putExtra(RecognizerIntent.EXTRA_SPEECH_INPUT_POSSIBLY_COMPLETE_SILENCE_LENGTH_MILLIS, 2000L);
        lastAlive = SystemClock.elapsedRealtime();
        try {
            recognizer.startListening(intent);
        } catch (Exception e) {
            failed(SpeechRecognizer.ERROR_CLIENT);
        }
    }

    /** Something went wrong with one listen: try again, unless it can't work. */
    private void failed(int error) {
        if (!running) return;
        if (stopping) { endSession(true); return; }
        switch (error) {
            case SpeechRecognizer.ERROR_INSUFFICIENT_PERMISSIONS:
            case SpeechRecognizer.ERROR_AUDIO:
                send(session, "error", null, error);
                endSession(true);
                return;
            case 12: // language not supported
            case 13: // language unavailable
                if (useLang) { useLang = false; listenSoon(100); return; }
                break;
            case SpeechRecognizer.ERROR_NO_MATCH:
            case SpeechRecognizer.ERROR_SPEECH_TIMEOUT:
                // Just a quiet moment. Listen again (the page decides when it's been quiet too long).
                listenSoon(50);
                return;
            default:
                break;
        }
        errorsInRow++;
        if (errorsInRow >= MAX_ERRORS_IN_A_ROW) {
            send(session, "error", null, error);
            endSession(true);
            return;
        }
        boolean network = error == SpeechRecognizer.ERROR_NETWORK || error == SpeechRecognizer.ERROR_NETWORK_TIMEOUT
            || error == SpeechRecognizer.ERROR_SERVER || error == 11;
        // Busy / client errors and anything unknown: start with a fresh recogniser.
        recreate();
        listenSoon(network ? 1000 : 300);
    }

    private void send(int s, String type, String text, Integer code) {
        if (s != session) return;
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
        private final int s, a;
        private boolean done = false;
        Listener(int s, int a) { this.s = s; this.a = a; }
        private boolean mine() { return s == session && running && !done; }

        @Override public void onReadyForSpeech(Bundle params) { if (mine()) lastAlive = SystemClock.elapsedRealtime(); }
        @Override public void onBeginningOfSpeech() { if (mine()) lastAlive = SystemClock.elapsedRealtime(); }
        @Override public void onRmsChanged(float rmsdB) { if (mine()) lastAlive = SystemClock.elapsedRealtime(); }
        @Override public void onBufferReceived(byte[] buffer) {}
        @Override public void onEndOfSpeech() { if (mine()) lastAlive = SystemClock.elapsedRealtime(); }
        @Override public void onEvent(int eventType, Bundle params) {}

        @Override public void onPartialResults(Bundle b) {
            if (!mine()) return;
            lastAlive = SystemClock.elapsedRealtime();
            String t = first(b);
            if (t != null && !t.trim().isEmpty()) send(s, "partial", t, null);
        }

        @Override public void onResults(Bundle b) {
            if (!mine()) return;
            done = true;
            String t = first(b);
            if (t != null && !t.trim().isEmpty()) { send(s, "final", t, null); errorsInRow = 0; }
            if (stopping) { endSession(true); return; }
            // Straight back to listening, on the same recogniser, so the next words aren't missed.
            if (a == attempt) listen();
        }

        @Override public void onError(int error) {
            if (!mine()) return;
            done = true;
            if (a != attempt) return;
            failed(error);
        }
    }
}
