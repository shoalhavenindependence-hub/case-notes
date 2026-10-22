package com.shoalhavenindependence.casenotes;

import android.content.Intent;
import android.media.AudioAttributes;
import android.os.Bundle;
import android.speech.tts.TextToSpeech;
import android.speech.tts.UtteranceProgressListener;
import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

/**
 * Hands-free note taking (for example in the car): speaks short prompts aloud with the
 * phone's own text-to-speech, tells the app when it was opened from the "Hands-free note"
 * shortcut, and tells it when the app comes back to the front.
 */
@CapacitorPlugin(name = "HandsFree")
public class HandsFreePlugin extends Plugin {

    static final String ACTION_HANDS_FREE = "com.shoalhavenindependence.casenotes.HANDS_FREE";

    private TextToSpeech tts;
    private boolean ttsReady;
    private boolean ttsFailed;
    private int nextId;
    private final Map<String, PluginCall> speaking = new HashMap<>();
    private final List<PluginCall> waitingForTts = new ArrayList<>();

    @Override
    public void load() {
        tts = new TextToSpeech(getContext(), status -> {
            if (status == TextToSpeech.SUCCESS) {
                tts.setLanguage(new Locale("en", "AU"));
                // Speak like sat-nav: other audio (music, radio) goes quieter while it talks.
                tts.setAudioAttributes(new AudioAttributes.Builder()
                    .setUsage(AudioAttributes.USAGE_ASSISTANCE_NAVIGATION_GUIDANCE)
                    .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                    .build());
                tts.setOnUtteranceProgressListener(new UtteranceProgressListener() {
                    @Override public void onStart(String id) {}
                    @Override public void onDone(String id) { finish(id); }
                    @Override public void onError(String id) { finish(id); }
                    @Override public void onStop(String id, boolean interrupted) { finish(id); }
                });
                ttsReady = true;
            } else {
                ttsFailed = true;
            }
            List<PluginCall> calls = new ArrayList<>(waitingForTts);
            waitingForTts.clear();
            for (PluginCall c : calls) speak(c);
        });
    }

    /** Says the text aloud and resolves once it has finished (or straight away if the phone can't speak). */
    @PluginMethod
    public void speak(PluginCall call) {
        if (ttsFailed) { call.resolve(); return; }
        if (!ttsReady) { waitingForTts.add(call); return; }
        String id = "u" + (nextId++);
        synchronized (speaking) { speaking.put(id, call); }
        Bundle params = new Bundle();
        params.putString(TextToSpeech.Engine.KEY_PARAM_UTTERANCE_ID, id);
        if (tts.speak(call.getString("text", ""), TextToSpeech.QUEUE_FLUSH, params, id) != TextToSpeech.SUCCESS) finish(id);
    }

    @PluginMethod
    public void stopSpeaking(PluginCall call) {
        if (ttsReady) tts.stop();
        call.resolve();
    }

    /** True once if the app was opened from the "Hands-free note" shortcut. */
    @PluginMethod
    public void takeLaunch(PluginCall call) {
        Intent intent = getActivity().getIntent();
        boolean handsFree = intent != null && ACTION_HANDS_FREE.equals(intent.getAction());
        if (handsFree) intent.setAction(Intent.ACTION_MAIN);
        call.resolve(new JSObject().put("handsFree", handsFree));
    }

    private void finish(String id) {
        PluginCall call;
        synchronized (speaking) { call = speaking.remove(id); }
        if (call != null) call.resolve();
    }

    @Override
    protected void handleOnNewIntent(Intent intent) {
        super.handleOnNewIntent(intent);
        if (intent != null && ACTION_HANDS_FREE.equals(intent.getAction())) {
            intent.setAction(Intent.ACTION_MAIN);
            notifyListeners("shortcut", new JSObject());
        }
    }

    @Override
    protected void handleOnResume() {
        super.handleOnResume();
        notifyListeners("resume", new JSObject());
    }

    @Override
    protected void handleOnPause() {
        super.handleOnPause();
        notifyListeners("pause", new JSObject());
    }

    @Override
    protected void handleOnDestroy() {
        super.handleOnDestroy();
        if (tts != null) tts.shutdown();
    }
}
